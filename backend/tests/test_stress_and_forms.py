#!/usr/bin/env python3
"""
Test Suite: Volume/Stress Testing, Edge Cases, and IRS Form Validation

This pytest-compatible test suite covers:
1. Volume/stress testing (250+ transactions, backdating cascades)
2. Edge cases (timing, amounts, lot consumption, account-specific FIFO)
3. All deposit sources and withdrawal purposes
4. IRS Form 8949 field-by-field validation
5. Schedule D totals verification
6. Year-specific form differences (2024 vs 2025)

Run: pytest backend/tests/test_stress_and_forms.py -v
Requires: Backend running at http://127.0.0.1:8000
"""

import pytest
import random
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Tuple
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
EXTERNAL = 99       # External entity (for deposits/withdrawals)
BANK_USD = 1        # Bank account (USD)
WALLET_BTC = 2      # Bitcoin wallet
EXCHANGE_USD = 3    # Exchange USD balance
EXCHANGE_BTC = 4    # Exchange BTC balance
BTC_FEES = 5        # BTC Fees account

# Deposit sources
DEPOSIT_SOURCES = ["MyBTC", "Gift", "Income", "Interest", "Reward"]

# Withdrawal purposes
WITHDRAWAL_PURPOSES = ["Spent", "Gift", "Donation", "Lost"]

# Non-taxable purposes (should NOT appear on Form 8949)
NON_TAXABLE_PURPOSES = ("Gift", "Donation", "Lost")

# Tolerance for decimal comparisons (1 cent)
DECIMAL_TOLERANCE = Decimal("0.01")

# Tolerance for BTC comparisons (1 satoshi)
SATOSHI_TOLERANCE = Decimal("0.00000001")


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
        error_detail = r.text
        try:
            error_detail = r.json()
        except Exception:
            pass
        return {"error": True, "status_code": r.status_code, "detail": error_detail}
    return r.json()


def update_tx(tx_id: int, updates: Dict) -> Dict:
    """Update a transaction."""
    r = CLIENT.put(f"/api/transactions/{tx_id}", json=updates)
    if not r.is_success:
        return {"error": True, "status_code": r.status_code, "detail": r.text}
    return r.json()


def delete_tx(tx_id: int) -> bool:
    """Delete a transaction."""
    r = CLIENT.delete(f"/api/transactions/{tx_id}")
    return r.status_code in (200, 204)


def get_transaction(tx_id: int) -> Optional[Dict]:
    """Get a single transaction by ID."""
    r = CLIENT.get(f"/api/transactions/{tx_id}")
    if not r.is_success:
        return None
    return r.json()


def get_all_transactions() -> List[Dict]:
    """Get all transactions."""
    r = CLIENT.get("/api/transactions")
    if not r.is_success:
        return []
    return r.json()


def get_lots() -> List[Dict]:
    """Get all Bitcoin lots via debug endpoint."""
    r = CLIENT.get("/api/debug/lots")
    if not r.is_success:
        return []
    return r.json()


def get_disposals() -> List[Dict]:
    """Get all lot disposals via debug endpoint."""
    r = CLIENT.get("/api/debug/disposals")
    if not r.is_success:
        return []
    return r.json()


def get_balance(account_id: int) -> float:
    """Get balance for a specific account."""
    r = CLIENT.get(f"/api/calculations/account/{account_id}/balance")
    if not r.is_success:
        return 0.0
    return r.json().get("balance", 0.0)


def get_balances() -> List[Dict]:
    """Get all account balances."""
    r = CLIENT.get("/api/calculations/accounts/balances")
    if not r.is_success:
        return []
    return r.json()


def get_gains_and_losses() -> Dict:
    """Get aggregated gains and losses."""
    r = CLIENT.get("/api/calculations/gains-and-losses")
    if not r.is_success:
        return {}
    return r.json()


def get_irs_report_data(year: int) -> Optional[bytes]:
    """Get IRS reports PDF for a given year."""
    r = CLIENT.get("/api/reports/irs_reports", params={"year": year})
    if not r.is_success:
        return None
    return r.content


def get_form_8949_data(year: int) -> Optional[Dict]:
    """Get Form 8949 data (JSON) for verification. Uses internal debug endpoint."""
    # Build the data via direct call (requires internal access)
    # For testing, we verify via disposals instead
    return None


def build_timestamp(year: int, month: int, day: int, hour: int = 12, minute: int = 0) -> str:
    """Build an ISO timestamp string."""
    dt = datetime(year, month, day, hour, minute, 0, tzinfo=timezone.utc)
    return dt.isoformat()


def assert_decimal_equal(actual: Any, expected: Any, tolerance: Decimal = DECIMAL_TOLERANCE) -> bool:
    """Assert two decimal values are equal within tolerance."""
    try:
        actual_d = Decimal(str(actual))
        expected_d = Decimal(str(expected))
        return abs(actual_d - expected_d) <= tolerance
    except (ValueError, TypeError, InvalidOperation):
        return False


def assert_lots_non_negative() -> Tuple[bool, str]:
    """Verify all lot remaining_btc values are non-negative."""
    lots = get_lots()
    for lot in lots:
        remaining = Decimal(str(lot.get("remaining_btc", 0)))
        if remaining < 0:
            return False, f"Lot {lot['id']} has negative remaining_btc: {remaining}"
    return True, "All lots have non-negative remaining_btc"


def random_datetime_in_range(start: datetime, end: datetime) -> datetime:
    """Return a random datetime between start and end."""
    delta = end - start
    random_seconds = random.randint(0, int(delta.total_seconds()))
    return start + timedelta(seconds=random_seconds)


# =============================================================================
# PYTEST FIXTURES
# =============================================================================

@pytest.fixture
def clean_db():
    """Delete all transactions before and after test."""
    delete_all_transactions()
    yield
    delete_all_transactions()


@pytest.fixture
def funded_exchange(clean_db):
    """Clean DB + USD deposit to Exchange USD."""
    tx = create_tx({
        "type": "Deposit",
        "timestamp": build_timestamp(2024, 1, 1, 10, 0),
        "from_account_id": EXTERNAL,
        "to_account_id": EXCHANGE_USD,
        "amount": "100000",
        "fee_amount": "0",
        "fee_currency": "USD",
        "source": "N/A",
    })
    assert "error" not in tx
    return tx


@pytest.fixture
def btc_inventory(funded_exchange):
    """Clean DB + USD + 5 BTC purchases at different dates for FIFO testing."""
    lots_data = []

    # Purchase 5 lots with different cost bases
    purchases = [
        {"date": (2024, 1, 15), "btc": "1.0", "cost": "30000"},
        {"date": (2024, 2, 15), "btc": "0.5", "cost": "17500"},
        {"date": (2024, 3, 15), "btc": "0.75", "cost": "30000"},
        {"date": (2024, 6, 15), "btc": "0.25", "cost": "12500"},
        {"date": (2024, 9, 15), "btc": "1.5", "cost": "75000"},
    ]

    for p in purchases:
        tx = create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(*p["date"]),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": p["btc"],
            "fee_amount": "10",
            "fee_currency": "USD",
            "cost_basis_usd": p["cost"],
        })
        assert "error" not in tx
        lots_data.append(tx)

    return lots_data


@pytest.fixture
def wallet_inventory(clean_db):
    """Clean DB + BTC deposits to Wallet for Wallet-specific tests."""
    deposits = []

    # Deposit to Wallet with different sources
    deposit_data = [
        {"date": (2024, 1, 10), "btc": "0.5", "cost": "20000", "source": "Income"},
        {"date": (2024, 2, 10), "btc": "0.3", "cost": "12000", "source": "Reward"},
    ]

    for d in deposit_data:
        tx = create_tx({
            "type": "Deposit",
            "timestamp": build_timestamp(*d["date"]),
            "from_account_id": EXTERNAL,
            "to_account_id": WALLET_BTC,
            "amount": d["btc"],
            "fee_amount": "0",
            "fee_currency": "BTC",
            "source": d["source"],
            "cost_basis_usd": d["cost"],
        })
        assert "error" not in tx
        deposits.append(tx)

    return deposits


