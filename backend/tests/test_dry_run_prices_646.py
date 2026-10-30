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
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.main import app
from backend.models.app_setting import save_setting
from backend.models.btc_price import BtcPriceHourly
from backend.models.transaction import Transaction
from backend.services import hourly_prices, price_history, recalculated_by
from backend.services import transaction as tx_service
from backend.tests.conftest import STUB_HISTORICAL_USD, default_login

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
    "gift with a fee": {"type": "Withdrawal", "timestamp": "2024-06-02T12:00:00Z", "from_account_id": WALLET,
                        "to_account_id": EXTERNAL, "amount": "0.05", "purpose": "Gift", **BTC_FEE},
    # Valued at the date of death's price: a row priced at the day by nature
    "inherited": {"type": "Deposit", "timestamp": "2024-07-01T12:00:00Z", "from_account_id": EXTERNAL,
                  "to_account_id": WALLET, "amount": "0.05", "source": "Inherited",
                  "acquired_at": "2024-06-15", **NO_FEE},
    "transfer": {"type": "Transfer", "timestamp": "2024-07-02T12:00:00Z", "from_account_id": WALLET,
                 "to_account_id": 4, "amount": "0.1", **BTC_FEE},
}
# What the form sends back unchanged (frontend/src/utils/transactionForm.ts,
# buildTransactionPayload): every field it shows, the values as shown, a
# Spent's proceeds as proceeds_usd, never a priced fee's value
SHOWN = ("type", "timestamp", "from_account_id", "to_account_id", "amount", "fee_amount", "fee_currency",
         "acquired_at", "broker_reporting")


class Ledger:
    """A ledger of its own; each price asked for is noted: (found first?, "hour" or "day", when)."""

    def __init__(self, client, tax_year, session):
        self.client, self.tax_year, self.session = client, tax_year, session
        self.finding, self.moment, self.asked, self.waits = False, "hour", [], []

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
        return self._sent_in_2026("put", f"/api/transactions/{tx_id}", change)

    def add_in_2026(self, row: dict) -> tuple[set, set]:
        """The row added in 2026, without its confirm, as edit's are."""
        return self._sent_in_2026("post", "/api/transactions", row)

    def _sent_in_2026(self, method: str, url: str, body: dict) -> tuple[set, set]:
        self.tax_year(2026)
        self.asked.clear()
        r = getattr(self.client, method)(url, json=body)
        self.tax_year(2009)
        assert r.status_code in (200, 409), r.text
        return ({(at, when) for first, at, when in self.asked if first},
                {(at, when) for first, at, when in self.asked if not first})

    def echo(self, tx_id: int, **change) -> dict:
        """The form's save of the row, with `change` made in it."""
        stored = self.client.get(f"/api/transactions/{tx_id}").json()
        sent = {key: stored[key] for key in SHOWN}
        if stored["type"] == "Deposit":
            sent.update(source=stored["source"], cost_basis_usd=stored["cost_basis_usd"])
        elif stored["type"] == "Withdrawal":
            sent.update(purpose=stored["purpose"], cost_basis_usd=None, fmv_usd=stored["fmv_usd"])
            if stored["purpose"] == "Spent":
                sent["proceeds_usd"] = stored["gross_proceeds_usd"]
        return {**sent, **change}


@pytest.fixture
def ledger(fresh_app, monkeypatch, tax_year):
    """A 2024 deposit to spend from, and every price noted."""
    lg = Ledger(TestClient(app), tax_year, fresh_app)

    def price_at(db, when):
        lg.asked.append((lg.finding, "hour", hourly_prices.hour_of(when)))
        at = datetime.fromtimestamp(hourly_prices.hour_of(when), tz=timezone.utc)
        return hourly_prices.Priced(Decimal("50000.00"), lg.moment, at)

    def hourly_price(db, when, wait=True):
        """A stored row's hour, found first (hours_a_replay_prices)."""
        lg.asked.append((lg.finding, "hour", hourly_prices.hour_of(when)))
        lg.waits.append(wait)
        return Decimal("50000.00"), "test"

    def daily_price(db, when):
        lg.asked.append((lg.finding, "day", price_history.utc_day(when)))
        return Decimal("40000.00")

    found_first = tx_service.find_prices_first

    def finding(db, *rows_and_moments):
        lg.finding = True
        try:
            found_first(db, *rows_and_moments)
        finally:
            lg.finding = False

    monkeypatch.setattr(hourly_prices, "price_at", price_at)
    monkeypatch.setattr(hourly_prices, "hourly_price", hourly_price)
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


