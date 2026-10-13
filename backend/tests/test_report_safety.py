"""
backend/tests/test_report_safety.py

Ledger text in the reports is data, never instructions:
- PDF: a ReportLab Paragraph reads markup, so a stored value such as
  <img src="http://..."/> made ReportLab fetch that URL (or open a local
  file) while building the transaction history. Now every value is escaped,
  ReportLab trusts no URL, and the text is printed as written.
- CSV: a text cell starting with = + - @ runs as a formula in a spreadsheet;
  it now starts with '. Numbers (a -120.00 loss) are left alone. A line
  break in stored text stays inside its quoted cell, so the text after it
  never starts a row of its own.
- A purpose or source with a line break (or another control character), and
  a fee currency other than USD or BTC, are refused on every new write.
- A deposit's source is one of the listed values on every new write; older
  rows with other text still load, recalculate and survive an edit.
"""

import csv
import io
import socket
import threading
from decimal import Decimal, InvalidOperation

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate
from sqlalchemy import text

from backend.main import app
from backend.services.csv_import import parse_csv_file
from backend.services.reports.complete_tax_report import generate_comprehensive_tax_report
from backend.services.reports.safe_text import csv_text

CLIENT: TestClient = None
BANK, WALLET, EXTERNAL = 1, 2, 99


@pytest.fixture(autouse=True, scope="module")
def _set_client(auth_client):
    global CLIENT
    CLIENT = auth_client


@pytest.fixture(autouse=True)
def _clean_ledger():
    CLIENT.delete("/api/transactions/delete_all")
    yield
    CLIENT.delete("/api/transactions/delete_all")


@pytest.fixture
def listener():
    """A local HTTP-ish server that counts the connections made to it."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    srv.settimeout(0.2)
    hits = []
    stop = threading.Event()

    def serve():
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except OSError:
                continue
            hits.append(1)
            conn.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    yield srv.getsockname()[1], hits
    stop.set()
    t.join()
    srv.close()


def pdf_text(content: bytes) -> str:
    """The PDF's text with all whitespace removed (table cells wrap)."""
    raw = "".join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages)
    return "".join(raw.split())


def store(test_engine, tx_id: int, **fields):
    """Write straight to the row: what an older version, a restored backup or
    a hand-edited database could hold."""
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    with test_engine.begin() as con:
        con.execute(text(f"UPDATE transactions SET {sets} WHERE id = :id"), {"id": tx_id, **fields})


def usd_deposit(**fields):
    body = {"type": "Deposit", "timestamp": "2024-03-01T12:00:00Z", "from_account_id": EXTERNAL,
            "to_account_id": BANK, "amount": "100", "fee_amount": "0", "fee_currency": "USD", **fields}
    r = CLIENT.post("/api/transactions", json=body)
    assert r.status_code == 200, r.text
    return r.json()


# Cash out of the bank: its purpose is free text, kept as written
USD_WITHDRAWAL = {"type": "Withdrawal", "timestamp": "2024-03-02T12:00:00Z", "from_account_id": BANK,
                  "to_account_id": EXTERNAL, "amount": "40", "fee_amount": "0", "fee_currency": "USD"}


def usd_withdrawal(**fields):
    r = CLIENT.post("/api/transactions", json={**USD_WITHDRAWAL, **fields})
    assert r.status_code == 200, r.text
    return r.json()


def test_transaction_history_pdf_prints_markup_and_fetches_nothing(test_engine, listener):
    port, hits = listener
    evil = f'<img src="http://127.0.0.1:{port}/x" width="9" height="9"/>'
    link = f'<a href="http://127.0.0.1:{port}/y">click</a>'
    tx = usd_deposit()
    # A fee, so the PDF shows its currency with it
    store(test_engine, tx["id"], source=evil, fee_currency=link, fee_amount="1")

    r = CLIENT.get("/api/reports/simple_transaction_history", params={"year": 2024, "format": "pdf"})
    assert r.status_code == 200, r.text
    assert hits == []
    shown = pdf_text(r.content)
    assert "".join(evil.split()) in shown
    assert "".join(link.split()) in shown


