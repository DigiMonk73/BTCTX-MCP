# Buy from Bank Feature

**Branch:** `feature/buy-from-bank`
**Commit:** `b30a790`
**Date:** 2025-01-16
**Status:** Ready for merge to `develop`

---

## Overview

This feature allows Buy transactions to originate from the **Bank account (ID 1)** in addition to the traditional **Exchange USD account (ID 3)**. This supports "auto-buy" scenarios where users purchase Bitcoin directly from their bank without first transferring USD to the exchange.

### Before This Feature
- Buy transactions required: `from_account = Exchange USD (3)` → `to_account = Exchange BTC (4)`
- Users had to first Transfer USD from Bank to Exchange, then Buy

### After This Feature
- Buy transactions accept: `from_account = Bank (1) OR Exchange USD (3)` → `to_account = Exchange BTC (4)`
- Users can Buy directly from Bank (simulating auto-buy/recurring purchases)

---

## Motivation

Many Bitcoin exchanges offer "auto-buy" features that pull USD directly from a linked bank account. Previously, users had to record this as two transactions:
1. Transfer: Bank → Exchange USD
2. Buy: Exchange USD → Exchange BTC

This feature simplifies the workflow to a single transaction:
1. Buy: Bank → Exchange BTC

---

## Technical Implementation

### Why This Is Safe (FIFO Unaffected)

The FIFO (First-In-First-Out) cost basis system is **not affected** by this change because:

1. **Lot creation** uses `Transaction.to_account_id` (Exchange BTC = 4)
2. **FIFO disposal** queries lots where `Transaction.to_account_id == disposal_from_account`
3. Since the destination remains Exchange BTC for all Buy transactions, lots land in the same pool regardless of whether the USD came from Bank or Exchange

Both Bank-bought and Exchange-bought BTC are consumed in FIFO order when selling from Exchange BTC.

### Files Modified

| File | Changes |
|------|---------|
| `backend/services/transaction.py` | Added `ACCOUNT_BANK` to imports; relaxed Buy validation to accept Bank or Exchange USD |
| `backend/services/csv_import.py` | Added `ACCOUNT_BANK` to imports; updated CSV validation for Buy transactions |
| `frontend/src/components/TransactionForm.tsx` | Added "From Account" dropdown for Buy; updated account mapping and edit mode |
| `frontend/src/types/global.d.ts` | Added `buyFromAccount` field to `TransactionFormData` interface |
| `backend/tests/test_stress_and_forms.py` | Added `TestBuyFromBank` class with 5 test cases |

### Backend Changes

#### `backend/services/transaction.py`

**Lines 36-41** - Added import:
```python
from backend.constants import (
    ACCOUNT_BANK,  # NEW
    ACCOUNT_EXCHANGE_USD,
    ACCOUNT_EXCHANGE_BTC,
    ACCOUNT_EXTERNAL,
)
```

**Lines 1105-1109** - Relaxed validation in `_enforce_transaction_type_rules()`:
```python
# BEFORE:
elif tx_type == "Buy":
    if from_id != ACCOUNT_EXCHANGE_USD:
        raise HTTPException(400, "Buy => from must be Exchange USD.")

# AFTER:
elif tx_type == "Buy":
    if from_id not in (ACCOUNT_BANK, ACCOUNT_EXCHANGE_USD):
        raise HTTPException(400, "Buy => from must be Bank or Exchange USD.")
```

#### `backend/services/csv_import.py`

**Lines 22-29** - Added import for `ACCOUNT_BANK`

**Lines 501-507** - Updated `_validate_accounts_for_type()`:
```python
# BEFORE:
elif tx_type == "Buy":
    if from_id != ACCOUNT_EXCHANGE_USD:
        errors.append(CSVParseError(..., message="Buy must have from_account = 'Exchange USD'."))

# AFTER:
elif tx_type == "Buy":
    if from_id not in (ACCOUNT_BANK, ACCOUNT_EXCHANGE_USD):
        errors.append(CSVParseError(..., message="Buy must have from_account = 'Bank' or 'Exchange USD'."))
```

### Frontend Changes

#### `frontend/src/components/TransactionForm.tsx`

1. **Added `BANK_ID` constant** (line 20):
   ```typescript
   const BANK_ID = 1;
   ```

2. **Updated `mapDoubleEntryAccounts()`** (lines 59-63):
   ```typescript
   case "Buy":
     return {
       from_account_id: data.buyFromAccount === "Bank" ? BANK_ID : EXCHANGE_USD_ID,
       to_account_id: EXCHANGE_BTC_ID,
     };
   ```

3. **Updated `mapTransactionToFormData()`** for edit mode (lines 158-168):
   ```typescript
   case "Buy": {
     const buyFromAccount = tx.from_account_id === 1 ? "Bank" : "Exchange";
     return {
       ...baseData,
       account: "Exchange",
       buyFromAccount,
       amountUSD: tx.cost_basis_usd ?? 0,
       amountBTC: tx.amount,
     };
   }
   ```

