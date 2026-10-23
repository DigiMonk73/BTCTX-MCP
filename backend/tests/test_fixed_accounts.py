"""
The six fixed accounts (database.FIXED_ACCOUNTS) through the account API
(2.0 spec 5.9): none takes a new name (renames come with B8) or currency;
your first bank, wallet and exchange (1-4) can be hidden, never deleted;
the fee accounts (5, 6) neither; and no account added takes a fixed name
(#289). The ledger finds the fee accounts by id, and every start puts 5's
and 6's names back.
"""

import pytest
from fastapi.testclient import TestClient

from backend.database import FIXED_ACCOUNTS, seed_defaults
from backend.main import app
from backend.tests.conftest import default_login

FIRST = "Your first bank, wallet and exchange can't be deleted. Hide one you don't use."


@pytest.mark.parametrize("fixed", FIXED_ACCOUNTS, ids=lambda a: a["name"])
def test_a_fixed_account_keeps_its_name_currency_and_place(auth_client, fixed):
    url = f"/api/accounts/{fixed['id']}"
    before = auth_client.get(url).json()
    other = "BTC" if fixed["currency"] == "USD" else "USD"
    assert auth_client.put(url, json={"name": "Renamed"}).status_code == 422
    assert auth_client.put(url, json={"currency": other}).status_code == 422
    deleted = auth_client.delete(url)
    assert deleted.status_code == 400
    assert deleted.json()["detail"] == (FIRST if fixed["kind"] != "fee" else "The fee accounts can't be deleted.")
    assert auth_client.get(url).json() == before


@pytest.mark.parametrize("name", ["BTC Fees", "usd fees"])
def test_no_second_fee_account(auth_client, name):
    r = auth_client.post("/api/accounts/", json={"kind": "wallet", "name": name})
    assert r.status_code == 400 and r.json()["detail"] == f"An account named '{name}' already exists."


def test_no_other_account_takes_a_fixed_name(auth_client):
    r = auth_client.post("/api/accounts/", json={"kind": "bank", "name": "Exchange USD"})
    assert r.status_code == 400
    assert r.json()["detail"].startswith("'Exchange USD' always means your first exchange in files")


def test_a_fee_still_goes_to_btc_fees_and_the_next_start_works(fresh_app):
    """#289's steps, with 5 renamed in the database itself (the API refuses
    it): a BTC fee goes to 5 all the same, no second "BTC Fees" is made, and
    the next start gives 5 its name back."""
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    engine = fresh_app.kw["bind"]
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE accounts SET name = 'Network fees' WHERE id = 5")
    for tx in (
        dict(type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=99, to_account_id=2,
             amount="1", source="MyBTC", cost_basis_usd="40000"),
        dict(type="Transfer", timestamp="2024-02-01T12:00:00Z", from_account_id=2, to_account_id=4,
             amount="0.5", fee_amount="0.0001", fee_currency="BTC", fee_usd="5.00"),
    ):
        assert client.post("/api/transactions", json=tx).status_code == 200
    seed_defaults(engine)  # what the next start does: it failed on a second "BTC Fees"
    fees = [a for a in client.get("/api/accounts/").json() if a["kind"] == "fee"]
    assert [(a["id"], a["name"]) for a in fees] == [(5, "BTC Fees"), (6, "USD Fees")]