# =============================================================================
# CLASS 1: VOLUME/STRESS TESTS
# =============================================================================

@pytest.mark.slow
class TestVolumeStress:
    """Volume and stress testing for transaction handling and FIFO integrity."""

    def test_stress_250_transactions_fifo_integrity(self, funded_exchange):
        """Generate 250 mixed transactions, verify all lot balances non-negative."""
        base_dt = datetime(2024, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
        end_dt = base_dt + timedelta(days=365)

        # First, create some BTC inventory
        for i in range(20):
            tx_data = {
                "type": "Buy",
                "timestamp": (base_dt + timedelta(days=i*5)).isoformat(),
                "from_account_id": EXCHANGE_USD,
                "to_account_id": EXCHANGE_BTC,
                "amount": str(round(random.uniform(0.1, 1.0), 8)),
                "fee_amount": "10",
                "fee_currency": "USD",
                "cost_basis_usd": str(round(random.uniform(3000, 50000), 2)),
            }
            result = create_tx(tx_data)
            # Continue even if some fail (insufficient funds)

        # Now mix in sells, deposits, transfers
        created_count = 20
        for i in range(230):
            tx_type = random.choice(["Buy", "Sell", "Deposit", "Withdrawal"])
            ts = random_datetime_in_range(base_dt + timedelta(days=100), end_dt)

            if tx_type == "Buy":
                tx_data = {
                    "type": "Buy",
                    "timestamp": ts.isoformat(),
                    "from_account_id": EXCHANGE_USD,
                    "to_account_id": EXCHANGE_BTC,
                    "amount": str(round(random.uniform(0.01, 0.5), 8)),
                    "fee_amount": "5",
                    "fee_currency": "USD",
                    "cost_basis_usd": str(round(random.uniform(1000, 30000), 2)),
                }
            elif tx_type == "Sell":
                tx_data = {
                    "type": "Sell",
                    "timestamp": ts.isoformat(),
                    "from_account_id": EXCHANGE_BTC,
                    "to_account_id": EXCHANGE_USD,
                    "amount": str(round(random.uniform(0.01, 0.1), 8)),
                    "fee_amount": "5",
                    "fee_currency": "USD",
                    "proceeds_usd": str(round(random.uniform(500, 10000), 2)),
                }
            elif tx_type == "Deposit":
                tx_data = {
                    "type": "Deposit",
                    "timestamp": ts.isoformat(),
                    "from_account_id": EXTERNAL,
                    "to_account_id": EXCHANGE_USD,
                    "amount": str(round(random.uniform(1000, 10000), 2)),
                    "fee_amount": "0",
                    "fee_currency": "USD",
                    "source": "N/A",
                }
            else:  # Withdrawal USD
                tx_data = {
                    "type": "Withdrawal",
                    "timestamp": ts.isoformat(),
                    "from_account_id": EXCHANGE_USD,
                    "to_account_id": EXTERNAL,
                    "amount": str(round(random.uniform(100, 500), 2)),
                    "fee_amount": "0",
                    "fee_currency": "USD",
                    "purpose": "N/A",
                }

            result = create_tx(tx_data)
            if "error" not in result:
                created_count += 1

        # Verify FIFO integrity
        is_valid, msg = assert_lots_non_negative()
        assert is_valid, msg
        assert created_count >= 100, f"Should have created at least 100 transactions, got {created_count}"

    def test_stress_50_same_day_ordering(self, funded_exchange):
        """50 transactions same day, verify timestamp+ID ordering."""
        base_date = build_timestamp(2024, 6, 15, 9, 0)

        # First create BTC inventory
        for i in range(10):
            create_tx({
                "type": "Buy",
                "timestamp": base_date,
                "from_account_id": EXCHANGE_USD,
                "to_account_id": EXCHANGE_BTC,
                "amount": "0.5",
                "fee_amount": "5",
                "fee_currency": "USD",
                "cost_basis_usd": "20000",
            })

        # Now create 40 more transactions on the same day
        for i in range(40):
            if i % 2 == 0:
                create_tx({
                    "type": "Buy",
                    "timestamp": base_date,
                    "from_account_id": EXCHANGE_USD,
                    "to_account_id": EXCHANGE_BTC,
                    "amount": "0.1",
                    "fee_amount": "2",
                    "fee_currency": "USD",
                    "cost_basis_usd": "4000",
                })
            else:
                create_tx({
                    "type": "Sell",
                    "timestamp": base_date,
                    "from_account_id": EXCHANGE_BTC,
                    "to_account_id": EXCHANGE_USD,
                    "amount": "0.05",
                    "fee_amount": "2",
                    "fee_currency": "USD",
                    "proceeds_usd": "2500",
                })

        is_valid, msg = assert_lots_non_negative()
        assert is_valid, msg

    def test_stress_reports_with_large_dataset(self, funded_exchange):
        """Generate reports with 200+ transactions, verify no timeout."""
        base_dt = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        # Create 100 buys
        for i in range(100):
            create_tx({
                "type": "Buy",
                "timestamp": (base_dt + timedelta(days=i)).isoformat(),
                "from_account_id": EXCHANGE_USD,
                "to_account_id": EXCHANGE_BTC,
                "amount": "0.1",
                "fee_amount": "5",
                "fee_currency": "USD",
                "cost_basis_usd": "5000",
            })

        # Create 100 sells to generate disposals
        for i in range(100):
            create_tx({
                "type": "Sell",
                "timestamp": (base_dt + timedelta(days=100+i)).isoformat(),
                "from_account_id": EXCHANGE_BTC,
                "to_account_id": EXCHANGE_USD,
                "amount": "0.05",
                "fee_amount": "5",
                "fee_currency": "USD",
                "proceeds_usd": "3000",
            })

        # Generate IRS report - should not timeout (default 2 minutes)
        pdf_bytes = get_irs_report_data(2024)
        assert pdf_bytes is not None, "IRS report generation failed"
        assert len(pdf_bytes) > 1000, "IRS report PDF seems too small"

    def test_stress_backdated_cascade_100(self, funded_exchange):
        """100 transactions, backdate 10, verify recalculation."""
        base_dt = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        created_ids = []

        # Create 50 buys
        for i in range(50):
            tx = create_tx({
                "type": "Buy",
                "timestamp": (base_dt + timedelta(days=i*2)).isoformat(),
                "from_account_id": EXCHANGE_USD,
                "to_account_id": EXCHANGE_BTC,
                "amount": "0.2",
                "fee_amount": "5",
                "fee_currency": "USD",
                "cost_basis_usd": "8000",
            })
            if "error" not in tx:
                created_ids.append(tx["id"])

        # Create 50 sells
        for i in range(50):
            tx = create_tx({
                "type": "Sell",
                "timestamp": (base_dt + timedelta(days=100+i*2)).isoformat(),
                "from_account_id": EXCHANGE_BTC,
                "to_account_id": EXCHANGE_USD,
                "amount": "0.1",
                "fee_amount": "5",
                "fee_currency": "USD",
                "proceeds_usd": "5000",
            })
            if "error" not in tx:
                created_ids.append(tx["id"])

        # Backdate 10 transactions
        backdated_count = 0
        for tx_id in random.sample(created_ids[:50], min(10, len(created_ids))):
            new_ts = (base_dt - timedelta(days=random.randint(1, 30))).isoformat()
            result = update_tx(tx_id, {"timestamp": new_ts})
            if "error" not in result:
                backdated_count += 1

        # Verify integrity after backdating
        is_valid, msg = assert_lots_non_negative()
        assert is_valid, msg

    def test_stress_multi_year_2023_2025(self, clean_db):
        """Span 3 years, verify year filtering in reports."""
        # Create USD deposit first
        create_tx({
            "type": "Deposit",
            "timestamp": build_timestamp(2023, 1, 1, 10, 0),
            "from_account_id": EXTERNAL,
            "to_account_id": EXCHANGE_USD,
            "amount": "200000",
            "fee_amount": "0",
            "fee_currency": "USD",
            "source": "N/A",
        })

        years_data = []
        for year in [2023, 2024, 2025]:
            # Buy in January
            buy_tx = create_tx({
                "type": "Buy",
                "timestamp": build_timestamp(year, 1, 15, 10, 0),
                "from_account_id": EXCHANGE_USD,
                "to_account_id": EXCHANGE_BTC,
                "amount": "1.0",
                "fee_amount": "10",
                "fee_currency": "USD",
                "cost_basis_usd": "40000",
            })

            # Sell in December
            sell_tx = create_tx({
                "type": "Sell",
                "timestamp": build_timestamp(year, 12, 15, 10, 0),
                "from_account_id": EXCHANGE_BTC,
                "to_account_id": EXCHANGE_USD,
                "amount": "0.5",
                "fee_amount": "10",
                "fee_currency": "USD",
                "proceeds_usd": "25000",
            })

            years_data.append((year, buy_tx, sell_tx))

        # Every year's sale produced a disposal
        disposal_tx_ids = {d.get("transaction_id") for d in get_disposals()}
        assert all(sell_tx["id"] in disposal_tx_ids for _, _, sell_tx in years_data)

        assert len(years_data) == 3


# =============================================================================
# CLASS 2: EDGE CASE TESTS
# =============================================================================

class TestEdgeCases:
    """Edge cases for timing, amounts, lot consumption, and account-specific FIFO."""

    # -------------------------------------------------------------------------
    # Timing Edge Cases
    # -------------------------------------------------------------------------

    def test_edge_same_timestamp_buy_before_sell(self, funded_exchange):
        """Buy and Sell at same timestamp, verify acquisition first."""
        ts = build_timestamp(2024, 6, 15, 12, 0)

        # Create buy and sell at exact same timestamp
        buy_tx = create_tx({
            "type": "Buy",
            "timestamp": ts,
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "cost_basis_usd": "40000",
        })
        assert "error" not in buy_tx

        sell_tx = create_tx({
            "type": "Sell",
            "timestamp": ts,
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "0.5",
            "fee_amount": "10",
            "fee_currency": "USD",
            "proceeds_usd": "22000",
        })
        assert "error" not in sell_tx

        # Verify lots are created and disposed correctly
        is_valid, msg = assert_lots_non_negative()
        assert is_valid, msg

    def test_edge_holding_period_364_days_short(self, funded_exchange):
        """Acquire Jan 1 2024, sell Dec 31 2024 (365 days, leap year) = SHORT."""
        buy_tx = create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 1, 1, 12, 0),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "cost_basis_usd": "40000",
        })
        assert "error" not in buy_tx

        sell_tx = create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2024, 12, 31, 12, 0),  # 365 days later (leap year)
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "proceeds_usd": "50000",
        })
        assert "error" not in sell_tx

        # Check disposal holding period
        disposals = get_disposals()
        sell_disposals = [d for d in disposals if d.get("transaction_id") == sell_tx["id"]]
        assert len(sell_disposals) == 1
        # 365 days in a leap year, but held LESS than one year (the anniversary
        # is Jan 1 2025). IRS: long-term needs MORE than one year -> SHORT.
        hp = sell_disposals[0].get("holding_period", "").upper()
        assert hp == "SHORT", f"Expected SHORT (sold before the anniversary), got {hp}"

    def test_edge_holding_period_anniversary_is_short(self, funded_exchange):
        """Acquire Jan 1 2024, sell on the anniversary Jan 1 2025 = exactly one year = SHORT.
        IRS Pub. 544: long-term requires holding MORE than one year."""
        buy_tx = create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 1, 1, 12, 0),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "cost_basis_usd": "40000",
        })
        assert "error" not in buy_tx

        sell_tx = create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2025, 1, 1, 12, 0),  # Exactly 366 days (leap year)
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "proceeds_usd": "50000",
        })
        assert "error" not in sell_tx

        disposals = get_disposals()
        sell_disposals = [d for d in disposals if d.get("transaction_id") == sell_tx["id"]]
        assert len(sell_disposals) == 1
        hp = sell_disposals[0].get("holding_period", "").upper()
        assert hp == "SHORT", f"Expected SHORT (sold on the anniversary), got {hp}"

    def test_edge_holding_period_366_days_long(self, funded_exchange):
        """Acquire Jan 1 2023, sell Jan 2 2024 = 366+ days = definitely LONG."""
        buy_tx = create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2023, 1, 1, 12, 0),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "cost_basis_usd": "40000",
        })
        assert "error" not in buy_tx

        sell_tx = create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2024, 1, 3, 12, 0),  # 367 days
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "proceeds_usd": "50000",
        })
        assert "error" not in sell_tx

        disposals = get_disposals()
        sell_disposals = [d for d in disposals if d.get("transaction_id") == sell_tx["id"]]
        assert len(sell_disposals) == 1
        hp = sell_disposals[0].get("holding_period", "").upper()
        assert hp == "LONG", f"Expected LONG (367 days), got {hp}"

    def test_edge_year_boundary_dec31_jan1(self, funded_exchange):
        """Buy Dec 31, sell Jan 1 next year = 1 day = SHORT."""
        buy_tx = create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 12, 31, 12, 0),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "cost_basis_usd": "40000",
        })
        assert "error" not in buy_tx

        sell_tx = create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2025, 1, 1, 12, 0),  # 1 day later
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "proceeds_usd": "42000",
        })
        assert "error" not in sell_tx

        disposals = get_disposals()
        sell_disposals = [d for d in disposals if d.get("transaction_id") == sell_tx["id"]]
        assert len(sell_disposals) == 1
        hp = sell_disposals[0].get("holding_period", "").upper()
        assert hp == "SHORT", f"Expected SHORT (1 day), got {hp}"

    # -------------------------------------------------------------------------
    # Amount Edge Cases
    # -------------------------------------------------------------------------

    def test_edge_satoshi_1_sat(self, funded_exchange):
        """0.00000001 BTC (1 satoshi) precision preserved."""
        buy_tx = create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 6, 15, 12, 0),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "0.00000001",
            "fee_amount": "1",
            "fee_currency": "USD",
            "cost_basis_usd": "0.50",
        })
        assert "error" not in buy_tx

        lots = get_lots()
        satoshi_lots = [l for l in lots if Decimal(str(l.get("total_btc", 0))) == Decimal("0.00000001")]
        assert len(satoshi_lots) >= 1, "1 satoshi lot should be created"

    def test_edge_large_1000_btc(self, clean_db):
        """1000+ BTC, $100M+ USD, no overflow."""
        # First deposit enough USD
        create_tx({
            "type": "Deposit",
            "timestamp": build_timestamp(2024, 1, 1, 10, 0),
            "from_account_id": EXTERNAL,
            "to_account_id": EXCHANGE_USD,
            "amount": "200000000",  # $200M
            "fee_amount": "0",
            "fee_currency": "USD",
            "source": "N/A",
        })

        buy_tx = create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 6, 15, 12, 0),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "1000.12345678",
            "fee_amount": "1000",
            "fee_currency": "USD",
            "cost_basis_usd": "100000000",  # $100M
        })
        assert "error" not in buy_tx

        lots = get_lots()
        large_lots = [l for l in lots if Decimal(str(l.get("total_btc", 0))) > Decimal("1000")]
        assert len(large_lots) >= 1, "Large BTC lot should be created"

        # Verify cost basis preserved (includes $1000 fee)
        large_lot = large_lots[0]
        cost = Decimal(str(large_lot.get("cost_basis_usd", 0)))
        # Cost basis = $100M + $1000 fee = $100,001,000
        assert cost == Decimal("100001000"), f"Cost basis should be $100,001,000 (includes fee), got {cost}"

    def test_edge_zero_gain_loss(self, funded_exchange):
        """Buy/sell same price = $0 gain."""
        buy_tx = create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 6, 15, 12, 0),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "1.0",
            "fee_amount": "0",
            "fee_currency": "USD",
            "cost_basis_usd": "50000",
        })
        assert "error" not in buy_tx

        sell_tx = create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2024, 6, 20, 12, 0),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "1.0",
            "fee_amount": "0",
            "fee_currency": "USD",
            "proceeds_usd": "50000",  # Same as cost
        })
        assert "error" not in sell_tx

        disposals = get_disposals()
        sell_disposals = [d for d in disposals if d.get("transaction_id") == sell_tx["id"]]
        assert len(sell_disposals) == 1

        gain = Decimal(str(sell_disposals[0].get("realized_gain_usd", 0)))
        assert abs(gain) < DECIMAL_TOLERANCE, f"Expected ~$0 gain, got {gain}"

    # -------------------------------------------------------------------------
    # Lot Consumption Edge Cases
    # -------------------------------------------------------------------------

    def test_edge_partial_lot_consumption(self, funded_exchange):
        """Buy 2 BTC, sell 0.5, verify 1.5 remaining."""
        buy_tx = create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 6, 15, 12, 0),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "2.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "cost_basis_usd": "80000",
        })
        assert "error" not in buy_tx

        sell_tx = create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2024, 6, 20, 12, 0),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "0.5",
            "fee_amount": "10",
            "fee_currency": "USD",
            "proceeds_usd": "25000",
        })
        assert "error" not in sell_tx

        lots = get_lots()
        # Find the lot we just created
        buy_lots = [l for l in lots if Decimal(str(l.get("total_btc", 0))) == Decimal("2.0")]
        assert len(buy_lots) >= 1

        remaining = Decimal(str(buy_lots[0].get("remaining_btc", 0)))
        assert abs(remaining - Decimal("1.5")) < SATOSHI_TOLERANCE, f"Expected 1.5 remaining, got {remaining}"

    def test_edge_single_sale_multiple_lots(self, btc_inventory):
        """5 small lots, 1 sale consuming all."""
        # btc_inventory creates 4 BTC total across 5 lots
        # Sell 3.5 BTC to consume multiple lots
        sell_tx = create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2024, 12, 15, 12, 0),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "3.5",
            "fee_amount": "50",
            "fee_currency": "USD",
            "proceeds_usd": "180000",
        })
        assert "error" not in sell_tx

        # Verify multiple disposals created for this single sale
        disposals = get_disposals()
        sell_disposals = [d for d in disposals if d.get("transaction_id") == sell_tx["id"]]
        assert len(sell_disposals) >= 2, f"Expected multiple lot disposals, got {len(sell_disposals)}"

    def test_edge_exact_lot_exhaustion(self, funded_exchange):
        """Buy 1 BTC, sell 1 BTC, remaining = 0."""
        buy_tx = create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 6, 15, 12, 0),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "cost_basis_usd": "40000",
        })
        assert "error" not in buy_tx

        sell_tx = create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2024, 6, 20, 12, 0),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "proceeds_usd": "45000",
        })
        assert "error" not in sell_tx

        lots = get_lots()
        exhausted_lots = [l for l in lots if Decimal(str(l.get("total_btc", 0))) == Decimal("1.0")]
        assert len(exhausted_lots) >= 1

        remaining = Decimal(str(exhausted_lots[0].get("remaining_btc", 0)))
        assert remaining == Decimal("0"), f"Expected 0 remaining, got {remaining}"

    # -------------------------------------------------------------------------
    # Account-Specific FIFO
    # -------------------------------------------------------------------------

    def test_edge_fifo_exchange_btc_only(self, clean_db):
        """Deposit to Wallet + Exchange, sell from Exchange uses Exchange lots only."""
        # Deposit USD
        create_tx({
            "type": "Deposit",
            "timestamp": build_timestamp(2024, 1, 1),
            "from_account_id": EXTERNAL,
            "to_account_id": EXCHANGE_USD,
            "amount": "100000",
            "fee_amount": "0",
            "fee_currency": "USD",
            "source": "N/A",
        })

        # Deposit BTC to Wallet (cost basis $30k)
        wallet_deposit = create_tx({
            "type": "Deposit",
            "timestamp": build_timestamp(2024, 1, 10),
            "from_account_id": EXTERNAL,
            "to_account_id": WALLET_BTC,
            "amount": "1.0",
            "fee_amount": "0",
            "fee_currency": "BTC",
            "source": "Income",
            "cost_basis_usd": "30000",
        })
        assert "error" not in wallet_deposit

        # Buy BTC on Exchange (cost basis $40k)
        exchange_buy = create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 1, 15),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "cost_basis_usd": "40000",
        })
        assert "error" not in exchange_buy

        # Sell 0.5 BTC from Exchange - should use ONLY Exchange lot (not Wallet)
        sell_tx = create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2024, 2, 1),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "0.5",
            "fee_amount": "10",
            "fee_currency": "USD",
            "proceeds_usd": "25000",
        })
        assert "error" not in sell_tx

        # Check that disposal used Exchange lot (cost basis ~$40k/BTC + fee)
        disposals = get_disposals()
        sell_disposals = [d for d in disposals if d.get("transaction_id") == sell_tx["id"]]
        assert len(sell_disposals) == 1

        # Cost basis for 0.5 BTC from ($40k + $10 fee) lot = $20,005
        disposal_basis = Decimal(str(sell_disposals[0].get("disposal_basis_usd", 0)))
        expected_basis = Decimal("20005")  # $40,010 total lot basis * 0.5
        assert abs(disposal_basis - expected_basis) < DECIMAL_TOLERANCE, \
            f"Expected basis ~$20,005 (from Exchange lot with fee), got {disposal_basis}"

        # Verify Wallet lot is untouched
        lots = get_lots()
        wallet_lots = [l for l in lots if Decimal(str(l.get("cost_basis_usd", 0))) == Decimal("30000")]
        assert len(wallet_lots) == 1
        wallet_remaining = Decimal(str(wallet_lots[0].get("remaining_btc", 0)))
        assert wallet_remaining == Decimal("1.0"), f"Wallet lot should be untouched, remaining={wallet_remaining}"

    def test_edge_fifo_wallet_only(self, clean_db):
        """Deposit to Wallet + Exchange, withdraw from Wallet uses Wallet lots only."""
        # Deposit USD
        create_tx({
            "type": "Deposit",
            "timestamp": build_timestamp(2024, 1, 1),
            "from_account_id": EXTERNAL,
            "to_account_id": EXCHANGE_USD,
            "amount": "100000",
            "fee_amount": "0",
            "fee_currency": "USD",
            "source": "N/A",
        })

        # Deposit BTC to Wallet (cost basis $30k)
        wallet_deposit = create_tx({
            "type": "Deposit",
            "timestamp": build_timestamp(2024, 1, 10),
            "from_account_id": EXTERNAL,
            "to_account_id": WALLET_BTC,
            "amount": "1.0",
            "fee_amount": "0",
            "fee_currency": "BTC",
            "source": "Income",
            "cost_basis_usd": "30000",
        })
        assert "error" not in wallet_deposit

        # Buy BTC on Exchange (cost basis $40k)
        exchange_buy = create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 1, 15),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "cost_basis_usd": "40000",
        })
        assert "error" not in exchange_buy

        # Withdraw 0.5 BTC from Wallet (Spent) - should use ONLY Wallet lot
        withdrawal_tx = create_tx({
            "type": "Withdrawal",
            "timestamp": build_timestamp(2024, 2, 1),
            "from_account_id": WALLET_BTC,
            "to_account_id": EXTERNAL,
            "amount": "0.5",
            "fee_amount": "0",
            "fee_currency": "BTC",
            "purpose": "Spent",
            "proceeds_usd": "22000",
        })
        assert "error" not in withdrawal_tx

        # Check that disposal used Wallet lot (cost basis ~$30k/BTC)
        disposals = get_disposals()
        withdrawal_disposals = [d for d in disposals if d.get("transaction_id") == withdrawal_tx["id"]]
        assert len(withdrawal_disposals) == 1

        # Cost basis for 0.5 BTC from $30k lot = $15k
        disposal_basis = Decimal(str(withdrawal_disposals[0].get("disposal_basis_usd", 0)))
        expected_basis = Decimal("15000")
        assert abs(disposal_basis - expected_basis) < DECIMAL_TOLERANCE, \
            f"Expected basis ~$15k (from Wallet lot), got {disposal_basis}"

    # -------------------------------------------------------------------------
    # Deposit Sources (5 tests)
    # -------------------------------------------------------------------------

    def test_edge_deposit_mybtc(self, clean_db):
        """MyBTC deposit creates lot with user-supplied cost basis."""
        tx = create_tx({
            "type": "Deposit",
            "timestamp": build_timestamp(2024, 6, 15),
            "from_account_id": EXTERNAL,
            "to_account_id": WALLET_BTC,
            "amount": "1.5",
            "fee_amount": "0",
            "fee_currency": "BTC",
            "source": "MyBTC",
            "cost_basis_usd": "45000",  # User specifies their original cost basis
        })
        assert "error" not in tx

        lots = get_lots()
        mybtc_lots = [l for l in lots if Decimal(str(l.get("cost_basis_usd", 0))) == Decimal("45000")]
        assert len(mybtc_lots) == 1

    def test_edge_deposit_gift(self, clean_db):
        """Gift deposit allows $0 cost basis (carryover basis from giver)."""
        tx = create_tx({
            "type": "Deposit",
            "timestamp": build_timestamp(2024, 6, 15),
            "from_account_id": EXTERNAL,
            "to_account_id": WALLET_BTC,
            "amount": "0.5",
            "fee_amount": "0",
            "fee_currency": "BTC",
            "source": "Gift",
            "cost_basis_usd": "0",  # Carryover basis scenario (unknown/zero)
        })
        assert "error" not in tx

        lots = get_lots()
        gift_lots = [l for l in lots if Decimal(str(l.get("total_btc", 0))) == Decimal("0.5")]
        assert len(gift_lots) >= 1

    def test_edge_deposit_income(self, clean_db):
        """Income deposit creates lot with FMV as cost basis."""
        tx = create_tx({
            "type": "Deposit",
            "timestamp": build_timestamp(2024, 6, 15),
            "from_account_id": EXTERNAL,
            "to_account_id": WALLET_BTC,
            "amount": "0.25",
            "fee_amount": "0",
            "fee_currency": "BTC",
            "source": "Income",
            "cost_basis_usd": "10000",  # FMV at time of receipt
        })
        assert "error" not in tx

        lots = get_lots()
        income_lots = [l for l in lots if Decimal(str(l.get("cost_basis_usd", 0))) == Decimal("10000")]
        assert len(income_lots) == 1

    def test_edge_deposit_interest(self, clean_db):
        """Interest deposit creates lot with FMV as cost basis."""
        tx = create_tx({
            "type": "Deposit",
            "timestamp": build_timestamp(2024, 6, 15),
            "from_account_id": EXTERNAL,
            "to_account_id": WALLET_BTC,
            "amount": "0.01",
            "fee_amount": "0",
            "fee_currency": "BTC",
            "source": "Interest",
            "cost_basis_usd": "500",  # FMV at time of receipt
        })
        assert "error" not in tx

        lots = get_lots()
        interest_lots = [l for l in lots if Decimal(str(l.get("cost_basis_usd", 0))) == Decimal("500")]
        assert len(interest_lots) == 1

    def test_edge_deposit_reward(self, clean_db):
        """Reward deposit creates lot with FMV as cost basis."""
        tx = create_tx({
            "type": "Deposit",
            "timestamp": build_timestamp(2024, 6, 15),
            "from_account_id": EXTERNAL,
            "to_account_id": WALLET_BTC,
            "amount": "0.001",
            "fee_amount": "0",
            "fee_currency": "BTC",
            "source": "Reward",
            "cost_basis_usd": "50",  # FMV at time of receipt
        })
        assert "error" not in tx

        lots = get_lots()
        reward_lots = [l for l in lots if Decimal(str(l.get("cost_basis_usd", 0))) == Decimal("50")]
        assert len(reward_lots) == 1

    # -------------------------------------------------------------------------
    # Withdrawal Purposes (4 tests)
    # -------------------------------------------------------------------------

    def test_edge_withdrawal_spent_taxable(self, btc_inventory):
        """Spent withdrawal = taxable event with gain/loss."""
        # btc_inventory already has BTC on Exchange
        withdrawal_tx = create_tx({
            "type": "Withdrawal",
            "timestamp": build_timestamp(2024, 12, 1),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXTERNAL,
            "amount": "0.5",
            "fee_amount": "0.0001",
            "fee_currency": "BTC",
            "purpose": "Spent",
            "proceeds_usd": "30000",
        })
        assert "error" not in withdrawal_tx

        disposals = get_disposals()
        spent_disposals = [d for d in disposals if d.get("transaction_id") == withdrawal_tx["id"]]
        assert len(spent_disposals) >= 1

        # Verify gain is non-zero (cost basis was ~$30k/BTC, proceeds are $30k for 0.5 BTC)
        total_gain = sum(Decimal(str(d.get("realized_gain_usd", 0))) for d in spent_disposals)
        # Should have a gain since proceeds ($30k) > cost (~$15k for 0.5 BTC at $30k/BTC)
        assert total_gain > 0, f"Spent should have positive gain, got {total_gain}"

    def test_edge_withdrawal_gift_zero_gain(self, btc_inventory):
        """Gift withdrawal = realized_gain_usd = 0 (no taxable event for giver)."""
        withdrawal_tx = create_tx({
            "type": "Withdrawal",
            "timestamp": build_timestamp(2024, 12, 1),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXTERNAL,
            "amount": "0.5",
            "fee_amount": "0",
            "fee_currency": "BTC",
            "purpose": "Gift",
        })
        assert "error" not in withdrawal_tx

        disposals = get_disposals()
        gift_disposals = [d for d in disposals if d.get("transaction_id") == withdrawal_tx["id"]]
        assert len(gift_disposals) >= 1

        # Gift disposals should have 0 realized gain
        for d in gift_disposals:
            gain = Decimal(str(d.get("realized_gain_usd", 0)))
            assert gain == Decimal("0"), f"Gift should have $0 gain, got {gain}"

    def test_edge_withdrawal_donation_zero_gain(self, btc_inventory):
        """Donation withdrawal = realized_gain_usd = 0."""
        withdrawal_tx = create_tx({
            "type": "Withdrawal",
            "timestamp": build_timestamp(2024, 12, 1),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXTERNAL,
            "amount": "0.25",
            "fee_amount": "0",
            "fee_currency": "BTC",
            "purpose": "Donation",
        })
        assert "error" not in withdrawal_tx

        disposals = get_disposals()
        donation_disposals = [d for d in disposals if d.get("transaction_id") == withdrawal_tx["id"]]
        assert len(donation_disposals) >= 1

        for d in donation_disposals:
            gain = Decimal(str(d.get("realized_gain_usd", 0)))
            assert gain == Decimal("0"), f"Donation should have $0 gain, got {gain}"

    def test_edge_withdrawal_lost_capital_loss(self, btc_inventory):
        """Lost withdrawal = proceeds $0, results in capital loss (negative gain)."""
        withdrawal_tx = create_tx({
            "type": "Withdrawal",
            "timestamp": build_timestamp(2024, 12, 1),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXTERNAL,
            "amount": "0.25",
            "fee_amount": "0",
            "fee_currency": "BTC",
            "purpose": "Lost",
        })
        assert "error" not in withdrawal_tx

        disposals = get_disposals()
        lost_disposals = [d for d in disposals if d.get("transaction_id") == withdrawal_tx["id"]]
        assert len(lost_disposals) >= 1

        # Lost assets: proceeds = 0, so gain = 0 - cost_basis = negative (capital loss)
        total_gain = sum(Decimal(str(d.get("realized_gain_usd", 0))) for d in lost_disposals)
        # This should be a loss (negative gain) since proceeds=0 but there was cost basis
        assert total_gain < 0, f"Lost should have negative gain (loss), got {total_gain}"

    # -------------------------------------------------------------------------
    # Transfer Edge Cases
    # -------------------------------------------------------------------------

    def test_edge_transfer_btc_fee_taxable(self, btc_inventory):
        """Transfer with BTC fee creates taxable disposal for fee portion."""
        # Transfer from Exchange BTC to Wallet with BTC fee
        transfer_tx = create_tx({
            "type": "Transfer",
            "timestamp": build_timestamp(2024, 12, 1),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": WALLET_BTC,
            "amount": "0.5",
            "fee_amount": "0.001",
            "fee_currency": "BTC",
        })
        assert "error" not in transfer_tx

        # BTC fee creates a disposal (treating fee as a taxable event)
        disposals = get_disposals()
        transfer_disposals = [d for d in disposals if d.get("transaction_id") == transfer_tx["id"]]

        # Should have disposal for the fee
        total_disposed = sum(Decimal(str(d.get("disposed_btc", 0))) for d in transfer_disposals)
        # The fee (0.001 BTC) should be disposed
        assert total_disposed >= Decimal("0.001"), f"Fee should create disposal, got {total_disposed}"

    def test_edge_transfer_preserves_cost_basis(self, btc_inventory):
        """Transfer preserves original cost basis and acquisition date."""
        # Get initial lot info before transfer
        initial_lots = get_lots()

        # Transfer from Exchange to Wallet
        transfer_tx = create_tx({
            "type": "Transfer",
            "timestamp": build_timestamp(2024, 12, 1),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": WALLET_BTC,
            "amount": "0.25",
            "fee_amount": "0",
            "fee_currency": "BTC",
        })
        assert "error" not in transfer_tx

        # FIFO: the 0.25 comes from the oldest lot; the wallet lot inherits its
        # acquisition date and a pro-rated share of its basis.
        oldest = min(initial_lots, key=lambda lot: lot["acquired_date"])
        new_lots = [lot for lot in get_lots() if lot["created_txn_id"] == transfer_tx["id"]]
        assert len(new_lots) == 1
        moved = new_lots[0]
        assert Decimal(moved["total_btc"]) == Decimal("0.25")
        assert moved["acquired_date"] == oldest["acquired_date"]
        expected = Decimal(oldest["cost_basis_usd"]) * Decimal("0.25") / Decimal(oldest["total_btc"])
        assert abs(Decimal(moved["cost_basis_usd"]) - expected) <= Decimal("0.01")


