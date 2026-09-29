"""
The report builders on inputs the ledger tests rarely produce: every
section of the complete tax report (empty and filled, rows of other assets
left out, dates that aren't ISO 8601, values not priced), the transaction
history of a year without transactions, and the Form 8949 page guards.
They pin what the builders print, so no refactoring can change it unseen.
"""

import io
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
    "start_of_year_balances": [{"quantity": 0.0, "avg_cost_basis": 0.0, "value": None}],
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
        {"asset": "BTC (Wallet)", "quantity": 0.5, "cost": 20000.0, "value": None, "description": "cold"},
        {"asset": "USD (Bank)", "quantity": 10.0, "cost": 10.0, "value": 10.0, "description": "left out"},
    ],
    "capital_gains_transactions": [
        {"asset": "BTC", "date_sold": "2024-07-01T03:00:00Z", "date_acquired": "not a date", "amount": 0.1,
         "cost": 3000.0, "proceeds": 6000.0, "gain_loss": 3000.0, "holding_period": "LONG"},
        {"asset": "ETH", "date_sold": "2024-07-01T03:00:00Z", "date_acquired": "", "amount": 1, "cost": 1,
         "proceeds": 1, "gain_loss": 0, "holding_period": "left out"},
    ],
    "gifts_donations_lost": [
        {"date": "2024-08-01T12:00:00Z", "asset": "BTC", "amount": 0.02, "proceeds_usd": 0.0, "fmv_usd": 1200.0,
         "type": "Gift"},
        {"date": "2024-08-02T12:00:00Z", "asset": "BTC", "amount": 0.03, "proceeds_usd": 0.0, "fmv_usd": None,
         "type": "Lost"},
    ],
    # No valid purpose leads here any more; an old ledger's "Expenses" rows would.
    "expenses": [
        {"date": "2024-09-01T12:00:00Z", "asset": "BTC", "amount": 0.001, "value_usd": 60.0, "type": "Expenses"},
        {"date": "2024-09-02T12:00:00Z", "asset": "ETH", "amount": 1, "value_usd": 1, "type": "left out"},
    ],
}

EMPTY_REPORT = {"tax_year": 2023, "report_date": "2024-01-02 03:04:05", "period": "2023-01-01 to 2023-12-31"}


def pdf_text(pdf: bytes) -> str:
    return " ".join(" ".join(page.extract_text().split()) for page in PdfReader(io.BytesIO(pdf)).pages)


def test_complete_report_sections():
    text = pdf_text(generate_comprehensive_tax_report(REPORT))
    for expected in (
        "Tax Report 2024 Date: 2025-01-05 10:00:00 Period: 2024-01-01 to 2024-12-31 Content",
        "in the tax timezone (America/New_York)",
        "2024 Beginning of Year Holdings Quantity (BTC) Avg Cost Basis (USD) Value (USD) 0.00000000 $0.00 "
        "not priced No BTC price is stored for 2024-01-01",
        "Number of Disposals 3 Proceeds from Sales $1,500.50 $0.00 Acquisition Costs $1,000.00 $0.00 "
        "Profits, Before Losses $600.00 $0.00 Losses $99.50 $0.00 Net Gains $500.50 $0.00",
        "Income $600.00 Reward $0.00 Interest $25.00 Total $625.00",
        "BTC (Wallet) 0.50000000 $20,000.00 not priced cold Total 0.50000000 $20,000.00 not priced "
        "Avg Cost Basis = $40,000.00 per BTC",
        # Dates in the tax timezone; one that isn't ISO 8601 is printed as it is.
        "06/30/2024 not a date BTC 0.10000000 $3,000.00 $6,000.00 $3,000.00 LONG",
        "02/29/2024 BTC 0.01000000 $600.00 Income salary 03/02/2024 USD",
        "08/01/2024 BTC 0.02000000 $0.00 $1,200.00 Gift 08/02/2024 BTC 0.03000000 $0.00 not given Lost",
        "2024 Expenses Date Asset Amount Value (USD) Type 09/01/2024 BTC 0.00100000 $60.00 Expenses",
    ):
        assert expected in text
    assert "left out" not in text and "USD (Bank)" not in text and "ETH" not in text


def test_complete_report_with_nothing_in_it():
    text = pdf_text(generate_comprehensive_tax_report(EMPTY_REPORT))
    assert "in the tax timezone (UTC)" in text
    assert "2023 Beginning of Year Holdings No data for beginning of year holdings" in text
    assert "2023 End of Year Balances No data for end of year balances" in text
    assert "2023 Expenses No transactions" in text
    for omitted in ("Capital Gains/Losses Transactions", "Income Transactions", "Gifts, Donations"):
        assert f"2023 {omitted}" not in text


def test_complete_report_page_numbers_skip_the_title_page():
    pages = PdfReader(io.BytesIO(generate_comprehensive_tax_report(REPORT))).pages
    assert "Generated by BitcoinTX\n1" in pages[1].extract_text()
    assert pages[0].extract_text().rstrip().endswith("Generated by BitcoinTX")


def test_transaction_history_of_a_year_without_transactions(auth_client):
    r = auth_client.get("/api/reports/simple_transaction_history", params={"year": 2001, "format": "pdf"})
    assert r.status_code == 200
    assert pdf_text(r.content) == "Transaction History for 2001 No transactions found for this period."


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
