"""
#990: two stray quotes that close each other make a valid CSV file, and
the csv module reads everything between them as one cell: the rows between
vanish, and the row holding them takes a later row's columns (its
acquired_at among them), with no error. A file like that is refused, with
the reason, by every reader of a CSV file (BitcoinTX's own import, River's
and any exchange's), as #952 refuses a quote never closed: a line inside a
cell that starts as the file's rows do gives it away. A correct note
across lines, commas and all, still reads.
"""

from pathlib import Path

import pytest

from backend.services.csv_import import CSV_COLUMNS, parse_csv_file
from backend.services.exchange_cells import records
from backend.services.river_import import parse_river_csv

ROOT = Path(__file__).resolve().parents[2]
NOTES = CSV_COLUMNS.index("notes")  # the export's 12th of 24 columns
JOINED = ("The file can't be read as CSV: row {row} has a cell holding, after a line break, what starts like"
          " another row (“{start}”). Two stray quotes (\") may have joined rows into that cell: remove them,"
          " or write each twice (\"\"). If that cell is a note across lines, start that line with a word instead.")


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
    """A file of BitcoinTX's export: a row for each note, then two more."""
    rows = [_row(day, note) for day, note in enumerate([*notes, "", ""], start=1)]
    return "\n".join([",".join(CSV_COLUMNS), *rows]).encode() + b"\n"


def test_the_issues_file_two_neighbouring_rows_is_refused():
    """Row 3's notes `"oops`, row 4's `a 12"`: read as valid CSV, row 4 is
    gone and row 3 takes its acquired_at."""
    result = parse_csv_file(_export("", '"oops', 'a 12"'))
    assert _messages(result.errors) == [JOINED.format(row=3, start="2024-01-03T12:00:00Z")]
    assert result.transactions == []


def test_a_whole_row_between_the_quotes_is_refused():
    result = parse_csv_file(_export('"oops', "", 'a 12"'))
    assert _messages(result.errors) == [JOINED.format(row=2, start="2024-01-02T12:00:00Z")]
    assert result.transactions == []


def test_the_same_file_without_the_quotes_reads_every_row():
    """The control: the file the quotes were typed into."""
    result = parse_csv_file(_export("", "oops", "a 12"))
    assert result.errors == [], _messages(result.errors)
    assert len(result.transactions) == 5


def test_rivers_import_refuses_it():
    river = (ROOT / "testdata" / "exchange_files" / "river_bitcoin_activity.csv").read_text().splitlines()
    # The stray quotes in the Tag column, the last: row 2's closes row 3's
    text = "\n".join([river[0], river[1].replace(",Buy", ',"Buy'), river[2].replace(",Sell", ',Sell"'), river[3]])
    rows, errors = parse_river_csv(text.encode())
    assert _messages(errors) == [JOINED.format(row=2, start=river[2].split(",")[0])]
    assert rows == []


def test_an_exchanges_file_is_refused_by_its_dates():
    """Strike's first column is an id, its second the time: a column
    other than the first gives the row away."""
    strike = (ROOT / "testdata" / "exchange_files" / "strike_activity.csv").read_text().splitlines()
    second = strike[2].split(",")
    second[0] = "b0c1d2e3-0000-4000-8000-00000000000f"  # an id with letters, as Strike's are: shaped as no other
    second[8] = 'Purchase"'
    text = "\n".join([strike[0], strike[1].replace(",Purchase,100000.00,", ',"Purchase,100000.00,'),
                      ",".join(second), strike[3]])
    found = records(text.encode())
    assert not isinstance(found, list), found
    assert found.message == JOINED.format(row=2, start=second[1])


def test_a_second_quote_in_an_earlier_column_is_refused():
    """Strike's statement: the Note (its last column) opens a quote that the
    next row's Description closes. The row holding them is two cells wider
    than the file's, both empty, which the exchange import lets by; the
    joined line holds fewer cells than come before the Note (the review of
    #990)."""
    strike = (ROOT / "testdata" / "exchange_files" / "strike_statement.csv").read_text().splitlines()
    sale = strike[3].split(",")
    sale[10] = 'Sale 12"'
    text = "\n".join([*strike[:2], strike[2] + '"for rent', ",".join(sale), *strike[4:]])
    found = records(text.encode())
    assert not isinstance(found, list), found
    assert found.message == JOINED.format(row=3, start=sale[0])


