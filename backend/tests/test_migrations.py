"""
backend/tests/test_migrations.py

Schema migrations (backend/migrate.py, backend/migrations/):
  - the migrations and the models describe the same schema (drift guard:
    changing a model without writing a migration fails here)
  - a real database written by v0.7.0 (fixtures/v0_7_0.db) is backed up,
    adopted, upgraded, and the app then works on it
  - older installs (no FK indexes, missing columns) are repaired on adoption
  - failures roll back completely; unknown/newer schemas are refused
  - restoring an old encrypted backup upgrades it before it replaces the live DB
"""

import shutil
import sqlite3
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.migrate as migrate
from backend.database import Base, get_db, init_db
from backend.main import app
from backend.migrate import MigrationError, head_revision, upgrade_database
from backend.services.backup import make_backup, restore_backup

FIXTURE = Path(__file__).parent / "fixtures" / "v0_7_0.db"
FK_INDEXES = [
    "ix_ledger_entries_transaction_id", "ix_ledger_entries_account_id",
    "ix_bitcoin_lots_created_txn_id", "ix_lot_disposals_lot_id", "ix_lot_disposals_transaction_id",
]


def engine_for(path: Path):
    return create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})


def q(path: Path, sql: str):
    con = sqlite3.connect(str(path))
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def schema(path: Path) -> dict:
    return {
        name: " ".join(sql.split())
        for name, sql in q(path, "SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL")
        if name != "alembic_version"
    }


@pytest.fixture
def v070(tmp_path) -> Path:
    db = tmp_path / "btctx.db"
    shutil.copy(FIXTURE, db)
    return db


# ---------------------------------------------------------------------------
# Migrations vs models
# ---------------------------------------------------------------------------
def test_models_and_migrations_agree(tmp_path):
    """If this fails you changed a model without a migration (or vice versa).
    Write one: see docs/MAINTENANCE.md, "Database migrations"."""
    migrated, created = tmp_path / "migrated.db", tmp_path / "created.db"
    upgrade_database(engine_for(migrated))
    Base.metadata.create_all(engine_for(created))

    with engine_for(migrated).connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == []
    assert schema(migrated) == schema(created)


def test_fresh_database_goes_to_head_without_a_backup(tmp_path):
    db = tmp_path / "btctx.db"
    result = init_db(engine_for(db))
    assert (result.from_revision, result.to_revision) == (None, head_revision())
    assert result.backup is None and not (tmp_path / "backups").exists()
    assert q(db, "SELECT username FROM users") == [("admin",)]
    assert [r[0] for r in q(db, "SELECT id FROM accounts ORDER BY id")] == [1, 2, 3, 4, 5, 6]


def test_second_start_changes_nothing(tmp_path):
    db = tmp_path / "btctx.db"
    init_db(engine_for(db))
    result = init_db(engine_for(db))
    assert not result.changed and result.backup is None


# ---------------------------------------------------------------------------
# Adopting databases from before migrations
# ---------------------------------------------------------------------------
def old_columns(table: str) -> str:
    return ", ".join(row[1] for row in q(FIXTURE, f"PRAGMA table_info({table})"))


def test_v0_7_0_database_is_backed_up_adopted_and_usable(v070):
    cols = old_columns("transactions")
    before = q(v070, f"SELECT {cols} FROM transactions ORDER BY id")
    result = init_db(engine_for(v070))

    assert result.adopted and result.repairs == []
    assert q(v070, "SELECT version_num FROM alembic_version") == [(head_revision(),)]
    assert q(v070, f"SELECT {cols} FROM transactions ORDER BY id") == before
    assert q(v070, "SELECT DISTINCT broker_reporting FROM transactions") == [(None,)]  # 0003
    # the backup is the untouched v0.7.0 file
    assert result.backup.parent == v070.parent / "backups"
    assert oct(result.backup.stat().st_mode & 0o777) == "0o600"
    assert schema(result.backup) == schema(FIXTURE)

    # the current app works on it
    Session = sessionmaker(bind=engine_for(v070))

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    try:
        client = TestClient(app)
        assert client.post("/api/login", json={"username": "admin", "password": "password"}).status_code == 200
        assert len(client.get("/api/transactions").json()) == 7
        assert client.post("/api/transactions/recalculate").status_code == 200
        assert client.put("/api/settings/tax-timezone", json={"timezone": "America/Chicago"}).status_code == 200
        pdf = client.get("/api/reports/irs_reports", params={"year": 2024})
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous


def test_pre_2026_database_gets_its_missing_indexes(v070):
    con = sqlite3.connect(str(v070))
    for name in FK_INDEXES:  # added to the models in Jan 2026 (v0.5.x DBs lack them)
        con.execute(f"DROP INDEX {name}")
    con.commit()
    con.close()

    result = init_db(engine_for(v070))
    assert sorted(result.repairs) == sorted(f"created index {n}" for n in FK_INDEXES)
    after, original = schema(v070), schema(FIXTURE)
    assert {n: after[n] for n in FK_INDEXES} == {n: original[n] for n in FK_INDEXES}