def test_complete_tax_report_prints_markup_and_fetches_nothing(listener):
    port, hits = listener
    evil = f'<img src="http://127.0.0.1:{port}/x" width="9" height="9"/>'
    report = {
        "tax_year": 2024,
        "report_date": evil,
        "period": "<b>unclosed",
        "income_transactions": [{"date": "2024-02-01T15:00:00Z", "asset": "BTC", "amount": 0.01,
                                 "value_usd": 420.0, "type": "Income", "description": evil}],
        "end_of_year_balances": [{"asset": "BTC (Bitcoin)", "quantity": 1.0, "cost": 1.0, "value": 2.0,
                                  "description": evil}],
    }
    shown = pdf_text(generate_comprehensive_tax_report(report))
    assert hits == []
    # Printed as written: the generation time on the cover, and the year-end
    # price note in the summary and in the holdings section
    assert shown.count("".join(evil.split())) == 3
    assert "<b>unclosed" in shown


def test_reportlab_trusts_no_url_even_for_unescaped_markup(listener):
    """Second line of defence: raw markup reaching a Paragraph still can't
    make ReportLab fetch anything."""
    import backend.services.reports.safe_text  # noqa: F401  (sets rl_config)

    port, hits = listener
    with pytest.raises(OSError, match="Cannot open resource"):
        story = [Paragraph(f'<img src="http://127.0.0.1:{port}/x" width="9" height="9"/>',
                           getSampleStyleSheet()["Normal"])]
        SimpleDocTemplate(io.BytesIO()).build(story)
    assert hits == []


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("value, expected", [
    ("=HYPERLINK(\"http://x\")", "'=HYPERLINK(\"http://x\")"),
    ("+1", "'+1"), ("-1", "'-1"), ("@SUM(A1)", "'@SUM(A1)"), ("\tx", "'\tx"), ("\rx", "'\rx"), ("\nx", "'\nx"),
    ("MyBTC", "MyBTC"), ("", ""), (None, ""),
    # Look-alikes: spaces or a full-width sign before it (#229's review)
    (" =1+1", "' =1+1"), ("\uff1d1+1", "'\uff1d1+1"), ("\u3000=1+1", "'\u3000=1+1"), ("\xa0=1+1", "'\xa0=1+1"),
    ("rent, March", "rent, March"),
])
def test_csv_text(value, expected):
    assert csv_text(value) == expected


def test_transaction_history_csv_neutralises_formulas_but_not_numbers(test_engine):
    tx = usd_deposit()
    store(test_engine, tx["id"], source="=cmd|' /C calc'!A0", fee_currency="@SUM(1)")
    r = CLIENT.get("/api/reports/simple_transaction_history", params={"year": 2024, "format": "csv"})
    assert r.status_code == 200, r.text
    row = next(csv.DictReader(io.StringIO(r.text)))
    assert row["description"] == "'=cmd|' /C calc'!A0"
    assert row["fee_currency"] == "'@SUM(1)"
    assert row["amount"] == "100.00"


def test_transaction_history_csv_keeps_negative_gains_numeric():
    usd_deposit(amount="100000")
    for body in (
        {"type": "Buy", "timestamp": "2024-03-02T12:00:00Z", "from_account_id": BANK, "to_account_id": 4,
         "amount": "1", "cost_basis_usd": "20000", "fee_amount": "0", "fee_currency": "USD"},
        {"type": "Sell", "timestamp": "2024-03-03T12:00:00Z", "from_account_id": 4, "to_account_id": 3,
         "amount": "0.5", "gross_proceeds_usd": "9880", "fee_amount": "0", "fee_currency": "USD"},
    ):
        assert CLIENT.post("/api/transactions", json=body).status_code == 200
    r = CLIENT.get("/api/reports/simple_transaction_history", params={"year": 2024, "format": "csv"})
    sell = [row for row in csv.DictReader(io.StringIO(r.text)) if row["type"] == "Sell/Withdrawal"][0]
    assert sell["realized_gain_usd"] == "-120.00"


