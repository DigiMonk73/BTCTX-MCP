"""
GET /api/accounts/ in 2.0's shape (spec 5.9), the draft branch's stub (P-2):
id, name, kind, currency, exchange_id, exchange, hidden, in_use, with banks,
wallets, exchanges, then the fee accounts 5 and 6; External (99) isn't
listed. On this branch the kinds come from the fixed ids (1 a bank, 2 a
wallet, 3 and 4 exchange 1 "Exchange", 5 and 6 fee), and any other row is a
wallet when it holds BTC, else a bank (5.3). B2b replaces it with the book.
"""

from fastapi.testclient import TestClient
from sqlalchemy import event

from backend.main import app
from backend.tests.conftest import default_login


def account(id, name, kind, currency, exchange_id=None, exchange=None, in_use=False):
    return dict(id=id, name=name, kind=kind, currency=currency, exchange_id=exchange_id,
                exchange=exchange, hidden=False, in_use=in_use)


ONE_OF_EACH = [
    account(1, "Bank", "bank", "USD"),
    account(2, "Wallet", "wallet", "BTC"),
    account(3, "Exchange USD", "exchange", "USD", 1, "Exchange"),
    account(4, "Exchange BTC", "exchange", "BTC", 1, "Exchange"),
    account(5, "BTC Fees", "fee", "BTC"),
    account(6, "USD Fees", "fee", "USD"),
]


def logged_in() -> TestClient:
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    return client


def test_a_fresh_ledger_lists_its_six_accounts_in_the_books_shape(fresh_app):
    assert logged_in().get("/api/accounts/").json() == ONE_OF_EACH


def test_in_use_is_an_account_a_transaction_names(fresh_app):
    client = logged_in()
    r = client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2024-01-02T12:00:00Z", "from_account_id": 99, "to_account_id": 2,
        "amount": "1", "source": "MyBTC", "cost_basis_usd": "40000", "fee_amount": "0", "fee_currency": "BTC",
    })
    assert r.status_code == 200, r.text
    used = {a["id"]: a["in_use"] for a in client.get("/api/accounts/").json()}
    assert used == {1: False, 2: True, 3: False, 4: False, 5: False, 6: False}


def test_an_account_made_through_the_1x_api_is_a_wallet_or_a_bank_by_its_currency(fresh_app):
    client = logged_in()
    made = {}
    for name, currency in (("Savings", "BTC"), ("Credit Union", "USD")):
        r = client.post("/api/accounts/", json={"user_id": 1, "name": name, "currency": currency})
        assert r.status_code == 200, r.text
        made[name] = r.json()["id"]
    listed = [(a["id"], a["kind"]) for a in client.get("/api/accounts/").json()]
    assert listed == [(1, "bank"), (made["Credit Union"], "bank"), (2, "wallet"), (made["Savings"], "wallet"),
                      (3, "exchange"), (4, "exchange"), (5, "fee"), (6, "fee")]


def test_listing_writes_nothing(fresh_app):
    client = logged_in()
    engine = fresh_app.kw["bind"]
    writes = []

    def note(conn, cursor, statement, *args):
        if statement.lstrip().split()[0].upper() in ("INSERT", "UPDATE", "DELETE", "REPLACE"):
            writes.append(statement)

    event.listen(engine, "before_cursor_execute", note)
    try:
        assert client.get("/api/accounts/").status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", note)
    assert writes == []
