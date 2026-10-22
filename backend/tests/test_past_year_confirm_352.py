"""
The confirmed save (5.8, B6b-7): a write sent again with ?confirm=<the
409's fingerprint> takes the database's write lock (database.
take_write_lock), makes a copy of the database under it (with a login a
"pre-change" copy; with the AI key a fresh AI copy at every confirmed
write), makes the write and its comparison again and commits only while
the fingerprint is the same: if the ledger changed since the 409, a new
409, nothing saved. No price is asked for under the lock (#442): a price
the write still needs rolls the try back, its copy with it, is found with
the lock free, and the write runs again; one confirmed save, one copy.

"This tax year" is 2026 here, set after each ledger goes in.
"""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import text

from backend.migrate import AI_CHANGE_LABEL, PRE_CHANGE_KIND, backup_copies
from backend.services import past_year_saves, price_history, year_changes
from backend.tests.past_years_ledger import own_app

WALLET, EXTERNAL = 2, 99


@pytest.fixture
def app_db(auth_client, tmp_path):
    yield from own_app(tmp_path)


def deposit(when: str, amount: str = "1", basis: str = "40000") -> dict:
    return {"type": "Deposit", "timestamp": when, "from_account_id": EXTERNAL, "to_account_id": WALLET,
            "amount": amount, "source": "MyBTC", "cost_basis_usd": basis, "fee_amount": "0", "fee_currency": "BTC"}


def spend(when: str, amount: str = "0.5", proceeds: str | None = "30000") -> dict:
    return {"type": "Withdrawal", "timestamp": when, "from_account_id": WALLET, "to_account_id": EXTERNAL,
            "amount": amount, "purpose": "Spent", "proceeds_usd": proceeds, "fee_amount": "0", "fee_currency": "BTC"}


def add(client, row: dict) -> int:
    r = client.post("/api/transactions", json=row)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def rows_in(path) -> int:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    finally:
        conn.close()


def lock_free(path) -> bool:
    other = sqlite3.connect(path, timeout=0)
    try:
        other.execute("BEGIN IMMEDIATE")
        other.rollback()
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        other.close()


@pytest.fixture
def ledger(app_db, tax_year):
    """1 BTC deposited in 2024, half spent in 2025, a deposit in 2026,
    recalculated; then this tax year is 2026. Yields (path, owner, ai, ids)."""
    path, Session, owner, ai = app_db
    ids = {"deposit": add(owner, deposit("2024-01-02T12:00:00Z")),
           "spend": add(owner, spend("2025-03-01T12:00:00Z")),
           "this year": add(owner, deposit("2026-02-01T12:00:00Z", "0.1", basis="9000"))}
    assert owner.post("/api/transactions/recalculate").status_code == 200
    tax_year(2026)
    yield path, owner, ai, ids


def confirmed_edit(client, tx_id: int, fields: dict):
    asked = client.put(f"/api/transactions/{tx_id}", json=fields)
    assert asked.status_code == 409, asked.text
    return client.put(f"/api/transactions/{tx_id}?confirm={asked.json()['confirm']}", json=fields)


@pytest.mark.parametrize("write", ["add", "edit", "delete"])
def test_a_confirmed_save_comes_after_one_pre_change_copy_of_the_ledger_as_it_was(ledger, write):
    path, owner, _, ids = ledger
    if write == "add":
        row = deposit("2025-01-15T12:00:00Z", "0.2")
        asked = owner.post("/api/transactions", json=row)
        r = owner.post(f"/api/transactions?confirm={asked.json()['confirm']}", json=row)
    elif write == "edit":
        r = confirmed_edit(owner, ids["deposit"], {"cost_basis_usd": "50000"})
    else:
        asked = owner.delete(f"/api/transactions/{ids['spend']}")
        r = owner.delete(f"/api/transactions/{ids['spend']}?confirm={asked.json()['confirm']}")
    assert r.status_code in (200, 204), r.text
    copies = backup_copies(path, PRE_CHANGE_KIND)
    assert len(copies) == 1
    assert rows_in(copies[0]) == 3  # from before the save
    assert backup_copies(path, "ai") == []


def test_a_409_or_a_write_in_this_year_makes_no_copy(ledger):
    path, owner, _, ids = ledger
    assert owner.put(f"/api/transactions/{ids['deposit']}", json={"cost_basis_usd": "50000"}).status_code == 409
    assert owner.put(f"/api/transactions/{ids['this year']}", json={"amount": "0.2"}).status_code == 200
    assert backup_copies(path, PRE_CHANGE_KIND) == []


def test_a_stale_fingerprint_gets_a_new_409_and_saves_nothing(ledger):
    path, owner, _, ids = ledger
    fields = {"cost_basis_usd": "50000"}
    old = owner.put(f"/api/transactions/{ids['deposit']}", json=fields).json()
    # Meanwhile another save changes 2025 (the AI and the owner at once)
    assert confirmed_edit(owner, ids["spend"], {"proceeds_usd": "31000"}).status_code == 200
    r = owner.put(f"/api/transactions/{ids['deposit']}?confirm={old['confirm']}", json=fields)
    assert r.status_code == 409, r.text
    assert r.json()["confirm"] != old["confirm"]
    assert owner.get(f"/api/transactions/{ids['deposit']}").json()["cost_basis_usd"] == "40000.00"
    r = owner.put(f"/api/transactions/{ids['deposit']}?confirm={r.json()['confirm']}", json=fields)
    assert r.status_code == 200, r.text


