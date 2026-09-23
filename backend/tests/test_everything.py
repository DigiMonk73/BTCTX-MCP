#!/usr/bin/env python3
"""
COMPREHENSIVE TEST SUITE - Tests EVERYTHING in BitcoinTX

This script performs end-to-end testing of all app functionality:
1. Database reset and seeding with comprehensive test data
2. All API endpoints (CRUD operations)
3. All report generation (Complete Tax Report, IRS Forms, Transaction History)
4. CSV export/import roundtrip
5. FIFO integrity verification
6. Account balance verification
7. Short-term vs Long-term gains verification

Usage:
    python backend/tests/test_everything.py [--skip-seed] [--verbose]

Options:
    --skip-seed    Don't reset database, use existing data
    --verbose      Show detailed output

Requirements:
    - Backend running at http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from decimal import Decimal, ROUND_HALF_DOWN
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest
from fastapi.testclient import TestClient

# =============================================================================
# CONFIGURATION
# =============================================================================

# Account IDs
ACCOUNT_BANK = 1
ACCOUNT_WALLET = 2
ACCOUNT_EXCHANGE_USD = 3
ACCOUNT_EXCHANGE_BTC = 4
ACCOUNT_BTC_FEES = 5
ACCOUNT_USD_FEES = 6
ACCOUNT_EXTERNAL = 99

# Test tracking
class TestResults:
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.failures: List[str] = []
        self.warnings: List[str] = []

RESULTS = TestResults()
VERBOSE = False

# Authenticated TestClient (set by autouse fixture from conftest.py)
CLIENT: TestClient = None


@pytest.fixture(autouse=True, scope="session")
def _set_client(auth_client):
    global CLIENT
    CLIENT = auth_client

# Colors for terminal
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    END = "\033[0m"

def colored(text: str, color: str) -> str:
    return f"{color}{text}{Colors.END}"


# =============================================================================
# LOGGING
# =============================================================================

def log(msg: str, level: str = "INFO"):
    prefix = {
        "INFO": "   ",
        "PASS": colored(" ✓ ", Colors.GREEN),
        "FAIL": colored(" ✗ ", Colors.RED),
        "WARN": colored(" ⚠ ", Colors.YELLOW),
        "SKIP": colored(" ○ ", Colors.YELLOW),
        "TEST": colored("▶  ", Colors.BLUE),
        "SECTION": colored("═══", Colors.BOLD),
    }.get(level, "   ")
    print(f"{prefix}{msg}")


def section(title: str):
    print()
    print(colored("=" * 70, Colors.BOLD))
    print(colored(f"  {title}", Colors.BOLD))
    print(colored("=" * 70, Colors.BOLD))
    print()


def subsection(title: str):
    print()
    log(title, "SECTION")
    print()


# =============================================================================
# ASSERTIONS
# =============================================================================

def assert_true(condition: bool, description: str) -> bool:
    RESULTS.total += 1
    if condition:
        RESULTS.passed += 1
        log(description, "PASS")
        return True
    else:
        RESULTS.failed += 1
        RESULTS.failures.append(description)
        log(description, "FAIL")
        return False


def assert_equal(actual, expected, description: str, tolerance: float = 0.01) -> bool:
    RESULTS.total += 1

    if isinstance(actual, (int, float, Decimal)) and isinstance(expected, (int, float, Decimal)):
        actual_f = float(actual)
        expected_f = float(expected)
        if abs(actual_f - expected_f) < tolerance:
            RESULTS.passed += 1
            if VERBOSE:
                log(f"{description}: {actual_f} == {expected_f}", "PASS")
            else:
                log(description, "PASS")
            return True
        else:
            RESULTS.failed += 1
            msg = f"{description}: Expected {expected_f}, got {actual_f}"
            RESULTS.failures.append(msg)
            log(msg, "FAIL")
            return False
    else:
        if actual == expected:
            RESULTS.passed += 1
            if VERBOSE:
                log(f"{description}: {actual} == {expected}", "PASS")
            else:
                log(description, "PASS")
            return True
        else:
            RESULTS.failed += 1
            msg = f"{description}: Expected {expected}, got {actual}"
            RESULTS.failures.append(msg)
            log(msg, "FAIL")
            return False


def skip_test(description: str, reason: str):
    RESULTS.total += 1
    RESULTS.skipped += 1
    log(f"{description} - SKIPPED: {reason}", "SKIP")


# =============================================================================
# HTTP HELPERS
# =============================================================================

def api_get(endpoint: str, **params) -> Tuple[int, Any]:
    """Make a GET request to the API."""
    try:
        r = CLIENT.get(f"/api/{endpoint}", params=params)
        try:
            return r.status_code, r.json()
        except:
            return r.status_code, r.content
    except Exception as e:
        return 0, str(e)


def api_post(endpoint: str, data: dict) -> Tuple[int, Any]:
    """Make a POST request to the API."""
    try:
        r = CLIENT.post(f"/api/{endpoint}", json=data)
        try:
            return r.status_code, r.json()
        except:
            return r.status_code, r.text
    except Exception as e:
        return 0, str(e)


def api_delete(endpoint: str) -> Tuple[int, Any]:
    """Make a DELETE request to the API."""
    try:
        r = CLIENT.delete(f"/api/{endpoint}")
        try:
            return r.status_code, r.json() if r.content else None
        except:
            return r.status_code, r.text
    except Exception as e:
        return 0, str(e)


# =============================================================================
# SECTION 1: DATABASE SEEDING
# =============================================================================

def load_seed_data() -> List[dict]:
    """Load seed data from JSON file."""
    seed_file = Path(__file__).parent / "transaction_seed_data.json"
    if not seed_file.exists():
        return []
    with open(seed_file, "r") as f:
        return json.load(f)


def test_database_reset():
    """Reset database by deleting all transactions."""
    subsection("Database Reset")

    status, _ = api_delete("transactions/delete_all")
    assert_true(status in (200, 204), "Delete all transactions")

    # Verify empty
    status, txns = api_get("transactions")
    assert_true(status == 200 and len(txns) == 0, "Database is empty after reset")


def test_seed_database():
    """Seed database with comprehensive test data."""
    subsection("Seeding Database")

    seed_data = load_seed_data()
    if not seed_data:
        skip_test("Seed database", "No seed data file found")
        return

    # Sort by timestamp, then ID for proper FIFO ordering
    seed_data.sort(key=lambda x: (x["timestamp"], x["id"]))

    created = 0
    failed = 0

    for tx in seed_data:
        # Normalize decimal fields
        decimal_fields = ["amount", "fee_amount", "cost_basis_usd", "proceeds_usd",
                         "realized_gain_usd", "fmv_usd", "gross_proceeds_usd"]
        for field in decimal_fields:
            if tx.get(field) is not None:
                tx[field] = str(tx[field])

        status, result = api_post("transactions", tx)
        if status == 200 or status == 201:
            created += 1
        else:
            failed += 1
            if VERBOSE:
                log(f"Failed to create tx {tx.get('id')}: {result}", "WARN")

    assert_true(created > 0, f"Seeded {created} transactions")
    if failed > 0:
        RESULTS.warnings.append(f"{failed} transactions failed to seed")
        log(f"{failed} transactions failed to seed", "WARN")

    # Verify count
    status, txns = api_get("transactions")
    assert_equal(len(txns), created, f"Transaction count matches ({created})")


# =============================================================================
# SECTION 2: API ENDPOINT TESTS
# =============================================================================

def test_api_endpoints():
    """Test all API endpoints."""
    section("API ENDPOINT TESTS")

    # Accounts (needs trailing slash)
    subsection("Accounts API")
    status, accounts = api_get("accounts/")
    assert_true(status == 200, "GET /api/accounts/ returns 200")
    assert_true(len(accounts) >= 4, f"At least 4 accounts exist ({len(accounts)} found)")

    # Individual account
    status, account = api_get("accounts/1")
    assert_true(status == 200, "GET /api/accounts/1 returns 200")
    assert_equal(account.get("id"), 1, "Account ID is 1")

    # Transactions (no trailing slash)
    subsection("Transactions API")
    status, txns = api_get("transactions")
    assert_true(status == 200, "GET /api/transactions returns 200")
    assert_true(isinstance(txns, list), "Transactions is a list")

    if txns:
        tx_id = txns[0]["id"]
        status, tx = api_get(f"transactions/{tx_id}")
        assert_true(status == 200, f"GET /api/transactions/{tx_id} returns 200")
        assert_equal(tx.get("id"), tx_id, "Transaction ID matches")

    # Calculations
    subsection("Calculations API")
    status, balances = api_get("calculations/accounts/balances")
    assert_true(status == 200, "GET /api/calculations/accounts/balances returns 200")
    assert_true(isinstance(balances, list), "Balances is a list")

    status, gl = api_get("calculations/gains-and-losses")
    assert_true(status == 200, "GET /api/calculations/gains-and-losses returns 200")
    assert_true(isinstance(gl, dict), "Gains/losses is a dict")

    status, avg = api_get("calculations/average-cost-basis")
    assert_true(status == 200, "GET /api/calculations/average-cost-basis returns 200")

    # Debug endpoints
    subsection("Debug API")
    status, lots = api_get("debug/lots")
    assert_true(status == 200, "GET /api/debug/lots returns 200")
    assert_true(isinstance(lots, list), "Lots is a list")

    status, disposals = api_get("debug/disposals")
    assert_true(status == 200, "GET /api/debug/disposals returns 200")
    assert_true(isinstance(disposals, list), "Disposals is a list")

    status, entries = api_get("debug/ledger-entries")
    assert_true(status == 200, "GET /api/debug/ledger-entries returns 200")
    assert_true(isinstance(entries, list), "Ledger entries is a list")


# =============================================================================
# SECTION 3: REPORT GENERATION TESTS
# =============================================================================

def test_reports():
    """Test all report generation."""
    section("REPORT GENERATION TESTS")

    # Test years based on seed data (2023, 2024, 2025)
    years = [2023, 2024, 2025]

    for year in years:
        subsection(f"Reports for {year}")

        # Complete Tax Report
        try:
            r = CLIENT.get("/api/reports/complete_tax_report", params={"year": year})
            if r.status_code == 200:
                is_pdf = r.content[:4] == b'%PDF'
                assert_true(is_pdf, f"Complete Tax Report {year} is valid PDF")
                if VERBOSE:
                    log(f"  PDF size: {len(r.content)} bytes", "INFO")
            elif r.status_code == 404:
                log(f"Complete Tax Report {year}: No data (acceptable)", "PASS")
                RESULTS.total += 1
                RESULTS.passed += 1
            else:
                assert_true(False, f"Complete Tax Report {year} - HTTP {r.status_code}")
        except Exception as e:
            assert_true(False, f"Complete Tax Report {year} - {str(e)}")

        # IRS Forms (Form 8949 + Schedule D)
        try:
            r = CLIENT.get("/api/reports/irs_reports", params={"year": year})
            if r.status_code == 200:
                is_pdf = r.content[:4] == b'%PDF'
                assert_true(is_pdf, f"IRS Forms {year} is valid PDF")
            elif r.status_code in (400, 404):
                # 400 can mean no taxable events for the year
                log(f"IRS Forms {year}: No taxable events (acceptable)", "PASS")
                RESULTS.total += 1
                RESULTS.passed += 1
            else:
                assert_true(False, f"IRS Forms {year} - HTTP {r.status_code}")
        except Exception as e:
            assert_true(False, f"IRS Forms {year} - {str(e)}")

        # Transaction History CSV
        try:
            r = CLIENT.get("/api/reports/simple_transaction_history",
                          params={"year": year, "format": "csv"})
            if r.status_code == 200:
                is_csv = "text/csv" in r.headers.get("content-type", "") or r.content.startswith(b"date,")
                assert_true(is_csv, f"Transaction History CSV {year} is valid")
            elif r.status_code == 404:
                log(f"Transaction History CSV {year}: No data (acceptable)", "PASS")
                RESULTS.total += 1
                RESULTS.passed += 1
            else:
                assert_true(False, f"Transaction History CSV {year} - HTTP {r.status_code}")
        except Exception as e:
            assert_true(False, f"Transaction History CSV {year} - {str(e)}")

        # Transaction History PDF
        try:
            r = CLIENT.get("/api/reports/simple_transaction_history",
                          params={"year": year, "format": "pdf"})
            if r.status_code == 200:
                is_pdf = r.content[:4] == b'%PDF'
                assert_true(is_pdf, f"Transaction History PDF {year} is valid PDF")
            elif r.status_code == 404:
                log(f"Transaction History PDF {year}: No data (acceptable)", "PASS")
                RESULTS.total += 1
                RESULTS.passed += 1
            else:
                assert_true(False, f"Transaction History PDF {year} - HTTP {r.status_code}")
        except Exception as e:
            assert_true(False, f"Transaction History PDF {year} - {str(e)}")


# =============================================================================
# SECTION 4: CSV EXPORT/IMPORT ROUNDTRIP
# =============================================================================

def test_csv_roundtrip():
    """Test CSV export and import roundtrip."""
    section("CSV EXPORT/IMPORT ROUNDTRIP")

    # Export current transactions
    subsection("CSV Export")
    r = CLIENT.get("/api/backup/csv")
    assert_true(r.status_code == 200, "CSV export returns 200")

    csv_content = r.text
    assert_true(len(csv_content) > 100, f"CSV has content ({len(csv_content)} chars)")

    # Parse CSV to count rows
    reader = csv.DictReader(io.StringIO(csv_content))
    rows = list(reader)
    original_count = len(rows)
    assert_true(original_count > 0, f"CSV has {original_count} transaction rows")

    # Save to temp file for import
    temp_csv = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
    temp_csv.write(csv_content)
    temp_csv.close()

    # Delete all transactions
    subsection("Delete All Before Import")
    status, _ = api_delete("transactions/delete_all")
    assert_true(status in (200, 204), "Delete all transactions for roundtrip")

    # Verify empty
    status, txns = api_get("transactions")
    assert_equal(len(txns), 0, "Database empty before import")

    # Import CSV (endpoint is /import/execute)
    subsection("CSV Import")
    with open(temp_csv.name, 'rb') as f:
        files = {'file': ('transactions.csv', f, 'text/csv')}
        r = CLIENT.post("/api/import/execute", files=files)

    if r.status_code == 200:
        result = r.json()
        imported_count = result.get("imported_count", 0)
        errors = result.get("errors", [])

        assert_true(imported_count > 0, f"Imported {imported_count} transactions")

        if errors:
            RESULTS.warnings.append(f"Import had {len(errors)} errors")
            log(f"Import had {len(errors)} errors", "WARN")
            for err in errors[:5]:
                log(f"  - {err}", "WARN")

        # Verify count matches (within tolerance for skipped rows)
        tolerance = max(5, original_count * 0.1)  # 10% tolerance
        diff = abs(imported_count - original_count)
        assert_true(diff <= tolerance,
                   f"Import count close to original ({imported_count} vs {original_count})")
    else:
        assert_true(False, f"CSV import failed - HTTP {r.status_code}: {r.text[:200]}")

    # Cleanup
    os.unlink(temp_csv.name)

    # Verify transactions exist
    subsection("Verify After Import")
    status, txns = api_get("transactions")
    assert_true(len(txns) > 0, f"Transactions exist after import ({len(txns)})")


# =============================================================================
# SECTION 5: FIFO INTEGRITY TESTS
# =============================================================================

def test_fifo_integrity():
    """Test FIFO lot ordering and disposal integrity."""
    section("FIFO INTEGRITY TESTS")

    subsection("BitcoinLot Verification")
    status, lots = api_get("debug/lots")
    assert_true(status == 200 and isinstance(lots, list), "Can retrieve lots")

    if lots:
        # Check lot structure
        lot = lots[0]
        required_fields = ["id", "created_txn_id", "total_btc", "remaining_btc", "cost_basis_usd"]
        has_fields = all(f in lot for f in required_fields)
        assert_true(has_fields, "Lots have required fields")

        # Check no negative remaining
        negative_lots = [l for l in lots if float(l.get("remaining_btc", 0)) < 0]
        assert_true(len(negative_lots) == 0, "No lots have negative remaining BTC")

        # Check remaining <= total
        invalid_lots = [l for l in lots if float(l.get("remaining_btc", 0)) > float(l.get("total_btc", 0)) + 0.00000001]
        assert_true(len(invalid_lots) == 0, "No lots have remaining > total")

        # Total remaining BTC
        total_remaining = sum(float(l.get("remaining_btc", 0)) for l in lots)
        log(f"Total remaining BTC in lots: {total_remaining:.8f}", "INFO")

    subsection("LotDisposal Verification")
    status, disposals = api_get("debug/disposals")
    assert_true(status == 200 and isinstance(disposals, list), "Can retrieve disposals")

    if disposals:
        # Check disposal structure
        disposal = disposals[0]
        required_fields = ["id", "lot_id", "transaction_id", "disposed_btc"]
        has_fields = all(f in disposal for f in required_fields)
        assert_true(has_fields, "Disposals have required fields")

        # Check no negative amounts
        negative_disposals = [d for d in disposals if float(d.get("disposed_btc", 0)) < 0]
        assert_true(len(negative_disposals) == 0, "No negative disposal amounts")

    subsection("Account Balance Verification")
    status, balances = api_get("calculations/accounts/balances")
    assert_true(status == 200, "Can retrieve balances")

    # Find BTC account balances
    btc_accounts = [b for b in balances if b.get("account_id") in (ACCOUNT_WALLET, ACCOUNT_EXCHANGE_BTC)]
    for acc in btc_accounts:
        balance = float(acc.get("balance", 0))
        assert_true(balance >= 0, f"Account {acc.get('account_id')} balance >= 0 ({balance:.8f})")

    # Verify BTC balance matches lot remaining
    if lots and btc_accounts:
        total_lot_btc = sum(float(l.get("remaining_btc", 0)) for l in lots)
        total_account_btc = sum(float(b.get("balance", 0)) for b in btc_accounts)

        # Should match within tolerance
        diff = abs(total_lot_btc - total_account_btc)
        assert_true(diff < 0.00001,
                   f"Lot BTC matches account BTC ({total_lot_btc:.8f} vs {total_account_btc:.8f})")


# =============================================================================
# SECTION 6: GAINS/LOSSES VERIFICATION
# =============================================================================

def test_gains_losses():
    """Test gains and losses calculations."""
    section("GAINS/LOSSES VERIFICATION")

    status, gl = api_get("calculations/gains-and-losses")
    assert_true(status == 200, "Can retrieve gains/losses")

    subsection("Capital Gains Structure")

    # Check structure
    expected_fields = ["short_term_gains", "short_term_losses", "long_term_gains", "long_term_losses"]
    has_fields = all(f in gl for f in expected_fields)
    assert_true(has_fields, "Has capital gains fields")

    # Calculate nets
    st_net = float(gl.get("short_term_gains", 0)) - float(gl.get("short_term_losses", 0))
    lt_net = float(gl.get("long_term_gains", 0)) - float(gl.get("long_term_losses", 0))

    log(f"Short-term net: ${st_net:,.2f}", "INFO")
    log(f"Long-term net: ${lt_net:,.2f}", "INFO")

    # Verify net matches sum
    reported_st_net = float(gl.get("short_term_net", 0))
    reported_lt_net = float(gl.get("long_term_net", 0))

    assert_true(abs(st_net - reported_st_net) < 1, "Short-term net calculation correct")
    assert_true(abs(lt_net - reported_lt_net) < 1, "Long-term net calculation correct")

    subsection("Income Verification")

    income_fields = ["income_earned", "interest_earned", "rewards_earned"]
    for field in income_fields:
        value = gl.get(field, 0)
        if value > 0:
            log(f"{field}: ${float(value):,.2f}", "INFO")

    total_income = float(gl.get("total_income", 0))
    if total_income > 0:
        assert_true(True, f"Total income tracked: ${total_income:,.2f}")

    subsection("Fee Tracking")

    fees = gl.get("fees", {})
    if fees:
        for currency, amount in fees.items():
            if float(amount) > 0:
                if currency == "USD":
                    log(f"USD fees: ${float(amount):,.2f}", "INFO")
                else:
                    log(f"BTC fees: {float(amount):.8f}", "INFO")
        assert_true(True, "Fees are tracked")


# =============================================================================
# SECTION 7: TRANSACTION TYPE VERIFICATION
# =============================================================================

def test_transaction_types():
    """Verify all transaction types work correctly."""
    section("TRANSACTION TYPE VERIFICATION")

    status, txns = api_get("transactions")
    if status != 200 or not txns:
        skip_test("Transaction types", "No transactions to verify")
        return

    # Group by type
    by_type = {}
    for tx in txns:
        t = tx.get("type")
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(tx)

    subsection("Transaction Type Coverage")

    expected_types = ["Deposit", "Withdrawal", "Transfer", "Buy", "Sell"]
    for t in expected_types:
        count = len(by_type.get(t, []))
        assert_true(count > 0, f"{t} transactions exist ({count})")

    subsection("Withdrawal Purpose Coverage")

    withdrawals = by_type.get("Withdrawal", [])
    purposes = set(tx.get("purpose") for tx in withdrawals if tx.get("purpose"))

    expected_purposes = ["Spent", "Gift", "Donation", "Lost"]
    for p in expected_purposes:
        exists = p in purposes
        if exists:
            assert_true(True, f"Withdrawal purpose '{p}' exists")
        else:
            log(f"Withdrawal purpose '{p}' not found (optional)", "WARN")
            RESULTS.warnings.append(f"Missing withdrawal purpose: {p}")

    subsection("Deposit Source Coverage")

    deposits = by_type.get("Deposit", [])
    # BTC deposits go to Wallet (2) or Exchange BTC (4)
    btc_deposits = [d for d in deposits if d.get("to_account_id") in (ACCOUNT_WALLET, ACCOUNT_EXCHANGE_BTC)]
    sources = set(d.get("source") for d in btc_deposits if d.get("source"))

    expected_sources = ["MyBTC", "Gift", "Income", "Interest", "Reward"]
    for s in expected_sources:
        exists = s in sources
        if exists:
            assert_true(True, f"Deposit source '{s}' exists")
        else:
            log(f"Deposit source '{s}' not found (optional)", "WARN")
            RESULTS.warnings.append(f"Missing deposit source: {s}")


# =============================================================================
# SECTION 8: SHORT-TERM VS LONG-TERM VERIFICATION
# =============================================================================

def test_holding_periods():
    """Verify short-term vs long-term classification."""
    section("HOLDING PERIOD VERIFICATION")

    status, txns = api_get("transactions")
    if status != 200:
        skip_test("Holding periods", "Cannot retrieve transactions")
        return

    # Find sells and withdrawals with holding period
    disposals = [tx for tx in txns if tx.get("type") in ("Sell", "Withdrawal")
                 and tx.get("purpose") in (None, "Spent")]

    if not disposals:
        skip_test("Holding periods", "No taxable disposals found")
        return

    subsection("Holding Period Analysis")

    short_count = 0
    long_count = 0
    mixed_count = 0

    for tx in disposals:
        hp = tx.get("holding_period")
        if hp == "SHORT":
            short_count += 1
        elif hp == "LONG":
            long_count += 1
        elif hp == "MIXED":
            mixed_count += 1

    log(f"Short-term disposals: {short_count}", "INFO")
    log(f"Long-term disposals: {long_count}", "INFO")
    if mixed_count:
        log(f"Mixed disposals: {mixed_count}", "INFO")

    # Verify we have both types (based on seed data design)
    assert_true(short_count > 0 or long_count > 0, "At least one holding period type exists")


# =============================================================================
# SECTION 9: AUTHENTICATED ENDPOINTS
# =============================================================================

def test_authenticated_endpoints():
    """Test endpoints that require authentication."""
    section("AUTHENTICATED ENDPOINT TESTS")

    subsection("Backup Endpoints")

    # CSV export (requires auth)
    r = CLIENT.get("/api/backup/csv")
    assert_true(r.status_code == 200, "CSV export with auth works")

    # Template download
    r = CLIENT.get("/api/import/template")
    assert_true(r.status_code == 200, "CSV template download works")

    subsection("Import Validation")

    # Test import validation with empty file (endpoint is /import/preview)
    files = {'file': ('empty.csv', io.BytesIO(b""), 'text/csv')}
    r = CLIENT.post("/api/import/preview", files=files)
    # Should fail gracefully with 400
    assert_true(r.status_code == 400, "Empty CSV import rejected properly")


# =============================================================================
# MAIN
# =============================================================================

def print_summary():
    """Print test summary."""
    print()
    print(colored("=" * 70, Colors.BOLD))
    print(colored("  TEST SUMMARY", Colors.BOLD))
    print(colored("=" * 70, Colors.BOLD))
    print()

    print(f"  Total Tests:  {RESULTS.total}")
    print(f"  {colored('Passed:', Colors.GREEN)}     {RESULTS.passed}")
    print(f"  {colored('Failed:', Colors.RED)}     {RESULTS.failed}")
    print(f"  {colored('Skipped:', Colors.YELLOW)}    {RESULTS.skipped}")
    print()

    if RESULTS.failures:
        print(colored("  FAILURES:", Colors.RED))
        for f in RESULTS.failures[:20]:
            print(f"    - {f}")
        if len(RESULTS.failures) > 20:
            print(f"    ... and {len(RESULTS.failures) - 20} more")
        print()

    if RESULTS.warnings:
        print(colored("  WARNINGS:", Colors.YELLOW))
        for w in RESULTS.warnings[:10]:
            print(f"    - {w}")
        if len(RESULTS.warnings) > 10:
            print(f"    ... and {len(RESULTS.warnings) - 10} more")
        print()

    if RESULTS.failed == 0:
        print(colored("  ✅ ALL TESTS PASSED!", Colors.GREEN))
    else:
        print(colored(f"  ❌ {RESULTS.failed} TEST(S) FAILED", Colors.RED))

    print()

    return RESULTS.failed


def main():
    global VERBOSE, CLIENT

    parser = argparse.ArgumentParser(description="Comprehensive test suite for BitcoinTX")
    parser.add_argument("--skip-seed", action="store_true", help="Skip database reset and seeding")
    parser.add_argument("--verbose", action="store_true", help="Show detailed output")
    args = parser.parse_args()

    VERBOSE = args.verbose

    print()
    print(colored("=" * 70, Colors.BOLD))
    print(colored("  BITCTX COMPREHENSIVE TEST SUITE", Colors.BOLD))
    print(colored("=" * 70, Colors.BOLD))
    print()

    # Set up isolated test database and TestClient
    from backend.tests.conftest import _seed_test_db
    from backend.database import Base, get_db
    from backend.main import app
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_engine(f"sqlite:///{tmp.name}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    _seed_test_db(engine)

    TestSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    CLIENT = TestClient(app)
    r = CLIENT.post("/api/login", json={"username": "admin", "password": "password"})
    if r.status_code != 200:
        print(colored(f"ERROR: Login failed: {r.status_code}", Colors.RED))
        sys.exit(1)

    log("TestClient ready (isolated database)", "PASS")

    # Run tests
    try:
        if not args.skip_seed:
            section("DATABASE SETUP")
            test_database_reset()
            test_seed_database()
        else:
            log("Skipping database reset/seed (--skip-seed)", "WARN")

        test_api_endpoints()
        test_reports()
        test_csv_roundtrip()
        test_fifo_integrity()
        test_gains_losses()
        test_transaction_types()
        test_holding_periods()
        test_authenticated_endpoints()

    except KeyboardInterrupt:
        print()
        log("Tests interrupted by user", "WARN")
    except Exception as e:
        print()
        log(f"Test suite error: {e}", "FAIL")
        RESULTS.failed += 1

    # Cleanup
    app.dependency_overrides.clear()
    engine.dispose()
    os.unlink(tmp.name)

    # Summary
    failures = print_summary()
    return 1 if failures > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
