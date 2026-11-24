"""
IRS holding period (Pub. 544, Pub. 550): long-term only if held MORE than
one year, counting from the day after acquisition. Selling on the
anniversary date is still short-term; the day after is long-term. Time of
day doesn't matter. Coins acquired on the last day of a month are held a
year at the end of the same month a year later (the holding period runs
in calendar months from the first of the next month: Rev. Rul. 66-7;
Caspe v. United States, 694 F.2d 1116), so 28 February 2023 turns
long-term on 1 March 2024, not 29 February (#950).
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from backend.services.reports.form_8949 import build_form_8949_and_schedule_d
from backend.services.transaction import holding_period


def utc(y, m, d, h=12):
    return datetime(y, m, d, h, tzinfo=timezone.utc)


@pytest.mark.parametrize("acquired, disposed, expected", [
    (utc(2023, 2, 5), utc(2024, 2, 4), "SHORT"),
    (utc(2023, 2, 5), utc(2024, 2, 5), "SHORT"),        # anniversary
    (utc(2023, 2, 5), utc(2024, 2, 6), "LONG"),         # day after
    (utc(2024, 1, 1), utc(2024, 12, 31), "SHORT"),      # 365 days, leap year
    (utc(2024, 1, 1), utc(2025, 1, 1), "SHORT"),        # 366 days, but = anniversary
    (utc(2024, 1, 1), utc(2025, 1, 2), "LONG"),
    (utc(2024, 2, 29), utc(2025, 2, 28), "SHORT"),      # leap-day purchase
    (utc(2024, 2, 29), utc(2025, 3, 1), "LONG"),
    (utc(2023, 2, 5, 23), utc(2024, 2, 5, 1), "SHORT"),  # time of day ignored
    (utc(2023, 2, 5, 1), utc(2024, 2, 6, 0), "LONG"),
    # The last day of a month (#950): a year ends on the last day of the same month
    (utc(2023, 2, 28), utc(2024, 2, 28), "SHORT"),
    (utc(2023, 2, 28), utc(2024, 2, 29), "SHORT"),
    (utc(2023, 2, 28), utc(2024, 3, 1), "LONG"),
    (utc(2011, 2, 28), utc(2012, 2, 29), "SHORT"),
    (utc(2027, 2, 28), utc(2028, 2, 29), "SHORT"),
    (utc(2023, 1, 31), utc(2024, 1, 31), "SHORT"),
    (utc(2023, 1, 31), utc(2024, 2, 1), "LONG"),
    (utc(2023, 4, 30), utc(2024, 4, 30), "SHORT"),
    (utc(2023, 4, 30), utc(2024, 5, 1), "LONG"),
    (utc(2023, 12, 31), utc(2024, 12, 31), "SHORT"),
    (utc(2023, 12, 31), utc(2025, 1, 1), "LONG"),
    # 28 February of a leap year isn't the month's last day: today's rule
    (utc(2024, 2, 28), utc(2025, 2, 28), "SHORT"),
    (utc(2024, 2, 28), utc(2025, 3, 1), "LONG"),
    # The day before a month's last isn't its last either
    (utc(2023, 2, 27), utc(2024, 2, 27), "SHORT"),
    (utc(2023, 2, 27), utc(2024, 2, 28), "LONG"),
])
def test_holding_period(acquired, disposed, expected):
    assert holding_period(acquired, disposed) == expected


def test_naive_timestamps_are_utc():
    assert holding_period(datetime(2023, 2, 5), datetime(2024, 2, 6)) == "LONG"


def test_the_month_end_is_the_tax_timezones():
    """01:00 UTC on 1 March 2023 is 28 February in Chicago, the month's last day there."""
    chicago = ZoneInfo("America/Chicago")
    acquired = datetime(2023, 3, 1, 1, tzinfo=timezone.utc)
    sold = datetime(2024, 2, 29, 18, tzinfo=timezone.utc)
    assert holding_period(acquired, sold, chicago) == "SHORT"
    assert holding_period(acquired, datetime(2024, 3, 1, 18, tzinfo=timezone.utc), chicago) == "LONG"
    # In UTC it was acquired on 1 March: long-term only from 2 March 2024
    assert holding_period(acquired, datetime(2024, 3, 1, 18, tzinfo=timezone.utc)) == "SHORT"


def test_the_month_end_east_of_utc():
    """20:00 UTC on 27 February 2023 is 28 February in Tokyo; 16:00 UTC on
    29 February 2024 is already 1 March there, the day it turns long-term."""
    tokyo = ZoneInfo("Asia/Tokyo")
    acquired = datetime(2023, 2, 27, 20, tzinfo=timezone.utc)
    assert holding_period(acquired, datetime(2024, 2, 29, 14, tzinfo=timezone.utc), tokyo) == "SHORT"
    assert holding_period(acquired, datetime(2024, 2, 29, 16, tzinfo=timezone.utc), tokyo) == "LONG"
    # In UTC it was acquired on 27 February, not a month's last day: long-term from 28 February 2024
    assert holding_period(acquired, datetime(2024, 2, 28, 12, tzinfo=timezone.utc)) == "LONG"


BANK, EXCH_USD, EXCH_BTC, WALLET, EXTERNAL = 1, 3, 4, 2, 99


@pytest.fixture
def month_end_ledger(auth_client):
    """A buy and a My BTC deposit dated 28 February 2023, each sold on 29 February 2024 (#950)."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    rows = [
        dict(type="Deposit", timestamp="2023-02-01T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
             amount="50000", fee_amount="0", fee_currency="USD", source="N/A"),
        dict(type="Buy", timestamp="2023-02-28T12:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
             amount="1", cost_basis_usd="23000", fee_amount="0", fee_currency="USD"),
        dict(type="Deposit", timestamp="2023-06-01T12:00:00Z", from_account_id=EXTERNAL, to_account_id=WALLET,
             amount="0.5", cost_basis_usd="11000", acquired_at="2023-02-28", fee_amount="0",
             fee_currency="BTC", source="MyBTC"),
        dict(type="Sell", timestamp="2024-02-29T12:00:00Z", from_account_id=EXCH_BTC, to_account_id=EXCH_USD,
             amount="1", gross_proceeds_usd="62000", fee_amount="0", fee_currency="USD"),
        dict(type="Withdrawal", timestamp="2024-02-29T13:00:00Z", from_account_id=WALLET, to_account_id=EXTERNAL,
             amount="0.5", proceeds_usd="31000", fee_amount="0", fee_currency="BTC", purpose="Spent"),
    ]
    ids = []
    for tx in rows:
        r = auth_client.post("/api/transactions", json=tx)
        assert r.status_code == 200, (tx, r.text)
        ids.append(r.json()["id"])
    yield ids
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def test_a_month_end_purchase_sold_on_29_february_is_short_term_on_form_8949(
        auth_client, test_engine, month_end_ledger):
    for tx_id in month_end_ledger[3:]:
        assert auth_client.get(f"/api/transactions/{tx_id}").json()["holding_period"] == "SHORT"
    with Session(test_engine) as db:
        forms = build_form_8949_and_schedule_d(2024, db)
    assert forms["long_term"] == []
    assert sorted((r["date_acquired"], r["date_sold"], r["box"]) for r in forms["short_term"]) == [
        ("02/28/2023", "02/29/2024", "C"), ("02/28/2023", "02/29/2024", "C")]
