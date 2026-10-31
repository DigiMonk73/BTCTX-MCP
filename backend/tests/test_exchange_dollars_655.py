"""
#655: an exchange's file leaves its dollars out (a deposit or withdrawal of
dollars moves no bitcoin), but its buys were paid from the exchange's own
dollars by default, so after Kraken's sample Kraken's dollars read -$338.34.
A buy's dollars now come from the exchange's own only when the file's
earlier rows (its sales) leave enough there; otherwise from the first bank
not hidden. Each sample file, imported as its preview proposes it, leaves
the exchange's dollars at or above zero at every moment. No tax figure
depends on which account paid: a buy's basis is the same either way.
"""

import io
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.exchange_import import propose_file
from backend.services.exchange_mappings import READY_MADE
from backend.services.river_import import BUY, RIVER_1X, SELL, FileRow, adapt_rows
from backend.tests.conftest import default_login, stub_daily_prices

FILES = Path(__file__).resolve().parents[2] / "testdata" / "exchange_files"
SAMPLES = [
    ("coinbase", "coinbase_2024.csv"), ("coinbase", "coinbase_2022.csv"), ("kraken", "kraken_ledgers.csv"),
    ("strike", "strike_statement.csv"), ("strike", "strike_activity.csv"), ("swan", "swan_deposits_and_purchases.csv"),
    ("swan-withdrawals", "swan_withdrawals.csv"), ("cash-app", "cash_app_bitcoin.csv"), ("cash-app", "cash_app_activity.csv"),
]
EXCHANGE_USD = 3
KEYS = ("row_number", "date", "type", "amount", "from_account", "to_account", "cost_basis_usd", "proceeds_usd",
        "fee_amount", "fee_currency", "source", "purpose")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 100000.0)


@pytest.fixture
def client(fresh_app) -> TestClient:
    """A ledger of its own with coins in the wallet and on the exchange since
    2020, so a sample's sends and receives have coins to move; no dollars."""
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    for account in (2, 4):
        r = client.post("/api/transactions", json={
            "type": "Deposit", "timestamp": "2020-01-01T12:00:00Z", "from_account_id": 99, "to_account_id": account,
            "amount": "1", "fee_amount": "0", "fee_currency": "BTC", "cost_basis_usd": "7000.00", "source": "MyBTC"})
        assert r.status_code in (200, 201), r.text
    return client


def dollars_over_time(transactions: list[dict], account: int) -> list[Decimal]:
    """The account's dollars after each transaction, in time order: a buy
    paid from it takes its cost and fee, a sale into it brings its proceeds
    less its fee."""
    balance, seen = Decimal(0), []
    for tx in sorted(transactions, key=lambda t: (t["timestamp"], t["id"])):
        if tx["type"] == "Buy" and tx["from_account_id"] == account:
            balance -= Decimal(tx["cost_basis_usd"]) + Decimal(tx["fee_amount"] or 0)
        elif tx["type"] == "Sell" and tx["to_account_id"] == account:
            balance += Decimal(tx["proceeds_usd"]) - Decimal(tx["fee_amount"] or 0)
        seen.append(balance)
    return seen


@pytest.mark.parametrize("mapping_id, name", SAMPLES, ids=[name for _, name in SAMPLES])
def test_a_sample_imported_as_proposed_never_takes_the_exchanges_dollars_below_zero(client, mapping_id, name):
    r = client.post("/api/import/exchange/preview", data={"mapping_id": mapping_id},
                    files={"file": (name, io.BytesIO((FILES / name).read_bytes()), "text/csv")})
    assert r.status_code == 200, r.text
    rows = [{k: p[k] for k in KEYS} for p in r.json()["proposals"]]
    r = client.post("/api/import/exchange/execute", json={"rows": rows})
    assert r.status_code == 200, r.text
    saved = client.get("/api/transactions").json()
    assert min(dollars_over_time(saved, EXCHANGE_USD), default=Decimal(0)) >= 0
    balances = {b["account_id"]: Decimal(str(b["balance_usd"])) for b in client.get(
        "/api/calculations/accounts/balances").json() if b.get("balance_usd") is not None}
    assert balances.get(EXCHANGE_USD, Decimal(0)) >= 0


