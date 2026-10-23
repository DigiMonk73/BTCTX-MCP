"""
The independent calculation's accounts (docs/temp/2.0-accounts.md 5.15;
5.1, 5.4): it reads the ledger's `accounts` list, else the six fixed
accounts and External, each entry checked once, there (a list that can't
be read one way only stops before any figure); an account id the ledger
doesn't have stops it; each bitcoin account keeps its own pile of lots (a
fee account has none); and a Buy lands in its own `to_account_id`.
"""

from zoneinfo import ZoneInfo

import pytest

from backend.tests.independent_calc import independent_figures, ledger_tx


independent = independent_figures()

FIXED = {
    1: ("Bank", "USD"),
    2: ("Wallet", "BTC"),
    3: ("Exchange USD", "USD"),
    4: ("Exchange BTC", "BTC"),
    5: ("BTC Fees", "BTC"),
    6: ("USD Fees", "USD"),
    99: ("External", None),
}
COLDCARD = {"id": 7, "name": "Coldcard", "kind": "wallet", "currency": "BTC"}


def test_read_accounts_defaults_to_the_six_fixed_and_external():
    found = independent.read_accounts({"transactions": []})
    assert {i: (a.name, a.currency) for i, a in found.items()} == FIXED


def test_read_accounts_takes_the_ledgers_own_list_and_external():
    data = {"accounts": [
        {"id": 2, "name": "Wallet", "kind": "wallet", "currency": "BTC"},
        COLDCARD,
        {"id": 8, "name": "Bank 2", "kind": "bank", "currency": "USD"},
    ], "transactions": []}
    found = independent.read_accounts(data)
    assert {i: (a.name, a.currency) for i, a in found.items()} == {
        2: ("Wallet", "BTC"), 7: ("Coldcard", "BTC"), 8: ("Bank 2", "USD"), 99: ("External", None)}


def test_read_accounts_btc_ids_are_the_bitcoin_accounts():
    found = independent.read_accounts({"transactions": []})
    assert sorted(i for i, a in found.items() if a.currency == "BTC") == [2, 4, 5]
    assert sorted(i for i, a in found.items() if a.holds_lots) == [2, 4]


def test_an_account_is_a_value_that_cant_be_changed():
    account = independent.read_accounts({})[2]
    with pytest.raises(AttributeError):
        account.name = "Cold storage"


def test_a_nickname_and_the_lists_notes_change_no_figure():
    # The owner's nickname is only what's shown; `hidden` and `why` are kept out.
    found = independent.read_accounts({"accounts": [dict(COLDCARD, name="My cold wallet", hidden=True, why="a test")]})
    assert found[7] == independent.Account(id=7, name="My cold wallet", kind="wallet", currency="BTC")


@pytest.mark.parametrize("entries, message", [
    ([COLDCARD, dict(COLDCARD, name="Again")], "The ledger's accounts list has account 7 twice."),
    ([{"id": 7, "name": "Coldcard", "currency": "BTC"}], "The ledger's accounts list: account 7 has no kind."),
    ([{"id": 7, "kind": "wallet"}], "The ledger's accounts list: account 7 has no name, currency."),
    ([dict(COLDCARD, sends_1099DA=True)],
     "The ledger's accounts list: account 7 has fields this check doesn't know: sends_1099DA."),
    ([dict(COLDCARD, id=None)], "An account in the ledger's accounts list has no whole-number id"),
    ([dict(COLDCARD, currency="USD")],
     "The ledger's accounts list: account 7 is a 'wallet' account in 'USD', which no account is."),
    ([dict(COLDCARD, kind="vault")],
     "The ledger's accounts list: account 7 is a 'vault' account in 'BTC', which no account is."),
    ([{"id": 98, "name": "Outside", "kind": "external", "currency": None}],
     "The ledger's accounts list: account 98: External is account 99, and only External is."),
    ([{"id": 9, "name": "Kraken BTC", "kind": "exchange", "currency": "BTC"}],
     "account 9: an exchange's account names its exchange (exchange_id), and no other does."),
    ([dict(COLDCARD, exchange_id=2)],
     "account 7: an exchange's account names its exchange (exchange_id), and no other does."),
    ([dict(COLDCARD, sends_1099da=False)], "account 7: sends_1099da is an exchange's switch, true or false."),
    ([{"id": 9, "name": "Kraken BTC", "kind": "exchange", "currency": "BTC", "exchange_id": 2}],
     "Exchange 2 in the ledger's accounts list needs one USD and one BTC account."),
    ([{"id": 8, "name": "Kraken USD", "kind": "exchange", "currency": "USD", "exchange_id": 2},
      {"id": 9, "name": "Kraken BTC", "kind": "exchange", "currency": "BTC", "exchange_id": 2, "sends_1099da": False}],
     "Exchange 2's two accounts disagree on its 1099-DA switch (sends_1099da)."),
])
def test_a_list_that_cant_be_read_one_way_stops(entries, message):
    with pytest.raises(ValueError) as found:
        independent.read_accounts({"accounts": entries})
    assert message in str(found.value)


