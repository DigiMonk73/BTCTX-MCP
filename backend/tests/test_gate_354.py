"""
The gate (2.0 spec 5.10; card B7a #354): a save takes any of your accounts
(a bank, a wallet or an exchange's account the account API made, hidden ones
too) and External, through the API and through a CSV, as it took 1.x's
four. The fee accounts stay the ledger's own (#266), and an id with no
account is still refused. These are the first saves into new accounts that
no test opens a gate for.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.csv_import import CSV_COLUMNS
from backend.tests.account_pairs import (
    BTC_FEES, COLD, CREDIT_UNION, EXTERNAL, KRAKEN_BTC, KRAKEN_USD, USD_FEES, add_them)
from backend.tests.conftest import default_login

HEADER = ",".join(CSV_COLUMNS[:11])
YOURS = "Bank, Wallet, Exchange USD, Exchange BTC, Cold Storage, Credit Union, Kraken USD, Kraken BTC"

# A second bank funds a second exchange, whose coins go to a second wallet
ROWS = [
    {"type": "Deposit", "timestamp": "2026-01-05T12:00:00Z", "from_account_id": EXTERNAL,
     "to_account_id": CREDIT_UNION, "amount": "20000", "fee_amount": "0", "fee_currency": "USD", "source": "N/A"},
    {"type": "Transfer", "timestamp": "2026-01-06T12:00:00Z", "from_account_id": CREDIT_UNION,
     "to_account_id": KRAKEN_USD, "amount": "15000", "fee_amount": "0", "fee_currency": "USD"},
    {"type": "Buy", "timestamp": "2026-01-07T12:00:00Z", "from_account_id": KRAKEN_USD,
     "to_account_id": KRAKEN_BTC, "amount": "0.1", "cost_basis_usd": "10000", "fee_amount": "10",
     "fee_currency": "USD"},
    {"type": "Transfer", "timestamp": "2026-01-08T12:00:00Z", "from_account_id": KRAKEN_BTC,
     "to_account_id": COLD, "amount": "0.05", "fee_amount": "0.0001", "fee_currency": "BTC", "fee_usd": "10.00"},
    {"type": "Sell", "timestamp": "2026-01-09T12:00:00Z", "from_account_id": KRAKEN_BTC,
     "to_account_id": KRAKEN_USD, "amount": "0.05", "gross_proceeds_usd": "5500", "fee_amount": "5",
     "fee_currency": "USD"},
]


@pytest.fixture
def client(fresh_app) -> TestClient:
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    add_them(client)
    return client


def balances(client: TestClient) -> dict[int, Decimal]:
    return {b["account_id"]: Decimal(str(b["balance"])) for b in client.get("/api/calculations/accounts/balances").json()}


def csv(*rows: str) -> dict:
    return {"file": ("rows.csv", ("\n".join([HEADER, *rows]) + "\n").encode(), "text/csv")}


def test_the_first_saves_into_new_accounts_through_the_api(client):
    for row in ROWS:
        r = client.post("/api/transactions", json=row)
        assert r.status_code == 200, (row, r.text)
    held = balances(client)
    assert (held[CREDIT_UNION], held[KRAKEN_USD], held[KRAKEN_BTC], held[COLD]) == (
        Decimal("5000"), Decimal("10485"), Decimal("0"), Decimal("0.0499"))
    [sale] = [t for t in client.get("/api/transactions").json() if t["type"] == "Sell"]
    # The Sell took what the Buy left after the move: 0.05 BTC of 0.1 that cost $10,010
    assert (Decimal(sale["cost_basis_usd"]), Decimal(sale["realized_gain_usd"])) == (Decimal("5005.00"),
                                                                                      Decimal("490.00"))


def test_an_edit_moves_a_row_into_a_new_account(client):
    first = client.post("/api/transactions", json=ROWS[0]).json()
    r = client.put(f"/api/transactions/{first['id']}", json={"to_account_id": 1})
    assert r.status_code == 200, r.text
    r = client.put(f"/api/transactions/{first['id']}", json={"to_account_id": CREDIT_UNION})
    assert r.status_code == 200, r.text
    assert balances(client)[CREDIT_UNION] == Decimal("20000")


def test_a_hidden_account_still_takes_a_row(client):
    assert client.put(f"/api/accounts/{COLD}", json={"hidden": True}).status_code == 200
    r = client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2026-02-01T12:00:00Z", "from_account_id": EXTERNAL, "to_account_id": COLD,
        "amount": "0.01", "fee_amount": "0", "fee_currency": "BTC", "source": "MyBTC", "cost_basis_usd": "900"})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("account", [BTC_FEES, USD_FEES, 98, 777])
def test_a_fee_account_or_an_id_with_no_account_is_still_refused(client, account):
    for side in ("from_account_id", "to_account_id"):
        row = {**ROWS[0], side: account} if side == "to_account_id" else {
            **ROWS[0], "type": "Withdrawal", "from_account_id": account, "to_account_id": EXTERNAL}
        r = client.post("/api/transactions", json=row)
        assert (r.status_code, r.json()["detail"]) == (422, f"Unknown account id {account}."), side


def test_a_csv_names_the_new_accounts(client):
    rows = ["2026-01-05T12:00:00Z,Deposit,20000,External,credit union,,,0,USD,,",
            "2026-01-07T12:00:00Z,Buy,0.1,Credit Union,Kraken BTC,10000,,10,USD,,",
            "2026-01-08T12:00:00Z,Transfer,0.05,Kraken BTC,Cold Storage,,,0.0001,BTC,,"]
    answer = client.post("/api/import/preview", files=csv(*rows)).json()
    assert answer["errors"] == [] and answer["valid_rows"] == 3, answer
    assert [(t["from_account"], t["to_account"]) for t in answer["transactions"]] == [
        ("External", "Credit Union"), ("Credit Union", "Kraken BTC"), ("Kraken BTC", "Cold Storage")]
    r = client.post("/api/import/execute", files=csv(*rows))
    assert r.status_code == 200, r.text
    held = balances(client)
    assert (held[CREDIT_UNION], held[KRAKEN_BTC], held[COLD]) == (Decimal("9990"), Decimal("0.05"),
                                                                   Decimal("0.0499"))


@pytest.mark.parametrize("name", ["BTC Fees", "usd fees", "Nowhere"])
def test_a_csv_naming_a_fee_account_or_an_unknown_one_is_refused(client, name):
    answer = client.post("/api/import/preview", files=csv(f"2026-01-05T12:00:00Z,Deposit,1,External,{name},,,0,,,")
                         ).json()
    assert [(e["column"], e["message"]) for e in answer["errors"]] == [
        ("to_account", f"Invalid account '{name}'. Must be one of your accounts ({YOURS}) or External.")]