4. **Added dropdown in Buy form** (lines 975-988):
   ```tsx
   <div className="form-group">
     <label>From Account:</label>
     <select
       className="form-control"
       {...register("buyFromAccount", { required: true })}
     >
       <option value="Exchange">Exchange USD</option>
       <option value="Bank">Bank (auto-buy)</option>
     </select>
     <small className="form-hint">
       Select where the USD is coming from.
     </small>
   </div>
   ```

5. **Added default value** in form initialization and reset handlers:
   ```typescript
   buyFromAccount: "Exchange",
   ```

#### `frontend/src/types/global.d.ts`

Added to `TransactionFormData` interface (lines 300-301):
```typescript
// For Buy transactions: source account (Bank or Exchange)
buyFromAccount?: "Bank" | "Exchange";
```

---

## Ledger Entry Behavior

When buying from Bank, the ledger entries are:

| Entry Type | Account | Amount | Currency |
|------------|---------|--------|----------|
| MAIN_OUT | Bank (1) | -(cost_basis + fee) | USD |
| MAIN_IN | Exchange BTC (4) | +amount | BTC |
| FEE | USD Fees (6) | +fee | USD |

This mirrors the existing Exchange USD behavior, just with a different source account.

---

## Test Coverage

Added `TestBuyFromBank` class in `backend/tests/test_stress_and_forms.py` with 5 tests:

| Test | Description |
|------|-------------|
| `test_buy_from_bank_basic` | Buy 0.5 BTC from Bank, verify balances and lot creation with correct cost basis |
| `test_buy_from_bank_fifo_with_exchange` | Buy from Bank then Exchange, verify FIFO consumes Bank lot first (older) |
| `test_buy_from_bank_allows_negative_balance` | Verify ledger allows negative Bank balance (enforcement is frontend concern) |
| `test_buy_from_bank_csv_import` | CSV import with `from_account=Bank` parses correctly |
| `test_buy_from_exchange_still_works` | Backward compatibility: traditional Buy from Exchange USD still works |

### Test Results
- All 135 tests pass (5 new + 130 existing)
- Pre-commit tests: 10/10 pass

---

## Backward Compatibility

| Scenario | Status |
|----------|--------|
| Existing Buy transactions (`from_account_id=3`) | ✅ Continue to work |
| Existing CSVs with `Exchange USD` source | ✅ Import correctly |
| Frontend defaults to "Exchange" | ✅ Unchanged UX for users who don't need Bank option |
| Edit mode for old Buy transactions | ✅ Dropdown shows "Exchange USD" correctly |

---

## CSV Format

### Import
Buy transactions now accept two `from_account` values:
- `Exchange USD` (existing)
- `Bank` (new)

Example CSV row:
```csv
2024-01-15T10:00:00Z,Buy,0.5,Bank,Exchange BTC,10000,,50,USD,,,Buy from Bank
```

### Export
Existing exports will show the actual `from_account` used (Bank or Exchange USD).

---

## Known Limitations

1. **No balance enforcement**: The backend allows negative balances (standard double-entry ledger behavior). Balance validation should be done in the frontend before submitting.

2. **Destination fixed**: Buy transactions still must go to Exchange BTC (ID 4). You cannot buy directly into Wallet - that would require a Transfer afterward.

3. **Fee currency**: Buy fees must still be in USD (enforced by `_enforce_fee_rules()`).

---

## Changelog Entry (for merge)

```markdown
### Added
- Buy transactions can now originate from Bank account (auto-buy support)
  - New "From Account" dropdown in Buy form (Exchange USD or Bank)
  - CSV import accepts `Bank` as source for Buy transactions
  - FIFO cost basis tracking works correctly for Bank-bought BTC
```

---

## Rollback

**Rollback tags were created before this feature was merged:**

| Tag | Branch | Commit | Description |
|-----|--------|--------|-------------|
| `pre-bank-buy` | develop | aeb3e35 | State before feature merge |
| `pre-bank-buy-master` | master | 430f584 | State before release |

### To Rollback Develop
```bash
git checkout develop
git reset --hard pre-bank-buy
git push --force origin develop
git push --force plebrick develop
```

### To Rollback Master
```bash
git checkout master
git reset --hard pre-bank-buy-master
git push --force origin master
git push --force plebrick master
```

### Alternative: Revert Single Commit
If only the feature commit needs reverting (preserving subsequent commits):
```bash
git revert b30a790
```

---

## Related Files

- `backend/constants.py` - Account ID definitions (unchanged, just referenced)
- `backend/models/transaction.py` - Transaction model (unchanged)
- `backend/services/transaction.py` - Core transaction logic (modified)
- `backend/services/csv_import.py` - CSV parsing (modified)
- `frontend/src/components/TransactionForm.tsx` - Form UI (modified)