def test_csv_export_neutralises_formulas_but_not_numbers(test_engine):
    tx = usd_deposit()
    store(test_engine, tx["id"], source="+SUM(1)", purpose="-x", fee_currency="=1")
    r = CLIENT.get("/api/backup/csv")
    assert r.status_code == 200, r.text
    row = next(csv.DictReader(io.StringIO(r.text)))
    assert (row["source"], row["purpose"], row["fee_currency"]) == ("'+SUM(1)", "'-x", "'=1")
    assert row["amount"] == "100.00000000" and row["type"] == "Deposit"


FORMULA_STARTS = ("=", "+", "-", "@")


def is_number(cell: str) -> bool:
    try:
        Decimal(cell)
    except InvalidOperation:
        return False
    return True


def parsed_rows(content: str) -> list[list[str]]:
    """The file as a spreadsheet reads it: every row as wide as the header,
    and no cell it would run as a formula (a number such as -120.00 aside)."""
    rows = list(csv.reader(io.StringIO(content)))
    assert [len(row) for row in rows] == [len(rows[0])] * len(rows), rows
    assert [cell for row in rows for cell in row if cell.startswith(FORMULA_STARTS) and not is_number(cell)] == []
    return rows


def set_account_name(test_engine, account_id: int, name: str) -> None:
    with test_engine.begin() as con:
        con.execute(text("UPDATE accounts SET name = :name WHERE id = :id"), {"name": name, "id": account_id})


def test_transaction_history_csv_keeps_every_cell_in_its_row(test_engine):
    """Stored text with a line break (an older version, a restored backup or
    a hand-edited database can hold one) stays inside its quoted cell: the
    text after the break never starts a row of its own."""
    deposit, cash_out = usd_deposit(), usd_withdrawal()
    store(test_engine, deposit["id"], fee_currency="USD\n=2+2", fee_amount="1")
    store(test_engine, cash_out["id"], purpose="rent\n=1+1")
    set_account_name(test_engine, BANK, "Bank\n@SUM(1)")
    try:
        r = CLIENT.get("/api/reports/simple_transaction_history", params={"year": 2024, "format": "csv"})
    finally:
        set_account_name(test_engine, BANK, "Bank")
    assert r.status_code == 200, r.text
    header, *rows = parsed_rows(r.text)
    deposit_row, cash_out_row = (dict(zip(header, row)) for row in rows)
    assert (deposit_row["type"], deposit_row["to_account"], deposit_row["fee_currency"]) == (
        "Deposit", "Bank\n@SUM(1)", "USD\n=2+2")
    assert (cash_out_row["from_account"], cash_out_row["description"]) == ("Bank\n@SUM(1)", "rent\n=1+1")
    assert cash_out_row["amount"] == "40.00"


def test_csv_export_neutralises_the_price_moment_and_keeps_rows_whole(test_engine):
    tx = usd_deposit()
    store(test_engine, tx["id"], price_moment="=1", purpose="rent\n=1+1")
    r = CLIENT.get("/api/backup/csv")
    assert r.status_code == 200, r.text
    header, row = parsed_rows(r.text)
    row = dict(zip(header, row))
    assert (row["price_moment"], row["purpose"]) == ("'=1", "rent\n=1+1")


# Text kept as written is one line; a fee is in USD or BTC
ONE_LINE = "must be one line of text, without a line break, tab or other control character."
FEE_CURRENCY = "fee_currency must be USD or BTC."
# A line break (LF, CR, NEL, line separator), a tab, NUL, ESC, DEL
NOT_ONE_LINE = ["rent\n=1+1", "rent\r=1+1", "rent\x85=1+1", "rent\u2028=1+1", "rent\t=1", "a\x00b", "a\x1bb",
                "a\x7fb"]


