"""
#988: a file whose lines end in a carriage return alone (CR, as an old
Mac's "CSV (Macintosh)" saves it) was refused by every import with the csv
module's own words ("new-line character seen in unquoted field - do you
need to open the file with newline=''?"). Such a file now reads exactly as
the same file with LF line ends. A CR alone in a file whose lines end in LF
(inside a cell that isn't quoted, or a line ended another way) is still
refused, in plain words naming its line: reading it as a line's end would
split that row in two, and the first half could lose its later columns
(its date acquired among them).
"""

import csv
import io
from pathlib import Path

import pytest

from backend.services.csv_import import CELL_OVER_LINES, CSV_COLUMNS, STRAY_CR, parse_csv_file, unreadable_csv
from backend.services.exchange_cells import records
from backend.services.river_import import parse_river_csv

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / "testdata" / "exchange_files"
RIVER = (FILES / "river_bitcoin_activity.csv").read_bytes()
STRIKE = (FILES / "strike_activity.csv").read_bytes()
CSV_MODULES_WORDS = "newline="


def _ours() -> bytes:
    """BitcoinTX's own 24 columns: two deposits, with a date acquired, and a sale."""
    rows = []
    for day, kind in ((1, "Deposit"), (2, "Deposit"), (3, "Sell")):
        cells = dict.fromkeys(CSV_COLUMNS, "")
        cells.update(date=f"2024-01-0{day}T12:00:00Z", type=kind, amount="0.25000000")
        if kind == "Deposit":
            cells.update(from_account="External", to_account="Exchange BTC", cost_basis_usd="5000.00",
                         source="MyBTC", acquired_at=f"2023-01-0{day}")
        else:
            cells.update(from_account="Exchange BTC", to_account="Exchange USD", proceeds_usd="9000.00")
        rows.append(",".join(cells.values()))
    return "\n".join([",".join(CSV_COLUMNS), *rows]).encode() + b"\n"


def cr_only(content: bytes) -> bytes:
    """The same file, each line ended by CR alone."""
    return content.replace(b"\r\n", b"\n").replace(b"\n", b"\r")


def _messages(errors) -> list[str]:
    return [e.message for e in errors]


def test_bitcointxs_own_file_with_cr_line_ends_reads_as_with_lf():
    lf, cr = parse_csv_file(_ours()), parse_csv_file(cr_only(_ours()))
    assert lf.errors == [] and len(lf.transactions) == 3, _messages(lf.errors)
    assert (cr.errors, cr.warnings, cr.transactions, cr.previews) == (lf.errors, lf.warnings, lf.transactions,
                                                                       lf.previews)


def test_rivers_file_with_cr_line_ends_reads_as_with_lf():
    lf, cr = parse_river_csv(RIVER), parse_river_csv(cr_only(RIVER))
    assert lf[1] == [] and lf[0], lf[1]
    assert cr == lf


def test_an_exchanges_file_with_cr_line_ends_reads_as_with_lf():
    lf = records(STRIKE)
    assert isinstance(lf, list) and lf, lf
    assert records(cr_only(STRIKE)) == lf


def test_crlf_and_a_bom_still_read():
    content = b"\xef\xbb\xbf" + _ours().replace(b"\n", b"\r\n")
    result = parse_csv_file(content)
    assert result.errors == [] and len(result.transactions) == 3, _messages(result.errors)


def test_a_cell_over_lines_in_a_cr_file_is_refused_naming_it():
    """A quoted cell holding a CR in a CR file: a cell over lines (#990)."""
    content = cr_only(_ours()).replace(b"MyBTC", b'"My\rBTC"', 1)
    expected = CELL_OVER_LINES.format(row=2, column="J (source)")
    assert _messages(parse_csv_file(content).errors) == [expected]


def _stray_cr(content: bytes, line: int) -> bytes:
    """`content` (LF line ends) with a CR alone inside the first cell of its `line`."""
    lines = content.split(b"\n")
    lines[line - 1] = lines[line - 1][:2] + b"\r" + lines[line - 1][2:]
    return b"\n".join(lines)


@pytest.mark.parametrize("line", [1, 3])
def test_a_cr_alone_in_a_file_of_lf_lines_is_refused_naming_its_line(line):
    expected = STRAY_CR.format(place=f"line {line}")
    assert _messages(parse_csv_file(_stray_cr(_ours(), line)).errors) == [expected]
    rows, errors = parse_river_csv(_stray_cr(RIVER, line))
    assert rows == [] and _messages(errors) == [expected]
    found = records(_stray_cr(STRIKE, line))
    assert not isinstance(found, list) and found.message == expected, found


def test_a_line_ended_by_cr_alone_among_crlf_lines_is_refused_naming_it():
    content = _ours().replace(b"\n", b"\r\n")
    lines = content.split(b"\r\n")
    content = b"\r\n".join(lines[:2]) + b"\r" + b"\r\n".join(lines[2:])
    assert _messages(parse_csv_file(content).errors) == [STRAY_CR.format(place="line 2")]


def test_the_message_is_in_plain_words():
    assert CSV_MODULES_WORDS not in STRAY_CR and "CR" in STRAY_CR and "{place}" in STRAY_CR


def test_a_cr_file_with_a_line_feed_in_a_quoted_cell_is_refused_in_true_words():
    """No LF ends its lines, but one is in a cell: left as it is, its first
    CR is refused, the message true of it too (the review of #988)."""
    found = parse_csv_file(b'date,type\r"x\ny",Deposit\r1,2\r').errors
    assert _messages(found) == [STRAY_CR.format(place="line 1")]


def test_the_message_without_a_line_says_a_line():
    error = unreadable_csv(csv.Error("new-line character seen in unquoted field - do you need to open the file"
                                     " with newline=''?"))
    assert error.message == STRAY_CR.format(place="a line")


def test_each_preview_reads_a_cr_file(auth_client):
    ours = auth_client.post("/api/import/preview", files={"file": ("ours.csv", cr_only(_ours()), "text/csv")})
    assert ours.status_code == 200 and ours.json()["errors"] == [], ours.text
    assert len(ours.json()["transactions"]) == 3
    for url, form in (("/api/import/river/preview", {}), ("/api/import/exchange/preview", {"mapping_id": "strike"}),
                      ("/api/import/exchange/columns", {})):
        content = RIVER if "river" in url else STRIKE
        lf = auth_client.post(url, files={"file": ("f.csv", io.BytesIO(content), "text/csv")}, data=form).json()
        cr = auth_client.post(url, files={"file": ("f.csv", io.BytesIO(cr_only(content)), "text/csv")},
                              data=form).json()
        assert cr == lf and not any(CSV_MODULES_WORDS in e["message"] for e in cr.get("errors", [])), (url, cr)
