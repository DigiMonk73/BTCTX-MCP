"""
The report builders on inputs the ledger tests rarely produce: every
section of the complete tax report (empty and filled, rows of other assets
left out, dates that aren't ISO 8601, values not priced), the transaction
history of a year without transactions, and the Form 8949 page guards.
They pin what the builders print, so no refactoring can change it unseen.
"""

import io
import re
from decimal import Decimal

import pytest
from pypdf import PdfReader

from backend.services.reports.complete_tax_report import generate_comprehensive_tax_report
from backend.services.reports.form_8949 import Form8949Row, map_8949_rows_to_field_data

REPORT = {
    "tax_year": 2024,
    "report_date": "2025-01-05 10:00:00",
    "period": "2024-01-01 to 2024-12-31",
    "tax_timezone": "America/New_York",
    "start_of_year_balances": [{"quantity": 0.25, "avg_cost_basis": 30000.0, "value": None}],
    "capital_gains_summary": {
        "short_term": {"proceeds": 1500.5, "basis": 1000.0, "gain": 500.5, "profits": 600.0, "losses": 99.5},
        "number_of_disposals": 3,
    },
    "income_transactions": [
        {"date": "2024-03-01T04:30:00Z", "asset": "BTC", "amount": 0.01, "value_usd": 600.0, "type": "Income",
         "description": "salary"},
        {"date": "2024-03-02T12:00:00", "asset": "USD", "amount": 25.0, "value_usd": 25.0, "type": "Interest",
         "description": ""},
        {"date": "", "asset": "ETH", "amount": 1.0, "value_usd": 9.0, "type": "Reward", "description": "left out"},
    ],
    "end_of_year_balances": [
        {"asset": "BTC (Bitcoin)", "account": "Wallet", "acquired": "2024-01-15T12:00:00Z", "quantity": 0.5,
         "cost": 20000.0, "value": None, "description": "No BTC price for 2024-12-31: not priced"},
        {"asset": "USD (Bank)", "quantity": 10.0, "cost": 10.0, "value": 10.0, "description": "left out"},
        {"asset": "Total", "quantity": 0.5, "cost": 20000.0, "value": None, "description": ""},
    ],
    "form_8949_boxes": [
        {"box": "F", "line": "10", "rows": 1, "proceeds": 6000.0, "cost": 3000.0, "gain_loss": 3000.0},
    ],
    "capital_gains_transactions": [
        {"asset": "BTC", "date_sold": "2024-07-01T03:00:00Z", "date_acquired": "not a date", "amount": 0.1,
         "cost": 3000.0, "proceeds": 6000.0, "gain_loss": 3000.0, "holding_period": "LONG", "kind": "Sale",
         "box": "F"},
        {"asset": "ETH", "date_sold": "2024-07-01T03:00:00Z", "date_acquired": "", "amount": 1, "cost": 1,
         "proceeds": 1, "gain_loss": 0, "holding_period": "left out"},
    ],
    "gifts_donations_lost": [
        {"date": "2024-08-01T12:00:00Z", "asset": "BTC", "amount": 0.02, "proceeds_usd": 0.0, "fmv_usd": 1200.0,
         "type": "Gift"},
        {"date": "2024-08-02T12:00:00Z", "asset": "BTC", "amount": 0.03, "proceeds_usd": 0.0, "fmv_usd": None,
         "type": "Lost"},
    ],
}

EMPTY_REPORT = {"tax_year": 2023, "report_date": "2024-01-02 03:04:05", "period": "2023-01-01 to 2023-12-31"}


def pdf_text(pdf: bytes) -> str:
    return " ".join(" ".join(page.extract_text().split()) for page in PdfReader(io.BytesIO(pdf)).pages)


def test_complete_report_sections():
    text = pdf_text(generate_comprehensive_tax_report(REPORT))
    for expected in (
        # The cover: the year's key figures and how the report was made
        "TAX YEAR 2024 Bitcoin Tax Report Capital gains, income and holdings, January 1 to December 31, 2024",
        "NET CAPITAL GAIN (LOSS) $500.50 Short-term $500.50 · Long-term $0.00 INCOME $600.00",
        "BITCOIN HELD AT YEAR END 0.50000000 BTC Cost basis $20,000.00 VALUE AT YEAR END not priced",
        "GENERATED 2025-01-05 10:00:00 UTC",
        # The summary; a loss in parentheses, as on the IRS forms
        "Total 1 $1,500.50 $1,000.00 $600.00 ($99.50) $500.50",
        "F Long-term, not on a Form 1099-B 10 1 $6,000.00 $3,000.00 $3,000.00",
        # Income rows are BTC: a USD row (none is ever built) stays out of the BTC column
        "Income 1 0.01000000 $600.00 Reward 0 0.00000000 $0.00 Interest 0 0.00000000 $0.00 "
        "Total 1 0.01000000 $600.00",
        "January 1, 2024 0.25000000 $7,500.00 $30,000.00 not priced December 31, 2024 0.50000000 $20,000.00 "
        "$40,000.00 not priced No BTC price is stored for 2024-01-01",
        # The detail: dates in the tax timezone; one that isn't ISO 8601 is printed as it is
        "06/30/2024 not a date Sale F Long 0.10000000 $6,000.00 $3,000.00 $3,000.00",
        "02/29/2024 Income 0.01000000 $600.00 Total 0.01000000 $600.00",
        # An unvalued gift is never counted as $0 (review of #63)
        "08/01/2024 Gift 0.02000000 $1,200.00 08/02/2024 Lost 0.03000000 not given "
        "Total 0.05000000 $1,200.00 + 1 not given",
        "Wallet 1 0.50000000 $20,000.00 not priced Total 1 0.50000000 $20,000.00 not priced "
        "No BTC price for 2024-12-31: not priced Average cost: $40,000.00 per BTC",
        "01/15/2024 Wallet 0.50000000 $20,000.00 not priced Total 0.50000000 $20,000.00 not priced",
        "in the tax timezone (America/New_York)",
    ):
        assert expected in text, expected
    assert "left out" not in text and "USD (Bank)" not in text and not re.search(r"\bETH\b", text)
    assert "-0.00" not in text


