"""
The six fixed accounts (database.FIXED_ACCOUNTS) can't be renamed, given
another currency or deleted through the account API (login only), and no
other account takes their names (#289). The ledger finds BTC Fees (5) and
USD Fees (6) by name, and every start puts a fixed account's name back: a
second "BTC Fees" would stop it, and a delete would take the account's
ledger lines with it.
"""

import pytest
from fastapi.testclient import TestClient

from backend.database import FIXED_ACCOUNTS, seed_defaults
from backend.main import app
from backend.tests.conftest import default_login


@pytest.mark.parametrize("fixed", FIXED_ACCOUNTS, ids=lambda a: a["name"])
def test_a_fixed_account_keeps_its_name_currency_and_place(auth_client, fixed):
    url = f"/api/accounts/{fixed['id']}"
    before = auth_client.get(url).json()
    other = "BTC" if fixed["currency"] == "USD" else "USD"
    assert auth_client.put(url, json={"name": "Renamed"}).status_code == 400
    assert auth_client.put(url, json={"currency": other}).status_code == 400
    assert auth_client.delete(url).status_code == 400
    assert auth_client.put(url, json={"name": fixed["name"]}).status_code == 200  # unchanged: fine
    assert auth_client.get(url).json() == before


@pytest.mark.parametrize("name, currency", [("BTC Fees", "BTC"), ("USD Fees", "USD")])
def test_no_second_fee_account(auth_client, name, currency):
    r = auth_client.post("/api/accounts/", json={"user_id": 1, "name": name, "currency": currency})
    assert r.status_code == 400


def test_no_other_account_takes_a_fixed_name(fresh_app):
    """A rename of an account someone made, to "BTC Fees", is refused (it was a 500 on the
    duplicate name); another name is fine."""
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    made = client.post("/api/accounts/", json={"user_id": 1, "name": "Savings", "currency": "BTC"}).json()
    url = f"/api/accounts/{made['id']}"
    assert client.put(url, json={"name": "BTC Fees"}).status_code == 400
    assert client.put(url, json={"name": "Cold storage"}).status_code == 200
    assert client.get(url).json()["name"] == "Cold storage"


def test_a_fee_still_goes_to_btc_fees_and_the_next_start_works(fresh_app):
    """The issue's steps: a rename of BTC Fees, a BTC fee, then a start."""
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    renamed = client.put("/api/accounts/5", json={"name": "Network fees"})
    for tx in (
        dict(type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=99, to_account_id=2,
             amount="1", source="MyBTC", cost_basis_usd="40000"),
        dict(type="Transfer", timestamp="2024-02-01T12:00:00Z", from_account_id=2, to_account_id=4,
             amount="0.5", fee_amount="0.0001", fee_currency="BTC"),
    ):
        assert client.post("/api/transactions", json=tx).status_code == 200
    seed_defaults(fresh_app.kw["bind"])  # what the next start does: it failed on a second "BTC Fees"
    fees = [a for a in client.get("/api/accounts/").json() if a["name"] == "BTC Fees"]
    assert [a["id"] for a in fees] == [5]
    assert renamed.status_code == 400
