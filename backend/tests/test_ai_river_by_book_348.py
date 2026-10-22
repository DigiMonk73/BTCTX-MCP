"""
The AI import and River by the book (spec 5.4, 5.5; card B3 #348): both run
the CSV import's row check with the ledger's book, and their own "is it
bitcoin?" questions (the AI's value autofill, a dollar withdrawal's value,
the duplicate check's purpose, River's transfer fee) are the book's. A file
can name only 1.x's accounts until B5, so the by-book cases use a book in
which Bank and Wallet swap kinds: each answer follows it.
"""

from decimal import Decimal

from fastapi.testclient import TestClient

from backend.main import app
from backend.routers.river_import import _ledger_amount
from backend.schemas.entry_import import EntryRow
from backend.schemas.river_import import RiverExecuteRow
from backend.services.account import AccountBook, BookAccount
from backend.services.entry_import import _autofill_target, _compared, validate_rows
from backend.tests.account_pairs import BOOK
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
    assert client.put("/api/accounts/3", json={"name": "Coinbase"}).status_code == 200
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
