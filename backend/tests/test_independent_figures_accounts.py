"""
2.0-B1 step 1 (docs/temp/2.0-accounts.md 5.15, 7.4 B1): the independent
calculation reads the ledger's accounts, an `accounts` list, else the six
fixed accounts and External. Each entry is checked once, there: a list
that can't be read one way only stops before any figure.
"""

import pytest

from backend.tests.conftest import independent_figures


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
