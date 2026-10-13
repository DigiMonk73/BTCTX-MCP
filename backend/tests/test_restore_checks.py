"""
An in-app restore brings back a backup's data, never its database as it is.
The backup's database must hold only ordinary tables and indexes (checked
before anything runs in it); it is upgraded to the current schema, and only
the rows of BitcoinTX's own tables and columns are copied into a new
database made by BitcoinTX's own migrations. This install's login, AI key
and switch, and price settings are written into that database and read
back before it replaces the live one. Anything that stops the restore
leaves the live database and the price settings in memory as they were,
answers in plain words, and leaves no temporary file (#151, #201).

Each test restores a real encrypted backup over a database of its own in a
temp folder. The genuine ones (v0.7.0, revision 0007, current) are compared
table by table with what starting the app on the same file gives.
"""

import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

import backend.database
import backend.migrate
from backend.database import get_db, seed_defaults
from backend.main import app
from backend.migrate import alembic_config, upgrade_database
from backend.models.user import User
from backend.routers import backup as backup_router
from backend.schemas.transaction import TransactionCreate
from backend.services import ai_key, backup, outbound
from backend.services.transaction import create_transaction_record
from backend.tests.conftest import init_test_db

OWNER = {"username": "owner", "password": "owner-password-123"}
OTHER = {"username": "other", "password": "other-password-123"}
BACKUP_PASSWORD = "backup-password"
TOR = "socks5h://127.0.0.1:9050"
BANK, EXCHANGE_BTC = 1, 4
REPO = Path(__file__).resolve().parents[2]
V0_7_0 = Path(__file__).parent / "fixtures" / "v0_7_0.db"
STOPPED = "Restore failed: This install's login, AI key and price settings couldn't be kept in the " \
          "restored backup, so the restore stopped. Your database is unchanged."
DAMAGED = "Restore failed: This file isn't a BitcoinTX backup, or it's damaged."


def _engine(path):
    return create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})


def _install(path, login, prices, buys):
    """A database as an install has it: its own login, an AI key with access
    on, a price choice and a few buys. Returns its engine and AI key."""
    engine = _engine(path)
    init_test_db(engine)
    with sessionmaker(bind=engine)() as db:
        user = db.query(User).order_by(User.id).first()
        user.username = login["username"]
        user.set_password(login["password"])
        db.commit()
        token = ai_key.create_key(db)
        ai_key.set_access(db, True)
        for day, amount in buys:
            tx = TransactionCreate(type="Buy", timestamp=f"{day}T12:00:00Z", from_account_id=BANK,
                                   to_account_id=EXCHANGE_BTC, amount=amount, cost_basis_usd="20000")
            create_transaction_record(tx.model_dump(), db)
    _settings(engine, prices)
    return engine, token


def _settings(engine, rows: dict) -> None:
    with engine.begin() as conn:
        for key, value in rows.items():
            conn.execute(text("INSERT OR REPLACE INTO app_settings (key, value) VALUES (:k, :v)"),
                         {"k": key, "v": value})


@pytest.fixture
def live(tmp_path, auth_client, monkeypatch):
    """
    This install: a database of its own that the app uses and a restore
    replaces (the owner's login, an AI key, public prices through Tor, two
    buys), its price settings loaded as at startup, and a client logged in
    as its owner.
    """
    path = tmp_path / "data" / "btctx.db"
    path.parent.mkdir()
    prices = {outbound.SOURCE_KEY: "public", outbound.FALLBACK_KEY: "off", outbound.PROXY_KEY: TOR,
              outbound.CHOSEN_AT_KEY: "2026-01-02T03:04:05Z", outbound.CHOSEN_VIA_KEY: "settings"}
    engine, token = _install(path, OWNER, prices, [("2024-01-10", "1.0"), ("2024-02-10", "0.5")])
    Session = sessionmaker(bind=engine)
    with Session() as db:
        outbound.load(db)
        carried = {**outbound.snapshot(db), **ai_key.snapshot(db)}

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(backup, "DB_PATH", path)
    monkeypatch.setattr(backend.database, "engine", engine)
    client = TestClient(app)
    assert client.post("/api/login", json=OWNER).status_code == 200
    yield SimpleNamespace(path=path, engine=engine, token=token, client=client, carried=carried)
    app.dependency_overrides[get_db] = previous
    engine.dispose()


