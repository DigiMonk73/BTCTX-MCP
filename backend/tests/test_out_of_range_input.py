"""
Input that can never be valid is refused with a 422 or a row's error naming
its field, never a server error (#211). Nothing is stored either way.

- A date at the edge of Python's years (1 to 9999) falls outside them once
  moved to another timezone: 9999-12-31 west of UTC, 0001-01-01 east of it
  (tax_time.DateOutOfRange), a date alone too, as noon in the tax timezone
  (at year 1, zoneinfo puts Alaska 14 hours ahead). The CSV and JSON entry
  imports, the transaction API's date and date originally acquired, each
  refusal naming its field.
- A report year before Bitcoin or far ahead.
- A CSV field longer than the csv module reads (131,072 characters): a file
  error of the CSV and River imports.
"""

import pytest

from backend.services.csv_import import parse_csv_file
from backend.services.entry_import import validate_rows
from backend.services.river_import import parse_river_csv
from backend.services.tax_time import DATE_OUT_OF_RANGE, date_out_of_range
from backend.schemas.entry_import import EntryRow
from zoneinfo import ZoneInfo

NEW_YORK, KIRITIMATI = ZoneInfo("America/New_York"), ZoneInfo("Pacific/Kiritimati")  # UTC-5, UTC+14
EDGE_DATES = ["9999-12-31T23:59:59", "9999-12-31T23:59:59-05:00", "0001-01-01T00:00:00+05:00"]
# A date alone is noon in the tax timezone: at year 1 Alaska's old local time is 14 hours ahead of UTC
DATES_ALONE = [("0001-01-01", "America/Anchorage"), ("01/01/0001", "America/Anchorage"),
               ("9999-12-31", "Etc/GMT+12"), ("12/31/9999", "Etc/GMT+12")]
ACQUIRED_OUT_OF_RANGE = date_out_of_range("The date originally acquired")
HEADER = "date,type,amount,from_account,to_account,cost_basis_usd,source,acquired_at"
TOO_LONG = "x" * 131_073
UNREADABLE = "The file can't be read as CSV (field larger than field limit (131072))."


def csv_errors(*rows, tz=NEW_YORK):
    result = parse_csv_file(("\n".join([HEADER, *rows]) + "\n").encode(), tz)
    return [(e.row_number, e.column, e.message) for e in result.errors]


@pytest.mark.parametrize("date", EDGE_DATES)
def test_a_csv_date_past_pythons_years(date):
    assert csv_errors(f"{date},Deposit,1,External,Wallet,100,MyBTC,") == [(2, "date", DATE_OUT_OF_RANGE)]


@pytest.mark.parametrize("date", EDGE_DATES)
def test_a_csv_date_originally_acquired_past_them(date):
    row = f"2024-01-01,Deposit,1,External,Wallet,100,MyBTC,{date}"
    assert csv_errors(row) == [(2, "acquired_at", ACQUIRED_OUT_OF_RANGE)]


def test_an_inheritances_names_the_date_of_death():
    row = "2024-01-01,Deposit,1,External,Wallet,100,Inherited,0001-01-01T00:00:00+05:00"
    assert csv_errors(row) == [(2, "acquired_at", date_out_of_range("The date of death"))]


def test_a_date_originally_acquired_past_them_in_the_tax_timezone():
    """In UTC still, but not in a tax timezone 14 hours ahead."""
    row = "2024-01-01,Deposit,1,External,Wallet,100,MyBTC,9999-12-31T23:00:00Z"
    assert csv_errors(row, tz=KIRITIMATI) == [(2, "acquired_at", ACQUIRED_OUT_OF_RANGE)]


@pytest.mark.parametrize("date, zone", DATES_ALONE)
def test_a_csv_date_alone_past_them_in_the_tax_timezone(date, zone):
    assert csv_errors(f"{date},Deposit,1,External,Wallet,100,MyBTC,", tz=ZoneInfo(zone)) == \
        [(2, "date", DATE_OUT_OF_RANGE)]
    assert csv_errors(f"2024-01-01T12:00:00Z,Deposit,1,External,Wallet,100,MyBTC,{date}", tz=ZoneInfo(zone)) == \
        [(2, "acquired_at", ACQUIRED_OUT_OF_RANGE)]


ENTRY = dict(date="2024-01-01", type="Deposit", amount="1", from_account="External", to_account="Wallet",
             source="MyBTC", cost_basis_usd="100")
NAMED = {"date": DATE_OUT_OF_RANGE, "acquired_at": ACQUIRED_OUT_OF_RANGE}


@pytest.mark.parametrize("field", ["date", "acquired_at"])
@pytest.mark.parametrize("date", EDGE_DATES)
def test_an_entry_import_date_past_them(field, date):
    """The AI connector's entries keep only a row error's words: each names its field."""
    [prepared] = validate_rows([EntryRow(**{**ENTRY, field: date})], NEW_YORK)
    assert prepared.result.errors == [NAMED[field]]


@pytest.mark.parametrize("field", ["date", "acquired_at"])
@pytest.mark.parametrize("date, zone", DATES_ALONE)
def test_an_entry_import_date_alone_past_them_in_the_tax_timezone(field, date, zone):
    row = {**ENTRY, "date": "2024-01-01T12:00:00Z", field: date}
    [prepared] = validate_rows([EntryRow(**row)], ZoneInfo(zone))
    assert prepared.result.errors == [NAMED[field]]


