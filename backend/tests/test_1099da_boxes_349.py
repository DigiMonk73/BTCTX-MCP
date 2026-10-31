"""
Form 8949's boxes per exchange (2.0 spec 5.7 and 5.15's box cases; card B4
#349). A Sell is on a Form 1099-DA when its exchange's "This exchange sends
me a Form 1099-DA" is on; its basis is reported (covered) only for a lot
bought into that same account from 2026 in the tax timezone. Coins moved
from one exchange to another arrive noncovered (Treas. Reg.
§1.6045-1(a)(15)(i)(J); no transfer statement is required between brokers),
so their Sell is H/K. With the switch off, an exchange's Sells are I/L, as a
self-custody spend's are: the gain is the same either way. Each case is
also worked out by the independent calculation, which must agree.
"""

import pytest

from backend.tests import two_exchanges
from backend.tests.two_exchanges import (
    BANK, EXCHANGE_BTC, EXCHANGE_USD, KRAKEN_BTC, KRAKEN_USD, OVERSEAS_BTC, OVERSEAS_USD, WALLET,
)

ledger = two_exchanges.ledger  # the fixture: a fresh ledger with Kraken and Overseas


def agrees(ledger, year: int) -> list[str]:
    """The year's boxes, once the app's rows and the second calculation's agree."""
    assert ledger.form_8949(year) == ledger.independent_form_8949(year)
    return ledger.boxes(year)


@pytest.mark.parametrize("bought, moved, box", [
    ("2026-02-01", "2026-03-01", "H"),   # short-term: proceeds only
    ("2024-03-01", "2025-01-10", "K"),   # long-term
])
def test_bought_on_one_exchange_moved_to_another_and_sold_there(ledger, bought, moved, box):
    ledger.save("Buy", bought, BANK, EXCHANGE_BTC, "1.00000000", cost_basis_usd="50000.00")
    ledger.save("Transfer", moved, EXCHANGE_BTC, KRAKEN_BTC, "1.00000000")
    ledger.save("Sell", "2026-06-01", KRAKEN_BTC, KRAKEN_USD, "0.50000000", gross_proceeds_usd="40000.00")
    assert agrees(ledger, 2026) == [box]


def test_a_buy_on_the_second_exchange_paid_from_a_bank_and_sold_there_in_2026_is_covered(ledger):
    ledger.save("Buy", "2026-02-01", BANK, KRAKEN_BTC, "1.00000000", cost_basis_usd="50000.00")
    ledger.save("Sell", "2026-06-01", KRAKEN_BTC, KRAKEN_USD, "0.50000000", gross_proceeds_usd="40000.00")
    assert agrees(ledger, 2026) == ["G"]


def test_a_buy_with_its_own_exchanges_dollars_is_covered_too(ledger):
    ledger.save("Deposit", "2026-01-10", 99, KRAKEN_USD, "60000.00", fee_currency="USD", source="N/A")
    ledger.save("Buy", "2026-02-01", KRAKEN_USD, KRAKEN_BTC, "1.00000000", cost_basis_usd="50000.00")
    ledger.save("Sell", "2026-06-01", KRAKEN_BTC, KRAKEN_USD, "0.50000000", gross_proceeds_usd="40000.00")
    assert agrees(ledger, 2026) == ["G"]


@pytest.mark.parametrize("zone, box", [("UTC", "G"), ("America/Chicago", "H")])
def test_bought_there_counts_from_2026_in_the_tax_timezone(ledger, zone, box):
    """03:00 UTC on 2026-01-01 is still 2025 in Chicago: bought then, the coins are noncovered there."""
    ledger.set_tax_timezone(zone)
    ledger.save("Buy", "2026-01-01T03:00:00Z", BANK, KRAKEN_BTC, "1.00000000", cost_basis_usd="50000.00")
    ledger.save("Sell", "2026-06-01", KRAKEN_BTC, KRAKEN_USD, "0.50000000", gross_proceeds_usd="40000.00")
    assert agrees(ledger, 2026) == [box]


def test_a_sell_on_the_second_exchange_in_2025_reports_proceeds_only(ledger):
    ledger.save("Buy", "2024-01-10", BANK, KRAKEN_BTC, "1.00000000", cost_basis_usd="40000.00")
    ledger.save("Buy", "2025-02-01", BANK, KRAKEN_BTC, "1.00000000", cost_basis_usd="90000.00")
    # FIFO: the 2024 lot (long-term, K), then half the 2025 one (short-term, H)
    ledger.save("Sell", "2025-03-01", KRAKEN_BTC, KRAKEN_USD, "1.50000000", gross_proceeds_usd="135000.00")
    assert agrees(ledger, 2025) == ["H", "K"]


def test_with_its_switch_off_an_exchanges_sells_are_on_no_1099da_in_2025_and_2026(ledger):
    ledger.switch("Overseas", False)
    ledger.save("Buy", "2024-01-10", BANK, OVERSEAS_BTC, "1.00000000", cost_basis_usd="40000.00")
    ledger.save("Buy", "2026-02-01", BANK, OVERSEAS_BTC, "1.00000000", cost_basis_usd="80000.00")
    ledger.save("Sell", "2025-03-01", OVERSEAS_BTC, OVERSEAS_USD, "0.50000000", gross_proceeds_usd="45000.00")
    # The rest of the 2024 lot (long-term), then half the one bought there in 2026
    ledger.save("Sell", "2026-06-01", OVERSEAS_BTC, OVERSEAS_USD, "1.00000000", gross_proceeds_usd="90000.00")
    assert (agrees(ledger, 2025), agrees(ledger, 2026)) == (["L"], ["I", "L"])
    gains = [row[3:] for row in ledger.form_8949(2026)]
    ledger.switch("Overseas", True)
    assert (agrees(ledger, 2025), agrees(ledger, 2026)) == (["K"], ["G", "K"])
    assert [row[3:] for row in ledger.form_8949(2026)] == gains  # the same figures, in other boxes


def test_a_sells_own_broker_form_still_wins_on_an_exchange_with_its_switch_off(ledger):
    ledger.switch("Overseas", False)
    ledger.save("Buy", "2026-02-01", BANK, OVERSEAS_BTC, "1.00000000", cost_basis_usd="50000.00")
    ledger.save("Sell", "2026-06-01", OVERSEAS_BTC, OVERSEAS_USD, "0.50000000", gross_proceeds_usd="40000.00",
                broker_reporting="basis")
    assert agrees(ledger, 2026) == ["G"]


def test_a_network_fee_leaving_the_second_exchange_is_on_no_1099da(ledger):
    ledger.save("Buy", "2026-02-01", BANK, KRAKEN_BTC, "1.00000000", cost_basis_usd="50000.00")
    ledger.save("Transfer", "2026-03-01", KRAKEN_BTC, WALLET, "0.50000000", fee_amount="0.00010000",
                fee_usd="6.00")
    assert agrees(ledger, 2026) == ["I"]


def test_unchanged_a_move_within_the_first_exchange_then_a_sale_is_covered(ledger):
    ledger.save("Buy", "2026-02-01", BANK, EXCHANGE_BTC, "1.00000000", cost_basis_usd="50000.00")
    # A consolidation (#159) moves no lot: only its fee leaves
    ledger.save("Transfer", "2026-03-01", EXCHANGE_BTC, EXCHANGE_BTC, "1.00000000", fee_amount="0.00010000",
                fee_usd="6.00")
    ledger.save("Sell", "2026-06-01", EXCHANGE_BTC, EXCHANGE_USD, "0.50000000", gross_proceeds_usd="40000.00")
    assert agrees(ledger, 2026) == ["G", "I"]
