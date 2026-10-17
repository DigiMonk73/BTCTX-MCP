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

from backend.routers.backup import _csv_number
from backend.services import outbound
from backend.services.csv_import import CSV_COLUMNS, TEMPLATE_ROWS
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
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    before = auth_client.get("/api/settings/tax-timezone").json()["timezone"]
    auth_client.put("/api/settings/tax-timezone", json={"timezone": "America/New_York", "chosen": True})
    for tx in LEDGER:
        r = auth_client.post("/api/transactions", json=tx)
        assert r.status_code == 200, (tx, r.text)
    yield
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    auth_client.put("/api/settings/tax-timezone", json={"timezone": before, "chosen": True})


def round_trip(client):
    exported = client.get("/api/backup/csv").text
    assert client.delete("/api/transactions/delete_all?confirm=DELETE").status_code == 204
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


def test_the_export_writes_a_numbers_own_digits():
    """Through a float, a number with more than about 16 digits lost its last ones."""
    assert _csv_number(Decimal("1234567890.12345678"), 8) == "1234567890.12345678"
    assert _csv_number(Decimal("0E-8"), 8) == "0.00000000"
    assert _csv_number(None, 2) == ""


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
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
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
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    content = f"{HEADER}\n{BANK}\n{row}\n"
    preview = auth_client.post("/api/import/preview", files=csv_file(content)).json()
    assert preview["can_import"] and preview["errors"] == []
    assert [(w["row_number"], w["column"]) for w in preview["warnings"]] == [(3, column)]
    assert auth_client.post("/api/import/execute", files=csv_file(content)).status_code == 200
    buy = next(t for t in auth_client.get("/api/transactions").json() if t["type"] == "Buy")
    assert buy["fee_usd"] is None and buy["fmv_usd"] is None
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


