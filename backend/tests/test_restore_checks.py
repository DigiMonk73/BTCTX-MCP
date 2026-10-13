"""
An in-app restore brings back only BitcoinTX's kind of database (tables and
indexes), and writes this install's login, AI key and switch, and price
settings into the restored database before it replaces the live one, then
reads them back. Anything that stops either leaves the live database, and
the price settings in memory, as they were (#151, #201).

Each test restores a real encrypted backup, built with the real migrations,
over a database of its own in a temp folder.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

import backend.database
from backend.database import get_db
from backend.main import app
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


def _install(path, login, prices, buys):
    """A database as an install has it: its own login, an AI key with access
    on, a price choice and a few buys. Returns its engine and AI key."""
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
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
    with engine.begin() as conn:
        for key, value in prices.items():
            conn.execute(text("INSERT OR REPLACE INTO app_settings (key, value) VALUES (:k, :v)"),
                         {"k": key, "v": value})
    return engine, token


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
    yield SimpleNamespace(path=path, engine=engine, token=token, client=client)
    app.dependency_overrides[get_db] = previous
    engine.dispose()


def _backup(tmp_path, *sql):
    """An encrypted backup of another install (another login, AI key, price
    choice and buy), with `sql` run in its database first. Returns the file's
    bytes and that install's AI key."""
    path = tmp_path / "other" / "btctx.db"
    path.parent.mkdir()
    prices = {outbound.SOURCE_KEY: "public", outbound.FALLBACK_KEY: "off",
              outbound.CHOSEN_AT_KEY: "2025-05-05T05:05:05Z", outbound.CHOSEN_VIA_KEY: "first-run"}
    engine, token = _install(path, OTHER, prices, [("2023-03-03", "2.0")])
    with engine.begin() as conn:
        for statement in sql:
            conn.exec_driver_sql(statement)
    engine.dispose()
    blob = backup.encrypt_backup(path.read_bytes(), BACKUP_PASSWORD, backup.MIN_ITERATIONS)
    return blob, token


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
            "objects": conn.execute(text("SELECT type, name FROM sqlite_master ORDER BY type, name")).all(),
        }


def _amounts(engine) -> list:
    with engine.connect() as conn:
        return [float(a) for (a,) in conn.execute(text("SELECT amount FROM transactions ORDER BY id"))]


def _logs_in(client, login) -> bool:
    return client.post("/api/login", json=login).status_code == 200


def _key_works(token) -> bool:
    return TestClient(app).get("/api/transactions", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def _assert_nothing_changed(live, before, in_memory):
    assert _stored(live.engine) == before
    assert outbound.as_dict() == in_memory
    assert not live.path.with_name(live.path.name + ".restoring").exists()
    assert not (live.path.parent / "backups").exists()  # no pre-restore copy: nothing was replaced
    assert _logs_in(live.client, OWNER)
    assert not _logs_in(live.client, OTHER)
    assert _key_works(live.token)


def test_an_ordinary_backup_restores_and_keeps_this_installs_settings(live, tmp_path):
    before = _stored(live.engine)
    blob, other_token = _backup(tmp_path)

    r = _restore(live.client, blob)

    assert r.status_code == 200, r.text
    after = _stored(live.engine)
    assert after["settings"] == before["settings"]  # the AI key and switch, the price settings
    assert after["users"] == before["users"]
    assert _amounts(live.engine) == [2.0]  # the backup's ledger
    assert outbound.current().proxy_url == TOR and outbound.current().price_source == "public"
    assert _logs_in(live.client, OWNER)
    assert not _logs_in(live.client, OTHER)
    assert _key_works(live.token) and not _key_works(other_token)
    kept = list((live.path.parent / "backups").glob("btctx-before-restore-*.db"))
    assert len(kept) == 1
    copy = create_engine(f"sqlite:///{kept[0]}")
    assert _amounts(copy) == [1.0, 0.5]  # the ledger it replaced
    copy.dispose()
    assert not live.path.with_name(live.path.name + ".restoring").exists()


@pytest.mark.parametrize("sql", [
    ["CREATE TRIGGER users_after_update AFTER UPDATE ON users BEGIN "
     "UPDATE users SET username = OLD.username, password_hash = OLD.password_hash WHERE id = NEW.id; END",
     "CREATE TRIGGER app_settings_after_update AFTER UPDATE ON app_settings BEGIN "
     "UPDATE app_settings SET value = OLD.value WHERE key = NEW.key; END"],
    ["CREATE VIEW buys AS SELECT id, amount FROM transactions WHERE type = 'Buy'"],
], ids=["triggers", "view"])
def test_a_backup_holding_objects_bitcointx_doesnt_make_is_refused(live, tmp_path, sql):
    before = _stored(live.engine)
    in_memory = outbound.as_dict()
    blob, _ = _backup(tmp_path, *sql)

    r = _restore(live.client, blob)

    assert r.status_code == 400, r.text
    assert "holds database objects BitcoinTX doesn't make" in r.json()["detail"]
    _assert_nothing_changed(live, before, in_memory)
    with live.engine.connect() as conn:
        assert not conn.execute(text("SELECT name FROM sqlite_master WHERE type IN ('trigger', 'view')")).all()


def _fails(*args):
    raise OperationalError("UPDATE app_settings SET value=?", (), Exception("disk I/O error"))


@pytest.mark.parametrize("module, name", [
    (outbound, "carry_over"), (ai_key, "carry_over"), (backup_router, "_keep_login"),
], ids=["price settings", "AI key", "login"])
def test_a_carry_over_that_fails_stops_the_restore(live, tmp_path, monkeypatch, module, name):
    """#201: such an error was only logged, and the backup's settings stayed."""
    before = _stored(live.engine)
    in_memory = outbound.as_dict()
    blob, _ = _backup(tmp_path)
    monkeypatch.setattr(module, name, _fails)

    r = _restore(live.client, blob)

    assert r.status_code == 400, r.text
    assert "the restore stopped. Your database is unchanged." in r.json()["detail"]
    _assert_nothing_changed(live, before, in_memory)


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
    before = _stored(live.engine)
    in_memory = outbound.as_dict()
    blob, _ = _backup(tmp_path)
    monkeypatch.setattr(module, name, differently(getattr(module, name)))

    r = _restore(live.client, blob)

    assert r.status_code == 400, r.text
    assert "the restore stopped. Your database is unchanged." in r.json()["detail"]
    _assert_nothing_changed(live, before, in_memory)
