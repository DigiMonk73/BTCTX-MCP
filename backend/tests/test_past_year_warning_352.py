"""
The past-year warning on adds, edits and deletes (2.0 spec 5.8, 5.15's "Q4's
reach" and "Q4"; card B6b #352; the owner's decision Q4, widened on
2026-10-15): a write that would change the figures of a tax year before this
one (the gains, the Form 8949 boxes, the dates acquired, the income and
rebates, gifts, donations and lost coins) answers
409 and saves nothing, until it comes back with the 409's fingerprint
(?confirm=); then a copy of the database is made first, under the write
lock, and the write is checked again before it's committed. Worked out on a
scratch copy, never in the live database. With a login, changes a
recalculation alone would make ("Don't warn for fixes", the owner,
2026-10-16) never ask; with the AI key, those in an earlier year do. If the
exact check runs past its time budget, the warning names the years from the
write's date instead (the lead's decision, 2026-10-18).

"This tax year" is 2026 here (conftest.tax_year), set once the ledger is
seeded.
"""

import re
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.main import app
from backend.migrate import PRE_CHANGE_KIND, backup_copies
from backend.models.transaction import Transaction
from backend.services import past_years, recalculated_by
from backend.services import transaction as tx_service
from backend.tests.conftest import default_login, stub_prices_at

BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 2, 3, 4, 99
TAIL = "which you may already have filed. Confirm to save it: a copy of your ledger is made first."


@pytest.fixture
def ledger(fresh_app, monkeypatch, tax_year):
    """A ledger of its own, logged in: a deposit in 2024, a sale in 2024 and
    one in 2025 from it, a deposit in 2026. Then this tax year is 2026."""
    stub_prices_at(monkeypatch, lambda when: Decimal("50000"))
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    rows = {
        "deposit 2024": deposit(client, "2024-01-10T12:00:00Z", amount="1", basis="1000"),
        "sale 2024": sell(client, "2024-06-01T12:00:00Z"),
        "sale 2025": sell(client, "2025-03-01T12:00:00Z"),
        "deposit 2026": deposit(client, "2026-02-01T12:00:00Z", amount="0.5", basis="20000"),
    }
    tax_year(2026)
    client.Session = fresh_app
    return client, rows


def post(client, params=None, **body):
    return client.post("/api/transactions", json={"fee_amount": "0", **body}, params=params)


def deposit(client, when: str, amount: str = "1", basis: str = "1000", params=None, **more) -> int:
    r = post(client, params, type="Deposit", from_account_id=EXTERNAL, to_account_id=EXCHANGE_BTC, amount=amount,
             timestamp=when, source="MyBTC", cost_basis_usd=basis, **more)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def sell(client, when: str, amount: str = "0.25", proceeds: str = "15000") -> int:
    r = post(client, type="Sell", from_account_id=EXCHANGE_BTC, to_account_id=EXCHANGE_USD, amount=amount,
             timestamp=when, proceeds_usd=proceeds)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def stored(client) -> list:
    """Every transaction and every lot disposal as stored."""
    with client.Session() as db:
        return [db.execute(text("SELECT * FROM transactions ORDER BY id")).all(),
                db.execute(text("SELECT * FROM lot_disposals ORDER BY id")).all()]


def copies(client, kind: str) -> list[Path]:
    with client.Session() as db:
        return backup_copies(Path(db.get_bind().url.database), kind)


def backdated_add(client, params=None):
    return post(client, params, type="Deposit", from_account_id=EXTERNAL, to_account_id=EXCHANGE_BTC, amount="1",
                timestamp="2023-12-01T12:00:00Z", source="MyBTC", cost_basis_usd="500")


WRITES = {
    "backdated add": lambda c, rows, params=None: backdated_add(c, params),
    "edit": lambda c, rows, params=None: c.put(f"/api/transactions/{rows['deposit 2024']}",
                                               json={"cost_basis_usd": "2000"}, params=params),
    "delete": lambda c, rows, params=None: c.delete(f"/api/transactions/{rows['sale 2024']}", params=params),
}


