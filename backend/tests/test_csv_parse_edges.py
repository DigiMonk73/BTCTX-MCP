"""
The CSV parser on files and rows at the edges: a bad fee_usd_typed value
(it crashed the preview with a server error before 1.2.3).
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
