"""
CSV import rules found in the v0.9.2 hardening sweep (F10, F25, F30, F12):
dates follow the tax timezone, malformed numbers are errors, a USD transfer's
fee is in USD, a BTC withdrawal needs a purpose. And the preview refuses
the fee accounts, dollar amounts past the cent and transfers across
currencies, as the save does (#266).
"""

from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from backend.constants import ACCOUNT_NAME_TO_ID
from backend.services.csv_import import parse_csv_file
from backend.services.transaction import create_transaction_record

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


def test_a_btc_deposit_that_isnt_income_needs_a_basis():
    """F15: a blank basis on a MyBTC/Gift deposit was a warning and saved as $0."""
    r = parse(
        "2024-01-05,Deposit,0.1,External,Wallet,,,,,MyBTC,,",
        "2024-01-05,Deposit,0.1,External,Exchange BTC,,,,,Gift,,",
    )
    assert messages(r) == ["Enter this deposit's cost basis (0 if it's unknown)."] * 2
    r = parse(
        "2024-01-05,Deposit,0.1,External,Wallet,0,,,,MyBTC,,",       # a stated 0 is fine
        "2024-01-05,Deposit,0.1,External,Wallet,,,,,Income,,",       # income: priced later
        "2024-01-05,Deposit,100,External,Bank,,,,,,,",               # USD: no basis
    )
    assert not r.errors, messages(r)


def test_a_utf8_file_with_a_byte_order_mark_is_read():
    """Bug hunt 2026-09-29: Excel's "CSV UTF-8" starts the file with a
    byte-order mark; it was kept in the first header ("\\ufeffdate"), so the
    file was refused with "Missing required columns: date"."""
    content = b"\xef\xbb\xbf" + f"{HEADER}\n2024-01-05,Deposit,100,External,Bank,,,,,,,\n".encode()
    r = parse_csv_file(content, CHICAGO)
    assert not r.errors, messages(r)
    assert len(r.transactions) == 1


def test_the_preview_says_what_each_amount_is_in_and_names_the_accounts_as_usual():
    """#254: the preview wrote every amount as BTC ($50,000 into Bank read
    "50000.00000000 BTC") and the accounts as "Exchange Usd"."""
    r = parse(
        "2024-01-05,Deposit,50000,External,Bank,,,,,,,",
        "2024-01-05,Transfer,5000,bank,exchange usd,,,,,,,",
        "2024-01-05,Withdrawal,2000,Bank,External,,,,,,,",
        "2024-01-06,Buy,0.1,Exchange USD,EXCHANGE BTC,4000,,,,,,",
        "2024-01-07,Transfer,0.1,Exchange BTC,Wallet,,,0.0001,BTC,,,",
        "2024-01-08,Withdrawal,0.01,Wallet,External,,500,,,,Spent,",
        "2024-01-09,Sell,0.05,Exchange BTC,Exchange USD,,2500,,,,,",
        "2024-01-10,Deposit,0.2,External,Wallet,8000,,,,MyBTC,,",
        "2024-01-11,Transfer,0.2,Wallet,Wallet,,,0.0001,BTC,,,",
    )
    assert not r.errors, messages(r)
    shown = [(p.amount_currency, p.from_account, p.to_account) for p in r.previews]
    assert shown == [
        ("USD", "External", "Bank"),
        ("USD", "Bank", "Exchange USD"),
        ("USD", "Bank", "External"),
        ("BTC", "Exchange USD", "Exchange BTC"),
        ("BTC", "Exchange BTC", "Wallet"),
        ("BTC", "Wallet", "External"),
        ("BTC", "Exchange BTC", "Exchange USD"),
        ("BTC", "External", "Wallet"),
        ("BTC", "Wallet", "Wallet"),
    ]


FEE_ACCOUNT = "Invalid account '{}'. Must be one of: Bank, Wallet, Exchange USD, Exchange BTC, External."
USD_CENTS = "A USD amount can have at most 2 decimal places."
ONE_CURRENCY = ("Transfer must stay in one currency: bitcoin between Wallet and Exchange BTC, "
                "dollars between Bank and Exchange USD.")