@pytest.mark.parametrize("fee, currency, stored", [
    ("", "", (None, None)),        # blank: no fee
    ("0", "USD", (0.0, "USD")),    # a zero fee stays a zero fee (the 1.2.3 VM walk: it became "no fee")
    ("0", "", (0.0, "USD")),       # its currency filled as for any fee
])
def test_a_blank_fee_is_no_fee_and_a_zero_fee_is_kept(auth_client, fee, currency, stored):
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    row = f"2024-01-02T12:00:00Z,Buy,0.01,Bank,Exchange BTC,500,,{fee},{currency},,,,,,"
    r = auth_client.post("/api/import/execute", files=csv_file(f"{HEADER}\n{BANK}\n{row}\n"))
    assert r.status_code == 200, r.text
    buy = next(t for t in auth_client.get("/api/transactions").json() if t["type"] == "Buy")
    fee_amount = None if buy["fee_amount"] is None else float(buy["fee_amount"])
    assert (fee_amount, buy["fee_currency"]) == stored
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def test_a_row_the_ledger_refuses_says_why_and_saves_nothing(auth_client, monkeypatch):
    """A BTC fee without fee_usd and no price to value it: the import says so (not a 500)."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
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


# Rows whose save prices a value left out (#125), after the BANK deposit and
# a Buy that funds them; each on 2024-01-03, an inheritance's death on 2023-12-25
NEEDS_A_PRICE = {
    "a BTC fee": ("2024-01-03T12:00:00Z,Transfer,0.01,Exchange BTC,Wallet,,,0.0001,BTC,,,", "fee_usd", "2024-01-03"),
    "an income": ("2024-01-03T12:00:00Z,Deposit,0.001,External,Wallet,,,,,Income,,", "cost_basis_usd", "2024-01-03"),
    "a spend": ("2024-01-03T12:00:00Z,Withdrawal,0.001,Exchange BTC,External,,,,,,Spent,", "proceeds_usd", "2024-01-03"),
    "an inheritance": ("2024-01-03T12:00:00Z,Deposit,0.001,External,Wallet,,,,,Inherited,,,,,,,,2023-12-25",
                       "cost_basis_usd", "2023-12-25"),
}
FUNDS = "2024-01-02T12:00:00Z,Buy,0.01,Bank,Exchange BTC,500,,,,,,"


def preview_of(auth_client, row: str) -> dict:
    r = auth_client.post("/api/import/preview", files=csv_file(f"{HEADER}\n{BANK}\n{FUNDS}\n{row}\n"))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("case", NEEDS_A_PRICE)
def test_the_preview_flags_a_row_the_import_would_refuse_for_want_of_a_price(auth_client, monkeypatch, case):
    """#125: with prices off and none stored, the preview called such a row
    valid, and the import then refused it (422). The preview now says so,
    naming the value to fill; the other rows stay valid."""
    row, column, day = NEEDS_A_PRICE[case]
    stub_daily_prices(monkeypatch, lambda day: None)
    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings(price_source="off"))
    data = preview_of(auth_client, row)
    assert (data["can_import"], data["valid_rows"], data["total_rows"]) == (False, 2, 3)
    [error] = data["errors"]
    assert (error["row_number"], error["column"]) == (4, column)
    assert error["message"].startswith(f"{column} needs the BTC price of {day}, and none is stored: fill it.")
    assert "You chose Nobody for prices" in error["message"]


@pytest.mark.parametrize("case", NEEDS_A_PRICE)
def test_a_row_whose_price_is_stored_or_may_be_asked_for_is_valid(auth_client, monkeypatch, test_engine, case):
    """The day's or the hour's price stored, or a source chosen that the
    import asks: the row is valid, as before (the import prices it)."""
    from datetime import date, datetime, timezone

    from sqlalchemy.orm import Session

    from backend.models.btc_price import BtcPriceDaily, BtcPriceHourly
    from backend.services.hourly_prices import hour_of

    row, _column, day = NEEDS_A_PRICE[case]
    assert preview_of(auth_client, row)["can_import"] is True  # the tests' public source
    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings(price_source="off"))
    with Session(test_engine) as db:
        if case == "an inheritance":  # its date of death's day price
            db.add(BtcPriceDaily(day=date.fromisoformat(day), usd=Decimal("42000"), source="test"))
        else:  # the hour's
            db.add(BtcPriceHourly(hour=hour_of(datetime(2024, 1, 3, 12, tzinfo=timezone.utc)), usd=Decimal("42000"),
                                  source="test"))
        db.commit()
    assert preview_of(auth_client, row)["can_import"] is True


def test_a_day_before_any_price_is_flagged_whatever_the_source(auth_client):
    """No price exists before 18 August 2011, so a fee left out then can't
    be priced even by a source that's asked."""
    content = (f"{HEADER}\n2010-05-01T12:00:00Z,Deposit,1000,External,Bank,,,,,,,\n"
               "2010-05-02T12:00:00Z,Buy,1,Bank,Exchange BTC,5,,,,,,\n"
               "2010-06-01T12:00:00Z,Transfer,1,Exchange BTC,Wallet,,,0.0001,BTC,,,\n")
    data = auth_client.post("/api/import/preview", files=csv_file(content)).json()
    [error] = data["errors"]
    assert error["message"] == "fee_usd needs the BTC price of 2010-06-01, and there is none for that day: fill it."


