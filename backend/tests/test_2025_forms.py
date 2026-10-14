#!/usr/bin/env python3
"""
Test Suite: 2025 IRS Form Generation

Verifies Form 8949 + Schedule D generation against the 2025 templates,
whose field layout differs from 2024 (Table_Line1_Part1/Part2, zero-padded
row-1 fields, and 11 rows per page instead of 14).

Follows the test_pdf_content.py pattern: authenticated TestClient from
conftest.py, pypdf text extraction, deterministic transactions (explicit
proceeds/cost basis, zero fees — no live price fetches).

Run: pytest backend/tests/test_2025_forms.py -v
"""

import pytest
import io
from datetime import datetime, timezone
from typing import Dict, Optional
from pypdf import PdfReader
from fastapi.testclient import TestClient

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
EXTERNAL = 99

# 2025 Form 8949 table capacity (the 2024 form had 14 rows per page)
ROWS_PER_PAGE_2025 = 11


def delete_all_transactions() -> bool:
    r = CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")
    return r.status_code in (200, 204)


def create_tx(tx_data: Dict) -> Dict:
    r = CLIENT.post("/api/transactions", json=tx_data)
    assert r.is_success, f"create_tx failed ({r.status_code}): {r.text}"
    return r.json()


def build_timestamp(year: int, month: int, day: int, hour: int = 12) -> str:
    dt = datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_irs_report(year: int) -> Optional[bytes]:
    r = CLIENT.get("/api/reports/irs_reports", params={"year": year})
    if r.status_code == 200:
        return r.content
    return None


def extract_pages(pdf_bytes: bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return [page.extract_text() for page in reader.pages]


def seed_short_term_2025(count: int):
    """count buy/sell pairs, all short-term in 2025, each sell fully
    consuming its matching buy lot (distinct amounts keep rows unique)."""
    for i in range(count):
        amount = f"0.{101 + i}"  # 0.101, 0.102, ... distinct per row
        create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2025, 1, i + 1),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": amount,
            "fee_amount": "0",
            "fee_currency": "USD",
            "cost_basis_usd": str(1000 + i),
        })
        create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2025, 3, i + 1),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": amount,
            "fee_amount": "0",
            "fee_currency": "USD",
            "proceeds_usd": str(1500 + i),
        })


def seed_long_term_2025():
    """One long-term disposal: deposit to Wallet mid-2023, spent mid-2025
    (>365 days; Wallet FIFO is separate from the Exchange BTC lots)."""
    create_tx({
        "type": "Deposit",
        "timestamp": build_timestamp(2023, 6, 1),
        "from_account_id": EXTERNAL,
        "to_account_id": WALLET_BTC,
        "amount": "0.5",
        "fee_amount": "0",
        "fee_currency": "BTC",
        "cost_basis_usd": "10000",
        "source": "MyBTC",
    })
    create_tx({
        "type": "Withdrawal",
        "timestamp": build_timestamp(2025, 6, 15),
        "from_account_id": WALLET_BTC,
        "to_account_id": EXTERNAL,
        "amount": "0.5",
        "fee_amount": "0",
        "fee_currency": "BTC",
        "proceeds_usd": "30000",
        "purpose": "Spent",
    })


