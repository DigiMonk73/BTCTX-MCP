"""
The AI key reads the account list, and nothing else of the account API
(spec 5.12, Q11; card B5a #350): the connector names any of the user's
accounts, so it reads them with the key (AI_KEY_ROUTES gains the one
read-only route, on purpose); adding, hiding or deleting one stays the
owner's (403 with the key: test_ai_key.py's REFUSED), and reading the list
changes nothing.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import ai_key
from backend.tests.account_pairs import add_them
from backend.tests.conftest import default_login


@pytest.fixture
def owner(fresh_app) -> TestClient:
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    add_them(client)
    return client


@pytest.fixture
def key(fresh_app) -> dict:
    """What the owner does in Settings: AI access on, a key made."""
    with fresh_app() as db:
        ai_key.set_access(db, True)
        return {"Authorization": f"Bearer {ai_key.create_key(db)}"}


def dump(Session) -> list[str]:
    with Session() as db:
        return list(db.connection().connection.dbapi_connection.iterdump())


def test_the_key_reads_the_list(owner, key):
    with_key = TestClient(app).get("/api/accounts/", headers=key)
    assert with_key.status_code == 200
    assert with_key.json() == owner.get("/api/accounts/").json()
    assert [a["name"] for a in with_key.json()] == [
        "Bank", "Credit Union", "Wallet", "Cold Storage", "Exchange USD", "Exchange BTC", "Kraken USD", "Kraken BTC",
        "BTC Fees", "USD Fees"]


def test_reading_the_list_writes_nothing(fresh_app, owner, key):
    before = dump(fresh_app)
    for _ in range(3):
        assert TestClient(app).get("/api/accounts/", headers=key).status_code == 200
    assert dump(fresh_app) == before


@pytest.mark.parametrize("method, path, kwargs", [
    ("POST", "/api/accounts/", {"json": {"kind": "wallet", "name": "Jade"}}),
    ("PUT", "/api/accounts/100", {"json": {"hidden": True}}),
    ("DELETE", "/api/accounts/100", {}),
    ("GET", "/api/accounts/100", {}),  # one account: the list is the one route
])
def test_the_rest_of_the_account_api_is_the_owners(fresh_app, owner, key, method, path, kwargs):
    before = dump(fresh_app)
    r = TestClient(app).request(method, path, headers=key, **kwargs)
    assert (r.status_code, r.json()["detail"]) == (403, ai_key.NOT_ALLOWED)
    assert dump(fresh_app) == before


def test_the_list_is_the_one_account_route_the_key_may_use():
    assert [(m, r) for m, r, _ in ai_key.AI_KEY_ROUTES if r.startswith("/api/accounts")] == [("GET", "/api/accounts/")]
