"""
The independent calculation checks each transaction's accounts against
its type, as 2.0's rules do (docs/temp/2.0-accounts.md 5.5, in its
words), before any figure: a transaction it can't place stops it, never
skipped (5.15), and a fee account is named by none (5.1). A dollar
transfer between any two dollar accounts moves no bitcoin (5.6, #490).
"""

import pytest

from backend.tests.conftest import independent_figures, ledger_tx


independent = independent_figures()

TWO_EXCHANGES = independent.read_accounts({"accounts": [
    {"id": 1, "name": "Bank", "currency": "USD", "kind": "bank"},
    {"id": 2, "name": "Wallet", "currency": "BTC", "kind": "wallet"},
    {"id": 3, "name": "Exchange USD", "currency": "USD", "kind": "exchange", "exchange_id": 1},
    {"id": 4, "name": "Exchange BTC", "currency": "BTC", "kind": "exchange", "exchange_id": 1},
    {"id": 6, "name": "USD Fees", "currency": "USD", "kind": "fee"},
    {"id": 7, "name": "Credit union", "currency": "USD", "kind": "bank"},
    {"id": 8, "name": "Kraken USD", "currency": "USD", "kind": "exchange", "exchange_id": 2},
    {"id": 9, "name": "Kraken BTC", "currency": "BTC", "kind": "exchange", "exchange_id": 2},
]})
WHEN = "2024-01-02T15:00:00Z"


def test_dollar_transfers_between_any_dollar_accounts_make_no_figure():
    ledger = independent.replay([
        ledger_tx("Deposit", WHEN, 99, 7, "1000.00"),
        ledger_tx("Transfer", "2024-01-03T15:00:00Z", 7, 1, "500.00", fee_amount="5.00", fee_currency="USD"),
        ledger_tx("Transfer", "2024-01-04T15:00:00Z", 1, 8, "495.00", fee_amount="1.00", fee_currency="USD"),
    ], accounts=TWO_EXCHANGES)
    assert ledger.rows == [] and ledger.lots == {2: [], 4: [], 9: []}
    figures = independent.year_figures(ledger, 2024)
    assert figures["form_8949"] == [] and figures["end_of_year_holdings"] == []


@pytest.mark.parametrize("kind, source, destination, message", [
    ("Deposit", 1, 2, "A Deposit comes from External."),
    ("Deposit", 99, 99, "A Deposit goes into one of your accounts, not External."),
    ("Withdrawal", 99, 99, "A Withdrawal comes from one of your accounts, not External."),
    ("Withdrawal", 2, 4, "A Withdrawal goes to External."),
    ("Transfer", 2, 99, "A Transfer is between two of your accounts, not External."),
    ("Transfer", 4, 1, "A Transfer stays in one currency: bitcoin between bitcoin accounts, "
                       "dollars between dollar accounts."),
    ("Transfer", 1, 1, "A Transfer goes to another account: only a bitcoin account can send to itself "
                       "(a consolidation)."),
    ("Buy", 2, 4, "A Buy is paid from a bank or from an exchange's USD account."),
    ("Buy", 1, 2, "A Buy's bitcoin goes into an exchange's BTC account."),
    ("Buy", 8, 4, "A Buy paid from Kraken USD goes into Kraken BTC: an exchange's dollars buy only on that exchange."),
    ("Sell", 2, 3, "A Sell is from an exchange's BTC account."),
    ("Sell", 4, 1, "A Sell from Exchange BTC goes into Exchange USD."),
    ("Sell", 9, 3, "A Sell from Kraken BTC goes into Kraken USD."),
])
def test_a_transaction_its_type_doesnt_allow_stops_the_calculation(kind, source, destination, message):
    fine = ledger_tx("Deposit", WHEN, 99, 2, "1.00000000", source="My BTC", cost_basis_usd="100.00")
    with pytest.raises(ValueError) as found:
        independent.replay([fine, ledger_tx(kind, WHEN, source, destination, "0.10000000")], accounts=TWO_EXCHANGES)
    assert str(found.value) == f"Transaction 2: {message}"


def test_the_routes_2_0_adds_are_allowed():
    independent.replay([
        ledger_tx("Deposit", WHEN, 99, 7, "1000.00"),
        ledger_tx("Buy", WHEN, 7, 9, "0.10000000", cost_basis_usd="1000.00"),  # a bank pays any exchange
        ledger_tx("Transfer", WHEN, 9, 4, "0.05000000"),  # one exchange's BTC to another's
        ledger_tx("Sell", WHEN, 4, 3, "0.01000000", gross_proceeds_usd="100.00"),
        ledger_tx("Transfer", WHEN, 3, 8, "50.00", fee_currency="USD"),  # one exchange's dollars to another's
        ledger_tx("Transfer", WHEN, 4, 4, "0.00010000", fee_amount="0.00010000", fee_usd="1.00"),  # a consolidation
    ], accounts=TWO_EXCHANGES)


@pytest.mark.parametrize("kind, source, destination, named", [
    ("Deposit", 99, 5, "5 (BTC Fees)"),
    ("Withdrawal", 5, 99, "5 (BTC Fees)"),
    ("Withdrawal", 6, 99, "6 (USD Fees)"),
    ("Transfer", 2, 5, "5 (BTC Fees)"),
])
def test_a_fee_account_is_named_by_no_transaction(kind, source, destination, named):
    with pytest.raises(ValueError) as found:
        independent.replay([ledger_tx(kind, WHEN, source, destination, "0.10000000", purpose="Spent")])
    assert str(found.value) == f"Transaction 1 names account {named}, a fee account, which no transaction names."


def test_a_type_it_doesnt_know_stops_the_calculation():
    with pytest.raises(ValueError) as found:
        independent.replay([ledger_tx("Swap", WHEN, 2, 4, "0.10000000")])
    assert str(found.value) == "Transaction 1 is a 'Swap', which isn't one of Deposit, Withdrawal, Transfer, Buy, Sell."


@pytest.mark.parametrize("number, shown", [(None, "1"), (0, "0"), (42, "42")])
def test_a_transaction_is_named_by_its_id_else_its_place(number, shown):
    with pytest.raises(ValueError) as found:
        independent.replay([ledger_tx("Deposit", WHEN, 99, 12, "1.00000000", id=number)])
    assert str(found.value) == f"Transaction {shown} names account 12, which the ledger's accounts list doesn't have."
