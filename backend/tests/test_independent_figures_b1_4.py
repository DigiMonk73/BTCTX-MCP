"""2.0-B1 step 4 (5.15): a Buy goes into its own to_account_id, not always Exchange BTC (4). Written by Silas; read-only to the implementer."""

from backend.tests.conftest import independent_figures, ledger_tx


independent = independent_figures()

ACCOUNTS = {"accounts": [
    {"id": 3, "name": "Exchange USD", "currency": "USD", "kind": "exchange", "exchange_id": 1, "sends_1099da": True},
    {"id": 4, "name": "Exchange BTC", "currency": "BTC", "kind": "exchange", "exchange_id": 1, "sends_1099da": True},
    {"id": 8, "name": "Kraken USD", "currency": "USD", "kind": "exchange", "exchange_id": 2, "sends_1099da": True},
    {"id": 9, "name": "Kraken BTC", "currency": "BTC", "kind": "exchange", "exchange_id": 2, "sends_1099da": True},
    {"id": 99, "name": "External", "currency": None, "kind": "external"},
]}


def test_a_buy_lands_in_its_own_account():
    ledger = independent.replay([
        ledger_tx("Buy", "2024-02-01T15:00:00Z", 8, 9, "1.00000000", cost_basis_usd="40000.00", fee_amount="10.00"),
    ], accounts=independent.read_accounts(ACCOUNTS))
    assert ledger.lots[4] == []
    (lot,) = ledger.lots[9]
    assert (lot.quantity, lot.basis) == (1, 40010)


def test_a_buy_into_exchange_btc_still_lands_there():
    ledger = independent.replay([
        ledger_tx("Buy", "2024-02-01T15:00:00Z", 3, 4, "0.50000000", cost_basis_usd="20000.00"),
    ])
    assert [lot.quantity for lot in ledger.lots[4]] == [independent.Fraction(1, 2)]