@pytest.mark.parametrize("purpose", NOT_ONE_LINE)
def test_a_purpose_kept_as_written_is_one_line(purpose):
    r = CLIENT.post("/api/transactions", json={**USD_WITHDRAWAL, "purpose": purpose})
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == f"purpose {ONE_LINE}"


def test_one_line_purposes_and_listed_values_are_kept():
    usd_deposit()
    assert usd_withdrawal(purpose="rent, March")["purpose"] == "rent, March"
    # A listed value is stored in its own spelling, whatever surrounds it
    r = CLIENT.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2024-03-03T12:00:00Z", "from_account_id": EXTERNAL,
        "to_account_id": WALLET, "amount": "0.1", "cost_basis_usd": "100", "source": "MyBTC\n"})
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "MyBTC"


def test_a_source_kept_as_written_is_one_line():
    r = CLIENT.post("/api/transactions", json={**USD_WITHDRAWAL, "source": "x\n=1+1"})
    assert r.status_code == 422 and r.json()["detail"] == f"source {ONE_LINE}", r.text


@pytest.mark.parametrize("fee_currency", ["USD\n=2+2", "EUR", "=1", " USD"])
def test_a_fee_currency_is_usd_or_btc(fee_currency):
    r = CLIENT.post("/api/transactions", json={**USD_WITHDRAWAL, "fee_currency": fee_currency})
    assert r.status_code == 422 and r.json()["detail"] == FEE_CURRENCY, r.text


@pytest.mark.parametrize("fee_currency", ["USD", "usd", "", None])
def test_usd_btc_or_none_is_a_fee_currency(fee_currency):
    usd_deposit(fee_currency=fee_currency)


def test_an_edit_by_the_ai_key_is_checked_too(ai_key_headers):
    usd_deposit()
    tx = usd_withdrawal(purpose="rent")
    ai = TestClient(app)
    for body, detail in (({"purpose": "rent\n=1+1"}, f"purpose {ONE_LINE}"),
                         ({"fee_currency": "USD\n=2+2"}, FEE_CURRENCY)):
        r = ai.put(f"/api/transactions/{tx['id']}", json=body, headers=ai_key_headers)
        assert r.status_code == 422 and r.json()["detail"] == detail, r.text
    kept = CLIENT.get(f"/api/transactions/{tx['id']}").json()
    assert (kept["purpose"], kept["fee_currency"]) == ("rent", "USD")


def test_the_csv_import_refuses_text_on_two_lines():
    header = "date,type,amount,from_account,to_account,fee_amount,fee_currency,source,purpose\n"
    rows = ('2024-03-02T12:00:00Z,Withdrawal,40,Bank,External,0,USD,,"rent\n=1+1"\n'
            '2024-03-02T12:00:00Z,Withdrawal,40,Bank,External,0,USD,"x\n=1+1",\n'
            '2024-03-02T12:00:00Z,Withdrawal,40,Bank,External,0,"USD\n=2+2",,\n')
    errors = [(e.row_number, e.column, e.message) for e in parse_csv_file((header + rows).encode()).errors]
    assert errors == [
        (2, "purpose", f"purpose {ONE_LINE}"),
        (3, "source", f"source {ONE_LINE}"),
        (4, "fee_currency", "Invalid fee currency 'USD\n=2+2'. Must be USD or BTC."),
    ]


def test_the_ai_import_refuses_text_on_two_lines(ai_key_headers):
    row = {"date": "2024-03-02T12:00:00Z", "type": "Withdrawal", "amount": "40", "from_account": "Bank",
           "to_account": "External", "fee_amount": "0", "fee_currency": "USD"}
    r = TestClient(app).post("/api/import/entries/preview", headers=ai_key_headers, json={"rows": [
        {**row, "purpose": "rent\n=1+1"}, {**row, "source": "x\n=1+1"}, {**row, "fee_currency": "USD\n=2+2"}]})
    assert r.status_code == 200, r.text
    assert [(res["status"], res["errors"]) for res in r.json()["results"]] == [
        ("invalid", [f"purpose {ONE_LINE}"]),
        ("invalid", [f"source {ONE_LINE}"]),
        ("invalid", ["Invalid fee currency 'USD\n=2+2'. Must be USD or BTC."]),
    ]


