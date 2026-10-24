"""
The past-year warning's dry run finds first only the prices the edit's save
uses (#646). An edit of a row dated in an earlier tax year finds its prices
before the dry run (transaction.find_prices_first, so none is asked for
under the write lock), from the row the edit makes (edited_inputs). A value
the row holds from a price is left blank there only when the save prices it
again, by the save's own conditions: a BTC fee's when its inputs change (the
fee, its currency, the type, the hour), a Spent's proceeds or a gift's value
when the amount or the hour does, an income's when its account, amount, hour
or type does. Before, every such value was blanked: each past-year edit
asked for a price the save never used, the form's unchanged echo included.

"This tax year" is 2026 here (conftest.tax_year), set once the rows are saved.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import hourly_prices
from backend.services import transaction as tx_service
from backend.tests.conftest import default_login

WALLET, EXTERNAL = 2, 99
BTC_FEE = {"fee_amount": "0.0001", "fee_currency": "BTC"}
ROWS = {
    "deposit": {"type": "Deposit", "timestamp": "2024-01-10T12:00:00Z", "from_account_id": EXTERNAL,
                "to_account_id": WALLET, "amount": "1", "fee_amount": "0", "fee_currency": "BTC",
                "source": "MyBTC", "cost_basis_usd": "30000"},
    # Its proceeds typed, its fee's value from the price
    "typed spend": {"type": "Withdrawal", "timestamp": "2024-03-01T12:00:00Z", "from_account_id": WALLET,
                    "to_account_id": EXTERNAL, "amount": "0.1", "purpose": "Spent",
                    "gross_proceeds_usd": "5000", **BTC_FEE},
    # Its proceeds and its fee's value from the price
    "priced spend": {"type": "Withdrawal", "timestamp": "2024-04-01T12:00:00Z", "from_account_id": WALLET,
                     "to_account_id": EXTERNAL, "amount": "0.1", "purpose": "Spent", **BTC_FEE},
    "income": {"type": "Deposit", "timestamp": "2024-05-01T12:00:00Z", "from_account_id": EXTERNAL,
               "to_account_id": WALLET, "amount": "0.05", "fee_amount": "0", "fee_currency": "BTC",
               "source": "Income"},
    "gift": {"type": "Withdrawal", "timestamp": "2024-06-01T12:00:00Z", "from_account_id": WALLET,
             "to_account_id": EXTERNAL, "amount": "0.05", "purpose": "Gift", "fee_amount": "0",
             "fee_currency": "BTC"},
}
# The form's echo: the fields it sends back unchanged (never a priced fee's value)
ECHOED = ("type", "timestamp", "from_account_id", "to_account_id", "amount", "fee_amount", "fee_currency")


class Lookups:
    """The prices asked for while the dry run finds them first."""

    def __init__(self):
        self.finding, self.asked = False, []


@pytest.fixture
def ledger(fresh_app, monkeypatch, tax_year):
    """The rows saved in 2024 (each priced value from a $50,000 price),
    then this tax year 2026; yields (client, {name: id}, the lookups)."""
    lookups = Lookups()

    def price_at(db, when):
        if lookups.finding:
            lookups.asked.append(when)
        at = datetime.fromtimestamp(hourly_prices.hour_of(when), tz=timezone.utc)
        return hourly_prices.Priced(Decimal("50000.00"), "hour", at)

    found_first = tx_service.find_prices_first

    def finding(db, rows):
        lookups.finding = True
        try:
            found_first(db, rows)
        finally:
            lookups.finding = False

    monkeypatch.setattr(hourly_prices, "price_at", price_at)
    monkeypatch.setattr(tx_service, "find_prices_first", finding)
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    ids = {}
    for name, row in ROWS.items():
        r = client.post("/api/transactions", json=row)
        assert r.status_code == 200, (name, r.text)
        ids[name] = r.json()["id"]
    tax_year(2026)
    lookups.asked.clear()
    return client, ids, lookups


def edit(ledger, name: str, **change) -> list:
    """The edit sent without its confirm (the dry run only); the prices it found first."""
    client, ids, lookups = ledger
    lookups.asked.clear()
    r = client.put(f"/api/transactions/{ids[name]}", json=change)
    assert r.status_code in (200, 409), (name, r.text)
    return list(lookups.asked)


def echo(ledger, name: str) -> dict:
    client, ids, _ = ledger
    stored = client.get(f"/api/transactions/{ids[name]}").json()
    return {key: stored[key] for key in ECHOED}


@pytest.mark.parametrize("name", ["typed spend", "priced spend", "income", "gift"])
def test_the_forms_unchanged_echo_finds_no_price(ledger, name):
    assert edit(ledger, name, **echo(ledger, name)) == []


def test_an_amount_edit_of_a_typed_spend_finds_none_for_its_priced_fee(ledger):
    """The fee's value hangs on the fee and the hour, not the amount; the proceeds are typed."""
    assert edit(ledger, "typed spend", amount="0.08") == []


@pytest.mark.parametrize("change", [{"timestamp": "2024-03-01T15:00:00Z"}, {"fee_amount": "0.0002"}])
def test_a_typed_spends_fee_priced_again_is_found_first(ledger, change):
    assert len(edit(ledger, "typed spend", **change)) == 1


@pytest.mark.parametrize("name", ["priced spend", "income", "gift"])
def test_a_value_the_amount_prices_again_is_still_found_first(ledger, name):
    """A Spent's proceeds (its fee's value at the same hour, kept), an
    income's value, a gift's value: one price, at the row's hour."""
    asked = edit(ledger, name, amount="0.04")
    saved_at = datetime.fromisoformat(ROWS[name]["timestamp"].replace("Z", "+00:00"))
    assert [hourly_prices.hour_of(when) for when in asked] == [hourly_prices.hour_of(saved_at)]
