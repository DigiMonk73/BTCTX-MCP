"""
IRS holding period (Pub. 544): long-term only if held MORE than one year,
counting from the day after acquisition. Selling on the anniversary date is
still short-term; the day after is long-term. Time of day doesn't matter.
"""

from datetime import datetime, timezone

import pytest

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
])
def test_holding_period(acquired, disposed, expected):
    assert holding_period(acquired, disposed) == expected


def test_naive_timestamps_are_utc():
    assert holding_period(datetime(2023, 2, 5), datetime(2024, 2, 6)) == "LONG"