# #266: rows the preview passed and the import then refused (the whole file)
REFUSED_AT_IMPORT = [
    ("2024-01-05,Deposit,1,External,BTC Fees,,,,,,,", FEE_ACCOUNT.format("btc fees")),
    ("2024-01-05,Deposit,100,External,usd fees,,,,,,,", FEE_ACCOUNT.format("usd fees")),
    ("2024-01-05,Withdrawal,0.1,BTC Fees,External,,,,,,,", FEE_ACCOUNT.format("btc fees")),  # no purpose asked
    ("2024-01-05,Deposit,50000.125,External,Bank,,,,,,,", USD_CENTS),
    ("2024-01-05,Withdrawal,20.001,Exchange USD,External,,,,,,,", USD_CENTS),
    ("2024-01-05,Transfer,100.5,Bank,Exchange USD,,,,,,,", None),  # cents are fine
    ("2024-01-05,Transfer,100,Bank,Wallet,,,,,,,", ONE_CURRENCY),
    ("2024-01-05,Transfer,0.1,Exchange BTC,Exchange USD,,,,,,,", ONE_CURRENCY),
]


@pytest.mark.parametrize("row, message", REFUSED_AT_IMPORT)
def test_the_preview_refuses_what_the_import_refuses(row, message):
    r = parse(row)
    assert messages(r) == ([message] if message else []), messages(r)


def test_a_usd_amount_with_trailing_zeros_has_its_cents_only():
    r = parse(
        "2024-01-05,Deposit,50000.120,External,Bank,,,,,,,",
        "2024-01-05,Deposit,0.123,External,Wallet,5,,,,MyBTC,,",  # bitcoin: 8 places
    )
    assert not r.errors, messages(r)


@pytest.mark.parametrize("row, message", REFUSED_AT_IMPORT)
def test_a_row_the_preview_passes_is_saved(auth_client, row, message):
    """What the preview passes, the import saves; what it refuses, it
    can't import (#266)."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    funds = "2024-01-01,Deposit,1000,External,Bank,,,,,,,\n2024-01-01,Deposit,1,External,Wallet,100,,,,MyBTC,,\n"
    content = {"file": ("rows.csv", f"{HEADER}\n{funds}{row}\n".encode(), "text/csv")}
    preview = auth_client.post("/api/import/preview", files=content).json()
    assert preview["can_import"] is (message is None), preview
    if message is None:
        assert auth_client.post("/api/import/execute", files=content).status_code == 200
        assert len(auth_client.get("/api/transactions").json()) == 3
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def _save_data(row: str) -> dict:
    """A refused row as the save would get it: its type, time, amount and accounts."""
    date, tx_type, amount, from_name, to_name = row.split(",")[:5]
    from_id, to_id = (ACCOUNT_NAME_TO_ID[n.strip().lower()] for n in (from_name, to_name))
    return {
        "type": tx_type, "timestamp": datetime(2024, 1, 5, 18, tzinfo=timezone.utc), "amount": Decimal(amount),
        "from_account_id": from_id, "to_account_id": to_id, "fee_amount": Decimal(0),
        "fee_currency": "USD", "purpose": "Spent",  # no fee: its currency doesn't matter
    }


# What the save says for each of the preview's reasons
SAVE_SAYS = {FEE_ACCOUNT.format("btc fees"): "Unknown account id 5.", FEE_ACCOUNT.format("usd fees"): "Unknown account id 6.",
             USD_CENTS: USD_CENTS, ONE_CURRENCY: "Transfer => same currency required."}


@pytest.mark.parametrize("row, message", [(r, m) for r, m in REFUSED_AT_IMPORT if m])
def test_the_save_refuses_each_row_the_preview_refuses(test_engine, row, message):
    """The preview is never stricter than the save (#266's review): if the
    save ever takes one of these rows, the preview's rule has to go too."""
    db = sessionmaker(bind=test_engine)()
    try:
        with pytest.raises(HTTPException) as refused:
            create_transaction_record(_save_data(row), db, auto_commit=False)
        assert refused.value.detail == SAVE_SAYS[message]
    finally:
        db.rollback()
        db.close()
