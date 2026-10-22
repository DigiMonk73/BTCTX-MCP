"""
Adds, edits and deletes through the past-year warning (5.8, B6b-6:
services/past_year_saves.py and the routes): 5.15's "Q4's reach" for them,
and its "Q4" tests of the dry run. A write that changes an earlier tax year
answers 409, saving nothing, with the years, the changes, the pending ones
and a fingerprint; the same request with ?confirm=<it> saves. A write in
this tax year saves at once with no dry run while nothing is pending; an
add after every other row into an earlier year "adds to" it, with no
replay. With a login pending changes alone never ask; with the AI key they
do. The dry run works on a scratch copy and leaves the live database
unlocked; a failed with pass answers as the save does; a failed without
pass doesn't stop the edit or the delete that repairs the ledger.

"This tax year" is 2026 here (conftest's tax_year), set after each ledger
goes in.
"""

import sqlite3

import pytest
from sqlalchemy import text

from backend.services import past_years, transaction, year_changes
from backend.tests.past_years_ledger import own_app

BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL, MISSING = 1, 2, 3, 4, 99, 999
FILED = "which you may already have filed. Confirm to save it: a copy of your ledger is made first."


@pytest.fixture
def app_db(auth_client, tmp_path):
    yield from own_app(tmp_path)


def deposit(when: str, amount: str = "1", to: int = WALLET, basis: str = "40000") -> dict:
    return {"type": "Deposit", "timestamp": when, "from_account_id": EXTERNAL, "to_account_id": to,
            "amount": amount, "source": "MyBTC" if to in (WALLET, EXCHANGE_BTC) else "N/A",
            "cost_basis_usd": basis, "fee_amount": "0", "fee_currency": "BTC"}


def spend(when: str, amount: str = "0.5", proceeds: str = "30000") -> dict:
    return {"type": "Withdrawal", "timestamp": when, "from_account_id": WALLET, "to_account_id": EXTERNAL,
            "amount": amount, "purpose": "Spent", "proceeds_usd": proceeds, "fee_amount": "0", "fee_currency": "BTC"}


def add(client, row: dict) -> int:
    r = client.post("/api/transactions", json=row)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def count(Session) -> int:
    with Session() as db:
        return db.execute(text("SELECT COUNT(*) FROM transactions")).scalar()


@pytest.fixture
def ledger(app_db, tax_year):
    """1 BTC deposited in 2024, half of it spent in 2025, a deposit in 2026,
    all recalculated (nothing pending); then this tax year is 2026. Yields
    (Session, owner, ai, {name: id})."""
    path, Session, owner, ai = app_db
    ids = {"deposit": add(owner, deposit("2024-01-02T12:00:00Z")),
           "spend": add(owner, spend("2025-03-01T12:00:00Z")),
           "this year": add(owner, deposit("2026-02-01T12:00:00Z", "0.1", basis="9000"))}
    assert owner.post("/api/transactions/recalculate").status_code == 200
    tax_year(2026)
    yield Session, owner, ai, ids


@pytest.fixture
def dry_runs(monkeypatch):
    """How many times the warning compared figures (year_changes.figures):
    0 when a write saved with no dry run."""
    calls = []
    real = year_changes.figures

    def counted(db, tz):
        calls.append(db)
        return real(db, tz)

    monkeypatch.setattr(year_changes, "figures", counted)
    return calls


def test_a_backdated_add_into_an_earlier_year_asks_and_saves_nothing(ledger):
    Session, owner, _, ids = ledger
    r = owner.post("/api/transactions", json=deposit("2025-01-15T12:00:00Z", "0.2", basis="8000"))
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"] == f"This changes the figures of tax year 2025, {FILED}"
    assert body["years"] == [2025]
    assert [(c["date"], c["type"], c["change"], c["years"]) for c in body["changes"]] == [
        ("2025-01-15 12:00", "Deposit", "Added.", [2025])]
    assert (body["pending"], body["recalc_error"]) == ([], None)
    assert len(body["confirm"]) == 64
    assert count(Session) == 3


def test_the_same_request_with_its_fingerprint_saves(ledger):
    Session, owner, _, _ = ledger
    row = deposit("2025-01-15T12:00:00Z", "0.2", basis="8000")
    confirm = owner.post("/api/transactions", json=row).json()["confirm"]
    assert owner.post("/api/transactions?confirm=not-it", json=row).status_code == 409
    assert count(Session) == 3
    r = owner.post(f"/api/transactions?confirm={confirm}", json=row)
    assert r.status_code == 200, r.text
    assert count(Session) == 4


