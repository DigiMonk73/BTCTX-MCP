#!/usr/bin/env python3
"""
Test that backdated transactions trigger proper FIFO recalculation.

Scenario:
1. Create Buy A on 2024-02-01 for 1 BTC at $40,000
2. Create Buy B on 2024-03-01 for 1 BTC at $50,000
3. Create Sell on 2024-04-01 for 1 BTC (should consume Buy A at $40k)
4. Create backdated Buy C on 2024-01-01 for 1 BTC at $30,000
5. After recalculation, Sell should now consume Buy C at $30k (oldest lot first)

Expected Result:
- Before backdated insert: Sell cost basis = $40,000 (from Buy A)
- After backdated insert: Sell cost basis = $30,000 (from Buy C)
"""

import requests
import sys

BASE_URL = "http://127.0.0.1:8000"
DELETE_ALL = f"{BASE_URL}/api/transactions/delete_all"
TRANSACTIONS_URL = f"{BASE_URL}/api/transactions"
LOTS_URL = f"{BASE_URL}/api/calculations/bitcoin-lots"

# Account IDs (from your schema)
EXTERNAL = 99
EXCHANGE_USD = 3
EXCHANGE_BTC = 4


def delete_all():
    """Delete all transactions to start fresh."""
    r = requests.delete(DELETE_ALL)
    if r.status_code not in (200, 204):
        print(f"FAIL: Could not delete transactions: {r.status_code}")
        sys.exit(1)
    print("Cleared all transactions.")


def create_tx(tx_data):
    """Create a transaction and return the response."""
    r = requests.post(TRANSACTIONS_URL, json=tx_data)
    if not r.ok:
        print(f"FAIL: Could not create transaction: {r.status_code} {r.text}")
        sys.exit(1)
    return r.json()


def get_lots():
    """Get all Bitcoin lots."""
    r = requests.get(LOTS_URL)
    if not r.ok:
        print(f"FAIL: Could not get lots: {r.status_code}")
        sys.exit(1)
    return r.json()


def get_transaction(tx_id):
    """Get a single transaction by ID."""
    r = requests.get(f"{TRANSACTIONS_URL}/{tx_id}")
    if not r.ok:
        print(f"FAIL: Could not get transaction {tx_id}: {r.status_code}")
        sys.exit(1)
    return r.json()


def main():
    print("=" * 60)
    print("BACKDATED FIFO RECALCULATION TEST")
    print("=" * 60)

    # Step 0: Clear everything
    delete_all()

    # Step 1: Deposit USD (needed for Buy transactions)
    print("\n[Step 1] Depositing USD...")
    create_tx({
        "type": "Deposit",
        "timestamp": "2024-01-01T00:00:00Z",
        "from_account_id": EXTERNAL,
        "to_account_id": EXCHANGE_USD,
        "amount": "200000",
        "fee_amount": "0",
        "fee_currency": "USD",
        "source": "N/A"
    })

    # Step 2: Create Buy A on 2024-02-01 for 1 BTC at $40,000
    print("\n[Step 2] Creating Buy A (2024-02-01) - 1 BTC @ $40,000...")
    buy_a = create_tx({
        "type": "Buy",
        "timestamp": "2024-02-01T12:00:00Z",
        "from_account_id": EXCHANGE_USD,
        "to_account_id": EXCHANGE_BTC,
        "amount": "1.0",
        "fee_amount": "0",
        "fee_currency": "USD",
        "cost_basis_usd": "40000"
    })
    print(f"   Created Buy A: ID={buy_a['id']}")

    # Step 3: Create Buy B on 2024-03-01 for 1 BTC at $50,000
    print("\n[Step 3] Creating Buy B (2024-03-01) - 1 BTC @ $50,000...")
    buy_b = create_tx({
        "type": "Buy",
        "timestamp": "2024-03-01T12:00:00Z",
        "from_account_id": EXCHANGE_USD,
        "to_account_id": EXCHANGE_BTC,
        "amount": "1.0",
        "fee_amount": "0",
        "fee_currency": "USD",
        "cost_basis_usd": "50000"
    })
    print(f"   Created Buy B: ID={buy_b['id']}")

    # Step 4: Create Sell on 2024-04-01 for 1 BTC
    print("\n[Step 4] Creating Sell (2024-04-01) - 1 BTC @ $60,000 proceeds...")
    sell = create_tx({
        "type": "Sell",
        "timestamp": "2024-04-01T12:00:00Z",
        "from_account_id": EXCHANGE_BTC,
        "to_account_id": EXCHANGE_USD,
        "amount": "1.0",
        "fee_amount": "0",
        "fee_currency": "USD",
        "proceeds_usd": "60000"
    })
    sell_id = sell['id']
    print(f"   Created Sell: ID={sell_id}")

    # Check the sell's cost basis BEFORE backdated insert
    sell_before = get_transaction(sell_id)
    cost_basis_before = float(sell_before.get('cost_basis_usd') or 0)
    print(f"\n[Check] Sell cost basis BEFORE backdated insert: ${cost_basis_before:,.2f}")

    if abs(cost_basis_before - 40000) < 0.01:
        print("   PASS: Sell consumed Buy A ($40,000) as expected (FIFO)")
    else:
        print(f"   WARNING: Expected $40,000, got ${cost_basis_before:,.2f}")

    # Step 5: Create BACKDATED Buy C on 2024-01-15 for 1 BTC at $30,000
    # This is EARLIER than Buy A, so after recalculation, Sell should consume Buy C
    print("\n[Step 5] Creating BACKDATED Buy C (2024-01-15) - 1 BTC @ $30,000...")
    buy_c = create_tx({
        "type": "Buy",
        "timestamp": "2024-01-15T12:00:00Z",  # BEFORE Buy A!
        "from_account_id": EXCHANGE_USD,
        "to_account_id": EXCHANGE_BTC,
        "amount": "1.0",
        "fee_amount": "0",
        "fee_currency": "USD",
        "cost_basis_usd": "30000"
    })
    print(f"   Created Buy C (backdated): ID={buy_c['id']}")

    # Check the sell's cost basis AFTER backdated insert
    sell_after = get_transaction(sell_id)
    cost_basis_after = float(sell_after.get('cost_basis_usd') or 0)
    print(f"\n[Check] Sell cost basis AFTER backdated insert: ${cost_basis_after:,.2f}")

    # Verify the recalculation worked
    print("\n" + "=" * 60)
    print("TEST RESULTS")
    print("=" * 60)

    if abs(cost_basis_after - 30000) < 0.01:
        print("PASS: Backdated recalculation worked!")
        print("  - Sell now uses Buy C ($30,000) instead of Buy A ($40,000)")
        print(f"  - Realized gain changed from ${60000 - cost_basis_before:,.2f} to ${60000 - cost_basis_after:,.2f}")
        return 0
    else:
        print("FAIL: Backdated recalculation did NOT work!")
        print("  - Expected cost basis: $30,000 (from Buy C)")
        print(f"  - Actual cost basis: ${cost_basis_after:,.2f}")
        print("  - The Sell is still using the wrong lot")
        return 1


if __name__ == "__main__":
    sys.exit(main())
