"""
Ledger Review and its hourly check by currency (spec 1.4, 5.13, 5.15's "by
currency"; card B3 #348): each check that asks whether an account holds
bitcoin asks the book, so a second wallet's rows are listed as the first
one's are, and a second bank's never.
"""

from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.transaction import Transaction
from backend.services import hourly_prices
from backend.tests.conftest import default_login, stub_prices_at

COLD, CREDIT_UNION, EXTERNAL = 100, 101, 99


def price_of(when: datetime) -> Decimal:
    """Each hour its own price, so a value priced at the day shows."""
    return Decimal(50000 + (hourly_prices.hour_of(when) // 3600) % 1000)


@pytest.fixture
def client(gate_open, fresh_app, monkeypatch) -> TestClient:
    stub_prices_at(monkeypatch, price_of)
    c = TestClient(app)
    assert c.post("/api/login", json=default_login()).status_code == 200
    for kind, name in (("wallet", "Cold Storage"), ("bank", "Credit Union")):
        assert c.post("/api/accounts/", json={"kind": kind, "name": name}).status_code == 201
    deposit(c, COLD, "MyBTC", amount="1", cost_basis_usd="20000", timestamp="2024-01-02T12:00:00Z")
    return c


def deposit(client, into, source, **fields) -> int:
    r = client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2024-06-15T15:00:00Z", "from_account_id": EXTERNAL, "to_account_id": into,
        "amount": "0.01", "fee_amount": "0", "source": source, **fields})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def withdrawal(client, purpose, **fields) -> int:
    r = client.post("/api/transactions", json={
        "type": "Withdrawal", "timestamp": "2024-07-01T15:00:00Z", "from_account_id": COLD,
        "to_account_id": EXTERNAL, "amount": "0.01", "fee_amount": "0", "purpose": purpose, **fields})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def stored(fresh_app, tx_id, **values) -> None:
    """What an older BitcoinTX could have saved, written over the row."""
    db = fresh_app()
    t = db.get(Transaction, tx_id)
    for key, value in values.items():
        setattr(t, key, value)
    db.commit()
    db.close()


def listed(client) -> dict[str, list[int]]:
    review = client.get("/api/review").json()
    return {c["key"]: [item["id"] for item in c["items"]] for c in review["checks"]}


def test_a_second_wallets_deposits_are_checked(client, fresh_app):
    gift = deposit(client, COLD, "Gift", cost_basis_usd="300")
    mybtc = deposit(client, COLD, "MyBTC", cost_basis_usd="0")
    inherited = deposit(client, COLD, "Inherited", cost_basis_usd="400", acquired_at="2024-05-01")
    stored(fresh_app, inherited, acquired_at=None)
    income = deposit(client, COLD, "Income", cost_basis_usd="600")
    typed_off = deposit(client, COLD, "Income", cost_basis_usd="100", timestamp="2024-06-16T15:00:00Z")
    stored(fresh_app, income, cost_basis_usd=Decimal("0"))
    deposit(client, CREDIT_UNION, "N/A", amount="500")
    found = listed(client)
    assert found["original_date_missing"] == [1, gift, mybtc]  # My BTC and Gift deposits without a date
    assert found["inherited_without_date"] == [inherited]
    assert found["deposit_without_basis"] == [mybtc]
    assert found["income_without_value"] == [income]
    assert found["income_value_off"] == [typed_off]


def test_a_second_wallets_withdrawals_are_checked(client, fresh_app):
    spent = withdrawal(client, "Spent", proceeds_usd="0")
    lost = withdrawal(client, "Lost")
    stored(fresh_app, lost, realized_gain_usd=Decimal("-100"))
    gift = withdrawal(client, "Gift", fmv_usd="0")
    expenses = withdrawal(client, "Spent", proceeds_usd="50")
    stored(fresh_app, expenses, purpose="Expenses")
    found = listed(client)
    assert found["zero_proceeds_spend"] == [spent]
    assert found["lost_with_loss"] == [lost]
    assert found["gift_without_value"] == [gift]
    assert found["withdrawal_purpose_unknown"] == [expenses]


def test_the_hourly_check_offers_a_second_wallets_day_priced_values(client, monkeypatch):
    stub_prices_at(monkeypatch, price_of, moment="day")
    income = deposit(client, COLD, "Income")
    gift = withdrawal(client, "Gift")
    stub_prices_at(monkeypatch, price_of)
    assert listed(client)["day_priced_values"] == [income, gift]


@pytest.mark.parametrize("kind, from_id, to_id, dollars", [
    ("Deposit", 99, 101, True),      # into a second bank
    ("Withdrawal", 102, 99, True),   # from a second exchange's USD
    ("Transfer", 102, 1, True),
    ("Deposit", 99, 100, False),     # into a second wallet
    ("Transfer", 103, 100, False),
    ("Buy", 102, 103, False),        # a Buy's amount is bitcoin
    ("Deposit", 99, 999, False),     # only External and a missing account: unknown, shown as BTC
    ("Withdrawal", 5, 99, False),    # a fee account is never yours
])
def test_an_items_unit_is_its_accounts_currency(kind, from_id, to_id, dollars):
    """Ledger Review shows an item's amount in dollars when a dollar account
    of yours, and no bitcoin account, is on a side (review._in_dollars)."""
    from backend.services.review import _in_dollars
    from backend.tests.account_pairs import BOOK
    row = Transaction(type=kind, from_account_id=from_id, to_account_id=to_id)
    assert _in_dollars(row, BOOK) is dollars
