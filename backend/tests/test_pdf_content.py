#!/usr/bin/env python3
"""
Test Suite: PDF Content Verification

This pytest-compatible test suite verifies that generated PDF reports
contain the correct data, not just that they were generated successfully.

Uses pypdf to extract text from PDFs and verify expected values.

Run: pytest backend/tests/test_pdf_content.py -v
Requires: Backend running at http://127.0.0.1:8000
"""

import pytest
import io
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pypdf import PdfReader
from fastapi.testclient import TestClient

# =============================================================================
# CONFIGURATION
# =============================================================================

# Authenticated TestClient (set by autouse fixture from conftest.py)
CLIENT: TestClient = None


@pytest.fixture(autouse=True, scope="session")
def _set_client(auth_client):
    global CLIENT
    CLIENT = auth_client

# Account IDs (standard BitcoinTX setup)
BANK_USD = 1
WALLET_BTC = 2
EXCHANGE_USD = 3
EXCHANGE_BTC = 4


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def delete_all_transactions() -> bool:
    """Clear all transactions for a fresh start."""
    r = CLIENT.delete("/api/transactions/delete_all")
    return r.status_code in (200, 204)


def create_tx(tx_data: Dict) -> Dict:
    """Create a transaction and return the response."""
    r = CLIENT.post("/api/transactions", json=tx_data)
    if not r.is_success:
        return {"error": True, "status_code": r.status_code, "detail": r.text}
    return r.json()


def build_timestamp(year: int, month: int, day: int, hour: int = 12) -> str:
    """Build ISO timestamp string."""
    dt = datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_complete_tax_report(year: int) -> Optional[bytes]:
    """Get the complete tax report PDF as bytes."""
    r = CLIENT.get("/api/reports/complete_tax_report", params={"year": year})
    if r.status_code == 200:
        return r.content
    return None


def get_irs_report(year: int) -> Optional[bytes]:
    """Get IRS Form 8949 + Schedule D PDF as bytes."""
    r = CLIENT.get("/api/reports/irs_reports", params={"year": year})
    if r.status_code == 200:
        return r.content
    return None


def get_transaction_history_pdf(year: int) -> Optional[bytes]:
    """Get transaction history PDF as bytes."""
    r = CLIENT.get(
        "/api/reports/simple_transaction_history",
        params={"year": year, "format": "pdf"}
    )
    if r.status_code == 200:
        return r.content
    return None


def get_transaction_history_csv(year: int) -> Optional[str]:
    """Get transaction history CSV as string."""
    r = CLIENT.get(
        "/api/reports/simple_transaction_history",
        params={"year": year, "format": "csv"}
    )
    if r.status_code == 200:
        return r.text
    return None


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract all text from a PDF."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text_parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            text_parts.append(text)
    return "\n".join(text_parts)


def extract_pdf_text_by_page(pdf_bytes: bytes) -> List[str]:
    """Extract text from each page of a PDF."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        pages.append(text if text else "")
    return pages


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace for easier matching."""
    return " ".join(text.split())


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def clean_db():
    """Clean database before test."""
    delete_all_transactions()
    yield
    delete_all_transactions()


