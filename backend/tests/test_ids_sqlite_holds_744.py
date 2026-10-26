"""
A whole-number id beyond what SQLite stores (#744). SQLite's INTEGER is
64-bit, Python's int isn't: an id beyond -2⁶³..2⁶³-1, bound into a query,
raised OverflowError, and the request answered 500 ("Something unexpected
went wrong") with the error logged. Every id a request sends that reaches a
query is now refused first, a plain 422 naming it, before anything is
looked up; the largest id SQLite holds still answers as before.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.tests.conftest import default_login, stub_prices_at

LARGEST = 2 ** 63 - 1

# Each route with an id in its path that reaches a query, a body it takes,
# and what it answers for an id SQLite holds that names nothing
ROUTES = [
    ("GET", "/api/transactions/{id}", None, 404),
    ("PUT", "/api/transactions/{id}", {"amount": "1"}, 404),
    ("DELETE", "/api/transactions/{id}", None, 404),
    ("POST", "/api/transactions/{id}/coins-moved", {"amount": "1"}, 404),
    ("GET", "/api/accounts/{id}", None, 404),
    ("PUT", "/api/accounts/{id}", {"hidden": True}, 404),
    ("DELETE", "/api/accounts/{id}", None, 404),
    ("GET", "/api/calculations/account/{id}/balance", None, 200),  # an account with nothing: 0
    ("GET", "/api/debug/lots/{id}", None, 404),
    ("GET", "/api/debug/transactions/{id}/ledger-entries", None, 404),
]
TOO_BIG = [2 ** 70, -(2 ** 70), LARGEST + 1, -(2 ** 63) - 1]


@pytest.fixture
def owner(fresh_app, monkeypatch) -> TestClient:
    stub_prices_at(monkeypatch, lambda when: Decimal("50000"))
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    return client


@pytest.mark.parametrize("method, path, body, _named_nothing", ROUTES)
@pytest.mark.parametrize("id_", TOO_BIG)
def test_an_id_sqlite_cant_hold_is_a_plain_422(owner, method, path, body, _named_nothing, id_):
    r = owner.request(method, path.format(id=id_), json=body)
    assert r.status_code == 422, r.text
    assert [problem["loc"][0] for problem in r.json()["detail"]] == ["path"]


@pytest.mark.parametrize("method, path, body, named_nothing", ROUTES)
def test_the_largest_id_it_holds_answers_as_before(owner, method, path, body, named_nothing):
    r = owner.request(method, path.format(id=LARGEST), json=body)
    assert r.status_code == named_nothing, r.text


@pytest.mark.parametrize("id_", TOO_BIG)
def test_a_users_id_too(owner, id_):
    for method, body in (("PATCH", {"username": "x"}), ("DELETE", None)):
        r = owner.request(method, f"/api/users/{id_}", json=body)
        assert r.status_code == 422, r.text
        assert [problem["loc"] for problem in r.json()["detail"]] == [["path", "user_id"]]


@pytest.mark.parametrize("id_", TOO_BIG)
@pytest.mark.parametrize("field", ["from_account_id", "to_account_id"])
def test_an_account_id_in_a_body(owner, field, id_):
    """An edit reads the account it's given before it checks it (an
    inheritance's date, a date originally acquired): so does the list of
    the coins a Transfer would move with it, and a new transaction's."""
    r = owner.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2025-01-01T00:00:00Z", "from_account_id": 99, "to_account_id": 2,
        "amount": "0.1", "fee_amount": "0", "source": "MyBTC", "cost_basis_usd": "100"})
    assert r.status_code == 200, r.text
    tx_id = r.json()["id"]
    transfer = {"type": "Transfer", "timestamp": "2025-02-01T00:00:00Z", "from_account_id": 2, "to_account_id": 4,
                "amount": "0.05", "fee_amount": "0", "fee_currency": "BTC", field: id_}
    for method, route, body in (
        ("PUT", f"/api/transactions/{tx_id}", {"type": "Transfer", "from_account_id": 2, "to_account_id": 4, field: id_}),
        ("PUT", f"/api/transactions/{tx_id}", {"source": "Gift", field: id_}),
        ("POST", f"/api/transactions/{tx_id}/coins-moved", transfer),
        ("POST", "/api/transactions/coins-moved", transfer),
        ("POST", "/api/transactions", transfer),
    ):
        r = owner.request(method, route, json=body)
        assert r.status_code == 422, (route, r.text)
        assert [problem["loc"] for problem in r.json()["detail"]] == [["body", field]], (route, r.text)


@pytest.mark.parametrize("route", ["/api/import/entries/preview", "/api/import/entries/execute"])
def test_the_ai_imports_not_a_duplicate_of(owner, route):
    """The AI connector's rows: the transaction a row says it isn't."""
    row = {"date": "2025-01-01T00:00:00Z", "type": "Deposit", "from_account": "External", "to_account": "Wallet",
           "amount": "0.1", "source": "MyBTC", "cost_basis_usd": "100", "not_a_duplicate_of": 2 ** 70}
    r = owner.post(route, json={"rows": [row]})
    assert r.status_code == 422, r.text
    assert [problem["loc"] for problem in r.json()["detail"]] == [["body", "rows", 0, "not_a_duplicate_of"]]
    assert owner.post(route, json={"rows": [{**row, "not_a_duplicate_of": LARGEST}]}).status_code == 200