def _other(tmp_path, *sql, name="other"):
    """Another install's database (another login, AI key, price choice and
    buy), with `sql` run in it. Returns its path and AI key."""
    path = tmp_path / name / "btctx.db"
    path.parent.mkdir()
    prices = {outbound.SOURCE_KEY: "public", outbound.FALLBACK_KEY: "off",
              outbound.CHOSEN_AT_KEY: "2025-05-05T05:05:05Z", outbound.CHOSEN_VIA_KEY: "first-run"}
    engine, token = _install(path, OTHER, prices, [("2023-03-03", "2.0")])
    with engine.begin() as conn:
        for statement in sql:
            conn.exec_driver_sql(statement)
    engine.dispose()
    return path, token


def _sealed(data: bytes) -> bytes:
    return backup.encrypt_backup(data, BACKUP_PASSWORD, backup.MIN_ITERATIONS)


def _backup(tmp_path, *sql):
    """An encrypted backup of another install's database; returns its bytes and AI key."""
    path, token = _other(tmp_path, *sql)
    return _sealed(path.read_bytes()), token


def _restore(client, blob):
    return client.post("/api/backup/restore", data={"password": BACKUP_PASSWORD},
                       files={"file": ("b.btx", blob)})


def _stored(engine) -> dict:
    """Everything a stopped restore must leave as it was."""
    with engine.connect() as conn:
        return {
            "settings": dict(conn.execute(text("SELECT key, value FROM app_settings")).all()),
            "users": conn.execute(text("SELECT id, username, password_hash FROM users")).all(),
            "transactions": conn.execute(text("SELECT * FROM transactions ORDER BY id")).all(),
            "lots": conn.execute(text("SELECT * FROM bitcoin_lots ORDER BY id")).all(),
            "objects": conn.execute(text("SELECT type, name, sql FROM sqlite_master ORDER BY type, name")).all(),
        }


def _amounts(engine) -> list:
    with engine.connect() as conn:
        return [float(a) for (a,) in conn.execute(text("SELECT amount FROM transactions ORDER BY id"))]


def _logs_in(client, login) -> bool:
    return client.post("/api/login", json=login).status_code == 200


def _key_works(token) -> bool:
    return TestClient(app).get("/api/transactions", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def _temp_files(live) -> list:
    """The restore's temporary files and anything SQLite kept beside them."""
    return sorted(p.name for p in live.path.parent.iterdir()
                  if p.name.startswith((live.path.name + ".restoring", live.path.name + ".rebuilding")))


def _side_files(live) -> list:
    return sorted(p.name for p in live.path.parent.iterdir()
                  if p.name in {live.path.name + s for s in ("-wal", "-shm", "-journal")})


def _schema(path) -> list:
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT type, name, tbl_name, sql FROM sqlite_master "
                           "WHERE name != 'alembic_version' ORDER BY type, name").fetchall()
    finally:
        con.close()


@pytest.fixture(scope="module")
def fresh(tmp_path_factory):
    """A database as BitcoinTX's migrations make it for a fresh install."""
    path = tmp_path_factory.mktemp("fresh") / "btctx.db"
    engine = _engine(path)
    upgrade_database(engine, backup=False)
    engine.dispose()
    return path


@pytest.fixture(scope="module")
def fresh_schema(fresh):
    return _schema(fresh)


def _assert_nothing_changed(live, before, in_memory, copy_made=False):
    assert _stored(live.engine) == before
    assert outbound.as_dict() == in_memory
    assert _temp_files(live) == []
    assert (live.path.parent / "backups").exists() == copy_made  # a pre-restore copy only once everything passed
    assert _logs_in(live.client, OWNER)
    assert not _logs_in(live.client, OTHER)
    assert _key_works(live.token)