def test_the_template_imports_as_it_is_with_prices_off(auth_client, monkeypatch):
    """Docs check before 1.2.6: the template says it imports as it is, but
    four rows with a BTC fee left fee_usd blank, so before a price source was
    chosen, or with prices off, the import stopped at "No BTC price is
    stored" and saved nothing."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    stub_daily_prices(monkeypatch, lambda day: None)
    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings(price_source="off"))
    template = auth_client.get("/api/import/template").text
    preview = auth_client.post("/api/import/preview", files=csv_file(template))
    assert preview.status_code == 200, preview.text
    r = auth_client.post("/api/import/execute", files=csv_file(template))
    assert r.status_code == 200, r.text
    assert len(auth_client.get("/api/transactions").json()) == len(TEMPLATE_ROWS)
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def test_csv_round_trip_keeps_the_order_of_same_time_transactions(auth_client, test_engine, monkeypatch):
    """Bug hunt 2026-09-29: the import put same-time rows in a fixed type
    order (Transfer before Sell) while the ledger keeps the order they were
    entered in, so a round trip changed FIFO: here the Sell's basis went from
    $2,000 to $4,000 and LONG to SHORT. Same-time rows now import in the
    file's order, which is the ledger's order in an export."""
    stub_daily_prices(monkeypatch, lambda day: 50000)
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
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
    assert auth_client.delete("/api/transactions/delete_all?confirm=DELETE").status_code == 204
    r = auth_client.post("/api/import/execute", files=csv_file(exported))
    assert r.status_code == 200, r.text

    assert sell() == (Decimal("2000"), "LONG")
    assert ledger_state(auth_client, test_engine) == before
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def test_a_sale_listed_before_its_same_time_buy_says_to_reorder(auth_client):
    """Same-time rows now import in the file's order: a hand-made file that
    lists a sale before the same-day buy paying for it is refused (nothing
    saved), and the message says how to fix the file."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
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


@pytest.mark.parametrize("purpose, back", [
    ("-5% fee", "-5% fee"), ("=SUM(A1)", "=SUM(A1)"), ("+1 card", "+1 card"), ("@home", "@home"),
    ("＝look-alike", "＝look-alike"), ("－10 off", "－10 off"),
    (" =x", "=x"),  # the import trims a cell's spaces, as it always has
])
def test_text_a_spreadsheet_could_run_comes_back_as_it_was(auth_client, purpose, back):
    """#230: the export puts a ' in front of such text (safe_text.csv_text),
    and the import kept it: "-5% fee" came back as "'-5% fee"."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    for tx in (
        dict(type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=99, to_account_id=1,
             amount="1000", source="N/A"),
        dict(type="Withdrawal", timestamp="2024-01-03T12:00:00Z", from_account_id=1, to_account_id=99,
             amount="100", purpose=purpose),
    ):
        r = auth_client.post("/api/transactions", json=tx)
        assert r.status_code == 200, r.text
    stored = [t["purpose"] for t in auth_client.get("/api/transactions").json() if t["type"] == "Withdrawal"]
    exported = auth_client.get("/api/backup/csv").text
    assert f",'{stored[0]}," in exported
    assert auth_client.delete("/api/transactions/delete_all?confirm=DELETE").status_code == 204
    r = auth_client.post("/api/import/execute", files=csv_file(exported))
    assert r.status_code == 200, r.text
    assert [t["purpose"] for t in auth_client.get("/api/transactions").json() if t["type"] == "Withdrawal"] == [back]
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


@pytest.mark.parametrize("column, cell, read", [
    ("purpose", "'-5% fee", "-5% fee"), ("purpose", "'hello", "'hello"), ("purpose", "'", "'"),
    ("purpose", "  '=1 ", "=1"), ("purpose", "''=1", "''=1"),
    ("amount", "'+0.01", "'+0.01"),  # a number the export writes as it is: a ' there was never its
])
def test_only_the_exports_quote_is_dropped(column, cell, read):
    """A ' the export didn't add (before text no spreadsheet runs, or in a
    column it doesn't quote) stays."""
    from backend.services.csv_import import _cell

    assert _cell(column, cell) == read


def test_the_quoted_columns_are_the_ones_the_export_quotes():
    """The import takes the ' off only where the export may have put one."""
    import re
    from pathlib import Path

    from backend.services.csv_import import QUOTED_COLUMNS

    export = (Path(__file__).resolve().parents[1] / "routers" / "backup.py").read_text()
    assert set(re.findall(r'"(\w+)": csv_text\(', export)) == QUOTED_COLUMNS