@pytest.fixture
def new_york(auth_client):
    before = auth_client.get("/api/settings/tax-timezone").json()["timezone"]
    assert auth_client.put("/api/settings/tax-timezone", json={"timezone": "America/New_York", "chosen": True}).status_code == 200
    yield
    auth_client.put("/api/settings/tax-timezone", json={"timezone": before, "chosen": True})


DEPOSIT = dict(type="Deposit", timestamp="2024-01-01T12:00:00Z", from_account_id=99, to_account_id=2,
               amount="1", source="MyBTC", cost_basis_usd="100")


@pytest.mark.parametrize("field", ["timestamp", "acquired_at"])
@pytest.mark.parametrize("date", ["9999-12-31T23:59:59-05:00", "0001-01-01T00:00:00+05:00"])
def test_the_transaction_api_refuses_them(auth_client, new_york, field, date):
    count = len(auth_client.get("/api/transactions").json())
    r = auth_client.post("/api/transactions", json={**DEPOSIT, field: date})
    assert r.status_code == 422, r.text
    [error] = r.json()["detail"]
    assert error["loc"] == ["body", field] and DATE_OUT_OF_RANGE in error["msg"]
    assert len(auth_client.get("/api/transactions").json()) == count


def test_and_an_edit_too(auth_client, new_york):
    r = auth_client.post("/api/transactions", json=DEPOSIT)
    assert r.status_code == 200, r.text
    tx_id = r.json()["id"]
    try:
        r = auth_client.put(f"/api/transactions/{tx_id}", json={"timestamp": "0001-01-01T00:00:00+05:00"})
        assert r.status_code == 422 and r.json()["detail"][0]["loc"] == ["body", "timestamp"]
        assert auth_client.get(f"/api/transactions/{tx_id}").json()["timestamp"] == "2024-01-01T12:00:00Z"
    finally:
        auth_client.delete(f"/api/transactions/{tx_id}")


def test_a_date_originally_acquired_past_them_in_the_api_tax_timezone(auth_client):
    """The service's own move to the tax timezone, named (transaction._check_original_date)."""
    before = auth_client.get("/api/settings/tax-timezone").json()["timezone"]
    auth_client.put("/api/settings/tax-timezone", json={"timezone": "Pacific/Kiritimati", "chosen": True})
    try:
        r = auth_client.post("/api/transactions", json={**DEPOSIT, "acquired_at": "9999-12-31T23:00:00Z"})
        assert (r.status_code, r.json()) == (422, {"detail": ACQUIRED_OUT_OF_RANGE})
    finally:
        auth_client.put("/api/settings/tax-timezone", json={"timezone": before, "chosen": True})


@pytest.mark.parametrize("report", ["complete_tax_report", "simple_transaction_history"])
@pytest.mark.parametrize("year", [0, -1, 2008, 2101, 9999, 10000, 99999999999])
def test_a_report_year_before_bitcoin_or_far_ahead(auth_client, report, year):
    r = auth_client.get(f"/api/reports/{report}?year={year}")
    assert r.status_code == 422, r.text
    assert r.json()["detail"][0]["loc"] == ["query", "year"]


def test_a_csv_field_too_long_to_read():
    assert csv_errors(f"2024-01-01,Deposit,1,External,Wallet,100,MyBTC,{TOO_LONG}") == [(0, None, UNREADABLE)]


RIVER = ("Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag\n"
         f"2024-01-01 12:00:00,,,1,BTC,,,{TOO_LONG}\n").encode()


def test_a_river_field_too_long_to_read():
    rows, errors = parse_river_csv(RIVER)
    assert rows == [] and [(e.row_number, e.message) for e in errors] == [(0, UNREADABLE)]


def test_through_the_import_routes(auth_client):
    content = f"{HEADER}\n2024-01-01,Deposit,1,External,Wallet,100,MyBTC,{TOO_LONG}\n".encode()
    for url, file in (("/api/import/preview", content), ("/api/import/river/preview", RIVER)):
        r = auth_client.post(url, files={"file": ("big.csv", file, "text/csv")})
        assert r.status_code == 200 and [e["message"] for e in r.json()["errors"]] == [UNREADABLE]


def test_any_other_move_past_them_is_a_422_too():
    """The backstop for a move no route names (main.date_out_of_range_handler)."""
    import asyncio
    import json

    from backend.main import app
    from backend.services.tax_time import DateOutOfRange

    response = asyncio.run(app.exception_handlers[DateOutOfRange](None, DateOutOfRange()))
    assert (response.status_code, json.loads(response.body)) == (422, {"detail": DATE_OUT_OF_RANGE})


@pytest.mark.parametrize("zone, date", [("America/Anchorage", "0001-01-01"), ("Etc/GMT+12", "9999-12-31")])
def test_the_api_takes_a_date_alone_at_the_edges_too(auth_client, zone, date):
    before = auth_client.get("/api/settings/tax-timezone").json()["timezone"]
    auth_client.put("/api/settings/tax-timezone", json={"timezone": zone, "chosen": True})
    try:
        for body in ({**DEPOSIT, "timestamp": date}, {**DEPOSIT, "acquired_at": date}):
            r = auth_client.post("/api/transactions", json=body)
            assert r.status_code == 422, r.text
    finally:
        auth_client.put("/api/settings/tax-timezone", json={"timezone": before, "chosen": True})