# The form's edits send the value they show (the review of #646): the save
# prices it again all the same when it isn't typed
@pytest.mark.parametrize("name, moment", [("priced spend", "hour"), ("priced spend", "day"),
                                          ("gift with a fee", "hour"), ("income", "hour")])
def test_the_forms_amount_edit_has_the_value_it_shows_found_first(ledger, name, moment):
    tx_id = ledger.add(ROWS[name], moment=moment)
    found, asked = ledger.edit(tx_id, ledger.echo(tx_id, amount="0.04"))
    assert asked and found == asked


def test_the_forms_date_of_death_moved_has_the_days_price_found_first(ledger):
    tx_id = ledger.add(ROWS["inherited"])
    found, asked = ledger.edit(tx_id, ledger.echo(tx_id, acquired_at="2024-06-20"))
    assert found == asked == {("day", price_history.utc_day(datetime(2024, 6, 20, 12, tzinfo=timezone.utc)))}


def test_proceeds_sent_as_0_are_priced_and_found_first(ledger):
    found, asked = ledger.edit(ledger.add(ROWS["priced spend"]), {"proceeds_usd": "0"})
    assert asked and found == asked


@pytest.mark.parametrize("change", [{"amount": "0.08"}, {"proceeds_usd": None}])
def test_a_fees_value_sent_back_is_typed_so_the_proceeds_take_the_hour(ledger, change):
    """A day-priced Spent whose fee's value comes back typed: the save prices
    its proceeds at the hour (nothing keeps the day), and so is it found."""
    tx_id = ledger.add(spend("2024-03-06"), moment="day")
    fee = ledger.client.get(f"/api/transactions/{tx_id}").json()["fee_usd"]
    found, asked = ledger.edit(tx_id, {**change, "fee_usd": fee})
    assert asked and found == asked


def test_a_fee_sent_alone_has_its_currency_filled_and_its_value_found_first(ledger):
    """A Spent saved without a fee, so without a fee currency: the save fills
    BTC for a fee sent alone (_check_edit), and prices it."""
    tx_id = ledger.add({k: v for k, v in spend("2024-03-07", gross_proceeds_usd="5000").items()
                        if k != "fee_currency"} | {"fee_amount": "0"})
    found, asked = ledger.edit(tx_id, {"fee_amount": "0.0001"})
    assert found == asked == {hour("2024-03-07T12:00:00Z")}


@pytest.mark.parametrize("name, change", [
    ("income", {"source": "Income"}), ("income", {"source": "Reward"}),
    ("inherited", {"acquired_at": "2024-06-15"}), ("transfer", {"amount": "0.08"}),
    ("typed spend", {"fee_amount": "0"}),
])
def test_an_edit_the_save_prices_nothing_for_finds_nothing(ledger, name, change):
    """A source sent unchanged, Income to Reward (both valued alike), a date
    of death sent back, a transfer's amount (its fee hangs on the fee), a fee
    removed."""
    assert ledger.edit(ledger.add(ROWS[name]), change) == (set(), set())


# A row priced at the day (#647): the edit's save prices at the day only
# while its values must share the day's price (_keeps_a_day_price), else at
# the hour; a Spent's blank proceeds the replay prices at the row's moment
def _stored(ledger, tx_id: int, key: str):
    return ledger.client.get(f"/api/transactions/{tx_id}").json()[key]


