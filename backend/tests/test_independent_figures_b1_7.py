"""2.0-B1 step 7 (5.15, 7.4 B1 "Done when"): a ledger with two wallets and two exchanges, its figures worked out by hand below, agrees with the independent calculation. Written by Silas; read-only to the implementer."""

from backend.tests.conftest import independent_figures, ledger_tx


independent = independent_figures()

ACCOUNTS = {"accounts": [
    {"id": 1, "name": "Bank", "currency": "USD", "kind": "bank"},
    {"id": 2, "name": "Wallet", "currency": "BTC", "kind": "wallet"},
    {"id": 3, "name": "Exchange USD", "currency": "USD", "kind": "exchange", "exchange_id": 1, "sends_1099da": True},
    {"id": 4, "name": "Exchange BTC", "currency": "BTC", "kind": "exchange", "exchange_id": 1, "sends_1099da": True},
    {"id": 5, "name": "BTC Fees", "currency": "BTC", "kind": "fee"},
    {"id": 6, "name": "USD Fees", "currency": "USD", "kind": "fee"},
    {"id": 7, "name": "Coldcard", "currency": "BTC", "kind": "wallet"},
    {"id": 8, "name": "Quiet USD", "currency": "USD", "kind": "exchange", "exchange_id": 2, "sends_1099da": False},
    {"id": 9, "name": "Quiet BTC", "currency": "BTC", "kind": "exchange", "exchange_id": 2, "sends_1099da": False},
    {"id": 99, "name": "External", "currency": None, "kind": "external"},
]}

LEDGER = [
    # 1. Exchange BTC (4): 1 BTC for $40,000 + $100 fee -> lot A, basis $40,100, acquired 2024-01-10.
    ledger_tx("Buy", "2024-01-10T15:00:00Z", 3, 4, "1.00000000", cost_basis_usd="40000.00", fee_amount="100.00"),
    # 2. Quiet BTC (9): 1 BTC for $50,000 -> lot B, basis $50,000, acquired 2024-02-10.
    ledger_tx("Buy", "2024-02-10T15:00:00Z", 8, 9, "1.00000000", cost_basis_usd="50000.00"),
    # 3. Wallet (2): a gift-free deposit of 0.2 BTC worth $9,000 -> lot C, acquired 2024-02-20.
    ledger_tx("Deposit", "2024-02-20T15:00:00Z", 99, 2, "0.20000000", source="My BTC", cost_basis_usd="9000.00"),
    # 4. 4 -> Wallet (2): 0.5 BTC of lot A, half its basis $20,050, keeps 2024-01-10. Lot A keeps 0.5 / $20,050.
    ledger_tx("Transfer", "2024-03-01T15:00:00Z", 4, 2, "0.50000000"),
    # 5. 9 -> Coldcard (7): 0.5 BTC of lot B, $25,000, keeps 2024-02-10. Lot B keeps 0.5 / $25,000.
    ledger_tx("Transfer", "2024-04-01T15:00:00Z", 9, 7, "0.50000000"),
    # 6. Sell 0.5 BTC from 4 for $50,000 gross, $50 fee -> proceeds $49,950. FIFO in 4: lot A's 0.5, cost $20,050.
    #    Long-term (2024-01-10 -> 2025-06-01), exchange 1's switch on, not covered (bought 2024): box K.
    #    Gain $49,950 - $20,050 = $29,900.
    ledger_tx("Sell", "2025-06-01T12:00:00Z", 4, 3, "0.50000000", gross_proceeds_usd="50000.00", fee_amount="50.00"),
    # 7. Sell 0.25 BTC from 9 for $25,000. FIFO in 9: lot B's 0.25, cost $12,500. Long-term, switch off: box L.
    #    Gain $12,500.
    ledger_tx("Sell", "2025-06-02T12:00:00Z", 9, 8, "0.25000000", gross_proceeds_usd="25000.00"),
    # 8. Wallet (2) FIFO: the 2024-01-10 piece goes before lot C (2024-02-20) though C arrived first.
    #    Moving 0.6 to Coldcard: all 0.5 of the 01-10 piece ($20,050) and 0.1 of C ($4,500).
    ledger_tx("Transfer", "2025-07-01T12:00:00Z", 2, 7, "0.60000000"),
]

# Year-end 2025 by hand:
#   Wallet (2):   0.1 of C, acquired 2024-02-20, cost $4,500.
#   Exchange BTC (4): empty.   Quiet BTC (9): 0.25 of B, 2024-02-10, $12,500.
#   Coldcard (7): 0.5 of B (2024-02-10, $25,000), 0.5 of A (2024-01-10, $20,050), 0.1 of C (2024-02-20, $4,500).
HOLDINGS_2025 = {
    ("Wallet", "2024-02-20T15:00:00+00:00", "0.10000000", "4500.00"),
    ("Quiet BTC", "2024-02-10T15:00:00+00:00", "0.25000000", "12500.00"),
    ("Coldcard", "2024-02-10T15:00:00+00:00", "0.50000000", "25000.00"),
    ("Coldcard", "2024-01-10T15:00:00+00:00", "0.50000000", "20050.00"),
    ("Coldcard", "2024-02-20T15:00:00+00:00", "0.10000000", "4500.00"),
}


def _figures(year):
    return independent.year_figures(independent.replay(LEDGER, accounts=independent.read_accounts(ACCOUNTS)), year)


def test_2024_has_no_disposal():
    assert _figures(2024)["form_8949"] == []


def test_2025s_rows_worked_by_hand():
    rows = [(r["box"], r["date_acquired"], r["date_sold"], r["proceeds"], r["cost"], r["gain_loss"])
            for r in _figures(2025)["form_8949"]]
    assert rows == [
        ("K", "01/10/2024", "06/01/2025", "49950.00", "20050.00", "29900.00"),
        ("L", "02/10/2024", "06/02/2025", "25000.00", "12500.00", "12500.00"),
    ]


def test_2025s_year_end_holdings_worked_by_hand():
    held = {(h["account"], h["acquired"], h["quantity"], h["cost"])
            for h in _figures(2025)["end_of_year_holdings"]}
    assert held == HOLDINGS_2025
