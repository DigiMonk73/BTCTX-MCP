"""
Deleting every transaction (#256): Settings' Delete All and Create account
on an install with transactions need the typed confirmation (DELETE), say
first what would go, and keep a copy of the database before anything goes
(backups/, "before-delete", newest 5, apart from the other copies). The
copy and the delete hold the write lock together (#276).
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import migrate
from backend.database import get_db
from backend.main import app
from backend.services import first_run, wipe

DELETE_ALL = "/api/transactions/delete_all"
CONFIRMED = f"{DELETE_ALL}?confirm=DELETE"


def deposit(client, when="2024-03-01T12:00:00Z", amount="100"):
    r = client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": when, "from_account_id": 99, "to_account_id": 1,
        "amount": amount, "fee_amount": "0", "fee_currency": "USD",
    })
    assert r.status_code in (200, 201), r.text


def count(client) -> int:
    return len(client.get("/api/transactions").json())


def delete_copies(engine) -> list[Path]:
    return migrate.backup_copies(Path(engine.url.database), migrate.DELETE_KIND)


def rows_in(copy: Path) -> int:
    con = sqlite3.connect(copy)
    try:
        return con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    finally:
        con.close()


@pytest.fixture
def ledger(auth_client):
    """Three transactions over two tax years (UTC), none after."""
    auth_client.delete(CONFIRMED)
    deposit(auth_client, "2023-06-01T12:00:00Z")
    deposit(auth_client, "2024-03-01T12:00:00Z")
    deposit(auth_client, "2024-09-01T12:00:00Z")
    yield auth_client
    auth_client.delete(CONFIRMED)


def test_delete_all_says_what_would_go_and_deletes_nothing_unconfirmed(ledger, test_engine):
    before = delete_copies(test_engine)
    assert ledger.get(DELETE_ALL).json() == {"transactions": 3, "first_year": 2023, "last_year": 2024}
    for url in (DELETE_ALL, f"{DELETE_ALL}?confirm=delete", f"{DELETE_ALL}?confirm=yes"):
        r = ledger.delete(url)
        assert r.status_code == 409, r.text
        assert r.json()["transactions"] == 3
        assert "3 transactions, 2023–2024" in r.json()["detail"]
        assert count(ledger) == 3
    assert delete_copies(test_engine) == before  # no copy without a delete


def test_delete_all_keeps_a_copy_of_the_ledger_first(ledger, test_engine):
    assert ledger.delete(CONFIRMED).status_code == 204
    assert count(ledger) == 0
    newest = delete_copies(test_engine)[0]
    assert newest.name.startswith("btctx-before-delete-all-")
    assert rows_in(newest) == 3  # the ledger as it was
    assert ledger.get(DELETE_ALL).json() == {"transactions": 0, "first_year": None, "last_year": None}


def test_an_empty_ledger_needs_no_confirmation_and_gets_no_copy(auth_client, test_engine):
    auth_client.delete(CONFIRMED)
    before = delete_copies(test_engine)
    assert auth_client.delete(DELETE_ALL).status_code == 204
    assert delete_copies(test_engine) == before


def test_the_newest_five_delete_copies_are_kept_apart_from_the_others(auth_client, test_engine):
    db = Path(test_engine.url.database)
    upgrade_copy = db.parent / migrate.BACKUP_DIRNAME / f"{db.stem}-before-schema-0010-20260101T000000Z.db"
    upgrade_copy.parent.mkdir(exist_ok=True)
    upgrade_copy.write_bytes(b"")
    try:
        for n in range(7):
            deposit(auth_client, amount=str(n + 1))
            assert auth_client.delete(CONFIRMED).status_code == 204
        assert len(delete_copies(test_engine)) == migrate.DELETE_COPIES_KEPT
        assert upgrade_copy.exists()  # never pushed out by the deletes
        assert migrate.backup_copies(db, "before") == [upgrade_copy]
    finally:
        upgrade_copy.unlink(missing_ok=True)


def test_the_copy_just_made_is_kept_even_when_the_clock_went_back(ledger, test_engine):
    """Five copies dated after now (a clock set back): the new one is the
    oldest by date, and pruning used to delete it right after it was made."""
    import os
    import time
    later = time.time() + 86400
    db = Path(test_engine.url.database)
    folder = db.parent / migrate.BACKUP_DIRNAME
    folder.mkdir(exist_ok=True)
    future = []
    for n in range(migrate.DELETE_COPIES_KEPT):
        copy = folder / f"{db.stem}-before-delete-all-20990101T00000{n}Z.db"
        copy.write_bytes(b"")
        os.utime(copy, (later + n, later + n))
        future.append(copy)
    try:
        assert ledger.delete(CONFIRMED).status_code == 204
        made = [c for c in delete_copies(test_engine) if c not in future]
        assert len(made) == 1 and rows_in(made[0]) == 3
    finally:
        for copy in future:
            copy.unlink(missing_ok=True)


def test_one_transaction_reads_as_one(auth_client):
    auth_client.delete(CONFIRMED)
    deposit(auth_client)
    r = auth_client.delete(DELETE_ALL)
    assert r.status_code == 409 and r.json()["detail"] == "This deletes 1 transaction, 2024. To go ahead, confirm with DELETE."
    auth_client.delete(CONFIRMED)


def test_no_copy_no_delete(ledger, monkeypatch):
    def full_disk(*args, **kwargs):
        raise OSError("No space left on device")

    monkeypatch.setattr("backend.services.wipe.backup_sqlite", full_disk)
    r = ledger.delete(CONFIRMED)
    assert r.status_code == 500
    assert "Not deleted" in r.json()["detail"]
    assert count(ledger) == 3


def test_a_save_during_the_copy_waits_until_after_the_delete(ledger, test_engine, monkeypatch):
    """#276: a transaction saved between the copy and the delete was in
    neither. Now it waits for the delete (here it gives up at once)."""
    real_copy = wipe.backup_sqlite
    saving = []

    def copy_then_save(db_path, *args, **kwargs):
        dest = real_copy(db_path, *args, **kwargs)
        other = sqlite3.connect(db_path, timeout=0.1)  # the AI connector, saving
        try:
            other.execute("INSERT INTO transactions (type, timestamp) VALUES ('Deposit', '2024-12-01T12:00:00Z')")
            other.commit()
            saving.append("saved")
        except sqlite3.OperationalError as e:
            saving.append(str(e))
        finally:
            other.close()
        return dest

    monkeypatch.setattr(wipe, "backup_sqlite", copy_then_save)
    assert ledger.delete(CONFIRMED).status_code == 204
    assert saving == ["database is locked"]  # it had to wait
    assert rows_in(delete_copies(test_engine)[0]) == 3
    assert count(ledger) == 0


def test_the_ai_key_can_neither_delete_everything_nor_ask_what_would_go(ledger, ai_key_headers):
    key_only = TestClient(app)
    assert key_only.get(DELETE_ALL, headers=ai_key_headers).status_code == 403
    assert key_only.delete(CONFIRMED, headers=ai_key_headers).status_code == 403
    assert count(ledger) == 3


# Create account (POST /api/users/reset-account) on a database of its own
CLAIM = {"username": "me", "password": "n3w-passw0rd"}


def anon() -> TestClient:
    return TestClient(app)


def with_transactions(n=2) -> TestClient:
    """Transactions on the fresh install's default login; its client."""
    me = anon()
    assert me.post("/api/login", json={"username": "admin", "password": "password",
                                       "setup_code": first_run.ensure_code()}).status_code == 200
    for i in range(n):
        deposit(me, f"202{4 + i}-01-02T12:00:00Z")
    return me


