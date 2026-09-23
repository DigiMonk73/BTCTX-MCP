# Pydantic V1 → V2 Migration

> **Status:** COMPLETED (2025-01-16)
> **Branch:** `feature/macos-desktop`
> **Commit:** `9a4cf42 refactor: Migrate Pydantic V1 patterns to V2`

---

## Migration Summary

BitcoinTX was using Pydantic 2.12.5 but with V1-style syntax that triggered deprecation warnings. This migration updated all deprecated patterns to V2 equivalents.

### Changes Made

| File | Change |
|------|--------|
| `backend/schemas/account.py` | `@validator` → `@field_validator` + `@classmethod`; `class Config` → `model_config = ConfigDict(...)` |
| `backend/schemas/user.py` | Added `ConfigDict` import; `class Config: orm_mode = True` → `model_config = ConfigDict(from_attributes=True)` |
| `backend/schemas/transaction.py` | Added `ConfigDict` import; 4× `class Config` → `model_config = ConfigDict(...)` |
| `backend/routers/transaction.py` | `.from_orm()` → `.model_validate()`; `.dict()` → `.model_dump()` |

### Pattern Mapping Reference

| V1 Pattern | V2 Pattern |
|------------|------------|
| `@validator("field")` | `@field_validator("field")` + `@classmethod` |
| `class Config: orm_mode = True` | `model_config = ConfigDict(from_attributes=True)` |
| `class Config: from_attributes = True` | `model_config = ConfigDict(from_attributes=True)` |
| `Model.from_orm(obj)` | `Model.model_validate(obj)` |
| `instance.dict()` | `instance.model_dump()` |
| `instance.dict(exclude_unset=True)` | `instance.model_dump(exclude_unset=True)` |

---

## Verification Results

### Automated Tests

| Test Suite | Tests | Result |
|------------|-------|--------|
| Pre-commit tests | 17 | All passed |
| Pytest suite | 84 | All passed |
| Pydantic deprecation warnings | 0 | None found |

### Manual Verification

| Feature | Endpoint | Result |
|---------|----------|--------|
| Transactions API | `GET /api/transactions` | JSON serialization works |
| CSV Export | `GET /api/backup/csv` | 5 rows exported correctly |
| CSV Import Preview | `POST /api/import/preview` | Parses correctly |
| CSV Roundtrip | Delete → Import | 5 transactions restored |
| Encrypted Backup | `POST /api/backup/download` | 196KB .btx file generated |
| IRS Forms | `GET /api/reports/irs_reports?year=2024` | 4-page PDF generated |
| Complete Tax Report | `GET /api/reports/complete_tax_report?year=2024` | 3-page PDF generated |
| Transaction History | `GET /api/reports/simple_transaction_history` | CSV exported correctly |

---

## Detailed Changes

### 1. backend/schemas/account.py

**Import change:**
```python
# BEFORE:
from pydantic import BaseModel, validator

# AFTER:
from pydantic import BaseModel, field_validator, ConfigDict
```

**Validator changes (2 occurrences):**
```python
# BEFORE:
@validator("currency")
def currency_must_be_valid(cls, v):
    ...

# AFTER:
@field_validator("currency")
@classmethod
def currency_must_be_valid(cls, v):
    ...
```

**Config change:**
```python
# BEFORE:
class Config:
    from_attributes = True

# AFTER:
model_config = ConfigDict(from_attributes=True)
```

### 2. backend/schemas/user.py

**Import change:**
```python
# BEFORE:
from pydantic import BaseModel

# AFTER:
from pydantic import BaseModel, ConfigDict
```

**Config change (note: `orm_mode` renamed to `from_attributes`):**
```python
# BEFORE:
class Config:
    orm_mode = True

# AFTER:
model_config = ConfigDict(from_attributes=True)
```

### 3. backend/schemas/transaction.py

**Import change:**
```python
# BEFORE:
from pydantic import BaseModel, Field, field_validator

# AFTER:
from pydantic import BaseModel, Field, field_validator, ConfigDict
```

**Config changes (4 occurrences in TransactionRead, LedgerEntryRead, BitcoinLotRead, LotDisposalRead):**
```python
# BEFORE:
class Config:
    from_attributes = True

# AFTER:
model_config = ConfigDict(from_attributes=True)
```

### 4. backend/routers/transaction.py

