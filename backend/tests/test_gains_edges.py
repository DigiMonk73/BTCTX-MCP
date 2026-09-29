"""
The dashboard's gains on a row the app never writes itself: a lot disposal
without a holding period counts as short-term.
"""

from sqlalchemy import text

BANK, EXCH_USD, EXCH_BTC, EXTERNAL = 1, 3, 4, 99

LEDGER = [
    dict(type="Deposit", timestamp="2023-01-05T15:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
         amount="50000", fee_amount="0", fee_currency="USD", source="N/A"),
    dict(type="Buy", timestamp="2023-01-10T15:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
         amount="1", cost_basis_usd="20000", fee_amount="0", fee_currency="USD"),
    dict(type="Sell", timestamp="2024-06-01T15:00:00Z", from_account_id=EXCH_BTC, to_account_id=EXCH_USD,
         amount="0.5", gross_proceeds_usd="30000", fee_amount="0", fee_currency="USD"),
]


def test_a_disposal_without_holding_period_counts_as_short_term(auth_client, test_engine):
    auth_client.delete("/api/transactions/delete_all")
    try:
        for tx in LEDGER:
            assert auth_client.post("/api/transactions", json=tx).status_code == 200
        gains = auth_client.get("/api/calculations/gains-and-losses").json()
        assert (gains["short_term_gains"], gains["long_term_gains"]) == (0.0, 20000.0)

        with test_engine.begin() as con:
            con.execute(text("UPDATE lot_disposals SET holding_period = NULL"))
        gains = auth_client.get("/api/calculations/gains-and-losses").json()
        assert (gains["short_term_gains"], gains["long_term_gains"]) == (20000.0, 0.0)
        assert gains["short_term_net"] == gains["total_net_capital_gains"] == 20000.0
    finally:
        auth_client.delete("/api/transactions/delete_all")
