"""
The account book (spec 5.4, card B3 #348): what an account is, asked by id
and answered from the accounts table, so a second wallet or exchange answers
as the first does. For a 1.x ledger it answers as 1.x's constants did.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.account import Account
from backend.services.account import FIXED_BOOK, AccountBook, BookAccount, read_book
from backend.tests.conftest import default_login


@pytest.fixture
def client(fresh_app) -> TestClient:
    c = TestClient(app)
    assert c.post("/api/login", json=default_login()).status_code == 200
    return c


def add(client, kind, name) -> list[int]:
    r = client.post("/api/accounts/", json={"kind": kind, "name": name})
    assert r.status_code == 201, r.text
    return [a["id"] for a in r.json()]


IDS = (None, 1, 2, 3, 4, 5, 6, 99, 7, 999)


@pytest.mark.parametrize("book", ["fresh", "fixed"])
def test_book_matches_1x(fresh_app, book):
    """A fresh ledger's book, and the 1.x book, answer as 1.x's constants did:
    bitcoin is 2 and 4 (5, BTC Fees, isn't), External and missing ids are no account."""
    if book == "fresh":
        db = fresh_app()
        found = read_book(db)
    else:
        found = FIXED_BOOK
    assert [i for i in IDS if found.is_btc(i)] == [2, 4]
    assert [i for i in IDS if found.is_yours(i)] == [1, 2, 3, 4]
    assert [found.currency(i) for i in IDS] == [None, "USD", "BTC", "USD", "BTC", "BTC", "USD", None, None, None]
    assert [found.kind(i) for i in IDS] == [None, "bank", "wallet", "exchange", "exchange", "fee", "fee",
                                            None, None, None]
    assert [found.name(i) for i in (1, 2, 3, 4, 5, 6, 99, 7)] == [
        "Bank", "Wallet", "Exchange USD", "Exchange BTC", "BTC Fees", "USD Fees", "External", "account 7 (missing)"]
    assert [found.exchange_of(i) for i in (1, 2, 3, 4, 5, 99)] == [None, None, 1, 1, None, None]
    assert [(found.usd_of(i), found.btc_of(i)) for i in (1, 2, 3, 4)] == [(None, None), (None, None), (3, 4), (3, 4)]


def test_a_second_wallet_bank_and_exchange_answer_as_the_first(client, fresh_app):
    wallet, = add(client, "wallet", "Cold Storage")
    bank, = add(client, "bank", "Credit Union")
    usd, btc = add(client, "exchange", "Kraken")
    assert client.put(f"/api/accounts/{wallet}", json={"hidden": True}).status_code == 200
    book = read_book(fresh_app())
    assert [i for i in (wallet, bank, usd, btc) if book.is_btc(i)] == [wallet, btc]
    assert [book.is_yours(i) for i in (wallet, bank, usd, btc)] == [True] * 4  # a hidden account is still yours
    assert [book.kind(i) for i in (wallet, bank, usd, btc)] == ["wallet", "bank", "exchange", "exchange"]
    assert [book.currency(i) for i in (wallet, bank, usd, btc)] == ["BTC", "USD", "USD", "BTC"]
    assert book.exchange_of(usd) == book.exchange_of(btc) == 2
    assert (book.usd_of(btc), book.btc_of(usd), book.btc_of(btc)) == (usd, btc, btc)
    assert (book.usd_of(4), book.btc_of(3)) == (3, 4)  # each exchange's own
    assert book.exchange_of(wallet) is None and book.usd_of(wallet) is None


def test_names_are_the_current_ones(client, fresh_app):
    usd, btc = add(client, "exchange", "Kraken")
    assert client.put("/api/accounts/2", json={"name": "Hardware"}).status_code == 200
    assert client.put(f"/api/accounts/{usd}", json={"name": "Coinbase"}).status_code == 200
    book = read_book(fresh_app())
    assert [book.name(i) for i in (2, usd, btc, 99, 5)] == ["Hardware", "Coinbase USD", "Coinbase BTC",
                                                            "External", "BTC Fees"]


def test_read_once_per_transaction(fresh_app):
    """One read per database transaction: the same book until a commit or a
    rollback, then the table as it is."""
    db = fresh_app()
    first = read_book(db)
    assert read_book(db) is first
    db.add(Account(id=100, user_id=1, name="Cold Storage", kind="wallet", currency="BTC"))
    db.commit()
    after = read_book(db)
    assert after is not first and after.is_btc(100)
    db.rollback()
    assert read_book(db) is not after


def test_a_book_of_any_rows():
    """The book answers from its rows alone: no id is special."""
    book = AccountBook([BookAccount(7, "Old wallet", "wallet", "BTC"),
                        BookAccount(8, "Old bank", "bank", "USD"),
                        BookAccount(2, "Wallet", "bank", "USD")])
    assert [i for i in (2, 7, 8, 4) if book.is_btc(i)] == [7]
    assert book.name(4) == "account 4 (missing)"
