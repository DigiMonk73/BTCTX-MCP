"""
Each account's own cost on the dashboard (#709): the balances route gives
every bitcoin account the cost of the BTC it still holds, its lots' cost
left ("Lot cost", #100), and none to a dollar or fee account. The costs add
up exactly to the total the average cost per BTC is worked out from, so the
opened lines and the card's totals always agree. No figure moves: the
service the reference figures read stays as it was (test_screens_renames_356).
"""

from decimal import ROUND_HALF_DOWN, Decimal

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.tests.conftest import default_login, stub_prices_at

BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, BTC_FEES, USD_FEES = 1, 2, 3, 4, 5, 6
EXTERNAL, COLD, KRAKEN_USD, KRAKEN_BTC = 99, 100, 101, 102


@pytest.fixture
def client(fresh_app, monkeypatch) -> TestClient:
    """Logged in on a database of its own with a second wallet and a second
    exchange (ids 100 to 102)."""
    stub_prices_at(monkeypatch, lambda _when: Decimal("50000"))
    c = TestClient(app)
    assert c.post("/api/login", json=default_login()).status_code == 200
    for kind, name in (("wallet", "Cold Storage"), ("exchange", "Kraken")):
        assert c.post("/api/accounts/", json={"kind": kind, "name": name}).status_code == 201
    return c


def save(client, **fields) -> None:
    r = client.post("/api/transactions", json={"fee_amount": "0", "fee_currency": "BTC", **fields})
    assert r.status_code == 200, r.text


def costs(client) -> dict[int, Decimal | None]:
    rows = client.get("/api/calculations/accounts/balances").json()
    return {r["account_id"]: None if r["cost_basis"] is None else Decimal(str(r["cost_basis"])) for r in rows}


def held(client) -> dict[int, Decimal]:
    rows = client.get("/api/calculations/accounts/balances").json()
    return {r["account_id"]: Decimal(str(r["balance"])) for r in rows}


def test_each_bitcoin_account_gives_what_its_btc_still_held_cost(client):
    save(client, type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=WALLET,
         amount="1", source="MyBTC", cost_basis_usd="30000.00")
    save(client, type="Deposit", timestamp="2024-01-03T12:00:00Z", from_account_id=EXTERNAL, to_account_id=COLD,
         amount="0.5", source="MyBTC", cost_basis_usd="10000.00")
    # 0.3 BTC leaves the wallet, 0.0001 of it the fee: the fee's piece costs
    # $3.00, the moved 0.2999 BTC the rest of $9,000.00 (running cost, #100)
    save(client, type="Transfer", timestamp="2024-02-01T12:00:00Z", from_account_id=WALLET, to_account_id=COLD,
         amount="0.3", fee_amount="0.0001", fee_currency="BTC")
    save(client, type="Buy", timestamp="2024-03-01T12:00:00Z", from_account_id=BANK, to_account_id=EXCHANGE_BTC,
         amount="0.2", cost_basis_usd="8000.00", fee_amount="10", fee_currency="USD")
    # A quarter of the $8,010.00 lot sold: $2,002.50 of its cost goes
    save(client, type="Sell", timestamp="2024-04-01T12:00:00Z", from_account_id=EXCHANGE_BTC,
         to_account_id=EXCHANGE_USD, amount="0.05", proceeds_usd="3000.00", fee_amount="0", fee_currency="USD")
    assert costs(client) == {
        WALLET: Decimal("21000.00"), COLD: Decimal("18997.00"), EXCHANGE_BTC: Decimal("6007.50"),
        KRAKEN_BTC: Decimal("0"),
        BANK: None, EXCHANGE_USD: None, KRAKEN_USD: None, BTC_FEES: None, USD_FEES: None}


def test_the_accounts_costs_add_up_to_the_average_cost_per_btc(client):
    """The average cost is the accounts' costs over the BTC they hold, the
    same sums: an account's cost never differs from the card's total."""
    save(client, type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=WALLET,
         amount="0.33333333", source="MyBTC", cost_basis_usd="10000.01")
    save(client, type="Deposit", timestamp="2024-01-03T12:00:00Z", from_account_id=EXTERNAL, to_account_id=COLD,
         amount="0.7", source="MyBTC", cost_basis_usd="25000.00")
    save(client, type="Transfer", timestamp="2024-02-01T12:00:00Z", from_account_id=WALLET, to_account_id=COLD,
         amount="0.11111111", fee_amount="0.00000777", fee_currency="BTC")
    save(client, type="Buy", timestamp="2024-03-01T12:00:00Z", from_account_id=BANK, to_account_id=KRAKEN_BTC,
         amount="0.03", cost_basis_usd="1999.99", fee_amount="0", fee_currency="USD")
    by_account, btc = costs(client), held(client)
    bitcoin = [i for i, cost in by_account.items() if cost is not None]
    total = sum(by_account[i] for i in bitcoin)
    average = (total / sum(btc[i] for i in bitcoin)).quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)
    assert Decimal(str(client.get("/api/calculations/average-cost-basis").json()["averageCostBasis"])) == average
    # All three costs, less the $0.23 the transfer's network fee took of the wallet's
    assert total == Decimal("36999.77")


def test_an_empty_ledger_costs_nothing(client):
    assert {i: c for i, c in costs(client).items() if c is not None} == {
        WALLET: Decimal("0"), EXCHANGE_BTC: Decimal("0"), COLD: Decimal("0"), KRAKEN_BTC: Decimal("0")}