def _assert_refused(live, sql_or_blob, detail, tmp_path):
    before = _stored(live.engine)
    in_memory = outbound.as_dict()
    blob = sql_or_blob if isinstance(sql_or_blob, bytes) else _backup(tmp_path, *sql_or_blob)[0]

    r = _restore(live.client, blob)

    assert r.status_code == 400, r.text
    assert r.json()["detail"] == detail
    _assert_nothing_changed(live, before, in_memory)


# A backup that restores
def test_an_ordinary_backup_restores_and_keeps_this_installs_settings(live, tmp_path, fresh_schema):
    before = _stored(live.engine)
    blob, other_token = _backup(tmp_path)

    r = _restore(live.client, blob)

    assert r.status_code == 200, r.text
    after = _stored(live.engine)
    assert after["settings"] == before["settings"]  # the AI key and switch, the price settings
    assert after["users"] == before["users"]
    assert _amounts(live.engine) == [2.0]  # the backup's ledger
    assert _schema(live.path) == fresh_schema
    assert outbound.current().proxy_url == TOR and outbound.current().price_source == "public"
    assert _logs_in(live.client, OWNER)
    assert not _logs_in(live.client, OTHER)
    assert _key_works(live.token) and not _key_works(other_token)
    kept = list((live.path.parent / "backups").glob("btctx-before-restore-*.db"))
    assert len(kept) == 1
    copy = _engine(kept[0])
    assert _amounts(copy) == [1.0, 0.5]  # the ledger it replaced
    copy.dispose()
    assert _temp_files(live) == [] and _side_files(live) == []


# What a backup's database may hold: only BitcoinTX's kind of objects
@pytest.mark.parametrize("sql", [
    ["CREATE TRIGGER users_after_update AFTER UPDATE ON users BEGIN "
     "UPDATE users SET username = OLD.username, password_hash = OLD.password_hash WHERE id = NEW.id; END",
     "CREATE TRIGGER app_settings_after_update AFTER UPDATE ON app_settings BEGIN "
     "UPDATE app_settings SET value = OLD.value WHERE key = NEW.key; END"],
    ["CREATE VIEW buys AS SELECT id, amount FROM transactions WHERE type = 'Buy'"],
    ["CREATE VIRTUAL TABLE notes USING fts5(body)", "INSERT INTO notes VALUES ('a note')"],
], ids=["triggers", "view", "virtual table"])
def test_a_backup_holding_objects_bitcointx_doesnt_make_is_refused(live, tmp_path, sql):
    _assert_refused(live, sql, "Restore failed: This backup can't be restored: it holds database "
                               "objects BitcoinTX doesn't make.", tmp_path)
    with live.engine.connect() as conn:
        assert not conn.execute(text("SELECT name FROM sqlite_master WHERE type IN ('trigger', 'view') "
                                     "OR name LIKE 'notes%'")).all()


def test_an_extra_table_and_column_stay_behind(live, tmp_path, fresh_schema):
    """Plain data BitcoinTX doesn't read: the restore copies only its own
    tables and columns, so these don't reach the live database."""
    blob, _ = _backup(tmp_path, "CREATE TABLE notes (body TEXT)", "INSERT INTO notes VALUES ('a note')",
                      "ALTER TABLE transactions ADD COLUMN memo TEXT", "UPDATE transactions SET memo = 'x'")

    r = _restore(live.client, blob)

    assert r.status_code == 200, r.text
    assert _schema(live.path) == fresh_schema
    assert _amounts(live.engine) == [2.0]


