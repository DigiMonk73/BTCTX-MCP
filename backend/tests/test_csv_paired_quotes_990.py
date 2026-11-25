"""
#990: two stray quotes that close each other make a valid CSV file, and
the csv module reads everything between them as one cell: the rows between
vanish, and the row holding them takes a later row's columns (its
acquired_at among them), with no error. No cell of a correct row needs more
than one line, and BitcoinTX's own export writes none: so every import
(BitcoinTX's own, River's and each exchange's) refuses a file with a cell
over more than one line, naming its row and column (the owner's choice, A).
A line break is \\r, \\n or \\r\\n alike.
"""

import io
from pathlib import Path

import pytest

from backend.services.csv_import import CELL_OVER_LINES, CSV_COLUMNS, parse_csv_file, strict_rows
from backend.services.exchange_cells import records
from backend.services.river_import import parse_river_csv
from backend.tests.test_report_safety import store

ROOT = Path(__file__).resolve().parents[2]
RIVER = (ROOT / "testdata" / "exchange_files" / "river_bitcoin_activity.csv").read_text().splitlines()
STRIKE = (ROOT / "testdata" / "exchange_files" / "strike_activity.csv").read_text().splitlines()


def refused(row: int, column: str) -> str:
    return CELL_OVER_LINES.format(row=row, column=column)


def _messages(errors) -> list[str]:
    return [e.message for e in errors]


def _row(day: int, note: str) -> str:
    """A row as BitcoinTX's export writes it: a deposit of coins bought a
    year before, `note` written raw in its notes."""
    cells = dict.fromkeys(CSV_COLUMNS, "")
    cells.update(date=f"2024-01-{day:02d}T12:00:00Z", type="Deposit", amount="0.25000000", from_account="External",
                 to_account="Wallet", cost_basis_usd="5000.00", source="MyBTC", acquired_at=f"2023-01-{day:02d}",
                 notes=note)
    return ",".join(cells.values())


def _export(*notes: str) -> bytes:
    """A file of BitcoinTX's 24 columns: a row for each note, then two more."""
    rows = [_row(day, note) for day, note in enumerate([*notes, "", ""], start=1)]
    return "\n".join([",".join(CSV_COLUMNS), *rows]).encode() + b"\n"


def _river(tag_2: str, tag_3: str) -> bytes:
    """River's file, its Tag (the last column) written as given in rows 2 and 3."""
    return "\n".join([RIVER[0], RIVER[1].replace(",Buy", f",{tag_2}"), RIVER[2].replace(",Sell", f",{tag_3}"),
                      RIVER[3]]).encode() + b"\n"


def _strike(description_2: str, description_3: str) -> bytes:
    """Strike's file, its Description (column I) written as given in rows 2 and 3."""
    rows = [line.split(",") for line in STRIKE]
    rows[1][8], rows[2][8] = description_2, description_3
    return "\n".join(",".join(cells) for cells in rows).encode() + b"\n"


def test_the_issues_file_is_refused():
    """`"oops` in row 2's notes, `a 12"` in row 3's: read as valid CSV, row
    3 was gone and row 2 took its acquired_at."""
    result = parse_csv_file(_export('"oops', 'a 12"'))
    assert _messages(result.errors) == [refused(2, "L (notes)")]
    assert result.transactions == []


def test_the_same_file_without_the_quotes_reads_every_row():
    result = parse_csv_file(_export("oops", "a 12"))
    assert result.errors == [], _messages(result.errors)
    assert len(result.transactions) == 4


def test_rivers_file_is_refused():
    rows, errors = parse_river_csv(_river('"Buy', 'Sell"'))
    assert _messages(errors) == [refused(2, "H (Tag)")]
    assert rows == []


def test_an_exchanges_file_is_refused():
    """The header isn't known yet where the file is read (it may sit below
    an exchange's name and address): the column is named by its letter."""
    found = records(_strike('"Purchase', 'Purchase"'))
    assert not isinstance(found, list), found
    assert found.message == refused(2, "I")


@pytest.mark.parametrize("line_break", ["\n", "\r", "\r\n"], ids=["LF", "CR", "CRLF"])
def test_a_quoted_cell_over_lines_is_refused_whatever_its_line_break(line_break):
    """A note across lines, quoted as it should be, is refused too: no cell
    needs a line, and none can be told from joined rows."""
    note = f'"rent, March{line_break}and April"'
    assert _messages(parse_csv_file(_export("", note)).errors) == [refused(3, "L (notes)")]
    _, errors = parse_river_csv(_river("Buy", f'"Sell{line_break}x"'))
    assert _messages(errors) == [refused(3, "H (Tag)")]
    found = records(_strike("Purchase", f'"Purchase{line_break}x"'))
    assert not isinstance(found, list) and found.message == refused(3, "I"), found


def test_a_header_over_lines_is_named_by_its_letter():
    header = ",".join(CSV_COLUMNS).replace("proceeds_usd", '"proceeds\nusd"')
    text = "\n".join([header, _row(1, ""), _row(2, "")]) + "\n"
    assert _messages(parse_csv_file(text.encode()).errors) == [refused(1, "G")]


