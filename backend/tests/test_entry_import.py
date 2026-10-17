"""
backend/tests/test_entry_import.py

Tests for the JSON entry import (/api/import/entries) used by the MCP server:
validation, FMV autofill, dedup, dry-run simulation, atomic execute.
"""

import sqlite3
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.tests.conftest import stub_daily_prices

CLIENT: TestClient = None
PRICE = 100000.0  # stubbed historical BTC price


@pytest.fixture(autouse=True, scope="session")
def _set_client(auth_client):
    global CLIENT
    CLIENT = auth_client


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: PRICE)


@pytest.fixture(autouse=True)
def _clean_ledger():
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")


def preview(rows):
    r = CLIENT.post("/api/import/entries/preview", json={"rows": rows})
    assert r.status_code == 200, r.text
    return r.json()


def execute(rows, expect=200):
    r = CLIENT.post("/api/import/entries/execute", json={"rows": rows})
    assert r.status_code == expect, r.text
    return r.json()


def tx_count():
    return len(CLIENT.get("/api/transactions").json())


BUY = {
    "date": "2023-01-10T15:00:00Z", "type": "Buy", "amount": "0.5",
    "from_account": "Bank", "to_account": "Exchange BTC",
    "cost_basis_usd": "10000.00", "fee_amount": "25.00", "fee_currency": "USD",
}
TO_COLD = {
    # amount = BTC that left the exchange, fee included; 0.4999 arrives
    "date": "2023-01-12T15:00:00Z", "type": "Transfer", "amount": "0.5",
    "from_account": "Exchange BTC", "to_account": "Wallet",
    "fee_amount": "0.0001", "fee_currency": "BTC",
}

INTEREST = {
    "date": "2025-03-20T12:00:00Z", "type": "Deposit", "amount": "0.002",
    "from_account": "External", "to_account": "Wallet", "source": "Interest", "cost_basis_usd": "210.00",
}


class TestPreview:
    def test_preview_writes_nothing_and_reports_balances(self):
        no_fee_move = dict(TO_COLD, amount="0.5", fee_amount=None, fee_currency=None)
        out = preview([BUY, no_fee_move])
        assert out["ok"] is True
        assert out["ready_count"] == 2
        assert tx_count() == 0
        balances = {b["account"]: Decimal(b["balance"]) for b in out["balances_after"]}
        assert balances["Wallet"] == Decimal("0.5")
        assert balances["Exchange BTC"] == Decimal("0")

    def test_sell_simulation_reports_gain_and_holding_period(self):
        execute([BUY])
        sell = {
            "date": "2024-06-01T12:00:00Z", "type": "Sell", "amount": "0.25",
            "from_account": "Exchange BTC", "to_account": "Exchange USD",
            "proceeds_usd": "17500.00", "fee_amount": "10.00", "fee_currency": "USD",
        }
        out = preview([sell])
        sim = out["results"][0]["simulated"]
        # basis: half of (10000 + 25 USD fee) = 5012.50; net proceeds 17490
        assert Decimal(sim["cost_basis_usd"]) == Decimal("5012.50")
        assert Decimal(sim["realized_gain_usd"]) == Decimal("12477.50")
        assert sim["holding_period"] == "LONG"
        assert tx_count() == 1

    def test_overspend_is_rejected_and_later_rows_not_simulated(self):
        spend = {
            "date": "2023-01-11T00:00:00Z", "type": "Withdrawal", "amount": "2",
            "from_account": "Exchange BTC", "to_account": "External",
            "purpose": "Spent", "proceeds_usd": "1.00",
        }
        out = preview([BUY, spend, TO_COLD])
        statuses = [r["status"] for r in out["results"]]
        assert statuses == ["ready", "rejected", "not_simulated"]
        assert "Not enough BTC" in out["results"][1]["errors"][0]
        assert out["ok"] is False
        assert tx_count() == 0

    def test_invalid_account_for_type(self):
        bad = dict(BUY, to_account="Wallet")
        out = preview([bad])
        assert out["results"][0]["status"] == "invalid"
        assert "Exchange BTC" in out["results"][0]["errors"][0]

    def test_backdated_buy_reports_affected_existing_sell(self):
        execute([
            dict(BUY, date="2023-06-01T00:00:00Z"),
            {"date": "2024-07-01T00:00:00Z", "type": "Sell", "amount": "0.5",
             "from_account": "Exchange BTC", "to_account": "Exchange USD",
             "proceeds_usd": "30000.00"},
        ])
        earlier_cheap_buy = dict(
            BUY, date="2022-01-01T00:00:00Z", cost_basis_usd="1000.00", fee_amount=None
        )
        out = preview([earlier_cheap_buy])
        assert len(out["affected_existing"]) == 1
        affected = out["affected_existing"][0]
        assert affected["type"] == "Sell"
        assert Decimal(affected["realized_gain_after"]) > Decimal(affected["realized_gain_before"])


