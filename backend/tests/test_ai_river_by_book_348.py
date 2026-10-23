"""
The AI import and River by the book (spec 5.4, 5.5; card B3 #348): both run
the CSV import's row check with the ledger's book, and their own "is it
bitcoin?" questions (the AI's value autofill, a dollar withdrawal's value,
the duplicate check's purpose, River's transfer fee) are the book's. A file
can name only 1.x's accounts until B5, so the by-book cases use a book in
which Bank and Wallet swap kinds: each answer follows it.
"""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from backend.main import app
from backend.models.account import Account
from backend.models.transaction import Transaction
from backend.routers.river_import import _ledger_amount
from backend.schemas.entry_import import EntryRow
from backend.schemas.river_import import RiverExecuteRow
from backend.services.account import AccountBook, BookAccount
from backend.services.entry_import import _autofill_target, _compared, validate_rows
from backend.services.river_import import RiverProposal, annotate_duplicates
from backend.tests.account_pairs import BOOK, COINBASE, rename
from backend.tests.conftest import default_login

# 1.x's accounts with Bank a bitcoin wallet and Wallet a dollar bank
SWAPPED = AccountBook([
    BookAccount(1, "Bank", "wallet", "BTC"),
    BookAccount(2, "Wallet", "bank", "USD"),
    BookAccount(3, "Exchange USD", "exchange", "USD", 1),
    BookAccount(4, "Exchange BTC", "exchange", "BTC", 1),
    BookAccount(5, "BTC Fees", "fee", "BTC"),
    BookAccount(6, "USD Fees", "fee", "USD"),
])

SELL_TO_BANK = {"date": "2024-01-05T10:00:00Z", "type": "Sell", "amount": "0.1", "from_account": "Exchange BTC",
                "to_account": "Bank", "proceeds_usd": "900", "fee_amount": "2", "fee_currency": "USD"}


def test_the_ai_and_river_check_in_the_ledgers_book(fresh_app):
    """Exchange 1 renamed: a row still names it by its reserved names, and
    the message names it as the ledger does now."""
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    rename(fresh_app, COINBASE)
    renamed = "A Sell from Coinbase BTC goes into Coinbase USD."
    ai = client.post("/api/import/entries/preview", json={"rows": [SELL_TO_BANK]}).json()
    assert ai["results"][0]["errors"] == [renamed]
    river = client.post("/api/import/river/execute", json={"rows": [SELL_TO_BANK]})
    assert river.status_code == 400 and renamed in river.json()["detail"]


def test_without_a_book_the_ai_checks_in_1xs_accounts():
    [prepared] = validate_rows([EntryRow(**SELL_TO_BANK)])
    assert prepared.result.errors == ["A Sell from Exchange BTC goes into Exchange USD."]


def test_the_ai_imports_checks_are_the_books():
    row = EntryRow(date="2024-01-05T10:00:00Z", type="Withdrawal", amount=Decimal("100"), from_account="Wallet",
                   to_account="External", purpose="Rent", fmv_usd=Decimal("50"))
    [prepared] = validate_rows([row], book=SWAPPED)
    assert prepared.result.warnings == [
        "fmv_usd is ignored: it is for Gift, Donation and Lost withdrawals of bitcoin."]
    income = {"type": "Deposit", "to_account_id": 1, "source": "Income"}
    assert (_autofill_target(income, SWAPPED), _autofill_target(income, BOOK)) == ("cost_basis_usd", None)
    spent = {"type": "Withdrawal", "from_account_id": 1, "purpose": "Spent"}
    assert (_autofill_target(spent, SWAPPED), _autofill_target(spent, BOOK)) == ("proceeds_usd", None)


def test_the_duplicate_checks_purpose_is_the_books():
    class Row:
        type, from_account_id, purpose = "Withdrawal", 2, "Gift"
    assert (_compared(Row(), "purpose", SWAPPED), _compared(Row(), "purpose", BOOK)) == ("", "gift")


def test_a_river_transfer_carries_its_fee_from_a_bitcoin_account_of_the_book():
    row = RiverExecuteRow(date="2024-01-05T10:00:00Z", type="Transfer", amount=Decimal("0.1"),
                          from_account="Bank", to_account="Exchange BTC", fee_amount=Decimal("0.0001"),
                          fee_currency="BTC")
    assert (_ledger_amount(row, SWAPPED), _ledger_amount(row, BOOK)) == (Decimal("0.1001"), Decimal("0.1"))


def _river_deposit_beside(fresh_app, to_account_id: int, into: int = 4) -> RiverProposal:
    """A River payout into Exchange BTC (or `into`) beside an old deposit
    from External into `to_account_id`, the same amount and minute, saved
    straight into the table as only a BitcoinTX before 0.9.2 could; the row
    as the duplicate check leaves it."""
    when = datetime(2024, 3, 1, 12, 0, tzinfo=timezone.utc)
    with fresh_app() as db:
        db.add_all([Account(id=7, user_id=1, name="cold2", kind="wallet", currency="BTC"),
                    Account(id=8, user_id=1, name="old bank", kind="bank", currency="USD")])
        db.add(Transaction(type="Deposit", timestamp=when, from_account_id=99, to_account_id=to_account_id,
                           amount=Decimal("0.0123"), fee_amount=Decimal("0"), source="MyBTC",
                           cost_basis_usd=Decimal("100")))
        db.commit()
        row = RiverProposal(row_number=1, timestamp=when, river_tag=None, type="Deposit", from_account_id=99,
                            to_account_id=into, amount=Decimal("0.0123"), source="MyBTC")
        annotate_duplicates([row], db)
    return row


def test_a_river_row_is_never_taken_for_a_row_into_a_missing_account(fresh_app):
    """1.x's answer kept: the amount of a row into an account that doesn't
    exist counts as dollars, so a bitcoin row is never its copy."""
    row = _river_deposit_beside(fresh_app, 999)
    assert (row.status, row.matched_tx_id) == ("new", None)


def test_a_river_row_is_compared_with_an_old_accounts_row_by_its_currency(fresh_app):
    """S7: a row into 7 (a wallet 1.x's account API made) is bitcoin now, so
    River's rule (the same kind, way, amount and minute) finds it; one into
    8 (dollars) stays dollars, never a bitcoin row's copy."""
    assert _river_deposit_beside(fresh_app, 7).status == "matched"


def test_a_row_into_wallet_is_never_an_old_wallets_copy(fresh_app):
    """Two wallets on the same side are never copies (the owner's rule,
    2026-10-15, B5a #350): 7 is a wallet, as Wallet is."""
    assert _river_deposit_beside(fresh_app, 7, into=2).status == "new"


def test_a_river_row_is_never_taken_for_an_old_dollar_accounts_row(fresh_app):
    assert _river_deposit_beside(fresh_app, 8).status == "new"
