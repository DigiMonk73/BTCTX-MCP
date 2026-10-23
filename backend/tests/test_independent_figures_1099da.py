"""
Broker reporting in the independent calculation (5.15, 5.7): a Sell is
broker-reported from any exchange whose 1099-DA switch (`sends_1099da`) is
on, and covered only for a lot bought into that same account from
2026-01-01 in the tax timezone. A Sell's own `broker_reporting` still wins.
With no accounts list, exchange 1 (3 and 4) has the switch on.
"""

from backend.tests.independent_calc import independent_figures, ledger_tx


independent = independent_figures()

ACCOUNTS = {"accounts": [
    {"id": 3, "name": "Exchange USD", "currency": "USD", "kind": "exchange", "exchange_id": 1, "sends_1099da": True},
    {"id": 4, "name": "Exchange BTC", "currency": "BTC", "kind": "exchange", "exchange_id": 1, "sends_1099da": True},
    {"id": 8, "name": "Quiet USD", "currency": "USD", "kind": "exchange", "exchange_id": 2, "sends_1099da": False},
    {"id": 9, "name": "Quiet BTC", "currency": "BTC", "kind": "exchange", "exchange_id": 2, "sends_1099da": False},
    {"id": 99, "name": "External", "currency": None, "kind": "external"},
]}


def _boxes(transactions, **options):
    ledger = independent.replay(transactions, **options)
    return [row["box"] for row in independent.year_figures(ledger, 2026)["form_8949"]]


# 03:00 UTC on Jan 1 2026 is still Dec 31 2025 in Chicago.
NEW_YEARS_NIGHT = ledger_tx("Buy", "2026-01-01T03:00:00Z", 3, 4, "1.00000000", cost_basis_usd="1000.00")
SELL_4 = ledger_tx("Sell", "2026-06-01T12:00:00Z", 4, 3, "0.50000000", gross_proceeds_usd="600.00")


def test_the_fixed_exchanges_switch_is_on_by_default():
    accounts = independent.read_accounts({})
    assert accounts[3].sends_1099da is True and accounts[4].on_1099da is True


def test_covered_is_the_tax_timezones_day_not_the_utc_day():
    assert _boxes([NEW_YEARS_NIGHT, SELL_4], tax_timezone="America/Chicago") == ["H"]  # bought 2025 there: noncovered


def test_in_utc_the_same_buy_is_covered():
    assert _boxes([NEW_YEARS_NIGHT, SELL_4]) == ["G"]


def test_an_exchange_with_the_switch_off_reports_nothing():
    accounts = independent.read_accounts(ACCOUNTS)
    sales = [ledger_tx("Buy", "2026-02-01T15:00:00Z", 8, 9, "1.00000000", cost_basis_usd="1000.00"),
             ledger_tx("Sell", "2026-06-01T12:00:00Z", 9, 8, "0.50000000", gross_proceeds_usd="600.00")]
    assert _boxes(sales, accounts=accounts) == ["I"]


def test_a_sells_own_broker_reporting_still_wins():
    accounts = independent.read_accounts(ACCOUNTS)
    sales = [ledger_tx("Buy", "2026-02-01T15:00:00Z", 8, 9, "1.00000000", cost_basis_usd="1000.00"),
             ledger_tx("Sell", "2026-06-01T12:00:00Z", 9, 8, "0.50000000", gross_proceeds_usd="600.00",
                broker_reporting="basis")]
    assert _boxes(sales, accounts=accounts) == ["G"]


def test_a_lot_bought_on_one_exchange_and_moved_is_not_covered_on_the_other():
    accounts = independent.read_accounts({"accounts": ACCOUNTS["accounts"][:2] + [
        {"id": 9, "name": "Other BTC", "currency": "BTC", "kind": "exchange", "exchange_id": 2, "sends_1099da": True},
        {"id": 8, "name": "Other USD", "currency": "USD", "kind": "exchange", "exchange_id": 2, "sends_1099da": True},
    ] + ACCOUNTS["accounts"][4:]})
    sales = [ledger_tx("Buy", "2026-02-01T15:00:00Z", 3, 4, "1.00000000", cost_basis_usd="1000.00"),
             ledger_tx("Transfer", "2026-03-01T15:00:00Z", 4, 9, "1.00000000"),
             ledger_tx("Sell", "2026-06-01T12:00:00Z", 9, 8, "0.50000000", gross_proceeds_usd="600.00")]
    assert _boxes(sales, accounts=accounts) == ["H"]


# Added in Claude's B1 fix run (claude-style-verdict-B1.md, gap 7).

def test_east_of_utc_a_buy_on_new_years_eve_in_utc_is_covered():
    # 16:00 UTC on Dec 31 2025 is 01:00 on Jan 1 2026 in Tokyo.
    buy = ledger_tx("Buy", "2025-12-31T16:00:00Z", 3, 4, "1.00000000", cost_basis_usd="1000.00")
    assert _boxes([buy, SELL_4], tax_timezone="Asia/Tokyo") == ["G"]
    assert _boxes([buy, SELL_4]) == ["H"]


def test_a_sell_across_a_lot_from_before_2026_and_one_after_splits_its_boxes():
    ledger = independent.replay([
        ledger_tx("Buy", "2025-11-01T15:00:00Z", 3, 4, "1.00000000", cost_basis_usd="1000.00"),
        ledger_tx("Buy", "2026-02-01T15:00:00Z", 3, 4, "1.00000000", cost_basis_usd="2000.00"),
        # FIFO: all of the 2025 lot (noncovered, H), then half the 2026 lot (covered, G);
        # the $3,000 shared by BTC, $2,000 and $1,000.
        ledger_tx("Sell", "2026-06-01T12:00:00Z", 4, 3, "1.50000000", gross_proceeds_usd="3000.00"),
    ])
    rows = [(r["box"], r["proceeds"], r["cost"]) for r in independent.year_figures(ledger, 2026)["form_8949"]]
    assert rows == [("H", "2000.00", "1000.00"), ("G", "1000.00", "1000.00")]


def test_a_sell_the_owner_says_no_broker_reported_is_box_i_with_the_switch_on():
    sell = dict(SELL_4, broker_reporting="none")
    bought = ledger_tx("Buy", "2026-02-01T15:00:00Z", 3, 4, "1.00000000", cost_basis_usd="1000.00")
    assert _boxes([bought, sell]) == ["I"]


def test_an_exchange_listed_without_its_switch_has_it_on():
    accounts = independent.read_accounts({"accounts": [
        {"id": 8, "name": "Kraken USD", "currency": "USD", "kind": "exchange", "exchange_id": 2},
        {"id": 9, "name": "Kraken BTC", "currency": "BTC", "kind": "exchange", "exchange_id": 2},
    ]})
    sales = [ledger_tx("Buy", "2026-02-01T15:00:00Z", 8, 9, "1.00000000", cost_basis_usd="1000.00"),
             ledger_tx("Sell", "2026-06-01T12:00:00Z", 9, 8, "0.50000000", gross_proceeds_usd="600.00")]
    assert accounts[9].on_1099da
    assert _boxes(sales, accounts=accounts) == ["G"]