def test_the_backups_table_definitions_stay_behind(live, tmp_path, fresh_schema):
    """A backup's own definition of a table (here a CHECK that keeps AI
    access on and public prices, values this install already has) doesn't
    reach the live database: the owner can still change them."""
    blob, _ = _backup(
        tmp_path,
        "ALTER TABLE app_settings RENAME TO app_settings_old",
        "CREATE TABLE app_settings (key VARCHAR NOT NULL PRIMARY KEY, value VARCHAR NOT NULL, "
        "CHECK (key != 'mcp_access' OR value = 'on'), CHECK (key != 'price_source' OR value = 'public'))",
        "INSERT INTO app_settings SELECT key, value FROM app_settings_old",
        "DROP TABLE app_settings_old",
    )

    r = _restore(live.client, blob)

    assert r.status_code == 200, r.text
    assert _schema(live.path) == fresh_schema
    assert _logs_in(live.client, OWNER)
    assert live.client.put("/api/settings/ai-access", json={"on": False}).status_code == 200
    off = {"price_source": "off", "mempool_url": None, "mempool_fallback": False, "proxy_url": TOR}
    assert live.client.put("/api/settings/network", json=off).status_code == 200
    with live.engine.connect() as conn:
        stored = dict(conn.execute(text("SELECT key, value FROM app_settings")).all())
    assert (stored[ai_key.ACCESS_KEY], stored[outbound.SOURCE_KEY]) == ("off", "off")


def test_a_second_login_is_refused(live, tmp_path):
    """BitcoinTX has one login, and the restore keeps only this install's."""
    second = User(username="second", password_hash="")
    second.set_password("second-password-123")
    _assert_refused(live, [f"INSERT INTO users (username, password_hash) VALUES ('second', '{second.password_hash}')"],
                    "Restore failed: This backup can't be restored: it holds more than one login, "
                    "and BitcoinTX has one.", tmp_path)
    assert not _logs_in(live.client, {"username": "second", "password": "second-password-123"})


def test_rows_that_dont_fit_bitcointxs_tables_are_refused(live, tmp_path):
    """Here app_settings without its primary key, holding a key twice."""
    _assert_refused(live, [
        "CREATE TABLE app_settings_new (key VARCHAR NOT NULL, value VARCHAR NOT NULL)",
        "INSERT INTO app_settings_new SELECT key, value FROM app_settings",
        "INSERT INTO app_settings_new VALUES ('mcp_access', 'on')",
        "DROP TABLE app_settings",
        "ALTER TABLE app_settings_new RENAME TO app_settings",
    ], "Restore failed: This backup can't be restored: its app_settings rows don't fit BitcoinTX's database.",
        tmp_path)


def test_a_column_bitcointx_needs_missing_is_refused(live, tmp_path):
    _assert_refused(live, ["ALTER TABLE transactions DROP COLUMN price_moment"],
                    "Restore failed: This backup can't be restored: its database lacks "
                    "transactions.price_moment, which BitcoinTX needs.", tmp_path)


