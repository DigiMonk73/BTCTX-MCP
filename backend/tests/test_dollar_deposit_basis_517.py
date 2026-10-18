"""
A dollar deposit's cost basis is no bitcoin's cost (#517): the form before
0.9.2 saved $0 on every dollar deposit, and the API keeps a figure sent
with one. An edit moving such a deposit into Wallet or Exchange BTC kept
it as the cost of the bitcoin it then brought in: a $0 or made-up lot. Now
the edit asks for the coins' cost (or prices an income deposit) unless it
sends one; a bitcoin deposit moved between bitcoin accounts keeps its own.
"""

from decimal import Decimal

import pytest
from sqlalchemy import text

from backend.services.transaction import DEPOSIT_BASIS_REQUIRED
from backend.tests.conftest import STUB_HISTORICAL_USD

BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 2, 3, 4, 99
INTO_BITCOIN = [(BANK, WALLET), (EXCHANGE_USD, EXCHANGE_BTC)]


@pytest.fixture(autouse=True)
def _clean_ledger(auth_client):
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def deposit(client, to_account: int, **fields) -> dict:
    currency = "USD" if to_account in (BANK, EXCHANGE_USD) else "BTC"
    r = client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2024-03-01T12:00:00Z", "from_account_id": EXTERNAL,
        "to_account_id": to_account, "amount": "500" if currency == "USD" else "0.5", "fee_amount": "0",
        "fee_currency": currency, **fields})
    assert r.status_code == 200, r.text
    return r.json()


def lot_costs(test_engine) -> list[Decimal]:
    with test_engine.connect() as con:
        rows = con.execute(text("SELECT cost_basis_usd FROM bitcoin_lots ORDER BY id")).all()
    return [Decimal(str(cost)) for (cost,) in rows]


def into_bitcoin(to_account: int, **fields) -> dict:
    return {"to_account_id": to_account, "amount": "0.5", "fee_currency": "BTC", **fields}


@pytest.mark.parametrize("dollars, bitcoin", INTO_BITCOIN)
@pytest.mark.parametrize("stored", ["0", "250"])
def test_a_dollar_deposit_moved_into_bitcoin_asks_for_the_coins_cost(auth_client, test_engine, dollars, bitcoin,
                                                                     stored):
    tx = deposit(auth_client, dollars, source="N/A", cost_basis_usd=stored)
    assert Decimal(str(tx["cost_basis_usd"])) == Decimal(stored)
    before = auth_client.get(f"/api/transactions/{tx['id']}").json()
    r = auth_client.put(f"/api/transactions/{tx['id']}", json=into_bitcoin(bitcoin))
    assert r.status_code == 422 and DEPOSIT_BASIS_REQUIRED in r.text, r.text
    assert auth_client.get(f"/api/transactions/{tx['id']}").json() == before and lot_costs(test_engine) == []

    r = auth_client.put(f"/api/transactions/{tx['id']}", json=into_bitcoin(bitcoin, cost_basis_usd="17500"))
    assert r.status_code == 200, r.text
    assert lot_costs(test_engine) == [Decimal("17500")]


def test_a_dollar_income_deposit_moved_into_bitcoin_is_valued_at_the_price(auth_client, test_engine):
    """Its stored figure isn't the coins' value at receipt: the price gives it."""
    tx = deposit(auth_client, BANK, source="Income", cost_basis_usd="250")
    r = auth_client.put(f"/api/transactions/{tx['id']}", json=into_bitcoin(WALLET))
    assert r.status_code == 200, r.text
    value = (Decimal("0.5") * Decimal(str(STUB_HISTORICAL_USD))).quantize(Decimal("0.01"))
    assert Decimal(str(r.json()["cost_basis_usd"])) == value and r.json()["cost_basis_from_price"] is True
    assert lot_costs(test_engine) == [value]


def test_a_bitcoin_deposit_moved_to_the_other_bitcoin_account_keeps_its_basis(auth_client, test_engine):
    tx = deposit(auth_client, WALLET, source="MyBTC", cost_basis_usd="12000")
    r = auth_client.put(f"/api/transactions/{tx['id']}", json={"to_account_id": EXCHANGE_BTC})
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["cost_basis_usd"])) == Decimal("12000")
    assert lot_costs(test_engine) == [Decimal("12000")]