@pytest.fixture
def sample_buy_sell_data(clean_db):
    """
    Create a sample buy and sell scenario with known values.

    Buy: 1.0 BTC at $40,000 on 2024-03-15
    Sell: 0.5 BTC at $50,000 on 2024-09-20
    Expected gain: $5,000 (short-term)
    """
    # Deposit USD to exchange
    create_tx({
        "type": "Deposit",
        "timestamp": build_timestamp(2024, 3, 1),
        "from_account_id": 99,  # External
        "to_account_id": EXCHANGE_USD,
        "amount": "50000",
        "is_income": False,
    })

    # Buy 1.0 BTC at $40,000
    create_tx({
        "type": "Buy",
        "timestamp": build_timestamp(2024, 3, 15),
        "from_account_id": EXCHANGE_USD,
        "to_account_id": EXCHANGE_BTC,
        "amount": "1.0",
        "cost_basis_usd": "40000",
    })

    # Sell 0.5 BTC at $50,000 total ($100,000/BTC rate)
    result = create_tx({
        "type": "Sell",
        "timestamp": build_timestamp(2024, 9, 20),
        "from_account_id": EXCHANGE_BTC,
        "to_account_id": EXCHANGE_USD,
        "amount": "0.5",
        "proceeds_usd": "50000",
    })

    yield {
        "buy_date": "03/15/2024",
        "sell_date": "09/20/2024",
        "buy_amount": "1.0",
        "sell_amount": "0.5",
        "cost_basis": "40000",  # Total for 1 BTC
        "cost_basis_sold": "20000",  # Cost basis for 0.5 BTC
        "proceeds": "50000",
        "gain": "30000",  # $50,000 - $20,000
        "holding_period": "short",
        "realized_gain": result.get("realized_gain_usd", "0"),
    }


@pytest.fixture
def long_term_gain_data(clean_db):
    """
    Create a long-term capital gain scenario.

    Buy: 2.0 BTC at $30,000 on 2023-01-15
    Sell: 1.0 BTC at $60,000 on 2024-06-20 (held > 1 year)
    Expected gain: $45,000 (long-term)
    """
    # Deposit USD
    create_tx({
        "type": "Deposit",
        "timestamp": build_timestamp(2023, 1, 1),
        "from_account_id": 99,
        "to_account_id": EXCHANGE_USD,
        "amount": "100000",
        "is_income": False,
    })

    # Buy 2.0 BTC at $30,000 total ($15,000/BTC)
    create_tx({
        "type": "Buy",
        "timestamp": build_timestamp(2023, 1, 15),
        "from_account_id": EXCHANGE_USD,
        "to_account_id": EXCHANGE_BTC,
        "amount": "2.0",
        "cost_basis_usd": "30000",
    })

    # Sell 1.0 BTC at $60,000 (held > 1 year = long-term)
    result = create_tx({
        "type": "Sell",
        "timestamp": build_timestamp(2024, 6, 20),
        "from_account_id": EXCHANGE_BTC,
        "to_account_id": EXCHANGE_USD,
        "amount": "1.0",
        "proceeds_usd": "60000",
    })

    yield {
        "buy_date": "01/15/2023",
        "sell_date": "06/20/2024",
        "sell_amount": "1.0",
        "cost_basis_sold": "15000",  # 1.0 BTC at $15,000/BTC
        "proceeds": "60000",
        "gain": "45000",
        "holding_period": "long",
        "realized_gain": result.get("realized_gain_usd", "0"),
    }


@pytest.fixture
def multiple_transactions_data(clean_db):
    """
    Create multiple transactions for comprehensive testing.

    Includes: deposits, buys, sells, transfers, income
    """
    transactions = []

    # 1. Deposit USD to bank
    transactions.append(create_tx({
        "type": "Deposit",
        "timestamp": build_timestamp(2024, 1, 5),
        "from_account_id": 99,
        "to_account_id": BANK_USD,
        "amount": "100000",
        "is_income": False,
    }))

    # 2. Transfer USD to exchange
    transactions.append(create_tx({
        "type": "Transfer",
        "timestamp": build_timestamp(2024, 1, 10),
        "from_account_id": BANK_USD,
        "to_account_id": EXCHANGE_USD,
        "amount": "50000",
    }))

    # 3. Buy BTC
    transactions.append(create_tx({
        "type": "Buy",
        "timestamp": build_timestamp(2024, 2, 1),
        "from_account_id": EXCHANGE_USD,
        "to_account_id": EXCHANGE_BTC,
        "amount": "1.5",
        "cost_basis_usd": "45000",
    }))

    # 4. Receive BTC as income
    transactions.append(create_tx({
        "type": "Deposit",
        "timestamp": build_timestamp(2024, 3, 15),
        "from_account_id": 99,
        "to_account_id": WALLET_BTC,
        "amount": "0.1",
        "cost_basis_usd": "5000",
        "is_income": True,
        "source": "Income",
    }))

    # 5. Transfer BTC (with fee)
    transactions.append(create_tx({
        "type": "Transfer",
        "timestamp": build_timestamp(2024, 4, 1),
        "from_account_id": EXCHANGE_BTC,
        "to_account_id": WALLET_BTC,
        "amount": "0.5",
        "fee_amount": "0.0001",
        "fee_currency": "BTC",
    }))

    # 6. Sell BTC
    transactions.append(create_tx({
        "type": "Sell",
        "timestamp": build_timestamp(2024, 5, 20),
        "from_account_id": EXCHANGE_BTC,
        "to_account_id": EXCHANGE_USD,
        "amount": "0.75",
        "proceeds_usd": "37500",
    }))

    yield {
        "transactions": transactions,
        "year": 2024,
        "total_income": "5000",  # BTC income
        "num_sells": 1,
    }