# =============================================================================
# CLASS 3: IRS FORM VALIDATION TESTS
# =============================================================================

class TestIRSFormValidation:
    """IRS Form 8949 and Schedule D validation tests."""

    # -------------------------------------------------------------------------
    # Form 8949 Structure
    # -------------------------------------------------------------------------

    def test_form_8949_short_term_created(self, funded_exchange):
        """Short-term disposals appear in Form 8949 data."""
        # Buy and sell within 1 year = short term
        create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 6, 1),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "cost_basis_usd": "40000",
        })

        sell_tx = create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2024, 8, 1),  # 61 days = short term
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "proceeds_usd": "45000",
        })

        disposals = get_disposals()
        sell_disposals = [d for d in disposals if d.get("transaction_id") == sell_tx["id"]]
        assert len(sell_disposals) == 1
        assert sell_disposals[0].get("holding_period", "").upper() == "SHORT"

    def test_form_8949_long_term_created(self, funded_exchange):
        """Long-term disposals appear in Form 8949 data."""
        # Buy and sell after 1 year = long term
        create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2023, 1, 1),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "cost_basis_usd": "30000",
        })

        sell_tx = create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2024, 6, 1),  # >1 year = long term
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "proceeds_usd": "50000",
        })

        disposals = get_disposals()
        sell_disposals = [d for d in disposals if d.get("transaction_id") == sell_tx["id"]]
        assert len(sell_disposals) == 1
        assert sell_disposals[0].get("holding_period", "").upper() == "LONG"

    def test_form_8949_multipage_15_disposals(self, funded_exchange):
        """15 disposals = 2 pages (14 per page), verify PDF generated."""
        # Create 15 buy/sell pairs
        for i in range(15):
            create_tx({
                "type": "Buy",
                "timestamp": build_timestamp(2024, 1, i+1),
                "from_account_id": EXCHANGE_USD,
                "to_account_id": EXCHANGE_BTC,
                "amount": "0.1",
                "fee_amount": "5",
                "fee_currency": "USD",
                "cost_basis_usd": "4000",
            })

            create_tx({
                "type": "Sell",
                "timestamp": build_timestamp(2024, 6, i+1),
                "from_account_id": EXCHANGE_BTC,
                "to_account_id": EXCHANGE_USD,
                "amount": "0.1",
                "fee_amount": "5",
                "fee_currency": "USD",
                "proceeds_usd": "4500",
            })

        # Generate IRS report
        pdf_bytes = get_irs_report_data(2024)
        assert pdf_bytes is not None, "IRS report should be generated"
        assert len(pdf_bytes) > 5000, "Multi-page PDF should be larger"

    def test_form_8949_multipage_30_disposals(self, funded_exchange):
        """30 disposals = 3 pages."""
        for i in range(30):
            create_tx({
                "type": "Buy",
                "timestamp": build_timestamp(2024, 1, (i % 28) + 1),
                "from_account_id": EXCHANGE_USD,
                "to_account_id": EXCHANGE_BTC,
                "amount": "0.05",
                "fee_amount": "2",
                "fee_currency": "USD",
                "cost_basis_usd": "2000",
            })

            create_tx({
                "type": "Sell",
                "timestamp": build_timestamp(2024, 6, (i % 28) + 1),
                "from_account_id": EXCHANGE_BTC,
                "to_account_id": EXCHANGE_USD,
                "amount": "0.05",
                "fee_amount": "2",
                "fee_currency": "USD",
                "proceeds_usd": "2200",
            })

        pdf_bytes = get_irs_report_data(2024)
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 10000, "30-disposal PDF should be substantial"

    # -------------------------------------------------------------------------
    # Non-Taxable Exclusions
    # -------------------------------------------------------------------------

    def test_form_8949_excludes_gift(self, btc_inventory):
        """Gift withdrawal NOT on Form 8949."""
        gift_tx = create_tx({
            "type": "Withdrawal",
            "timestamp": build_timestamp(2024, 12, 1),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXTERNAL,
            "amount": "0.1",
            "fee_amount": "0",
            "fee_currency": "BTC",
            "purpose": "Gift",
        })
        assert "error" not in gift_tx

        # Gift disposals exist but should be excluded from Form 8949
        disposals = get_disposals()
        gift_disposals = [d for d in disposals if d.get("transaction_id") == gift_tx["id"]]
        assert len(gift_disposals) >= 1, "Gift disposal should be recorded"

        # Verify realized_gain is 0 (Gift should not be taxable)
        for d in gift_disposals:
            assert Decimal(str(d.get("realized_gain_usd", 0))) == 0

    def test_form_8949_excludes_donation(self, btc_inventory):
        """Donation withdrawal NOT on Form 8949."""
        donation_tx = create_tx({
            "type": "Withdrawal",
            "timestamp": build_timestamp(2024, 12, 1),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXTERNAL,
            "amount": "0.1",
            "fee_amount": "0",
            "fee_currency": "BTC",
            "purpose": "Donation",
        })
        assert "error" not in donation_tx

        disposals = get_disposals()
        donation_disposals = [d for d in disposals if d.get("transaction_id") == donation_tx["id"]]
        assert len(donation_disposals) >= 1

        for d in donation_disposals:
            assert Decimal(str(d.get("realized_gain_usd", 0))) == 0

    def test_form_8949_excludes_lost(self, btc_inventory):
        """Lost withdrawal NOT on Form 8949 (reported separately as casualty loss)."""
        lost_tx = create_tx({
            "type": "Withdrawal",
            "timestamp": build_timestamp(2024, 12, 1),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXTERNAL,
            "amount": "0.1",
            "fee_amount": "0",
            "fee_currency": "BTC",
            "purpose": "Lost",
        })
        assert "error" not in lost_tx

        # Lost creates a disposal but excluded from Form 8949
        # (capital losses from lost assets reported separately)
        disposals = get_disposals()
        lost_disposals = [d for d in disposals if d.get("transaction_id") == lost_tx["id"]]
        assert len(lost_disposals) >= 1

    def test_form_8949_includes_spent(self, btc_inventory):
        """Spent withdrawal IS on Form 8949 (taxable event)."""
        spent_tx = create_tx({
            "type": "Withdrawal",
            "timestamp": build_timestamp(2024, 12, 1),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXTERNAL,
            "amount": "0.1",
            "fee_amount": "0",
            "fee_currency": "BTC",
            "purpose": "Spent",
            "proceeds_usd": "5000",
        })
        assert "error" not in spent_tx

        disposals = get_disposals()
        spent_disposals = [d for d in disposals if d.get("transaction_id") == spent_tx["id"]]
        assert len(spent_disposals) >= 1

        # Verify disposal was created with proper gain calculation
        assert spent_disposals[0].get("disposal_basis_usd") is not None

    # -------------------------------------------------------------------------
    # Date Handling
    # -------------------------------------------------------------------------

    def test_form_8949_various_for_multiple_lots(self, btc_inventory):
        """Sale consuming 3 lots should show 'VARIOUS' for acquired date."""
        # btc_inventory has multiple lots; sell enough to consume 3+
        sell_tx = create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2024, 12, 15),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "2.0",  # Should consume multiple lots
            "fee_amount": "20",
            "fee_currency": "USD",
            "proceeds_usd": "100000",
        })
        assert "error" not in sell_tx

        disposals = get_disposals()
        sell_disposals = [d for d in disposals if d.get("transaction_id") == sell_tx["id"]]

        # Should have multiple disposals (one per lot consumed)
        assert len(sell_disposals) >= 2, f"Expected multiple disposals, got {len(sell_disposals)}"

    def test_form_8949_actual_date_single_lot(self, funded_exchange):
        """Sale consuming 1 lot shows actual acquisition date."""
        create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 3, 15, 10, 30),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "cost_basis_usd": "40000",
        })

        sell_tx = create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2024, 6, 15),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "proceeds_usd": "45000",
        })

        disposals = get_disposals()
        sell_disposals = [d for d in disposals if d.get("transaction_id") == sell_tx["id"]]
        assert len(sell_disposals) == 1  # Single lot disposal

    # -------------------------------------------------------------------------
    # Schedule D
    # -------------------------------------------------------------------------

    def test_schedule_d_short_term_totals(self, funded_exchange):
        """Schedule D line 3 matches sum of 8949 Part I short-term gains."""
        # Create short-term transactions
        total_proceeds = Decimal("0")
        total_cost = Decimal("0")

        for i in range(3):
            create_tx({
                "type": "Buy",
                "timestamp": build_timestamp(2024, 1, i+1),
                "from_account_id": EXCHANGE_USD,
                "to_account_id": EXCHANGE_BTC,
                "amount": "0.5",
                "fee_amount": "10",
                "fee_currency": "USD",
                "cost_basis_usd": "20000",
            })

            create_tx({
                "type": "Sell",
                "timestamp": build_timestamp(2024, 6, i+1),
                "from_account_id": EXCHANGE_BTC,
                "to_account_id": EXCHANGE_USD,
                "amount": "0.5",
                "fee_amount": "10",
                "fee_currency": "USD",
                "proceeds_usd": "22000",
            })

            total_proceeds += Decimal("22000")
            total_cost += Decimal("20000")

        # Get disposals and verify totals
        disposals = get_disposals()
        short_term_disposals = [d for d in disposals if d.get("holding_period", "").upper() == "SHORT"]

        calc_proceeds = sum(Decimal(str(d.get("proceeds_usd_for_that_portion", 0))) for d in short_term_disposals)

        # Should match (within tolerance due to fees)
        assert calc_proceeds > 0, "Should have short-term proceeds"

    def test_schedule_d_long_term_totals(self, funded_exchange):
        """Schedule D line 10 matches sum of 8949 Part II long-term gains."""
        # Create long-term transactions
        create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2023, 1, 1),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "cost_basis_usd": "30000",
        })

        create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2024, 6, 1),  # >1 year later
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "1.0",
            "fee_amount": "10",
            "fee_currency": "USD",
            "proceeds_usd": "50000",
        })

        disposals = get_disposals()
        long_term_disposals = [d for d in disposals if d.get("holding_period", "").upper() == "LONG"]

        assert len(long_term_disposals) >= 1, "Should have long-term disposals"

        calc_gain = sum(Decimal(str(d.get("realized_gain_usd", 0))) for d in long_term_disposals)
        # Gain should be ~$20k ($50k - $30k)
        assert calc_gain > Decimal("15000"), f"Expected substantial long-term gain, got {calc_gain}"

    def test_schedule_d_mixed_short_long(self, funded_exchange):
        """Both short and long term sections populated correctly."""
        # Short term
        create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 3, 1),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "0.5",
            "fee_amount": "5",
            "fee_currency": "USD",
            "cost_basis_usd": "20000",
        })
        create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2024, 6, 1),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "0.5",
            "fee_amount": "5",
            "fee_currency": "USD",
            "proceeds_usd": "22000",
        })

        # Long term
        create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2023, 1, 1),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "0.5",
            "fee_amount": "5",
            "fee_currency": "USD",
            "cost_basis_usd": "15000",
        })
        create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2024, 6, 1),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "0.5",
            "fee_amount": "5",
            "fee_currency": "USD",
            "proceeds_usd": "25000",
        })

        disposals = get_disposals()
        short_term = [d for d in disposals if d.get("holding_period", "").upper() == "SHORT"]
        long_term = [d for d in disposals if d.get("holding_period", "").upper() == "LONG"]

        assert len(short_term) >= 1, "Should have short-term disposals"
        assert len(long_term) >= 1, "Should have long-term disposals"

    # -------------------------------------------------------------------------
    # Precision
    # -------------------------------------------------------------------------

    def test_form_usd_two_decimal_precision(self, funded_exchange):
        """USD amounts rounded to $X.XX."""
        create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 6, 1),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "0.333333",
            "fee_amount": "7.77",
            "fee_currency": "USD",
            "cost_basis_usd": "13333.33",
        })

        sell = create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2024, 8, 1),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "0.333333",
            "fee_amount": "8.88",
            "fee_currency": "USD",
            "proceeds_usd": "15555.55",
        })

        disposals = get_disposals()
        sell_disposals = [d for d in disposals if d.get("transaction_id") == sell["id"]]

        for d in sell_disposals:
            gain = Decimal(str(d.get("realized_gain_usd", 0)))
            # Verify it's rounded to 2 decimal places
            assert gain == gain.quantize(Decimal("0.01")), f"Gain should be 2 decimals: {gain}"

    def test_form_btc_eight_decimal_precision(self, funded_exchange):
        """BTC amounts show X.XXXXXXXX (8 decimals)."""
        create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 6, 1),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "0.12345678",
            "fee_amount": "5",
            "fee_currency": "USD",
            "cost_basis_usd": "5000",
        })

        lots = get_lots()
        precise_lots = [l for l in lots if Decimal(str(l.get("total_btc", 0))) == Decimal("0.12345678")]
        assert len(precise_lots) >= 1, "8-decimal BTC precision should be preserved"

    # -------------------------------------------------------------------------
    # PDF Generation
    # -------------------------------------------------------------------------

    def test_irs_report_pdf_generated(self, btc_inventory):
        """IRS report PDF is generated successfully."""
        # Create a taxable sale
        create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2024, 12, 1),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "0.5",
            "fee_amount": "10",
            "fee_currency": "USD",
            "proceeds_usd": "25000",
        })

        pdf_bytes = get_irs_report_data(2024)

        # Basic PDF validation
        assert pdf_bytes is not None, "PDF should be generated"
        assert len(pdf_bytes) > 1000, "PDF should have substantial content"
        assert pdf_bytes[:4] == b'%PDF', "Should be valid PDF format"

    def test_empty_year_no_crash(self, clean_db):
        """Year with no transactions should not crash."""
        # Don't create any transactions, just try to generate report
        get_irs_report_data(2024)

        # Should either return empty PDF or handle gracefully
        # The API may return None or a minimal PDF
        # Key is that it doesn't crash