**ORM conversion change:**
```python
# BEFORE:
pyd_model = TransactionRead.from_orm(tx)
data = pyd_model.dict()

# AFTER:
pyd_model = TransactionRead.model_validate(tx)
data = pyd_model.model_dump()
```

**Schema serialization changes:**
```python
# BEFORE:
tx_data = tx.dict()
tx_data = tx.dict(exclude_unset=True)

# AFTER:
tx_data = tx.model_dump()
tx_data = tx.model_dump(exclude_unset=True)
```

---

## Files NOT Requiring Changes

These files were reviewed and found to be V2-compliant or not using Pydantic patterns:

- `backend/schemas/csv_import.py` - Uses only `BaseModel` with simple fields
- `backend/main.py` (`LoginRequest` class) - Simple schema, no deprecated patterns
- `backend/tests/seed_transactions.py` - Already uses `.model_dump()`

---

## Troubleshooting

If issues arise after this migration, check for:

1. **ValidationError on model creation:**
   - V2 `@field_validator` requires `@classmethod` decorator
   - Validator function still receives `cls` as first argument

2. **AttributeError: 'Model' object has no attribute 'dict':**
   - Change `.dict()` to `.model_dump()`

3. **AttributeError: type object 'Model' has no attribute 'from_orm':**
   - Change `.from_orm(obj)` to `.model_validate(obj)`
   - Ensure `model_config = ConfigDict(from_attributes=True)` is set

4. **ORM objects not converting to Pydantic:**
   - Verify `from_attributes=True` is set in `model_config`

---

## Original Planning Document

The sections below contain the original pre-migration analysis and planning notes.

---

## Pre-Migration Analysis

### Files Identified for Changes

| File | Line(s) | Current Pattern | Required Change |
|------|---------|-----------------|-----------------|
| `backend/schemas/account.py` | 9 | `from pydantic import BaseModel, validator` | Change import to `field_validator` |
| `backend/schemas/account.py` | 24-28 | `@validator("currency")` | Change to `@field_validator` with `@classmethod` |
| `backend/schemas/account.py` | 46-50 | `@validator("currency")` | Change to `@field_validator` with `@classmethod` |
| `backend/schemas/account.py` | 61-62 | `class Config: from_attributes = True` | Change to `model_config = ConfigDict(from_attributes=True)` |
| `backend/schemas/user.py` | 43-44 | `class Config: orm_mode = True` | Change to `model_config = ConfigDict(from_attributes=True)` |
| `backend/schemas/transaction.py` | 251-252 | `class Config: from_attributes = True` | Change to `model_config = ConfigDict(from_attributes=True)` |
| `backend/schemas/transaction.py` | 287-288 | `class Config: from_attributes = True` | Change to `model_config = ConfigDict(from_attributes=True)` |
| `backend/schemas/transaction.py` | 347-348 | `class Config: from_attributes = True` | Change to `model_config = ConfigDict(from_attributes=True)` |
| `backend/schemas/transaction.py` | 398-399 | `class Config: from_attributes = True` | Change to `model_config = ConfigDict(from_attributes=True)` |

### Additional Files Found During Migration

The router file was discovered during codebase scanning:

| File | Line(s) | Current Pattern | Required Change |
|------|---------|-----------------|-----------------|
| `backend/routers/transaction.py` | 56 | `TransactionRead.from_orm(tx)` | Change to `.model_validate(tx)` |
| `backend/routers/transaction.py` | 57 | `pyd_model.dict()` | Change to `.model_dump()` |
| `backend/routers/transaction.py` | 117 | `tx.dict()` | Change to `.model_dump()` |
| `backend/routers/transaction.py` | 133 | `tx.dict(exclude_unset=True)` | Change to `.model_dump(exclude_unset=True)` |

### Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Validator behavior differences | Low | V2 `@field_validator` has same default behavior; simple value checks work identically |
| ORM mode compatibility | Low | `from_attributes=True` is just a rename of `orm_mode` |
| Missing `@classmethod` decorator | Self-catching | Causes immediate runtime error, caught by tests |
| Secondary usages elsewhere | Medium | Full codebase scan performed; router file changes caught |

---

## Test Commands

```bash
# Pre-commit tests (17 tests)
./scripts/pre-commit.sh

# Pytest suite (84 tests)
python3 -m pytest backend/tests/test_*.py -v

# Check for Pydantic deprecation warnings
python3 -m pytest backend/tests/test_*.py 2>&1 | grep -i "pydantic.*deprecated"
```