HEADER = ("Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,Fee BTC,BTC Price,"
          "Cost Basis (USD),Destination,Description,Transaction Hash,Note")


def funding(rows: list[str]) -> list[str]:
    content = ("\n".join([HEADER, *rows]) + "\n").encode()
    return [p.from_account for p in propose_file(content, READY_MADE["strike"], RIVER_1X).proposals if p.type == "Buy"]


def test_a_buy_is_paid_from_the_exchanges_dollars_only_when_its_earlier_sales_left_enough():
    # $49.50 net from a sale: a $40 buy after it fits, a $20 one after that doesn't ($9.50 left)
    assert funding([
        "a,Jan 05 2025 10:00:00,Purchase,-101.00,1.00,0.00100000,,,,,,,",
        "b,Jan 06 2025 10:00:00,Sale,49.50,0.50,-0.00050000,,,,,,,",
        "c,Jan 07 2025 10:00:00,Purchase,-40.00,0.40,0.00040000,,,,,,,",
        "d,Jan 08 2025 10:00:00,Purchase,-20.00,0.20,0.00020000,,,,,,,",
    ]) == ["Bank", "Exchange USD", "Bank"]


def test_the_rows_count_in_time_order_whatever_the_files_order():
    """A file listed newest first: its sale still comes before the buy it pays for."""
    assert funding([
        "c,Jan 07 2025 10:00:00,Purchase,-40.00,0.40,0.00040000,,,,,,,",
        "b,Jan 06 2025 10:00:00,Sale,49.50,0.50,-0.00050000,,,,,,,",
    ]) == ["Exchange USD"]


def test_with_every_bank_hidden_a_buy_is_paid_from_the_exchanges_dollars(fresh_app, client):
    """The rule never picks a hidden bank (5.11): with none to pick, the exchange's dollars, as before."""
    assert client.put("/api/accounts/1", json={"hidden": True}).status_code == 200
    content = ("\n".join([HEADER, "a,Jan 05 2025 10:00:00,Purchase,-101.00,1.00,0.00100000,,,,,,,"]) + "\n").encode()
    r = client.post("/api/import/exchange/preview", data={"mapping_id": "strike"},
                    files={"file": ("s.csv", io.BytesIO(content), "text/csv")})
    assert [p["from_account"] for p in r.json()["proposals"]] == ["Exchange USD"]


RIVER_HEADER = "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag"
RIVER_ROWS = [
    "2026-01-05 12:00:00,25.00,USD,0.00030000,BTC,,,Buy",
    "2026-01-12 12:00:00,25.00,USD,0.00031000,BTC,,,Buy",
    "2026-01-19 12:00:00,25.00,USD,0.00032000,BTC,,,Buy",
    "2026-01-26 12:00:00,25.00,USD,0.00033000,BTC,,,Buy",
    "2026-02-03 15:30:00,148.50,USD,0.00180000,BTC,1.50,USD,Buy",
    "2026-02-10 16:00:00,0.00050000,BTC,55.00,USD,0.55,USD,Sell",
    "2026-02-20 15:30:00,40.00,USD,0.00050000,BTC,0.40,USD,Buy",
]


def test_a_river_file_saved_under_1xs_default_is_found_again_whole(client):
    """Only the default "Paid from" changed: a file imported under 1.x's
    (every one-time buy from Exchange USD), imported again, has every row
    already in the ledger, left out (the bank River's file never names
    doesn't stop a match, 5.11)."""
    content = ("\n".join([RIVER_HEADER, *RIVER_ROWS]) + "\n").encode()

    def preview() -> dict:
        r = client.post("/api/import/river/preview", files={"file": ("river.csv", io.BytesIO(content), "text/csv")})
        assert r.status_code == 200, r.text
        return r.json()

    first = preview()
    assert [p["from_account"] for p in first["proposals"] if p["type"] == "Buy"] == ["Bank"] * 5 + ["Exchange USD"]
    as_1x_saved_them = [{**{k: p[k] for k in KEYS},
                         **({"from_account": "Exchange USD"} if p["type"] == "Buy" and p["row_number"] == 6 else {})}
                        for p in first["proposals"]]
    r = client.post("/api/import/river/execute", json={"rows": as_1x_saved_them})
    assert r.status_code == 200 and r.json()["imported_count"] == len(RIVER_ROWS), r.text
    again = preview()
    assert {p["status"] for p in again["proposals"]} == {"matched"}
    assert again["new_count"] == 0 and again["discrepancy_count"] == 0


