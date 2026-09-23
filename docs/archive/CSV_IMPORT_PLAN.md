# CSV Import Feature Plan

> **Status:** Planning
> **Target Version:** v0.4.0
> **Last Updated:** 2025-01-10

---

## Overview

Enable users to import transactions from CSV files exported from exchanges, Koinly, or personal spreadsheets. This is a high-risk feature that can corrupt FIFO calculations if done incorrectly, so we proceed with extreme caution.

---

## Critical Constraints

### 1. Empty Database Only (Phase 1-2)

**Decision:** CSV import will ONLY work on an empty database initially.

**Rationale:**
- Merging imported transactions with existing ones is extremely complex
- FIFO lot ordering depends on chronological order of ALL transactions
- Duplicate detection is error-prone (same amount on same day = duplicate or coincidence?)
- Cost basis calculations would need full re-lot after merge
- User could accidentally destroy months of carefully entered data

**User Flow:**
1. User clicks "Import CSV"
2. System checks if database has existing transactions
3. If transactions exist → Show warning: "Import only works with an empty database. Please backup and delete all transactions first, or start fresh."
4. If empty → Proceed with import

**Future (Phase 3+):** Consider merge capability after core import is battle-tested.

### 2. Validation Before Commit

All imported transactions are validated and previewed BEFORE any database writes:
- Parse entire CSV
- Validate all rows
- Show preview with any warnings/errors
- User confirms
- Only then write to database (in single transaction for rollback safety)

### 3. Supported Transaction Types