# Q4's reach

@pytest.mark.parametrize("write, years, named", [
    ("backdated add", [2023, 2024, 2025], "tax years 2023, 2024 and 2025"),  # its lot is now the oldest
    ("edit", [2024, 2025], "tax years 2024 and 2025"),  # the lot both sales took from
    ("delete", [2024], "tax year 2024"),  # the 2025 sale's quarter of the lot costs the same
])
def test_an_add_an_edit_or_a_delete_that_changes_an_earlier_year_asks_and_saves_nothing(ledger, write, years,
                                                                                         named):
    client, rows = ledger
    before = stored(client)
    r = WRITES[write](client, rows)
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"] == f"This changes the figures of {named}, {TAIL}"
    assert body["years"] == years
    assert body["changes"] and all(set(i["years"]) & set(years) for i in body["changes"])
    assert body["pending"] == [] and body["recalc_error"] is None
    assert body["exact"] is True and body["why_not_exact"] is None
    assert body["timezone"] == "UTC"  # the zone its rows' dates are in, the tax timezone (#737)
    assert re.fullmatch(r"[0-9a-f]{64}", body["confirm"])
    assert stored(client) == before
    assert copies(client, PRE_CHANGE_KIND) == []


def test_a_write_in_this_tax_year_saves_at_once_with_no_dry_run(ledger, monkeypatch):
    client, rows = ledger
    monkeypatch.setattr(past_years, "scratch_copy", None)  # any dry run would fail
    assert client.put(f"/api/transactions/{rows['deposit 2026']}", json={"cost_basis_usd": "21000"}).status_code == 200
    assert deposit(client, "2026-03-01T12:00:00Z")
    assert client.delete(f"/api/transactions/{rows['deposit 2026']}").status_code == 204


def test_an_add_dated_after_every_row_into_an_earlier_year_adds_to_it_with_no_replay(fresh_app, monkeypatch,
                                                                                        tax_year):
    stub_prices_at(monkeypatch, lambda when: Decimal("50000"))
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    deposit(client, "2025-01-10T12:00:00Z")
    tax_year(2026)
    replays = []
    real = tx_service.recalculate_all_transactions
    monkeypatch.setattr(tx_service, "recalculate_all_transactions", lambda *a, **k: replays.append(1) or real(*a, **k))
    r = post(client, type="Deposit", from_account_id=EXTERNAL, to_account_id=EXCHANGE_BTC, amount="0.5",
             timestamp="2025-08-01T12:00:00Z", source="MyBTC", cost_basis_usd="30000")
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"] == f"This adds to tax year 2025, {TAIL}"
    assert [(i["id"], i["change"], i["years"]) for i in body["changes"]] == [
        (None, "Added: basis 30000.00; cost of the lots it made 30000.00.", [2025])]
    assert replays == []


def test_a_dollar_row_into_an_earlier_year_saves_at_once(ledger):
    client, _ = ledger
    r = post(client, type="Deposit", from_account_id=EXTERNAL, to_account_id=BANK, amount="500",
             timestamp="2024-03-01T12:00:00Z", source="N/A")
    assert r.status_code == 200, r.text


# Q4

def test_a_confirm_with_the_fingerprint_saves_after_its_copy(ledger):
    client, rows = ledger
    asked = WRITES["edit"](client, rows).json()
    r = WRITES["edit"](client, rows, {"confirm": asked["confirm"]})
    assert r.status_code == 200, r.text
    assert r.json()["cost_basis_usd"] == "2000.00"
    made = copies(client, PRE_CHANGE_KIND)
    assert len(made) == 1
    with sqlite3.connect(made[0]) as copy:  # the ledger as it was
        (basis,) = copy.execute("SELECT cost_basis_usd FROM transactions WHERE id = ?",
                                (rows["deposit 2024"],)).fetchone()
    assert Decimal(str(basis)) == 1000


