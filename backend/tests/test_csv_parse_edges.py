"""
The CSV parser on files and rows at the edges: no header, a header alone,
a byte that isn't UTF-8, rows out of date order, and a bad fee_usd_typed
value (it crashed the preview with a server error before 1.2.3).
"""

from backend.services.csv_import import parse_csv_file

HEADER = "date,type,amount,from_account,to_account,fee_amount,fee_currency,fee_usd,fee_usd_typed"


def parse(*rows):
    return parse_csv_file(("\n".join([HEADER, *rows]) + "\n").encode())


def test_an_unknown_fee_usd_typed_is_a_row_error():
    r = parse("2024-01-04T10:00:00Z,Transfer,0.05,Exchange BTC,Wallet,0.0001,BTC,4.20,maybe")
    assert [(e.row_number, e.column, e.message, e.severity) for e in r.errors] == [
        (2, "fee_usd_typed", "Invalid fee_usd_typed 'maybe'. Must be yes, no or blank.", "error"),
    ]
    assert r.transactions == []


def test_the_preview_reports_it(auth_client):
    csv = (HEADER + "\n2024-01-04T10:00:00Z,Transfer,0.05,Exchange BTC,Wallet,0.0001,BTC,4.20,maybe\n").encode()
    r = auth_client.post("/api/import/preview", files={"file": ("import.csv", csv, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["errors"][0]["message"] == "Invalid fee_usd_typed 'maybe'. Must be yes, no or blank."


def errors_of(content: bytes):
    return [(e.row_number, e.column, e.message) for e in parse_csv_file(content).errors]


def test_a_file_without_a_header():
    assert errors_of(b"") == [(0, None, "CSV file is empty or has no headers.")]


def test_a_header_missing_columns():
    assert errors_of(b"\n") == [
        (0, None, "Missing required columns: amount, date, from_account, to_account, type"),
    ]
    assert errors_of(b"date,type\n") == [(0, None, "Missing required columns: amount, from_account, to_account")]


def test_a_header_alone():
    assert errors_of(b"date,type,amount,from_account,to_account\n") == [
        (0, None, "No valid transactions found in file."),
    ]


def test_a_file_that_isnt_utf8_is_read_as_latin1():
    content = b"date,type,amount,from_account,to_account\n2024-01-01,Deposit,1,External,Bank\xff\n"
    assert errors_of(content) == [
        (2, "to_account", "Invalid account 'bank\xff'. Must be one of: Bank, Wallet, Exchange USD, Exchange BTC, External."),
    ]


def test_rows_out_of_date_order_are_a_warning():
    r = parse("2024-01-02T10:00:00Z,Deposit,100,External,Bank,,,,",
              "2024-01-01T10:00:00Z,Deposit,100,External,Bank,,,,")
    assert r.errors == []
    assert [(w.row_number, w.column, w.message) for w in r.warnings] == [
        (3, "date", "Row is not in chronological order. Import will sort by date."),
    ]
    assert len(r.transactions) == 2
