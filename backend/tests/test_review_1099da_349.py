"""
Ledger Review's sale_may_differ_from_1099da (2.0 spec 5.7, 5.13, 5.15;
card B4 #349). An exchange without the purchase dates of coins moved in
treats them as bought when they arrived, and sells the coins it dates first
(Instructions for Form 1099-DA, 2026, lot selection). BitcoinTX sells the
oldest coins first by the date each was first acquired. So a Sell from 2026
on an exchange that sends a 1099-DA can differ from that form when it took
coins moved into its account while that account held coins bought there
before they arrived: listed, as a reminder (nothing in the ledger is
wrong, and nothing would clear it). The account's lots are replayed from
the stored figures to know what it held just before each Sell; that replay
ends where the ledger's own lots are.
"""

from decimal import Decimal

from backend.models.transaction import BitcoinLot, Transaction
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
    """Kraken: bought there on 2026-02-01, then 2024's coins moved in from the wallet on 03-01, then a Sell:
    BitcoinTX sells 2024's coins first; the exchange, dating them 03-01, the coins bought there."""
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


def test_not_when_the_sells_broker_form_says_none(ledger):
    bought_then_older_coins_moved_in(ledger, broker_reporting="none")
    assert listed(ledger) == []


def test_not_when_the_coins_were_bought_there_after_the_move_in(ledger):
    """Dated by their arrival, the moved coins are the exchange's oldest too: both sell them first."""
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


def test_the_replay_ends_where_the_ledgers_lots_are(ledger):
    """Buys, deposits, sells, spends with their fees, moves out and in, and a consolidation, in one
    account: replayed from the stored figures, each lot holds what the engine left in it."""
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
        held_before, held_at_the_end = replayed_lots(db, KRAKEN_BTC, set())
    assert len(stored) == 4 and sum(stored.values()) > 0
    assert {lot.id: btc for lot, btc in held_at_the_end.items()} == stored
    assert held_before == {}
    assert sum(stored.values()) == Decimal("0.59980000")  # 0.2498 bought in February, the reward, the September buy