@pytest.mark.parametrize("write", WRITES)
def test_each_write_saves_once_confirmed(ledger, write):
    client, rows = ledger
    asked = WRITES[write](client, rows).json()
    assert WRITES[write](client, rows, {"confirm": asked["confirm"]}).status_code in (200, 204)
    assert len(copies(client, PRE_CHANGE_KIND)) == 1


def test_a_stale_fingerprint_gets_a_new_409_and_saves_nothing(ledger):
    client, rows = ledger
    asked = WRITES["edit"](client, rows).json()
    # the ledger changes meanwhile: another 2024 sale, confirmed
    other = post(client, type="Sell", from_account_id=EXCHANGE_BTC, to_account_id=EXCHANGE_USD, amount="0.1",
                 timestamp="2024-09-01T12:00:00Z", proceeds_usd="5000")
    assert other.status_code == 409
    sale = post(client, {"confirm": other.json()["confirm"]}, type="Sell", from_account_id=EXCHANGE_BTC,
                to_account_id=EXCHANGE_USD, amount="0.1", timestamp="2024-09-01T12:00:00Z", proceeds_usd="5000")
    assert sale.status_code == 200, sale.text
    before, made = stored(client), copies(client, PRE_CHANGE_KIND)
    r = WRITES["edit"](client, rows, {"confirm": asked["confirm"]})
    assert r.status_code == 409, r.text
    assert r.json()["confirm"] != asked["confirm"]
    assert stored(client) == before
    assert copies(client, PRE_CHANGE_KIND) == made  # its copy went with it


def test_a_made_up_fingerprint_saves_nothing(ledger):
    client, rows = ledger
    before = stored(client)
    assert WRITES["delete"](client, rows, {"confirm": "0" * 64}).status_code == 409
    assert stored(client) == before
    assert copies(client, PRE_CHANGE_KIND) == []


def test_a_value_filled_from_the_price_stays_marked(ledger):
    client, _ = ledger
    body = {"type": "Deposit", "from_account_id": EXTERNAL, "to_account_id": EXCHANGE_BTC, "amount": "0.1",
            "timestamp": "2024-02-01T12:00:00Z", "source": "Income", "fee_amount": "0"}
    asked = client.post("/api/transactions", json=body)
    assert asked.status_code == 409, asked.text
    r = client.post("/api/transactions", json=body, params={"confirm": asked.json()["confirm"]})
    assert r.status_code == 200, r.text
    assert r.json()["cost_basis_usd"] == "5000.00"
    assert r.json()["values_from_price"] == ["cost_basis_usd"]


def test_a_box_that_moves_asks(ledger):
    client, rows = ledger
    r = client.put(f"/api/transactions/{rows['sale 2025']}", json={"broker_reporting": "basis"})
    assert r.status_code == 409, r.text
    assert [i["change"] for i in r.json()["changes"]] == ["Form 8949 box K -> J."]
    assert r.json()["years"] == [2025]


def test_a_date_acquired_that_moves_asks(ledger):
    client, rows = ledger
    r = client.put(f"/api/transactions/{rows['deposit 2024']}", json={"acquired_at": "2023-12-20"})
    assert r.status_code == 409, r.text
    assert "Form 8949 column (b), date acquired 01/10/2024 -> 12/20/2023" in " ".join(
        i["change"] for i in r.json()["changes"])


def test_a_failed_with_pass_answers_as_the_save_would(ledger):
    client, rows = ledger
    r = client.delete(f"/api/transactions/{rows['deposit 2024']}")  # its coins were sold
    assert r.status_code == 400
    assert r.json()["detail"].startswith("Not deleted: later transactions depend on this one.")


def test_a_refused_date_still_comes_before_any_409(ledger):
    client, rows = ledger
    r = post(client, type="Deposit", from_account_id=EXTERNAL, to_account_id=EXCHANGE_BTC, amount="1",
             timestamp="2008-06-01T12:00:00Z", source="MyBTC", cost_basis_usd="1")
    assert (r.status_code, r.json()["detail"]) == (422, tx_service.BEFORE_BITCOIN)
    r = client.put(f"/api/transactions/{rows['deposit 2024']}", json={"timestamp": "2008-06-01T12:00:00Z"})
    assert (r.status_code, r.json()["detail"]) == (422, tx_service.BEFORE_BITCOIN)


