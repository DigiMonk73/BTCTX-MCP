"""
#952: a cell whose quote is never closed swallowed every row after it into
that cell, and the import said nothing: the CSV module's lenient reading
ends the cell at the end of the file. A file like that is refused, with
the reason, by every reader of a CSV file: BitcoinTX's own import, River's
and any exchange's. So is a closing quote followed by more text, which was
read with the quotes dropped; and, by BitcoinTX's own import and River's
(whose headers give a row's width), a stray quote that a second one further
down closes, which reads the rows between as one cell. A cell holding a
line break or a doubled quote, as BitcoinTX's own export writes them, still
reads.
"""

from backend.services.csv_import import parse_csv_file
from backend.services.exchange_cells import records
from backend.services.river_import import parse_river_csv

HEADER = "date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency,source,purpose,notes"
NEVER_CLOSED = "The file can't be read as CSV: a cell opens a quote (\") that is never closed."
TEXT_AFTER = "The file can't be read as CSV: a cell has more text after its closing quote (\"), even a space."

# The issue's file: the second row's notes open a quote and never close it.
THREE_ROWS = (
    f"{HEADER}\n"
    "2024-01-05,Deposit,1000,External,Bank,,,,,N/A,,first\n"
    "2024-01-06,Deposit,0.5,External,Wallet,20000,,,,MyBTC,,\"oops\n"
    "2024-01-07,Withdrawal,0.1,Wallet,External,,5000,0,BTC,,Spent,third\n"
)

RIVER_HEADER = "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag"


def _messages(errors) -> list[str]:
    return [e.message for e in errors]


def test_an_unclosed_quote_refuses_the_file():
    result = parse_csv_file(THREE_ROWS.encode())
    assert _messages(result.errors) == [NEVER_CLOSED]
    assert result.transactions == []


def test_text_after_a_closing_quote_refuses_the_file():
    text = f"{HEADER}\n2024-01-05,Deposit,1000,External,Bank,,,,,N/A,,\"one\"two\n"
    assert _messages(parse_csv_file(text.encode()).errors) == [TEXT_AFTER]


def test_a_space_after_a_closing_quote_refuses_the_file():
    text = f"{HEADER}\n2024-01-05,Deposit,1000,External,Bank,,,,,N/A,,\"note\" \n"
    assert _messages(parse_csv_file(text.encode()).errors) == [TEXT_AFTER]


# A second stray quote, before a line break, closes the first: the rows between vanish into one cell.
PAIRED = (
    f"{HEADER}\n"
    "2024-01-05,Deposit,1000,External,Bank,,,,,N/A,,\"oops\n"
    "2024-01-06,Deposit,500,External,Bank,,,,,N/A,,second\n"
    "2024-01-07,Deposit,700,External,Bank,,,,,N/A,,a 12\"\n"
    "2024-01-08,Deposit,900,External,Bank,,,,,N/A,,fourth\n"
)
SWALLOWED = ("The file can't be read as CSV: a cell in row 2 holds the rows after it,"
             " between two quotes (\") out of place.")


def test_two_stray_quotes_that_close_each_other_refuse_the_file():
    result = parse_csv_file(PAIRED.encode())
    assert _messages(result.errors) == [SWALLOWED]
    assert result.transactions == []


def test_rivers_import_refuses_two_stray_quotes():
    text = (f"{RIVER_HEADER}\n2026-01-05 12:00:00,25.00,USD,0.00030000,BTC,,,\"Buy\n"
            "2026-01-12 12:00:00,25.00,USD,0.00031000,BTC,,,Buy\"\n"
            "2026-01-19 12:00:00,25.00,USD,0.00032000,BTC,,,Buy\n")
    rows, errors = parse_river_csv(text.encode())
    assert _messages(errors) == [SWALLOWED]
    assert rows == []


def test_an_exchanges_note_with_a_line_break_and_commas_still_reads():
    """An exchange's file has few columns: a correct note across two lines
    with a comma is never taken for rows held in a cell."""
    found = records(b'Date,Note\n2026-01-05,"Bought\nfrom Bob, Alice"\n2026-01-06,x\n')
    assert isinstance(found, list), found
    assert [cells for _, cells in found][1:] == [["2026-01-05", "Bought\nfrom Bob, Alice"], ["2026-01-06", "x"]]


def test_a_note_with_a_line_break_and_a_comma_still_reads():
    text = f"{HEADER}\n2024-01-05,Deposit,1000,External,Bank,,,,,N/A,,\"rent, March\nand April, paid\"\n"
    result = parse_csv_file(text.encode())
    assert result.errors == [], _messages(result.errors)


def test_a_cell_with_a_line_break_or_a_doubled_quote_still_reads():
    text = (f"{HEADER}\n2024-01-05,Deposit,1000,External,Bank,,,,,N/A,,\"a \"\"rent\"\"\nnote\"\n"
            "2024-01-06,Deposit,500,External,Bank,,,,,N/A,,plain\n")
    result = parse_csv_file(text.encode())
    assert result.errors == [], _messages(result.errors)
    assert len(result.transactions) == 2


def test_the_preview_and_the_import_refuse_it_and_save_nothing(auth_client):
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    file = {"file": ("rows.csv", THREE_ROWS.encode(), "text/csv")}
    preview = auth_client.post("/api/import/preview", files=file).json()
    assert preview["can_import"] is False, preview
    assert NEVER_CLOSED in [e["message"] for e in preview["errors"]], preview["errors"]
    assert auth_client.post("/api/import/execute", files=file).status_code == 400
    assert auth_client.get("/api/transactions").json() == []


def test_rivers_import_refuses_an_unclosed_quote():
    text = (f"{RIVER_HEADER}\n2026-01-05 12:00:00,25.00,USD,0.00030000,BTC,,,\"Buy\n"
            "2026-01-12 12:00:00,25.00,USD,0.00031000,BTC,,,Buy\n")
    rows, errors = parse_river_csv(text.encode())
    assert _messages(errors) == [NEVER_CLOSED]
    assert rows == []


def test_an_exchanges_file_with_an_unclosed_quote_is_refused():
    found = records(b"Date,Amount,Note\n2026-01-05,0.1,\"open\n2026-01-06,0.2,x\n")
    assert not isinstance(found, list), found
    assert found.message == NEVER_CLOSED