class TestAutofill:
    def test_income_deposit_basis_from_fmv(self):
        dep = {
            "date": "2024-03-01", "type": "Deposit", "amount": "0.001",
            "from_account": "External", "to_account": "Wallet", "source": "Income",
        }
        out = preview([dep])
        res = out["results"][0]
        assert res["autofilled_fields"] == ["cost_basis_usd"]
        assert Decimal(res["normalized"]["cost_basis_usd"]) == Decimal("100.00")
        assert not any("cost_basis_usd" in w for w in res["warnings"])

    def test_spent_withdrawal_proceeds_from_fmv(self):
        execute([BUY])
        spend = {
            "date": "2024-03-01T00:00:00Z", "type": "Withdrawal", "amount": "0.01",
            "from_account": "Exchange BTC", "to_account": "External", "purpose": "Spent",
        }
        res = preview([spend])["results"][0]
        assert res["autofilled_fields"] == ["proceeds_usd"]
        assert Decimal(res["normalized"]["proceeds_usd"]) == Decimal("1000.00")

    def test_usd_moves_are_not_valued_at_the_btc_price(self):
        """Bug hunt 2026-09-29: $5,000 of pay into Bank (source Income) got a
        cost basis, and income, of 5,000 x the BTC price; a Spent or Gift
        withdrawal from Bank got proceeds or FMV the same way. Only deposits
        into and withdrawals from a BTC account are valued at the BTC price."""
        rows = [
            {"date": "2024-03-01", "type": "Deposit", "amount": "5000",
             "from_account": "External", "to_account": "Bank", "source": "Income"},
            {"date": "2024-03-02", "type": "Withdrawal", "amount": "100",
             "from_account": "Bank", "to_account": "External", "purpose": "Spent"},
            {"date": "2024-03-03", "type": "Withdrawal", "amount": "50",
             "from_account": "Bank", "to_account": "External", "purpose": "Gift"},
        ]
        for res in preview(rows)["results"]:
            assert res["status"] == "ready", res
            assert res["autofilled_fields"] == [], res
            assert not {"cost_basis_usd", "proceeds_usd", "fmv_usd"} & set(res["normalized"]), res
            assert not any("BTC price" in w or "market value" in w for w in res["warnings"]), res

    def test_mybtc_deposit_needs_a_basis_and_is_not_autofilled(self):
        """F15: the AI can't save a MyBTC deposit without a basis (it used to be $0)."""
        dep = {
            "date": "2024-03-01", "type": "Deposit", "amount": "0.001",
            "from_account": "External", "to_account": "Wallet", "source": "MyBTC",
        }
        res = preview([dep])["results"][0]
        assert res["status"] == "invalid" and res["autofilled_fields"] == []
        assert any("cost basis (0 if it's unknown)" in e for e in res["errors"])
        res = preview([{**dep, "cost_basis_usd": "0"}])["results"][0]
        assert res["status"] == "ready" and res["normalized"]["cost_basis_usd"] == "0"


