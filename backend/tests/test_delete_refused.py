"""
Deleting a transaction that later ones depend on is refused and changes
nothing. Before the fix the delete was committed before the ledger was
recalculated: the request answered 400 ("Not enough BTC to ..."), but the row
was gone and every later save failed on the same error.
"""

import pytest

DEPOSIT = dict(type="Deposit", timestamp="2023-01-15T17:00:00Z", from_account_id=99, to_account_id=1,
               amount="100000", fee_amount="0", fee_currency="USD", source="N/A")
BUY = dict(type="Buy", timestamp="2023-02-01T17:00:00Z", from_account_id=1, to_account_id=4,
           amount="1.0", cost_basis_usd="23000", fee_amount="0", fee_currency="USD")
TRANSFER = dict(type="Transfer", timestamp="2023-06-01T16:00:00Z", from_account_id=4, to_account_id=2,
                amount="0.6", fee_amount="0.0002", fee_currency="BTC", fee_usd="10")
SELL = dict(type="Sell", timestamp="2023-09-10T16:00:00Z", from_account_id=4, to_account_id=3,
            amount="0.4", gross_proceeds_usd="13000", fee_amount="10", fee_currency="USD")


def snapshot(client):
    return {
        "transactions": client.get("/api/transactions").json(),
        "balances": client.get("/api/calculations/accounts/balances").json(),
        "gains": client.get("/api/calculations/gains-and-losses").json(),
    }


@pytest.fixture
def ledger(auth_client):
    auth_client.delete("/api/transactions/delete_all")
    ids = {}
    for name, tx in (("deposit", DEPOSIT), ("buy", BUY), ("transfer", TRANSFER), ("sell", SELL)):
        r = auth_client.post("/api/transactions", json=tx)
        assert r.status_code == 200, r.text
        ids[name] = r.json()["id"]
    yield ids
    auth_client.delete("/api/transactions/delete_all")


def test_deleting_a_buy_later_rows_spend_is_refused_and_changes_nothing(auth_client, ledger):
    before = snapshot(auth_client)

    r = auth_client.delete(f"/api/transactions/{ledger['buy']}")

    assert r.status_code == 400
    assert r.json()["detail"].startswith("Not deleted: later transactions depend on this one. Not enough BTC")
    assert auth_client.get(f"/api/transactions/{ledger['buy']}").status_code == 200
    assert snapshot(auth_client) == before


def test_the_ledger_still_saves_after_a_refused_delete(auth_client, ledger):
    auth_client.delete(f"/api/transactions/{ledger['buy']}")

    r = auth_client.post("/api/transactions", json={**DEPOSIT, "timestamp": "2023-10-01T16:00:00Z", "amount": "500"})
    assert r.status_code == 200, r.text
    assert auth_client.delete(f"/api/transactions/{r.json()['id']}").status_code == 204


def test_a_delete_nothing_depends_on_still_recalculates(auth_client, ledger):
    assert auth_client.delete(f"/api/transactions/{ledger['sell']}").status_code == 204

    balances = {b["name"]: b["balance"] for b in auth_client.get("/api/calculations/accounts/balances").json()}
    assert balances["Exchange BTC"] == pytest.approx(0.4)
    assert balances["Exchange USD"] == 0
    assert auth_client.get("/api/calculations/gains-and-losses").json()["total_net_capital_gains"] == pytest.approx(5.40)