def _make_pending(client, tx_id: int) -> None:
    """A stored figure a recalculation would put right: a pending change."""
    with client.Session() as db:
        db.execute(text("UPDATE transactions SET realized_gain_usd = '1.00' WHERE id = :id"), {"id": tx_id})
        db.commit()


def test_with_a_login_changes_a_recalculation_alone_would_make_never_ask(ledger):
    client, rows = ledger
    _make_pending(client, rows["sale 2024"])
    # an edit of a 2025 sale that moves nothing but the pending fix
    r = client.put(f"/api/transactions/{rows['sale 2025']}", json={"proceeds_usd": "15000"})
    assert r.status_code == 200, r.text
    with client.Session() as db:
        assert db.get(Transaction, rows["sale 2024"]).realized_gain_usd != Decimal("1.00")


def test_listed_apart_when_the_write_asks_anyway(ledger):
    client, rows = ledger
    _make_pending(client, rows["sale 2024"])
    r = WRITES["edit"](client, rows)
    assert r.status_code == 409
    assert [(i["id"], i["issue"]) for i in r.json()["pending"]] == [
        (rows["sale 2024"], "Stored figures differ from what the current rules give.")]
    assert rows["sale 2024"] not in [i["id"] for i in r.json()["changes"] if "1.00 ->" in i["change"]]


def test_one_pass_and_two_give_the_same_answer(ledger):
    client, rows = ledger
    assert client.post("/api/transactions/recalculate").status_code == 200
    with client.Session() as db:
        assert recalculated_by.matches(db)
    one = WRITES["edit"](client, rows).json()
    with client.Session() as db:
        db.execute(text("DELETE FROM app_settings WHERE key = 'recalculated_by'"))
        db.commit()
    two = WRITES["edit"](client, rows).json()
    assert one == two


def test_the_dry_run_leaves_the_live_database_unlocked(ledger, monkeypatch):
    client, rows = ledger
    seen = []
    figures = past_years.year_changes.figures

    def look(db, tz):
        with client.Session() as live:
            path = live.get_bind().url.database
        other = sqlite3.connect(path, timeout=0)
        try:
            other.execute("BEGIN IMMEDIATE")
            other.rollback()
            seen.append(True)
        except sqlite3.OperationalError:
            seen.append(False)
        finally:
            other.close()
        return figures(db, tz)

    monkeypatch.setattr(past_years.year_changes, "figures", look)
    assert WRITES["edit"](client, rows).status_code == 409
    assert seen and all(seen)


# The time budget (the lead's decision of 2026-10-18)

def test_past_the_time_budget_the_years_come_from_its_date(ledger, monkeypatch):
    client, rows = ledger
    monkeypatch.setattr(past_years, "DRY_RUN_SECONDS", 0)
    r = WRITES["edit"](client, rows)
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"] == ("This is dated in 2024, so it can change 2024's figures and later years you may "
                              "have filed. Save it? A copy of your ledger is made first.")
    assert (body["years"], body["changes"], body["pending"], body["exact"]) == ([2024, 2025], [], [], False)
    assert body["why_not_exact"] and body["timezone"] == "UTC"
    r = WRITES["edit"](client, rows, {"confirm": body["confirm"]})
    assert r.status_code == 200, r.text
    assert len(copies(client, PRE_CHANGE_KIND)) == 1


def test_within_the_time_budget_a_small_ledger_gets_the_exact_answer(ledger):
    client, rows = ledger
    assert past_years.DRY_RUN_SECONDS == 10  # set from the StartOS VM's measurement
    assert WRITES["edit"](client, rows).json()["exact"] is True


# With the AI key

