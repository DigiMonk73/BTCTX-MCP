"""
The ledger engine on inputs its other tests don't reach: a transaction that
isn't there, and a BTC amount over the 21 million that can exist.
"""

BANK, WALLET, EXCH_BTC, EXTERNAL = 1, 2, 4, 99

LEDGER = [
    dict(type="Deposit", timestamp="2024-01-05T15:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
         amount="50000", fee_amount="0", fee_currency="USD", source="N/A"),
    dict(type="Buy", timestamp="2024-01-10T15:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
         amount="1", cost_basis_usd="20000", fee_amount="0", fee_currency="USD"),
]


def enter_ledger(client):
    client.delete("/api/transactions/delete_all")
    return [client.post("/api/transactions", json=tx).json()["id"] for tx in LEDGER]


def test_editing_or_deleting_a_missing_transaction_is_404_and_changes_nothing(auth_client):
    _, buy_id = enter_ledger(auth_client)
    try:
        missing = buy_id + 1000
        r = auth_client.put(f"/api/transactions/{missing}", json={"amount": "0.5"})
        assert (r.status_code, r.json()) == (404, {"detail": "Transaction not found."})
        r = auth_client.delete(f"/api/transactions/{missing}")
        assert (r.status_code, r.json()) == (404, {"detail": "Transaction not found."})
        lots = auth_client.get("/api/debug/lots").json()
        assert [(lot["created_txn_id"], lot["total_btc"]) for lot in lots] == [(buy_id, "1.00000000")]
    finally:
        auth_client.delete("/api/transactions/delete_all")


def test_a_btc_amount_over_21_million_is_refused(auth_client):
    auth_client.delete("/api/transactions/delete_all")
    r = auth_client.post("/api/transactions", json=dict(
        type="Deposit", timestamp="2024-01-05T15:00:00Z", from_account_id=EXTERNAL, to_account_id=WALLET,
        amount="21000000.00000001", cost_basis_usd="1", fee_amount="0", fee_currency="BTC", source="MyBTC"))
    assert (r.status_code, r.json()) == (422, {"detail": "A BTC amount can't be more than 21,000,000."})
