"""
B8's server half on the draft branch (the Grok trial, never merged): the
balances route's kind, exchange and hidden (B8-1, the dashboard's rows by
kind), Ledger Review's items naming their accounts and their unit from the
book (B8-5), and renames through PUT /api/accounts/{id} (B8-5r, spec 5.9).
"""

from datetime import timezone

import pytest
from fastapi.testclient import TestClient

from backend.database import seed_defaults
from backend.main import app
from backend.models.transaction import Transaction
from backend.services.review import _item
from backend.tests.conftest import default_login


@pytest.fixture
def client(fresh_app) -> TestClient:
    c = TestClient(app)
    c.sessions = fresh_app  # the test's own database
    assert c.post("/api/login", json=default_login()).status_code == 200
    return c


def add(client, kind, name):
    r = client.post("/api/accounts/", json={"kind": kind, "name": name})
    assert r.status_code == 201, r.text
    return {a["currency"]: a["id"] for a in r.json()} if kind == "exchange" else r.json()[0]["id"]


def rename(client, account_id, name):
    return client.put(f"/api/accounts/{account_id}", json={"name": name})


def names(client):
    return {a["id"]: a["name"] for a in client.get("/api/accounts/").json()}


def create(client, **fields):
    r = client.post("/api/transactions", json={"fee_amount": "0", "fee_currency": "BTC", **fields})
    assert r.status_code == 200, r.text
    return r.json()["id"]


# --- B8-1: the balances route ---

def test_balances_carry_kind_exchange_and_hidden(client):
    kraken = add(client, "exchange", "Kraken")
    wallet = add(client, "wallet", "Cold Storage")
    client.put(f"/api/accounts/{wallet}", json={"hidden": True})
    rows = {r["account_id"]: r for r in client.get("/api/calculations/accounts/balances").json()}
    assert {k: rows[4][k] for k in ("kind", "exchange_id", "exchange", "hidden")} == \
        {"kind": "exchange", "exchange_id": 1, "exchange": "Exchange", "hidden": False}
    assert {k: rows[kraken["USD"]][k] for k in ("name", "kind", "exchange_id", "exchange")} == \
        {"name": "Kraken USD", "kind": "exchange", "exchange_id": 2, "exchange": "Kraken"}
    assert (rows[wallet]["kind"], rows[wallet]["exchange"], rows[wallet]["hidden"]) == ("wallet", None, True)
    assert (rows[5]["kind"], rows[6]["kind"], rows[1]["kind"]) == ("fee", "fee", "bank")


# --- B8-5: Ledger Review's items ---

def review_items(client, key):
    checks = {c["key"]: c for c in client.get("/api/review").json()["checks"]}
    return checks[key]["items"]


def test_an_item_names_its_accounts_by_nickname(client):
    # A My BTC deposit with no date originally acquired is a reminder that names its wallet.
    # (Only into 2: the checks read BTC_ACCOUNTS, an added wallet's wait for B3 on this branch.)
    assert rename(client, 2, "Phone Wallet").status_code == 200
    create(client, type="Deposit", timestamp="2024-01-03T12:00:00Z", from_account_id=99,
           to_account_id=2, amount="0.25", source="MyBTC", cost_basis_usd="10000")
    [item] = review_items(client, "original_date_missing")
    assert item["accounts"] == ["Phone Wallet"]  # External is never named
    assert (item["amount"], item["unit"]) == ("0.25000000", "BTC")


def test_a_dollar_move_into_an_added_bank_is_in_dollars(client):
    bank = add(client, "bank", "Credit Union")
    create(client, type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=99, to_account_id=1,
           amount="500", source="N/A", fee_currency="USD")
    tx = create(client, type="Transfer", timestamp="2024-01-03T12:00:00Z", from_account_id=1,
                to_account_id=bank, amount="200", fee_currency="USD")
    with client.sessions() as db:
        item = _item(db.get(Transaction, tx), timezone.utc, "", "")
    assert (item["amount"], item["unit"], item["accounts"]) == ("200.00", "USD", ["Bank", "Credit Union"])


# --- B8-5r: renames ---

def test_a_wallet_renamed_keeps_its_id_and_shows_its_nickname(client):
    wallet = add(client, "wallet", "Cold Storage")
    r = rename(client, wallet, "  Ledger   Nano ")
    assert r.status_code == 200, r.text
    assert [(a["id"], a["name"]) for a in r.json()] == [(wallet, "Ledger Nano")]


def test_an_exchange_renamed_renames_both_its_accounts(client):
    kraken = add(client, "exchange", "Kraken")
    r = rename(client, kraken["BTC"], "Kraken Pro")
    assert r.status_code == 200, r.text
    assert sorted((a["name"], a["exchange"]) for a in r.json()) == \
        [("Kraken Pro BTC", "Kraken Pro"), ("Kraken Pro USD", "Kraken Pro")]


def test_ids_1_to_4_are_renamed_and_renamed_back(client):
    for account_id, new, old in ((2, "Wallet 2", "Wallet"), (1, "Checking", "Bank"), (3, "Coinbase", "Exchange")):
        assert rename(client, account_id, new).status_code == 200
        assert rename(client, account_id, old).status_code == 200
    assert names(client)[2] == "Wallet"
    assert (names(client)[3], names(client)[4]) == ("Exchange USD", "Exchange BTC")


def test_a_nickname_survives_a_restart(client):
    assert rename(client, 2, "Phone Wallet").status_code == 200
    seed_defaults(bind=client.sessions.kw["bind"])
    assert names(client)[2] == "Phone Wallet"
    assert names(client)[5] == "BTC Fees"


@pytest.mark.parametrize("account_id, name, detail", [
    (100, "Wallet", "'Wallet' always means your first wallet in files (CSV, River, BitcoinTX 1.x): "
                    "choose another name."),
    (2, "Bank", "'Bank' always means your first bank in files (CSV, River, BitcoinTX 1.x): choose another name."),
    (100, "Kraken BTC", "An account named 'Kraken BTC' already exists."),
    (100, "external", "External means everything outside BitcoinTX: choose another name."),
    (100, "", "A name is 1 to 40 characters on one line."),
    (5, "Fees", "The fee accounts keep their names and can't be hidden."),
])
def test_a_rename_is_refused_in_the_specs_words(client, account_id, name, detail):
    add(client, "wallet", "Cold Storage")  # 100
    add(client, "exchange", "Kraken")
    r = rename(client, account_id, name)
    assert (r.status_code, r.json()["detail"]) == (400, detail)


def test_the_same_name_again_changes_nothing(client):
    kraken = add(client, "exchange", "Kraken")
    assert rename(client, kraken["USD"], "Kraken").status_code == 200
    assert rename(client, 2, "Wallet").status_code == 200
