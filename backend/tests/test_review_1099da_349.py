"""
Ledger Review's sale_may_differ_from_1099da (2.0 spec 5.7, 5.13, 5.15;
card B4 #349). An exchange without the purchase dates of coins moved in
counts them from their arrival and sells first the coins it counts as
oldest (Instructions for Form 1099-DA, 2026, lot selection). BitcoinTX
sells first the coins acquired first. So a Sell from 2026 on an exchange
that sends a 1099-DA can differ from that form: listed, as a reminder
(nothing in the ledger is wrong, and nothing would clear it), when the
exchange's order takes other coins bought there (whose basis its form
reports) than BitcoinTX's. Both orders are replayed over the account's lots
from the stored figures; replayed in the engine's order, every Sell takes
what its lot disposals say, and the lots end where the ledger's are.
"""

from decimal import Decimal

import pytest

from backend.models.transaction import BitcoinLot, LotDisposal, Transaction
from backend.services.review import replayed_lots
from backend.tests import two_exchanges
from backend.tests.two_exchanges import (
    BANK, EXCHANGE_BTC, EXCHANGE_USD, EXTERNAL, KRAKEN_BTC, KRAKEN_USD, WALLET,
)

ledger = two_exchanges.ledger  # the fixture: a fresh ledger with Kraken and Overseas

KEY = "sale_may_differ_from_1099da"


def listed(ledger) -> list[int]:
    check = next(c for c in ledger.review()["checks"] if c["key"] == KEY)
    return [item["id"] for item in check["items"]]


def old_coins_in_the_wallet(ledger) -> None:
    ledger.save("Deposit", "2024-01-10", EXTERNAL, WALLET, "1.00000000", source="MyBTC",
                cost_basis_usd="40000.00", acquired_at="2023-06-01")


def bought_then_older_coins_moved_in(ledger, sold="2026-06-01", amount="0.50000000", **sell) -> dict:
    """Kraken: bought there on 2026-02-01, then 2023's coins moved in from the wallet on 03-01, then a Sell:
    BitcoinTX sells 2023's coins first; the exchange, counting them from 03-01, the coins bought there."""
    old_coins_in_the_wallet(ledger)
    ledger.save("Buy", "2026-02-01", BANK, KRAKEN_BTC, "1.00000000", cost_basis_usd="80000.00")
    ledger.save("Transfer", "2026-03-01", WALLET, KRAKEN_BTC, "0.20000000")
    return ledger.save("Sell", sold, KRAKEN_BTC, KRAKEN_USD, amount, gross_proceeds_usd="40000.00", **sell)


def test_a_sale_of_coins_moved_in_while_coins_bought_there_were_held_is_listed(ledger):
    sale = bought_then_older_coins_moved_in(ledger, amount="0.10000000")
    assert listed(ledger) == [sale["id"]]
    review = ledger.review()
    check = next(c for c in review["checks"] if c["key"] == KEY)
    assert (check["kind"], check["count"], review["total"], review["reminders"]) == ("reminder", 1, 0, 1)
    assert check["explanation"] and "Form 1099-DA" in check["action"]
    item = check["items"][0]
    assert (item["type"], item["amount"], item["unit"]) == ("Sell", "0.10000000", "BTC")
    assert "Kraken BTC" in item["issue"]


def test_a_sale_taking_both_kinds_of_coins_is_listed(ledger):
    sale = bought_then_older_coins_moved_in(ledger, amount="0.50000000")  # 0.2 moved in, then 0.3 bought there
    assert listed(ledger) == [sale["id"]]


def test_a_later_sale_differs_too_once_the_orders_have_parted(ledger):
    """The first sale takes the moved coins here, the bought ones there; the second, the other way round."""
    old_coins_in_the_wallet(ledger)
    ledger.save("Buy", "2026-02-01", BANK, KRAKEN_BTC, "0.20000000", cost_basis_usd="16000.00")
    ledger.save("Transfer", "2026-03-01", WALLET, KRAKEN_BTC, "0.20000000")
    first = ledger.save("Sell", "2026-04-01", KRAKEN_BTC, KRAKEN_USD, "0.20000000", gross_proceeds_usd="18000.00")
    second = ledger.save("Sell", "2026-05-01", KRAKEN_BTC, KRAKEN_USD, "0.20000000", gross_proceeds_usd="19000.00")
    assert listed(ledger) == [first["id"], second["id"]]


def test_not_a_sale_of_everything_the_account_holds(ledger):
    """Both orders sell the same coins."""
    old_coins_in_the_wallet(ledger)
    ledger.save("Buy", "2026-02-01", BANK, KRAKEN_BTC, "0.30000000", cost_basis_usd="24000.00")
    ledger.save("Transfer", "2026-03-01", WALLET, KRAKEN_BTC, "0.20000000")
    ledger.save("Sell", "2026-06-01", KRAKEN_BTC, KRAKEN_USD, "0.50000000", gross_proceeds_usd="45000.00")
    assert listed(ledger) == []


