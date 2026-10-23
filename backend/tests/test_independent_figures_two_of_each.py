"""
A ledger with two wallets and two exchanges (5.15; 7.4, B1's "Done when"),
its figures worked out by hand below, agrees with the independent
calculation.
"""

from backend.tests.independent_calc import independent_figures, ledger_tx


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


# Added in Claude's B1 fix run (claude-style-verdict-B1.md, gap 7): the same
# accounts in New York time, with BTC network fees, income, a gift and a
# spend, a covered 2026 Sell, every year's lots, and cents shared across
# moved pieces. Every figure worked out by hand. A lot's piece costs what
# the lot's BTC taken so far costs with it, in cents, less without it (#100).
ZONE = "America/New_York"
NEW_YORK = [
    # 1. Exchange BTC (4): lot A, 1 BTC for $40,000, 2024-01-10.
    ledger_tx("Buy", "2024-01-10T15:00:00Z", 3, 4, "1.00000000", cost_basis_usd="40000.00"),
    # 2. Wallet (2): income, lot I, 0.3 BTC worth $1,000, 2024-03-05. 2024 income $1,000.
    ledger_tx("Deposit", "2024-03-05T15:00:00Z", 99, 2, "0.30000000", source="Income", cost_basis_usd="1000.00"),
    # 3. Wallet -> Coldcard (7), 0.1001 BTC with a 0.0001 BTC fee worth $7.00.
    #    The fee first, from lot I: 0.0001 of 0.3 of $1,000 = $0.333.. -> $0.33. Row: C (2024, no broker),
    #    short, $7.00 - $0.33 = $6.67. Then 0.1 BTC moves: cost to 0.1001 = $333.666.. -> $333.67,
    #    less $0.33 = $333.34, keeping 2024-03-05.
    ledger_tx("Transfer", "2024-04-01T15:00:00Z", 2, 7, "0.10010000", fee_amount="0.00010000", fee_usd="7.00"),
    # 4. Wallet -> Coldcard, 0.1 BTC: cost to 0.2001 = $667.00, less $333.67 = $333.33. Lot I keeps
    #    0.0999 BTC and $1,000 - $0.33 - $333.34 - $333.33 = $333.00.
    ledger_tx("Transfer", "2024-05-01T15:00:00Z", 2, 7, "0.10000000"),
    # 5. A gift of 0.05 BTC (FMV $3,000) from Coldcard at 03:00 UTC on Jan 1 2025: 22:00 on Dec 31 2024
    #    in New York, so 2024's. FIFO: the first moved piece ($333.34): half of it, $166.67. Held since
    #    2024-03-05: short.
    ledger_tx("Withdrawal", "2025-01-01T03:00:00Z", 7, 99, "0.05000000", purpose="Gift", fmv_usd="3000.00"),
    # 6. Exchange BTC: lot B, 1 BTC for $50,000 at 03:00 UTC on Jan 1 2026: Dec 31 2025 in New York,
    #    so not covered.
    ledger_tx("Buy", "2026-01-01T03:00:00Z", 3, 4, "1.00000000", cost_basis_usd="50000.00"),
    # 7. Exchange BTC: lot C, 0.5 BTC for $30,000 + $10 fee = $30,010, 2026-02-01: covered.
    ledger_tx("Buy", "2026-02-01T15:00:00Z", 3, 4, "0.50000000", cost_basis_usd="30000.00", fee_amount="10.00"),
    # 8. Sell 2.25 BTC from 4 for $160,000 gross less a $40 fee: $159,960, shared by BTC as a running
    #    total: A (1) $71,093.333.. -> $71,093.33; A+B (2) $142,186.666.. -> $142,186.67, so B $71,093.34;
    #    C (0.25) the rest, $17,773.33.
    #    A: long, not covered: K, cost $40,000, gain $31,093.33.
    #    B: short (from Dec 31 2025), not covered: H, cost $50,000, gain $21,093.34.
    #    C: short, covered: G, cost half of $30,010 = $15,005.00, gain $2,768.33.
    ledger_tx("Sell", "2026-03-01T15:00:00Z", 4, 3, "2.25000000", gross_proceeds_usd="160000.00", fee_amount="40.00"),
    # 9. A spend of 0.05 BTC from Wallet received $4,000, with a 0.0001 BTC fee worth $8.00. Lot I has
    #    given 0.2001 BTC ($667.00). The fee: cost to 0.2002 = $667.333.. -> $667.33, so $0.33; a cost of
    #    the spend, so it realizes $8.00, and the spend $4,000 - $8 = $3,992.00. The spend: cost to
    #    0.2502 = $834.00, less $667.33 = $166.67. Both long (from 2024-03-05), no broker: L.
    #    Lot I keeps 0.0498 BTC and $333.00 - $0.33 - $166.67 = $166.00.
    ledger_tx("Withdrawal", "2026-04-01T15:00:00Z", 2, 99, "0.05000000", purpose="Spent",
              gross_proceeds_usd="4000.00", fee_amount="0.00010000", fee_currency="BTC", fee_usd="8.00"),
]


