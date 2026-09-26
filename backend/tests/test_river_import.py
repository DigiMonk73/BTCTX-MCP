"""
backend/tests/test_river_import.py

Tests for the River bitcoin-activity CSV import (adapter, funding
heuristic, dedup/merge engine, preview/execute endpoints).

All fixture data is SYNTHETIC — modeled on real River export patterns
(recurring no-fee buys, irregular fee buys, untagged on-chain moves,
monthly Interest payouts) but never copied from a real account.
"""

import io
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List

import pytest
from fastapi.testclient import TestClient

from backend.services.river_import import (
    STATUS_DISCREPANCY,
    STATUS_MATCHED,
    adapt_river_rows,
    parse_river_csv,
)

# Authenticated TestClient (set by autouse fixture from conftest.py)
CLIENT: TestClient = None


@pytest.fixture(autouse=True, scope="session")
def _set_client(auth_client):
    global CLIENT
    CLIENT = auth_client


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Tests must never hit price APIs: stub historical FMV lookups and the
    live price used for transfer-fee/withdrawal valuation."""
    async def fake_historical(date: str):
        return {"USD": 100000.0}

    monkeypatch.setattr(
        "backend.services.bitcoin.get_historical_price", fake_historical
    )
    monkeypatch.setattr(
        "backend.services.transaction.get_btc_price",
        lambda timestamp, db: Decimal("100000"),
    )


RIVER_HEADER = (
    "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,"
    "Fee Amount,Fee Currency,Tag"
)


def river_csv(rows: List[str]) -> bytes:
    return ("\n".join([RIVER_HEADER] + rows) + "\n").encode("utf-8")


# Five recurring $25 no-fee buys (auto-buy pattern → Bank), one irregular
# $150 buy with a fee (→ Exchange USD), one sell, one Interest payout, one
# untagged send (cold storage), one untagged receive, one tagged Withdrawal.
SYNTHETIC_ROWS = [
    "2026-01-05 12:00:00,25.00,USD,0.00030000,BTC,,,Buy",
    "2026-01-12 12:00:00,25.00,USD,0.00031000,BTC,,,Buy",
    "2026-01-19 12:00:00,25.00,USD,0.00032000,BTC,,,Buy",
    "2026-01-26 12:00:00,25.00,USD,0.00033000,BTC,,,Buy",
    "2026-02-02 12:00:00,25.00,USD,0.00034000,BTC,,,Buy",
    "2026-02-03 15:30:00,148.50,USD,0.00180000,BTC,1.50,USD,Buy",
    "2026-02-10 16:00:00,0.00050000,BTC,55.00,USD,0.55,USD,Sell",
    "2026-02-01 09:00:00,,,0.00002000,BTC,,,Interest",
    "2026-02-15 10:00:00,0.00100000,BTC,,,0.00000500,BTC,",
    "2026-03-01 10:00:00,,,0.00060000,BTC,,,",
    "2026-03-10 10:00:00,0.00010000,BTC,,,0.00000200,BTC,Withdrawal",
]


def adapt(rows: List[str]):
    parsed, errors = parse_river_csv(river_csv(rows))
    assert not errors, f"unexpected parse errors: {errors}"
    return adapt_river_rows(parsed)


def by_row(proposals, row_number: int):
    return next(p for p in proposals if p.row_number == row_number)


def delete_all_transactions():
    r = CLIENT.delete("/api/transactions/delete_all")
    assert r.status_code in (200, 204)


def create_tx(tx_data: Dict) -> Dict:
    r = CLIENT.post("/api/transactions", json=tx_data)
    assert r.is_success, f"create_tx failed ({r.status_code}): {r.text}"
    return r.json()


def ts(month: int, day: int, hour: int = 12) -> str:
    return datetime(2026, month, day, hour, tzinfo=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


# ---------------------------------------------------------------------------
# Adapter unit tests (no DB)
# ---------------------------------------------------------------------------

class TestRiverParser:
    def test_rejects_non_river_headers(self):
        rows, errors = parse_river_csv(b"date,type,amount\n2026-01-01,Buy,1\n")
        assert not rows
        assert errors and "River" in errors[0].message

    def test_rejects_bad_date(self):
        rows, errors = parse_river_csv(river_csv(["01/05/2026,25.00,USD,0.0003,BTC,,,Buy"]))
        assert not rows
        assert errors and errors[0].column == "date"

    def test_parses_utc_timestamps(self):
        rows, errors = parse_river_csv(river_csv(SYNTHETIC_ROWS))
        assert not errors
        assert len(rows) == len(SYNTHETIC_ROWS)
        assert rows[0].timestamp == datetime(2026, 1, 5, 12, tzinfo=timezone.utc)


class TestRiverAdapter:
    def test_recurring_buys_default_to_bank(self):
        proposals, _, _ = adapt(SYNTHETIC_ROWS)
        for row_number in (2, 3, 4, 5, 6):  # the five $25 buys
            p = by_row(proposals, row_number)
            assert p.type == "Buy"
            assert p.from_account == "Bank"
            assert p.to_account == "Exchange BTC"
            assert p.funding_choices == ["Bank", "Exchange USD"]

    def test_irregular_buy_defaults_to_exchange_usd(self):
        proposals, _, _ = adapt(SYNTHETIC_ROWS)
        p = by_row(proposals, 7)
        assert p.type == "Buy"
        assert p.from_account == "Exchange USD"
        assert p.amount == Decimal("0.00180000")
        assert p.cost_basis_usd == Decimal("148.50")  # sent, fee separate
        assert p.fee_amount == Decimal("1.50")
        assert p.fee_currency == "USD"

    def test_sell_mapping(self):
        proposals, _, _ = adapt(SYNTHETIC_ROWS)
        p = by_row(proposals, 8)
        assert p.type == "Sell"
        assert p.from_account == "Exchange BTC"
        assert p.to_account == "Exchange USD"
        assert p.amount == Decimal("0.00050000")
        assert p.proceeds_usd == Decimal("55.55")  # Received 55.00 + fee 0.55
        assert p.fee_amount == Decimal("0.55")

    def test_sell_proceeds_are_gross_of_the_usd_fee(self):
        # River's Received Amount on a Sell is what landed in the account,
        # after River's fee (receipt: subtotal - fee = received). BitcoinTX's
        # proceeds_usd is the gross before fees, so gross = received + fee.
        proposals, _, _ = adapt(["2026-07-31 20:16:07,0.01000000,BTC,990.00,USD,10.00,USD,Sell"])
        assert proposals[0].proceeds_usd == Decimal("1000.00")

    def test_sell_without_fee_keeps_received_as_proceeds(self):
        proposals, _, _ = adapt(["2026-07-31 20:16:07,0.01000000,BTC,990.00,USD,,,Sell"])
        assert proposals[0].proceeds_usd == Decimal("990.00")

    def test_interest_maps_to_deposit(self):
        proposals, _, _ = adapt(SYNTHETIC_ROWS)
        p = by_row(proposals, 9)
        assert p.type == "Deposit"
        assert p.from_account == "External"
        assert p.to_account == "Exchange BTC"
        assert p.source == "Interest"
        assert p.cost_basis_usd is None  # FMV filled by router autofill

    def test_untagged_send_maps_to_transfer_with_fee(self):
        proposals, _, _ = adapt(SYNTHETIC_ROWS)
        p = by_row(proposals, 10)
        assert p.type == "Transfer"
        assert p.from_account == "Exchange BTC"
        assert p.to_account == "Wallet"
        assert p.amount == Decimal("0.00100000")
        assert p.fee_amount == Decimal("0.00000500")
        assert p.fee_currency == "BTC"
        assert p.type_choices == ["Transfer", "Withdrawal"]

    def test_untagged_receive_maps_to_transfer_from_wallet(self):
        proposals, _, _ = adapt(SYNTHETIC_ROWS)
        p = by_row(proposals, 11)
        assert p.type == "Transfer"
        assert p.from_account == "Wallet"
        assert p.to_account == "Exchange BTC"
        assert p.fee_amount is None  # River can't see wallet-side fee
        assert p.type_choices == ["Transfer", "Deposit"]

    def test_tagged_withdrawal(self):
        proposals, _, _ = adapt(SYNTHETIC_ROWS)
        p = by_row(proposals, 12)
        assert p.type == "Withdrawal"
        assert p.to_account == "External"
        assert p.purpose == "Spent"
        assert p.type_choices == ["Withdrawal", "Transfer"]

    def test_unknown_pattern_warns_and_skips(self):
        proposals, _, warnings = adapt(["2026-01-01 10:00:00,10.00,USD,,,,,"])
        assert not proposals
        assert warnings and "Unrecognized" in warnings[0].message

    def test_all_synthetic_rows_covered(self):
        proposals, errors, warnings = adapt(SYNTHETIC_ROWS)
        assert len(proposals) == len(SYNTHETIC_ROWS)
        assert not errors and not warnings


# ---------------------------------------------------------------------------
# Preview endpoint (dedup + FMV autofill)
# ---------------------------------------------------------------------------

def preview(rows: List[str]) -> Dict:
    r = CLIENT.post(
        "/api/import/river/preview",
        files={"file": ("river.csv", io.BytesIO(river_csv(rows)), "text/csv")},
    )
    assert r.status_code == 200, f"preview failed: {r.status_code} {r.text}"
    return r.json()


def execute(rows: List[Dict]) -> Dict:
    r = CLIENT.post("/api/import/river/execute", json={"rows": rows})
    assert r.status_code == 200, f"execute failed: {r.status_code} {r.text}"
    return r.json()


def proposals_to_execute_rows(data: Dict, statuses=("new",)) -> List[Dict]:
    keys = (
        "date", "type", "amount", "from_account", "to_account",
        "cost_basis_usd", "proceeds_usd", "fee_amount", "fee_currency",
        "source", "purpose",
    )
    return [
        {k: p[k] for k in keys}
        for p in data["proposals"]
        if p["status"] in statuses
    ]


class TestPreview:
    def test_fresh_db_all_rows_new_and_fmv_autofilled(self):
        delete_all_transactions()
        data = preview(SYNTHETIC_ROWS)
        assert data["success"] is True
        assert data["total_rows"] == len(SYNTHETIC_ROWS)
        assert data["new_count"] == len(SYNTHETIC_ROWS)
        assert data["matched_count"] == 0

        interest = next(p for p in data["proposals"] if p["source"] == "Interest")
        # 0.00002 BTC * $100,000 stub price = $2.00
        assert Decimal(interest["cost_basis_usd"]) == Decimal("2.00")
        assert interest["basis_autofilled"] is True

    def test_existing_tx_marked_matched(self):
        delete_all_transactions()
        # Manual entry ~3h off River's timestamp, same amount/basis
        create_tx({
            "type": "Buy",
            "timestamp": ts(1, 5, 15),
            "from_account_id": 1,
            "to_account_id": 4,
            "amount": "0.00030000",
            "fee_amount": "0",
            "fee_currency": "USD",
            "cost_basis_usd": "25.00",
        })
        data = preview(SYNTHETIC_ROWS)
        matched = [p for p in data["proposals"] if p["status"] == STATUS_MATCHED]
        assert len(matched) == 1
        assert matched[0]["row_number"] == 2
        assert data["new_count"] == len(SYNTHETIC_ROWS) - 1

    def test_same_amount_different_basis_is_discrepancy(self):
        delete_all_transactions()
        create_tx({
            "type": "Buy",
            "timestamp": ts(1, 5, 15),
            "from_account_id": 1,
            "to_account_id": 4,
            "amount": "0.00030000",
            "fee_amount": "0",
            "fee_currency": "USD",
            "cost_basis_usd": "10.00",  # wrong basis vs River's $25
        })
        data = preview(SYNTHETIC_ROWS)
        disc = [p for p in data["proposals"] if p["status"] == STATUS_DISCREPANCY]
        assert len(disc) == 1
        assert disc[0]["row_number"] == 2
        assert "differs" in disc[0]["discrepancy"]

    def test_approximate_manual_transfer_is_fuzzy_discrepancy(self):
        delete_all_transactions()
        # Seed BTC so the transfer/manual entry has lots to draw on
        create_tx({
            "type": "Deposit",
            "timestamp": ts(1, 1),
            "from_account_id": 99,
            "to_account_id": 4,
            "amount": "0.01000000",
            "fee_amount": "0",
            "fee_currency": "BTC",
            "cost_basis_usd": "1000.00",
            "source": "MyBTC",
        })
        # Manual transfer with an approximated amount (~3% off River's)
        create_tx({
            "type": "Transfer",
            "timestamp": ts(2, 15, 8),
            "from_account_id": 4,
            "to_account_id": 2,
            "amount": "0.00103000",
            "fee_amount": "0.00000500",
            "fee_currency": "BTC",
        })
        data = preview(["2026-02-15 10:00:00,0.00100000,BTC,,,0.00000500,BTC,"])
        p = data["proposals"][0]
        assert p["status"] == STATUS_DISCREPANCY
        assert "different amount" in p["discrepancy"]


# ---------------------------------------------------------------------------
# Execute endpoint (atomic import, idempotency)
# ---------------------------------------------------------------------------

class TestExecute:
    def test_full_import_then_idempotent_reimport(self):
        delete_all_transactions()
        data = preview(SYNTHETIC_ROWS)
        rows = proposals_to_execute_rows(data)
        assert len(rows) == len(SYNTHETIC_ROWS)

        result = execute(rows)
        assert result["imported_count"] == len(SYNTHETIC_ROWS)
        assert result["skipped_existing"] == 0

        # Re-running the same preview now matches everything
        data2 = preview(SYNTHETIC_ROWS)
        assert data2["matched_count"] == len(SYNTHETIC_ROWS)
        assert data2["new_count"] == 0

        # Double-submit guard: executing the same rows imports nothing
        result2 = execute(rows)
        assert result2["imported_count"] == 0
        assert result2["skipped_existing"] == len(rows)

    def test_sell_lands_at_rivers_received_amount(self):
        """The fee is subtracted once: net proceeds (Form 8949) and the cash
        credited to Exchange USD both equal River's Received Amount."""
        delete_all_transactions()
        data = preview([
            "2026-07-01 12:00:00,1000.00,USD,0.01000000,BTC,,,Buy",
            "2026-07-31 20:16:07,0.00500000,BTC,990.00,USD,10.00,USD,Sell",
        ])
        execute(proposals_to_execute_rows(data))

        sell = next(t for t in CLIENT.get("/api/transactions").json() if t["type"] == "Sell")
        assert Decimal(str(sell["gross_proceeds_usd"])) == Decimal("1000.00")
        assert Decimal(str(sell["proceeds_usd"])) == Decimal("990.00")

        balances = CLIENT.get("/api/calculations/accounts/balances").json()
        exchange_usd = next(b for b in balances if b["account_id"] == 3)
        assert round(exchange_usd["balance"], 2) == -10.00  # -1000 buy + 990 sell

    def test_funding_toggle_override_is_respected(self):
        delete_all_transactions()
        # The recurrence heuristic needs the full file: all five $25 buys
        data = preview(SYNTHETIC_ROWS[:5])
        rows = proposals_to_execute_rows(data)
        assert all(r["from_account"] == "Bank" for r in rows)
        rows[0]["from_account"] = "Exchange USD"  # user flips the toggle

        result = execute(rows[:1])
        assert result["imported_count"] == 1

        r = CLIENT.get("/api/transactions")
        txs = r.json()
        assert len(txs) == 1
        assert txs[0]["from_account_id"] == 3  # Exchange USD

    def test_invalid_row_rejected_with_400(self):
        delete_all_transactions()
        r = CLIENT.post("/api/import/river/execute", json={"rows": [{
            "date": ts(1, 5),
            "type": "Buy",
            "amount": "0.001",
            "from_account": "Wallet",  # invalid funding account for Buy
            "to_account": "Exchange BTC",
            "cost_basis_usd": "25.00",
        }]})
        assert r.status_code == 400
        assert "Bank" in r.text

    def test_atomic_rollback_on_failure(self):
        delete_all_transactions()
        # The sell predates the buy, so it is processed first and fails
        # (no lots) — the entire batch must roll back.
        rows = [
            {
                "date": ts(2, 1),
                "type": "Sell",
                "amount": "0.50000000",
                "from_account": "Exchange BTC",
                "to_account": "Exchange USD",
                "proceeds_usd": "50000.00",
            },
            {
                "date": ts(2, 2),
                "type": "Buy",
                "amount": "0.00030000",
                "from_account": "Bank",
                "to_account": "Exchange BTC",
                "cost_basis_usd": "25.00",
            },
        ]
        r = CLIENT.post("/api/import/river/execute", json={"rows": rows})
        assert r.status_code in (400, 500)
        assert "No transactions were saved" in r.text

        txs = CLIENT.get("/api/transactions").json()
        assert len(txs) == 0


def test_a_fee_in_an_unexpected_currency_is_flagged():
    """F21: River's Fee Currency column was ignored (forced by row type)."""
    proposals, errors, warnings = adapt([
        "2026-02-03 15:30:00,148.50,USD,0.00180000,BTC,0.00001,BTC,Buy",
        "2026-02-15 10:00:00,0.00100000,BTC,,,0.50,USD,",
        "2026-02-16 10:00:00,0.00100000,BTC,,,0.00000500,BTC,",
    ])
    flagged = sorted(w.row_number for w in warnings if w.column == "Fee Currency")
    assert flagged == [2, 3]
