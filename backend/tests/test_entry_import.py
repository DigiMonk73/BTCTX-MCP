"""
backend/tests/test_entry_import.py

Tests for the JSON entry import (/api/import/entries) used by the MCP server:
validation, FMV autofill, dedup, dry-run simulation, atomic execute.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.main import app

CLIENT: TestClient = None
PRICE = 100000.0  # stubbed historical BTC price


@pytest.fixture(autouse=True, scope="session")
def _set_client(auth_client):
    global CLIENT
    CLIENT = auth_client


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    async def fake_historical(date: str):
        return {"USD": PRICE}

    monkeypatch.setattr(
        "backend.services.entry_import.get_historical_price", fake_historical
    )
    monkeypatch.setattr(
        "backend.services.transaction.get_btc_price",
        lambda timestamp, db: Decimal("100000"),
    )


@pytest.fixture(autouse=True)
def _clean_ledger():
    CLIENT.delete("/api/transactions/delete_all")
    yield
    CLIENT.delete("/api/transactions/delete_all")


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
    # amount = BTC that arrives in cold storage; the network fee is on top
    "date": "2023-01-12T15:00:00Z", "type": "Transfer", "amount": "0.4999",
    "from_account": "Exchange BTC", "to_account": "Wallet",
    "fee_amount": "0.0001", "fee_currency": "BTC",
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

    def test_mybtc_deposit_is_not_autofilled(self):
        dep = {
            "date": "2024-03-01", "type": "Deposit", "amount": "0.001",
            "from_account": "External", "to_account": "Wallet", "source": "MyBTC",
        }
        res = preview([dep])["results"][0]
        assert res["autofilled_fields"] == []
        assert any("cost_basis_usd" in w for w in res["warnings"])


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

    def test_api_key_clients_are_rejected(self, monkeypatch):
        monkeypatch.setattr("backend.main.API_KEY", "k")
        anon = TestClient(app)
        r = anon.post(
            "/api/import/entries/preview", json={"rows": [BUY]}, headers={"X-API-Key": "k"}
        )
        assert r.status_code == 401
