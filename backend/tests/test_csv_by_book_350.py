"""
The CSV import and export by the book (spec 5.11; card B5a #350). A file
names an account by a reserved name (1.x's names, always the first bank,
wallet and exchange) or by its name now, ignoring case; any other name is
refused, saying which names the file may use. A hidden account is still
yours: warned about, never refused. The preview and the export write each
account's name as it is now, and a blank fee currency is the one the save
fills in (#303). A file names any of your accounts and External (B7a's
gate, #354), so the round trip keeps the added accounts.
"""

import csv as csv_module
import io
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.transaction import Transaction
from backend.services.csv_import import CSV_COLUMNS, parse_csv_file
from backend.tests.account_pairs import COINBASE, add_them, rename
from backend.tests.conftest import default_login

HEADER = ",".join(CSV_COLUMNS[:11])
UNKNOWN = "Invalid account '{}'. Must be one of your accounts ({}) or External."
FIRST = "Bank, Wallet, Exchange USD, Exchange BTC"


def csv(*rows: str) -> bytes:
    return ("\n".join([HEADER, *rows]) + "\n").encode()


def errors(result) -> list:
    return [(e.row_number, e.column, e.message) for e in result.errors]


def warnings(result) -> list:
    return [(w.column, w.message) for w in result.warnings]


@pytest.fixture
def client(fresh_app) -> TestClient:
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    return client


