"""
What B3 (#348) adds to B2b's account book (spec 5.4; test_account_book.py
has the rest): `is_yours`, the 1.x book the CSV and AI imports use when
given none, a book of any rows, and one read per database transaction.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.account import Account
from backend.services.account import FIXED_BOOK, AccountBook, BookAccount, account_book
from backend.tests.conftest import default_login

IDS = (None, 1, 2, 3, 4, 5, 6, 99, 7, 999)


@pytest.fixture
def client(fresh_app) -> TestClient:
    c = TestClient(app)
    assert c.post("/api/login", json=default_login()).status_code == 200
    return c


def add(client, kind, name) -> list[int]:
    r = client.post("/api/accounts/", json={"kind": kind, "name": name})
    assert r.status_code == 201, r.text
    return [a["id"] for a in r.json()]


def answers(book: AccountBook) -> list:
    return [[i for i in IDS if book.is_btc(i)], [i for i in IDS if book.is_yours(i)],
            [book.currency(i) for i in IDS], [book.kind(i) for i in IDS], [book.name(i) for i in IDS[1:]],
            [(book.exchange_of(i), book.usd_of(i), book.btc_of(i), book.sends_1099da(i)) for i in IDS]]


def test_the_1x_book_answers_as_a_fresh_ledgers(fresh_app):
    """FIXED_BOOK, for a file read without a ledger, is what seed_defaults makes."""
    assert answers(FIXED_BOOK) == answers(account_book(fresh_app()))
    assert [i for i in IDS if FIXED_BOOK.is_yours(i)] == [1, 2, 3, 4]
    assert [i for i in IDS if FIXED_BOOK.is_btc(i)] == [2, 4]


def test_a_second_wallet_bank_and_exchange_are_yours_hidden_too(client, fresh_app):
    wallet, = add(client, "wallet", "Cold Storage")
    bank, = add(client, "bank", "Credit Union")
    usd, btc = add(client, "exchange", "Kraken")
    assert client.put(f"/api/accounts/{wallet}", json={"hidden": True}).status_code == 200
    book = account_book(fresh_app())
    assert [book.is_yours(i) for i in (wallet, bank, usd, btc, 5, 6, 99, None, 999)] == [True] * 4 + [False] * 5
    assert [i for i in (wallet, bank, usd, btc) if book.is_btc(i)] == [wallet, btc]


def test_a_book_of_any_rows():
    """The book answers from its rows alone: no id is special."""
    book = AccountBook([BookAccount(7, "Old wallet", "wallet", "BTC"),
                        BookAccount(8, "Old bank", "bank", "USD"),
                        BookAccount(2, "Wallet", "bank", "USD")])
    assert [i for i in (2, 7, 8, 4) if book.is_btc(i)] == [7]
    assert [i for i in (2, 7, 8, 4) if book.is_yours(i)] == [2, 7, 8]
    assert book.name(4) == "account 4 (missing)"


def test_read_once_per_transaction(fresh_app):
    """One read per database transaction: the same book until a commit or a
    rollback, then the table as it is."""
    db = fresh_app()
    first = account_book(db)
    assert account_book(db) is first
    db.add(Account(id=100, user_id=1, name="Cold Storage", kind="wallet", currency="BTC"))
    db.commit()
    after = account_book(db)
    assert after is not first and after.is_btc(100)
    db.rollback()
    assert account_book(db) is not after


def test_a_closed_session_reads_the_table_again(fresh_app):
    """A session closed and used again (a test's, a CLI command's) never
    keeps a book from before."""
    db = fresh_app()
    first = account_book(db)
    db.close()
    with fresh_app() as other:
        other.add(Account(id=100, user_id=1, name="Cold Storage", kind="wallet", currency="BTC"))
        other.commit()
    assert account_book(db) is not first and account_book(db).is_btc(100)