class Test2025FormGeneration:
    """2025-template generation: capacity, part placement, totals."""

    def test_basic_2025_generation(self):
        """A short and a long disposal in 2025 produce a parseable PDF."""
        delete_all_transactions()
        seed_short_term_2025(1)
        seed_long_term_2025()

        pdf = get_irs_report(2025)
        assert pdf is not None, "2025 IRS report should generate"
        pages = extract_pages(pdf)
        # One 8949 sheet, both Parts used (2 pages) + Schedule D (2 pages)
        assert len(pages) == 4, f"Expected 4 pages, got {len(pages)}"
        full_text = "\n".join(pages)
        assert "2025" in full_text

    def test_all_rows_survive_11_row_pages(self):
        """Regression: 13 short rows exceed the 2025 form's 11-row capacity.
        Every row must appear in the output (the old 14-row chunking wrote
        rows 12-14 to nonexistent fields, silently dropping them)."""
        delete_all_transactions()
        seed_short_term_2025(13)

        pdf = get_irs_report(2025)
        assert pdf is not None
        full_text = "\n".join(extract_pages(pdf))
        for i in range(13):
            amount = f"0.{101 + i}"
            assert amount in full_text, f"Row {i + 1} ({amount} BTC) missing from filled form"

    def test_overflow_creates_second_sheet(self):
        """13 short rows => 2 sheets, each printing only its Part I (#78), + Schedule D (2 pages)."""
        delete_all_transactions()
        seed_short_term_2025(ROWS_PER_PAGE_2025 + 2)

        pdf = get_irs_report(2025)
        assert pdf is not None
        pages = extract_pages(pdf)
        assert len(pages) == 4, f"Expected 4 pages (2 Part I pages + Sched D), got {len(pages)}"

    def test_long_term_lands_in_part_ii(self):
        """Short rows must fill Part I (page 1); long rows Part II (page 2)."""
        delete_all_transactions()
        seed_short_term_2025(2)
        seed_long_term_2025()

        pdf = get_irs_report(2025)
        assert pdf is not None
        pages = extract_pages(pdf)
        part1, part2 = pages[0], pages[1]
        # "Part I" is a substring of "Part II", so anchor on the captions
        assert "Short-Term" in part1
        assert "Long-Term" in part2
        # Short-term amounts on page 1, not page 2
        assert "0.101" in part1 and "0.101" not in part2
        assert "0.102" in part1 and "0.102" not in part2
        # Long-term 0.5 BTC disposal on page 2
        assert "0.50000000" in part2, "Long-term disposal missing from Part II"

    def test_schedule_d_totals_2025(self):
        """Schedule D lines 3/10 carry the SUMMED 8949 totals.

        Assertions are scoped to the Schedule D pages (last two), and both
        terms have two disposals each, so every expected number is a genuine
        sum — it cannot match any single Form 8949 row by coincidence.
        """
        delete_all_transactions()
        seed_short_term_2025(2)  # proceeds 1500+1501, basis 1000+1001
        seed_long_term_2025()    # proceeds 30000, basis 10000
        # Second long-term disposal so long totals differ from any single row
        create_tx({
            "type": "Deposit",
            "timestamp": build_timestamp(2023, 7, 1),
            "from_account_id": EXTERNAL,
            "to_account_id": WALLET_BTC,
            "amount": "0.3",
            "fee_amount": "0",
            "fee_currency": "BTC",
            "cost_basis_usd": "6000",
            "source": "MyBTC",
        })
        create_tx({
            "type": "Withdrawal",
            "timestamp": build_timestamp(2025, 7, 1),
            "from_account_id": WALLET_BTC,
            "to_account_id": EXTERNAL,
            "amount": "0.3",
            "fee_amount": "0",
            "fee_currency": "BTC",
            "proceeds_usd": "18000",
            "purpose": "Spent",
        })

        pdf = get_irs_report(2025)
        assert pdf is not None
        sched_d_text = "\n".join(extract_pages(pdf)[-2:])
        # Short-term totals (line 3): 1500+1501 / 1000+1001 / 500+500
        assert "3001.00" in sched_d_text, "Short-term proceeds total missing from Schedule D"
        assert "2001.00" in sched_d_text, "Short-term cost total missing from Schedule D"
        assert "1000.00" in sched_d_text, "Short-term gain total missing from Schedule D"
        # Long-term totals (line 10): 30000+18000 / 10000+6000 / 20000+12000
        assert "48000.00" in sched_d_text, "Long-term proceeds total missing from Schedule D"
        assert "16000.00" in sched_d_text, "Long-term cost total missing from Schedule D"
        assert "32000.00" in sched_d_text, "Long-term gain total missing from Schedule D"

    def test_2024_capacity_unchanged(self):
        """The 2024 path still packs 14 rows on one sheet (no regression)."""
        delete_all_transactions()
        for i in range(14):
            amount = f"0.{201 + i}"
            create_tx({
                "type": "Buy",
                "timestamp": build_timestamp(2024, 1, i + 1),
                "from_account_id": EXCHANGE_USD,
                "to_account_id": EXCHANGE_BTC,
                "amount": amount,
                "fee_amount": "0",
                "fee_currency": "USD",
                "cost_basis_usd": str(2000 + i),
            })
            create_tx({
                "type": "Sell",
                "timestamp": build_timestamp(2024, 3, i + 1),
                "from_account_id": EXCHANGE_BTC,
                "to_account_id": EXCHANGE_USD,
                "amount": amount,
                "fee_amount": "0",
                "fee_currency": "USD",
                "proceeds_usd": str(2500 + i),
            })

        pdf = get_irs_report(2024)
        assert pdf is not None
        pages = extract_pages(pdf)
        # 14 rows fit one 2024 sheet: its Part I (no empty Part II, #78) + 2 pages Schedule D
        assert len(pages) == 3, f"Expected 3 pages, got {len(pages)}"
        full_text = "\n".join(pages)
        for i in range(14):
            assert f"0.{201 + i}" in full_text, f"2024 row {i + 1} missing"
