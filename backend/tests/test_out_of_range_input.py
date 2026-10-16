"""
Input that can never be valid is refused with a 422 or a row's error naming
its field, never a server error (#211). Nothing is stored either way.

- A date at the edge of Python's years (1 to 9999) falls outside them once
  moved to another timezone: 9999-12-31 west of UTC, 0001-01-01 east of it
  (tax_time.DateOutOfRange). The CSV and JSON entry imports, the
  transaction API's date and date originally acquired.
- A report year before Bitcoin or far ahead.
- A CSV field longer than the csv module reads (131,072 characters): a file
  error of the CSV and River imports.
"""

import pytest

from backend.services.csv_import import parse_csv_file
from backend.services.entry_import import validate_rows
from backend.services.river_import import parse_river_csv
from backend.services.tax_time import DATE_OUT_OF_RANGE
from backend.schemas.entry_import import EntryRow
from zoneinfo import ZoneInfo

NEW_YORK, KIRITIMATI = ZoneInfo("America/New_York"), ZoneInfo("Pacific/Kiritimati")  # UTC-5, UTC+14
EDGE_DATES = ["9999-12-31T23:59:59", "9999-12-31T23:59:59-05:00", "0001-01-01T00:00:00+05:00"]
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
    assert csv_errors(row) == [(2, "acquired_at", DATE_OUT_OF_RANGE)]


def test_a_date_originally_acquired_past_them_in_the_tax_timezone():
    """In UTC still, but not in a tax timezone 14 hours ahead."""
    row = "2024-01-01,Deposit,1,External,Wallet,100,MyBTC,9999-12-31T23:00:00Z"
    assert csv_errors(row, tz=KIRITIMATI) == [(2, "acquired_at", DATE_OUT_OF_RANGE)]


@pytest.mark.parametrize("field", ["date", "acquired_at"])
@pytest.mark.parametrize("date", EDGE_DATES)
def test_an_entry_import_date_past_them(field, date):
    row = dict(date="2024-01-01", type="Deposit", amount="1", from_account="External", to_account="Wallet",
               source="MyBTC", cost_basis_usd="100")
    [prepared] = validate_rows([EntryRow(**{**row, field: date})], NEW_YORK)
    assert prepared.result.errors == [DATE_OUT_OF_RANGE]


@pytest.fixture
def new_york(auth_client):
    before = auth_client.get("/api/settings/tax-timezone").json()["timezone"]
    assert auth_client.put("/api/settings/tax-timezone", json={"timezone": "America/New_York"}).status_code == 200
    yield
    auth_client.put("/api/settings/tax-timezone", json={"timezone": before})


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
    """The service's own move to the tax timezone (main.date_out_of_range_handler)."""
    before = auth_client.get("/api/settings/tax-timezone").json()["timezone"]
    auth_client.put("/api/settings/tax-timezone", json={"timezone": "Pacific/Kiritimati"})
    try:
        r = auth_client.post("/api/transactions", json={**DEPOSIT, "acquired_at": "9999-12-31T23:00:00Z"})
        assert (r.status_code, r.json()) == (422, {"detail": DATE_OUT_OF_RANGE})
    finally:
        auth_client.put("/api/settings/tax-timezone", json={"timezone": before})


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