# =============================================================================
# COMPLETE TAX REPORT TESTS
# =============================================================================

class TestCompleteTaxReportContent:
    """Tests for complete tax report PDF content."""

    def test_report_contains_year(self, sample_buy_sell_data):
        """Report should contain the tax year."""
        pdf_bytes = get_complete_tax_report(2024)
        assert pdf_bytes is not None

        text = extract_pdf_text(pdf_bytes)
        assert "2024" in text, "Report should contain the year 2024"

    def test_report_contains_sections(self, sample_buy_sell_data):
        """Report should contain all expected sections."""
        pdf_bytes = get_complete_tax_report(2024)
        text = extract_pdf_text(pdf_bytes)

        expected_sections = [
            "1. Summary",
            "Capital gains and losses",
            "3. Income",
            "Holdings at year end",
        ]

        for section in expected_sections:
            assert section in text, f"Report should contain '{section}' section"

    def test_report_says_where_prices_come_from(self, sample_buy_sell_data):
        """VM test 2026-09-29 (F4): the notes claimed "the average market value
        at the time of disposal"; values are the ones typed, else the day's
        stored price, and the tax timezone decides the dates."""
        text = normalize_whitespace(extract_pdf_text(get_complete_tax_report(2024)))
        assert "average market value" not in text
        assert "daily BTC price" in text and "tax timezone" in text

    def test_report_shows_capital_gains(self, sample_buy_sell_data):
        """Report should show capital gains from sales."""
        pdf_bytes = get_complete_tax_report(2024)
        text = extract_pdf_text(pdf_bytes)

        # Should show proceeds
        assert "50,000" in text or "50000" in text, \
            "Report should show $50,000 proceeds"

        # Should indicate short-term (held < 1 year)
        assert "Short-term" in text, "Report should indicate short-term gains"

    def test_report_shows_ending_balance(self, sample_buy_sell_data):
        """Report should show remaining BTC balance."""
        pdf_bytes = get_complete_tax_report(2024)
        text = extract_pdf_text(pdf_bytes)

        # After buying 1.0 and selling 0.5, should have 0.5 BTC
        assert "0.5" in text, "Report should show 0.5 BTC remaining"

    def test_report_shows_income(self, multiple_transactions_data):
        """Report should show BTC income."""
        pdf_bytes = get_complete_tax_report(2024)
        text = extract_pdf_text(pdf_bytes)

        # Should show income section with value
        assert "Income" in text, "Report should contain Income section"
        assert "5,000" in text or "5000" in text, \
            "Report should show $5,000 income"

    def test_report_long_term_vs_short_term(self, long_term_gain_data):
        """Report should correctly categorize long-term gains."""
        pdf_bytes = get_complete_tax_report(2024)
        text = extract_pdf_text(pdf_bytes)

        # Should show long-term classification
        assert "Long-term" in text, "Report should indicate long-term gains"


# =============================================================================
# IRS FORM TESTS
# =============================================================================