@pytest.fixture
def impatient_app(fresh_app):
    """fresh_app's database, its requests waiting at most 0.1 s for SQLite's
    write lock (5 s in the app). Yields the engine."""
    engine = create_engine(fresh_app.kw["bind"].url, connect_args={"check_same_thread": False, "timeout": 0.1})
    Session = sessionmaker(bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = override
    yield engine
    app.dependency_overrides[get_db] = previous
    engine.dispose()


def test_a_busy_database_deletes_nothing(impatient_app):
    """Another save holding the write lock longer than the wait: nothing
    copied, nothing deleted, and a message that says so (#276)."""
    me = with_transactions()
    other = sqlite3.connect(impatient_app.url.database)
    other.execute("BEGIN IMMEDIATE")  # an import, saving
    try:
        r = me.delete(CONFIRMED)
    finally:
        other.rollback()
        other.close()
    assert r.status_code == 503 and r.json()["detail"].startswith("Not deleted"), r.text
    assert count(me) == 2
    assert delete_copies(impatient_app) == []


def test_create_account_with_transactions_asks_once_the_code_is_right(fresh_app):
    with_transactions()
    code = first_run.ensure_code()
    # A wrong code is refused before anything is said about the ledger
    r = anon().post("/api/users/reset-account", json=dict(CLAIM, setup_code="WRNG-WRNG-WRNG"))
    assert r.status_code == 403 and "transactions" not in r.json()
    # The right one: what would go, and nothing changes
    r = anon().post("/api/users/reset-account", json=dict(CLAIM, setup_code=code))
    assert r.status_code == 409, r.text
    assert r.json()["transactions"] == 2 and "2024–2025" in r.json()["detail"]
    assert anon().get("/api/users/setup-status").json()["is_default"] is True
    # Confirmed: a copy, then the new login on an empty ledger
    r = anon().post("/api/users/reset-account", json=dict(CLAIM, setup_code=code, confirm="DELETE"))
    assert r.status_code == 200, r.text
    engine = fresh_app.kw["bind"]
    assert rows_in(delete_copies(engine)[0]) == 2
    me = anon()
    assert me.post("/api/login", json=CLAIM).status_code == 200
    assert count(me) == 0


def test_create_account_on_an_empty_install_asks_nothing(fresh_app):
    r = anon().post("/api/users/reset-account", json=dict(CLAIM, setup_code=first_run.ensure_code()))
    assert r.status_code == 200, r.text
    assert delete_copies(fresh_app.kw["bind"]) == []


def test_registering_again_needs_the_current_password_before_it_asks(fresh_app):
    with_transactions(1)
    assert anon().post("/api/users/reset-account",
                       json=dict(CLAIM, setup_code=first_run.ensure_code(), confirm="DELETE")).status_code == 200
    with_login = {"username": "me", "password": "n3w-passw0rd"}
    me = anon()
    assert me.post("/api/login", json=with_login).status_code == 200
    deposit(me)
    again = {"username": "me2", "password": "an0ther-passw0rd"}
    r = anon().post("/api/users/reset-account", json=dict(again, current_password="wrong-password"))
    assert r.status_code == 403 and "transactions" not in r.json()
    r = anon().post("/api/users/reset-account", json=dict(again, current_password="n3w-passw0rd"))
    assert r.status_code == 409 and r.json()["transactions"] == 1
    assert anon().post("/api/login", json=with_login).status_code == 200  # unchanged