@pytest.mark.parametrize("name, change", [
    ("income", {"amount": "0.04"}),  # an income's value: the hour
    ("transfer", {"fee_amount": "0.0002"}),  # a transfer's fee: the hour
    ("priced spend", {"timestamp": "2024-04-01T15:00:00Z"}),  # proceeds and fee both priced again: the hour
    ("gift", {"amount": "0.04"}),  # a gift without a fee: the hour
    ("typed spend", {"proceeds_usd": None}),  # proceeds the replay prices, the fee's kept: the day
])
def test_a_day_rows_value_is_found_at_the_moment_the_save_prices_it(ledger, name, change):
    found, asked = ledger.edit(ledger.add(ROWS[name], moment="day"), change)
    assert asked and found == asked


def test_a_day_gifts_value_with_its_fee_typed_takes_the_hour(ledger):
    """The fee's value sent back is typed, so nothing keeps the day: the gift's priced at the hour."""
    tx_id = ledger.add(ROWS["gift with a fee"], moment="day")
    found, asked = ledger.edit(tx_id, ledger.echo(tx_id, amount="0.04", fee_usd=_stored(ledger, tx_id, "fee_usd")))
    assert asked and found == asked


def test_an_inheritance_made_income_is_found_at_the_hour(ledger):
    """An inheritance is valued at its date of death's day; as income, at its hour."""
    found, asked = ledger.edit(ledger.add(ROWS["inherited"]), {"source": "Income"})
    assert asked == {hour(ROWS["inherited"]["timestamp"])} and found == asked


def test_a_fee_added_without_its_currency_to_a_day_spend_is_found_at_the_day(ledger):
    """The fee's currency is filled before the save asks whether the spend's
    values share the day's price, so the fee takes the day's, as its
    proceeds keep it (#649); found first the same way."""
    tx_id = ledger.add({k: v for k, v in spend("2024-03-08").items() if k != "fee_currency"} | {"fee_amount": "0"},
                       moment="day")
    found, asked = ledger.edit(tx_id, {"fee_amount": "0.0001"})
    assert found == asked == {("day", price_history.utc_day(datetime(2024, 3, 8, 12, tzinfo=timezone.utc)))}


def test_an_old_0_income_value_an_edit_leaves_alone_finds_no_price(ledger):
    """#653: an income deposit holding a $0 value never priced (only a row
    saved before income deposits were always valued holds one), edited
    without any input of its value: the save leaves the value as it is
    (_revalue_income_deposit), and nothing is found first for it."""
    tx_id = ledger.add(ROWS["income"])
    _store(ledger, tx_id, cost_basis_usd=0, cost_basis_from_price=False)
    assert ledger.edit(tx_id, {"fee_amount": "0"}) == (set(), set())


@pytest.mark.parametrize("stored", [{"source": "income"},
                                    {"timestamp": datetime(2024, 5, 1, 12, 0, 0, 500000, tzinfo=timezone.utc)}])
def test_an_old_0_income_value_the_save_puts_right_is_found_first(ledger, stored):
    """The review of #653: a source in an old spelling, or a fraction of a
    second, which the save puts right, is an input of the value to it: the
    save prices it, and so it's found first."""
    tx_id = ledger.add(ROWS["income"])
    _store(ledger, tx_id, cost_basis_usd=0, cost_basis_from_price=False, **stored)
    found, asked = ledger.edit(tx_id, {"fee_amount": "0"})
    assert asked and found == asked


def _store(ledger, tx_id: int, **values) -> None:
    """Stored as an older BitcoinTX left the row."""
    with ledger.session() as db:
        db.query(Transaction).filter_by(id=tx_id).update(values)
        db.commit()


def test_a_past_year_spend_added_with_only_its_gross_finds_no_price(ledger):
    """#653: a Spent an API client adds with gross_proceeds_usd and no
    proceeds_usd: the save keeps the gross given (_withdrawal_gross_proceeds),
    and nothing is found first for it."""
    found, asked = ledger.add_in_2026(spend("2024-03-09", gross_proceeds_usd="5000", **NO_FEE))
    assert found == asked == set()