def test_coins_deposited_with_an_earlier_date_count_as_moved_in(ledger):
    """Inherited coins, dated by the death: BitcoinTX sells them before coins bought there since; the
    exchange counts them from their deposit (as the reference ledger's 2026-09-02 Sell)."""
    ledger.save("Buy", "2026-03-20", BANK, KRAKEN_BTC, "0.25000000", cost_basis_usd="20000.00")
    ledger.save("Deposit", "2026-08-29", EXTERNAL, KRAKEN_BTC, "0.02000000", source="Inherited",
                acquired_at="2026-02-01", cost_basis_usd="1500.00")
    sale = ledger.save("Sell", "2026-09-02", KRAKEN_BTC, KRAKEN_USD, "0.01000000", gross_proceeds_usd="900.00")
    assert listed(ledger) == [sale["id"]]


def test_not_when_the_coins_bought_there_before_2026_have_no_basis_on_the_form(ledger):
    """Bought in 2025: noncovered, so the form reports no basis whichever coins it sold."""
    old_coins_in_the_wallet(ledger)
    ledger.save("Buy", "2025-12-01", BANK, KRAKEN_BTC, "1.00000000", cost_basis_usd="80000.00")
    ledger.save("Transfer", "2026-01-10", WALLET, KRAKEN_BTC, "0.20000000")
    ledger.save("Sell", "2026-06-01", KRAKEN_BTC, KRAKEN_USD, "0.10000000", gross_proceeds_usd="9000.00")
    assert listed(ledger) == []


@pytest.mark.parametrize("zone, listed_too", [("UTC", True), ("America/Chicago", False)])
def test_coins_bought_there_count_from_2026_in_the_tax_timezone(ledger, zone, listed_too):
    """03:00 UTC on 2026-01-01 is still 2025 in Chicago: bought then, the coins are noncovered there."""
    ledger.set_tax_timezone(zone)
    old_coins_in_the_wallet(ledger)
    ledger.save("Buy", "2026-01-01T03:00:00Z", BANK, KRAKEN_BTC, "1.00000000", cost_basis_usd="80000.00")
    ledger.save("Transfer", "2026-01-10", WALLET, KRAKEN_BTC, "0.20000000")
    sale = ledger.save("Sell", "2026-06-01", KRAKEN_BTC, KRAKEN_USD, "0.10000000", gross_proceeds_usd="9000.00")
    assert listed(ledger) == ([sale["id"]] if listed_too else [])


def test_not_when_the_exchange_sends_no_1099da(ledger):
    bought_then_older_coins_moved_in(ledger)
    ledger.switch("Kraken", False)
    assert listed(ledger) == []


def test_not_in_2025_whose_1099da_reports_no_basis(ledger):
    old_coins_in_the_wallet(ledger)
    ledger.save("Buy", "2025-02-01", BANK, KRAKEN_BTC, "1.00000000", cost_basis_usd="80000.00")
    ledger.save("Transfer", "2025-03-01", WALLET, KRAKEN_BTC, "0.20000000")
    ledger.save("Sell", "2025-06-01", KRAKEN_BTC, KRAKEN_USD, "0.10000000", gross_proceeds_usd="9000.00")
    assert listed(ledger) == []


@pytest.mark.parametrize("broker_form", ["none", "proceeds", "basis"])
def test_not_a_sale_whose_broker_form_the_owner_set(ledger, broker_form):
    bought_then_older_coins_moved_in(ledger, broker_reporting=broker_form)
    assert listed(ledger) == []


def test_not_when_the_coins_were_bought_there_after_the_move_in(ledger):
    """Counted from their arrival, the moved coins are the exchange's oldest too: both sell them first."""
    old_coins_in_the_wallet(ledger)
    ledger.save("Transfer", "2026-02-01", WALLET, KRAKEN_BTC, "0.20000000")
    ledger.save("Buy", "2026-03-01", BANK, KRAKEN_BTC, "1.00000000", cost_basis_usd="80000.00")
    ledger.save("Sell", "2026-06-01", KRAKEN_BTC, KRAKEN_USD, "0.10000000", gross_proceeds_usd="9000.00")
    assert listed(ledger) == []


def test_not_when_the_coins_it_took_were_no_older_than_those_bought_there(ledger):
    """A reward the exchange paid is dated when it arrived: both sell the coins bought before it first."""
    ledger.save("Buy", "2026-02-01", BANK, KRAKEN_BTC, "1.00000000", cost_basis_usd="80000.00")
    ledger.save("Deposit", "2026-03-01", EXTERNAL, KRAKEN_BTC, "0.20000000", source="Reward",
                cost_basis_usd="16000.00")
    ledger.save("Sell", "2026-06-01", KRAKEN_BTC, KRAKEN_USD, "1.10000000", gross_proceeds_usd="99000.00")
    assert listed(ledger) == []