def preview(client: TestClient, *rows: str) -> dict:
    r = client.post("/api/import/preview", files={"file": ("rows.csv", csv(*rows), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


def preview_errors(answer: dict) -> list:
    return [(e["column"], e["message"]) for e in answer["errors"]]


def test_a_1x_file_names_the_reserved_names_in_any_case():
    result = parse_csv_file(csv("2024-01-05T10:00:00Z,Buy,0.01,bank,EXCHANGE btc,500,,,,,",
                                "2024-01-06T10:00:00Z,Transfer,0.01,Exchange BTC,wallet,,,,,,"))
    assert errors(result) == []
    assert [(t["from_account_id"], t["to_account_id"]) for t in result.transactions] == [(1, 4), (4, 2)]
    assert [(p.from_account, p.to_account) for p in result.previews] == [
        ("Bank", "Exchange BTC"), ("Exchange BTC", "Wallet")]


def test_an_unknown_name_is_refused_with_the_names_a_file_may_use():
    result = parse_csv_file(csv("2024-01-05T10:00:00Z,Deposit,0.1,External,Coldcard,100,,,,MyBTC,"))
    assert errors(result) == [(2, "to_account", UNKNOWN.format("Coldcard", FIRST))]


def test_a_fee_account_stays_refused():
    result = parse_csv_file(csv("2024-01-05T10:00:00Z,Withdrawal,0.1,BTC Fees,External,,,,,,Spent"))
    assert errors(result) == [(2, "from_account", UNKNOWN.format("BTC Fees", FIRST))]


def test_an_account_is_named_by_its_name_now_or_its_reserved_one(fresh_app, client):
    """Exchange 1 called Coinbase: a file names it either way, in any case,
    and the preview writes its name now."""
    rename(fresh_app, COINBASE)
    answer = preview(client, "2024-01-05T10:00:00Z,Sell,0.1,coinbase btc,Coinbase USD,,900,,,,",
                     "2024-01-06T10:00:00Z,Sell,0.1,Exchange BTC,exchange usd,,900,,,,")
    assert answer["errors"] == []
    assert [(t["from_account"], t["to_account"]) for t in answer["transactions"]] == [
        ("Coinbase BTC", "Coinbase USD"), ("Coinbase BTC", "Coinbase USD")]


def test_the_refusal_says_the_accounts_names_now(fresh_app, client):
    rename(fresh_app, COINBASE)
    answer = preview(client, "2024-01-05T10:00:00Z,Deposit,0.1,External,Kraken BTC,100,,,,MyBTC,")
    assert preview_errors(answer) == [
        ("to_account", UNKNOWN.format("Kraken BTC", "Bank, Wallet, Coinbase USD, Coinbase BTC"))]


def test_an_added_account_is_read_by_its_name(client):
    add_them(client)
    answer = preview(client, "2024-01-05T10:00:00Z,Deposit,0.1,External,cold storage,100,,,,MyBTC,",
                     "2024-01-06T10:00:00Z,Deposit,0.1,External,Nowhere,100,,,,MyBTC,")
    assert [(t["to_account"]) for t in answer["transactions"]] == ["Cold Storage"]
    assert preview_errors(answer) == [("to_account", UNKNOWN.format(
        "Nowhere", f"{FIRST}, Cold Storage, Credit Union, Kraken USD, Kraken BTC"))]


def test_a_hidden_account_is_warned_about_never_refused(client):
    assert client.put("/api/accounts/2", json={"hidden": True}).status_code == 200
    assert client.put("/api/accounts/4", json={"hidden": True}).status_code == 200  # the exchange: both
    answer = preview(client, "2024-01-05T10:00:00Z,Deposit,0.1,External,Wallet,100,,,,MyBTC,",
                     "2024-01-06T10:00:00Z,Transfer,0.05,Wallet,Wallet,,,0.0001,BTC,,",
                     "2024-01-07T10:00:00Z,Sell,0.01,Exchange BTC,Exchange USD,,500,,,,")
    assert answer["errors"] == [] and answer["can_import"]
    assert [(w["row_number"], w["column"], w["message"]) for w in answer["warnings"]] == [
        (2, "to_account", "Wallet is hidden in Settings."),
        (3, "from_account", "Wallet is hidden in Settings."),
        (4, "from_account", "Exchange BTC is hidden in Settings."),
        (4, "to_account", "Exchange USD is hidden in Settings."),
    ]


@pytest.mark.parametrize("row, currency", [
    ("2024-01-05T10:00:00Z,Deposit,100,External,Bank,,,1,,,", "USD"),  # refused before #350: read as BTC
    ("2024-01-05T10:00:00Z,Deposit,100,External,Exchange USD,,,1,,,", "USD"),
    ("2024-01-05T10:00:00Z,Deposit,0.1,External,Wallet,100,,0.0001,,MyBTC,", "BTC"),
    ("2024-01-05T10:00:00Z,Withdrawal,100,Bank,External,,,1,,,", "USD"),
    ("2024-01-05T10:00:00Z,Transfer,0.1,Wallet,Exchange BTC,,,0.0001,,,", "BTC"),
    ("2024-01-05T10:00:00Z,Transfer,100,Bank,Exchange USD,,,1,,,", "USD"),
    ("2024-01-05T10:00:00Z,Buy,0.01,Bank,Exchange BTC,500,,1,,,", "USD"),
])
def test_a_blank_fee_currency_is_the_one_the_save_fills_in(row, currency):
    """#303's fee_currency_used: the currency of the account the fee is paid
    from, a deposit's of the account it goes into, a Buy's or Sell's USD."""
    result = parse_csv_file(csv(row))
    assert errors(result) == []
    assert result.transactions[0]["fee_currency"] == currency


def test_a_usd_deposit_with_a_blank_fee_currency_is_saved_in_usd(client):
    content = {"file": ("rows.csv", csv("2024-01-05T10:00:00Z,Deposit,100,External,Bank,,,1,,,"), "text/csv")}
    assert client.post("/api/import/execute", files=content).status_code == 200
    [tx] = client.get("/api/transactions").json()
    assert (tx["fee_currency"], tx["fee_amount"]) == ("USD", "1.00000000")


# The export
def exported(client: TestClient) -> list[dict]:
    return list(csv_module.DictReader(io.StringIO(client.get("/api/backup/csv").text)))


def test_the_export_writes_each_accounts_name_now(fresh_app, client):
    for tx in ({"type": "Deposit", "timestamp": "2024-01-01T12:00:00Z", "from_account_id": 99, "to_account_id": 3,
                "amount": "1000"},
               {"type": "Buy", "timestamp": "2024-01-02T12:00:00Z", "from_account_id": 3, "to_account_id": 4,
                "amount": "0.01", "cost_basis_usd": "500"}):
        assert client.post("/api/transactions", json=tx).status_code == 200
    rename(fresh_app, COINBASE)
    assert [(r["from_account"], r["to_account"]) for r in exported(client)] == [
        ("External", "Coinbase USD"), ("Coinbase USD", "Coinbase BTC")]


def test_an_id_with_no_account_is_exported_blank_as_before(fresh_app, client):
    """A row saved before 0.9.2 into an account that's gone (5.3)."""
    with fresh_app() as db:
        db.add(Transaction(type="Deposit", timestamp=datetime(2024, 1, 1, 12),
                           from_account_id=99, to_account_id=777, amount=1))
        db.commit()
    assert [(r["from_account"], r["to_account"]) for r in exported(client)] == [("External", "")]


# The round trip with added accounts
ROWS = [
    {"type": "Deposit", "timestamp": "2024-01-01T12:00:00Z", "from_account_id": 99, "to_account_id": 101,
     "amount": "5000"},
    {"type": "Transfer", "timestamp": "2024-01-02T12:00:00Z", "from_account_id": 101, "to_account_id": 102,
     "amount": "4000", "fee_amount": "2", "fee_currency": "USD"},
    {"type": "Buy", "timestamp": "2024-01-03T12:00:00Z", "from_account_id": 102, "to_account_id": 103,
     "amount": "0.1", "cost_basis_usd": "3000", "fee_amount": "5", "fee_currency": "USD"},
    {"type": "Transfer", "timestamp": "2024-02-01T12:00:00Z", "from_account_id": 103, "to_account_id": 100,
     "amount": "0.06", "fee_amount": "0.0001", "fee_currency": "BTC", "fee_usd": "4"},
    {"type": "Deposit", "timestamp": "2024-03-01T12:00:00Z", "from_account_id": 99, "to_account_id": 100,
     "amount": "0.01", "source": "Income", "cost_basis_usd": "600"},
    {"type": "Sell", "timestamp": "2025-03-01T12:00:00Z", "from_account_id": 103, "to_account_id": 102,
     "amount": "0.03", "proceeds_usd": "2700", "fee_amount": "3", "fee_currency": "USD"},
    {"type": "Withdrawal", "timestamp": "2025-04-01T12:00:00Z", "from_account_id": 100, "to_account_id": 99,
     "amount": "0.02", "purpose": "Spent", "proceeds_usd": "1900", "fee_amount": "0.0001", "fee_currency": "BTC",
     "fee_usd": "9"},
]
KEPT = ("type", "timestamp", "from_account_id", "to_account_id", "amount", "fee_amount", "fee_currency", "fee_usd",
        "cost_basis_usd", "gross_proceeds_usd", "proceeds_usd", "realized_gain_usd", "holding_period", "source",
        "purpose")


def ledger(client: TestClient) -> dict:
    rows = [{k: t[k] for k in KEPT} for t in client.get("/api/transactions").json()]
    return {"rows": sorted(rows, key=lambda t: t["timestamp"]),
            "balances": client.get("/api/calculations/accounts/balances").json(),
            "gains": client.get("/api/calculations/gains-and-losses").json()}


def test_a_csv_round_trip_keeps_the_added_accounts(client):
    add_them(client)
    for tx in ROWS:
        r = client.post("/api/transactions", json=tx)
        assert r.status_code == 200, (tx, r.text)
    before = ledger(client)
    text = client.get("/api/backup/csv").text
    names = {(r["from_account"], r["to_account"]) for r in csv_module.DictReader(io.StringIO(text))}
    assert ("Kraken BTC", "Cold Storage") in names and ("External", "Credit Union") in names
    assert client.delete("/api/transactions/delete_all?confirm=DELETE").status_code == 204
    content = {"file": ("export.csv", text.encode(), "text/csv")}
    answer = client.post("/api/import/preview", files=content).json()
    assert answer["errors"] == [] and answer["warnings"] == [] and answer["valid_rows"] == len(ROWS), answer
    r = client.post("/api/import/execute", files=content)
    assert r.status_code == 200, r.text
    assert ledger(client) == before
