"""
backend/tests/test_disposal_proceeds.py

Proceeds for Sells and Spent withdrawals must not shrink on recalculation,
rows saved by older versions must stop shrinking, and Spent withdrawals
imported without proceeds are valued at market instead of $0.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.models.transaction import Transaction

CLIENT: TestClient = None
ENGINE = None
PRICE = {"value": Decimal("100000")}

BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 2, 3, 4, 99


@pytest.fixture(autouse=True, scope="session")
def _set_client(auth_client, test_engine):
    global CLIENT, ENGINE
    CLIENT, ENGINE = auth_client, test_engine


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    PRICE["value"] = Decimal("100000")
    monkeypatch.setattr(
        "backend.services.transaction.get_btc_price", lambda timestamp, db: PRICE["value"]
    )


@pytest.fixture(autouse=True)
def _clean_ledger():
    CLIENT.delete("/api/transactions/delete_all")
    yield
    CLIENT.delete("/api/transactions/delete_all")


def post(**tx):
    r = CLIENT.post("/api/transactions", json=tx)
    assert r.status_code == 200, r.text
    return r.json()


def get(tx_id):
    return CLIENT.get(f"/api/transactions/{tx_id}").json()


def buy(month=1, amount="0.1", year=2023):
    return post(type="Buy", timestamp=f"{year}-{month:02d}-01T00:00:00Z",
                from_account_id=BANK, to_account_id=EXCHANGE_BTC,
                amount=amount, cost_basis_usd="2000.00")


def force_recalc(n=3):
    """Backdated buys trigger a full scorched-earth recalculation each."""
    for i in range(n):
        buy(month=i + 1, amount="0.001", year=2022)


def forget_gross(tx_id):
    """Simulate a row saved before gross_proceeds_usd was always recorded."""
    db = sessionmaker(bind=ENGINE)()
    try:
        db.query(Transaction).filter(Transaction.id == tx_id).update(
            {Transaction.gross_proceeds_usd: None}
        )
        db.commit()
    finally:
        db.close()


SPENT = dict(type="Withdrawal", timestamp="2024-06-01T00:00:00Z",
             from_account_id=EXCHANGE_BTC, to_account_id=EXTERNAL,
             amount="0.01", fee_amount="0.0001", fee_currency="BTC",
             purpose="Spent", proceeds_usd="1000.00")


class TestSpentWithdrawals:
    def test_proceeds_stable_across_recalculations(self):
        buy()
        tx = post(**SPENT)
        net = Decimal(get(tx["id"])["proceeds_usd"])
        assert net == Decimal("990.10")  # fee offset applied once
        force_recalc()
        after = get(tx["id"])
        assert Decimal(after["proceeds_usd"]) == net
        assert Decimal(after["gross_proceeds_usd"]) == Decimal("1000.00")

    def test_legacy_row_stops_shrinking_and_recovers_gross(self):
        buy()
        tx = post(**SPENT)
        forget_gross(tx["id"])  # old data: proceeds_usd already net, no gross
        force_recalc()
        after = get(tx["id"])
        assert Decimal(after["proceeds_usd"]) == Decimal("990.10")
        assert Decimal(after["gross_proceeds_usd"]) == Decimal("1000.00")

    def test_missing_proceeds_valued_at_market_once(self):
        buy()
        no_proceeds = {k: v for k, v in SPENT.items() if k != "proceeds_usd"}
        tx = post(**no_proceeds)
        first = get(tx["id"])
        # 0.01 BTC at $100k = $1000 gross; realized gain is not a full-basis loss
        assert Decimal(first["gross_proceeds_usd"]) == Decimal("1000.00")
        assert Decimal(first["realized_gain_usd"]) > 0

        PRICE["value"] = Decimal("1")  # the stored value must not be re-fetched
        force_recalc()
        assert Decimal(get(tx["id"])["gross_proceeds_usd"]) == Decimal("1000.00")

    def test_river_withdrawal_without_proceeds_is_not_a_fake_loss(self):
        buy()
        r = CLIENT.post("/api/import/river/execute", json={"rows": [{
            "date": "2024-06-01T00:00:00Z", "type": "Withdrawal", "amount": "0.01",
            "from_account": "Exchange BTC", "to_account": "External", "purpose": "Spent",
        }]})
        assert r.status_code == 200, r.text
        tx = next(t for t in CLIENT.get("/api/transactions").json() if t["type"] == "Withdrawal")
        # basis 0.01 of $2000/0.1 = $200; proceeds $1000 -> +$800, not -$200
        assert Decimal(tx["realized_gain_usd"]) == Decimal("800.00")

    def test_explicit_zero_proceeds_is_respected(self):
        buy()
        tx = post(**dict(SPENT, proceeds_usd="0", fee_amount="0"))
        assert Decimal(get(tx["id"])["realized_gain_usd"]) == Decimal("-200.00")

    def test_editing_proceeds_updates_the_gross(self):
        buy()
        tx = post(**SPENT)
        r = CLIENT.put(f"/api/transactions/{tx['id']}", json={"proceeds_usd": "2000.00"})
        assert r.status_code == 200, r.text
        after = r.json()
        assert Decimal(after["gross_proceeds_usd"]) == Decimal("2000.00")
        assert Decimal(after["proceeds_usd"]) == Decimal("1980.20")

    def test_gift_ignores_proceeds(self):
        buy()
        tx = post(**dict(SPENT, purpose="Gift", proceeds_usd="0"))
        force_recalc(1)
        assert Decimal(get(tx["id"])["realized_gain_usd"]) == Decimal("0")


SELL = dict(type="Sell", timestamp="2024-06-01T00:00:00Z",
            from_account_id=EXCHANGE_BTC, to_account_id=EXCHANGE_USD,
            amount="0.05", fee_amount="10.00", fee_currency="USD")


class TestSells:
    def test_api_sell_with_only_proceeds_is_stable(self):
        buy()
        tx = post(**SELL, proceeds_usd="5000.00")
        force_recalc()
        after = get(tx["id"])
        assert Decimal(after["proceeds_usd"]) == Decimal("4990.00")
        assert Decimal(after["gross_proceeds_usd"]) == Decimal("5000.00")

    def test_legacy_sell_stops_shrinking_and_recovers_gross(self):
        buy()
        tx = post(**SELL, proceeds_usd="5000.00")
        forget_gross(tx["id"])  # old CSV/River import: net stored, no gross
        force_recalc()
        after = get(tx["id"])
        assert Decimal(after["proceeds_usd"]) == Decimal("4990.00")
        assert Decimal(after["gross_proceeds_usd"]) == Decimal("5000.00")

    def test_ui_style_sell_unchanged(self):
        buy()
        tx = post(**SELL, gross_proceeds_usd="5000.00")
        force_recalc()
        assert Decimal(get(tx["id"])["proceeds_usd"]) == Decimal("4990.00")


class TestRecalculateEndpoint:
    def test_repairs_legacy_rows_without_other_edits(self):
        buy()
        spent = post(**SPENT)
        sell = post(**SELL, proceeds_usd="5000.00")
        forget_gross(spent["id"])
        forget_gross(sell["id"])

        r = CLIENT.post("/api/transactions/recalculate")
        assert r.status_code == 200, r.text
        assert r.json()["transactions"] == 3
        assert Decimal(get(spent["id"])["gross_proceeds_usd"]) == Decimal("1000.00")
        assert Decimal(get(sell["id"])["gross_proceeds_usd"]) == Decimal("5000.00")

        # Idempotent
        before = CLIENT.get("/api/transactions").json()
        CLIENT.post("/api/transactions/recalculate")
        assert CLIENT.get("/api/transactions").json() == before
