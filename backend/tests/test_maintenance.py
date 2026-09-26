"""
backend/tests/test_maintenance.py

What the StartOS package (and any admin) relies on besides the web UI:
  - GET /api/health: public, 200 only when the database answers at the
    current schema, reveals nothing about the ledger
  - python -m backend.cli migrate / set-password / recalculate, run as real
    subprocesses against a temp DATABASE_FILE
  - LOG_LEVEL (default INFO, not DEBUG)
  - only the newest BACKUPS_KEPT pre-upgrade copies stay in <db dir>/backups/
"""

import logging
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.migrate as migrate
from backend.database import get_db, init_db, log_level_from_env
from backend.main import app
from backend.migrate import BACKUPS_KEPT, backup_sqlite, head_revision
from backend.version import app_version

REPO = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "v0_7_0.db"


def q(path: Path, sql: str):
    con = sqlite3.connect(str(path))
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def engine_for(path: Path):
    return create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})


def client_on(path: Path) -> TestClient:
    """Anonymous client whose requests use the database at `path`."""
    Session = sessionmaker(bind=engine_for(path))

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app)


@pytest.fixture
def restore_overrides():
    previous = dict(app.dependency_overrides)
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


def cli(db: Path, *args: str, stdin: str = "", env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = {k: v for k, v in os.environ.items() if k != "BTCTX_NEW_PASSWORD"}
    full_env.update(DATABASE_FILE=str(db), **(env or {}))
    return subprocess.run(
        [sys.executable, "-m", "backend.cli", *args],
        cwd=REPO, env=full_env, input=stdin, capture_output=True, text=True, timeout=120,
    )


def can_login(db: Path, username: str, password: str) -> bool:
    r = client_on(db).post("/api/login", json={"username": username, "password": password})
    return r.status_code == 200


# ---------------------------------------------------------------------------
# /api/health
# ---------------------------------------------------------------------------
def test_health_is_public_and_reports_version_and_schema(tmp_path, restore_overrides):
    db = tmp_path / "btctx.db"
    init_db(engine_for(db))
    r = client_on(db).get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": app_version(), "schema": head_revision()}


def test_health_version_is_the_version_file():
    assert app_version() == (REPO / "VERSION").read_text().strip()


def test_health_fails_when_the_schema_is_behind(tmp_path, restore_overrides):
    db = tmp_path / "btctx.db"
    init_db(engine_for(db))
    con = sqlite3.connect(str(db))
    con.execute("UPDATE alembic_version SET version_num = '0001'")
    con.commit()
    con.close()
    r = client_on(db).get("/api/health")
    assert r.status_code == 503
    assert r.json()["status"] == "error" and r.json()["schema"] == "0001"


def test_health_fails_on_an_empty_database(tmp_path, restore_overrides):
    r = client_on(tmp_path / "empty.db").get("/api/health")
    assert r.status_code == 503 and r.json()["schema"] is None


# ---------------------------------------------------------------------------
# python -m backend.cli
# ---------------------------------------------------------------------------
def test_cli_migrate_builds_a_fresh_database_then_is_idempotent(tmp_path):
    db = tmp_path / "data" / "btctx.db"
    db.parent.mkdir()
    r = cli(db, "migrate")
    assert r.returncode == 0, r.stderr
    assert f"-> {head_revision()}" in r.stdout
    assert q(db, "SELECT version_num FROM alembic_version") == [(head_revision(),)]
    assert q(db, "SELECT username FROM users") == [("admin",)]

    r = cli(db, "migrate")
    assert r.returncode == 0 and "up to date" in r.stdout
    assert not (db.parent / "backups").exists()


def test_cli_migrate_upgrades_v0_7_0_with_a_backup(tmp_path):
    db = tmp_path / "btctx.db"
    shutil.copy(FIXTURE, db)
    r = cli(db, "migrate")
    assert r.returncode == 0, r.stderr
    assert "Copy of the previous database" in r.stdout
    assert len(list((tmp_path / "backups").glob("btctx-before-*.db"))) == 1


def test_cli_migrate_refuses_a_newer_schema(tmp_path):
    db = tmp_path / "btctx.db"
    init_db(engine_for(db))
    con = sqlite3.connect(str(db))
    con.execute("UPDATE alembic_version SET version_num = 'ffff_from_the_future'")
    con.commit()
    con.close()
    r = cli(db, "migrate")
    assert r.returncode == 1 and "newer version" in r.stderr


def test_cli_set_password_from_stdin_on_an_empty_volume(tmp_path, restore_overrides):
    db = tmp_path / "btctx.db"
    r = cli(db, "set-password", "--username", "admin", "--password-stdin", stdin="S3cret-from-stdin\n")
    assert r.returncode == 0, r.stderr
    assert can_login(db, "admin", "S3cret-from-stdin")
    assert not can_login(db, "admin", "password")


def test_cli_set_password_from_env_keeps_the_username(tmp_path, restore_overrides):
    db = tmp_path / "btctx.db"
    init_db(engine_for(db))
    con = sqlite3.connect(str(db))
    con.execute("UPDATE users SET username = 'satoshi'")
    con.commit()
    con.close()
    r = cli(db, "set-password", env={"BTCTX_NEW_PASSWORD": "from-the-env"})
    assert r.returncode == 0, r.stderr
    assert can_login(db, "satoshi", "from-the-env")


def test_cli_set_password_renames_back_to_admin(tmp_path, restore_overrides):
    db = tmp_path / "btctx.db"
    init_db(engine_for(db))
    con = sqlite3.connect(str(db))
    con.execute("UPDATE users SET username = 'satoshi'")
    con.commit()
    con.close()
    r = cli(db, "set-password", "--username", "admin", "--password-stdin", stdin="reset-pw")
    assert r.returncode == 0, r.stderr
    assert can_login(db, "admin", "reset-pw")


@pytest.mark.parametrize(
    "args, stdin, message",
    [
        (["set-password"], "", "No password given"),
        (["set-password", "--password-stdin"], "\n", "No password given"),
        (["set-password", "--password-stdin"], "x" * 73, "72 bytes"),
        (["set-password", "--username", " ", "--password-stdin"], "pw", "username can't be empty"),
    ],
)
def test_cli_set_password_rejects_bad_input_without_changing_anything(tmp_path, args, stdin, message, restore_overrides):
    db = tmp_path / "btctx.db"
    init_db(engine_for(db))
    r = cli(db, *args, stdin=stdin)
    assert r.returncode == 1 and message in r.stderr
    assert can_login(db, "admin", "password")


def test_cli_set_password_takes_no_password_argument(tmp_path):
    r = cli(tmp_path / "btctx.db", "set-password", "hunter2")
    assert r.returncode == 2


def test_cli_recalculate_runs_on_an_empty_ledger(tmp_path):
    r = cli(tmp_path / "btctx.db", "recalculate")
    assert r.returncode == 0, r.stderr
    assert "Recalculated 0 transaction(s)." in r.stdout


def test_cli_recalculate_rebuilds_the_ledger(tmp_path, monkeypatch, capsys):
    # In-process so the session's stubbed BTC prices apply (the fixture has an
    # unpriced spend whose FMV is looked up); the subprocess path is covered above.
    import backend.database as database
    from backend import cli as backend_cli

    db = tmp_path / "btctx.db"
    shutil.copy(FIXTURE, db)
    engine = engine_for(db)
    init_db(engine)
    con = sqlite3.connect(str(db))
    con.execute("DELETE FROM ledger_entries")
    con.execute("DELETE FROM lot_disposals")
    con.execute("DELETE FROM bitcoin_lots")
    con.commit()
    con.close()

    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(database, "init_db", lambda: init_db(engine))
    assert backend_cli.main(["recalculate"]) == 0
    assert "Recalculated 7 transaction(s)." in capsys.readouterr().out
    assert q(db, "SELECT COUNT(*) FROM ledger_entries")[0][0] > 0
    assert q(db, "SELECT COUNT(*) FROM bitcoin_lots")[0][0] > 0



def test_cli_review_lists_zero_proceeds_spends_and_lost(tmp_path, monkeypatch, capsys):
    """Read-only list of what to check after v0.9.2 (F1 and F2)."""
    import backend.database as database
    from backend import cli as backend_cli

    db = tmp_path / "btctx.db"
    engine = engine_for(db)
    init_db(engine)
    con = sqlite3.connect(str(db))
    rows = [  # id, purpose, gross proceeds
        (1, "Spent", "0.00"), (2, "Spent", "5000.00"), (3, "Spent", None), (4, "Lost", None), (5, "Gift", None),
    ]
    for tx_id, purpose, gross in rows:
        con.execute(
            "INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount,"
            " fee_amount, fee_currency, purpose, gross_proceeds_usd, is_locked)"
            " VALUES (?, 'Withdrawal', '2024-05-01 12:00:00', 2, 99, '0.1', '0', 'BTC', ?, ?, 0)",
            (tx_id, purpose, gross),
        )
    con.commit()
    before = q(db, "SELECT COUNT(*), SUM(id) FROM transactions")
    con.close()

    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(database, "init_db", lambda: init_db(engine))
    assert backend_cli.main(["review"]) == 0
    out = capsys.readouterr().out
    assert "Spent withdrawals with $0 proceeds: 1\n  #1 " in out
    assert "Lost withdrawals (loss removed by Recalculate Ledger): 1\n  #4 " in out
    assert q(db, "SELECT COUNT(*), SUM(id) FROM transactions") == before  # read-only

# ---------------------------------------------------------------------------
# LOG_LEVEL
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value, level",
    [(None, logging.INFO), ("debug", logging.DEBUG), (" WARNING ", logging.WARNING),
     ("error", logging.ERROR), ("nonsense", logging.INFO), ("", logging.INFO)],
)
def test_log_level_from_env(monkeypatch, value, level):
    if value is None:
        monkeypatch.delenv("LOG_LEVEL", raising=False)
    else:
        monkeypatch.setenv("LOG_LEVEL", value)
    assert log_level_from_env() == level


def test_the_app_no_longer_logs_debug_by_default(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "LOG_LEVEL"}
    env["DATABASE_FILE"] = str(tmp_path / "btctx.db")
    code = "import logging, backend.database; print(logging.getLogger().getEffectiveLevel())"
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == str(logging.INFO)


# ---------------------------------------------------------------------------
# Retention of pre-upgrade copies
# ---------------------------------------------------------------------------
def test_only_the_newest_copies_are_kept(tmp_path):
    db = tmp_path / "btctx.db"
    init_db(engine_for(db))
    backups = tmp_path / "backups"
    backups.mkdir()
    unrelated = backups / "my-own-notes.db"
    unrelated.write_bytes(b"keep me")

    made = []
    for i in range(BACKUPS_KEPT + 3):
        path = backup_sqlite(db, f"test-{i}")
        # distinct, increasing mtimes regardless of filesystem timestamp resolution
        os.utime(path, ns=(1_700_000_000_000_000_000 + i * 10**9,) * 2)
        made.append(path)
    migrate.prune_backups(db)

    kept = sorted(backups.glob("btctx-before-*.db"))
    assert kept == sorted(made[-BACKUPS_KEPT:])
    assert unrelated.read_bytes() == b"keep me"
