"""
CSV import rules found in the v0.9.2 hardening sweep (F10, F25, F30, F12):
dates follow the tax timezone, malformed numbers are errors, a USD transfer's
fee is in USD, a BTC withdrawal needs a purpose.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from backend.services.csv_import import parse_csv_file

HEADER = "date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency,source,purpose,notes"
CHICAGO = ZoneInfo("America/Chicago")


def parse(*rows, tz=CHICAGO):
    return parse_csv_file(("\n".join([HEADER, *rows]) + "\n").encode(), tz)


def ts(result, i=0):
    return result.transactions[i]["timestamp"]


def messages(result):
    return [e.message for e in result.errors]


def test_a_date_alone_is_that_day_in_the_tax_timezone():
    """F10: '2024-01-01' used to be UTC midnight, Dec 31 2023 in Chicago."""
    r = parse("2024-01-01,Deposit,100,External,Bank,,,,,,,")
    assert not r.errors, messages(r)
    assert ts(r).astimezone(CHICAGO).date().isoformat() == "2024-01-01"
    assert ts(r) == datetime(2024, 1, 1, 18, 0, tzinfo=timezone.utc)  # noon CST


def test_a_time_without_a_timezone_is_local_and_z_is_utc():
    r = parse(
        "2024-07-04 21:30:00,Deposit,100,External,Bank,,,,,,,",
        "2024-07-04T21:30:00Z,Deposit,100,External,Bank,,,,,,,",
        "01/02/2024,Deposit,100,External,Bank,,,,,,,",
    )
    assert not r.errors, messages(r)
    assert ts(r, 0) == datetime(2024, 7, 5, 2, 30, tzinfo=timezone.utc)  # 21:30 CDT
    assert ts(r, 1) == datetime(2024, 7, 4, 21, 30, tzinfo=timezone.utc)
    assert ts(r, 2).astimezone(CHICAGO).date().isoformat() == "2024-01-02"


def test_a_malformed_optional_number_is_an_error_not_a_blank():
    """F30: a basis of '1.123' was dropped silently (then valued at $0)."""
    r = parse("2024-01-05,Deposit,0.1,External,Wallet,1.123,,,,MyBTC,,")
    assert any("Invalid cost_basis_usd '1.123'" in m for m in messages(r))
    r = parse("2024-01-05,Transfer,0.1,Wallet,Exchange BTC,,,0.000000001,BTC,,,")
    assert any("Invalid fee_amount" in m for m in messages(r))
    r = parse("2024-01-05,Deposit,1E-9,External,Wallet,10,,,,MyBTC,,")
    assert r.errors and not r.transactions


def test_a_usd_transfer_pays_its_fee_in_usd():
    """F25: the importer insisted on BTC, which the ledger refuses for USD."""
    r = parse("2024-01-05,Transfer,500,Bank,Exchange USD,,,1.50,USD,,,")
    assert not r.errors, messages(r)
    assert r.transactions[0]["fee_currency"] == "USD"
    r = parse("2024-01-05,Transfer,500,Bank,Exchange USD,,,1.50,,,,")
    assert r.transactions[0]["fee_currency"] == "USD"  # default follows the account
    r = parse("2024-01-05,Transfer,500,Bank,Exchange USD,,,1.50,BTC,,,")
    assert any("pays its fee in USD" in m for m in messages(r))


def test_a_btc_withdrawal_needs_a_purpose():
    """F12: without one it got $0 proceeds, a loss of its basis on Form 8949."""
    r = parse("2024-01-05,Withdrawal,0.1,Wallet,External,,,,,,,")
    assert any("needs a purpose" in m for m in messages(r))
    r = parse("2024-01-05,Withdrawal,0.1,Wallet,External,,,,,,gift,")
    assert not r.errors, messages(r)
    r = parse("2024-01-05,Withdrawal,100,Bank,External,,,,,,,")  # USD: no purpose needed
    assert not r.errors, messages(r)