@pytest.fixture
def ai(ledger, ai_key_headers_for):
    client, rows = ledger
    return ai_key_headers_for(client), client, rows


@pytest.fixture
def ai_key_headers_for():
    def make(client):
        assert client.put("/api/settings/ai-access", json={"on": True}).status_code == 200
        r = client.post("/api/settings/ai-key")
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['key']}"}
    return make


def test_the_ai_key_gets_the_409_and_its_confirm_makes_a_fresh_ai_copy(ai):
    headers, client, rows = ai
    ai_client = TestClient(app, headers=headers)
    url = f"/api/transactions/{rows['deposit 2024']}"
    asked = ai_client.put(url, json={"cost_basis_usd": "2000"})
    assert asked.status_code == 409, asked.text
    assert copies(client, "ai") == []  # the 409 saved nothing, and copied nothing
    r = ai_client.put(url, json={"cost_basis_usd": "2000"}, params={"confirm": asked.json()["confirm"]})
    assert r.status_code == 200, r.text
    assert len(copies(client, "ai")) == 1 and copies(client, PRE_CHANGE_KIND) == []


def test_with_the_ai_key_a_change_from_a_fixed_rule_in_an_earlier_year_asks(ai):
    headers, client, rows = ai
    ai_client = TestClient(app, headers=headers)
    _make_pending(client, rows["sale 2024"])
    r = ai_client.put(f"/api/transactions/{rows['deposit 2026']}", json={"cost_basis_usd": "21000"})
    assert r.status_code == 409, r.text
    assert r.json()["years"] == [2024]
    assert [i["id"] for i in r.json()["pending"]] == [rows["sale 2024"]]
    assert r.json()["changes"] == []


def test_with_the_ai_key_this_years_write_saves_at_once_while_nothing_is_pending(ai, monkeypatch):
    headers, client, rows = ai
    assert client.post("/api/transactions/recalculate").status_code == 200
    monkeypatch.setattr(past_years, "scratch_copy", None)  # any dry run would fail
    ai_client = TestClient(app, headers=headers)
    r = ai_client.put(f"/api/transactions/{rows['deposit 2026']}", json={"cost_basis_usd": "21000"})
    assert r.status_code == 200, r.text


# A row the replay can't pass (5.13's missing-account Transfer, from before 0.9.2)

@pytest.fixture
def missing_account_row(ledger):
    client, rows = ledger
    with client.Session() as db:
        db.execute(text(
            "INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount, fee_amount,"
            " fee_currency) VALUES (970, 'Transfer', '2024-02-01T12:00:00Z', 2, 999, '0.1', '0', 'BTC')"))
        db.commit()
    with client.Session() as db:  # coins in Wallet for it, before it
        db.execute(text(
            "INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount, fee_amount,"
            " fee_currency, source, cost_basis_usd) VALUES (969, 'Deposit', '2023-06-01T12:00:00Z', 99, 2, '0.2',"
            " '0', 'BTC', 'MyBTC', '300')"))
        db.commit()
    return client, rows


def test_a_failed_without_pass_doesnt_stop_the_edit_that_repairs_the_row(missing_account_row):
    client, _ = missing_account_row
    asked = client.put("/api/transactions/970", json={"to_account_id": EXCHANGE_BTC})
    assert asked.status_code == 409, asked.text
    assert asked.json()["recalc_error"].startswith("Transaction 970 (a Transfer of 2024-02-01) names account 999")
    r = client.put("/api/transactions/970", json={"to_account_id": EXCHANGE_BTC},
                   params={"confirm": asked.json()["confirm"]})
    assert r.status_code == 200, r.text


def test_nor_its_delete(missing_account_row):
    client, _ = missing_account_row
    asked = client.delete("/api/transactions/970")
    assert asked.status_code == 409, asked.text
    assert client.delete("/api/transactions/970", params={"confirm": asked.json()["confirm"]}).status_code == 204


