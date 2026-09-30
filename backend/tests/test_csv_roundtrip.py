"""
Settings > Export CSV, then Delete All and Import CSV, gives back the same
ledger: the same rows and the same Form 8949 / Schedule D.

Before, the export had no column for a BTC fee's stored USD value, a gift's
FMV or the Broker form override (all added to the database after the export
was written). A round trip re-priced every BTC fee at that day's price,
changing gains, and failed outright with price lookups off.
"""

import copy
import csv
import io
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from backend.services import outbound
from backend.services.csv_import import CSV_COLUMNS
from backend.services.reports.form_8949 import build_form_8949_and_schedule_d
from backend.tests.conftest import stub_daily_prices
from backend.tests.test_golden_years import LEDGER as GOLDEN, _normalize

# The golden ledger with its USD values typed, plus what the export used to
# lose: a Broker form override, a gift's FMV, and a transfer fee valued at
# the day's price (not typed).
LEDGER = copy.deepcopy(GOLDEN)
LEDGER[3]["fee_usd"] = "10"            # transfer fee 0.0002 BTC, typed
LEDGER[8]["cost_basis_usd"] = "1000"   # income
LEDGER[9]["fmv_usd"] = "6000"          # the gift
LEDGER[11]["broker_reporting"] = "basis"
LEDGER[13]["fee_usd"] = "5"            # spend fee 0.0001 BTC, typed
LEDGER.append(dict(type="Transfer", timestamp="2025-02-01T16:00:00Z", from_account_id=4, to_account_id=2,
                   amount="0.05", fee_amount="0.0001", fee_currency="BTC"))  # fee at the day's price

USER_FIELDS = ("type", "timestamp", "from_account_id", "to_account_id", "amount", "fee_amount", "fee_currency",
               "fee_usd", "cost_basis_usd", "gross_proceeds_usd", "proceeds_usd", "realized_gain_usd",
               "holding_period", "fmv_usd", "source", "purpose", "broker_reporting", "fee_usd_manual")


def user_fields(tx):
    return {f: tx[f] for f in USER_FIELDS}


def ledger_state(client, engine):
    rows = sorted((user_fields(t) for t in client.get("/api/transactions").json()),
                  key=lambda t: (t["timestamp"], t["type"]))
    with sessionmaker(bind=engine)() as db:
        forms = {year: _normalize(build_form_8949_and_schedule_d(year, db)) for year in (2023, 2024, 2025)}
    return {
        "rows": rows,
        "forms": forms,
        "balances": client.get("/api/calculations/accounts/balances").json(),
        "gains": client.get("/api/calculations/gains-and-losses").json(),
    }


def csv_file(text):
    return {"file": ("export.csv", text.encode(), "text/csv")}


@pytest.fixture
def odd_price(monkeypatch):
    """A day's price nowhere near the typed values: a re-priced fee would show."""
    stub_daily_prices(monkeypatch, lambda day: 77777)


@pytest.fixture
def ledger(auth_client, odd_price):
    auth_client.delete("/api/transactions/delete_all")
    before = auth_client.get("/api/settings/tax-timezone").json()["timezone"]
    auth_client.put("/api/settings/tax-timezone", json={"timezone": "America/New_York"})
    for tx in LEDGER:
        r = auth_client.post("/api/transactions", json=tx)
        assert r.status_code == 200, (tx, r.text)
    yield
    auth_client.delete("/api/transactions/delete_all")
    auth_client.put("/api/settings/tax-timezone", json={"timezone": before})


def round_trip(client):
    exported = client.get("/api/backup/csv").text
    assert client.delete("/api/transactions/delete_all").status_code == 204
    preview = client.post("/api/import/preview", files=csv_file(exported)).json()
    assert preview["can_import"] and preview["valid_rows"] == len(LEDGER), preview
    assert preview["errors"] == [] and preview["warnings"] == [], preview
    r = client.post("/api/import/execute", files=csv_file(exported))
    assert r.status_code == 200, r.text
    assert r.json()["imported_count"] == len(LEDGER)


def test_export_then_import_gives_back_the_same_ledger(auth_client, test_engine, ledger):
    before = ledger_state(auth_client, test_engine)
    round_trip(auth_client)
    assert ledger_state(auth_client, test_engine) == before


def test_the_round_trip_needs_no_price_lookups(auth_client, test_engine, ledger, monkeypatch):
    before = ledger_state(auth_client, test_engine)
    stub_daily_prices(monkeypatch, lambda day: None)
    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings(price_source="off"))
    round_trip(auth_client)
    assert ledger_state(auth_client, test_engine) == before