def _at(day: int) -> datetime:
    return datetime(2026, 1, day, 12, 0, tzinfo=timezone.utc)


def test_a_sales_fee_counts_as_the_usd_the_proposal_records_whatever_its_currency():
    """covered_buys must mirror what the ledger does, not what the file
    labels: buy() and sell() record every fee as USD (fee_currency="USD"),
    so a sale's fee leaves the exchange's dollars even when the file wrote it
    in bitcoin. A $50 sale with a $5 fee leaves $45 on the exchange; a $48
    buy after it isn't covered, and is paid from the bank, not the exchange
    (#655 review finding 1: counting the fee as _usd_fee, which is 0 for a
    BTC fee currency, would cover the buy and take the exchange to -$3)."""
    rows = [
        FileRow(1, _at(5), SELL, Decimal("0.001"), Decimal("50"), Decimal("5"), "BTC", None),
        FileRow(2, _at(6), BUY, Decimal("0.0005"), Decimal("48"), None, None, None),
    ]
    proposals, _, _ = adapt_rows(rows, RIVER_1X)
    buy = next(p for p in proposals if p.type == "Buy")
    assert buy.from_account_id == RIVER_1X.bank


def _buy_funding(rows: list[FileRow], **kw) -> list[int]:
    proposals, _, _ = adapt_rows(rows, RIVER_1X, **kw)
    return [p.from_account_id for p in proposals if p.type == "Buy"]


def test_the_fee_decides_whether_a_sale_covers_a_buy():
    """A buy is covered only when the exchange's dollars reach its cost and
    its USD fee together: a $50 sale covers a $49 buy with a $1 fee exactly
    ($50), but not a $50 buy with a $1 fee ($51 needed) — that one is paid
    from the bank. The fee the ledger subtracts is part of the test (#655)."""
    sale = FileRow(1, _at(5), SELL, Decimal("0.001"), Decimal("50"), None, None, None)
    covered = FileRow(2, _at(6), BUY, Decimal("0.0005"), Decimal("49"), Decimal("1"), "USD", None)
    not_covered = FileRow(2, _at(6), BUY, Decimal("0.0005"), Decimal("50"), Decimal("1"), "USD", None)
    assert _buy_funding([sale, covered]) == [RIVER_1X.exchange_usd]
    assert _buy_funding([sale, not_covered]) == [RIVER_1X.bank]


def test_a_bank_funded_buy_doesnt_consume_a_sales_proceeds():
    """A buy the rule pays from a bank anyway doesn't draw on a sale's
    dollars, so a later one-time buy still finds them (#655). River's
    recurring no-fee auto-buys (outlays) are such buys; Swan's (from_bank)
    are too — there every buy is the bank's."""
    recurring = [FileRow(i, _at(i), BUY, Decimal("0.0003"), Decimal("25"), None, None, "Buy")
                 for i in range(1, 5)]
    sale = FileRow(5, _at(5), SELL, Decimal("0.01"), Decimal("500"), None, None, "Sell")
    one_time = FileRow(6, _at(6), BUY, Decimal("0.005"), Decimal("500"), None, None, "Buy")
    rows = [*recurring, sale, one_time]
    # The four recurring buys are the bank's and spend none of the sale, so
    # the one-time buy's $500 is still on the exchange and covers it.
    assert _buy_funding(rows, outlays={Decimal("25"): 4}) == [RIVER_1X.bank] * 4 + [RIVER_1X.exchange_usd]
    # Swan: every buy is the bank's, the sale untouched.
    assert _buy_funding(rows, from_bank=True) == [RIVER_1X.bank] * 5