def test_into_wallet_it_would_be_a_consolidation_which_needs_a_fee(missing_account_row):
    client, _ = missing_account_row
    r = client.put("/api/transactions/970", json={"to_account_id": WALLET})
    assert (r.status_code, r.json()["detail"]) == (400, tx_service.SAME_ACCOUNT_NEEDS_FEE)


# The server review's findings

def test_an_income_change_asks(ledger):
    """A deposit made income with its typed value kept: no stored figure,
    lot or box moves, but the year's income does."""
    client, rows = ledger
    r = client.put(f"/api/transactions/{rows['deposit 2024']}", json={"source": "Income", "cost_basis_usd": "1000"})
    assert r.status_code == 409, r.text
    assert [i["change"] for i in r.json()["changes"]] == ["Income and rebates: none -> Income 1000.00."]


def test_income_made_a_rebate_asks(ledger):
    client, _ = ledger
    body = {"type": "Deposit", "from_account_id": EXTERNAL, "to_account_id": WALLET, "amount": "0.01",
            "timestamp": "2025-05-01T12:00:00Z", "source": "Income", "cost_basis_usd": "600", "fee_amount": "0"}
    asked = client.post("/api/transactions", json=body)
    income = client.post("/api/transactions", json=body, params={"confirm": asked.json()["confirm"]}).json()["id"]
    r = client.put(f"/api/transactions/{income}", json={"source": "Rebate", "cost_basis_usd": "600"})
    assert r.status_code == 409, r.text
    assert "Income and rebates: Income 600.00 -> Rebate 600.00" in r.json()["changes"][0]["change"]


def test_after_an_upgrade_the_first_confirm_saves(ledger):
    """With recalculated_by unmatched and a fix pending on the row itself,
    the dry run and the confirm both apply the write to the stored ledger,
    so they give the same fingerprint."""
    client, rows = ledger
    _make_pending(client, rows["sale 2024"])
    asked = client.delete(f"/api/transactions/{rows['sale 2024']}")
    assert asked.status_code == 409, asked.text
    r = client.delete(f"/api/transactions/{rows['sale 2024']}", params={"confirm": asked.json()["confirm"]})
    assert r.status_code == 204, r.text


def test_a_pending_fix_on_a_spend_made_a_gift_names_its_own_rows_never_a_network_fees(fresh_app, monkeypatch,
                                                                                         tax_year):
    """The pending list compares the stored figures with a recalculation
    without the write: there the row is a Spent on both sides, whatever the
    write makes it, so its Form 8949 rows are its own (#736's re-check)."""
    stub_prices_at(monkeypatch, lambda when: Decimal("50000"))
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    deposit(client, "2025-01-01T12:00:00Z", amount="0.1", basis="2000")
    r = post(client, type="Withdrawal", from_account_id=EXCHANGE_BTC, to_account_id=EXTERNAL, amount="0.05",
             timestamp="2025-07-01T12:00:00Z", purpose="Spent", proceeds_usd="3000")
    assert r.status_code == 200, r.text
    spend = r.json()["id"]
    tax_year(2026)
    with fresh_app() as db:  # a fix pending on the spend itself, as after an upgrade
        db.execute(text("UPDATE lot_disposals SET holding_period = 'LONG' WHERE transaction_id = :id"), {"id": spend})
        db.execute(text("DELETE FROM app_settings WHERE key = 'recalculated_by'"))
        db.commit()
    r = client.put(f"/api/transactions/{spend}", json={"purpose": "Gift", "fmv_usd": "3000"})
    assert r.status_code == 409, r.text
    pending = {item["id"]: item["change"] for item in r.json()["pending"]}
    assert "Form 8949 box L -> I" in pending[spend] and "network fee's" not in pending[spend]
    changes = {item["id"]: item["change"] for item in r.json()["changes"]}
    assert "Form 8949 box I -> none" in changes[spend] and "network fee's" not in changes[spend]


