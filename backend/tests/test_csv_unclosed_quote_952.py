"""
#952: a cell whose quote is never closed swallowed every row after it into
that cell, and the import said nothing: the CSV module's lenient reading
ends the cell at the end of the file. A file like that is refused, with
the reason, by every reader of a CSV file: BitcoinTX's own import, River's
and any exchange's. So is a closing quote followed by more text, which was
read with the quotes dropped. A cell holding a line break or a doubled
quote, as BitcoinTX's own export writes them, still reads.
"""

from backend.services.csv_import import parse_csv_file
from backend.services.exchange_cells import records
from backend.services.river_import import parse_river_csv

HEADER = "date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency,source,purpose,notes"
NEVER_CLOSED = "The file can't be read as CSV: a cell opens a quote (\") that is never closed."
TEXT_AFTER = "The file can't be read as CSV: a cell has more text after its closing quote (\")."

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
    assert auth_client.post("/api/import/execute", files=file).status_code != 200
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
