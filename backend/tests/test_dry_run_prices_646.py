"""
The past-year warning's dry run finds first the prices the edit's save uses,
and no other (#646). An edit of a row dated in an earlier tax year finds its
prices before the dry run (transaction.find_prices_first, so none is asked
for under the write lock), from the row the edit makes (edited_inputs): the
stored row with the edit, as the save's first steps leave it, a value it
holds from a price blank only when the save prices it again (a BTC fee's
when its inputs change, a Spent's proceeds or a gift's value when the amount
or the hour does, an income's when its account, amount, hour or type does).
Before, every such value was blanked, so each past-year edit asked for a
price the save never used, the form's unchanged echo included; and a value
a type change or a move into a bitcoin account leaves to be priced wasn't
found first.

Each case counts the prices found first, and those the dry run's save then
asks for, hour or day. "This tax year" is 2026 while an edit is sent
(conftest.tax_year), 2009 while the rows are saved.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import hourly_prices, price_history
from backend.services import transaction as tx_service
from backend.tests.conftest import default_login

BANK, WALLET, EXTERNAL = 1, 2, 99
BTC_FEE = {"fee_amount": "0.0001", "fee_currency": "BTC"}
NO_FEE = {"fee_amount": "0", "fee_currency": "BTC"}


def spend(when: str, **more) -> dict:
    return {"type": "Withdrawal", "timestamp": f"{when}T12:00:00Z", "from_account_id": WALLET,
            "to_account_id": EXTERNAL, "amount": "0.1", "purpose": "Spent", **BTC_FEE, **more}


ROWS = {
    "typed spend": spend("2024-03-01", gross_proceeds_usd="5000"),  # its fee's value from the price
    "priced spend": spend("2024-04-01"),  # its proceeds and its fee's value from the price
    "income": {"type": "Deposit", "timestamp": "2024-05-01T12:00:00Z", "from_account_id": EXTERNAL,
               "to_account_id": WALLET, "amount": "0.05", "source": "Income", **NO_FEE},
    "gift": {"type": "Withdrawal", "timestamp": "2024-06-01T12:00:00Z", "from_account_id": WALLET,
             "to_account_id": EXTERNAL, "amount": "0.05", "purpose": "Gift", **NO_FEE},
}
# What the form sends back unchanged: every field it shows, the values as
# shown (never a priced fee's value)
SHOWN = ("type", "timestamp", "from_account_id", "to_account_id", "amount", "fee_amount", "fee_currency",
         "source", "purpose", "acquired_at", "broker_reporting")
SHOWN_VALUES = {"Deposit": ("cost_basis_usd",), "Withdrawal": ("gross_proceeds_usd", "fmv_usd")}


class Ledger:
    """A ledger of its own; each price asked for is noted: (found first?, "hour" or "day", when)."""

    def __init__(self, client, tax_year):
        self.client, self.tax_year = client, tax_year
        self.finding, self.moment, self.asked = False, "hour", []

    def add(self, row: dict, moment: str = "hour") -> int:
        """Saved in its year (this tax year 2009), its values priced at the hour or the day."""
        self.moment = moment
        r = self.client.post("/api/transactions", json=row)
        self.moment = "hour"
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def edit(self, tx_id: int, change: dict) -> tuple[set, set]:
        """The edit sent in 2026, without its confirm: (the prices found
        first, the prices the dry run's save asked for)."""
        self.tax_year(2026)
        self.asked.clear()
        r = self.client.put(f"/api/transactions/{tx_id}", json=change)
        self.tax_year(2009)
        assert r.status_code in (200, 409), r.text
        return ({(at, when) for first, at, when in self.asked if first},
                {(at, when) for first, at, when in self.asked if not first})

    def echo(self, tx_id: int) -> dict:
        stored = self.client.get(f"/api/transactions/{tx_id}").json()
        return {key: stored[key] for key in SHOWN + SHOWN_VALUES.get(stored["type"], ())}


@pytest.fixture
def ledger(fresh_app, monkeypatch, tax_year):
    """A 2024 deposit to spend from, and every price noted."""
    lg = Ledger(TestClient(app), tax_year)

    def price_at(db, when):
        lg.asked.append((lg.finding, "hour", hourly_prices.hour_of(when)))
        at = datetime.fromtimestamp(hourly_prices.hour_of(when), tz=timezone.utc)
        return hourly_prices.Priced(Decimal("50000.00"), lg.moment, at)

    def daily_price(db, when):
        lg.asked.append((lg.finding, "day", price_history.utc_day(when)))
        return Decimal("40000.00")

    found_first = tx_service.find_prices_first

    def finding(db, rows):
        lg.finding = True
        try:
            found_first(db, rows)
        finally:
            lg.finding = False

    monkeypatch.setattr(hourly_prices, "price_at", price_at)
    monkeypatch.setattr(price_history, "daily_price", daily_price)
    monkeypatch.setattr(tx_service, "find_prices_first", finding)
    assert lg.client.post("/api/login", json=default_login()).status_code == 200
    lg.add({"type": "Deposit", "timestamp": "2024-01-10T12:00:00Z", "from_account_id": EXTERNAL,
            "to_account_id": WALLET, "amount": "5", "source": "MyBTC", "cost_basis_usd": "30000", **NO_FEE})
    return lg


def hour(when: str) -> tuple[str, int]:
    return "hour", hourly_prices.hour_of(datetime.fromisoformat(when.replace("Z", "+00:00")))


@pytest.mark.parametrize("name", list(ROWS))
def test_the_forms_unchanged_echo_finds_no_price(ledger, name):
    tx_id = ledger.add(ROWS[name])
    assert ledger.edit(tx_id, ledger.echo(tx_id)) == (set(), set())


def test_an_amount_edit_of_a_typed_spend_finds_none_for_its_priced_fee(ledger):
    """The fee's value hangs on the fee and the hour, not the amount; the proceeds are typed."""
    assert ledger.edit(ledger.add(ROWS["typed spend"]), {"amount": "0.08"}) == (set(), set())


@pytest.mark.parametrize("change, at", [({"timestamp": "2024-03-01T15:00:00Z"}, "2024-03-01T15:00:00Z"),
                                        ({"fee_amount": "0.0002"}, "2024-03-01T12:00:00Z")])
def test_a_typed_spends_fee_priced_again_is_found_first(ledger, change, at):
    found, asked = ledger.edit(ledger.add(ROWS["typed spend"]), change)
    assert found == asked == {hour(at)}


@pytest.mark.parametrize("name", ["priced spend", "income", "gift"])
def test_a_value_the_amount_prices_again_is_found_first(ledger, name):
    """A Spent's proceeds (its fee's value kept), an income's, a gift's: one price, at the row's hour."""
    found, asked = ledger.edit(ledger.add(ROWS[name]), {"amount": "0.04"})
    assert found == asked == {hour(ROWS[name]["timestamp"])}


def test_a_spend_priced_at_the_day_is_priced_again_at_the_day(ledger):
    """Its fee's value kept from the day's price, the proceeds take the day's
    too (_keeps_a_day_price), and so does what's found first: its fee's mark
    kept (the review of #646)."""
    tx_id = ledger.add(spend("2024-03-02"), moment="day")
    found, asked = ledger.edit(tx_id, {"amount": "0.08"})
    assert found == asked == {("day", price_history.utc_day(datetime(2024, 3, 2, 12, tzinfo=timezone.utc)))}


def test_a_spends_0_value_made_a_gift_is_priced_and_found_first(ledger):
    """A Spent holding a $0 value (an API client's), made a gift by an edit
    that sends no value: the save prices the gift (_gift_priced_by_edit)."""
    tx_id = ledger.add(spend("2024-03-03", gross_proceeds_usd="5000", fmv_usd="0"))
    found, asked = ledger.edit(tx_id, {"purpose": "Gift"})
    assert hour("2024-03-03T12:00:00Z") in asked and found == asked


def test_a_spend_made_an_income_deposit_has_its_value_found_first(ledger):
    """The type change drops the stored FIFO basis (_drop_fields_of_old_type); the save prices the income."""
    tx_id = ledger.add(spend("2024-03-04", gross_proceeds_usd="5000"))
    found, asked = ledger.edit(tx_id, {"type": "Deposit", "from_account_id": EXTERNAL, "to_account_id": WALLET,
                                       "source": "Income", **NO_FEE})
    assert found == asked == {hour("2024-03-04T12:00:00Z")}


def test_a_dollar_deposit_moved_into_a_wallet_as_income_has_its_value_found_first(ledger):
    """Its dollar basis is dropped (_drop_dollar_deposit_basis); the save prices the income."""
    tx_id = ledger.add({"type": "Deposit", "timestamp": "2024-03-05T12:00:00Z", "from_account_id": EXTERNAL,
                        "to_account_id": BANK, "amount": "500", "source": "N/A", "cost_basis_usd": "500",
                        "fee_amount": "0", "fee_currency": "USD"})
    found, asked = ledger.edit(tx_id, {"to_account_id": WALLET, "amount": "0.01", "source": "Income", **NO_FEE})
    assert found == asked == {hour("2024-03-05T12:00:00Z")}