# #824: a replay prices a stored row's missing value at its stored moment
# (_price_for), and the past-year question's replays run on a scratch copy, so
# what they found was lost and the confirmed save tried twice. Its hour is
# found first. The sources' own limits, which these stubs skip:
# test_prices_found_lock_free.py
BLANK_FEE = {"fee_usd": None, "fee_usd_manual": False}
TYPED = spend("2024-08-01", gross_proceeds_usd="5000")  # the row a question is asked about


def _edit_another_row(ledger) -> tuple[set, set]:
    return ledger.edit(ledger.add(TYPED), {"amount": "0.08"})


def _nothing_pending(ledger) -> None:
    """This BitcoinTX last recalculated the ledger: one replay, with the write."""
    with ledger.session() as db:
        save_setting(db, recalculated_by.KEY, recalculated_by.stamp(db))
        db.commit()


@pytest.mark.parametrize("name, blanked", [
    ("transfer", BLANK_FEE),
    ("typed spend", BLANK_FEE),
    ("gift with a fee", BLANK_FEE),  # a fee is its own disposal, whatever the purpose
    ("priced spend", {"proceeds_usd": None, "gross_proceeds_usd": None, "proceeds_from_price": False}),
    ("priced spend", {**BLANK_FEE, "proceeds_usd": None, "gross_proceeds_usd": None}),  # one price
    ("transfer", {**BLANK_FEE, "fee_currency": None}),  # the replay fills its currency (_fill_stored_fee_currency)
])
def test_a_stored_rows_missing_value_is_found_first(ledger, name, blanked):
    _store(ledger, ledger.add(ROWS[name]), **blanked)
    found, asked = _edit_another_row(ledger)
    assert found == asked == {hour(ROWS[name]["timestamp"])}


def test_a_stored_rows_missing_value_kept_at_the_day_is_left_to_the_replay(ledger):
    """The latest days are asked for once a day: found first, a row the
    replay's own look refuses would be saved. It stays as it was."""
    _store(ledger, ledger.add(ROWS["priced spend"], moment="day"), **BLANK_FEE, price_moment="day")
    found, asked = _edit_another_row(ledger)
    assert found == set() and asked == {("day", price_history.utc_day(datetime(2024, 4, 1, 12, tzinfo=timezone.utc)))}


@pytest.mark.parametrize("name, blanked", [
    ("typed spend", {}),  # nothing missing
    ("gift", {"proceeds_usd": None, "gross_proceeds_usd": None}),  # a gift has no proceeds
    ("income", {"fee_usd": None}),  # no fee, and a deposit prices nothing in a replay
])
def test_what_a_replay_doesnt_price_isnt_found(ledger, name, blanked):
    _store(ledger, ledger.add(ROWS[name]), **blanked)
    assert _edit_another_row(ledger) == (set(), set())


def test_a_dollar_withdrawals_blank_value_isnt_found(ledger):
    """No lots, so no disposal and no fee's value: even with a BTC fee an older save left there."""
    tx_id = ledger.add({"type": "Withdrawal", "timestamp": "2024-02-01T12:00:00Z", "from_account_id": BANK,
                        "to_account_id": EXTERNAL, "amount": "100", "fee_amount": "0", "fee_currency": "USD"})
    _store(ledger, tx_id, fee_amount=1, fee_currency="BTC", fee_usd=None, purpose="Spent")
    assert _edit_another_row(ledger) == (set(), set())


def test_a_write_that_replays_nothing_finds_no_stored_rows_price(ledger):
    """An add dated last only adds its own lines: the blank value stays, unpriced, as it did."""
    _store(ledger, ledger.add(ROWS["transfer"]), **BLANK_FEE)
    assert ledger.add_in_2026(spend("2024-12-01", gross_proceeds_usd="5000", **NO_FEE)) == (set(), set())