def test_the_export_has_every_column_the_import_reads(auth_client, ledger):
    rows = list(csv.DictReader(io.StringIO(auth_client.get("/api/backup/csv").text)))
    assert list(rows[0].keys()) == CSV_COLUMNS
    assert auth_client.get("/api/import/template").text.splitlines()[0] == ",".join(CSV_COLUMNS)

    transfer = next(r for r in rows if r["type"] == "Transfer" and r["date"].startswith("2023-06-01"))
    priced = next(r for r in rows if r["type"] == "Transfer" and r["date"].startswith("2025-02-01"))
    gift = next(r for r in rows if r["purpose"] == "Gift")
    sell = next(r for r in rows if r["date"].startswith("2025-04-01"))
    assert transfer["fee_usd"] == "10.00"
    assert priced["fee_usd"] == "7.78"  # 0.0001 BTC x $77,777, stored at save
    assert gift["fmv_usd"] == "6000.00"
    assert sell["broker_reporting"] == "basis"
    assert all(r["fee_usd"] == "" for r in rows if r["fee_currency"] != "BTC" or float(r["fee_amount"] or 0) == 0)


HEADER = ",".join(CSV_COLUMNS)
BANK = "2024-01-01T12:00:00Z,Deposit,1000,External,Bank,,,,,,,"


@pytest.mark.parametrize("row, column, message", [
    ("2024-01-02T12:00:00Z,Buy,0.01,Bank,Exchange BTC,500,,,,,,,,,maybe", "broker_reporting",
     "Invalid broker_reporting 'maybe'"),
    ("2024-01-02T12:00:00Z,Buy,0.01,Bank,Exchange BTC,500,,,,,,,,,basis", "broker_reporting",
     "broker_reporting can only be set on a Sell or Withdrawal, not a Buy."),
    ("2024-01-02T12:00:00Z,Buy,0.01,Bank,Exchange BTC,500,,,,,,,,abc,", "fmv_usd", None),
])
def test_bad_values_in_the_new_columns_are_errors(auth_client, row, column, message):
    auth_client.delete("/api/transactions/delete_all")
    preview = auth_client.post("/api/import/preview", files=csv_file(f"{HEADER}\n{BANK}\n{row}\n")).json()
    errors = [e for e in preview["errors"] if e["row_number"] == 3]
    assert [e["column"] for e in errors] == [column]
    if message:
        assert errors[0]["message"].startswith(message)
    assert not preview["can_import"]


@pytest.mark.parametrize("row, column", [
    # a USD fee has no separate USD value
    ("2024-01-02T12:00:00Z,Buy,0.01,Bank,Exchange BTC,500,,5,USD,,,,5,,", "fee_usd"),
    # only gifts, donations and lost BTC carry an FMV
    ("2024-01-02T12:00:00Z,Buy,0.01,Bank,Exchange BTC,500,,,,,,,,600,", "fmv_usd"),
])
def test_a_value_the_row_cant_use_is_a_warning_and_left_out(auth_client, row, column):
    auth_client.delete("/api/transactions/delete_all")
    content = f"{HEADER}\n{BANK}\n{row}\n"
    preview = auth_client.post("/api/import/preview", files=csv_file(content)).json()
    assert preview["can_import"] and preview["errors"] == []
    assert [(w["row_number"], w["column"]) for w in preview["warnings"]] == [(3, column)]
    assert auth_client.post("/api/import/execute", files=csv_file(content)).status_code == 200
    buy = next(t for t in auth_client.get("/api/transactions").json() if t["type"] == "Buy")
    assert buy["fee_usd"] is None and buy["fmv_usd"] is None
    auth_client.delete("/api/transactions/delete_all")


@pytest.mark.parametrize("fee, currency, stored", [
    ("", "", (None, None)),        # blank: no fee
    ("0", "USD", (0.0, "USD")),    # a zero fee stays a zero fee (the 1.2.3 VM walk: it became "no fee")
    ("0", "", (0.0, "USD")),       # its currency filled as for any fee
])
def test_a_blank_fee_is_no_fee_and_a_zero_fee_is_kept(auth_client, fee, currency, stored):
    auth_client.delete("/api/transactions/delete_all")
    row = f"2024-01-02T12:00:00Z,Buy,0.01,Bank,Exchange BTC,500,,{fee},{currency},,,,,,"
    r = auth_client.post("/api/import/execute", files=csv_file(f"{HEADER}\n{BANK}\n{row}\n"))
    assert r.status_code == 200, r.text
    buy = next(t for t in auth_client.get("/api/transactions").json() if t["type"] == "Buy")
    fee_amount = None if buy["fee_amount"] is None else float(buy["fee_amount"])
    assert (fee_amount, buy["fee_currency"]) == stored
    auth_client.delete("/api/transactions/delete_all")