def test_rows_are_numbered_as_each_imports_other_errors():
    """BitcoinTX's and River's imports number rows without the blank lines
    (the csv module's DictReader skips them); the exchange import as a
    spreadsheet does."""
    rows = _export('"oops', 'a 12"').decode().split("\n")
    text = "\n".join([rows[0], "", *rows[1:]]).encode()
    assert _messages(parse_csv_file(text).errors) == [refused(2, "L (notes)")]
    assert records(text).message == refused(3, "L")
    river = _river('"Buy', 'Sell"').decode().split("\n")
    _, errors = parse_river_csv("\n".join([river[0], "", *river[1:]]).encode())
    assert _messages(errors) == [refused(2, "H (Tag)")]


@pytest.mark.parametrize("path", sorted((ROOT / "testdata").rglob("*.csv")), ids=lambda p: p.name)
def test_every_file_in_testdata_still_reads(path):
    found = records(path.read_bytes())
    assert isinstance(found, list), found


def test_each_preview_and_import_refuse_it_and_save_nothing(auth_client):
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    ours = {"file": ("rows.csv", _export('"oops', 'a 12"'), "text/csv")}
    preview = auth_client.post("/api/import/preview", files=ours).json()
    assert preview["can_import"] is False and _messages_of(preview) == [refused(2, "L (notes)")], preview
    assert auth_client.post("/api/import/execute", files=ours).status_code == 400
    river, strike = _river('"Buy', 'Sell"'), _strike('"Purchase', 'Purchase"')
    for url, file, form, column in (("/api/import/river/preview", river, {}, "H (Tag)"),
                                    ("/api/import/exchange/preview", river, {"mapping_id": "river"}, "H (Tag)"),
                                    ("/api/import/exchange/preview", strike, {"mapping_id": "strike"}, "I"),
                                    ("/api/import/exchange/columns", strike, {}, "I")):
        r = auth_client.post(url, files={"file": ("f.csv", io.BytesIO(file), "text/csv")}, data=form)
        found = r.json().get("errors") or [r.json()]
        assert [e.get("message", e.get("detail")) for e in found] == [refused(2, column)], (url, r.text)
    assert auth_client.get("/api/transactions").json() == []


def _messages_of(preview: dict) -> list[str]:
    return [e["message"] for e in preview["errors"]]


# What each column of BitcoinTX's export holds, and why it is one line:
# numbers and moments it writes itself; values the app lists; names it
# checks (_check_name; migration 0100 cleaned 1.x's); text checked on every
# new write; ids and amounts (chosen coins, joined with "; ").
ONE_LINE_BY_WRITING = {"date", "amount", "cost_basis_usd", "proceeds_usd", "fee_amount", "notes", "fee_usd",
                       "fmv_usd", "fee_usd_typed", "cost_basis_typed", "acquired_at", "proceeds_typed", "fmv_typed",
                       "id", "chosen_coins", "coins_chosen_at"}
ONE_LINE_BY_LIST = {"type", "broker_reporting", "price_moment"}
ONE_LINE_BY_NAME = {"from_account", "to_account"}
# Refused with a line break on every new write since 1.2.8; an older row's
# may hold one (an edit keeps a source or purpose as it is)
ONE_LINE_SINCE_CHECKED = {"source", "purpose", "fee_currency"}


def test_every_column_of_the_export_is_one_line_by_how_it_is_written():
    """The export writes CSV_COLUMNS (a DictWriter refuses a row with
    other keys): a column added to it is classed here, or this fails."""
    classed = ONE_LINE_BY_WRITING | ONE_LINE_BY_LIST | ONE_LINE_BY_NAME | ONE_LINE_SINCE_CHECKED
    assert set(CSV_COLUMNS) == classed


def test_the_reference_ledgers_export_has_no_cell_over_lines():
    """testdata/reference_ledger.csv is today's export of the reference
    ledger (test_reference_csv_844), every kind of transaction BitcoinTX
    has: it imports back (test_reference_csv_844) with no cell over lines."""
    rows = strict_rows((ROOT / "testdata" / "reference_ledger.csv").read_text())
    assert rows and not any("\n" in cell or "\r" in cell for cells in rows for cell in cells)


def test_an_older_rows_source_over_lines_is_named_when_its_export_comes_back(auth_client, test_engine):
    """A source stored before the one-line check (an edit keeps it as it
    is): the export writes it in its quoted cell, and the import refuses
    that file, naming the row and the column to put on one line."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    body = {"type": "Deposit", "timestamp": "2024-03-01T12:00:00Z", "from_account_id": 99, "to_account_id": 2,
            "amount": "0.1", "fee_amount": "0", "fee_currency": "BTC", "cost_basis_usd": "3000", "source": "MyBTC"}
    tx = auth_client.post("/api/transactions", json=body).json()
    store(test_engine, tx["id"], source="Old coins\r\nfrom 2015")
    export = auth_client.get("/api/backup/csv").text
    column = f"{chr(ord('A') + CSV_COLUMNS.index('source'))} (source)"
    assert _messages(parse_csv_file(export.encode()).errors) == [refused(2, column)]
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def test_columns_past_z_and_long_header_names_are_named_by_their_letters():
    wide = ",".join(["h"] * 27 + ["x" * 41]) + "\n" + ",".join([""] * 26 + ['"a\nb"', "1"]) + "\n"
    assert _messages(parse_csv_file(wide.encode()).errors) == [refused(2, "AA (h)")]
    long_name = ",".join(["h"] * 27 + ["x" * 41]) + "\n" + ",".join([""] * 27 + ['"a\nb"']) + "\n"
    assert _messages(parse_csv_file(long_name.encode()).errors) == [refused(2, "AB")]
