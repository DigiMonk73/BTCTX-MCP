"""
The AI import by the book (spec 5.11, 5.12; card B5a #350): the AI's rows
name accounts as a CSV does (a reserved name, then a name now, ignoring
case), the preview writes each account's name now, its duplicate notes
too, and a hidden account's warning is passed on (5.5). A 1.x connector's
names (the reserved ones) work as they always did. Until B7a's gate the
save takes only 1 to 4, so rows into added accounts are saved with the gate
opened as B7a will (gate_open).
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.tests.account_pairs import COINBASE, add_them, rename
from backend.tests.conftest import default_login, stub_prices_at

AT = "2025-03-20T15:00:00Z"
PAYOUT = {"date": AT, "type": "Deposit", "amount": "0.002", "from_account": "External", "to_account": "Wallet",
          "source": "Interest", "cost_basis_usd": "200.00"}


@pytest.fixture
def client(fresh_app, monkeypatch) -> TestClient:
    stub_prices_at(monkeypatch, lambda when: 100000)
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    return client


def results(client: TestClient, *rows: dict) -> list[dict]:
    r = client.post("/api/import/entries/preview", json={"rows": list(rows)})
    assert r.status_code == 200, r.text
    return r.json()["results"]


def created(client: TestClient, *rows: dict) -> list[int]:
    r = client.post("/api/import/entries/execute", json={"rows": list(rows)})
    assert r.status_code == 200, r.text
    return [c["id"] for c in r.json()["created"]]


def test_a_1x_connectors_names_work_as_they_did(client):
    [result] = results(client, dict(PAYOUT, to_account="Exchange BTC"))
    assert result["status"] == "ready"
    assert (result["normalized"]["from_account"], result["normalized"]["to_account"]) == ("External", "Exchange BTC")


def test_an_account_is_named_by_its_name_now_or_its_reserved_one(fresh_app, client):
    rename(fresh_app, COINBASE)
    found = results(client, dict(PAYOUT, to_account="coinbase btc"), dict(PAYOUT, to_account="Exchange BTC",
                                                                            amount="0.003"))
    assert [(r["status"], r["normalized"]["to_account"]) for r in found] == [
        ("ready", "Coinbase BTC"), ("ready", "Coinbase BTC")]


def test_an_unknown_name_is_refused_with_the_names_the_ai_may_use(client):
    [result] = results(client, dict(PAYOUT, to_account="Coldcard"))
    assert (result["status"], result["errors"]) == ("invalid", [
        "Invalid account 'Coldcard'. Must be one of your accounts (Bank, Wallet, Exchange USD, Exchange BTC) "
        "or External."])


def test_the_duplicate_note_names_the_accounts_as_they_are_called_now(fresh_app, client):
    rename(fresh_app, COINBASE)
    [saved] = created(client, dict(PAYOUT, to_account="Coinbase BTC"))
    [result] = results(client, PAYOUT)
    assert (result["status"], result["matched_transaction_id"]) == ("possible_duplicate", saved)
    assert "recorded into Coinbase BTC, not Wallet" in " ".join(result["warnings"])


def test_a_hidden_account_is_passed_on_as_a_warning(client):
    assert client.put("/api/accounts/2", json={"hidden": True}).status_code == 200
    [result] = results(client, PAYOUT)
    assert result["status"] == "ready"
    assert "Wallet is hidden in Settings." in result["warnings"]


def test_the_ais_rows_into_added_accounts_and_back(gate_open, client):
    add_them(client)
    rows = [dict(PAYOUT, to_account="cold storage"),
            {"date": "2025-03-21T10:00:00Z", "type": "Transfer", "amount": "0.001", "from_account": "Cold Storage",
             "to_account": "Kraken BTC", "fee_amount": "0.00001", "fee_currency": "BTC"},
            {"date": "2025-03-22T10:00:00Z", "type": "Deposit", "amount": "250", "from_account": "External",
             "to_account": "credit union"}]
    saved = created(client, *rows)
    by_id = {t["id"]: t for t in client.get("/api/transactions").json()}
    assert [(by_id[i]["from_account_id"], by_id[i]["to_account_id"]) for i in saved] == [
        (99, 100), (100, 103), (99, 101)]
    again = results(client, *rows)
    assert [(r["status"], r["normalized"]["to_account"]) for r in again] == [
        ("duplicate", "Cold Storage"), ("duplicate", "Kraken BTC"), ("duplicate", "Credit Union")]
