"""2.0-B1 step 2 (5.15): an account id the ledger does not have stops the calculation. Written by Silas; read-only to the implementer."""

import pytest

from backend.tests.conftest import independent_figures


independent = independent_figures()

DEPOSIT = {"type": "Deposit", "timestamp": "2024-01-15T10:00:00Z", "from_account_id": 99, "to_account_id": 7,
           "amount": "1.00000000", "fee_amount": "0", "fee_currency": "BTC", "source": "My BTC",
           "cost_basis_usd": "100.00"}


def test_an_unknown_account_stops_the_calculation_by_position():
    with pytest.raises(ValueError) as found:
        independent.replay([dict(DEPOSIT)])
    assert str(found.value) == "Transaction 1 names account 7, which the ledger's accounts list doesn't have."


def test_an_unknown_account_names_the_transactions_id():
    tx = dict(DEPOSIT, id=42, to_account_id=2, from_account_id=12)
    with pytest.raises(ValueError) as found:
        independent.replay([tx])
    assert str(found.value) == "Transaction 42 names account 12, which the ledger's accounts list doesn't have."


def test_a_ledgers_own_accounts_are_known():
    accounts = independent.read_accounts({"accounts": [
        {"id": 2, "name": "Wallet", "kind": "wallet", "currency": "BTC"}]})
    ledger = independent.replay([dict(DEPOSIT, to_account_id=2)], accounts=accounts)
    assert sum(lot.quantity for lot in ledger.lots[2]) == 1
    with pytest.raises(ValueError, match="names account 4,"):
        independent.replay([dict(DEPOSIT, to_account_id=4)], accounts=accounts)