class TestIRSFormContent:
    """Tests for IRS Form 8949 and Schedule D content."""

    def test_schedule_d_present(self, sample_buy_sell_data):
        """IRS report should contain Schedule D."""
        pdf_bytes = get_irs_report(2024)
        assert pdf_bytes is not None

        text = extract_pdf_text(pdf_bytes)
        assert "Schedule D" in text or "SCHEDULE D" in text, \
            "IRS report should contain Schedule D"

    def test_form_8949_present_with_sales(self, sample_buy_sell_data):
        """IRS report should contain Form 8949 when there are sales."""
        pdf_bytes = get_irs_report(2024)
        text = extract_pdf_text(pdf_bytes)

        assert "Form 8949" in text or "8949" in text, \
            "IRS report should reference Form 8949"

    def test_schedule_d_shows_proceeds(self, sample_buy_sell_data):
        """Schedule D should show proceeds from sales."""
        pdf_bytes = get_irs_report(2024)
        text = extract_pdf_text(pdf_bytes)

        # The proceeds value should appear somewhere
        # Note: PDF text extraction may not perfectly align with form fields
        assert "50" in text, "Should show proceeds value (50,000)"

    def test_correct_tax_year(self, sample_buy_sell_data):
        """IRS forms should show correct tax year."""
        pdf_bytes = get_irs_report(2024)
        text = extract_pdf_text(pdf_bytes)

        assert "2024" in text, "IRS forms should show 2024 tax year"

    def test_long_term_section(self, long_term_gain_data):
        """IRS report should have long-term section for gains held > 1 year."""
        pdf_bytes = get_irs_report(2024)
        text = extract_pdf_text(pdf_bytes)

        # Schedule D has Part I (short-term) and Part II (long-term)
        assert "Part II" in text, "Should have Part II for long-term gains"
        assert "Long-Term" in text or "long-term" in text.lower(), \
            "Should reference long-term capital gains"

    def test_pdf_page_count(self, sample_buy_sell_data):
        """IRS report should have at least 2 pages (Schedule D + Form 8949)."""
        pdf_bytes = get_irs_report(2024)
        reader = PdfReader(io.BytesIO(pdf_bytes))

        assert len(reader.pages) >= 2, \
            "IRS report should have at least 2 pages"


# =============================================================================
# FORM 8949 LINE 2 TOTALS
# =============================================================================

# Line 2 "Totals" fields, read off the templates (position under the row
# columns, below the last row; XFA tooltip "2. Totals. ..."): directly under
# PageN, columns (d), (e), (f), (g), (h). Hard-coded here on purpose, so the
# test doesn't trust the app's own config.
LINE_2_FIELDS = {
    2024: ("115", "116", "117", "118", "119"),
    2025: ("91", "92", "93", "94", "95"),
}
ROWS_PER_SHEET = {2024: 14, 2025: 11}
# Schedule D line of the short-term exchange Sells and long-term spends below
SCHEDULE_D_LINES = {2024: ("3", "10"), 2025: ("2", "10")}  # boxes C/F, H/L


