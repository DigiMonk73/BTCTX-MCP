"""
backend/tests/test_report_safety.py

Ledger text in the reports is data, never instructions:
- PDF: a ReportLab Paragraph reads markup, so a stored value such as
  <img src="http://..."/> made ReportLab fetch that URL (or open a local
  file) while building the transaction history. Now every value is escaped,
  ReportLab trusts no URL, and the text is printed as written.
- CSV: a text cell starting with = + - @ runs as a formula in a spreadsheet;
  it now starts with '. Numbers (a -120.00 loss) are left alone.
- A deposit's source is one of the listed values on every new write; older
  rows with other text still load, recalculate and survive an edit.
"""

import csv
import io
import socket
import threading

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate
from sqlalchemy import text

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


def test_transaction_history_pdf_prints_markup_and_fetches_nothing(test_engine, listener):
    port, hits = listener
    evil = f'<img src="http://127.0.0.1:{port}/x" width="9" height="9"/>'
    link = f'<a href="http://127.0.0.1:{port}/y">click</a>'
    tx = usd_deposit()
    store(test_engine, tx["id"], source=evil, fee_currency=link)

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
    ("+1", "'+1"), ("-1", "'-1"), ("@SUM(A1)", "'@SUM(A1)"), ("\tx", "'\tx"), ("\rx", "'\rx"),
    ("MyBTC", "MyBTC"), ("", ""), (None, ""),
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