def test_with_the_ai_key_each_confirmed_save_makes_a_fresh_ai_copy(ledger):
    path, _, ai, ids = ledger
    assert confirmed_edit(ai, ids["deposit"], {"cost_basis_usd": "50000"}).status_code == 200
    assert confirmed_edit(ai, ids["deposit"], {"cost_basis_usd": "51000"}).status_code == 200
    # The hour's copy came before the first unconfirmed edit; each confirmed one made its own
    assert len(backup_copies(path, "ai", label=AI_CHANGE_LABEL)) == 3
    assert backup_copies(path, PRE_CHANGE_KIND) == []


def test_the_write_and_its_comparison_hold_the_write_lock(ledger, monkeypatch):
    path, owner, _, ids = ledger
    fields = {"cost_basis_usd": "50000"}
    asked = owner.put(f"/api/transactions/{ids['deposit']}", json=fields).json()
    held = []
    real = year_changes.figures

    def check_lock(db, tz):
        held.append(not lock_free(path))
        return real(db, tz)

    monkeypatch.setattr(year_changes, "figures", check_lock)
    r = owner.put(f"/api/transactions/{ids['deposit']}?confirm={asked['confirm']}", json=fields)
    assert r.status_code == 200, r.text
    assert held and all(held)


def test_busy_saving_something_else_saves_nothing(ledger, monkeypatch):
    path, owner, _, ids = ledger
    fields = {"cost_basis_usd": "50000"}
    asked = owner.put(f"/api/transactions/{ids['deposit']}", json=fields).json()
    monkeypatch.setattr(past_year_saves, "take_write_lock", lambda db: False)
    r = owner.put(f"/api/transactions/{ids['deposit']}?confirm={asked['confirm']}", json=fields)
    assert (r.status_code, r.json()["detail"]) == (
        503, "Not changed: BitcoinTX was busy saving something else. Try again.")
    assert backup_copies(path, PRE_CHANGE_KIND) == []


@pytest.mark.parametrize("write, verb", [("edit", "Not changed"), ("delete", "Not deleted"), ("add", "Not added")])
def test_no_copy_no_save(ledger, monkeypatch, write, verb):
    path, owner, _, ids = ledger

    def no_copy(*args, **kwargs):
        raise OSError("disk full")

    if write == "add":
        row = deposit("2025-01-15T12:00:00Z", "0.2")
        send = lambda confirm="": owner.post(f"/api/transactions?confirm={confirm}" if confirm else "/api/transactions",
                                             json=row)
    elif write == "edit":
        send = lambda confirm="": owner.put(f"/api/transactions/{ids['deposit']}" + (
            f"?confirm={confirm}" if confirm else ""), json={"cost_basis_usd": "50000"})
    else:
        send = lambda confirm="": owner.delete(f"/api/transactions/{ids['spend']}" + (
            f"?confirm={confirm}" if confirm else ""))
    confirm = send().json()["confirm"]
    monkeypatch.setattr(past_year_saves, "backup_sqlite", no_copy)
    r = send(confirm)
    assert (r.status_code, r.json()["detail"]) == (
        500, f"{verb}: BitcoinTX couldn't make its copy of the database first.")
    assert rows_in(path) == 3
    assert owner.get(f"/api/transactions/{ids['deposit']}").json()["cost_basis_usd"] == "40000.00"


def test_a_refused_confirmed_save_leaves_no_copy(ledger):
    path, owner, _, ids = ledger
    asked = owner.put(f"/api/transactions/{ids['deposit']}", json={"cost_basis_usd": "50000"}).json()
    r = owner.put(f"/api/transactions/{ids['spend']}?confirm={asked['confirm']}", json={"amount": "2"})
    assert r.status_code == 400, r.text  # more than the wallet holds: the save's own refusal
    assert backup_copies(path, PRE_CHANGE_KIND) == []


def test_a_price_the_confirmed_save_needs_is_asked_for_with_the_lock_free_and_leaves_one_copy(
        app_db, tax_year, monkeypatch):
    path, Session, owner, _ = app_db
    add(owner, deposit("2024-01-02T12:00:00Z"))
    spent = add(owner, spend("2025-03-01T12:00:00Z", proceeds=None))  # priced at the day: marked
    assert owner.post("/api/transactions/recalculate").status_code == 200
    tax_year(2026)
    asks = []

    async def find_prices(day, full):
        price_history.refuse_if_held()  # where the real lookup's request would go out
        asks.append(lock_free(path))
        return {day: (Decimal("60000.00"), "stub")}, False  # not the day before's: its proceeds move

    monkeypatch.setattr(price_history, "find_prices", find_prices)
    fields = {"timestamp": "2025-03-09T12:00:00Z"}  # another day: its proceeds priced again
    asked = owner.put(f"/api/transactions/{spent}", json=fields)
    assert asked.status_code == 409, asked.text
    with Session() as db:  # the dry run's price stayed on its scratch copy
        db.execute(text("DELETE FROM btc_price_daily WHERE day = '2025-03-09'"))
        db.commit()
    price_history.reset_state()
    asks.clear()
    r = owner.put(f"/api/transactions/{spent}?confirm={asked.json()['confirm']}", json=fields)
    assert r.status_code == 200, r.text
    assert asks and all(asks)
    assert len(backup_copies(path, PRE_CHANGE_KIND)) == 1
