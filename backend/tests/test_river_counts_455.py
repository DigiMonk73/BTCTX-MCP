"""
#455: the River import's preview counted only the rows it could read
("N rows in file"), and an Import refusal numbered the rows by their place
among the ticked rows, so it named another row than the preview had.

All rows are synthetic.
"""

import io

import pytest

from backend.tests.conftest import stub_daily_prices

RIVER_HEADER = (
    "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,"
    "Fee Amount,Fee Currency,Tag"
)
KEYS = ("row_number", "date", "type", "amount", "from_account", "to_account", "cost_basis_usd",
        "proceeds_usd", "fee_amount", "fee_currency", "source", "purpose")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 100000.0)


@pytest.fixture
def client(auth_client):
    r = auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    assert r.status_code in (200, 204)
    return auth_client


def preview(client, rows: list[str]) -> dict:
    content = ("\n".join([RIVER_HEADER, *rows]) + "\n").encode()
    r = client.post("/api/import/river/preview",
                    files={"file": ("river.csv", io.BytesIO(content), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


def test_rows_in_file_counts_the_rows_it_could_not_read(client):
    """The issue's file: 12 rows with an unquoted thousands comma, 3 good."""
    bad = [f"2024-01-{day:02d} 10:00:00,1,000.00,USD,0.01,BTC,,USD,Buy" for day in range(1, 13)]
    good = [f"2024-01-{day:02d} 10:00:00,100.00,USD,0.0025,BTC,1.00,USD,Buy" for day in range(13, 16)]
    data = preview(client, bad + good)
    assert data["total_rows"] == 15
    assert [e["row_number"] for e in data["errors"]] == list(range(2, 14))
    assert [p["row_number"] for p in data["proposals"]] == [14, 15, 16]


def test_rows_in_file_counts_every_kind_of_row(client):
    """A row refused for its date, for a number, for an extra field, and one
    the import reads but proposes nothing for (a warning): each is a row of
    the file."""
    data = preview(client, [
        "2024-01-01 10:00:00,100.00,USD,0.0025,BTC,,,Buy",   # row 2: read
        "01/02/2024,100.00,USD,0.0025,BTC,,,Buy",            # row 3: its date
        "2024-01-03 10:00:00,abc,USD,0.0025,BTC,,,Buy",      # row 4: a number
        "2024-01-04 10:00:00,100.00,USD,0.0025,BTC,,,Buy,",  # row 5: an extra field
        "2024-01-05 10:00:00,,,,,,,",                         # row 6: nothing to propose
    ])
    assert data["total_rows"] == 5
    assert [e["row_number"] for e in data["errors"]] == [3, 4, 5]
    assert [w["row_number"] for w in data["warnings"]] == [6]
    assert [p["row_number"] for p in data["proposals"]] == [2]


def test_an_import_refusal_names_the_rows_file_number(client):
    """The issue's second file: the untagged receive (file row 4) made a
    Deposit with no cost basis. The refusal named it "Row 3", its place among
    the rows sent."""
    data = preview(client, [
        "2024-01-01 10:00:00,100.00,USD,0.0025,BTC,,,Buy",
        "2024-01-02 10:00:00,100.00,USD,0.0025,BTC,,,Buy",
        "2024-01-03 10:00:00,,,0.00100000,BTC,,,",
        "2024-01-04 10:00:00,0.00100000,BTC,,,0.00000500,BTC,",
    ])
    rows = [{k: p[k] for k in KEYS} for p in data["proposals"]]
    receive = next(row for row in rows if row["row_number"] == 4)
    receive.update(type="Deposit", from_account="External", source="MyBTC", cost_basis_usd=None)

    r = client.post("/api/import/river/execute", json={"rows": rows})
    assert r.status_code == 400
    assert "Row 4: Enter this deposit's cost basis" in r.json()["detail"]


def test_a_row_left_unticked_before_it_doesnt_move_its_number(client):
    """The rows the owner unticked aren't sent: a refused row keeps its number."""
    data = preview(client, [
        "2024-01-01 10:00:00,100.00,USD,0.0025,BTC,,,Buy",
        "2024-01-02 10:00:00,100.00,USD,0.0025,BTC,,,Buy",
        "2024-01-03 10:00:00,,,0.00100000,BTC,,,",
    ])
    rows = [{k: p[k] for k in KEYS} for p in data["proposals"] if p["row_number"] != 2]
    rows[-1].update(type="Deposit", from_account="External", source="MyBTC", cost_basis_usd=None)

    r = client.post("/api/import/river/execute", json={"rows": rows})
    assert r.status_code == 400
    assert "Row 4: Enter this deposit's cost basis" in r.json()["detail"]
