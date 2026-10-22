"""
The independent calculation takes every date a tax rule reads in the tax
timezone, as the app does (AGENTS.md, "Tax timezone"): the tax year, the
holding period, Form 8949's dates, income's year, the year-end lots and a
date originally acquired, besides a covered lot's day (B1-5). Moments
stay in UTC, as the ledger stores and the report prints them.
"""

import json

import pytest

from backend.tests.conftest import independent_figures, ledger_tx


independent = independent_figures()

# Times picked so that Chicago's date is the day before UTC's.
CHICAGO_LEDGER = [
    # Exchange BTC: 1 BTC for $1,000, at 03:00 UTC on June 1: May 31, 2024 in Chicago.
    ledger_tx("Buy", "2024-06-01T03:00:00Z", 3, 4, "1.00000000", cost_basis_usd="1000.00"),
    # A reward of 0.1 BTC worth $500 at 03:00 UTC on New Year's Day: still 2024 in Chicago.
    ledger_tx("Deposit", "2025-01-01T03:00:00Z", 99, 2, "0.10000000", source="Reward", cost_basis_usd="500.00"),
    # Half the lot sold at noon UTC on June 1, 2025 (June 1 in Chicago too), for $2,000:
    # in Chicago held from May 31, 2024, past the anniversary, so long-term; exchange 1's
    # switch is on and the lot was bought before 2026: box K. Gain $2,000 - $500.
    ledger_tx("Sell", "2025-06-01T12:00:00Z", 4, 3, "0.50000000", gross_proceeds_usd="2000.00"),
]


def _figures(year, transactions=CHICAGO_LEDGER, zone="America/Chicago"):
    return independent.year_figures(independent.replay(transactions, tax_timezone=zone), year)


def _rows(figures):
    return [(r["box"], r["date_acquired"], r["date_sold"], r["gain_loss"], r["holding_period"])
            for r in figures["form_8949"]]


def test_the_holding_period_and_8949_dates_are_the_tax_timezones():
    assert _rows(_figures(2025)) == [("K", "05/31/2024", "06/01/2025", "1500.00", "LONG")]
    # In UTC the same sale falls on the lot's anniversary: short-term.
    assert _rows(_figures(2025, zone="UTC")) == [("H", "06/01/2024", "06/01/2025", "1500.00", "SHORT")]


def test_income_and_the_year_end_lots_fall_in_the_tax_timezones_year():
    figures = _figures(2024)
    assert figures["income"]["Reward"] == "500.00"
    assert {(h["account"], h["acquired"], h["quantity"]) for h in figures["end_of_year_holdings"]} == {
        ("Exchange BTC", "2024-06-01T03:00:00+00:00", "1.00000000"),
        ("Wallet", "2025-01-01T03:00:00+00:00", "0.10000000"),
    }
    assert _figures(2025)["income"]["Reward"] == "0.00"


def test_a_sale_on_new_years_night_is_last_years():
    sale = [ledger_tx("Buy", "2024-01-10T15:00:00Z", 3, 4, "1.00000000", cost_basis_usd="1000.00"),
            ledger_tx("Sell", "2025-01-01T03:00:00Z", 4, 3, "0.50000000", gross_proceeds_usd="600.00")]
    assert _rows(_figures(2024, sale)) == [("C", "01/10/2024", "12/31/2024", "100.00", "SHORT")]
    assert _figures(2025, sale)["form_8949"] == []


def test_a_date_originally_acquired_is_noon_in_the_tax_timezone():
    gift = [ledger_tx("Deposit", "2024-02-01T00:00:00Z", 99, 2, "0.10000000", source="Gift",
                      cost_basis_usd="100.00", acquired_at="2023-05-20")]
    (lot,) = _figures(2024, gift, "Asia/Tokyo")["end_of_year_holdings"]
    assert lot["acquired"] == "2023-05-20T03:00:00+00:00"  # noon in Tokyo, UTC+9


def test_a_time_zone_it_doesnt_know_stops_it():
    with pytest.raises(ValueError) as found:
        independent.replay([], tax_timezone="Mars/Olympus_Mons")
    assert str(found.value) == "The tax timezone 'Mars/Olympus_Mons' isn't a time zone this computer knows."


def test_a_time_without_a_time_zone_stops_it():
    with pytest.raises(ValueError) as found:
        independent.replay([ledger_tx("Deposit", "2024-02-01T00:00:00", 99, 1, "100.00")])
    assert str(found.value) == "The time '2024-02-01T00:00:00' has no time zone: write it in UTC, ending in Z."


def test_a_ledger_file_is_replayed_in_its_own_accounts_and_tax_timezone():
    data = {"tax_timezone": "America/Chicago", "transactions": CHICAGO_LEDGER, "accounts": [
        {"id": 3, "name": "Exchange USD", "kind": "exchange", "currency": "USD", "exchange_id": 1},
        {"id": 4, "name": "My exchange's BTC", "kind": "exchange", "currency": "BTC", "exchange_id": 1},
        {"id": 2, "name": "Wallet", "kind": "wallet", "currency": "BTC"},
    ]}
    ledger = independent.replay_ledger(data)
    assert ledger.tax_zone.key == "America/Chicago" and sorted(ledger.lots) == [2, 4]
    figures = independent.year_figures(ledger, 2024)
    assert "My exchange's BTC" in {h["account"] for h in figures["end_of_year_holdings"]}


def test_compare_names_a_tax_timezone_the_app_didnt_use():
    data = dict(json.loads(independent.LEDGER.read_text()), tax_timezone="America/Chicago")
    saved = json.loads(independent.FIGURES.read_text())["years"]["2025"]
    found = independent.differences(independent.year_figures(independent.replay_ledger(data), 2025), saved)
    assert found[0] == "tax timezone: here America/Chicago, in the app UTC"