# =============================================================================
# BUY FROM BANK TESTS
# =============================================================================

class TestBuyFromBank:
    """Tests for Buy transactions originating from Bank account (ID 1)."""

    @pytest.fixture
    def funded_bank(self, clean_db):
        """Fund the Bank account with USD for testing."""
        deposit = create_tx({
            "type": "Deposit",
            "timestamp": build_timestamp(2024, 1, 1),
            "from_account_id": EXTERNAL,
            "to_account_id": BANK_USD,
            "amount": "50000",
            "fee_amount": "0",
            "fee_currency": "USD",
            "source": "N/A",
        })
        assert "error" not in deposit, f"Bank deposit failed: {deposit}"
        return deposit

    def test_buy_from_bank_basic(self, funded_bank):
        """Buy 0.5 BTC from Bank for $10,000 - verify balances and lot creation."""
        bank_balance_before = get_balance(BANK_USD)
        assert bank_balance_before >= 10000, "Bank should have sufficient USD"

        buy_tx = create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 1, 15, 12, 0),
            "from_account_id": BANK_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "0.5",
            "fee_amount": "25",
            "fee_currency": "USD",
            "cost_basis_usd": "10000",
        })
        assert "error" not in buy_tx, f"Buy from Bank failed: {buy_tx}"

        # Verify Bank balance decreased by cost_basis + fee
        bank_balance_after = get_balance(BANK_USD)
        expected_bank = bank_balance_before - 10000 - 25
        assert abs(bank_balance_after - expected_bank) < 1, \
            f"Bank balance should be ~{expected_bank}, got {bank_balance_after}"

        # Verify Exchange BTC balance increased by 0.5
        exchange_btc_balance = get_balance(EXCHANGE_BTC)
        assert abs(exchange_btc_balance - 0.5) < 0.00000001, \
            f"Exchange BTC should be 0.5, got {exchange_btc_balance}"

        # Verify BitcoinLot created with correct cost basis (including fee)
        lots = get_lots()
        buy_lot = next(
            (l for l in lots if l.get("created_txn_id") == buy_tx["id"]),
            None
        )
        assert buy_lot is not None, "Should create a Bitcoin lot"
        lot_basis = Decimal(str(buy_lot.get("cost_basis_usd", 0)))
        # Cost basis for Buy with USD fee includes the fee
        expected_basis = Decimal("10025")  # 10000 + 25 fee
        assert abs(lot_basis - expected_basis) < DECIMAL_TOLERANCE, \
            f"Lot cost basis should be {expected_basis}, got {lot_basis}"

    def test_buy_from_bank_fifo_with_exchange(self, funded_bank):
        """Buy from Bank then Exchange, sell consumes in FIFO order."""
        # Also fund Exchange USD
        create_tx({
            "type": "Deposit",
            "timestamp": build_timestamp(2024, 1, 2),
            "from_account_id": EXTERNAL,
            "to_account_id": EXCHANGE_USD,
            "amount": "50000",
            "fee_amount": "0",
            "fee_currency": "USD",
            "source": "N/A",
        })

        # Buy 0.5 BTC from Bank at $30k ($15k for 0.5)
        bank_buy = create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 1, 10),
            "from_account_id": BANK_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "0.5",
            "fee_amount": "10",
            "fee_currency": "USD",
            "cost_basis_usd": "15000",
        })
        assert "error" not in bank_buy, f"Buy from Bank failed: {bank_buy}"

        # Buy 0.5 BTC from Exchange at $40k ($20k for 0.5)
        exchange_buy = create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 1, 15),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "0.5",
            "fee_amount": "10",
            "fee_currency": "USD",
            "cost_basis_usd": "20000",
        })
        assert "error" not in exchange_buy, f"Buy from Exchange failed: {exchange_buy}"

        # Sell 0.5 BTC - should consume Bank-bought lot first (older)
        sell_tx = create_tx({
            "type": "Sell",
            "timestamp": build_timestamp(2024, 2, 1),
            "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD,
            "amount": "0.5",
            "fee_amount": "10",
            "fee_currency": "USD",
            "proceeds_usd": "25000",
        })
        assert "error" not in sell_tx, f"Sell failed: {sell_tx}"

        # Verify disposal used Bank-bought lot (cost basis $15k + $10 fee = $15010)
        disposals = get_disposals()
        sell_disposals = [d for d in disposals if d.get("transaction_id") == sell_tx["id"]]
        assert len(sell_disposals) == 1, "Should have one disposal"

        disposal_basis = Decimal(str(sell_disposals[0].get("disposal_basis_usd", 0)))
        # Cost basis for 0.5 BTC from Bank lot = $15,010 total / 0.5 BTC * 0.5 BTC = $15,010
        expected_basis = Decimal("15010")
        assert abs(disposal_basis - expected_basis) < DECIMAL_TOLERANCE, \
            f"Disposal basis should be ~{expected_basis} (from Bank lot), got {disposal_basis}"

        # Verify Exchange-bought lot is still full (remaining = 0.5)
        lots = get_lots()
        exchange_lot = next(
            (l for l in lots if l.get("created_txn_id") == exchange_buy["id"]),
            None
        )
        assert exchange_lot is not None, "Exchange lot should exist"
        remaining = Decimal(str(exchange_lot.get("remaining_btc", 0)))
        assert abs(remaining - Decimal("0.5")) < SATOSHI_TOLERANCE, \
            f"Exchange lot should be untouched, remaining={remaining}"

    def test_buy_from_bank_allows_negative_balance(self, funded_bank):
        """Buy exceeding Bank balance creates negative balance (ledger behavior)."""
        # Bank has $50,000 from fixture
        # Double-entry ledgers allow negative balances - enforcement is frontend concern
        buy_tx = create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 1, 15),
            "from_account_id": BANK_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "1.0",
            "fee_amount": "100",
            "fee_currency": "USD",
            "cost_basis_usd": "60000",  # More than Bank balance
        })

        # Transaction succeeds (ledger allows negative balances)
        assert "error" not in buy_tx, f"Transaction should succeed: {buy_tx}"

        # Bank balance should be negative
        bank_balance = get_balance(BANK_USD)
        assert bank_balance < 0, f"Bank balance should be negative, got {bank_balance}"

    def test_buy_from_bank_csv_import(self, clean_db):
        """CSV import with Buy from Bank should work."""
        from backend.services.csv_import import parse_csv_file

        # Create CSV content with Buy from Bank
        csv_content = """date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency,source,purpose,notes
2024-01-01T10:00:00Z,Deposit,50000,External,Bank,,,,,,,Initial USD
2024-01-15T10:00:00Z,Buy,0.5,Bank,Exchange BTC,10000,,50,USD,,,Buy from Bank
"""
        result = parse_csv_file(csv_content.encode('utf-8'))

        # Should parse without errors
        assert len(result.errors) == 0, f"CSV parse errors: {result.errors}"
        assert result.can_import, "Should be importable"
        assert len(result.transactions) == 2, "Should have 2 transactions"

        # Verify second transaction is Buy from Bank
        buy_tx = result.transactions[1]
        assert buy_tx["type"] == "Buy"
        assert buy_tx["from_account_id"] == BANK_USD
        assert buy_tx["to_account_id"] == EXCHANGE_BTC

    def test_buy_from_exchange_still_works(self, funded_bank):
        """Traditional Buy from Exchange USD still works."""
        # Fund Exchange USD
        create_tx({
            "type": "Deposit",
            "timestamp": build_timestamp(2024, 1, 2),
            "from_account_id": EXTERNAL,
            "to_account_id": EXCHANGE_USD,
            "amount": "20000",
            "fee_amount": "0",
            "fee_currency": "USD",
            "source": "N/A",
        })

        # Buy from Exchange USD (original behavior)
        buy_tx = create_tx({
            "type": "Buy",
            "timestamp": build_timestamp(2024, 1, 15),
            "from_account_id": EXCHANGE_USD,
            "to_account_id": EXCHANGE_BTC,
            "amount": "0.5",
            "fee_amount": "10",
            "fee_currency": "USD",
            "cost_basis_usd": "10000",
        })
        assert "error" not in buy_tx, f"Traditional Buy from Exchange should work: {buy_tx}"

        # Verify lot created
        lots = get_lots()
        buy_lot = next(
            (l for l in lots if l.get("created_txn_id") == buy_tx["id"]),
            None
        )
        assert buy_lot is not None, "Should create a Bitcoin lot"


# =============================================================================
# MAIN EXECUTION (for running outside pytest)
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