def test_a_row_the_ledger_refuses_says_why_and_saves_nothing(auth_client, monkeypatch):
    """A BTC fee without fee_usd and no price to value it: the import says so (not a 500)."""
    auth_client.delete("/api/transactions/delete_all")
    stub_daily_prices(monkeypatch, lambda day: None)
    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings(price_source="off"))
    content = (f"{HEADER}\n{BANK}\n"
               "2024-01-02T12:00:00Z,Buy,0.01,Bank,Exchange BTC,500,,,,,,,,,\n"
               "2024-01-03T12:00:00Z,Transfer,0.01,Exchange BTC,Wallet,,,0.0001,BTC,,,,,,\n")
    r = auth_client.post("/api/import/execute", files=csv_file(content))
    assert r.status_code == 422, r.text
    assert r.json()["detail"].startswith("Import failed: No BTC price is stored for 2024-01-03.")
    assert r.json()["detail"].endswith("No transactions were saved.")
    assert auth_client.get("/api/transactions").json() == []


def test_csv_round_trip_keeps_the_order_of_same_time_transactions(auth_client, test_engine, monkeypatch):
    """Bug hunt 2026-09-29: the import put same-time rows in a fixed type
    order (Transfer before Sell) while the ledger keeps the order they were
    entered in, so a round trip changed FIFO: here the Sell's basis went from
    $2,000 to $4,000 and LONG to SHORT. Same-time rows now import in the
    file's order, which is the ledger's order in an export."""
    stub_daily_prices(monkeypatch, lambda day: 50000)
    auth_client.delete("/api/transactions/delete_all")
    for tx in (
        dict(type="Buy", timestamp="2023-01-02T12:00:00Z", from_account_id=1, to_account_id=4,
             amount="0.5", cost_basis_usd="10000"),
        dict(type="Buy", timestamp="2024-01-02T12:00:00Z", from_account_id=1, to_account_id=4,
             amount="0.5", cost_basis_usd="20000"),
        # Both at noon (e.g. two date-only entries): the sale saved first, then the move
        dict(type="Sell", timestamp="2024-03-05T12:00:00Z", from_account_id=4, to_account_id=3,
             amount="0.1", gross_proceeds_usd="6000", proceeds_usd="6000"),
        dict(type="Transfer", timestamp="2024-03-05T12:00:00Z", from_account_id=4, to_account_id=2,
             amount="0.9"),
    ):
        r = auth_client.post("/api/transactions", json=tx)
        assert r.status_code == 200, r.text

    def sell():
        [s] = [t for t in auth_client.get("/api/transactions").json() if t["type"] == "Sell"]
        return Decimal(str(s["cost_basis_usd"])), s["holding_period"]

    assert sell() == (Decimal("2000"), "LONG")  # FIFO: 0.1 of the 2023 lot
    before = ledger_state(auth_client, test_engine)

    exported = auth_client.get("/api/backup/csv").text
    assert auth_client.delete("/api/transactions/delete_all").status_code == 204
    r = auth_client.post("/api/import/execute", files=csv_file(exported))
    assert r.status_code == 200, r.text

    assert sell() == (Decimal("2000"), "LONG")
    assert ledger_state(auth_client, test_engine) == before
    auth_client.delete("/api/transactions/delete_all")


def test_a_sale_listed_before_its_same_time_buy_says_to_reorder(auth_client):
    """Same-time rows now import in the file's order: a hand-made file that
    lists a sale before the same-day buy paying for it is refused (nothing
    saved), and the message says how to fix the file."""
    auth_client.delete("/api/transactions/delete_all")
    header = ",".join(CSV_COLUMNS)
    blank = {c: "" for c in CSV_COLUMNS}
    rows = [
        {**blank, "date": "2024-03-05", "type": "Deposit", "amount": "10000", "from_account": "External",
         "to_account": "Bank", "fee_amount": "0", "fee_currency": "USD", "source": "N/A"},
        {**blank, "date": "2024-03-06", "type": "Sell", "amount": "0.1", "from_account": "Exchange BTC",
         "to_account": "Exchange USD", "proceeds_usd": "6000", "fee_amount": "0", "fee_currency": "USD"},
        {**blank, "date": "2024-03-06", "type": "Buy", "amount": "0.1", "from_account": "Bank",
         "to_account": "Exchange BTC", "cost_basis_usd": "5000", "fee_amount": "0", "fee_currency": "USD"},
    ]
    text = header + "\n" + "\n".join(",".join(r[c] for c in CSV_COLUMNS) for r in rows) + "\n"
    r = auth_client.post("/api/import/execute", files=csv_file(text))
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert "Not enough BTC" in detail and "file's order" in detail and ". No transactions were saved." in detail
    assert auth_client.get("/api/transactions").json() == []