# ---------------------------------------------------------------------------
# Deposit source
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("source", ["Coinbase", "<img src=x>", "Incomex"])
def test_new_deposit_with_unknown_source_is_refused(source):
    r = CLIENT.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2024-03-01T12:00:00Z", "from_account_id": EXTERNAL,
        "to_account_id": WALLET, "amount": "0.1", "cost_basis_usd": "100", "source": source})
    assert r.status_code == 422
    assert "MyBTC" in r.json()["detail"]


@pytest.mark.parametrize("source", ["MyBTC", "gift", "INCOME", "N/A", "", None])
def test_listed_or_blank_sources_are_accepted(source):
    r = CLIENT.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2024-03-01T12:00:00Z", "from_account_id": EXTERNAL,
        "to_account_id": WALLET, "amount": "0.1", "cost_basis_usd": "100", "source": source})
    assert r.status_code == 200, r.text


def test_an_older_row_with_other_text_still_loads_recalculates_and_edits(test_engine):
    tx = usd_deposit(source="N/A")
    store(test_engine, tx["id"], source="Coinbase")
    assert CLIENT.post("/api/transactions/recalculate").status_code == 200
    assert CLIENT.get(f"/api/transactions/{tx['id']}").json()["source"] == "Coinbase"
    # an edit that leaves the source alone (the form sends it back unchanged)
    r = CLIENT.put(f"/api/transactions/{tx['id']}", json={"amount": "150", "source": "Coinbase"})
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "Coinbase"
    # a new source is checked
    r = CLIENT.put(f"/api/transactions/{tx['id']}", json={"source": "Kraken"})
    assert r.status_code == 422


def test_csv_import_flags_an_unknown_deposit_source():
    from backend.services.csv_import import _validate_row

    row = {"date": "2024-01-05", "type": "Deposit", "amount": "0.1", "from_account": "External",
           "to_account": "Wallet", "cost_basis_usd": "10", "proceeds_usd": "", "fee_amount": "",
           "fee_currency": "", "source": "Coinbase", "purpose": "", "notes": ""}
    tx_data, _preview, errors, _warnings = _validate_row(row, 2)
    assert tx_data is None and [e.column for e in errors] == ["source"]


def test_a_lone_carriage_return_stays_in_its_cell_too(test_engine):
    """Python 3.10's csv writer quoted only for its own line ending's
    characters, so a lone CR split a row there (#229's review; CI runs 3.10)."""
    cash_out = usd_withdrawal()
    store(test_engine, cash_out["id"], purpose="rent\r=1+1")
    r = CLIENT.get("/api/reports/simple_transaction_history", params={"year": 2024, "format": "csv"})
    assert r.status_code == 200, r.text
    header, *rows = parsed_rows(r.text)
    assert all(len(row) == len(header) for row in rows)
    assert dict(zip(header, rows[-1]))["description"] == "rent\r=1+1"


def test_a_row_stored_with_multi_line_text_can_still_be_edited(test_engine):
    """The form sends the stored purpose back unchanged: an edit that leaves
    it alone works; one that sets new multi-line text is refused (#229's review)."""
    cash_out = usd_withdrawal()
    store(test_engine, cash_out["id"], purpose="rent\nMarch")
    r = CLIENT.put(f"/api/transactions/{cash_out['id']}", json={"amount": "41", "purpose": "rent\nMarch"})
    assert r.status_code == 200, r.text
    assert r.json()["purpose"] == "rent\nMarch"
    assert CLIENT.put(f"/api/transactions/{cash_out['id']}", json={"amount": "42"}).status_code == 200
    r = CLIENT.put(f"/api/transactions/{cash_out['id']}", json={"purpose": "other\nline"})
    assert r.status_code == 422 and "one line" in r.text
