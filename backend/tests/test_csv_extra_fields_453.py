"""
A CSV row with more fields than the header (#453). An amount written with a
thousands comma and no quotes (20,000.00) is two fields, 20 and 000.00, and
every column after it moves one place: the import read it so and dropped
the last field, with no error, and a $20,000 basis was saved as $20. Such a
row is refused, in the preview and at Import, naming its row and saying
why, as River's import does. A row with fewer fields is read as before (it
can't be told from one whose last cells are blank), and the CSV export
still imports as it was (#230).
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import first_run, outbound
from backend.services.csv_import import parse_csv_file
from backend.tests.test_seed_ledger import PASSWORD, USER, reference_figures, seed_ledger

HEADER = ("date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency,"
          "source,purpose,notes")
# #453's row: a My BTC deposit whose cost basis is typed 20,000.00, no quotes
SHIFTED = "2024-01-10T10:00:00Z,Deposit,1.0,External,Wallet,20,000.00,,,,MyBTC,,Moved from my old wallet"
EXTRA_FIELDS = ("This row has more fields than the header: a stray comma, or an amount written with a comma "
                "(write 1000.00, not 1,000.00)?")
REFUSED = [(2, None, EXTRA_FIELDS, "error")]


def csv_bytes(*rows: str) -> bytes:
    return ("\n".join([HEADER, *rows]) + "\n").encode()


def errors_of(result):
    return [(e.row_number, e.column, e.message, e.severity) for e in result.errors]


def csv_file(content: bytes):
    return {"file": ("import.csv", content, "text/csv")}


@pytest.mark.parametrize("row", [
    SHIFTED,
    # The same with its notes blank: the field past the header is empty,
    # but the basis, proceeds and source were still read from the wrong columns
    "2024-01-10T10:00:00Z,Deposit,1.0,External,Wallet,20,000.00,,,,MyBTC,,",
    # Two extra fields: a Sell's proceeds and its fee, each with a comma
    "2024-01-10T10:00:00Z,Sell,0.5,Exchange BTC,Exchange USD,,45,000.00,1,250.00,USD,,,",
    # A stray comma at the end of a row
    "2024-01-10T10:00:00Z,Deposit,1000,External,Bank,,,,,,,,",
], ids=["453s-row", "blank-extra-field", "two-extra-fields", "stray-comma-at-the-end"])
def test_a_row_with_more_fields_than_the_header_is_refused(row):
    result = parse_csv_file(csv_bytes(row))
    assert errors_of(result) == REFUSED
    assert result.transactions == [] and result.previews == [] and not result.can_import


def test_only_that_row_is_refused_and_named():
    result = parse_csv_file(csv_bytes(
        "2024-01-09T10:00:00Z,Deposit,1000,External,Bank,,,,,,,",
        SHIFTED,
        "2024-01-11T10:00:00Z,Deposit,500,External,Bank,,,,,,,",
    ))
    assert errors_of(result) == [(3, None, EXTRA_FIELDS, "error")]
    assert [p.row_number for p in result.previews] == [2, 4]
    assert not result.can_import


def test_a_row_with_fewer_fields_is_read_with_its_last_cells_blank():
    result = parse_csv_file(csv_bytes("2024-01-10T10:00:00Z,Deposit,1.0,External,Wallet,20000.00,,,,MyBTC"))
    assert result.errors == [] and result.can_import
    [preview] = result.previews
    assert (str(preview.cost_basis_usd), preview.source, preview.purpose, preview.notes) == \
        ("20000.00", "MyBTC", None, None)


def test_the_amount_in_quotes_is_read_whole():
    """What the error's advice leads to: quoted, the comma stays in its cell."""
    result = parse_csv_file(csv_bytes(
        '2024-01-10T10:00:00Z,Deposit,1.0,External,Wallet,"20,000.00",,,,MyBTC,,Moved from my old wallet'))
    assert result.errors == []
    [preview] = result.previews
    assert (str(preview.cost_basis_usd), preview.source, preview.notes) == \
        ("20000.00", "MyBTC", "Moved from my old wallet")


def test_the_preview_names_the_row(auth_client):
    r = auth_client.post("/api/import/preview", files=csv_file(csv_bytes(SHIFTED)))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["errors"] == [{"row_number": 2, "column": None, "message": EXTRA_FIELDS, "severity": "error"}]
    assert (body["can_import"], body["valid_rows"], body["transactions"]) == (False, 0, [])


def test_the_import_refuses_it_and_saves_nothing(auth_client):
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    r = auth_client.post("/api/import/execute", files=csv_file(csv_bytes(SHIFTED)))
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == f"CSV has errors: Row 2: {EXTRA_FIELDS}"
    assert auth_client.get("/api/transactions").json() == []


@pytest.fixture
def reference_ledger(fresh_app, monkeypatch):
    """A fresh install claimed and seeded with the reference test ledger,
    price source Off; yields (client, Session)."""
    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings(price_source="off"))
    c = TestClient(app)
    seed_ledger.log_in(c, USER, PASSWORD, first_run.ensure_code())
    assert seed_ledger.seed(c) == len(seed_ledger.ledger_rows())
    yield c, fresh_app


def test_the_reference_ledgers_export_imports_as_it_was(reference_ledger):
    c, Session = reference_ledger
    with Session() as db:
        before = reference_figures.figures(db)
    exported = c.get("/api/backup/csv").content
    assert c.delete("/api/transactions/delete_all?confirm=DELETE").status_code == 204
    preview = c.post("/api/import/preview", files=csv_file(exported)).json()
    assert preview["errors"] == [] and preview["valid_rows"] == len(seed_ledger.ledger_rows())
    r = c.post("/api/import/execute", files=csv_file(exported))
    assert r.status_code == 200, r.text
    with Session() as db:
        moved = list(reference_figures.differences(before, reference_figures.figures(db)))
    assert not moved, "figures moved in the round trip:\n" + "\n".join(moved[:20])