# Damaged files: plain words, never SQL
def _damaged(path: Path, how: str) -> bytes:
    data = bytearray(path.read_bytes())
    if how == "truncated":
        return bytes(data[:len(data) // 2])
    if how == "header only":
        return bytes(data[:100])
    con = sqlite3.connect(path)
    page_size, root = con.execute("PRAGMA page_size").fetchone()[0], con.execute(
        "SELECT rootpage FROM sqlite_master WHERE name = 'transactions'").fetchone()[0]
    con.close()
    data[(root - 1) * page_size:root * page_size] = b"\xa5" * page_size  # the transactions table's page
    return bytes(data)


@pytest.mark.parametrize("how", ["truncated", "header only", "garbage page"])
def test_a_damaged_file_answers_in_plain_words(live, tmp_path, how):
    path, _ = _other(tmp_path)
    _assert_refused(live, _sealed(_damaged(path, how)), DAMAGED, tmp_path)


def test_a_database_that_cant_be_upgraded_answers_in_plain_words(live, tmp_path):
    """Stamped 0009 though it has 0010's columns: the upgrade fails on SQL
    the answer doesn't show."""
    _assert_refused(live, ["UPDATE alembic_version SET version_num = '0009'"],
                    "Restore failed: This backup can't be restored: its database couldn't be brought up "
                    "to this version of BitcoinTX.", tmp_path)


# Every failure leaves no temporary file
@pytest.mark.parametrize("step", ["copy of the live database", "swap"])
def test_a_failure_at_the_last_steps_leaves_no_temporary_file(live, tmp_path, monkeypatch, step):
    before = _stored(live.engine)
    in_memory = outbound.as_dict()
    blob, _ = _backup(tmp_path)
    if step == "swap":
        real_replace = backup.os.replace

        def replace(src, dst):
            if Path(dst) == live.path:
                raise OSError("No space left on device")
            return real_replace(src, dst)

        monkeypatch.setattr(backup.os, "replace", replace)
    else:
        def no_copy(*args, **kwargs):
            raise OSError("No space left on device")

        monkeypatch.setattr(backend.migrate, "backup_sqlite", no_copy)

    r = _restore(live.client, blob)

    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "Restore failed: No space left on device"
    _assert_nothing_changed(live, before, in_memory, copy_made=step == "swap")


def test_no_write_ahead_log_stays_beside_the_live_database(live, tmp_path):
    """
    A backup in write-ahead-log mode restores into the migrations' own
    rollback journal. And a live database left in that mode by an earlier
    restore, with a connection still holding writes in its log, leaves no
    -wal or -shm file beside the new one: opened with it, that log would be
    read as the new database's.
    """
    with live.engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
    held = sqlite3.connect(live.path)
    held.execute("INSERT INTO app_settings (key, value) VALUES ('written_before', 'x')")
    held.commit()  # in the log, not yet in the database file
    path, _ = _other(tmp_path, name="wal")
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.close()
    assert path.read_bytes()[18:20] == b"\x02\x02"
    try:
        r = _restore(live.client, _sealed(path.read_bytes()))

        assert r.status_code == 200, r.text
        assert _side_files(live) == [] and _temp_files(live) == []
        assert live.path.read_bytes()[18:20] == b"\x01\x01"  # rollback journal
        assert _logs_in(live.client, OWNER)
        assert _amounts(live.engine) == [2.0]
        with live.engine.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
            assert conn.exec_driver_sql("SELECT count(*) FROM app_settings WHERE key = 'written_before'").scalar() == 0
    finally:
        held.close()
    kept = next((live.path.parent / "backups").glob("btctx-before-restore-*.db"))
    with closing(sqlite3.connect(kept)) as copy:  # the pre-restore copy has what the log held
        assert copy.execute("SELECT value FROM app_settings WHERE key = 'written_before'").fetchone() == ("x",)


# A carry-over that can't complete
def _fails(*args):
    raise OperationalError("UPDATE app_settings SET value=?", (), Exception("disk I/O error"))


@pytest.mark.parametrize("module, name", [
    (outbound, "carry_over"), (ai_key, "carry_over"), (backup_router, "_keep_login"),
], ids=["price settings", "AI key", "login"])
def test_a_carry_over_that_fails_stops_the_restore(live, tmp_path, monkeypatch, module, name):
    """#201: such an error was only logged, and the backup's settings stayed."""
    monkeypatch.setattr(module, name, _fails)
    _assert_refused(live, [], STOPPED, tmp_path)


def _prices_without_proxy(real):
    return lambda db, before: real(db, {**before, outbound.PROXY_KEY: None})


def _ai_access_off(real):
    return lambda db, before: real(db, {**before, ai_key.ACCESS_KEY: "off"})


def _another_password(real):
    return lambda db, login: real(db, (login[0], "not-the-hash"))


@pytest.mark.parametrize("module, name, differently", [
    (outbound, "carry_over", _prices_without_proxy),
    (ai_key, "carry_over", _ai_access_off),
    (backup_router, "_keep_login", _another_password),
], ids=["price settings", "AI key", "login"])
def test_a_value_that_doesnt_read_back_as_written_stops_the_restore(live, tmp_path, monkeypatch,
                                                                     module, name, differently):
    monkeypatch.setattr(module, name, differently(getattr(module, name)))
    _assert_refused(live, [], STOPPED, tmp_path)


# Genuine backups: every row of BitcoinTX's tables comes back as it was
@pytest.fixture(scope="module")
def reference_db(tmp_path_factory):
    """The reference test ledger (testdata/reference_ledger.json: every kind
    of transaction, with its lots, disposals and ledger lines), stored daily
    and hourly prices, and settings of its own, at the current schema."""
    path = tmp_path_factory.mktemp("reference") / "btctx.db"
    engine = _engine(path)
    init_test_db(engine)
    rows = json.loads((REPO / "testdata" / "reference_ledger.json").read_text())["transactions"]
    with sessionmaker(bind=engine)() as db:
        for row in rows:
            data = TransactionCreate(**{k: v for k, v in row.items() if k != "why"}).model_dump()
            create_transaction_record(data, db)
    with engine.begin() as conn:
        for day, usd in (("2023-01-15", "21000.00"), ("2024-06-01", "67000.50"), ("2025-03-03", "86000.25")):
            conn.execute(text("INSERT INTO btc_price_daily (day, usd, source) VALUES (:d, :u, 'bitstamp')"),
                         {"d": day, "u": usd})
        for hour, usd in ((1704067200, "42000.10"), (1704070800, "42100.20")):
            conn.execute(text("INSERT INTO btc_price_hourly (hour, usd, source) VALUES (:h, :u, 'bitstamp')"),
                         {"h": hour, "u": usd})
    _settings(engine, {"tax_timezone": "America/Chicago", outbound.SOURCE_KEY: "public",
                       outbound.FALLBACK_KEY: "off", ai_key.ACCESS_KEY: "on", ai_key.HASH_KEY: "0" * 64})
    engine.dispose()
    return path


def _at_revision(source: Path, dest: Path, revision: str) -> Path:
    shutil.copy(source, dest)
    engine = _engine(dest)
    with engine.begin() as conn:
        cfg = alembic_config()
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, revision)
    engine.dispose()
    return dest


def _started_on(source: Path, dest: Path) -> Path:
    """What starting the app on this database gives (upgraded in place,
    defaults seeded): the data a restore of it must bring back."""
    shutil.copy(source, dest)
    engine = _engine(dest)
    upgrade_database(engine, backup=False)
    seed_defaults(engine)
    engine.dispose()
    return dest


def _table_rows(path: Path, fresh: Path) -> dict:
    """Every table the migrations make, in their columns, as sorted rows."""
    reference = sqlite3.connect(fresh)
    con = sqlite3.connect(path)
    try:
        tables = {}
        for (name,) in reference.execute("SELECT name FROM sqlite_master WHERE type = 'table' "
                                         "AND name != 'alembic_version'"):
            columns = ", ".join(f'"{c[1]}"' for c in reference.execute(f'PRAGMA table_info("{name}")'))
            tables[name] = sorted(con.execute(f'SELECT {columns} FROM "{name}"').fetchall(), key=repr)
        return tables
    finally:
        con.close()
        reference.close()


@pytest.mark.parametrize("source", ["v0.7.0", "0007", "current"])
def test_a_genuine_backup_brings_back_every_row(live, tmp_path, reference_db, fresh, source):
    if source == "v0.7.0":
        backup_file = V0_7_0
    elif source == "0007":
        backup_file = _at_revision(reference_db, tmp_path / "at-0007.db", "0007")
    else:
        backup_file = reference_db
    expected = _table_rows(_started_on(backup_file, tmp_path / "expected.db"), fresh)

    r = _restore(live.client, _sealed(backup_file.read_bytes()))

    assert r.status_code == 200, r.text
    restored = _table_rows(live.path, fresh)
    assert _schema(live.path) == _schema(fresh)
    users = restored.pop("users")
    assert len(users) == 1 and users[0][0] == expected.pop("users")[0][0]  # the same id, this install's login
    settings, expected_settings = dict(restored.pop("app_settings")), dict(expected.pop("app_settings"))
    assert {k: v for k, v in settings.items() if k not in live.carried} == \
        {k: v for k, v in expected_settings.items() if k not in live.carried}
    assert {k: settings.get(k) for k in live.carried} == live.carried
    assert restored == expected
    assert restored["transactions"] and restored["ledger_entries"] and restored["bitcoin_lots"]
    if source != "v0.7.0":
        assert restored["lot_disposals"] and restored["btc_price_daily"]
    assert _logs_in(live.client, OWNER) and _key_works(live.token)
