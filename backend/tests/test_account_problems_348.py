"""
One copy of the rules (spec 5.5, card B3 #348): account_problems gives every
rule a pair of accounts breaks, by the book's kinds, in 5.5's words, and the
save refuses with the first. A second bank, wallet or exchange follows the
first one's rules; a Buy or a Sell stays on one exchange (Q15).
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.transaction import account_problems
from backend.tests.account_pairs import BOOK, MESSAGES, PAIRS, add_them, pair_id
from backend.tests.conftest import default_login


@pytest.fixture
def client(fresh_app) -> TestClient:
    c = TestClient(app)
    assert c.post("/api/login", json=default_login()).status_code == 200
    add_them(c)
    return c


@pytest.mark.parametrize("pair", PAIRS, ids=pair_id)
def test_each_pair_of_the_table(pair):
    tx_type, from_id, to_id, found = pair
    assert account_problems(tx_type, from_id, to_id, BOOK) == found


def test_a_type_that_isnt_one_breaks_no_account_rule():
    assert account_problems("Swap", 1, 2, BOOK) == []


@pytest.mark.parametrize("pair", [p for p in PAIRS if 5 not in p[1:3] and 6 not in p[1:3]], ids=pair_id)
def test_the_save_refuses_with_the_first(client, pair):
    """Through the API: a refused pair is a 400 with its first message; an
    allowed one never answers with an account rule (it may lack funds)."""
    tx_type, from_id, to_id, found = pair
    r = client.post("/api/transactions", json={
        "type": tx_type, "timestamp": "2024-06-15T15:00:00Z", "from_account_id": from_id, "to_account_id": to_id,
        "amount": "1", "fee_amount": "0.01" if from_id == to_id else "0", "cost_basis_usd": "500",
        "gross_proceeds_usd": "600", "source": "MyBTC", "purpose": "Gift"})
    if found:
        assert (r.status_code, r.json()["detail"]) == (400, found[0][1])
    else:
        assert r.status_code == 200 or r.json()["detail"] not in MESSAGES, r.text


def test_names_are_the_accounts_current_ones(client):
    assert client.put("/api/accounts/102", json={"name": "Coinbase"}).status_code == 200
    r = client.post("/api/transactions", json={
        "type": "Sell", "timestamp": "2024-06-15T15:00:00Z", "from_account_id": 103, "to_account_id": 1,
        "amount": "0.01", "fee_amount": "0", "gross_proceeds_usd": "600"})
    assert (r.status_code, r.json()["detail"]) == (400, "A Sell from Coinbase BTC goes into Coinbase USD.")


def test_a_buy_and_a_sell_on_the_second_exchange_save(client):
    funded = client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2024-01-02T12:00:00Z", "from_account_id": 99, "to_account_id": 102,
        "amount": "20000", "source": "N/A", "fee_amount": "0", "fee_currency": "USD"})
    assert funded.status_code == 200, funded.text
    for body in ({"type": "Buy", "from_account_id": 102, "to_account_id": 103, "cost_basis_usd": "6000"},
                 {"type": "Buy", "from_account_id": 101, "to_account_id": 103, "cost_basis_usd": "6000"},
                 {"type": "Sell", "from_account_id": 103, "to_account_id": 102, "gross_proceeds_usd": "3200"}):
        if body["from_account_id"] == 101:
            client.post("/api/transactions", json={
                "type": "Deposit", "timestamp": "2024-01-02T12:00:00Z", "from_account_id": 99,
                "to_account_id": 101, "amount": "20000", "source": "N/A", "fee_amount": "0"})
        r = client.post("/api/transactions", json={
            "timestamp": "2024-06-15T15:00:00Z", "amount": "0.1", "fee_amount": "0", "fee_currency": "USD", **body})
        assert r.status_code == 200, r.text


def test_a_consolidation_in_a_second_wallet_saves(client):
    deposit = client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2024-01-02T12:00:00Z", "from_account_id": 99, "to_account_id": 100,
        "amount": "1", "source": "MyBTC", "cost_basis_usd": "40000", "fee_amount": "0"})
    assert deposit.status_code == 200, deposit.text
    r = client.post("/api/transactions", json={
        "type": "Transfer", "timestamp": "2024-06-15T15:00:00Z", "from_account_id": 100, "to_account_id": 100,
        "amount": "0.5", "fee_amount": "0.0001", "fee_currency": "BTC"})
    assert r.status_code == 200, r.text