def test_not_when_the_coins_bought_there_were_sold_before_the_move_in(ledger):
    old_coins_in_the_wallet(ledger)
    ledger.save("Buy", "2026-02-01", BANK, KRAKEN_BTC, "1.00000000", cost_basis_usd="80000.00")
    ledger.save("Sell", "2026-02-15", KRAKEN_BTC, KRAKEN_USD, "1.00000000", gross_proceeds_usd="85000.00")
    ledger.save("Transfer", "2026-03-01", WALLET, KRAKEN_BTC, "0.20000000")
    ledger.save("Sell", "2026-06-01", KRAKEN_BTC, KRAKEN_USD, "0.10000000", gross_proceeds_usd="9000.00")
    assert listed(ledger) == []


def test_not_when_the_coins_bought_there_were_moved_out_before_the_move_in(ledger):
    old_coins_in_the_wallet(ledger)
    ledger.save("Buy", "2026-02-01", BANK, KRAKEN_BTC, "1.00000000", cost_basis_usd="80000.00")
    ledger.save("Transfer", "2026-02-15", KRAKEN_BTC, EXCHANGE_BTC, "1.00000000")
    ledger.save("Transfer", "2026-03-01", WALLET, KRAKEN_BTC, "0.20000000")
    ledger.save("Sell", "2026-06-01", KRAKEN_BTC, KRAKEN_USD, "0.10000000", gross_proceeds_usd="9000.00")
    assert listed(ledger) == []


def test_the_first_exchange_too(ledger):
    old_coins_in_the_wallet(ledger)
    ledger.save("Buy", "2026-02-01", BANK, EXCHANGE_BTC, "1.00000000", cost_basis_usd="80000.00")
    ledger.save("Transfer", "2026-03-01", WALLET, EXCHANGE_BTC, "0.20000000")
    sale = ledger.save("Sell", "2026-06-01", EXCHANGE_BTC, EXCHANGE_USD, "0.10000000", gross_proceeds_usd="9000.00")
    assert listed(ledger) == [sale["id"]]


def test_the_replay_follows_the_engine(ledger):
    """Buys, deposits, sells, spends with their fees, moves out and in, and a consolidation, in one
    account: replayed in the engine's order from the stored figures, each Sell takes what its lot
    disposals say, and each lot ends holding what the engine left in it."""
    old_coins_in_the_wallet(ledger)
    ledger.save("Buy", "2025-02-01", BANK, KRAKEN_BTC, "1.00000000", cost_basis_usd="80000.00")
    ledger.save("Transfer", "2025-03-01", WALLET, KRAKEN_BTC, "0.40000000")
    ledger.save("Sell", "2025-04-01", KRAKEN_BTC, KRAKEN_USD, "0.30000000", gross_proceeds_usd="25000.00")
    ledger.save("Transfer", "2025-05-01", KRAKEN_BTC, WALLET, "0.25000000", fee_amount="0.00020000", fee_usd="9.00")
    ledger.save("Deposit", "2025-06-01", EXTERNAL, KRAKEN_BTC, "0.05000000", source="Reward",
                cost_basis_usd="3000.00")
    ledger.save("Transfer", "2025-07-01", KRAKEN_BTC, KRAKEN_BTC, "0.50000000", fee_amount="0.00010000",
                fee_usd="7.00")
    ledger.save("Withdrawal", "2025-08-01", KRAKEN_BTC, EXTERNAL, "0.20000000", purpose="Spent",
                proceeds_usd="18000.00", fee_amount="0.00010000", fee_currency="BTC", fee_usd="8.00")
    ledger.save("Buy", "2025-09-01", BANK, KRAKEN_BTC, "0.30000000", cost_basis_usd="30000.00")
    ledger.save("Sell", "2025-10-01", KRAKEN_BTC, KRAKEN_USD, "0.40000000", gross_proceeds_usd="40000.00")
    with ledger.Session() as db:
        stored = {lot.id: lot.remaining_btc for lot, _ in db.query(BitcoinLot, Transaction)
                  .join(Transaction, Transaction.id == BitcoinLot.created_txn_id)
                  .filter(Transaction.to_account_id == KRAKEN_BTC)}
        sells = {t.id: {d.lot_id: d.disposed_btc for d in db.query(LotDisposal).filter(LotDisposal.transaction_id == t.id)}
                 for t in db.query(Transaction).filter(Transaction.type == "Sell")}
        took, held_at_the_end = replayed_lots(db, KRAKEN_BTC, set(sells))
    assert {sale: {lot.id: btc for lot, btc in lots.items()} for sale, lots in took.items()} == sells
    assert len(stored) == 4 and {lot.id: btc for lot, btc in held_at_the_end.items()} == stored
    assert sum(stored.values()) == Decimal("0.59980000")  # 0.2498 bought in February, the reward, the September buy