def test_past_the_budget_a_dollar_row_still_saves_at_once(ledger, monkeypatch):
    client, _ = ledger
    monkeypatch.setattr(past_years, "DRY_RUN_SECONDS", 0)
    r = post(client, type="Deposit", from_account_id=EXTERNAL, to_account_id=BANK, amount="500",
             timestamp="2024-03-01T12:00:00Z", source="N/A")
    assert r.status_code == 200, r.text


def test_past_the_budget_a_refused_input_is_still_refused_first(ledger, monkeypatch):
    client, rows = ledger
    monkeypatch.setattr(past_years, "DRY_RUN_SECONDS", 0)
    r = client.put(f"/api/transactions/{rows['deposit 2024']}", json={"timestamp": "2008-06-01T12:00:00Z"})
    assert (r.status_code, r.json()["detail"]) == (422, tx_service.BEFORE_BITCOIN)


def test_a_row_deleted_before_its_confirm_takes_the_lock_is_404(ledger, monkeypatch):
    client, rows = ledger
    asked = WRITES["edit"](client, rows).json()
    take = past_years.take_write_lock

    def deleted_meanwhile(db):
        with client.Session() as other:
            other.execute(text("DELETE FROM transactions WHERE id = :id"), {"id": rows["deposit 2024"]})
            other.commit()
        return take(db)

    monkeypatch.setattr(past_years, "take_write_lock", deleted_meanwhile)
    r = WRITES["edit"](client, rows, {"confirm": asked["confirm"]})
    assert (r.status_code, r.json()["detail"]) == (404, "Transaction not found.")
    assert copies(client, PRE_CHANGE_KIND) == []


def test_a_row_deleted_before_the_dry_run_is_404(ledger, monkeypatch):
    """The re-check's: between the route's check and the dry run's copy."""
    client, rows = ledger
    find = tx_service.find_prices_first

    def deleted_meanwhile(db, priced):
        with client.Session() as other:  # the sale and what it left, as another save's delete leaves them
            for table, key in (("lot_disposals", "transaction_id"), ("ledger_entries", "transaction_id"),
                               ("transactions", "id")):
                other.execute(text(f"DELETE FROM {table} WHERE {key} = :id"), {"id": rows["sale 2024"]})
            other.commit()
        return find(db, priced)

    monkeypatch.setattr(tx_service, "find_prices_first", deleted_meanwhile)
    r = client.delete(f"/api/transactions/{rows['sale 2024']}")
    assert (r.status_code, r.json()["detail"]) == (404, "Transaction not found.")


# Gifts, donations and lost coins (the build's lead, 2026-10-24, under the
# owner's decision 25): the report's section of them changes, and a
# donation's value can be a charitable deduction on a filed return

@pytest.fixture
def gift_2025(ledger):
    client, rows = ledger
    body = {"type": "Withdrawal", "from_account_id": EXCHANGE_BTC, "to_account_id": EXTERNAL, "amount": "0.01",
            "timestamp": "2025-06-01T12:00:00Z", "purpose": "Gift", "fmv_usd": "500", "fee_amount": "0"}
    asked = client.post("/api/transactions", json=body)
    gift = client.post("/api/transactions", json=body, params={"confirm": asked.json()["confirm"]})
    assert gift.status_code == 200, gift.text
    return client, gift.json()["id"]


def test_a_gifts_value_that_moves_asks(gift_2025):
    client, gift = gift_2025
    r = client.put(f"/api/transactions/{gift}", json={"fmv_usd": "5000"})
    assert r.status_code == 409, r.text
    assert r.json()["years"] == [2025]
    assert [i["change"] for i in r.json()["changes"]] == [
        "Gifts, donations and lost coins: Gift 500.00 -> Gift 5000.00."]


def test_a_gift_made_a_donation_asks(gift_2025):
    client, gift = gift_2025
    r = client.put(f"/api/transactions/{gift}", json={"purpose": "Donation", "fmv_usd": "500"})
    assert r.status_code == 409, r.text
    assert "Gifts, donations and lost coins: Gift 500.00 -> Donation 500.00" in r.json()["changes"][0]["change"]