class TestDedup:
    def test_exact_duplicate_flagged_and_skipped_on_execute(self):
        first = execute([BUY, TO_COLD])
        assert first["imported_count"] == 2

        out = preview([BUY])
        assert out["results"][0]["status"] == "duplicate"
        assert out["results"][0]["matched_transaction_id"] == first["created"][0]["id"]

        again = execute([BUY, TO_COLD])
        assert again["imported_count"] == 0
        assert again["skipped_duplicates"] == 2
        assert tx_count() == 2

    def test_a_same_amount_buy_at_another_price_is_saved_but_flagged(self):
        """Bug hunt 2026-09-29 (owner decision): a Buy of the same BTC amount
        within 48 h but at another price was a "duplicate", skipped, and could
        never be saved through the AI. It's a possible duplicate now: flagged
        for the AI to ask about, saved when the user confirms."""
        first = dict(BUY, date="2024-01-15T14:00:00Z", cost_basis_usd="420.00", amount="0.01")
        second = dict(first, date="2024-01-16T14:00:00Z", cost_basis_usd="455.00")
        assert execute([first])["imported_count"] == 1
        res = preview([second])["results"][0]
        assert res["status"] == "possible_duplicate" and res["matched_transaction_id"]
        assert any("$455.00" in w and "$420.00" in w and "River" not in w for w in res["warnings"])
        out = execute([second])
        assert out["imported_count"] == 1 and out["skipped_duplicates"] == 0
        assert tx_count() == 2
        # The very same buy (same amount and price) is still skipped
        assert execute([second])["skipped_duplicates"] == 1 and tx_count() == 2

    def test_a_deposit_of_another_source_at_the_same_time_is_saved(self):
        """#253's reproduction: an Inherited deposit was a "duplicate" of an
        Interest deposit of the same amount and time, and couldn't be saved."""
        execute([INTEREST])
        inherited = dict(INTEREST, source="Inherited", cost_basis_usd="168.80", acquired_at="2025-02-28")
        res = preview([inherited])["results"][0]
        assert res["status"] == "possible_duplicate" and res["matched_transaction_id"]
        assert any("the same minute; its source is Interest, not Inherited" in w for w in res["warnings"])
        assert execute([inherited])["imported_count"] == 1 and tx_count() == 2

    def test_a_payout_at_another_minute_is_saved(self):
        """The same amount and source a minute apart is never left out by itself."""
        execute([INTEREST])
        later = dict(INTEREST, date="2025-03-20T12:01:00Z")
        res = preview([later])["results"][0]
        assert res["status"] == "possible_duplicate"
        assert any("recorded 1 minute earlier" in w and "Saved unless you remove it" in w for w in res["warnings"])
        assert execute([later])["imported_count"] == 1 and tx_count() == 2

    def test_a_duplicate_is_saved_when_the_user_says_it_is_another_transaction(self):
        """D1: left out by default; naming the match in not_a_duplicate_of saves it."""
        recorded = execute([INTEREST])["created"][0]["id"]
        res = preview([INTEREST])["results"][0]
        assert res["status"] == "duplicate" and res["matched_transaction_id"] == recorded
        assert any(f"not_a_duplicate_of: {recorded}" in w for w in res["warnings"])
        assert execute([INTEREST])["skipped_duplicates"] == 1 and tx_count() == 1
        another = dict(INTEREST, not_a_duplicate_of=recorded)
        assert preview([another])["results"][0]["status"] == "ready"
        out = execute([another])
        assert out["imported_count"] == 1 and out["skipped_duplicates"] == 0 and tx_count() == 2
        # The lead review of 6ac27ac: a repeated add_transactions (a retry after a timeout) saves it once
        again = execute([another])
        assert again["imported_count"] == 0 and again["skipped_duplicates"] == 1 and tx_count() == 2
        res = preview([another])["results"][0]
        assert res["status"] == "duplicate" and any("sent twice" in w for w in res["warnings"])

    def test_a_flagged_row_keeps_its_match_so_an_identical_one_beside_it_is_saved(self):
        """The review of #277: the same payout twice, once recorded. The
        preview's duplicate, flagged, takes the match; the other stays ready."""
        recorded = execute([INTEREST])["created"][0]["id"]
        assert [r["status"] for r in preview([INTEREST, INTEREST])["results"]] == ["duplicate", "ready"]
        rows = [dict(INTEREST, not_a_duplicate_of=recorded), INTEREST]
        assert [r["status"] for r in preview(rows)["results"]] == ["ready", "ready"]
        out = execute(rows)
        assert out["imported_count"] == 2 and out["skipped_duplicates"] == 0 and tx_count() == 3
        assert execute(rows)["imported_count"] == 0 and tx_count() == 3  # sent again: nothing more

    @pytest.mark.parametrize("named, saved", [
        ([True], 1),
        ([True, True], 2),
        ([True, True, True], 3),
        ([True, False], 2),
        ([False, True], 1),
    ], ids=["one named", "two named", "three named", "named, then plain", "plain, then named"])
    def test_a_request_sent_again_saves_nothing_more(self, named, saved):
        """#378: identical rows, some naming the recorded Buy as the one
        they aren't, sent three times (a retry after a timeout, say): only
        the first send saves anything. A row naming it that matched
        another copy is that copy (an identical row beside it took the
        named one), so no extra named row, and no named row after a plain
        one, saves another copy."""
        recorded = execute([BUY])["created"][0]["id"]
        rows = [dict(BUY, not_a_duplicate_of=recorded) if n else BUY for n in named]
        assert [execute(rows)["imported_count"] for _ in range(3)] == [saved, 0, 0]
        assert tx_count() == 1 + saved
        results = preview(rows)["results"]
        assert all(r["status"] == "duplicate" for r in results)
        assert all(any("sent twice" in w for w in r["warnings"]) for r, n in zip(results, named) if n)

    def test_a_resend_saves_nothing_when_a_date_alone_row_took_the_named_rows_copy(self):
        """#388's review: two Interest payouts recorded on a day (10:00 and
        15:00); the user adds a third at 10:00, named as another than the
        10:00 one, beside the 15:00 one given as a date alone. Sent again,
        the date-alone row would take the copy the first send saved at
        10:00 (nearer noon than 15:00), leaving the named row none: the
        named row takes that copy, and the date-alone row the 15:00 one."""
        at_ten = dict(INTEREST, date="2025-03-20T10:00:00Z")
        ten, three = (execute([row])["created"][0]["id"] for row in (at_ten, dict(INTEREST, date="2025-03-20T15:00:00Z")))
        day = dict(INTEREST, date="2025-03-20")
        assert [(r["status"], r["matched_transaction_id"]) for r in preview([at_ten, day])["results"]] == [
            ("duplicate", ten), ("duplicate", three)]
        rows = [dict(at_ten, not_a_duplicate_of=ten), day]
        assert [execute(rows)["imported_count"] for _ in range(3)] == [1, 0, 0]
        assert tx_count() == 3
        results = preview(rows)["results"]
        assert results[1]["matched_transaction_id"] == three and any("sent twice" in w for w in results[0]["warnings"])

    @pytest.mark.parametrize("seed", range(3))
    def test_a_row_named_as_its_previews_match_is_saved_only_once(self, seed):
        """#378 on random ledgers: payouts of two amounts at a few times of
        one day (some rows given as a date alone), some of the preview's
        duplicates named as other transactions. Sent three times, only the
        first send saves anything. (Its times never put a later payout
        nearer noon than an earlier one: a plain row can then be saved again
        beside a date-alone one, #411.)"""
        import random

        rng = random.Random(seed)
        times = ["2025-03-20T10:00:00Z", "2025-03-20T10:00:30Z", "2025-03-20T15:00:00Z", "2025-03-20"]
        for _ in range(60):
            CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")
            payout = lambda: dict(INTEREST, date=rng.choice(times), amount=rng.choice(["0.002", "0.003"]))  # noqa: E731
            for _ in range(rng.randrange(4)):
                execute([dict(payout(), date=rng.choice(times[:3]))])
            rows = [payout() for _ in range(rng.randrange(1, 5))]
            for row, res in zip(rows, preview(rows)["results"]):
                if res["status"] == "duplicate" and rng.random() < 0.6:
                    row["not_a_duplicate_of"] = res["matched_transaction_id"]
            saved = [execute(rows)["imported_count"] for _ in range(3)]
            assert saved[1:] == [0, 0], (rows, saved)

    def test_two_rows_each_naming_its_own_match_are_both_saved(self):
        """Two identical Buys recorded, and the user says the two rows are
        two more: each names the one the preview matched it to. Both are
        saved, once."""
        recorded = [tx["id"] for tx in execute([BUY, BUY])["created"]]
        matched = [r["matched_transaction_id"] for r in preview([BUY, BUY])["results"]]
        assert sorted(matched) == sorted(recorded)
        rows = [dict(BUY, not_a_duplicate_of=tx_id) for tx_id in matched]
        assert [execute(rows)["imported_count"] for _ in range(3)] == [2, 0, 0]
        assert tx_count() == 4

    def test_a_row_naming_a_transaction_that_isnt_its_duplicate_is_checked_as_any_other(self):
        """A wrong id frees the row from nothing: a duplicate is still left
        out, and the warning names the right one to send."""
        recorded = execute([BUY, TO_COLD])["created"]
        buy, move = recorded[0]["id"], recorded[1]["id"]
        res = preview([dict(BUY, not_a_duplicate_of=move)])["results"][0]
        assert res["status"] == "duplicate" and res["matched_transaction_id"] == buy
        assert any(f"not_a_duplicate_of: {buy}" in w and f"names tx #{move}, which isn't" in w for w in res["warnings"])
        assert execute([dict(BUY, not_a_duplicate_of=move)])["imported_count"] == 0 and tx_count() == 2

    def test_a_gap_under_a_minute_is_said_so(self):
        execute([dict(INTEREST, date="2025-03-20T12:00:59Z")])
        res = preview([dict(INTEREST, date="2025-03-20T12:01:10Z")])["results"][0]
        assert any("recorded less than a minute earlier" in w for w in res["warnings"])

    def test_a_date_alone_matches_that_day_in_the_tax_timezone(self):
        """A row without a time matches any time that day; the next day's is only similar."""
        assert CLIENT.put("/api/settings/tax-timezone", json={"timezone": "America/New_York", "chosen": True}).status_code == 200
        try:
            execute([dict(INTEREST, date="2025-03-21T02:00:00Z")])  # 10 pm on the 20th in New York
            assert preview([dict(INTEREST, date="2025-03-20")])["results"][0]["status"] == "duplicate"
            res = preview([dict(INTEREST, date="2025-03-21")])["results"][0]
            assert res["status"] == "possible_duplicate"
            assert any("recorded on 2025-03-20" in w for w in res["warnings"])
        finally:
            CLIENT.put("/api/settings/tax-timezone", json={"timezone": "UTC", "chosen": True})

    def test_near_match_transfer_is_possible_duplicate(self):
        execute([dict(BUY, amount="1.0"), TO_COLD])
        near = dict(TO_COLD, amount="0.45", date="2023-01-12T20:00:00Z")
        res = preview([near])["results"][0]
        assert res["status"] == "possible_duplicate"
        assert res["warnings"]


