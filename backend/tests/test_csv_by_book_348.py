"""
The CSV import by the book (spec 5.4, 5.5; card B3 #348): its account rules
are account_problems', so every pair of 5.5's table gets the same answer
from the CSV check as from the save, and every "is it bitcoin?" and "which
currency?" it asks is the book's, never 1.x's numbers. A file can name only
1.x's accounts until B5, so the by-book cases use a book in which Bank and
Wallet swap kinds: each answer follows it.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.account import AccountBook, BookAccount
from backend.services.csv_import import _validate_accounts_for_type, parse_csv_file
from backend.services.transaction import account_problems
from backend.tests.account_pairs import BOOK, COINBASE, PAIRS, pair_id, rename
from backend.tests.conftest import default_login

HEADER = "date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency,source,purpose"

# 1.x's accounts with Bank a bitcoin wallet and Wallet a dollar bank
SWAPPED = AccountBook([
    BookAccount(1, "Bank", "wallet", "BTC"),
    BookAccount(2, "Wallet", "bank", "USD"),
    BookAccount(3, "Exchange USD", "exchange", "USD", 1),
    BookAccount(4, "Exchange BTC", "exchange", "BTC", 1),
    BookAccount(5, "BTC Fees", "fee", "BTC"),
    BookAccount(6, "USD Fees", "fee", "USD"),
])

SELL_TO_BANK = "2024-01-05T10:00:00Z,Sell,0.1,Exchange BTC,Bank,,900,2,USD,,"


def csv(*rows: str) -> bytes:
    return ("\n".join([HEADER, *rows]) + "\n").encode()


@pytest.mark.parametrize("pair", PAIRS, ids=pair_id)
def test_the_csv_check_and_the_save_agree_on_each_pair(pair):
    tx_type, from_id, to_id, found = pair
    errors = _validate_accounts_for_type(tx_type, from_id, to_id, 7, BOOK)
    assert [(e.row_number, e.column, e.message) for e in errors] == [
        (7, f"{side}_account", message) for side, message in found]
    assert [(e.column, e.message) for e in errors] == [
        (f"{side}_account", message) for side, message in account_problems(tx_type, from_id, to_id, BOOK)]


def test_without_a_book_the_file_is_checked_in_1xs_accounts():
    [error] = parse_csv_file(csv(SELL_TO_BANK)).errors
    assert (error.column, error.message) == ("to_account", "A Sell from Exchange BTC goes into Exchange USD.")


def test_the_preview_checks_in_the_ledgers_book(fresh_app):
    """Exchange 1 renamed: a file still names it by its reserved names, and
    the message names it as the ledger does now."""
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    rename(fresh_app, COINBASE)
    preview = client.post("/api/import/preview", files={"file": ("x.csv", csv(SELL_TO_BANK), "text/csv")}).json()
    assert [(e["column"], e["message"]) for e in preview["errors"]] == [
        ("to_account", "A Sell from Coinbase BTC goes into Coinbase USD.")]


def test_the_amounts_unit_is_the_books():
    deposit = "2024-01-05T10:00:00Z,Deposit,0.123,External,Bank,100,,,,MyBTC,"
    assert parse_csv_file(csv(deposit)).errors  # dollars in 1.x's Bank: cents at most
    [preview] = parse_csv_file(csv(deposit), book=SWAPPED).previews
    assert preview.amount_currency == "BTC"


def test_a_dollar_withdrawal_is_the_books():
    gift = "2024-01-05T10:00:00Z,Withdrawal,100,Wallet,External,,,,,,Gift"
    result = parse_csv_file(csv(gift), book=SWAPPED)
    assert [(w.column, w.message) for w in result.warnings] == [
        ("purpose", "purpose is ignored: Spent, Gift, Donation and Lost are for bitcoin, and this withdrawal is in "
                    "dollars.")]
    assert "purpose" not in result.transactions[0]


def test_a_blank_fee_currency_and_a_transfers_fee_are_the_books():
    withdrawal = "2024-01-05T10:00:00Z,Withdrawal,0.1,Bank,External,,,0.0001,,,Lost"
    [tx] = parse_csv_file(csv(withdrawal), book=SWAPPED).transactions
    assert tx["fee_currency"] == "BTC"
    transfer = "2024-01-05T10:00:00Z,Transfer,0.1,Bank,Exchange BTC,,,1,USD,,"
    [error] = parse_csv_file(csv(transfer), book=SWAPPED).errors
    assert (error.column, error.message) == ("fee_currency", "A transfer from this account pays its fee in BTC.")
    consolidation = "2024-01-05T10:00:00Z,Transfer,0.1,Bank,Bank,,,,,,"
    [error] = parse_csv_file(csv(consolidation), book=SWAPPED).errors
    assert (error.column, error.message) == (
        "fee_amount", "A move within the same account records only its network fee: enter the fee.")


def test_a_deposits_basis_rules_are_the_books():
    income = "2024-01-05T10:00:00Z,Deposit,0.5,External,Bank,,,,,Income,"
    [warning] = parse_csv_file(csv(income), book=SWAPPED).warnings
    assert warning.column == "cost_basis_usd" and "valued at that hour's BTC price" in warning.message
    mybtc = "2024-01-05T10:00:00Z,Deposit,0.5,External,Bank,,,,,MyBTC,"
    [error] = parse_csv_file(csv(mybtc), book=SWAPPED).errors
    assert error.column == "cost_basis_usd"