def test_a_delete_finds_the_price_of_another_row_and_never_of_its_own(ledger):
    blank, other = ledger.add(ROWS["gift with a fee"]), ledger.add(ROWS["transfer"])
    _store(ledger, blank, **BLANK_FEE)
    _store(ledger, other, **BLANK_FEE)
    _nothing_pending(ledger)
    ledger.tax_year(2026)
    ledger.asked.clear()
    r = ledger.client.delete(f"/api/transactions/{blank}")
    ledger.tax_year(2009)
    assert r.status_code == 409, r.text
    assert {(at, when) for first, at, when in ledger.asked if first} == {hour(ROWS["transfer"]["timestamp"])}


def test_an_edit_moving_a_blank_row_finds_its_new_hour_not_its_old(ledger):
    """The row's own value is the edit's to price, as #646 finds it."""
    tx_id = ledger.add(ROWS["transfer"])
    _store(ledger, tx_id, **BLANK_FEE)
    _nothing_pending(ledger)
    found, asked = ledger.edit(tx_id, {"timestamp": "2024-07-02T15:00:00Z"})
    assert found == asked == {hour("2024-07-02T15:00:00Z")}


def test_with_a_change_pending_its_own_stored_moment_is_found_too(ledger):
    """The recalculation without the write replays the row as it's stored."""
    tx_id = ledger.add(ROWS["transfer"])
    _store(ledger, tx_id, **BLANK_FEE)
    found, asked = ledger.edit(tx_id, {"timestamp": "2024-07-02T15:00:00Z"})
    assert found == asked == {hour("2024-07-02T15:00:00Z"), hour(ROWS["transfer"]["timestamp"])}


def test_the_coins_moved_list_finds_no_stored_rows_price_first(ledger):
    """Keeping it would change what a later save of the row takes: left as it was (#824's review)."""
    _store(ledger, ledger.add(ROWS["gift with a fee"]), **BLANK_FEE)
    found, asked = ledger._sent_in_2026("post", "/api/transactions/coins-moved",
                                        {**ROWS["transfer"], "timestamp": "2024-02-01T12:00:00Z", "fee_usd": "5"})
    assert found == set() and asked == {hour(ROWS["gift with a fee"]["timestamp"])}


def test_a_stored_rows_price_never_waits_for_a_download(ledger):
    """Waiting could give it the hour's price where the save gives the day's."""
    _store(ledger, ledger.add(ROWS["transfer"]), **BLANK_FEE)
    _edit_another_row(ledger)
    assert ledger.waits == [False]


def test_the_time_for_stored_rows_prices_is_limited(ledger, monkeypatch):
    """A price source that doesn't answer costs each lookup its timeout: the
    question still comes, its replay asking as it did, under its own limit."""
    monkeypatch.setattr(tx_service, "STORED_VALUES_SECONDS", 0)
    _store(ledger, ledger.add(ROWS["transfer"]), **BLANK_FEE)
    found, asked = _edit_another_row(ledger)
    assert found == set() and asked == {hour(ROWS["transfer"]["timestamp"])}


@pytest.fixture
def real_lookups(fresh_app, monkeypatch, tax_year):
    """The real lookups, with a source that answers for the hour asked and
    notes each time a save's lock held its request back: its second try."""
    state = {"held": 0, "asked": [], "price": Decimal("50000.00"), "downloading": False, "waited": [], "fail": 0}

    async def find_hours(hour, files_end, stored):
        if state["fail"]:
            state["fail"] -= 1
            raise OSError("the source didn't answer")
        try:
            price_history.refuse_if_held()
        except price_history.RequestHeld:
            state["held"] += 1
            raise
        state["asked"].append(hour)
        return {} if state["price"] is None else {hour: (state["price"], "test")}

    monkeypatch.setattr(hourly_prices, "find_hours", find_hours)
    monkeypatch.setattr(hourly_prices, "start_download", lambda: state["downloading"])
    monkeypatch.setattr(hourly_prices, "_wait_for_year", lambda line: state["waited"].append(line.year))
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    assert client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2024-01-10T12:00:00Z", "from_account_id": EXTERNAL,
        "to_account_id": WALLET, "amount": "5", "source": "MyBTC", "cost_basis_usd": "30000", **NO_FEE,
    }).status_code == 200
    return client, tax_year, state