Import must map to BitcoinTX's existing types:
- `Deposit` (BTC coming in from external source)
- `Withdrawal` (BTC leaving to external destination)
- `Buy` (USD → BTC on exchange)
- `Sell` (BTC → USD on exchange)
- `Transfer` (BTC moving between user's own accounts)

---

## Phase 1: Koinly Universal Format Import

**Goal:** Import from Koinly exports, which already normalize data from 400+ exchanges.

### Why Koinly First?

1. Koinly aggregates data from most exchanges (Coinbase, Kraken, River, etc.)
2. Users already using Koinly have clean, normalized data
3. Single format to support initially
4. Well-documented CSV structure

### Koinly CSV Format

```csv
Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Net Worth Amount,Net Worth Currency,Label,Description,TxHash
2024-01-15 10:30:00 UTC,500,USD,0.012,BTC,5,USD,500,USD,,Coinbase,abc123
2024-01-20 14:00:00 UTC,0.1,BTC,,,0.0001,BTC,4500,USD,gift,,def456
```

### Mapping to BitcoinTX

| Koinly Pattern | BitcoinTX Type | Notes |
|----------------|----------------|-------|
| Sent=USD, Received=BTC | `Buy` | Exchange purchase |
| Sent=BTC, Received=USD | `Sell` | Exchange sale |
| Sent=BTC, Received=empty | `Withdrawal` | BTC leaving |
| Sent=empty, Received=BTC | `Deposit` | BTC arriving |
| Sent=BTC, Received=BTC (same amount) | `Transfer` | Internal move |

### Koinly Label Mapping

| Koinly Label | BitcoinTX Field |
|--------------|-----------------|
| `gift` (sent) | `purpose: "Gift"` |
| `donation` | `purpose: "Donation"` |
| `lost` | `purpose: "Lost"` |
| `cost` / `payment` | `purpose: "Spent"` |
| `income` | `source: "Income"` |
| `mining` | `source: "Reward"` |
| `staking` | `source: "Interest"` |
| `airdrop` | `source: "Reward"` |
| `gift` (received) | `source: "Gift"` |

### Account Assignment

Since Koinly doesn't map to BitcoinTX's specific accounts (Wallet, Exchange BTC, etc.), use these defaults:

| Transaction Type | From Account | To Account |
|------------------|--------------|------------|
| Buy | Exchange USD (3) | Exchange BTC (4) |
| Sell | Exchange BTC (4) | Exchange USD (3) |
| Deposit | External (99) | Wallet (2) |
| Withdrawal | Wallet (2) | External (99) |
| Transfer | Exchange BTC (4) | Wallet (2) |

**Note:** User can edit individual transactions after import to fix account assignments.

### Phase 1 Implementation Tasks

1. **Backend: CSV Parser Service** (`backend/services/csv_import.py`)
   - [ ] Parse Koinly CSV format
   - [ ] Validate required columns exist
   - [ ] Map rows to transaction dictionaries
   - [ ] Return list of parsed transactions + any errors/warnings

2. **Backend: Import Router** (`backend/routers/csv_import.py`)
   - [ ] `POST /api/import/preview` - Parse and return preview (no DB writes)
   - [ ] `POST /api/import/execute` - Actually import after user confirms
   - [ ] Check for empty database before allowing import
   - [ ] Wrap all inserts in single DB transaction

3. **Frontend: Import UI** (Settings page)
   - [ ] File upload component
   - [ ] Format selector (Koinly only in Phase 1)
   - [ ] Preview table showing parsed transactions
   - [ ] Error/warning display
   - [ ] Confirm/Cancel buttons
   - [ ] Progress indicator for large imports

4. **Validation Rules**
   - [ ] Date must be valid and parseable
   - [ ] Amounts must be positive numbers
   - [ ] Currency must be BTC or USD
   - [ ] No future dates (warning, not error)
   - [ ] Chronological order check

5. **Testing**
   - [ ] Unit tests for CSV parser
   - [ ] Test with real Koinly exports
   - [ ] Test error handling (malformed CSV, missing columns)
   - [ ] Test rollback on partial failure

---

## Phase 2: BitcoinTX Native Format + Column Mapping UI

**Goal:** Support a simple native format AND let users map arbitrary CSV columns.

### BitcoinTX Native CSV Format

```csv
date,type,amount,amount_usd,fee_amount,fee_currency,from_account,to_account,source,purpose,cost_basis_usd
2024-01-15T10:30:00Z,Buy,0.012,500.00,5.00,USD,Exchange USD,Exchange BTC,,,
2024-01-20T14:00:00Z,Withdrawal,0.1,,0.0001,BTC,Wallet,External,,Gift,4500.00
```

### Column Mapping UI

For arbitrary CSVs:
1. User uploads CSV
2. System shows first 5 rows as preview
3. User maps each BitcoinTX field to a CSV column (or "skip"):
   - Date column: [dropdown of CSV columns]
   - Type column: [dropdown] OR [fixed value: "Buy"]
   - Amount column: [dropdown]
   - etc.
4. System validates mapping makes sense
5. Preview result of mapping
6. User confirms

### Mapping Persistence

- Save mappings with a name (e.g., "My Coinbase Export")
- User can reuse saved mappings for future imports
- Store in database or localStorage

### Phase 2 Implementation Tasks

1. **Backend: Generic CSV Parser**
   - [ ] Accept column mapping configuration
   - [ ] Apply mapping to parse rows
   - [ ] Handle missing optional columns gracefully

2. **Backend: Mapping Storage**
   - [ ] Model for saved mappings (name, column_config JSON)
   - [ ] CRUD endpoints for mappings

3. **Frontend: Mapping UI**
   - [ ] Column detection from uploaded CSV
   - [ ] Drag-drop or dropdown mapping interface
   - [ ] Live preview as mapping changes
   - [ ] Save/load mapping presets

4. **Built-in Presets**
   - [ ] Koinly (from Phase 1)
   - [ ] BitcoinTX native format
   - [ ] Coinbase (if format is stable)
   - [ ] Generic (user maps everything)

---

## Phase 3: Merge with Existing Data (Future)

**Goal:** Allow importing into a database that already has transactions.

### Challenges

1. **Duplicate Detection**
   - Same date + same amount = duplicate?
   - What if user legitimately bought same amount twice on same day?
   - Need fuzzy matching + user confirmation

2. **FIFO Recalculation**
   - All lots must be recalculated after import
   - Could take time for large datasets
   - Must happen atomically

3. **Conflict Resolution**
   - What if imported transaction conflicts with existing?
   - UI to show conflicts and let user choose

### Phase 3 Implementation Tasks (Deferred)

1. **Duplicate Detection Algorithm**
   - [ ] Define matching criteria (date within X minutes, amount within tolerance)
   - [ ] Mark potential duplicates for user review
   - [ ] Allow user to skip duplicates or import anyway

2. **Merge Preview**
   - [ ] Show which transactions would be added
   - [ ] Show which might be duplicates
   - [ ] Show warning about FIFO recalculation

3. **Post-Import Recalculation**
   - [ ] Trigger full `recalculate_all_transactions()` after merge
   - [ ] Show progress for large datasets

---

## UI Location

**Recommendation:** Settings page, not Transactions page

**Reasons:**
- Import is a "setup" operation, not daily use
- Reduces accidental imports
- Settings already has backup/restore, import fits there
- Keeps Transactions page focused on viewing/editing

**Settings Page Layout:**
```
Settings
├── Account
│   └── Change Password
├── Data
│   ├── Backup Database
│   ├── Restore Database
│   └── Import Transactions (CSV)  ← NEW
└── About
    └── Version info
```

---

## Error Handling

### Parse Errors (Non-Fatal)
- Missing optional field → Use default, show warning
- Invalid date format → Skip row, show error
- Unknown transaction type → Skip row, show error

### Parse Errors (Fatal)
- Missing required column (Date, Amount) → Abort with message
- File not valid CSV → Abort with message
- File too large (>10MB?) → Abort with message

### Import Errors
- Database not empty → Block import, show message
- Duplicate transaction detected → Show warning, let user decide
- Database write fails → Full rollback, show error

---

## Security Considerations

1. **File Size Limit:** Max 10MB to prevent DoS
2. **Row Limit:** Max 10,000 transactions per import
3. **Sanitization:** Strip any HTML/scripts from text fields
4. **No External Fetches:** Don't fetch prices during import (use provided data)
5. **Audit Log:** Log all imports with timestamp and row count

---

## Testing Strategy

### Unit Tests
- CSV parser with valid Koinly file
- CSV parser with missing columns
- CSV parser with malformed data
- Transaction type mapping logic
- Account assignment logic

### Integration Tests
- Full import flow with mock database
- Rollback on failure
- Empty database check

### Manual Testing
- Real Koinly export from user's account
- Export from River, Coinbase (via Koinly)
- Large file (1000+ transactions)
- Edge cases (same-day transactions, tiny amounts)

---

## Rollout Plan

1. **Phase 1 (v0.4.0):** Koinly import only, empty database only
2. **Phase 2 (v0.5.0):** Native format + column mapping UI
3. **Phase 3 (v0.6.0+):** Merge with existing data (if needed)

---

## Open Questions

1. **Should we auto-fetch historical prices for imports?**
   - Pro: Better cost basis accuracy
   - Con: Slow, API rate limits, adds complexity
   - **Recommendation:** No, use data from CSV. User can edit after.

2. **Should Transfer detection be automatic?**
   - Koinly marks transfers, but other formats might not
   - Could detect: BTC out followed by BTC in of same amount within X minutes
   - **Recommendation:** Trust CSV labels for now, Phase 3 could add detection

3. **What about non-BTC crypto?**
   - BitcoinTX is BTC-only currently
   - Should import skip non-BTC rows or error?
   - **Recommendation:** Skip with warning ("Skipped 5 ETH transactions")

---

## Success Criteria

Phase 1 is complete when:
- [ ] User can export from Koinly and import to BitcoinTX
- [ ] All transaction types map correctly
- [ ] FIFO calculations work correctly after import
- [ ] IRS reports generate correctly from imported data
- [ ] No data corruption possible (empty DB requirement enforced)
- [ ] Clear error messages for invalid files

---

## References

- [Koinly CSV Export Format](https://help.koinly.io/en/articles/3662999-how-to-export-your-data-from-koinly)
- [BitcoinTX Transaction Model](../backend/models/transaction.py)
- [FIFO Lot Tracking](../backend/services/transaction.py)