class TestExecute:
    def test_execute_is_atomic_on_invalid_row(self):
        bad = dict(TO_COLD, to_account="Nowhere")
        out = execute([BUY, bad], expect=400)
        assert "No transactions were saved" in out["detail"]
        assert tx_count() == 0

    def test_execute_is_atomic_on_ledger_rejection(self):
        spend = {
            "date": "2023-02-01T00:00:00Z", "type": "Withdrawal", "amount": "5",
            "from_account": "Wallet", "to_account": "External",
            "purpose": "Spent", "proceeds_usd": "1.00",
        }
        out = execute([BUY, TO_COLD, spend], expect=400)
        assert "Not enough BTC" in out["detail"]
        assert tx_count() == 0

    def test_sell_proceeds_stable_across_recalculations(self):
        """Regression: USD sell fee was re-subtracted on every scorched-earth re-lot."""
        sell = {
            "date": "2024-06-01T12:00:00Z", "type": "Sell", "amount": "0.25",
            "from_account": "Exchange BTC", "to_account": "Exchange USD",
            "proceeds_usd": "17500.00", "fee_amount": "10.00", "fee_currency": "USD",
        }
        sell_id = execute([BUY, sell])["created"][1]["id"]
        for month in ("01", "02"):  # backdated buys force full recalculation
            execute([dict(BUY, date=f"2022-{month}-01T00:00:00Z", amount="0.01",
                          cost_basis_usd="100.00", fee_amount=None)])
        tx = CLIENT.get(f"/api/transactions/{sell_id}").json()
        assert Decimal(tx["proceeds_usd"]) == Decimal("17490.00")

    def test_execute_returns_created_ids_in_row_order(self):
        # Submitted out of chronological order; created list follows input order
        out = execute([TO_COLD, BUY])
        assert [c["row"] for c in out["created"]] == [1, 2]
        assert [c["type"] for c in out["created"]] == ["Transfer", "Buy"]


