"""
A comma in a number is read only as a thousands separator: between groups
of three digits before the point ("1,000", "12,345.67"). The CSV and River
imports dropped every comma, so "0,5" BTC (half a bitcoin written with a
decimal comma) was saved as 5 BTC, and "1234,56" dollars as 123456, with
no error (#452). Any other comma is refused now, naming its column.
"""

import csv
import io
from decimal import Decimal

import pytest

from backend.services.csv_import import parse_csv_file
from backend.services.river_import import RIVER_NUMBER_COLUMNS, parse_river_csv
from backend.tests.conftest import stub_daily_prices

# Each was read as another number: 5, 123456, 1, 150, 100, 500, 10000, 1234,
# 100000, 1000.50, 0.5, 5, 1000, 1000, 1000000
NOT_THOUSANDS = [
    "0,5", "1234,56", "0,01", "1,5,0", "1,00", "0,500", "1,0000", "12,34",
    "1,000,00", "1,000.5,0", ",5", "5,", "1,,000", "01,000", "1,000E3",
]
THOUSANDS = [
    ("1,000", "1000"), ("12,345.67", "12345.67"), ("1,000,000", "1000000"),
    ("999,999.99", "999999.99"), ("1,000.", "1000"),
]
COMMA_NOTE = "A comma is read only as a thousands separator (1,000.50): write decimals with a point (0.5, not 0,5)."

DEPOSIT = {"date": "2024-01-10T10:00:00Z", "type": "Deposit", "amount": "0.5", "from_account": "External",
           "to_account": "Wallet", "cost_basis_usd": "100", "source": "MyBTC"}
SPENT = {**DEPOSIT, "type": "Withdrawal", "from_account": "Wallet", "to_account": "External",
         "cost_basis_usd": "", "source": "", "purpose": "Spent", "proceeds_usd": "100"}
TRANSFER = {**DEPOSIT, "type": "Transfer", "from_account": "Exchange BTC", "cost_basis_usd": "", "source": "",
            "fee_amount": "0.0001", "fee_currency": "BTC"}
GIFT = {**SPENT, "purpose": "Gift", "proceeds_usd": ""}
BUY = {**DEPOSIT, "type": "Buy", "from_account": "Bank", "to_account": "Exchange BTC", "source": "",
       "fee_amount": "5", "fee_currency": "USD"}

# Every number column of the CSV import, in a row that takes it (a dollar
# fee: a bitcoin fee of 1,000 is larger than the amount)
COLUMNS = [
    ("amount", DEPOSIT), ("cost_basis_usd", DEPOSIT), ("proceeds_usd", SPENT),
    ("fee_amount", BUY), ("fee_usd", TRANSFER), ("fmv_usd", GIFT),
]


def csv_file(row: dict) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(row), quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerow(row)
    return out.getvalue().encode()


@pytest.mark.parametrize("column, row", COLUMNS)
@pytest.mark.parametrize("cell", NOT_THOUSANDS)
def test_a_comma_that_isnt_a_thousands_separator_is_refused(column, row, cell):
    result = parse_csv_file(csv_file({**row, column: cell}))
    errors = [e for e in result.errors if e.column == column]
    assert len(errors) == 1, result.errors
    assert f"'{cell}'" in errors[0].message and errors[0].message.endswith(COMMA_NOTE)
    assert errors[0].row_number == 2 and errors[0].severity == "error"
    assert result.transactions == []


@pytest.mark.parametrize("column, row", COLUMNS)
@pytest.mark.parametrize("cell, number", THOUSANDS)
def test_a_thousands_separator_still_works(column, row, cell, number):
    result = parse_csv_file(csv_file({**row, column: cell}))
    assert result.errors == []
    assert Decimal(str(result.transactions[0][column])) == Decimal(number)


def test_a_number_with_thousands_separators_too_many_places_is_refused_without_the_note():
    """The comma is fine; the places aren't. The message says only that."""
    result = parse_csv_file(csv_file({**DEPOSIT, "amount": "1,000.123456789"}))
    assert [(e.column, e.message) for e in result.errors] == [(
        "amount",
        "Invalid amount '1,000.123456789'. Must be a positive number with up to "
        "8 decimal places and 10 digits before the decimal point.",
    )]