def test_an_edit_into_an_earlier_year_lists_what_moves(ledger):
    Session, owner, _, ids = ledger
    r = owner.put(f"/api/transactions/{ids['deposit']}", json={"cost_basis_usd": "50000"})
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["years"] == [2024, 2025]
    assert body["detail"] == f"This changes the figures of tax years 2024 and 2025, {FILED}"
    changes = {c["id"]: c for c in body["changes"]}
    assert set(changes) == {ids["deposit"], ids["spend"]}
    assert changes[ids["spend"]]["change"].startswith("basis 20000.00 -> 25000.00; gain 10000.00 -> 5000.00")
    assert changes[ids["spend"]]["accounts"] == ["Wallet"]
    r = owner.put(f"/api/transactions/{ids['deposit']}?confirm={body['confirm']}", json={"cost_basis_usd": "50000"})
    assert r.status_code == 200, r.text
    assert owner.get(f"/api/transactions/{ids['spend']}").json()["realized_gain_usd"] == "5000.00"


def test_a_delete_in_an_earlier_year_asks(ledger):
    Session, owner, _, ids = ledger
    r = owner.delete(f"/api/transactions/{ids['spend']}")
    assert r.status_code == 409, r.text
    assert [(c["id"], c["change"]) for c in r.json()["changes"]] == [(ids["spend"], "Deleted.")]
    assert count(Session) == 3
    assert owner.delete(f"/api/transactions/{ids['spend']}?confirm={r.json()['confirm']}").status_code == 204
    assert count(Session) == 2


def test_a_write_in_this_year_saves_at_once_with_no_dry_run(ledger, dry_runs):
    _, owner, _, ids = ledger
    add(owner, deposit("2026-03-01T12:00:00Z", "0.1"))  # after the rest
    add(owner, deposit("2026-01-15T12:00:00Z", "0.1"))  # before the latest: a replay, still this year
    assert owner.put(f"/api/transactions/{ids['this year']}", json={"amount": "0.2"}).status_code == 200
    assert owner.delete(f"/api/transactions/{ids['this year']}").status_code == 204
    assert dry_runs == []


def test_an_add_after_every_row_into_an_earlier_year_adds_to_it_with_no_replay(app_db, tax_year, monkeypatch):
    _, Session, owner, _ = app_db
    add(owner, deposit("2025-01-02T12:00:00Z"))
    tax_year(2026)
    replays = []
    real = transaction.recalculate_all_transactions
    monkeypatch.setattr(transaction, "recalculate_all_transactions",
                        lambda db, *a, **k: replays.append(db) or real(db, *a, **k))
    r = owner.post("/api/transactions", json=spend("2025-03-01T12:00:00Z"))
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == f"This adds to tax year 2025, {FILED}"
    assert [c["change"] for c in r.json()["changes"]] == ["Added."]
    assert replays == []
    assert owner.post(f"/api/transactions?confirm={r.json()['confirm']}", json=spend("2025-03-01T12:00:00Z")
                      ).status_code == 200
    assert replays == []


def test_an_add_after_every_row_in_this_year_saves_at_once_even_while_something_is_pending(app_db, tax_year,
                                                                                            dry_runs):
    _, Session, owner, _ = app_db
    add(owner, deposit("2025-01-02T12:00:00Z"))  # never recalculated: recalculated_by doesn't match
    tax_year(2026)
    add(owner, deposit("2026-01-02T12:00:00Z"))
    assert dry_runs == []


def test_a_write_in_this_year_takes_the_dry_run_while_something_may_be_pending(app_db, tax_year, dry_runs):
    _, Session, owner, _ = app_db
    add(owner, deposit("2025-01-02T12:00:00Z"))
    this_year = add(owner, deposit("2026-01-02T12:00:00Z"))  # neither recalculated
    tax_year(2026)
    assert owner.put(f"/api/transactions/{this_year}", json={"amount": "0.5"}).status_code == 200
    assert dry_runs != []  # nothing moved in 2025: saved


def test_an_edit_that_moves_no_figure_saves_as_today(ledger):
    Session, owner, _, _ = ledger
    cash = add(owner, deposit("2026-01-03T12:00:00Z", "100", to=BANK, basis=None))
    r = owner.put(f"/api/transactions/{cash}", json={"timestamp": "2025-06-01T12:00:00Z"})
    assert r.status_code == 200, r.text  # dollars only: no gain, box or date moves


def make_pending(Session, tx_id: int) -> None:
    """A stored figure a recalculation would correct (Ledger Review's
    recalc_changes), as an older BitcoinTX could leave it."""
    with Session() as db:
        db.execute(text("UPDATE transactions SET realized_gain_usd = '9999.00' WHERE id = :id"), {"id": tx_id})
        db.execute(text("DELETE FROM app_settings WHERE key = 'recalculated_by'"))
        db.commit()


def test_with_a_login_pending_changes_alone_never_ask(ledger):
    Session, owner, _, ids = ledger
    make_pending(Session, ids["spend"])
    r = owner.put(f"/api/transactions/{ids['this year']}", json={"amount": "0.2"})
    assert r.status_code == 200, r.text  # "Don't warn for fixes"
    assert owner.get(f"/api/transactions/{ids['spend']}").json()["realized_gain_usd"] == "10000.00"  # applied