class TestInputFormats:
    @pytest.mark.parametrize("date", [
        "2023-01-10",
        "2023-01-10T15:00:00.123Z",
        "2023-01-10T10:00:00-05:00",
        "01/10/2023",
    ])
    def test_date_formats(self, date):
        res = preview([dict(BUY, date=date)])["results"][0]
        assert res["status"] == "ready", res
        assert res["normalized"]["date"].startswith("2023-01-10")

    def test_json_number_amounts_keep_precision(self):
        row = dict(BUY, amount=0.1, cost_basis_usd=2000.1, fee_amount=None)
        res = preview([row])["results"][0]
        assert res["status"] == "ready", res
        assert res["normalized"]["amount"] == "0.1"

    def test_needs_a_login_or_the_ai_key(self, ai_key_headers):
        anon = TestClient(app)
        assert anon.post("/api/import/entries/preview", json={"rows": [BUY]}).status_code == 401
        r = anon.post("/api/import/entries/preview", json={"rows": [BUY]}, headers=ai_key_headers)
        assert r.status_code == 200, r.text


def test_the_preview_reads_the_year_files_before_its_dry_run(test_engine, monkeypatch):
    """#204: which price filled each value (#208) was looked up inside the
    dry run, reading and fingerprinting each year file not cached (the module
    keeps two), so SQLite's write lock was held the longer. The year files
    are read before the dry run now: while one is read another connection
    can take the write lock, and the lookups inside read none."""
    from datetime import datetime

    from backend.services import hourly_prices
    from backend.services import price_files as pf

    dates = ["2019-03-01T12:00:00Z", "2020-03-01T12:00:00Z", "2021-03-01T12:00:00Z"]
    hours = [hourly_prices.hour_of(datetime.fromisoformat(d.replace("Z", "+00:00"))) for d in dates]
    lines = [pf.YearLine(y, pf.year_start(y), pf.year_end(y), 1, "x") for y in (2019, 2020, 2021)]
    free = []

    def year_file(line, remember=True):
        other = sqlite3.connect(test_engine.url.database, timeout=0)
        try:
            other.execute("BEGIN IMMEDIATE")
            other.rollback()
            free.append(True)
        except sqlite3.OperationalError:  # database is locked
            free.append(False)
        finally:
            other.close()
        return {h: Decimal("40000.00") for h in hours}

    monkeypatch.setattr(pf, "read_manifest", lambda path=None: lines)
    monkeypatch.setattr(hourly_prices, "_year_prices", year_file)
    monkeypatch.setattr(hourly_prices, "hourly_price", lambda db, when, **k: (Decimal("40000.00"), "bitstamp"))
    rows = [{"date": d, "type": "Deposit", "amount": "0.01", "from_account": "External",
             "to_account": "Wallet", "source": "Income"} for d in dates]
    results = preview(rows)["results"]
    assert [r["simulated"]["from_price"]["source"] for r in results] == ["bitstamp"] * 3
    assert free == [True, True, True]