class TestForm8949Line2Totals:
    """Bug hunt 2026-09-29: Form 8949 line 2 ("Totals": add columns (d), (e),
    (g) and (h), carried to Schedule D) was never filled, and the sheets are
    flattened, so the owner couldn't write the totals in either. Each sheet's
    line 2 must total the rows on that sheet (one box's chunk), and Schedule
    D's line for the box must be the sum of that box's sheets."""

    @pytest.mark.parametrize("year", [2024, 2025])
    def test_each_sheet_totals_its_own_rows(self, clean_db, monkeypatch, year):
        import re
        import backend.routers.reports as reports
        from backend.services.reports.form_8949 import get_schedule_d_field_config

        def ok(result):
            assert "error" not in result, result
            return result

        per_sheet = ROWS_PER_SHEET[year]
        # Part I: exchange Sells of 0.01 BTC from one 1 BTC lot ($200.00 basis
        # each), two more than a sheet holds, so the box runs onto a second
        # sheet. The first is a loss.
        proceeds = [Decimal("150.10")] + [Decimal(f"{250 + i}.37") for i in range(1, per_sheet + 2)]
        ok(create_tx({
            "type": "Buy", "timestamp": build_timestamp(year, 1, 2),
            "from_account_id": EXCHANGE_USD, "to_account_id": EXCHANGE_BTC,
            "amount": "1", "cost_basis_usd": "20000", "fee_amount": "0", "fee_currency": "USD",
        }))
        for i, p in enumerate(proceeds):
            ok(create_tx({
                "type": "Sell", "timestamp": build_timestamp(year, 3, 1 + i),
                "from_account_id": EXCHANGE_BTC, "to_account_id": EXCHANGE_USD,
                "amount": "0.01", "gross_proceeds_usd": str(p), "fee_amount": "0", "fee_currency": "USD",
            }))
        # Part II: two long-term spends of 0.1 BTC ($1,000.00 basis each), one a loss.
        ok(create_tx({
            "type": "Deposit", "timestamp": build_timestamp(year - 2, 6, 1),
            "from_account_id": 99, "to_account_id": WALLET_BTC, "amount": "1",
            "cost_basis_usd": "10000", "source": "MyBTC", "fee_amount": "0", "fee_currency": "BTC",
        }))
        for month, p in ((6, "3000.55"), (7, "800.20")):
            ok(create_tx({
                "type": "Withdrawal", "timestamp": build_timestamp(year, month, 1),
                "from_account_id": WALLET_BTC, "to_account_id": 99, "amount": "0.1",
                "fee_amount": "0", "fee_currency": "BTC", "purpose": "Spent", "proceeds_usd": p,
            }))

        filled = []
        real_fill = reports.fill_pdf_form

        def capture(path, fields, **kw):
            filled.append((path.rsplit("/", 1)[-1], dict(fields)))
            return real_fill(path, fields, **kw)

        monkeypatch.setattr(reports, "fill_pdf_form", capture)
        pdf = get_irs_report(year)
        assert pdf is not None
        sheets = [f for name, f in filled if name == "f8949.pdf"]
        schedule_d = next(f for name, f in filled if name == "f1040sd.pdf")
        assert len(sheets) == 2

        def line_2(sheet, page):
            return [sheet.get(f"topmostSubform[0].Page{page}[0].f{page}_{n}[0]") for n in LINE_2_FIELDS[year]]

        def expected(amounts, basis_each):
            d, e = sum(amounts, Decimal("0")), basis_each * len(amounts)
            return [f"{d:.2f}", f"{e:.2f}", "", "", f"{d - e:.2f}"]

        # Worked by hand: each sheet's own rows, (f) and (g) blank like the rows.
        assert line_2(sheets[0], 1) == expected(proceeds[:per_sheet], Decimal("200"))
        assert line_2(sheets[1], 1) == expected(proceeds[per_sheet:], Decimal("200"))
        assert line_2(sheets[0], 2) == ["3800.75", "2000.00", "", "", "1800.75"]
        assert line_2(sheets[1], 2) == [None] * 5  # no long-term rows on sheet 2

        # And to the cent the sum of the row fields printed on that page.
        def column_sum(sheet, page, offset):  # offset: (d) 3, (e) 4, (h) 7
            total = Decimal("0")
            for name, value in sheet.items():
                m = re.search(rf"Page{page}\[0\]\.Table[^.]*\.Row\d+\[0\]\.f{page}_(\d+)\[0\]$", name)
                if m and (int(m.group(1)) - 3) % 8 == offset:
                    total += Decimal(value)
            return total

        for sheet, page in ((sheets[0], 1), (sheets[1], 1), (sheets[0], 2)):
            d, e, _, _, h = line_2(sheet, page)
            assert [Decimal(d), Decimal(e), Decimal(h)] == [column_sum(sheet, page, o) for o in (3, 4, 7)]

        # Schedule D: each box's line is the sum of that box's sheets.
        config = get_schedule_d_field_config(year)
        short_line, long_line = SCHEDULE_D_LINES[year]
        for line, parts in ((short_line, [(sheets[0], 1), (sheets[1], 1)]), (long_line, [(sheets[0], 2)])):
            d_field, e_field, _, h_field = config[line]
            for field, col in ((d_field, 0), (e_field, 1), (h_field, 4)):
                assert Decimal(schedule_d[field]) == sum(Decimal(line_2(s, p)[col]) for s, p in parts), line

        # The flattened PDF prints them: sheet 1 Part I, sheet 1 Part II, sheet 2 Part I.
        pages = extract_pdf_text_by_page(pdf)
        assert len(pages) == 6
        for text, (sheet, page) in zip(pages[:3], ((sheets[0], 1), (sheets[0], 2), (sheets[1], 1))):
            d, e, _, _, h = line_2(sheet, page)
            for value in (d, e, h):
                assert value in text, f"line 2 total {value} not printed"