def test_a_second_quote_ending_a_rows_first_cell_is_refused():
    """The joined line's last cell is a whole one: strict reading ends it
    at the stray quote. Here it is the Sale's Reference (the re-check of
    #990)."""
    strike = (ROOT / "testdata" / "exchange_files" / "strike_statement.csv").read_text().splitlines()
    sale = strike[3].split(",")
    text = "\n".join([*strike[:2], strike[2] + '"for rent', sale[0] + '",' + ",".join(sale[1:]), *strike[4:]])
    found = records(text.encode())
    assert not isinstance(found, list), found
    assert found.message == JOINED.format(row=3, start=sale[0])


def test_a_correct_note_in_a_row_wider_than_the_others_still_reads():
    """A hand-written file whose rows leave the later columns off, but for
    one, whose note has a line starting with a date and a comma: no wider
    than the header, it isn't taken for joined rows (the re-check of #990)."""
    header = ",".join(CSV_COLUMNS[:CSV_COLUMNS.index("acquired_at") + 1])
    deposit = "2024-01-0{day}T12:00:00Z,Deposit,0.{day},External,Wallet,{day}000,,,,MyBTC,,"
    text = "\n".join([
        header,
        deposit.format(day=1) + "first",
        deposit.format(day=2) + '"Old coins\n2023-01-05T12:00:00Z, bought on an exchange",,,,,,2023-01-05',
        deposit.format(day=3) + "third",
        deposit.format(day=4) + "fourth",
    ]) + "\n"
    result = parse_csv_file(text.encode())
    assert result.errors == [], _messages(result.errors)
    assert len(result.transactions) == 4


def test_a_quote_opened_in_the_header_is_refused():
    """The header's proceeds_usd opens a quote the first row's type closes:
    the header takes the row's later columns, and the row is gone."""
    header = ",".join(CSV_COLUMNS).replace("proceeds_usd", '"proceeds_usd')
    first = _row(1, "").replace(",Deposit,", ',Deposit",', 1)
    text = "\n".join([header, first, _row(2, ""), _row(3, "")]) + "\n"
    result = parse_csv_file(text.encode())
    assert _messages(result.errors) == [JOINED.format(row=1, start="2024-01-01T12:00:00Z")]


def test_a_blank_line_counts_as_the_other_errors_count_it():
    """BitcoinTX's import numbers its rows without the blank lines, as the
    csv module's DictReader reads them: so does this error."""
    rows = _export("", '"oops', 'a 12"').decode().split("\n")
    text = "\n".join([rows[0], "", *rows[1:]])
    assert _messages(parse_csv_file(text.encode()).errors) == [JOINED.format(row=3, start="2024-01-03T12:00:00Z")]


def test_a_narrow_exchange_file_is_refused():
    found = records(b'Date,Amount,Note\n2026-01-05,0.1,"open\n2026-01-06,0.2,x\n2026-01-07,0.3,y"\n')
    assert not isinstance(found, list), found
    assert found.message == JOINED.format(row=2, start="2026-01-06")


@pytest.mark.parametrize("note", [
    '"rent, March\nand April, paid"',
    '"a ""rent""\nnote"',
    '"Paid on\n2024-01-07, the second half"',  # a date, but not the row's 11 cells before its notes
    '"line one\n\nline three, with a comma"',
    '"3, then\n12345678, an id"',
])
def test_a_correct_note_across_lines_still_reads(note):
    result = parse_csv_file(_export("", note))
    assert result.errors == [], _messages(result.errors)
    assert len(result.transactions) == 4


@pytest.mark.parametrize("note", [
    '"Bought\nfrom Bob, Alice"',
    '"Bought\nfrom Bob, Alice, and Carol"',
    '"Bought\n0.1, from Bob, and Alice"',  # an amount, but too short to tell from a note's number
    '"Bought\n2026 01 05, from Bob, and Alice"',  # a date, written as the file's dates aren't
])
def test_an_exchanges_note_across_lines_still_reads(note):
    found = records(f"Date,Amount,Note\n2026-01-05,0.1,{note}\n2026-01-06,0.2,x\n".encode())
    assert isinstance(found, list), found
    assert len(found) == 3


@pytest.mark.parametrize("path", sorted((ROOT / "testdata").rglob("*.csv")), ids=lambda p: p.name)
def test_every_file_in_testdata_still_reads(path):
    found = records(path.read_bytes())
    assert isinstance(found, list), found


def test_the_preview_and_the_import_refuse_it_and_save_nothing(auth_client):
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    file = {"file": ("rows.csv", _export("", '"oops', 'a 12"'), "text/csv")}
    preview = auth_client.post("/api/import/preview", files=file).json()
    assert preview["can_import"] is False, preview
    assert any("joined rows" in e["message"] for e in preview["errors"]), preview["errors"]
    assert auth_client.post("/api/import/execute", files=file).status_code == 400
    assert auth_client.get("/api/transactions").json() == []