def test_a_dollar_withdrawals_leftover_purpose_and_value_count_for_nothing(ledger):
    """#449: only bitcoin leaving is given, donated or lost; an older save's
    leftover fields on a dollar withdrawal are dropped by an edit, and
    nothing of a tax year moves."""
    client, _ = ledger
    with client.Session() as db:
        db.execute(text(
            "INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount, fee_amount,"
            " fee_currency, purpose, fmv_usd) VALUES (980, 'Withdrawal', '2025-04-01T12:00:00Z', 1, 99, '100',"
            " '0', 'USD', 'Gift', '100')"))
        db.commit()
    r = client.put("/api/transactions/980", json={"amount": "100"})
    assert r.status_code == 200, r.text
    assert (r.json()["purpose"], r.json()["fmv_usd"]) == (None, None)  # dropped by the save


# The dates a filed return prints (the build's lead, 2026-10-24, under the
# owner's decisions 25 and 26): Form 8949's columns (b) and (c), the report's
# gift and income dates. A row with figures whose date moves asks, even
# within its year, with every figure and term the same

def test_a_sale_moved_a_day_within_its_year_asks(ledger):
    client, rows = ledger
    r = client.put(f"/api/transactions/{rows['sale 2025']}", json={"timestamp": "2025-03-02T12:00:00Z"})
    assert r.status_code == 409, r.text
    assert r.json()["years"] == [2025]
    assert [i["change"] for i in r.json()["changes"]] == ["Date 03/01/2025 -> 03/02/2025."]


def test_a_time_moved_within_its_day_doesnt_ask(ledger):
    client, rows = ledger
    r = client.put(f"/api/transactions/{rows['sale 2025']}", json={"timestamp": "2025-03-01T15:30:00Z"})
    assert r.status_code == 200, r.text


def test_a_deposit_dated_from_its_date_originally_acquired_moved_a_day_doesnt_ask(ledger):
    """No return prints its own date: its lot keeps the date originally
    acquired (column (b)), and it's no income."""
    client, _ = ledger
    body = {"type": "Deposit", "from_account_id": EXTERNAL, "to_account_id": WALLET, "amount": "0.1",
            "timestamp": "2025-05-01T12:00:00Z", "source": "MyBTC", "cost_basis_usd": "100",
            "acquired_at": "2020-01-01", "fee_amount": "0"}
    asked = client.post("/api/transactions", json=body)
    mine = client.post("/api/transactions", json=body, params={"confirm": asked.json()["confirm"]}).json()["id"]
    r = client.put(f"/api/transactions/{mine}", json={"timestamp": "2025-05-02T12:00:00Z"})
    assert r.status_code == 200, r.text


def test_a_deposit_whose_lot_is_dated_from_it_moved_a_day_asks(ledger):
    client, rows = ledger
    r = client.put(f"/api/transactions/{rows['deposit 2024']}", json={"timestamp": "2024-01-11T12:00:00Z"})
    assert r.status_code == 409, r.text  # its lot's date, every later sale's column (b)


def test_an_inherited_deposit_valued_from_the_price_moved_a_day_asks(ledger):
    """The report's table of values from the BTC price prints its date."""
    client, _ = ledger
    body = {"type": "Deposit", "from_account_id": EXTERNAL, "to_account_id": WALLET, "amount": "0.1",
            "timestamp": "2025-05-01T12:00:00Z", "source": "Inherited", "acquired_at": "2025-04-01",
            "fee_amount": "0"}
    asked = client.post("/api/transactions", json=body)
    inherited = client.post("/api/transactions", json=body, params={"confirm": asked.json()["confirm"]}).json()
    assert inherited["values_from_price"] == ["cost_basis_usd"]
    r = client.put(f"/api/transactions/{inherited['id']}", json={"timestamp": "2025-05-02T12:00:00Z"})
    assert r.status_code == 409, r.text
    assert [i["change"] for i in r.json()["changes"]] == ["Date 05/01/2025 -> 05/02/2025."]