# =============================================================================
# TRANSACTION HISTORY TESTS
# =============================================================================

class TestTransactionHistoryContent:
    """Tests for transaction history report content."""

    def test_csv_contains_headers(self, multiple_transactions_data):
        """CSV should contain column headers."""
        csv_content = get_transaction_history_csv(2024)
        assert csv_content is not None

        # Check for expected column headers
        first_line = csv_content.split("\n")[0].lower()
        expected_headers = ["date", "type", "amount"]

        for header in expected_headers:
            assert header in first_line, f"CSV should have '{header}' column"

    def test_csv_contains_transactions(self, multiple_transactions_data):
        """CSV should contain transaction data."""
        csv_content = get_transaction_history_csv(2024)
        lines = [l for l in csv_content.split("\n") if l.strip()]

        # Should have header + data rows
        assert len(lines) > 1, "CSV should have data rows"

    def test_csv_transaction_types(self, multiple_transactions_data):
        """CSV should show different transaction types."""
        csv_content = get_transaction_history_csv(2024)

        assert "Buy" in csv_content, "CSV should contain Buy transactions"
        assert "Sell" in csv_content, "CSV should contain Sell transactions"

    def test_pdf_contains_transaction_list(self, multiple_transactions_data):
        """PDF history should contain transaction details."""
        pdf_bytes = get_transaction_history_pdf(2024)
        assert pdf_bytes is not None

        text = extract_pdf_text(pdf_bytes)

        assert "Buy" in text or "BUY" in text, \
            "PDF should show Buy transactions"
        assert "Sell" in text or "SELL" in text, \
            "PDF should show Sell transactions"


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestPDFEdgeCases:
    """Tests for edge cases in PDF generation."""

    def test_empty_year_generates_pdf(self, clean_db):
        """Empty year should still generate a valid PDF."""
        # Don't create any transactions
        pdf_bytes = get_complete_tax_report(2024)

        # Should either return valid PDF or handle gracefully
        if pdf_bytes:
            assert pdf_bytes[:4] == b'%PDF', "Should be valid PDF"
            text = extract_pdf_text(pdf_bytes)
            assert "2024" in text, "Should still show the year"

    def test_large_amounts_display_correctly(self, clean_db):
        """Large dollar amounts should display correctly."""
        # Create a large transaction
        create_tx({
            "type": "Deposit",
            "timestamp": build_timestamp(2024, 1, 1),
            "from_account_id": 99,
            "to_account_id": EXCHANGE_USD,
            "amount": "10000000",  # $10 million
            "is_income": False,
        })

        create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 1, 15),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "100.0",
            "cost_basis_usd": "5000000",  # $5 million
        })

        create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2024, 6, 15),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "50.0",
            "proceeds_usd": "7500000",  # $7.5 million
        })

        pdf_bytes = get_complete_tax_report(2024)
        text = extract_pdf_text(pdf_bytes)

        # Should show large numbers (may be formatted with commas)
        assert "7,500,000" in text or "7500000" in text, \
            "Should display large proceeds"

    def test_small_btc_amounts_precision(self, clean_db):
        """Small BTC amounts should maintain precision."""
        create_tx({
            "type": "Deposit",
            "timestamp": build_timestamp(2024, 1, 1),
            "from_account_id": 99,
            "to_account_id": EXCHANGE_USD,
            "amount": "100",
            "is_income": False,
        })

        create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 1, 15),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "0.00012345",  # Small BTC amount
            "cost_basis_usd": "5",
        })

        pdf_bytes = get_complete_tax_report(2024)
        text = extract_pdf_text(pdf_bytes)

        # Should show the small amount with precision
        assert "0.0001" in text, "Should show small BTC amounts"

    def test_multiple_sales_same_day(self, clean_db):
        """Multiple sales on same day should all appear."""
        # Setup
        create_tx({
            "type": "Deposit",
            "timestamp": build_timestamp(2024, 1, 1),
            "from_account_id": 99,
            "to_account_id": EXCHANGE_USD,
            "amount": "100000",
            "is_income": False,
        })

        create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 2, 1),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "2.0",
            "cost_basis_usd": "80000",
        })

        # Two sells on same day
        for i in range(2):
            create_tx({
                "type": "Sell",
                "timestamp": build_timestamp(2024, 6, 15, hour=10 + i),
                "from_account_id": EXCHANGE_BTC,
                "to_account_id": EXCHANGE_USD,
                "amount": "0.5",
                "proceeds_usd": "30000",
            })

        csv_content = get_transaction_history_csv(2024)

        # Count sell transactions
        sell_count = csv_content.count("Sell")
        assert sell_count >= 2, "Should show both sales"