def test_with_the_ai_key_pending_changes_in_an_earlier_year_ask(ledger):
    Session, owner, ai, ids = ledger
    make_pending(Session, ids["spend"])
    r = ai.put(f"/api/transactions/{ids['this year']}", json={"amount": "0.2"})
    assert r.status_code == 409, r.text
    body = r.json()
    assert (body["years"], body["changes"]) == ([2025], [])
    assert [(p["id"], p["change"]) for p in body["pending"]] == [(ids["spend"], "gain 9999.00 -> 10000.00.")]
    r = ai.put(f"/api/transactions/{ids['this year']}?confirm={body['confirm']}", json={"amount": "0.2"})
    assert r.status_code == 200, r.text


def test_pending_changes_are_listed_apart_when_the_write_asks_anyway(ledger):
    Session, owner, _, ids = ledger
    make_pending(Session, ids["spend"])
    r = owner.post("/api/transactions", json=deposit("2024-06-01T12:00:00Z", "0.2"))
    assert r.status_code == 409, r.text
    assert [c["change"] for c in r.json()["changes"]] == ["Added."]
    assert [p["id"] for p in r.json()["pending"]] == [ids["spend"]]


def test_a_failed_with_pass_answers_as_the_save_does(ledger, tax_year):
    Session, owner, _, ids = ledger
    too_much = {"amount": "2"}
    asked = owner.put(f"/api/transactions/{ids['spend']}", json=too_much)
    tax_year(2009)
    plain = owner.put(f"/api/transactions/{ids['spend']}", json=too_much)
    assert asked.status_code == plain.status_code == 400
    assert asked.json() == plain.json()


@pytest.fixture
def missing_transfer(ledger):
    """5.13's case: an old Transfer from Wallet to a missing account (saved
    before v0.9.2), which stops every replay."""
    Session, owner, _, ids = ledger
    with Session() as db:
        db.execute(text(
            "INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount, fee_amount,"
            " fee_currency) VALUES (970, 'Transfer', '2024-02-01T12:00:00Z', :frm, :to, '0.1', '0', 'BTC')"),
            {"frm": WALLET, "to": MISSING})
        db.execute(text("DELETE FROM app_settings WHERE key = 'recalculated_by'"))
        db.commit()
    return ledger


def test_a_failed_without_pass_doesnt_stop_the_edit_that_repairs_the_row(missing_transfer):
    """Compared with the stored figures instead, with Recalculate Ledger's
    message: its lot moves into Exchange BTC in 2024."""
    _, owner, _, _ = missing_transfer
    fix = {"to_account_id": EXCHANGE_BTC}
    r = owner.put("/api/transactions/970", json=fix)
    assert r.status_code == 409, r.text
    assert r.json()["recalc_error"].startswith("Transaction 970 (a Transfer of 2024-02-01) names account 999")
    assert r.json()["years"] == [2024]
    assert owner.put(f"/api/transactions/970?confirm={r.json()['confirm']}", json=fix).status_code == 200
    assert owner.post("/api/transactions/recalculate").status_code == 200  # the ledger replays again


def test_a_failed_without_pass_doesnt_stop_the_delete_that_repairs_the_ledger(missing_transfer):
    """The row never had figures of its own (no replay could take it), so
    deleting it moves none: it saves at once."""
    _, owner, _, _ = missing_transfer
    assert owner.delete("/api/transactions/970").status_code == 204
    assert owner.post("/api/transactions/recalculate").status_code == 200


def test_the_dry_run_leaves_the_live_database_unlocked(ledger, app_db, monkeypatch):
    path = app_db[0]
    Session, owner, _, ids = ledger
    free = []
    real = year_changes.figures

    def check_lock(db, tz):
        other = sqlite3.connect(path, timeout=0)
        try:
            other.execute("BEGIN IMMEDIATE")  # another save would go through
            other.rollback()
            free.append(True)
        except sqlite3.OperationalError:
            free.append(False)
        finally:
            other.close()
        return real(db, tz)

    monkeypatch.setattr(year_changes, "figures", check_lock)
    assert owner.put(f"/api/transactions/{ids['deposit']}", json={"cost_basis_usd": "50000"}).status_code == 409
    assert free and all(free)


def test_the_fingerprint_covers_the_write_and_what_it_changes(ledger):
    _, owner, _, ids = ledger
    one = owner.put(f"/api/transactions/{ids['deposit']}", json={"cost_basis_usd": "50000"}).json()
    again = owner.put(f"/api/transactions/{ids['deposit']}", json={"cost_basis_usd": "50000"}).json()
    other = owner.put(f"/api/transactions/{ids['deposit']}", json={"cost_basis_usd": "51000"}).json()
    assert one["confirm"] == again["confirm"] != other["confirm"]
    assert one["confirm"] == past_years.fingerprint(
        {"kind": "edit", "tx_id": ids["deposit"], "data": {"cost_basis_usd": "50000"}},
        one["years"], one["changes"], one["pending"], one["recalc_error"])