def _blank_fee_and_a_question(client, tax_year, session, state, downloading: bool = False) -> tuple[int, int, dict]:
    """A transfer with no fee value, and a past-year edit of another row, sent in 2026 and answered 409."""
    blank = client.post("/api/transactions", json=ROWS["transfer"]).json()["id"]
    other = client.post("/api/transactions", json=TYPED).json()["id"]
    with session() as db:
        db.query(Transaction).filter_by(id=blank).update(BLANK_FEE)
        db.query(BtcPriceHourly).delete()  # its save found its hour: as if it never had
        db.commit()
    state["asked"].clear()
    state["downloading"] = downloading
    tax_year(2026)
    r = client.put(f"/api/transactions/{other}", json={"amount": "0.08"})
    assert r.status_code == 409, r.text
    return blank, other, r.json()


def test_the_confirmed_save_doesnt_try_twice_and_the_value_is_the_same(fresh_app, real_lookups):
    """The whole of #824: the price is kept before the dry run, so the
    confirm's replay finds it stored: no second try. The value and its moment
    are what they were: the fee at the hour's price."""
    client, tax_year, state = real_lookups
    blank, other, question = _blank_fee_and_a_question(client, tax_year, fresh_app, state)
    assert state["asked"] == [hourly_prices.hour_of(datetime(2024, 7, 2, 12, tzinfo=timezone.utc))]
    r = client.put(f"/api/transactions/{other}?confirm={question['confirm']}", json={"amount": "0.08"})
    tax_year(2009)
    assert r.status_code == 200, r.text
    assert state["held"] == 0
    stored = client.get(f"/api/transactions/{blank}").json()
    assert Decimal(stored["fee_usd"]) == Decimal("5.00") and stored["price_moment"] == "hour"


def test_an_hour_no_source_has_takes_the_days_price_as_it_did(fresh_app, real_lookups):
    """No price at the hour: the day's, marked as such, in the question and in the save."""
    client, tax_year, state = real_lookups
    state["price"] = None
    blank, other, question = _blank_fee_and_a_question(client, tax_year, fresh_app, state)
    r = client.put(f"/api/transactions/{other}?confirm={question['confirm']}", json={"amount": "0.08"})
    tax_year(2009)
    assert r.status_code == 200, r.text
    stored = client.get(f"/api/transactions/{blank}").json()
    assert Decimal(stored["fee_usd"]) == (Decimal(str(STUB_HISTORICAL_USD)) * Decimal("0.0001")).quantize(Decimal("0.01"))
    assert stored["price_moment"] == "day"


def _confirm(client, tax_year, other: int, question: dict) -> None:
    r = client.put(f"/api/transactions/{other}?confirm={question['confirm']}", json={"amount": "0.08"})
    tax_year(2009)
    assert r.status_code == 200, r.text


def test_a_year_whose_file_is_missing_takes_the_days_price_as_it_did(fresh_app, real_lookups):
    """The year's file isn't here, no source has the hour, and a download is
    under way. The question and the save wait for it no more than they did,
    in a replay or in its second try: waiting could have brought the hour's
    price where the save gives the day's."""
    client, tax_year, state = real_lookups
    state["price"] = None
    blank, other, question = _blank_fee_and_a_question(client, tax_year, fresh_app, state, downloading=True)
    _confirm(client, tax_year, other, question)
    assert state["waited"] == []
    stored = client.get(f"/api/transactions/{blank}").json()
    assert Decimal(stored["fee_usd"]) == (Decimal(str(STUB_HISTORICAL_USD)) * Decimal("0.0001")).quantize(Decimal("0.01"))
    assert stored["price_moment"] == "day"


