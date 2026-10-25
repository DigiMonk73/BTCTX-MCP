"""
B8's server half (2.0 spec 5.9, 5.13; card #356):

- the balances route gives each account's kind, exchange and hidden, from
  the account book, for the dashboard's balances by kind; the service it reads
  (and so the reference figures) stays as it was;
- a Ledger Review item, the hourly check's too, names its accounts (from
  then to, External never);
- renames through PUT /api/accounts/{id} {name}: an exchange's account
  renames its exchange and both of its accounts; ids 1 to 4 can be renamed
  and renamed back, the fee accounts never; 5.9's refusals word for word.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.database import seed_defaults
from backend.main import app
from backend.models.transaction import Transaction
from backend.services import calculation
from backend.services.account import account_book
from backend.services.review import row_item
from backend.tests.account_pairs import BOOK
from backend.tests.conftest import default_login, stub_prices_at

URL = "/api/accounts/"
EXTERNAL, COLD, CREDIT_UNION, KRAKEN_USD, KRAKEN_BTC = 99, 100, 101, 102, 103
ONE_LINE = "A name is 1 to 40 characters on one line."
EXCHANGE_LINE = "A name is 1 to 36 characters on one line."
FIRST_WALLET = "'Wallet' always means your first wallet in files (CSV, River, BitcoinTX 1.x): choose another name."
FEES_STAY = "The fee accounts keep their names and can't be hidden."


@pytest.fixture
def client(fresh_app, monkeypatch) -> TestClient:
    """Logged in on a database of its own with a second wallet, bank and
    exchange (ids 100 to 103, as account_pairs has them)."""
    stub_prices_at(monkeypatch, lambda _when: Decimal("50000"))
    c = TestClient(app)
    c.sessions = fresh_app
    assert c.post("/api/login", json=default_login()).status_code == 200
    for kind, name in (("wallet", "Cold Storage"), ("bank", "Credit Union"), ("exchange", "Kraken")):
        assert c.post(URL, json={"kind": kind, "name": name}).status_code == 201
    return c


def names(client) -> dict[int, str]:
    return {a["id"]: a["name"] for a in client.get(URL).json()}


def rename(client, account_id, name):
    return client.put(f"{URL}{account_id}", json={"name": name})


def save(client, **fields) -> int:
    r = client.post("/api/transactions", json={"fee_amount": "0", "fee_currency": "BTC", **fields})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def items(client, key) -> list[dict]:
    checks = {c["key"]: c for c in client.get("/api/review").json()["checks"]}
    return checks[key]["items"]


# The balances route
def test_the_balances_name_each_accounts_kind_exchange_and_hidden(client):
    assert client.put(f"{URL}{COLD}", json={"hidden": True}).status_code == 200
    rows = {r["account_id"]: r for r in client.get("/api/calculations/accounts/balances").json()}
    about = {i: (r["kind"], r["exchange_id"], r["exchange"], r["hidden"]) for i, r in rows.items()}
    assert about == {
        1: ("bank", None, None, False), 2: ("wallet", None, None, False),
        3: ("exchange", 1, "Exchange", False), 4: ("exchange", 1, "Exchange", False),
        5: ("fee", None, None, False), 6: ("fee", None, None, False),
        COLD: ("wallet", None, None, True), CREDIT_UNION: ("bank", None, None, False),
        KRAKEN_USD: ("exchange", 2, "Kraken", False), KRAKEN_BTC: ("exchange", 2, "Kraken", False)}
    assert {k for r in rows.values() for k in r} == {
        "account_id", "name", "currency", "balance", "kind", "exchange_id", "exchange", "hidden"}


def test_the_service_the_reference_figures_read_is_unchanged(client):
    with client.sessions() as db:
        rows = calculation.get_all_account_balances(db)
    assert {k for r in rows for k in r} == {"account_id", "name", "currency", "balance"}


def test_a_renamed_wallet_keeps_its_balance_row(client):
    save(client, type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=2,
         amount="0.5", source="MyBTC", cost_basis_usd="10000")
    assert rename(client, 2, "Coldcard").status_code == 200
    [row] = [r for r in client.get("/api/calculations/accounts/balances").json() if r["account_id"] == 2]
    assert (row["name"], row["kind"], row["balance"]) == ("Coldcard", "wallet", 0.5)


# Ledger Review's items
def test_an_item_names_its_accounts_but_never_external(client):
    save(client, type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=COLD,
         amount="0.25", source="MyBTC", cost_basis_usd="10000")
    assert rename(client, COLD, "Coldcard").status_code == 200
    [item] = [i for i in items(client, "original_date_missing") if i["amount"] == "0.25000000"]
    assert (item["accounts"], item["unit"]) == (["Coldcard"], "BTC")


def test_an_item_between_two_accounts_names_both_from_then_to(client):
    save(client, type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=1,
         amount="500", source="N/A", fee_currency="USD")
    tx = save(client, type="Transfer", timestamp="2024-01-03T12:00:00Z", from_account_id=1,
              to_account_id=CREDIT_UNION, amount="200", fee_currency="USD")
    with client.sessions() as db:
        item = row_item(db.get(Transaction, tx), timezone.utc, account_book(db), "", "")
    assert (item["accounts"], item["amount"], item["unit"]) == (["Bank", "Credit Union"], "200.00", "USD")


def test_a_consolidation_names_its_account_once_and_a_missing_one_as_the_book_does():
    when = datetime(2024, 1, 3, 12, tzinfo=timezone.utc)
    to_itself = Transaction(id=1, type="Transfer", timestamp=when, amount=Decimal("0.1"),
                            from_account_id=COLD, to_account_id=COLD)
    missing = Transaction(id=2, type="Transfer", timestamp=when, amount=Decimal("0.1"),
                          from_account_id=2, to_account_id=12345)
    assert row_item(to_itself, timezone.utc, BOOK, "", "")["accounts"] == ["Cold Storage"]
    assert row_item(missing, timezone.utc, BOOK, "", "")["accounts"] == ["Wallet", "account 12345 (missing)"]


def test_the_hourly_checks_items_name_their_accounts(client, monkeypatch):
    # Valued at a day's price the stored day doesn't have, as an older save could be
    stub_prices_at(monkeypatch, lambda when: Decimal("51000"), moment="day")
    save(client, type="Deposit", timestamp="2024-06-15T15:00:00Z", from_account_id=EXTERNAL, to_account_id=COLD,
         amount="0.01", source="Income")
    [item] = items(client, "day_priced_values")
    assert item["accounts"] == ["Cold Storage"]


# Renames
def test_a_wallet_renamed_keeps_its_id_and_takes_its_cleaned_name(client):
    r = rename(client, COLD, "  Ledger   Nano ")
    assert r.status_code == 200, r.text
    assert (r.json()["id"], r.json()["name"]) == (COLD, "Ledger Nano")
    assert names(client)[COLD] == "Ledger Nano"


def test_an_exchange_renamed_renames_its_exchange_and_both_accounts(client):
    r = rename(client, KRAKEN_BTC, "Kraken Pro")
    assert r.status_code == 200, r.text
    listed = {a["id"]: (a["name"], a["exchange"]) for a in client.get(URL).json()}
    assert (listed[KRAKEN_USD], listed[KRAKEN_BTC]) == (("Kraken Pro USD", "Kraken Pro"), ("Kraken Pro BTC", "Kraken Pro"))


def test_only_the_case_of_a_name_can_change(client):
    assert rename(client, COLD, "COLD STORAGE").status_code == 200
    assert rename(client, KRAKEN_USD, "kraken").status_code == 200
    assert (names(client)[COLD], names(client)[KRAKEN_BTC]) == ("COLD STORAGE", "kraken BTC")


def test_the_first_bank_wallet_and_exchange_are_renamed_and_renamed_back(client):
    for account_id, new, old in ((1, "Checking", "Bank"), (2, "Phone Wallet", "Wallet"), (3, "Coinbase", "Exchange")):
        assert rename(client, account_id, new).status_code == 200
        assert rename(client, account_id, old).status_code == 200
    assert [names(client)[i] for i in (1, 2, 3, 4)] == ["Bank", "Wallet", "Exchange USD", "Exchange BTC"]


def test_a_name_survives_a_restart(client):
    assert rename(client, 2, "Phone Wallet").status_code == 200
    assert rename(client, 4, "Coinbase").status_code == 200
    seed_defaults(bind=client.sessions.kw["bind"])
    assert [names(client)[i] for i in (2, 3, 4, 5)] == ["Phone Wallet", "Coinbase USD", "Coinbase BTC", "BTC Fees"]


def test_the_same_name_again_changes_nothing(client):
    assert rename(client, KRAKEN_USD, "Kraken").status_code == 200
    assert rename(client, 2, "Wallet").status_code == 200
    assert (names(client)[KRAKEN_USD], names(client)[2]) == ("Kraken USD", "Wallet")


def test_a_name_and_hidden_together(client):
    r = client.put(f"{URL}{COLD}", json={"name": "Old Coldcard", "hidden": True})
    assert r.status_code == 200, r.text
    assert (r.json()["name"], r.json()["hidden"]) == ("Old Coldcard", True)


@pytest.mark.parametrize("account_id, name, detail", [
    (COLD, "Wallet", FIRST_WALLET),
    (2, "Bank", "'Bank' always means your first bank in files (CSV, River, BitcoinTX 1.x): choose another name."),
    (2, "Exchange BTC", "'Exchange BTC' always means your first exchange in files (CSV, River, BitcoinTX 1.x): "
                        "choose another name."),
    (COLD, "kraken btc", "An account named 'kraken btc' already exists."),
    (CREDIT_UNION, "cold storage", "An account named 'cold storage' already exists."),
    (COLD, "BTC Fees", "An account named 'BTC Fees' already exists."),
    (COLD, "external", "External means everything outside BitcoinTX: choose another name."),
    (KRAKEN_USD, "External", "External means everything outside BitcoinTX: choose another name."),
    (KRAKEN_BTC, "Exchange", "An exchange named 'Exchange' already exists."),
    (KRAKEN_BTC, "Cold Storage", None),  # its accounts' names are free: "Cold Storage USD" and "... BTC"
    (COLD, "", ONE_LINE),
    (COLD, "x" * 41, ONE_LINE),
    (COLD, "Cold\nstorage", ONE_LINE),
    (COLD, "Cold​storage", ONE_LINE),
    (KRAKEN_USD, "y" * 37, EXCHANGE_LINE),
    (5, "Fees", FEES_STAY),
    (6, "USD Fees", FEES_STAY),
])
def test_a_rename_is_refused_in_the_specs_words(client, account_id, name, detail):
    before = names(client)
    r = rename(client, account_id, name)
    if detail is None:
        assert r.status_code == 200, r.text
        return
    assert (r.status_code, r.json()["detail"]) == (400, detail)
    assert names(client) == before


def test_another_exchange_cant_take_the_first_exchanges_names_once_free(client):
    assert rename(client, 3, "Coinbase").status_code == 200
    r = rename(client, KRAKEN_USD, "Exchange")
    assert (r.status_code, r.json()["detail"]) == (
        400, "'Exchange USD' always means your first exchange in files (CSV, River, BitcoinTX 1.x): "
             "choose another name.")


def test_an_exchange_account_whose_exchange_row_is_gone_is_renamed_alone(client):
    """No foreign key keeps an exchange's row (a hand-edited database): its
    account is renamed as a bank's or a wallet's is, never a 200 that renames nothing."""
    with client.sessions() as db:
        db.execute(text("DELETE FROM exchanges WHERE id = 2"))
        db.commit()
    r = rename(client, KRAKEN_USD, "Kraken dollars")
    assert r.status_code == 200, r.text
    assert (names(client)[KRAKEN_USD], names(client)[KRAKEN_BTC]) == ("Kraken dollars", "Kraken BTC")


@pytest.mark.parametrize("body", [{}, {"kind": "bank"}, {"currency": "USD"}, {"name": None, "hidden": None}])
def test_a_change_with_nothing_to_change_or_a_kind_is_422(client, body):
    assert client.put(f"{URL}{COLD}", json=body).status_code == 422


def test_a_rename_of_an_account_that_isnt_listed_is_404(client):
    assert rename(client, 9999, "Nope").status_code == 404
    assert rename(client, EXTERNAL, "Nope").status_code == 404