# An account id the ledger doesn't have.

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


# One pile per bitcoin account.

WITH_A_FEE_ACCOUNT = {"accounts": [
    {"id": 2, "name": "Wallet", "currency": "BTC", "kind": "wallet"},
    {"id": 5, "name": "BTC Fees", "currency": "BTC", "kind": "fee"},
    {"id": 7, "name": "Coldcard", "currency": "BTC", "kind": "wallet"},
    {"id": 99, "name": "External", "currency": None, "kind": "external"},
]}


def test_the_fixed_accounts_have_their_kinds():
    kinds = {i: a.kind for i, a in independent.read_accounts({}).items()}
    assert kinds == {1: "bank", 2: "wallet", 3: "exchange", 4: "exchange", 5: "fee", 6: "fee", 99: "external"}


def test_by_default_the_piles_are_wallet_and_exchange_btc():
    assert sorted(independent.replay([]).lots) == [2, 4]


def test_each_bitcoin_account_of_the_ledger_keeps_its_own_pile():
    accounts = independent.read_accounts(WITH_A_FEE_ACCOUNT)
    ledger = independent.replay([
        ledger_tx("Deposit", "2024-01-15T10:00:00Z", 99, 7, "1.00000000", source="My BTC", cost_basis_usd="100.00"),
        ledger_tx("Transfer", "2024-03-01T10:00:00Z", 7, 2, "0.40000000"),
    ], accounts=accounts)
    assert sorted(ledger.lots) == [2, 7]  # no pile for the fee account
    held = {(h["account"], h["acquired"], h["quantity"], h["cost"])
            for h in independent.year_figures(ledger, 2024)["end_of_year_holdings"]}
    assert held == {("Coldcard", "2024-01-15T10:00:00+00:00", "0.60000000", "60.00"),
                    ("Wallet", "2024-01-15T10:00:00+00:00", "0.40000000", "40.00")}


def test_a_ledger_is_built_with_its_piles_or_not_at_all():
    ledger = independent.Ledger(accounts=independent.read_accounts(WITH_A_FEE_ACCOUNT), rounding=independent.ROUND_HALF_UP,
                                tax_zone=ZoneInfo("UTC"))
    assert sorted(ledger.lots) == [2, 7]
    with pytest.raises(TypeError):  # no accounts, so no piles: refused rather than a KeyError later
        independent.Ledger(rounding=independent.ROUND_HALF_UP)


# A Buy into its own account.

TWO_EXCHANGES = {"accounts": [
    {"id": 3, "name": "Exchange USD", "currency": "USD", "kind": "exchange", "exchange_id": 1, "sends_1099da": True},
    {"id": 4, "name": "Exchange BTC", "currency": "BTC", "kind": "exchange", "exchange_id": 1, "sends_1099da": True},
    {"id": 8, "name": "Kraken USD", "currency": "USD", "kind": "exchange", "exchange_id": 2, "sends_1099da": True},
    {"id": 9, "name": "Kraken BTC", "currency": "BTC", "kind": "exchange", "exchange_id": 2, "sends_1099da": True},
    {"id": 99, "name": "External", "currency": None, "kind": "external"},
]}


def test_a_buy_lands_in_its_own_account():
    ledger = independent.replay([
        ledger_tx("Buy", "2024-02-01T15:00:00Z", 8, 9, "1.00000000", cost_basis_usd="40000.00", fee_amount="10.00"),
    ], accounts=independent.read_accounts(TWO_EXCHANGES))
    assert ledger.lots[4] == []
    (lot,) = ledger.lots[9]
    assert (lot.quantity, lot.basis) == (1, 40010)


def test_a_buy_into_exchange_btc_still_lands_there():
    ledger = independent.replay([
        ledger_tx("Buy", "2024-02-01T15:00:00Z", 3, 4, "0.50000000", cost_basis_usd="20000.00"),
    ])
    assert [lot.quantity for lot in ledger.lots[4]] == [independent.Fraction(1, 2)]