def _new_york(year):
    return independent.year_figures(
        independent.replay(NEW_YORK, accounts=independent.read_accounts(ACCOUNTS), tax_timezone=ZONE), year)


def _lots(figures):
    return {(h["account"], h["acquired"], h["quantity"], h["cost"]) for h in figures["end_of_year_holdings"]}


def test_new_york_2024_the_fee_income_gift_and_lots():
    figures = _new_york(2024)
    assert [(r["box"], r["date_acquired"], r["date_sold"], r["proceeds"], r["cost"], r["gain_loss"])
            for r in figures["form_8949"]] == [("C", "03/05/2024", "04/01/2024", "7.00", "0.33", "6.67")]
    assert figures["boxes"] == [{"box": "C", "line": "3", "rows": 1,
                                 "proceeds": "7.00", "cost": "0.33", "gain_loss": "6.67"}]
    assert figures["schedule_d"]["lines"] == {"3": {"proceeds": "7.00", "cost": "0.33", "gain_loss": "6.67"}}
    assert figures["income"] == {"Income": "1000.00", "Interest": "0.00", "Reward": "0.00", "Total": "1000.00"}
    assert figures["gifts_donations_lost"] == [{
        "date": "2025-01-01T03:00:00+00:00", "type": "Gift", "amount": "0.05000000", "fmv_usd": "3000.00",
        "lots_by_term": [{"term": "SHORT", "btc": "0.05000000", "cost_basis": "166.67"}]}]
    assert _lots(figures) == {
        ("Exchange BTC", "2024-01-10T15:00:00+00:00", "1.00000000", "40000.00"),
        ("Wallet", "2024-03-05T15:00:00+00:00", "0.09990000", "333.00"),
        ("Coldcard", "2024-03-05T15:00:00+00:00", "0.05000000", "166.67"),
        ("Coldcard", "2024-03-05T15:00:00+00:00", "0.10000000", "333.33"),
    }
    assert figures["end_of_year_total"] == {"quantity": "1.24990000", "cost": "40833.00"}


def test_new_york_2025_holds_the_lot_bought_on_its_last_night():
    figures = _new_york(2025)
    assert figures["form_8949"] == [] and figures["gifts_donations_lost"] == []
    assert ("Exchange BTC", "2026-01-01T03:00:00+00:00", "1.00000000", "50000.00") in _lots(figures)


def test_new_york_2026_rows_boxes_and_schedule_d():
    figures = _new_york(2026)
    assert [(r["box"], r["date_acquired"], r["proceeds"], r["cost"], r["gain_loss"], r["holding_period"])
            for r in figures["form_8949"]] == [
        ("K", "01/10/2024", "71093.33", "40000.00", "31093.33", "LONG"),
        ("H", "12/31/2025", "71093.34", "50000.00", "21093.34", "SHORT"),
        ("G", "02/01/2026", "17773.33", "15005.00", "2768.33", "SHORT"),
        ("L", "03/05/2024", "8.00", "0.33", "7.67", "LONG"),
        ("L", "03/05/2024", "3992.00", "166.67", "3825.33", "LONG"),
    ]
    assert {b["box"]: (b["rows"], b["proceeds"], b["cost"], b["gain_loss"]) for b in figures["boxes"]} == {
        "K": (1, "71093.33", "40000.00", "31093.33"), "H": (1, "71093.34", "50000.00", "21093.34"),
        "G": (1, "17773.33", "15005.00", "2768.33"), "L": (2, "4000.00", "167.00", "3833.00")}
    schedule_d = figures["schedule_d"]
    assert schedule_d["short_term"] == {"proceeds": "88866.67", "cost": "65005.00", "gain_loss": "23861.67"}
    assert schedule_d["long_term"] == {"proceeds": "75093.33", "cost": "40167.00", "gain_loss": "34926.33"}
    assert sorted(schedule_d["lines"]) == ["10", "1b", "2", "9"]
    assert _lots(figures) == {
        ("Exchange BTC", "2026-02-01T15:00:00+00:00", "0.25000000", "15005.00"),
        ("Wallet", "2024-03-05T15:00:00+00:00", "0.04980000", "166.00"),
        ("Coldcard", "2024-03-05T15:00:00+00:00", "0.05000000", "166.67"),
        ("Coldcard", "2024-03-05T15:00:00+00:00", "0.10000000", "333.33"),
    }
