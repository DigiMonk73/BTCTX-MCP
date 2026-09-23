#!/usr/bin/env python3
"""
Pre-Commit Test Suite for BitcoinTX

This script runs a comprehensive battery of tests before each commit to ensure:
1. Docker/StartOS compatibility (no hardcoded paths, proper env vars)
2. Transaction/FIFO integrity (scorched earth recalculation works)
3. Report generation accuracy (Form 8949, Schedule D, Complete Tax Report)
4. CSV import/export roundtrip works
5. Non-taxable disposals correctly excluded from tax forms

Run this script before every commit, especially when modifying backend code.

Usage:
    python backend/tests/pre_commit_tests.py [--quick] [--no-api] [--verbose]

Options:
    --quick     Skip long-running tests (report generation, stress tests)
    --no-api    Skip API tests (only run static checks)
    --verbose   Show detailed output

Requirements:
    - Backend running at http://127.0.0.1:8000 (for API tests)
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Colors for terminal output
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"

def colored(text: str, color: str) -> str:
    """Return colored text for terminal."""
    return f"{color}{text}{Colors.END}"

# Test results tracking
RESULTS: Dict[str, List[Tuple[str, bool, str]]] = {}
VERBOSE = False


def log(msg: str, level: str = "INFO"):
    """Print formatted log message."""
    prefix = {
        "INFO": "   ",
        "PASS": colored(" ✓ ", Colors.GREEN),
        "FAIL": colored(" ✗ ", Colors.RED),
        "WARN": colored(" ⚠ ", Colors.YELLOW),
        "TEST": colored("▶  ", Colors.BLUE),
        "SECTION": colored("═══", Colors.BOLD),
    }.get(level, "   ")
    print(f"{prefix}{msg}")


def record_result(category: str, test_name: str, passed: bool, details: str = ""):
    """Record a test result."""
    if category not in RESULTS:
        RESULTS[category] = []
    RESULTS[category].append((test_name, passed, details))
    if passed:
        log(f"{test_name}", "PASS")
    else:
        log(f"{test_name}: {details}", "FAIL")


# =============================================================================
# SECTION 1: STATIC CODE ANALYSIS (Docker/StartOS Compatibility)
# =============================================================================

def check_hardcoded_database_paths() -> bool:
    """
    Check that no Python files have hardcoded database paths.
    All database access should use DATABASE_FILE env var.
    """
    project_root = Path(__file__).parent.parent.parent
    backend_dir = project_root / "backend"

    # Patterns that indicate hardcoded paths (bad)
    bad_patterns = [
        r'["\']backend/bitcoin_tracker\.db["\']',
        r'["\']bitcoin_tracker\.db["\']',
        r'["\']\.?/data/btctx\.db["\']',  # Direct path without env var
        r'Path\s*\(["\'].*\.db["\']\)',  # Path("something.db") without env var
    ]

    # Files/patterns that are exceptions (allowed)
    exceptions = [
        "pre_commit_tests.py",  # This file
        "test_",  # Test files may have hardcoded test paths
        "__pycache__",
        ".pyc",
    ]

    violations = []

    for py_file in backend_dir.rglob("*.py"):
        # Skip exceptions
        if any(exc in str(py_file) for exc in exceptions):
            continue

        try:
            content = py_file.read_text()
            for pattern in bad_patterns:
                matches = re.findall(pattern, content)
                if matches:
                    # Check if it's in a proper env var context
                    # Allow: os.getenv("DATABASE_FILE", "backend/bitcoin_tracker.db")
                    for match in matches:
                        # Look for the line containing the match
                        for i, line in enumerate(content.split("\n"), 1):
                            if match in line and "getenv" not in line and "DATABASE_FILE" not in line:
                                violations.append(f"{py_file.relative_to(project_root)}:{i}: {line.strip()}")
        except Exception as e:
            if VERBOSE:
                log(f"Could not read {py_file}: {e}", "WARN")

    passed = len(violations) == 0
    details = "; ".join(violations[:3]) if violations else ""
    if len(violations) > 3:
        details += f" (+{len(violations) - 3} more)"
    record_result("Docker/StartOS Compatibility", "No hardcoded database paths", passed, details)
    return passed


def check_database_file_env_usage() -> bool:
    """
    Verify that DATABASE_FILE env var is used in critical files.
    """
    project_root = Path(__file__).parent.parent.parent

    critical_files = [
        ("backend/database.py", ["DATABASE_FILE", "os.getenv"]),
        ("backend/services/backup.py", ["DATABASE_FILE", "os.getenv"]),
    ]

    violations = []

    for file_path, required_patterns in critical_files:
        full_path = project_root / file_path
        if not full_path.exists():
            violations.append(f"{file_path} not found")
            continue

        content = full_path.read_text()
        for pattern in required_patterns:
            if pattern not in content:
                violations.append(f"{file_path} missing '{pattern}'")

    passed = len(violations) == 0
    details = "; ".join(violations)
    record_result("Docker/StartOS Compatibility", "DATABASE_FILE env var used correctly", passed, details)
    return passed


def check_no_hardcoded_localhost_urls() -> bool:
    """
    Check that backend code doesn't use hardcoded localhost URLs for internal calls.
    (This caused the Docker BTC price bug)
    """
    project_root = Path(__file__).parent.parent.parent
    backend_services = project_root / "backend" / "services"

    # Pattern for hardcoded localhost API calls
    bad_patterns = [
        r'localhost:\d+/api',
        r'127\.0\.0\.1:\d+/api',
        r'http://localhost',
        r'http://127\.0\.0\.1',
    ]

    # Exceptions
    exceptions = [
        "test_",
        "__pycache__",
        "pre_commit_tests.py",
    ]

    violations = []

    for py_file in backend_services.rglob("*.py"):
        if any(exc in str(py_file) for exc in exceptions):
            continue

        try:
            content = py_file.read_text()
            for pattern in bad_patterns:
                matches = re.finditer(pattern, content)
                for match in matches:
                    # Find line number
                    line_num = content[:match.start()].count("\n") + 1
                    violations.append(f"{py_file.name}:{line_num}")
        except Exception as e:
            if VERBOSE:
                log(f"Could not read {py_file}: {e}", "WARN")

    passed = len(violations) == 0
    details = "; ".join(violations[:3]) if violations else ""
    record_result("Docker/StartOS Compatibility", "No hardcoded localhost URLs in services", passed, details)
    return passed


def check_python39_compatibility() -> bool:
    """
    Every backend file must parse as Python 3.10, the oldest supported
    version (fastapi >= 0.130 requires it; Docker ships 3.11). Uses the real
    parser, so syntax newer than 3.10 is caught without regex false alarms.
    (Name kept for callers; Python 3.9 support was dropped in 2026-09.)
    """
    project_root = Path(__file__).parent.parent.parent
    backend_dir = project_root / "backend"

    violations = []
    for py_file in backend_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        try:
            ast.parse(py_file.read_text(), filename=str(py_file), feature_version=(3, 10))
        except SyntaxError as e:
            violations.append(f"{py_file.relative_to(project_root)}:{e.lineno}: {e.msg}")

    passed = len(violations) == 0
    details = "; ".join(violations[:2]) if violations else ""
    record_result("Docker/StartOS Compatibility", "Python 3.10 compatibility", passed, details)
    return passed


def check_file_operations_use_data_volume() -> bool:
    """
    Check that any file writes for persistent data use /data or env vars.
    """
    project_root = Path(__file__).parent.parent.parent
    backend_dir = project_root / "backend"

    # Patterns that might indicate writing to wrong location
    suspicious_patterns = [
        r'open\(["\'](?!/tmp|/data|\.)[^"\']+["\']\s*,\s*["\']w',  # open("path", "w") not in /tmp or /data
    ]

    violations = []

    for py_file in backend_dir.rglob("*.py"):
        if "__pycache__" in str(py_file) or "test" in py_file.name.lower():
            continue

        try:
            content = py_file.read_text()
            for pattern in suspicious_patterns:
                if re.search(pattern, content):
                    violations.append(str(py_file.relative_to(project_root)))
        except Exception:
            pass

    passed = not violations
    details = "" if passed else f"hardcoded write path in: {', '.join(violations)}"
    record_result("Docker/StartOS Compatibility", "File operations use data volume", passed, details)
    return passed


def check_absolute_paths_in_reports() -> bool:
    """
    Verify that reports.py uses __file__ for template paths (not relative paths).
    """
    project_root = Path(__file__).parent.parent.parent
    reports_file = project_root / "backend" / "routers" / "reports.py"

    if not reports_file.exists():
        record_result("Docker/StartOS Compatibility", "Reports use absolute paths", False, "reports.py not found")
        return False

    content = reports_file.read_text()

    # Check for __file__ usage for path construction
    # Accepts: Path(__file__), os.path.dirname(__file__), os.path.abspath(__file__), etc.
    has_file_reference = "__file__" in content
    has_path_construction = any(pattern in content for pattern in [
        "Path(__file__)",
        "os.path.dirname",
        "os.path.abspath(__file__)",
    ])

    passed = has_file_reference and has_path_construction
    details = "" if passed else "Template paths should use __file__ for Docker compatibility"
    record_result("Docker/StartOS Compatibility", "Reports use absolute paths", passed, details)
    return passed


# =============================================================================
# SECTION 2: API TESTS (Transaction/FIFO Integrity)
# =============================================================================

def check_backend_running() -> bool:
    """Check if backend is running."""
    try:
        import requests
        r = requests.get("http://127.0.0.1:8000/api/accounts/", timeout=5)
        return r.ok
    except Exception:
        return False


def run_comprehensive_transaction_tests() -> bool:
    """Run the comprehensive transaction test suite."""
    project_root = Path(__file__).parent.parent.parent
    test_script = project_root / "backend" / "tests" / "test_comprehensive_transactions.py"

    if not test_script.exists():
        record_result("Transaction Integrity", "Comprehensive transaction tests", False, "test script not found")
        return False

    try:
        result = subprocess.run(
            [sys.executable, str(test_script)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(project_root)
        )

        # Check for success message in output
        passed = "ALL TESTS PASSED" in result.stdout

        if not passed:
            # Extract failure count
            match = re.search(r'(\d+) TEST\(S\) FAILED', result.stdout)
            details = match.group(0) if match else "Tests failed"
        else:
            details = ""

        record_result("Transaction Integrity", "Comprehensive transaction tests", passed, details)
        return passed
    except subprocess.TimeoutExpired:
        record_result("Transaction Integrity", "Comprehensive transaction tests", False, "Timeout (>120s)")
        return False
    except Exception as e:
        record_result("Transaction Integrity", "Comprehensive transaction tests", False, str(e))
        return False


def run_backdated_fifo_test() -> bool:
    """Run the backdated FIFO recalculation test."""
    project_root = Path(__file__).parent.parent.parent
    test_script = project_root / "backend" / "tests" / "test_backdated_fifo.py"

    if not test_script.exists():
        record_result("Transaction Integrity", "Backdated FIFO recalculation", False, "test script not found")
        return False

    try:
        result = subprocess.run(
            [sys.executable, str(test_script)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(project_root)
        )

        passed = "PASS" in result.stdout and "FAIL" not in result.stdout
        details = "" if passed else "Backdated recalculation failed"
        record_result("Transaction Integrity", "Backdated FIFO recalculation", passed, details)
        return passed
    except Exception as e:
        record_result("Transaction Integrity", "Backdated FIFO recalculation", False, str(e))
        return False


# =============================================================================
# SECTION 3: REPORT GENERATION TESTS
# =============================================================================

def test_form_8949_generation() -> bool:
    """Test Form 8949 PDF generation."""
    try:
        import requests

        # Generate Form 8949 for 2024
        r = requests.get(
            "http://127.0.0.1:8000/api/reports/irs_reports",
            params={"year": 2024},
            timeout=30
        )

        if r.status_code == 200:
            # Check it's a valid PDF
            passed = r.content[:4] == b'%PDF'
            details = "" if passed else "Response is not a valid PDF"
        elif r.status_code == 404:
            # No transactions for year - acceptable
            passed = True
            details = "No transactions for 2024 (acceptable)"
        else:
            passed = False
            details = f"HTTP {r.status_code}"

        record_result("Report Generation", "Form 8949 generation", passed, details)
        return passed
    except Exception as e:
        record_result("Report Generation", "Form 8949 generation", False, str(e))
        return False


def test_complete_tax_report() -> bool:
    """Test Complete Tax Report PDF generation."""
    try:
        import requests

        r = requests.get(
            "http://127.0.0.1:8000/api/reports/complete_tax_report",
            params={"year": 2024},
            timeout=30
        )

        if r.status_code == 200:
            passed = r.content[:4] == b'%PDF'
            details = "" if passed else "Response is not a valid PDF"
        elif r.status_code == 404:
            passed = True
            details = "No transactions for 2024 (acceptable)"
        else:
            passed = False
            details = f"HTTP {r.status_code}"

        record_result("Report Generation", "Complete Tax Report generation", passed, details)
        return passed
    except Exception as e:
        record_result("Report Generation", "Complete Tax Report generation", False, str(e))
        return False


def test_form_8949_excludes_nontaxable() -> bool:
    """
    Verify that Form 8949 excludes non-taxable disposals (Gift, Donation, Lost).
    This tests the fix we made to form_8949.py.
    """
    project_root = Path(__file__).parent.parent.parent
    form_8949_file = project_root / "backend" / "services" / "reports" / "form_8949.py"

    if not form_8949_file.exists():
        record_result("Report Generation", "Form 8949 excludes non-taxable", False, "form_8949.py not found")
        return False

    content = form_8949_file.read_text()

    # Check for NON_TAXABLE_PURPOSES constant and filter
    has_nontaxable_const = "NON_TAXABLE_PURPOSES" in content
    has_purpose_filter = "Transaction.purpose" in content and "Gift" in content

    passed = has_nontaxable_const and has_purpose_filter
    details = "" if passed else "Missing filter for Gift/Donation/Lost disposals"
    record_result("Report Generation", "Form 8949 excludes non-taxable disposals", passed, details)
    return passed


# =============================================================================
# SECTION 4: CSV IMPORT/EXPORT TESTS
# =============================================================================

def test_csv_export_endpoint() -> bool:
    """Test that CSV export endpoint exists and returns CSV."""
    try:
        import requests

        # Need to be authenticated for this endpoint
        session = requests.Session()

        # Login first (endpoint is /api/login, not /api/auth/login)
        login_r = session.post(
            "http://127.0.0.1:8000/api/login",
            json={"username": "admin", "password": "password"}
        )

        if login_r.status_code != 200:
            record_result("CSV Import/Export", "CSV export endpoint", False, f"Could not authenticate: {login_r.status_code}")
            return False

        # Try to export
        r = session.get("http://127.0.0.1:8000/api/backup/csv", timeout=10)

        passed = r.status_code == 200 and "text/csv" in r.headers.get("content-type", "")
        details = "" if passed else f"HTTP {r.status_code}"
        record_result("CSV Import/Export", "CSV export endpoint", passed, details)
        return passed
    except Exception as e:
        record_result("CSV Import/Export", "CSV export endpoint", False, str(e))
        return False


def test_csv_template_endpoint() -> bool:
    """Test that CSV template download works."""
    try:
        import requests

        # Need to be authenticated for this endpoint
        session = requests.Session()

        # Login first
        login_r = session.post(
            "http://127.0.0.1:8000/api/login",
            json={"username": "admin", "password": "password"}
        )

        if login_r.status_code != 200:
            record_result("CSV Import/Export", "CSV template endpoint", False, f"Could not authenticate: {login_r.status_code}")
            return False

        r = session.get("http://127.0.0.1:8000/api/import/template", timeout=10)

        passed = r.status_code == 200 and "text/csv" in r.headers.get("content-type", "")
        details = "" if passed else f"HTTP {r.status_code}"
        record_result("CSV Import/Export", "CSV template endpoint", passed, details)
        return passed
    except Exception as e:
        record_result("CSV Import/Export", "CSV template endpoint", False, str(e))
        return False


def test_csv_roundtrip_format_check() -> bool:
    """
    Check that CSV export uses the same columns as CSV import template.
    """
    project_root = Path(__file__).parent.parent.parent

    # Check backup.py CSV_COLUMNS matches csv_import.py generate_template_csv columns
    backup_file = project_root / "backend" / "routers" / "backup.py"
    import_file = project_root / "backend" / "services" / "csv_import.py"

    if not backup_file.exists() or not import_file.exists():
        record_result("CSV Import/Export", "CSV format consistency", False, "Required files not found")
        return False

    backup_content = backup_file.read_text()
    import_content = import_file.read_text()

    # Check that common columns exist in both
    common_cols = ["date", "type", "amount", "from_account", "to_account", "cost_basis_usd", "proceeds_usd"]

    passed = all(col in backup_content for col in common_cols) and all(col in import_content for col in common_cols)
    details = "" if passed else "CSV column mismatch between import/export"
    record_result("CSV Import/Export", "CSV format consistency", passed, details)
    return passed


# =============================================================================
# SECTION 5: TRANSACTION CODE INTEGRITY CHECKS
# =============================================================================

def check_transaction_service_integrity() -> bool:
    """
    Verify critical patterns in transaction.py:
    - scorched earth recalculation exists
    - FIFO ordering is by timestamp, then ID
    - proceeds_usd uses tx.proceeds_usd (not tx_data degradation)
    """
    project_root = Path(__file__).parent.parent.parent
    tx_file = project_root / "backend" / "services" / "transaction.py"

    if not tx_file.exists():
        record_result("Transaction Code", "Service file exists", False, "transaction.py not found")
        return False

    content = tx_file.read_text()

    checks = []

    # Check 1: recalculate_all_transactions exists
    checks.append(("recalculate_all_transactions function", "def recalculate_all_transactions" in content))

    # Check 2: FIFO uses timestamp ordering
    checks.append(("FIFO timestamp ordering", "order_by" in content and "timestamp" in content))

    # Check 3: proceeds_usd fix (use tx.proceeds_usd when available)
    checks.append(("proceeds_usd degradation fix", "tx.proceeds_usd" in content))

    # Check 4: Backdated detection exists
    checks.append(("Backdated transaction detection", "Backdated" in content or "backdated" in content))

    all_passed = all(passed for _, passed in checks)
    failed = [name for name, passed in checks if not passed]
    details = "; ".join(failed) if failed else ""

    record_result("Transaction Code", "Critical patterns present", all_passed, details)
    return all_passed


def check_form_8949_query_integrity() -> bool:
    """
    Verify Form 8949 query properly joins and filters.
    """
    project_root = Path(__file__).parent.parent.parent
    form_8949_file = project_root / "backend" / "services" / "reports" / "form_8949.py"

    if not form_8949_file.exists():
        record_result("Transaction Code", "Form 8949 query integrity", False, "form_8949.py not found")
        return False

    content = form_8949_file.read_text()

    checks = []

    # Check 1: Query joins LotDisposal with Transaction
    checks.append(("Joins LotDisposal with Transaction", "join" in content.lower() and "Transaction" in content))

    # Check 2: Filters by date range
    checks.append(("Date range filtering", "start_date" in content and "end_date" in content))

    # Check 3: Excludes non-taxable purposes
    checks.append(("Non-taxable exclusion", "NON_TAXABLE_PURPOSES" in content or "Gift" in content))

    all_passed = all(passed for _, passed in checks)
    failed = [name for name, passed in checks if not passed]
    details = "; ".join(failed) if failed else ""

    record_result("Transaction Code", "Form 8949 query integrity", all_passed, details)
    return all_passed


# =============================================================================
# MAIN TEST RUNNER
# =============================================================================

def run_static_checks() -> int:
    """Run all static code analysis checks."""
    log("Docker/StartOS Compatibility Checks", "SECTION")
    print()

    checks = [
        check_hardcoded_database_paths,
        check_database_file_env_usage,
        check_no_hardcoded_localhost_urls,
        check_python39_compatibility,
        check_absolute_paths_in_reports,
        check_file_operations_use_data_volume,
    ]

    failures = 0
    for check in checks:
        try:
            if not check():
                failures += 1
        except Exception as e:
            log(f"{check.__name__} raised exception: {e}", "FAIL")
            failures += 1

    return failures


def run_code_integrity_checks() -> int:
    """Run code integrity checks (no API needed)."""
    log("Transaction Code Integrity Checks", "SECTION")
    print()

    checks = [
        check_transaction_service_integrity,
        check_form_8949_query_integrity,
        test_form_8949_excludes_nontaxable,
        test_csv_roundtrip_format_check,
    ]

    failures = 0
    for check in checks:
        try:
            if not check():
                failures += 1
        except Exception as e:
            log(f"{check.__name__} raised exception: {e}", "FAIL")
            failures += 1

    return failures


def run_api_tests(quick: bool = False) -> int:
    """Run API-dependent tests."""
    if not check_backend_running():
        log("Backend not running at http://127.0.0.1:8000 - skipping API tests", "WARN")
        return 0

    failures = 0

    # Transaction integrity tests
    log("Transaction Integrity Tests", "SECTION")
    print()

    if not quick:
        if not run_comprehensive_transaction_tests():
            failures += 1
        if not run_backdated_fifo_test():
            failures += 1
    else:
        log("Skipping comprehensive tests (--quick mode)", "WARN")

    # Report generation tests
    log("Report Generation Tests", "SECTION")
    print()

    if not quick:
        if not test_form_8949_generation():
            failures += 1
        if not test_complete_tax_report():
            failures += 1

    # CSV tests
    log("CSV Import/Export Tests", "SECTION")
    print()

    if not test_csv_template_endpoint():
        failures += 1
    if not test_csv_export_endpoint():
        failures += 1

    return failures


def print_summary():
    """Print test summary."""
    print()
    log("TEST SUMMARY", "SECTION")
    print()

    total_passed = 0
    total_failed = 0

    for category, results in RESULTS.items():
        passed = sum(1 for _, p, _ in results if p)
        failed = sum(1 for _, p, _ in results if not p)
        total_passed += passed
        total_failed += failed

        status = colored("PASS", Colors.GREEN) if failed == 0 else colored("FAIL", Colors.RED)
        print(f"  {category}: {passed}/{passed + failed} tests passed [{status}]")

    print()
    print(f"  {colored('Total:', Colors.BOLD)} {total_passed} passed, {total_failed} failed")
    print()

    if total_failed == 0:
        print(colored("  All tests passed! Safe to commit.", Colors.GREEN))
    else:
        print(colored("  Some tests failed. Please fix before committing.", Colors.RED))

    return total_failed


def main():
    global VERBOSE

    parser = argparse.ArgumentParser(description="Pre-commit test suite for BitcoinTX")
    parser.add_argument("--quick", action="store_true", help="Skip long-running tests")
    parser.add_argument("--no-api", action="store_true", help="Skip API tests")
    parser.add_argument("--verbose", action="store_true", help="Show detailed output")
    args = parser.parse_args()

    VERBOSE = args.verbose

    print()
    print(colored("=" * 60, Colors.BOLD))
    print(colored("  BITCTX PRE-COMMIT TEST SUITE", Colors.BOLD))
    print(colored("=" * 60, Colors.BOLD))
    print()

    failures = 0

    # Always run static checks
    failures += run_static_checks()
    print()

    # Always run code integrity checks (no API needed)
    failures += run_code_integrity_checks()
    print()

    # Run API tests unless --no-api
    if not args.no_api:
        failures += run_api_tests(quick=args.quick)
    else:
        log("Skipping API tests (--no-api mode)", "WARN")

    # Print summary
    total_failures = print_summary()

    return 0 if total_failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
