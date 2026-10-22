"""
#479: the CSV import's preview ("N valid / M total rows") counted a row once
per error, so a one-row file whose row had two errors said "2 total rows".
It counts the file's rows, as River's preview does (#455): each row once,
however many errors it has, and an error about the whole file (row 0) is
no row.

All rows are synthetic.
"""

import io

import pytest

from backend.tests.conftest import stub_daily_prices

HEADER = ("date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency,"
          "source,purpose,notes")
# The issue's row: a Buy without its cost basis, its fee in BTC (two errors)
TWO_ERRORS = "2024-01-10T10:00:00Z,Buy,0.01,Bank,Exchange BTC,,,0.0001,BTC,,,"
FUNDS = "2024-01-01T10:00:00Z,Deposit,1000,External,Bank,,,,,,,"
BUY = "2024-01-02T10:00:00Z,Buy,0.01,Bank,Exchange BTC,400.00,,,,,,"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 40000.0)


def preview(auth_client, rows: list[str]) -> dict:
    content = ("\n".join([HEADER, *rows]) + "\n").encode()
    r = auth_client.post("/api/import/preview", files={"file": ("import.csv", io.BytesIO(content), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_row_with_two_errors_is_one_row(auth_client):
    """The issue's file: one row, two errors, "0 valid / 1 total rows"."""
    data = preview(auth_client, [TWO_ERRORS])
    assert [(e["row_number"], e["column"]) for e in data["errors"]] == [(2, "cost_basis_usd"), (2, "fee_currency")]
    assert (data["valid_rows"], data["total_rows"]) == (0, 1)


def test_each_row_counts_once_beside_valid_ones(auth_client):
    data = preview(auth_client, [FUNDS, TWO_ERRORS, BUY])
    assert [e["row_number"] for e in data["errors"]] == [3, 3]
    assert (data["valid_rows"], data["total_rows"]) == (2, 3)


def test_an_error_about_the_whole_file_is_no_row(auth_client):
    """A header and no rows: its error is the file's (row 0), not a row of it."""
    data = preview(auth_client, [])
    assert [(e["row_number"], e["message"]) for e in data["errors"]] == [(0, "No valid transactions found in file.")]
    assert (data["valid_rows"], data["total_rows"]) == (0, 0)
