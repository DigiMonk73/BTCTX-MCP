# macOS Desktop App - Transaction Edit Bug

**Status:** FIXED
**Date:** 2025-01-17
**Affected:** v0.5.4 desktop app
**Root Cause:** Backend FIFO lot logic, not pywebview

---

## Problem Description

Editing transactions in the macOS desktop app (PyInstaller + pywebview) failed silently. The same functionality worked correctly in Docker/StartOS deployments.

**Symptoms:**
- Click "Update" on an existing transaction
- Brief flash of the progress spinner
- Process aborts and returns to starting state
- No visible success or error message

---

## Root Cause

**NOT a pywebview/WebKit issue.** The bug was in the backend's transaction update logic.

When editing a transaction, `update_transaction_record()` had a flawed flow:

1. Remove old lot usage (but didn't restore `remaining_btc` on source lots)
2. Rebuild lot logic for this transaction (validation fails - "Not enough BTC")
3. Run scorched earth re-lot (never reached due to step 2 failing)

**The specific trigger:** When **backdating** a transaction (changing timestamp to earlier), the partial re-lot `recalculate_subsequent_transactions()` was called before the full scorched earth. This partial re-lot only cleared lots from the new timestamp forward, leaving lots from before with stale (depleted) balances.

**Why Docker worked:** Different database with different transaction history. The validation happened to pass there due to sufficient BTC balance even with stale lots.

---

## The Fix

Simplified `update_transaction_record()` to skip all individual lot logic and use only the full scorched earth re-lot:

```python
def update_transaction_record(transaction_id: int, tx_data: dict, db: Session):
    # ... validate and update transaction fields ...

    tx.updated_at = datetime.now(timezone.utc)
    db.flush()

    # Single scorched earth handles all cases uniformly
    recalculate_all_transactions(db)

    db.commit()
    db.refresh(tx)
    return tx
```

**Why this works:** The scorched earth:
1. Deletes ALL ledger entries, lot disposals, and bitcoin lots
2. Rebuilds everything in chronological order from scratch
3. No stale state issues - always consistent

---

## Investigation Journey

### Phase 1: Wrong Hypothesis

**Initial theory:** pywebview's WebKit handles PUT requests differently than browsers.

**Actions taken:**
- Added PUT response validation in `TransactionForm.tsx`
- Added realized gain display on edit (matching create behavior)

**Outcome:** Good defensive changes, but didn't solve the problem. Kept these changes anyway.

### Phase 2: Debug Logging

**Actions taken:**
- Added console.log statements to trace request flow
- Enabled pywebview debug mode (`debug=True`)

**Discovery:** The PUT request was returning 400 Bad Request with:
```
{detail: "Not enough BTC to transfer 0.01030181 + fee 0"}
```

This revealed it was a backend validation error, not a frontend/pywebview issue.

### Phase 3: Failed Fix Attempts

**Attempt 1:** Restore `remaining_btc` in `remove_lot_usage_for_tx()` when removing disposals.
- **Result:** Failed. Source lot matching by `acquired_date` didn't reliably find the correct lots.

**Attempt 2:** Skip individual lot logic, rely on scorched earth at end.
- **Result:** Failed. The backdating code (`recalculate_subsequent_transactions`) still ran before scorched earth.

### Phase 4: Success

**Attempt 3:** Remove ALL intermediate lot logic, including backdating partial re-lot. Use only scorched earth.
- **Result:** Success!

---

## Key Observations

### 1. The "Scorched Earth" Pattern Works
The codebase already had a robust `recalculate_all_transactions()` function that rebuilds everything correctly. The bug was trying to be "smart" with partial updates before calling it.

**Lesson:** For a single-user app with modest data sizes, full rebuilds are simpler and more reliable than incremental updates.

### 2. Desktop vs Docker Have Separate Databases
- Desktop: `~/Library/Application Support/BitcoinTX/btctx.db`
- Docker: `/data/btctx.db`

Bugs that depend on data state may appear in one environment but not the other.

### 3. Debug Mode is Essential for Desktop
pywebview with `debug=True` allows right-click → Inspect Element → Console, which was critical for discovering the real error.

### 4. Don't Assume the Obvious Cause
Initial hypothesis (pywebview PUT handling) was wrong. The real cause (backend FIFO logic) only surfaced through systematic debugging.

---

## Final Changes

### Kept (Improvements)

| File | Change | Reason |
|------|--------|--------|
| `TransactionForm.tsx` | PUT response validation | Defensive programming |
| `TransactionForm.tsx` | Show realized gain on edit | Feature parity with create |
| `transaction.py` | Simplified update to scorched earth only | **THE FIX** |

### Reverted (Debug/Failed)

| File | Change | Reason |
|------|--------|--------|
| `TransactionForm.tsx` | Debug console.log | Cleanup |
| `entrypoint.py` | `debug=True` | Cleanup |
| `transaction.py` | Lot restoration in `remove_lot_usage_for_tx` | Dead code (function unused) |

---

## Verification

- **Pre-commit tests:** 17/17 passed
- **Full pytest suite:** 135/135 passed
- **Docker compatibility:** Verified

---

## Debug Reference

### Enable Desktop Debug Mode
```python
# desktop/entrypoint.py
webview.start(debug=True)
```
Then right-click in app → Inspect Element → Console

### Check Desktop Database
```bash
sqlite3 ~/Library/Application\ Support/BitcoinTX/btctx.db \
  "SELECT id, type, datetime(timestamp), amount FROM transactions ORDER BY timestamp;"
```

### Verbose Backend Logging
```python
# desktop/entrypoint.py
uvicorn.run(
    "backend.main:app",
    host="127.0.0.1",
    port=port,
    log_level="debug",
    access_log=True,
)
```

---

## Related Files

- `backend/services/transaction.py` - Core transaction/FIFO logic (fix location)
- `frontend/src/components/TransactionForm.tsx` - Edit form (defensive improvements)
- `desktop/entrypoint.py` - Desktop app entry point
- `docs/MACOS_DESKTOP_APP.md` - Desktop build documentation