def test_out_of_time_it_falls_back_to_the_second_try_with_the_same_value(fresh_app, real_lookups, monkeypatch):
    """Nothing is looked for first: the confirmed save's replay asks, is held
    back, and runs again. The value and its moment are those of a price
    found first (test_the_confirmed_save_doesnt_try_twice_...)."""
    client, tax_year, state = real_lookups
    monkeypatch.setattr(tx_service, "STORED_VALUES_SECONDS", 0)
    blank, other, question = _blank_fee_and_a_question(client, tax_year, fresh_app, state)
    _confirm(client, tax_year, other, question)
    assert state["held"] == 1
    stored = client.get(f"/api/transactions/{blank}").json()
    assert Decimal(stored["fee_usd"]) == Decimal("5.00") and stored["price_moment"] == "hour"


def test_time_running_out_part_way_leaves_the_rest_to_the_second_try(fresh_app, real_lookups, monkeypatch):
    """The earlier of two blank rows is found first, taking all the time
    there is: the later one's price comes by the second try, and both values
    are right."""
    client, tax_year, state = real_lookups
    earlier = client.post("/api/transactions", json=ROWS["gift with a fee"]).json()["id"]
    with fresh_app() as db:
        db.query(Transaction).filter_by(id=earlier).update(BLANK_FEE)
        db.commit()
    now = {"seconds": 0}
    hourly_price = hourly_prices.hourly_price

    def a_slow_source(db, when, wait=True):
        found = hourly_price(db, when, wait)
        if not wait:  # only looking first: a replay's lookups wait where they may
            now["seconds"] += tx_service.STORED_VALUES_SECONDS
        return found

    monkeypatch.setattr(tx_service, "time", SimpleNamespace(monotonic=lambda: now["seconds"]))
    monkeypatch.setattr(hourly_prices, "hourly_price", a_slow_source)
    blank, other, question = _blank_fee_and_a_question(client, tax_year, fresh_app, state)
    _confirm(client, tax_year, other, question)
    assert state["held"] == 1
    assert Decimal(client.get(f"/api/transactions/{earlier}").json()["fee_usd"]) == Decimal("5.00")
    assert Decimal(client.get(f"/api/transactions/{blank}").json()["fee_usd"]) == Decimal("5.00")


def test_blank_rows_stored_with_and_without_a_timezone_are_found_first(fresh_app, real_lookups):
    """The review's: SQLite can hand back a time with no offset (tax_time.as_utc),
    and sorting one beside one that has an offset answered 500."""
    client, tax_year, state = real_lookups
    earlier = client.post("/api/transactions", json=ROWS["gift with a fee"]).json()["id"]
    blank = client.post("/api/transactions", json=ROWS["transfer"]).json()["id"]
    other = client.post("/api/transactions", json=TYPED).json()["id"]
    with fresh_app() as db:
        db.query(Transaction).filter(Transaction.id.in_((earlier, blank))).update(BLANK_FEE)
        db.execute(text("UPDATE transactions SET timestamp = '2024-07-02 12:00:00' WHERE id = :id"), {"id": blank})
        db.commit()
    tax_year(2026)
    r = client.put(f"/api/transactions/{other}", json={"amount": "0.08"})
    tax_year(2009)
    assert r.status_code == 409, r.text


def test_a_source_that_fails_once_leaves_the_save_to_look_again(fresh_app, real_lookups):
    """The review's: what the look first found none of is noted nowhere, so
    in a write that saves without asking the save's own look gets the hour's
    price, as it did."""
    client, tax_year, state = real_lookups
    blank = client.post("/api/transactions", json=ROWS["transfer"]).json()["id"]
    other = client.post("/api/transactions", json=TYPED).json()["id"]
    with fresh_app() as db:
        db.query(Transaction).filter_by(id=blank).update(BLANK_FEE)
        db.query(BtcPriceHourly).delete()
        db.commit()
    state["fail"] = 1
    tax_year(2026)
    r = client.put(f"/api/transactions/{other}", json={"amount": TYPED["amount"]})  # nothing of its own to ask about
    tax_year(2009)
    assert r.status_code == 200, r.text
    stored = client.get(f"/api/transactions/{blank}").json()
    assert Decimal(stored["fee_usd"]) == Decimal("5.00") and stored["price_moment"] == "hour"
