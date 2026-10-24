"""
The past-year warning's other writes (2.0 spec 5.8, 5.15's "Q4's reach";
card B6c #353; the owner's decision Q4, widened on 2026-10-15): the AI's
import and River's (one confirm per batch or file, their previews naming the
years), saving the tax timezone (each pass in its own timezone), each
exchange's 1099-DA switch (boxes compared with no replay) and, with the AI
key, Recalculate Ledger (what it changes is `pending`). Each answers 409 and
saves nothing when it would change an earlier tax year's figures, and saves
once sent again with the 409's fingerprint, after a copy of the database.
The login's fill of the timezone stays 1.x's (#359): an empty ledger only.

"This tax year" is 2026 here (conftest.tax_year), set once the ledger is
seeded.
"""

import io
import re
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.database import SCRATCH
from backend.main import app
from backend.migrate import PRE_CHANGE_KIND, backup_copies
from backend.models.transaction import Transaction
from backend.services import entry_import, past_years
from backend.services import transaction as tx_service
from backend.tests.conftest import default_login, stub_prices_at

BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 2, 3, 4, 99
TAIL = "which you may already have filed. Confirm to save it: a copy of your ledger is made first."


def logged_in() -> TestClient:
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    return client


@pytest.fixture
def ledger(fresh_app, monkeypatch, tax_year):
    """A ledger of its own, logged in: a deposit in 2024, a sale in 2024 and
    one in 2025 from it, a deposit in 2026. Then this tax year is 2026."""
    stub_prices_at(monkeypatch, lambda when: Decimal("50000"))
    client = logged_in()
    rows = {
        "deposit 2024": deposit(client, "2024-01-10T12:00:00Z", amount="1", basis="1000"),
        "sale 2024": sell(client, "2024-06-01T12:00:00Z"),
        "sale 2025": sell(client, "2025-03-01T12:00:00Z"),
        "deposit 2026": deposit(client, "2026-02-01T12:00:00Z", amount="0.5", basis="20000"),
    }
    tax_year(2026)
    client.Session = fresh_app
    return client, rows