# =============================================================================
# DATA ACCURACY TESTS
# =============================================================================

class TestDataAccuracy:
    """Tests that verify calculated values in reports match expected values."""

    def test_gain_calculation_accuracy(self, sample_buy_sell_data):
        """Verify gain calculation is correct in report."""
        pdf_bytes = get_complete_tax_report(2024)
        text = extract_pdf_text(pdf_bytes)

        # Cost basis for 0.5 BTC at $40,000/BTC = $20,000
        # Proceeds = $50,000
        # Gain = $30,000
        assert "30,000" in text or "30000" in text, \
            "Report should show $30,000 gain"

    def test_cost_basis_tracking(self, clean_db):
        """Verify FIFO cost basis is tracked correctly."""
        # First buy: 1.0 BTC at $30,000
        create_tx({
            "type": "Deposit",
            "timestamp": build_timestamp(2024, 1, 1),
            "from_account_id": 99,
            "to_account_id": EXCHANGE_USD,
            "amount": "100000",
            "is_income": False,
        })

        create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 1, 15),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "1.0",
            "cost_basis_usd": "30000",
        })

        # Second buy: 1.0 BTC at $50,000
        create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 3, 15),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "1.0",
            "cost_basis_usd": "50000",
        })

        # Sell 1.5 BTC - should use FIFO
        # First 1.0 from lot 1 ($30,000) + 0.5 from lot 2 ($25,000) = $55,000 cost basis
        result = create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2024, 6, 15),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "1.5",
            "proceeds_usd": "75000",
        })

        # Gain should be $75,000 - $55,000 = $20,000
        realized_gain = Decimal(result.get("realized_gain_usd", "0"))
        assert abs(realized_gain - Decimal("20000")) < Decimal("1"), \
            f"Expected gain ~$20,000, got ${realized_gain}"

        # Verify in report
        pdf_bytes = get_complete_tax_report(2024)
        text = extract_pdf_text(pdf_bytes)
        assert "20,000" in text or "20000" in text, \
            "Report should show $20,000 gain from FIFO calculation"

    def test_income_totals(self, clean_db):
        """Verify income is totaled correctly."""
        # Multiple income deposits
        for month in [2, 4, 6]:
            create_tx({
                "type": "Deposit",
                "timestamp": build_timestamp(2024, month, 15),
                "from_account_id": 99,
                "to_account_id": WALLET_BTC,
                "amount": "0.01",
                "cost_basis_usd": "500",
                "is_income": True,
                "source": "Income",
            })

        pdf_bytes = get_complete_tax_report(2024)
        text = extract_pdf_text(pdf_bytes)

        # Total income should be $1,500
        assert "1,500" in text or "1500" in text, \
            "Report should show $1,500 total income"