def test_missing_nullable_columns_are_added_and_data_kept(v070):
    con = sqlite3.connect(str(v070))
    con.execute("ALTER TABLE transactions DROP COLUMN fmv_usd")
    con.execute("ALTER TABLE transactions DROP COLUMN gross_proceeds_usd")
    con.commit()
    con.close()
    ids = q(v070, "SELECT id, type, amount FROM transactions ORDER BY id")

    result = init_db(engine_for(v070))
    assert set(result.repairs) == {
        "added column transactions.gross_proceeds_usd", "added column transactions.fmv_usd",
    }
    assert q(v070, "SELECT id, type, amount FROM transactions ORDER BY id") == ids


def test_dev_build_database_with_app_settings_keeps_its_settings(v070):
    con = sqlite3.connect(str(v070))
    con.execute("CREATE TABLE app_settings (key VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (key))")
    con.execute("INSERT INTO app_settings VALUES ('tax_timezone', 'America/Denver')")
    con.commit()
    con.close()

    init_db(engine_for(v070))
    assert q(v070, "SELECT value FROM app_settings") == [("America/Denver",)]


def test_foreign_database_is_refused(tmp_path):
    db = tmp_path / "other.db"
    q(db, "CREATE TABLE notes (id INTEGER)")
    with pytest.raises(MigrationError, match="isn't a BitcoinTX database"):
        upgrade_database(engine_for(db))
    assert q(db, "SELECT name FROM sqlite_master WHERE type='table'") == [("notes",)]


def test_newer_schema_is_refused(tmp_path):
    db = tmp_path / "btctx.db"
    init_db(engine_for(db))
    con = sqlite3.connect(str(db))
    con.execute("UPDATE alembic_version SET version_num = 'ffff'")
    con.commit()
    con.close()
    with pytest.raises(MigrationError, match="newer version"):
        upgrade_database(engine_for(db))


def test_failed_upgrade_rolls_back_completely(v070, monkeypatch):
    real_upgrade = migrate.command.upgrade

    def upgrade_then_fail(cfg, target):
        real_upgrade(cfg, target)
        if target == "head":  # the real upgrade, after adoption's repairs + stamp
            raise RuntimeError("disk on fire")

    con = sqlite3.connect(str(v070))
    con.execute(f"DROP INDEX {FK_INDEXES[0]}")
    con.commit()
    con.close()
    before = schema(v070)

    monkeypatch.setattr(migrate.command, "upgrade", upgrade_then_fail)
    with pytest.raises(MigrationError, match="disk on fire") as err:
        upgrade_database(engine_for(v070))

    # adoption stamp, index repair and the app_settings table are all gone
    assert schema(v070) == before
    assert not q(v070, "SELECT name FROM sqlite_master WHERE name = 'alembic_version'")
    assert "backups" in str(err.value)


# ---------------------------------------------------------------------------
# Restoring encrypted backups
# ---------------------------------------------------------------------------
@pytest.fixture
def live(tmp_path):
    """A current, migrated live database with one user renamed so we can
    tell it apart from a restored one."""
    db = tmp_path / "live" / "btctx.db"
    db.parent.mkdir()
    engine = engine_for(db)
    init_db(engine)
    q_con = sqlite3.connect(str(db))
    q_con.execute("UPDATE users SET username = 'live-user'")
    q_con.commit()
    q_con.close()
    return db, engine


def test_restoring_a_v0_7_0_backup_upgrades_it(tmp_path, live):
    db, engine = live
    btx = tmp_path / "old.btx"
    make_backup("pw", btx, db_path=FIXTURE)

    result = restore_backup("pw", btx, db_path=db, engine=engine)

    assert result.adopted and result.to_revision == head_revision()
    assert q(db, "SELECT version_num FROM alembic_version") == [(head_revision(),)]
    assert q(db, "SELECT count(*) FROM transactions") == [(7,)]
    kept = list((db.parent / "backups").glob("btctx-before-restore-*.db"))
    assert len(kept) == 1 and q(kept[0], "SELECT username FROM users") == [("live-user",)]
    assert not (db.parent / "btctx.db.restoring").exists()


@pytest.mark.parametrize("case", ["wrong-password", "not-a-database", "newer-schema"])
def test_bad_restore_leaves_the_live_database_alone(tmp_path, live, case):
    db, engine = live
    before = q(db, "SELECT username FROM users")
    btx = tmp_path / "x.btx"
    if case == "not-a-database":
        junk = tmp_path / "junk.db"
        junk.write_bytes(b"hello" * 100)
        from backend.services import backup as svc
        salt, iv = b"s" * svc.SALT_LENGTH, b"i" * svc.IV_LENGTH
        btx.write_bytes(salt + iv + svc._encrypt_data(junk.read_bytes(), svc._derive_key("pw", salt), iv))
    else:
        newer = tmp_path / "newer.db"
        init_db(engine_for(newer))
        if case == "newer-schema":
            con = sqlite3.connect(str(newer))
            con.execute("UPDATE alembic_version SET version_num = 'ffff'")
            con.commit()
            con.close()
        make_backup("pw", btx, db_path=newer)

    with pytest.raises(ValueError):
        restore_backup("wrong" if case == "wrong-password" else "pw", btx, db_path=db, engine=engine)
    assert q(db, "SELECT username FROM users") == before
    assert not (db.parent / "btctx.db.restoring").exists()
    assert not (db.parent / "backups").exists()