def deposit(client, when: str, amount: str = "1", basis: str = "1000") -> int:
    r = client.post("/api/transactions", json={
        "type": "Deposit", "from_account_id": EXTERNAL, "to_account_id": EXCHANGE_BTC, "amount": amount,
        "timestamp": when, "source": "MyBTC", "cost_basis_usd": basis, "fee_amount": "0"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def sell(client, when: str, amount: str = "0.25", proceeds: str = "15000", params=None):
    r = client.post("/api/transactions", params=params, json={
        "type": "Sell", "from_account_id": EXCHANGE_BTC, "to_account_id": EXCHANGE_USD, "amount": amount,
        "timestamp": when, "proceeds_usd": proceeds, "fee_amount": "0"})
    if params is None and r.status_code == 409:
        return r
    assert r.status_code == 200, r.text
    return r.json()["id"]


def stored(client) -> list:
    """Every transaction, every lot disposal and every setting as stored."""
    with client.Session() as db:
        return [db.execute(text(f"SELECT * FROM {table} ORDER BY 1")).all()
                for table in ("transactions", "lot_disposals", "app_settings", "exchanges")]


def copies(client, kind: str) -> list[Path]:
    with client.Session() as db:
        return backup_copies(Path(db.get_bind().url.database), kind)


def count_replays(monkeypatch) -> list:
    replays = []
    real = tx_service.recalculate_all_transactions
    monkeypatch.setattr(tx_service, "recalculate_all_transactions",
                        lambda *a, **k: replays.append(1) or real(*a, **k))
    return replays


def no_dry_run(monkeypatch) -> None:
    monkeypatch.setattr(past_years, "scratch_copy", None)  # any dry run would fail


def _make_pending(client, tx_id: int) -> None:
    """A stored figure a recalculation would put right: a pending change."""
    with client.Session() as db:
        db.execute(text("UPDATE transactions SET realized_gain_usd = '1.00' WHERE id = :id"), {"id": tx_id})
        db.commit()


@pytest.fixture
def ai(ledger):
    client, rows = ledger
    assert client.put("/api/settings/ai-access", json={"on": True}).status_code == 200
    r = client.post("/api/settings/ai-key")
    assert r.status_code == 200, r.text
    return TestClient(app, headers={"Authorization": f"Bearer {r.json()['key']}"}), client, rows


# The AI's import (/api/import/entries): one confirm per batch

OLD_ROW = {"date": "2023-12-01T12:00:00Z", "type": "Deposit", "amount": "1", "from_account": "External",
           "to_account": "Exchange BTC", "source": "MyBTC", "cost_basis_usd": "500"}
NEW_ROW = {**OLD_ROW, "date": "2026-03-01T12:00:00Z"}


def ai_import(client, rows, params=None, step="execute"):
    return client.post(f"/api/import/entries/{step}", json={"rows": rows}, params=params)


def test_an_ai_import_that_changes_an_earlier_year_asks_and_saves_nothing(ledger):
    client, _ = ledger
    before = stored(client)
    r = ai_import(client, [OLD_ROW])
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"] == f"This changes the figures of tax years 2023, 2024 and 2025, {TAIL}"
    assert body["years"] == [2023, 2024, 2025]  # its lot is now the oldest
    assert [(i["id"], i["years"]) for i in body["changes"] if i["id"] is None] == [(None, [2023])]
    assert body["pending"] == [] and body["exact"] is True
    assert re.fullmatch(r"[0-9a-f]{64}", body["confirm"])
    assert stored(client) == before
    assert copies(client, PRE_CHANGE_KIND) == []


def test_its_confirm_saves_the_batch_once_after_its_copy(ledger):
    client, _ = ledger
    asked = ai_import(client, [OLD_ROW]).json()
    r = ai_import(client, [OLD_ROW], {"confirm": asked["confirm"]})
    assert r.status_code == 200, r.text
    assert r.json()["imported_count"] == 1
    made = copies(client, PRE_CHANGE_KIND)
    assert len(made) == 1
    with sqlite3.connect(made[0]) as copy:  # the ledger as it was
        assert copy.execute("SELECT COUNT(*) FROM transactions").fetchone() == (4,)
    with client.Session() as db:
        assert db.query(Transaction).count() == 5


def test_with_the_ai_key_its_confirm_makes_a_fresh_ai_copy(ai):
    key, client, _ = ai
    asked = ai_import(key, [OLD_ROW])
    assert asked.status_code == 409, asked.text
    assert copies(client, "ai") == []  # the 409 saved nothing, and copied nothing
    r = ai_import(key, [OLD_ROW], {"confirm": asked.json()["confirm"]})
    assert r.status_code == 200, r.text
    assert len(copies(client, "ai")) == 1 and copies(client, PRE_CHANGE_KIND) == []


def test_a_stale_fingerprint_gets_a_new_409_and_saves_nothing(ledger):
    client, _ = ledger
    asked = ai_import(client, [OLD_ROW]).json()
    other = sell(client, "2024-09-01T12:00:00Z", amount="0.1", proceeds="5000")  # the ledger changes meanwhile
    assert sell(client, "2024-09-01T12:00:00Z", "0.1", "5000", {"confirm": other.json()["confirm"]})
    before, made = stored(client), copies(client, PRE_CHANGE_KIND)
    r = ai_import(client, [OLD_ROW], {"confirm": asked["confirm"]})
    assert r.status_code == 409, r.text
    assert r.json()["confirm"] != asked["confirm"]
    assert stored(client) == before
    assert copies(client, PRE_CHANGE_KIND) == made  # its copy went with it


def test_a_batch_dated_this_year_saves_at_once_with_no_dry_run(ledger, monkeypatch):
    client, _ = ledger
    no_dry_run(monkeypatch)
    r = ai_import(client, [NEW_ROW])
    assert r.status_code == 200, r.text
    assert r.json()["imported_count"] == 1


def test_a_batch_dated_after_every_row_into_an_earlier_year_adds_to_it_with_no_replay(fresh_app, monkeypatch,
                                                                                         tax_year):
    stub_prices_at(monkeypatch, lambda when: Decimal("50000"))
    client = logged_in()
    deposit(client, "2025-01-10T12:00:00Z")
    tax_year(2026)
    replays = count_replays(monkeypatch)
    r = ai_import(client, [{**OLD_ROW, "date": "2025-08-01T12:00:00Z"}, {**OLD_ROW, "date": "2025-09-01T12:00:00Z"}])
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == f"This adds to tax year 2025, {TAIL}"
    assert [(i["id"], i["years"]) for i in r.json()["changes"]] == [(None, [2025]), (None, [2025])]
    assert replays == []


def test_the_preview_shows_what_the_execute_asks_with_the_same_fingerprint(ledger):
    client, _ = ledger
    preview = ai_import(client, [OLD_ROW], step="preview")
    assert preview.status_code == 200, preview.text
    asked = ai_import(client, [OLD_ROW]).json()
    assert preview.json()["past_years"] == asked
    assert ai_import(client, [NEW_ROW], step="preview").json()["past_years"] is None


def test_a_batch_already_in_the_ledger_saves_nothing_and_asks_nothing(ledger):
    client, _ = ledger
    same = {**OLD_ROW, "date": "2024-01-10T12:00:00Z", "cost_basis_usd": "1000"}  # the 2024 deposit again
    r = ai_import(client, [same])
    assert r.status_code == 200, r.text
    assert (r.json()["imported_count"], r.json()["skipped_duplicates"]) == (0, 1)


SAME_DEPOSIT = {**OLD_ROW, "date": "2024-01-10T12:00:00Z", "cost_basis_usd": "1000"}  # the 2024 deposit again


def test_a_duplicate_beside_a_row_dated_last_adds_at_once_and_applies_no_pending_change(ledger, monkeypatch):
    """The rows its duplicate check leaves out don't count: the batch only
    appends (review of #353: the duplicate's date made it a backdated batch,
    whose dry run then showed a pending fix, reversed, as its own change)."""
    client, rows = ledger
    _make_pending(client, rows["sale 2024"])
    no_dry_run(monkeypatch)
    r = ai_import(client, [SAME_DEPOSIT, NEW_ROW])
    assert r.status_code == 200, r.text
    assert (r.json()["imported_count"], r.json()["skipped_duplicates"]) == (1, 1)
    with client.Session() as db:  # an append replays nothing: the fix is still pending
        assert db.get(Transaction, rows["sale 2024"]).realized_gain_usd == Decimal("1.00")


@pytest.mark.parametrize("by", ["login", "AI key"])
def test_a_batch_sent_again_saves_nothing_and_asks_nothing(ai, monkeypatch, by):
    key, client, rows = ai
    _make_pending(client, rows["sale 2024"])
    no_dry_run(monkeypatch)
    r = ai_import(client if by == "login" else key, [SAME_DEPOSIT])
    assert r.status_code == 200, r.text
    assert (r.json()["imported_count"], r.json()["skipped_duplicates"]) == (0, 1)


def test_with_the_ai_key_a_duplicate_beside_a_row_dated_last_adds_at_once(ai, monkeypatch):
    key, client, rows = ai
    _make_pending(client, rows["sale 2024"])
    no_dry_run(monkeypatch)
    r = ai_import(key, [SAME_DEPOSIT, NEW_ROW])
    assert r.status_code == 200, r.text
    assert r.json()["imported_count"] == 1


def test_its_confirm_checks_for_duplicates_inside_the_write_lock_it_writes_in(ledger, monkeypatch):
    client, _ = ledger
    asked = ai_import(client, [OLD_ROW]).json()
    locked = []
    real = entry_import.mark_duplicates

    def check(prepared, db, exact_only=False):
        if exact_only and not db.info.get(SCRATCH):
            other = sqlite3.connect(db.get_bind().url.database, timeout=0)
            try:
                other.execute("BEGIN IMMEDIATE")
                other.rollback()
                locked.append(False)
            except sqlite3.OperationalError:
                locked.append(True)
            finally:
                other.close()
        return real(prepared, db, exact_only)

    monkeypatch.setattr(entry_import, "mark_duplicates", check)
    assert ai_import(client, [OLD_ROW], {"confirm": asked["confirm"]}).status_code == 200
    # The last check is the one its rows are written after (the earlier ones
    # only decide which years the rows can reach)
    assert locked and locked[-1] is True


def test_with_the_ai_key_a_change_from_a_fixed_rule_in_an_earlier_year_asks(ai):
    key, client, rows = ai
    _make_pending(client, rows["sale 2024"])
    # dated this year, but before the 2026 deposit: it replays the ledger, which applies the pending change
    r = ai_import(key, [{**NEW_ROW, "date": "2026-01-15T12:00:00Z"}])
    assert r.status_code == 409, r.text
    assert [i["id"] for i in r.json()["pending"]] == [rows["sale 2024"]]
    assert r.json()["years"] == [2024]


# River's import (/api/import/river): one confirm per file

RIVER_HEADER = "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag"
RIVER_OLD = {"row_number": 2, "date": "2023-12-01T12:00:00Z", "type": "Deposit", "amount": "1",
             "from_account": "External", "to_account": "Exchange BTC", "cost_basis_usd": "500", "source": "MyBTC"}


def river(client, rows, params=None):
    return client.post("/api/import/river/execute", json={"rows": rows}, params=params)


def river_preview(client, lines: list[str]):
    data = ("\n".join([RIVER_HEADER, *lines]) + "\n").encode()
    return client.post("/api/import/river/preview", files={"file": ("river.csv", io.BytesIO(data), "text/csv")})


def test_a_river_import_that_changes_an_earlier_year_asks_and_its_confirm_saves_once(ledger):
    client, _ = ledger
    before = stored(client)
    asked = river(client, [RIVER_OLD])
    assert asked.status_code == 409, asked.text
    assert asked.json()["years"] == [2023, 2024, 2025]
    assert asked.json()["detail"] == f"This changes the figures of tax years 2023, 2024 and 2025, {TAIL}"
    assert stored(client) == before
    r = river(client, [RIVER_OLD], {"confirm": asked.json()["confirm"]})
    assert r.status_code == 200, r.text
    assert r.json()["imported_count"] == 1
    assert len(copies(client, PRE_CHANGE_KIND)) == 1


def test_a_river_import_dated_this_year_saves_at_once(ledger, monkeypatch):
    client, _ = ledger
    no_dry_run(monkeypatch)
    r = river(client, [{**RIVER_OLD, "date": "2026-03-01T12:00:00Z"}])
    assert r.status_code == 200, r.text


def test_a_river_file_sent_again_saves_nothing_and_asks_nothing(ledger, monkeypatch):
    client, rows = ledger
    _make_pending(client, rows["sale 2024"])
    asked = river(client, [RIVER_OLD]).json()
    assert river(client, [RIVER_OLD], {"confirm": asked["confirm"]}).status_code == 200
    _make_pending(client, rows["sale 2024"])  # the confirmed import replayed the ledger
    no_dry_run(monkeypatch)
    r = river(client, [RIVER_OLD])  # a second tab, or a resend
    assert r.status_code == 200, r.text
    assert r.json()["imported_count"] == 0


def test_a_river_row_the_ledger_refuses_is_refused_as_before(ledger):
    client, _ = ledger
    too_much = {**RIVER_OLD, "type": "Sell", "date": "2024-02-01T12:00:00Z", "amount": "5",
                "from_account": "Exchange BTC", "to_account": "Exchange USD", "proceeds_usd": "1000",
                "cost_basis_usd": None, "source": None}
    r = river(client, [too_much])
    assert r.status_code == 400, r.text
    assert r.json()["detail"].startswith("Import failed: ") and r.json()["detail"].endswith(
        "No transactions were saved.")


def test_the_river_preview_names_the_past_years_its_new_rows_are_dated_in(ledger):
    client, _ = ledger
    r = river_preview(client, ["2025-03-05 12:00:00,25.00,USD,0.00030000,BTC,,,Buy",
                               "2026-03-05 12:00:00,25.00,USD,0.00030000,BTC,,,Buy"])
    assert r.status_code == 200, r.text
    assert r.json()["past_years_dated"] == [2025]
    r = river_preview(client, ["2026-03-05 12:00:00,25.00,USD,0.00030000,BTC,,,Buy"])
    assert r.json()["past_years_dated"] == []


# The tax timezone: Settings' Save (the PUT with "chosen")

@pytest.fixture
def tz_ledger(fresh_app, monkeypatch, tax_year):
    """Coins deposited 2024-03-01 12:00 UTC; a sale long-term in UTC (2025-03-02
    03:00 UTC) that is 2025-03-01 in Chicago, the anniversary, so short-term
    there; and a sale on 2026-01-01 03:00 UTC, which is 2025 in Chicago."""
    stub_prices_at(monkeypatch, lambda when: Decimal("50000"))
    client = logged_in()
    rows = {
        "deposit": deposit(client, "2024-03-01T12:00:00Z"),
        "sale 2025": sell(client, "2025-03-02T03:00:00Z"),
        "sale 2026": sell(client, "2026-01-01T03:00:00Z"),
    }
    tax_year(2026)
    client.Session = fresh_app
    return client, rows


def save_timezone(client, name: str, params=None):
    return client.put("/api/settings/tax-timezone", json={"timezone": name, "chosen": True}, params=params)


def test_saving_a_timezone_that_changes_an_earlier_years_figures_asks_and_saves_nothing(tz_ledger):
    client, rows = tz_ledger
    before = stored(client)
    r = save_timezone(client, "America/Chicago")
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"] == f"This changes the figures of tax years 2025 and 2026, {TAIL}"
    changed = {i["id"]: i for i in body["changes"]}
    assert set(changed) == {rows["sale 2025"], rows["sale 2026"]}
    assert changed[rows["sale 2025"]]["change"] == ("short-term gain 0.00 -> 14750.00; long-term gain 14750.00 -> "
                                                  "0.00; Form 8949 box K -> H.")
    assert changed[rows["sale 2025"]]["years"] == [2025]
    assert stored(client) == before
    assert client.get("/api/settings/tax-timezone").json() == {"timezone": "UTC", "source": "default"}


def test_a_sale_that_only_changes_tax_year_is_listed_under_both(tz_ledger):
    client, rows = tz_ledger
    body = save_timezone(client, "America/Chicago").json()
    moved = next(i for i in body["changes"] if i["id"] == rows["sale 2026"])
    assert moved["years"] == [2025, 2026]
    assert moved["change"] == "Tax year 2026 -> 2025."


def test_its_confirm_saves_the_timezone_after_a_copy(tz_ledger):
    client, rows = tz_ledger
    asked = save_timezone(client, "America/Chicago").json()
    r = save_timezone(client, "America/Chicago", {"confirm": asked["confirm"]})
    assert r.status_code == 200, r.text
    assert r.json() == {"timezone": "America/Chicago", "source": "setting"}
    assert len(copies(client, PRE_CHANGE_KIND)) == 1
    with client.Session() as db:
        assert db.get(Transaction, rows["sale 2025"]).holding_period == "SHORT"


def test_the_timezone_in_use_saved_again_saves_at_once(tz_ledger, monkeypatch):
    client, _ = tz_ledger
    no_dry_run(monkeypatch)
    r = save_timezone(client, "UTC")  # in use (the default), now chosen
    assert r.status_code == 200, r.text
    assert r.json() == {"timezone": "UTC", "source": "setting"}


def test_an_empty_ledger_saves_the_timezone_at_once(fresh_app, monkeypatch, tax_year):
    client = logged_in()
    tax_year(2026)
    no_dry_run(monkeypatch)
    assert save_timezone(client, "America/Chicago").status_code == 200


def test_an_unknown_timezone_is_refused_before_any_dry_run(tz_ledger, monkeypatch):
    client, _ = tz_ledger
    no_dry_run(monkeypatch)
    r = save_timezone(client, "Mars/Olympus_Mons")
    assert r.status_code == 400, r.text


def test_the_logins_fill_still_saves_only_on_an_empty_ledger_and_never_asks(tz_ledger, fresh_app):
    client, _ = tz_ledger
    r = client.post("/api/settings/tax-timezone/fill", json={"timezone": "America/Chicago"})
    assert r.status_code == 200, r.text
    assert r.json() == {"timezone": "UTC", "source": "default", "filled": False}
    with fresh_app() as db:
        db.execute(text("DELETE FROM lot_disposals"))
        db.execute(text("DELETE FROM bitcoin_lots"))
        db.execute(text("DELETE FROM ledger_entries"))
        db.execute(text("DELETE FROM transactions"))
        db.commit()
    r = client.post("/api/settings/tax-timezone/fill", json={"timezone": "America/Chicago"})
    assert r.json() == {"timezone": "America/Chicago", "source": "setting", "filled": True}


# Each exchange's 1099-DA switch (PUT /api/accounts/{id} {sends_1099da})

def switch(client, account_id: int, sends: bool, params=None):
    return client.put(f"/api/accounts/{account_id}", json={"sends_1099da": sends}, params=params)


def test_turning_an_exchanges_1099da_off_asks_with_no_replay(ledger, monkeypatch):
    client, rows = ledger
    replays = count_replays(monkeypatch)
    before = stored(client)
    r = switch(client, EXCHANGE_BTC, False)
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"] == f"This changes the figures of tax year 2025, {TAIL}"
    assert [(i["id"], i["change"], i["years"]) for i in body["changes"]] == [
        (rows["sale 2025"], "Form 8949 box K -> L.", [2025])]
    assert replays == []
    assert stored(client) == before


def test_its_confirm_saves_the_switch_for_both_of_the_exchanges_accounts_after_a_copy(ledger):
    client, _ = ledger
    asked = switch(client, EXCHANGE_USD, False).json()  # either of its accounts
    r = switch(client, EXCHANGE_USD, False, {"confirm": asked["confirm"]})
    assert r.status_code == 200, r.text
    assert r.json()["sends_1099da"] is False
    assert client.get(f"/api/accounts/{EXCHANGE_BTC}").json()["sends_1099da"] is False
    assert len(copies(client, PRE_CHANGE_KIND)) == 1


def test_turning_it_on_again_asks_too_and_puts_the_box_back(ledger):
    client, rows = ledger
    off = switch(client, EXCHANGE_BTC, False).json()
    assert switch(client, EXCHANGE_BTC, False, {"confirm": off["confirm"]}).status_code == 200
    on = switch(client, EXCHANGE_BTC, True)
    assert on.status_code == 409, on.text
    assert [(i["id"], i["change"]) for i in on.json()["changes"]] == [(rows["sale 2025"], "Form 8949 box L -> K.")]
    assert switch(client, EXCHANGE_BTC, True, {"confirm": on.json()["confirm"]}).json()["sends_1099da"] is True


def test_an_exchange_with_nothing_before_this_year_switches_at_once(ledger, monkeypatch):
    client, _ = ledger
    made = client.post("/api/accounts/", json={"kind": "exchange", "name": "Kraken"})
    assert made.status_code == 201, made.text
    no_dry_run(monkeypatch)
    r = switch(client, made.json()[1]["id"], False)
    assert r.status_code == 200, r.text
    assert r.json()["sends_1099da"] is False


def test_the_same_setting_again_saves_at_once(ledger, monkeypatch):
    client, _ = ledger
    no_dry_run(monkeypatch)
    assert switch(client, EXCHANGE_BTC, True).status_code == 200


def test_the_switch_is_only_an_exchanges(ledger):
    client, _ = ledger
    for account_id in (BANK, WALLET, 5):
        r = switch(client, account_id, False)
        assert (r.status_code, r.json()["detail"]) == (400, "Only an exchange's accounts have the 1099-DA setting.")


def test_the_account_list_shows_each_exchanges_switch(ledger):
    client, _ = ledger
    listed = {a["id"]: a["sends_1099da"] for a in client.get("/api/accounts/").json()}
    assert listed == {BANK: None, WALLET: None, EXCHANGE_USD: True, EXCHANGE_BTC: True, 5: None, 6: None}


def test_an_account_change_names_something_to_change(ledger):
    client, _ = ledger
    assert client.put(f"/api/accounts/{EXCHANGE_BTC}", json={}).status_code == 422
    assert client.put(f"/api/accounts/{WALLET}", json={"hidden": True}).status_code == 200


def test_the_switch_is_never_the_ai_keys(ai):
    key, _, _ = ai
    assert switch(key, EXCHANGE_BTC, False).status_code == 403


# Recalculate Ledger: with the AI key it asks; with a login it never does

def test_the_ais_recalculate_with_a_change_pending_in_an_earlier_year_asks(ai):
    key, client, rows = ai
    _make_pending(client, rows["sale 2024"])
    before = stored(client)
    r = key.post("/api/transactions/recalculate")
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"] == ("Recalculating applies the rules fixed since your transactions were saved, and changes "
                              "the figures of tax year 2024, which you may already have filed. Confirm to recalculate: "
                              "a copy of your ledger is made first.")
    assert body["years"] == [2024] and body["changes"] == []
    assert [i["id"] for i in body["pending"]] == [rows["sale 2024"]]
    assert stored(client) == before
    assert copies(client, "ai") == []


def test_its_confirm_recalculates_after_a_fresh_ai_copy(ai):
    key, client, rows = ai
    _make_pending(client, rows["sale 2024"])
    asked = key.post("/api/transactions/recalculate").json()
    r = key.post("/api/transactions/recalculate", params={"confirm": asked["confirm"]})
    assert r.status_code == 200, r.text
    assert r.json()["transactions"] == 4
    with client.Session() as db:
        assert db.get(Transaction, rows["sale 2024"]).realized_gain_usd != Decimal("1.00")
    assert len(copies(client, "ai")) == 1


def test_with_nothing_pending_the_ais_recalculate_runs_at_once(ai, monkeypatch):
    key, client, _ = ai
    assert client.post("/api/transactions/recalculate").status_code == 200  # recalculated_by: this BitcoinTX
    no_dry_run(monkeypatch)
    assert key.post("/api/transactions/recalculate").status_code == 200


def test_with_a_login_recalculate_never_asks(ledger, monkeypatch):
    client, rows = ledger
    _make_pending(client, rows["sale 2024"])
    no_dry_run(monkeypatch)
    assert client.post("/api/transactions/recalculate").status_code == 200
    with client.Session() as db:
        assert db.get(Transaction, rows["sale 2024"]).realized_gain_usd != Decimal("1.00")


# Past the time budget (the lead's decision of 2026-10-18, on #353 too): the
# years from the write's earliest date, then the confirmed save as ever

def past_the_budget(monkeypatch):
    monkeypatch.setattr(past_years, "DRY_RUN_SECONDS", 0)


def by_date_and_confirmed(client, send, detail: str, years: list[int], kind: str) -> None:
    """The date-based 409 with these words and years, then its confirm saved after one copy of `kind`."""
    r = send(None)
    assert r.status_code == 409, r.text
    body = r.json()
    assert (body["detail"], body["years"], body["changes"], body["exact"]) == (detail, years, [], False)
    assert body["why_not_exact"] == past_years.TOO_SLOW
    assert send({"confirm": body["confirm"]}).status_code == 200
    assert len(copies(client, kind)) == 1


def test_past_the_budget_an_ai_import_names_the_years_from_its_first_row(ledger, monkeypatch):
    client, _ = ledger
    past_the_budget(monkeypatch)
    by_date_and_confirmed(client, lambda params: ai_import(client, [OLD_ROW], params),
                          "These rows start in 2023, so they can change 2023's figures and later years you may have "
                          "filed. Save them? A copy of your ledger is made first.", [2023, 2024, 2025], PRE_CHANGE_KIND)


def test_past_the_budget_with_the_ai_key_a_batch_names_every_year_a_fix_can_reach(ai, monkeypatch):
    key, client, _ = ai
    past_the_budget(monkeypatch)
    by_date_and_confirmed(client, lambda params: ai_import(key, [{**NEW_ROW, "date": "2026-01-15T12:00:00Z"}], params),
                          "These rows can change the figures of tax year 2024 and later years you may have filed: "
                          "saving them also applies the rules fixed since they were saved. Save them? A copy of your "
                          "ledger is made first.", [2024, 2025], "ai")


def test_past_the_budget_a_river_import_names_the_years_from_its_first_row(ledger, monkeypatch):
    client, _ = ledger
    past_the_budget(monkeypatch)
    by_date_and_confirmed(client, lambda params: river(client, [RIVER_OLD], params),
                          "These rows start in 2023, so they can change 2023's figures and later years you may have "
                          "filed. Save them? A copy of your ledger is made first.", [2023, 2024, 2025], PRE_CHANGE_KIND)


def test_past_the_budget_the_tax_timezone_names_the_years_from_the_ledgers_first(tz_ledger, monkeypatch):
    client, _ = tz_ledger
    past_the_budget(monkeypatch)
    by_date_and_confirmed(client, lambda params: save_timezone(client, "America/Chicago", params),
                          "Saving this tax timezone recalculates your ledger from 2024 on, so it can change 2024's "
                          "figures and later years you may have filed. Save it? A copy of your ledger is made first.",
                          [2024, 2025], PRE_CHANGE_KIND)


def test_past_the_budget_the_ais_recalculate_names_the_years_from_the_ledgers_first(ai, monkeypatch):
    key, client, rows = ai
    _make_pending(client, rows["sale 2024"])
    past_the_budget(monkeypatch)
    by_date_and_confirmed(client, lambda params: key.post("/api/transactions/recalculate", params=params),
                          "Recalculating applies the rules fixed since your transactions were saved, so it can change "
                          "the figures of tax year 2024 and later years you may have filed. Recalculate? A copy of "
                          "your ledger is made first.", [2024, 2025], "ai")
