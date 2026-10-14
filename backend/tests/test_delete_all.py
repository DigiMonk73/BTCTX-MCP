"""
Deleting every transaction (#256): Settings' Delete All and Create account
on an install with transactions need the typed confirmation (DELETE), say
first what would go, and keep a copy of the database before anything goes
(backups/, "before-delete", newest 5, apart from the other copies).
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import migrate
from backend.main import app
from backend.services import first_run

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


def test_no_copy_no_delete(ledger, monkeypatch):
    def full_disk(*args, **kwargs):
        raise OSError("No space left on device")

    monkeypatch.setattr("backend.services.wipe.backup_sqlite", full_disk)
    r = ledger.delete(CONFIRMED)
    assert r.status_code == 500
    assert "Not deleted" in r.json()["detail"]
    assert count(ledger) == 3


def test_the_ai_key_can_neither_delete_everything_nor_ask_what_would_go(ledger, ai_key_headers):
    key_only = TestClient(app)
    assert key_only.get(DELETE_ALL, headers=ai_key_headers).status_code == 403
    assert key_only.delete(CONFIRMED, headers=ai_key_headers).status_code == 403
    assert count(ledger) == 3


# Create account (POST /api/users/reset-account) on a database of its own
CLAIM = {"username": "me", "password": "n3w-passw0rd"}


def anon() -> TestClient:
    return TestClient(app)


def with_transactions(n=2) -> None:
    """Transactions on the fresh install's default login."""
    me = anon()
    assert me.post("/api/login", json={"username": "admin", "password": "password",
                                       "setup_code": first_run.ensure_code()}).status_code == 200
    for i in range(n):
        deposit(me, f"202{4 + i}-01-02T12:00:00Z")


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