def test_complete_report_with_nothing_in_it():
    text = pdf_text(generate_comprehensive_tax_report(EMPTY_REPORT))
    assert "in the tax timezone (UTC)" in text
    for empty in ("No disposals for Form 8949 in 2023.", "No disposals in 2023.", "No income in 2023.",
                  "No gifts, donations or lost coins in 2023.", "No bitcoin held on December 31, 2023."):
        assert empty in text
    assert "Expenses" not in text  # #58: no transaction could ever fill it
    assert "-0.00" not in text


def test_complete_report_pages_contents_and_numbers():
    """The cover has no running header; every page says "Page N of M"; the
    contents give each section's page."""
    pages = [page.extract_text() for page in PdfReader(io.BytesIO(generate_comprehensive_tax_report(REPORT))).pages]
    assert all(f"Page {n} of {len(pages)}" in text for n, text in enumerate(pages, start=1))
    assert "2024 Bitcoin Tax Report" not in pages[0]
    assert all("2024 Bitcoin Tax Report" in text for text in pages[1:])
    # Where each section starts: the page with its heading, a line "N. Title"
    starts = {n: next(i for i, text in enumerate(pages[1:], start=2)
                      if any(line.startswith(f"{n}. ") for line in text.split("\n")))
              for n in range(1, 7)}
    # The contents: each entry's page number comes out of the text just before its title
    listed = {int(n): int(page) for page, n in re.findall(r"(\d+) (\d)\. [A-Z]", " ".join(pages[0].split()))}
    assert listed == starts


def test_a_long_report_keeps_every_row_its_headers_and_page_numbers():
    """Review of #63: a table over many pages repeats its header on each,
    loses no row, and the contents still give each section's page."""
    disposals = [{"asset": "BTC", "date_sold": f"2024-{1 + i % 12:02d}-{1 + i % 28:02d}T12:00:00Z",
                  "date_acquired": "2023-01-02T12:00:00Z", "amount": 0.001 + i / 1e6, "cost": 10.0, "proceeds": 20.0,
                  "gain_loss": 10.0, "holding_period": "LONG", "kind": "Sale", "box": "F"} for i in range(150)]
    pdf = generate_comprehensive_tax_report({**REPORT, "capital_gains_transactions": disposals})
    pages = [page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages]
    detail = [text for text in pages if "Gain (loss)" in text and "Kind" in text]
    assert len(detail) >= 4  # the header on every page of the table
    assert sum(" ".join(text.split()).count(" Sale F Long ") for text in detail) == 150
    starts = {n: next(i for i, text in enumerate(pages[1:], start=2)
                      if any(line.startswith(f"{n}. ") for line in text.split("\n")))
              for n in range(1, 7)}
    listed = {int(n): int(page) for page, n in re.findall(r"(\d+) (\d)\. [A-Z]", " ".join(pages[0].split()))}
    assert listed == starts and starts[3] > starts[2] + 2


def test_transaction_history_of_a_year_without_transactions(auth_client):
    r = auth_client.get("/api/reports/simple_transaction_history", params={"year": 2001, "format": "pdf"})
    assert r.status_code == 200
    assert "TAX YEAR 2001 Transaction History" in pdf_text(r.content)
    assert "No transactions in 2001. " in pdf_text(r.content) + " "


def row(box: str) -> Form8949Row:
    return Form8949Row("0.1 BTC", "01/01/2024", "06/01/2024", Decimal("10"), Decimal("5"), Decimal("5"),
                       "SHORT", box)


@pytest.mark.parametrize("rows, page, message", [
    ([row("A")], 3, "page must be 1 (Part I) or 2 (Part II)"),
    ([row("A")] * 15, 1, "Cannot fit more than 14 rows on one 2024 Form 8949 page"),
    ([row("A"), row("B")], 1, "Rows for one Form 8949 page must share a box, got ['A', 'B']"),
])
def test_form_8949_page_guards(rows, page, message):
    with pytest.raises(ValueError) as refused:
        map_8949_rows_to_field_data(rows, page=page, year=2024)
    assert str(refused.value) == message