def test_a_negative_number_with_thousands_separators_is_negative():
    result = parse_csv_file(csv_file({**DEPOSIT, "cost_basis_usd": "-1,000"}))
    assert [(e.column, e.message) for e in result.errors] == [("cost_basis_usd", "cost_basis_usd can't be negative.")]


# The files of #452's "How to reproduce"
ISSUE_CSV = (
    b"date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency,source,purpose,notes\n"
    b'2024-01-10T10:00:00Z,Deposit,"0,5",External,Wallet,"1234,56",,,,MyBTC,,\n'
)
RIVER_HEADER = "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag"
ISSUE_RIVER = (RIVER_HEADER + '\n2024-01-10 10:00:00,"1000,00",USD,"0,01",BTC,,USD,Buy\n').encode()


def test_the_issues_csv_file_is_refused_at_preview_and_import(auth_client):
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    content = {"file": ("import.csv", ISSUE_CSV, "text/csv")}

    preview = auth_client.post("/api/import/preview", files=content)
    assert preview.status_code == 200, preview.text
    assert preview.json()["can_import"] is False
    assert preview.json()["transactions"] == []
    assert [(e["row_number"], e["column"]) for e in preview.json()["errors"]] == [(2, "amount")]
    assert preview.json()["errors"][0]["message"] == (
        "Invalid amount '0,5'. Must be a positive number with up to 8 decimal places and "
        f"10 digits before the decimal point. {COMMA_NOTE}"
    )

    imported = auth_client.post("/api/import/execute", files=content)
    assert imported.status_code == 400
    assert "Invalid amount '0,5'" in imported.json()["detail"]
    assert auth_client.get("/api/transactions").json() == []


def test_the_issues_river_file_is_refused_at_preview(auth_client, monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 100000.0)
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    r = auth_client.post("/api/import/river/preview", files={"file": ("river.csv", ISSUE_RIVER, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["proposals"] == []
    assert [(e["row_number"], e["column"], e["message"]) for e in r.json()["errors"]] == [(
        2, "Sent Amount",
        f"Sent Amount '1000,00' isn't a number with at most 8 decimal places and 10 digits before "
        f"the decimal point. {COMMA_NOTE}",
    )]


def river_row(column: str, cell: str) -> dict[str, str]:
    row = {"Sent Amount": "25.00", "Received Amount": "0.0003", "Fee Amount": "1.00"}
    return {**row, column: cell}


def river_file(row: dict[str, str]) -> bytes:
    line = (f'2024-01-10 10:00:00,"{row["Sent Amount"]}",USD,"{row["Received Amount"]}",BTC,'
            f'"{row["Fee Amount"]}",USD,Buy')
    return (RIVER_HEADER + "\n" + line + "\n").encode()


@pytest.mark.parametrize("column", RIVER_NUMBER_COLUMNS)
@pytest.mark.parametrize("cell", NOT_THOUSANDS)
def test_a_river_amount_with_a_decimal_comma_is_refused(column, cell):
    rows, errors = parse_river_csv(river_file(river_row(column, cell)))
    assert rows == []
    assert [(e.row_number, e.column) for e in errors] == [(2, column)]
    assert errors[0].message.startswith(f"{column} '{cell}' isn't a number") and errors[0].message.endswith(COMMA_NOTE)


@pytest.mark.parametrize("column", RIVER_NUMBER_COLUMNS)
@pytest.mark.parametrize("cell, number", THOUSANDS)
def test_a_river_amount_with_thousands_separators_still_works(column, cell, number):
    rows, errors = parse_river_csv(river_file(river_row(column, cell)))
    assert errors == []
    attribute = {"Sent Amount": "sent", "Received Amount": "received", "Fee Amount": "fee"}[column]
    assert getattr(rows[0], attribute) == Decimal(number)
