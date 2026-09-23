# CLAUDE.md - AI Assistant Context File

> This file provides context for AI assistants (Claude, etc.) working on this project.
> It should be updated after significant changes to maintain continuity across sessions.

**Last Updated:** 2026-06-10

---

## IMPORTANT: Check Current Branch First

**At the start of every new session, check what branch you're on and what work is in progress:**

```bash
git branch          # See current branch
git status          # See uncommitted changes
git log -3 --oneline  # See recent commits
```

### Branch Workflow

| Branch | Purpose | When to Use |
|--------|---------|-------------|
| `develop` | Stable development | Normal bug fixes, small changes |
| `feature/*` | Major changes | Risky/complex work (e.g., `feature/2025-forms`) |
| `master` | Production releases | Only merge from develop when stable |

### Active Feature Branches

| Branch | Purpose | Status |
|--------|---------|--------|
| `feature/buy-from-bank` | Allow Buy transactions from Bank account | Ready to merge |
| `feature/macos-desktop` | macOS desktop app (PyInstaller + pywebview) | In progress |

(`feature/river-import` was merged, released in v0.7.0, and deleted — see [docs/RIVER_IMPORT_PLAN.md](docs/RIVER_IMPORT_PLAN.md) for the design and phase status.)

See [docs/MACOS_DESKTOP_APP.md](docs/MACOS_DESKTOP_APP.md) for complete desktop build documentation.
See [docs/BUY_FROM_BANK_FEATURE.md](docs/BUY_FROM_BANK_FEATURE.md) for Buy from Bank feature details.

### Rollback Tags

| Tag | Branch | Purpose |
|-----|--------|---------|
| `pre-bank-buy` | develop | Rollback point before buy-from-bank merge |
| `pre-bank-buy-master` | master | Rollback point before buy-from-bank release |

To rollback: `git reset --hard <tag> && git push --force origin <branch>`

### Feature Branch Rules

1. **Create feature branch for major work:**
   ```bash
   git checkout develop
   git checkout -b feature/my-feature
   ```

2. **When feature is complete and tested:**
   ```bash
   git checkout develop
   git merge feature/my-feature
   git branch -d feature/my-feature  # Delete local
   git push origin --delete feature/my-feature  # Delete remote
   ```

3. **Keep feature branch updated with develop:**
   ```bash
   git checkout feature/my-feature
   git merge develop  # Pull in any bug fixes from develop
   ```

- Never commit directly to `master`
- Use feature branches for major/risky changes

---

## Key Architectural Decisions

### Multi-Year IRS Form Support

**Decision:** The app maintains all historical IRS form templates in a year-based folder structure. This allows users to generate reports for any supported tax year without needing old app versions.

```
backend/assets/irs_templates/
├── 2024/
│   ├── f8949.pdf
│   └── f1040sd.pdf
├── 2025/
│   └── ...
```

**Rationale:**
- Users may need to file amended/late returns for prior years
- Single codebase is simpler than maintaining multiple app versions
- New tax year = add folder + update field mappings if changed

**Versioning:** Bump minor version when adding new tax year forms (e.g., v0.3.0 for 2025 forms).

See [docs/IRS_FORM_GENERATION.md](docs/IRS_FORM_GENERATION.md) for how the pipeline works, and [docs/IRS_ANNUAL_FORM_UPDATE.md](docs/IRS_ANNUAL_FORM_UPDATE.md) for the **annual update runbook** (follow it step-by-step when adding a new tax year).

---

## Project Overview

BitcoinTX is a self-hosted Bitcoin portfolio tracker with IRS tax form generation capabilities.

### Architecture

```
Single Docker Container
├── Backend: FastAPI (Python 3.11) on Uvicorn
│   ├── API endpoints at /api/*
│   ├── SQLite database at /data/btctx.db
│   └── PDF generation with pdftk
└── Frontend: React/Vite (static files served at /*)
```

### Core Data Model

```
Transaction (user input)
    ↓ creates
LedgerEntry (double-entry: debit + credit)
    ↓ for BTC acquisitions, creates
BitcoinLot (cost basis tracking)
    ↓ when BTC is sold/spent, creates
LotDisposal (FIFO consumption record)
```

### Key Files

| File | Purpose |
|------|---------|
| `backend/main.py` | FastAPI app entry point, mounts routers |
| `backend/database.py` | SQLite setup, `get_db()` dependency |
| `backend/models/` | SQLAlchemy models (Transaction, LedgerEntry, BitcoinLot, etc.) |
| `backend/services/transaction.py` | Transaction processing, FIFO logic |
| `backend/services/bitcoin.py` | BTC price fetching (CoinGecko, Kraken, CoinDesk) |
| `backend/routers/reports.py` | PDF report generation endpoints |
| `backend/services/reports/form_8949.py` | IRS Form 8949 data preparation |
| `backend/services/reports/pdftk_path.py` | Centralized pdftk path resolution (macOS desktop compat) |
| `backend/tests/conftest.py` | Shared test fixtures (isolated TestClient + temp DB) |
| `backend/services/entry_import.py` | JSON entry import: validate, FMV autofill, dedup, dry-run simulation |
| `mcp_server/btctx_mcp/server.py` | MCP server for AI-assisted transaction entry (see `mcp_server/README.md`) |
| `scripts/backup-db.sh` | Daily SQLite backup with 60-day retention |
| `Dockerfile` | Multi-stage build (Node for frontend, Python for backend) |

---

## Current State

### What's Working
- All transaction types (Deposit, Withdraw, Transfer, Buy, Sell)
- Double-entry ledger with proper debit/credit
- FIFO cost basis tracking
- IRS Form 8949 + Schedule D generation (pdftk)
- Complete tax report (ReportLab)
- Transaction history export (CSV/PDF)
- **River CSV import** (merge into live ledger with dedup) - see [docs/RIVER_IMPORT_PLAN.md](docs/RIVER_IMPORT_PLAN.md)
- Docker deployment on port 80
- BTC price fetching with 3-source fallback
- **macOS desktop app** (PyInstaller + pywebview) - see [docs/MACOS_DESKTOP_APP.md](docs/MACOS_DESKTOP_APP.md)

### Docker Image
- **Registry:** Docker Hub
- **Image:** `b1ackswan/btctx:latest`
- **Port:** 80
- **Data Volume:** `/data` (SQLite database)
- **Architectures:** `linux/amd64`, `linux/arm64` (multi-arch)

> **CRITICAL:** Before modifying ANY code that touches database paths, file storage, or environment variables, you MUST read [docs/STARTOS_COMPATIBILITY.md](docs/STARTOS_COMPATIBILITY.md). This document explains how data persistence works in Docker/StartOS containers and documents past bugs caused by hardcoded paths.

### Git State
- **Primary Repo:** BitcoinTX-org/BTCTX (origin)
- **Backup Repo:** PlebRick/BTCTX (plebrick remote)
- **Branches:** `master` (production), `develop` (active work)

---

## Git Workflow & Versioning

### Remotes
| Remote | Repo | Purpose |
|--------|------|---------|
| `origin` | BitcoinTX-org/BTCTX-org | Organization repo |
| `plebrick` | PlebRick/BTCTX | Personal backup repo |

**IMPORTANT: Keep Both Repos in Perfect Sync**

These two repos must always be identical. When releasing:
1. Push branches to BOTH remotes: `git push origin <branch> && git push plebrick <branch>`
2. Push tags to BOTH remotes: `git push origin --tags && git push plebrick --tags`
3. Create GitHub releases on BOTH repos with identical content
4. Upload release assets (DMG, etc.) to BOTH repos

```bash
# Release checklist:
git push origin master --tags && git push plebrick master --tags
gh release create vX.Y.Z --repo BitcoinTX-org/BTCTX-org --title "..." --notes "..."
gh release create vX.Y.Z --repo PlebRick/BTCTX --title "..." --notes "..."
gh release upload vX.Y.Z asset.dmg --repo BitcoinTX-org/BTCTX-org
gh release upload vX.Y.Z asset.dmg --repo PlebRick/BTCTX
./scripts/release-docker.sh vX.Y.Z   # Docker Hub push (enforces StartOS wrapper tag contract)
```

**Docker tag contract (StartOS wrapper dependency):** Every release must push
`b1ackswan/btctx:vX.Y.Z` (exact `^v[0-9]+\.[0-9]+\.[0-9]+$`, no -rc/-beta) as a
multi-arch (amd64+arm64) manifest. Version tags are immutable — never re-push
different bytes under an existing tag; cut a new patch version instead. `:latest`
is convenience only and must never be the only tag. The wrapper
(PlebRick/BTCTX-StartOS) pins the version tag in its manifest and auto-detects
new releases from Docker Hub. Use `scripts/release-docker.sh`, which enforces
all of this. Full details: [docs/STARTOS_COMPATIBILITY.md](docs/STARTOS_COMPATIBILITY.md).

### Branches
- `develop` - Active development, push here regularly
- `master` - Production-ready code, merge from develop when stable

### Tags & Releases
Use semantic versioning: `vMAJOR.MINOR.PATCH`
- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes

```bash
# Create a release
git checkout master
git merge develop
git tag -a v1.0.0 -m "Release v1.0.0: Description"
git push origin master --tags
git push plebrick master --tags  # Sync backup at releases
```

### Current Version
- **Latest Tag:** `v0.7.0` (2026-06-10)
- **Status:** River CSV import release (merge-with-dedup importer, preview UI, FMV autofill; 184 tests)
- **Docker Image:** `b1ackswan/btctx:v0.7.0` and `latest` on Docker Hub (multi-arch: amd64 + arm64)
- **Target Release:** `v1.0.0`

---

## Recent Changes

### Session: 2026-09-23 (MCP server — branch `claude/zealous-wright-nk7vol`)
1. **MCP server** `mcp_server/` (package `btctx-mcp`, mcp SDK 2.x `MCPServer`, stdio): AI assistants add transactions from pasted text / plain English
   - REST client only (never touches the DB); logs in with username/password because import endpoints are deliberately session-only (API-key clients stay locked out)
   - Tools: get_ledger_guide, preview_transactions, add_transactions, list_transactions, update_transaction, delete_transaction, get_portfolio, get_btc_price. No bulk delete, by design
   - `btctx_mcp/guide.py` is the domain prompt (account mapping, per-type fields, workflow); it's sent as the server instructions and returned by a tool
2. **Backend**: `routers/entry_import.py` + `services/entry_import.py` + `schemas/entry_import.py` → `POST /api/import/entries/{preview,execute}`
   - Reuses `csv_import._validate_row`, `river_import.annotate_duplicates`, `create_transaction_record`
   - Preview = real create path in the request session, then `db.rollback()` (calls `ensure_fee_account_exists` first because it can commit)
3. **Proceeds anchored on `gross_proceeds_usd`** (`transaction.py`: `_record_gross_proceeds`, `_withdrawal_gross_proceeds`, Sell legacy branch in `build_ledger_entries_for_transaction`): stored `proceeds_usd` is NET; recalcs must derive net from the gross, never from proceeds_usd. Create + proceeds edits record gross; legacy rows (gross NULL) recover it once. Spent withdrawals with no proceeds → day's FMV, stored. Tests: `test_disposal_proceeds.py`
4. **Transfer fee semantics unified**: `amount` = what left the source, fee included (UI "amount sent"; ledger already did this). `maybe_transfer_bitcoin_lot` no longer adds the fee on top. River proposals keep River's net amounts; `river_import.ledger_amount()` converts Transfers at execute + dedup. Withdrawals keep fee ON TOP (unchanged). Tests: `test_transfer_fees.py`
5. Tests: `backend/tests/test_entry_import.py` (20), `mcp_server/tests/test_server.py` (9, end-to-end MCP client → server → ASGI app)

### Session: 2026-06-10 (River CSV Import — branch `feature/river-import`)
1. **River bitcoin-activity CSV import** (Phases 1–2 of docs/RIVER_IMPORT_PLAN.md)
   - Backend: `services/river_import.py` (adapter + dedup engine), `routers/river_import.py` (`/api/import/river/preview` + `/execute`), `schemas/river_import.py`
   - Frontend: `components/RiverImport.tsx` + `styles/riverImport.css`, section on Settings page
   - Merges into a LIVE ledger (no empty-DB requirement); dedup = exact BTC amount + compatible type ±48h, fuzzy ±20% pass flags transfer near-matches for review; idempotent re-imports
   - Buy funding (Bank vs Exchange USD) is a per-row preview toggle — owner decision: funding is a human choice per purchase, do NOT build predictors; heuristic defaults are best-effort from file recurrence (weak on small files — expected)
   - FMV basis autofill on Interest/Income deposits via existing `get_historical_price`
   - 20 new tests (synthetic fixtures), suite now 184; validated against real 1,197-row export (100% coverage); real import reconciled to River balance to the satoshi
   - **User data privacy:** real CSV exports live locally in `docs/*.csv` — gitignored (generic pattern, no filenames leaked); NEVER commit or reference their contents in code/tests/docs
2. **Annual IRS form update runbook**: `docs/IRS_ANNUAL_FORM_UPDATE.md` (committed on develop) — follow it step-by-step each year; replaced stale section in IRS_FORM_GENERATION.md
3. Phase 3 (account-activity CSV) DROPPED by owner decision — USD cash deposits stay manual (~3 trivial entries/month, not worth a second adapter); do not revive unless asked
4. **Released as v0.7.0 same day**: merged to master, tagged, pushed to BOTH repos, GitHub releases with `BitcoinTX-0.7.0.dmg` on both, Docker Hub `b1ackswan/btctx:v0.7.0` + `latest` (multi-arch, wrapper contract verified via release-docker.sh)
5. Cleanup: real CSV samples deleted from docs/ after validation; `docs/*.csv` gitignore rule retained for future samples; VS Code interpreter fixed (stale conda path → desktop/.venv, was breaking Pylance import resolution)

### Session: 2026-06-09/10 (2026 Modernization — branch `feature/2026-modernization`)
1. **Conservative dependency pass** (CVE-driven; React 18 / Vite 6 / pydantic 2.12 retained)
   - Backend: fastapi 0.121.3, starlette pinned 0.49.3, cryptography 46.0.7, pypdf 6.13.1, python-multipart 0.0.32, reportlab 4.4.10 (NOT 4.5.x — PDF drift risk), others patch/minor
   - Frontend: vite 6.4.3, axios 1.17.0, react-router-dom 7.17.0, TS 5.9.3; `npm audit` = 0 vulnerabilities
   - Deferred majors + unblock conditions documented in `docs/MAINTENANCE.md` ("Deferred Updates")
2. **2025 IRS forms verified and fixed** (⚠ requires minor version bump at release → v0.6.0)
   - Bundled 2025 templates MD5-identical to final irs.gov releases
   - Fixed: 2025 form holds 11 rows/page (was chunked by 14 → silent row loss); fixed multi-page handling (short→Part I, long→Part II on shared sheets; continuous f3_+ page numbering wrote to nonexistent fields)
   - New `backend/tests/test_2025_forms.py` (6 tests); **suite now 164 tests**
3. **Backend quality pass** (behavior-preserving): dead code removed, duplication consolidated, N+1s fixed in transaction-history report + account balances, module loggers
4. **UI polish** (CSS-only, dark theme): design tokens (easing/tracking/shadows), tabular numerals on figures, active-nav underline, panel slide-in, reduced-motion support; browser-verified at 1440/800/768/480px
5. **PDF safety net**: `baseline-pdfs/regen_and_diff.sh` regenerates the three reports from a frozen seed and text-diffs vs committed baselines (PASS after every phase)
6. **Test environment notes**: venv is `desktop/.venv` (Python 3.11); run pytest with `--ignore=backend/tests/test_requests.py --ignore=backend/tests/test_transactions.py` (stale live-server scripts); 7 auth tests still need a live backend on :8000 (start one with a temp `DATABASE_FILE`); pre-commit API section deliberately disabled (`test_backdated_fifo.py` sends delete_all to :8000 — production-wipe hazard)

### Session: 2026-02-14 (Test Isolation & Backups)
1. **Test Suite Isolated from Production Database**
   - Root cause: tests used `requests.Session` hitting live backend at `localhost:8000`, and `delete_all_transactions()` wiped production data
   - Converted all 6 test files to use FastAPI `TestClient` with `app.dependency_overrides[get_db]`
   - Tests now use a temporary SQLite database created fresh per pytest session
   - No running backend required — `TestClient` runs the app in-process
   - Fixed httpx API difference: `r.ok` (requests) → `r.is_success` (httpx/TestClient)
   - Files modified: `conftest.py`, `test_stress_and_forms.py`, `test_pdf_content.py`, `test_comprehensive_transactions.py`, `test_everything.py`, `test_seed_data_integrity.py`
   - All 158 tests pass against isolated temp DB

2. **Daily Database Backup**
   - Added `scripts/backup-db.sh` — uses `sqlite3 .backup` for safe online copy (handles WAL mode)
   - Cron job runs daily at 3 AM CT
   - Backups stored in `backups/btctx_YYYY-MM-DD.db` (gitignored)
   - Auto-prunes backups older than 60 days
   - Logs to `backups/backup.log`

### Session: 2025-01-17 (PDF Content Tests)
1. **PDF Content Verification Test Suite**
   - Added `backend/tests/test_pdf_content.py` with 23 new tests
   - Uses `pypdf` to extract and verify actual PDF content (not just file generation)
   - Tests: Complete Tax Report, IRS Forms, Transaction History, edge cases, data accuracy
   - Fixed `test_seed_data_integrity.py` to be self-contained with auto-seeding fixture
   - Total pytest tests: 158

### Session: 2025-01-17 (Transaction Edit Bug Fix)
1. **Fixed Transaction Editing in macOS Desktop App**
   - Bug: Editing transactions failed with "Not enough BTC" error
   - Root cause: `update_transaction_record()` had flawed lot logic when backdating
   - The partial re-lot (`recalculate_subsequent_transactions`) ran before full scorched earth, using stale lot balances
   - Fix: Simplified update flow to use only full scorched earth (`recalculate_all_transactions`)
   - Also fixes potential edge cases in Docker deployments with specific transaction histories
   - Documentation: `docs/edit-tx-bug-mac.md` (full investigation details)

2. **Improved Transaction Form**
   - Added PUT response validation (defensive programming)
   - Edit transactions now show realized gain in success toast (feature parity with create)

3. **Release v0.5.5**
   - Tagged and pushed to both repos (origin, plebrick)
   - GitHub releases created with DMG on both repos
   - Docker image pushed: `b1ackswan/btctx:v0.5.5` and `latest`

### Session: 2025-01-17 (Testing & Cleanup)
1. **Comprehensive Test Suite**
   - Added `backend/tests/test_stress_and_forms.py` with 46 new pytest tests
   - Volume/stress testing (250+ transactions, backdating cascades)
   - Edge cases (holding periods 364/365/366 days, satoshi precision, $100M amounts)
   - Account-specific FIFO verification
   - All deposit sources (MyBTC, Gift, Income, Interest, Reward)
   - All withdrawal purposes (Spent, Gift, Donation, Lost)
   - IRS Form 8949 validation (multi-page, non-taxable exclusions)
   - Schedule D totals verification
   - Total pytest tests now: 158 (was 84)

2. **pdftk Path Resolution Fix**
   - Added `backend/services/reports/pdftk_path.py` for centralized path resolution
   - Checks known Homebrew locations for PyInstaller bundles
   - Fixes pdftk not found in macOS desktop app (bundles don't inherit PATH)
   - Updated `pdf_utils.py`, `pdftk_filler.py`, `reports.py` to use new module

3. **Reports Page Desktop Download Fix**
   - Updated `frontend/src/pages/Reports.tsx` to use desktop-aware download utility
   - Added PyWebView API TypeScript types to `frontend/src/types/global.d.ts`

4. **Codebase Cleanup**
   - Deleted 7 duplicate files (`* 2.*` pattern from macOS copy conflicts)
   - Deleted temporary `cookies.txt` file

### Session: 2025-01-17 (macOS Desktop App)
1. **macOS Desktop App Build**
   - Added complete PyInstaller + pywebview setup for native macOS app
   - Files added: `desktop/entrypoint.py`, `desktop/BitcoinTX.spec`, `desktop/build-mac.sh`, `desktop/requirements.txt`, `desktop/README.md`
   - Modified `backend/main.py` to support `BTCTX_FRONTEND_DIST` env var for bundled frontend path
   - App bundles entire backend + frontend into single ~61MB `.app`
   - Data stored in `~/Library/Application Support/BitcoinTX/btctx.db`
   - See [docs/MACOS_DESKTOP_APP.md](docs/MACOS_DESKTOP_APP.md) for complete documentation

2. **Desktop App Downloads Fix**
   - Fixed Settings page downloads (backup, CSV export, templates) not working in desktop app
   - Added `frontend/src/utils/desktopDownload.ts` utility that detects pywebview environment
   - Uses native file save dialog via `window.pywebview.api.save_file()` in desktop app
   - Falls back to standard browser download for web/Docker deployment
   - Updated `desktop/entrypoint.py` to expose `save_file` API to JavaScript

3. **Lint Fixes**
   - Removed unused `err` variables in catch blocks in `useBtcPrice.ts`
   - Removed unused `dbStatus` variable in `Settings.tsx` (only setter was used)

### Session: 2025-01-17 (Mobile/UI)
1. **Mobile Responsiveness Overhaul**
   - Comprehensive mobile UI fixes across 10 CSS files (330+ lines added)
   - Fixed transaction panel: responsive width (was fixed 500px), overlay positioning bug
   - Fixed login card: fluid width instead of fixed 400px
   - Added `:active` states for touch feedback on all interactive elements
   - Added mobile labels to transaction list at 800px breakpoint using `::before` pseudo-elements
   - Added 480px breakpoint for extra small screens across all pages
   - Improved navigation layout with CSS grid on mobile (3-col at 768px, 2-col at 480px)
   - Ensured 44px minimum touch targets on all buttons and inputs
   - Added mobile font size scale to `theme.css`
   - Files modified: `app.css`, `converter.css`, `dashboard.css`, `login.css`, `reports.css`, `settings.css`, `theme.css`, `transactionForm.css`, `transactionPanel.css`, `transactions.css`

2. **UI Refinements**
   - Sidebar brand: changed from horizontal to vertical stack (logo above title)
   - Reduced spacing between brand and Sats Converter
   - Removed lock emoji from logout button
   - Fixed logout font rendering on macOS dark backgrounds (dark red #811922 → brighter red #cf4655)

3. **Release v0.5.2**
   - Tagged and pushed to both repos (origin, plebrick)
   - Built and pushed multi-arch Docker image

### Session: 2025-01-16
1. **CSV Template Fix**
   - Fixed broken template that had incorrect balance math (withdrawals exceeded deposits)
   - New template has 18 transactions (was 7) with verified balance math
   - Includes all transaction types: Deposit, Withdrawal, Transfer, Buy, Sell
   - Includes all deposit sources: MyBTC, Gift, Income, Interest, Reward
   - Includes all withdrawal purposes: Spent, Gift, Donation, Lost
   - File: `backend/services/csv_import.py`

2. **CSV Import Ordering Fix**
   - Added same-timestamp sorting: acquisitions (Deposit, Buy) process before disposals (Sell, Withdrawal)
   - Fixes edge case where same-timestamp transactions could fail due to ordering
   - File: `backend/services/csv_import.py`

3. **CSV Export Ordering Fix**
   - Added deterministic ordering by ID for same-timestamp transactions
   - Ensures consistent export order across runs
   - File: `backend/routers/backup.py`

4. **Docker Image Update**
   - Rebuilt with `--no-cache` and pushed to Docker Hub
   - Tags: `b1ackswan/btctx:v0.5.1`, `b1ackswan/btctx:latest`

### Session: 2025-01-15
1. **FIFO Lot Disposal Fix**
   - Made FIFO disposal account-specific (was consuming lots from all accounts globally)
   - File: `backend/services/transaction.py`

2. **Test Fixes**
   - Fixed 5 stale tests to match current codebase
   - All tests pass
   - Files: `test_backend.py`, `test_main.py`, `test_seed_data_integrity.py`

3. **SPA Routing Fix (Docker)**
   - Fixed browser refresh returning 404 JSON on client-side routes (`/dashboard`, `/transactions`, etc.)
   - Root cause: `StaticFiles(html=True)` does NOT provide SPA fallback for arbitrary paths
   - Solution: Added `spa_fallback_handler` exception handler to serve `index.html` for non-API 404s
   - API routes still return proper JSON errors (`{"detail":"Not Found"}`)
   - File: `backend/main.py`

4. **UI Fixes**
   - Fixed Toast close button not rendering (Unicode escape issue)
   - Updated application logo (`logo.svg`, `icon.svg`)
   - Removed unused `bitcoin-logo.png`

4. **Release v0.5.1**
   - Tagged and pushed to both repos (origin, plebrick)
   - Built and pushed multi-arch Docker image

### Session: 2025-01-10
1. **Python 3.9 Compatibility**
   - Added `from __future__ import annotations` to `transaction.py` and `user.py`
   - Fixes union type syntax (`datetime | None` → works on Python 3.9)

2. **PDF Path Fixes**
   - Changed relative paths to absolute paths using `__file__`
   - Added pre-flight checks (`_verify_pdftk_installed()`, `_verify_templates_exist()`)
   - File: `backend/routers/reports.py`

3. **Docker BTC Price Fix**
   - Changed `get_btc_price()` from HTTP calls to direct service calls
   - Was calling `localhost:8000` but Docker runs on port 80
   - File: `backend/services/transaction.py`

4. **Repository Cleanup**
   - Deleted 63 stale branches across repos
   - Established master/develop workflow

---

## Known Issues & Future Work

### Deferred Items
- [x] ~~Edge cases in FIFO calculations~~ (covered by pre-commit tests)
- [x] ~~Review PDF calculations for accuracy~~ (verified, fixed Form 8949 non-taxable exclusion)
- [x] ~~2025 IRS form template updates~~ (verified final + capacity/multi-page fixes, June 2026)

### Planned Features
- [ ] Multi-user support (optional)
- [x] ~~CSV import merge with existing data (Phase 2)~~ shipped for River in v0.7.0

### Completed Recently
- [x] River CSV import (Jun 2026, v0.7.0) - merge-with-dedup importer, editable preview UI, FMV autofill; reconciled to River balance to the satoshi on real data; 184 tests
- [x] 2026 modernization (Jun 2026) - CVE-driven dep refresh, 2025 form fixes, backend cleanup, UI polish, 164 tests
- [x] Test isolation from production DB (Feb 2026) - TestClient + temp DB, no live backend needed
- [x] Daily database backups (Feb 2026) - `scripts/backup-db.sh`, cron at 3 AM, 60-day retention
- [x] Comprehensive test suite (Jan 2025) - 158 pytest tests + 17 pre-commit checks
  - `test_stress_and_forms.py`: stress testing, edge cases, IRS form validation
  - `test_pdf_content.py`: PDF content verification using pypdf text extraction
  - All deposit sources and withdrawal purposes tested
  - Account-specific FIFO verification
- [x] macOS desktop app (Jan 2025) - PyInstaller + pywebview bundling
- [x] Mobile responsiveness overhaul (Jan 2025)
  - 10 CSS files updated with responsive breakpoints
  - Touch-friendly UI with 44px minimum targets
  - Mobile labels on transaction list
  - CSS grid navigation on mobile
- [x] Frontend design system refactor (Jan 2025)
  - Custom hooks: `useAccounts`, `useApiCall`, `useBtcPrice`
  - Toast notification system with context
  - Error boundaries for graceful error handling
  - Centralized theme system (`theme.css`)
- [x] CSV template import feature (v0.4.0)
- [x] Atomic bulk import with rollback
- [x] Pre-commit test suite (17 tests)
- [x] Fixed Form 8949 to exclude Gift/Donation/Lost disposals

---

## Development Notes

### Running Locally
```bash
# Backend
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000

# Frontend (dev mode)
cd frontend && npm run dev

# Frontend (production build)
cd frontend && npm run build
# Then backend serves static files from frontend/dist
```

### Running in Docker
```bash
# Local single-arch build
docker build -t btctx .
docker run -p 80:80 -v btctx-data:/data btctx

# Multi-arch release build for production (required for StartOS compatibility;
# always use the script — it enforces the wrapper's pinned-version-tag contract)
./scripts/release-docker.sh vX.Y.Z
```

> See [docs/STARTOS_COMPATIBILITY.md](docs/STARTOS_COMPATIBILITY.md) for full multi-arch build requirements.

### Testing — see docs/TESTING.md (current source of truth)
`make hooks` once; `make test-fast` / `make smoke` / `make check`. Suite is hermetic
(conftest stubs BTC prices session-wide; no live server needed — the old
TestAuthEndpoints live-server tests now use TestClient). CI: .github/workflows/ci.yml.
The notes below predate this and are kept for history.

### Pytest Suite (IMPORTANT)

**Tests are fully isolated** — they use FastAPI `TestClient` with a temporary SQLite database via `app.dependency_overrides[get_db]`. No running backend required, and the production database is never touched.

```bash
# Run all 164 tests from the repo root (venv lives at desktop/.venv)
# Note: 7 TestAuthEndpoints tests need a live backend on :8000 — start one
# against a TEMP database first (never the production DB):
#   DATABASE_FILE=/tmp/btctx-test.db PYTHONPATH=$(pwd) \
#     desktop/.venv/bin/uvicorn backend.main:app --port 8000 &
PYTHONPATH=$(pwd) desktop/.venv/bin/pytest backend/tests/ \
  --ignore=backend/tests/test_requests.py \
  --ignore=backend/tests/test_transactions.py \
  -v --tb=short

# Run a specific test file
PYTHONPATH=$(pwd) desktop/.venv/bin/pytest backend/tests/test_comprehensive_transactions.py -v
```

**Test architecture:**
- `conftest.py` creates a temp SQLite DB, seeds admin user + 6 accounts
- `auth_client` fixture provides an authenticated `TestClient`
- `test_db` fixture provides direct SQLAlchemy session access
- All fixtures are session-scoped (shared across test module)

### Pre-Commit Testing

```bash
# Full pre-commit suite (starts backend if needed)
./scripts/pre-commit.sh

# Quick mode (skip long-running tests)
./scripts/pre-commit.sh --quick

# Static checks only (no backend needed)
python3 backend/tests/pre_commit_tests.py --no-api
```

**What it tests:** (static checks only — the API section is currently disabled;
`check_backend_running` can't succeed against auth-protected routes, and enabling it
would run a destructive legacy script against :8000. See ROADMAP housekeeping item.)
- Docker/StartOS compatibility (no hardcoded paths, DATABASE_FILE env var, Python 3.9)
- Transaction/FIFO integrity (scorched earth recalculation, backdated transactions)
- Report generation (Form 8949, Schedule D, non-taxable exclusions)
- CSV import/export roundtrip

**Critical files that REQUIRE pre-commit tests after changes:**
- `backend/services/transaction.py` - FIFO logic, lot disposal
- `backend/services/reports/form_8949.py` - Tax form generation
- `backend/database.py` - Database paths
- `backend/services/backup.py` - Backup/restore paths
- Any file touching file paths or environment variables

### Testing Reports
```bash
# Complete tax report
curl "http://localhost:8000/api/reports/complete_tax_report?year=2024" -o report.pdf

# IRS forms (requires pdftk)
curl "http://localhost:8000/api/reports/irs_reports?year=2024" -o irs.pdf

# Transaction history
curl "http://localhost:8000/api/reports/simple_transaction_history?year=2024&format=csv" -o history.csv
```

### Key Dependencies
- `pdftk` - Required for IRS form filling (install via brew/apt)
- `pypdf` - PDF merging
- `reportlab` - PDF generation from scratch
- `httpx` - Async HTTP for price APIs

---

## Handoff Checklist

When starting a new session, the AI should:
1. Read this file first (`CLAUDE.md` - auto-detected in root)
2. Check `docs/CHANGELOG.md` for recent changes
3. Check `docs/ROADMAP.md` for current goals
4. **Before any database/storage/Docker changes:** Review `docs/STARTOS_COMPATIBILITY.md` - this is CRITICAL for understanding how data persistence works
5. **Before updating dependencies:** Review `docs/MAINTENANCE.md` for safe update procedures and known issues
6. **Before any macOS desktop app changes:** Review `docs/MACOS_DESKTOP_APP.md` for build system, architecture, and bundling details
7. Run `git status` to see uncommitted changes
8. Run `git log -5 --oneline` to see recent commits

When ending a session:
1. **Run pre-commit tests:** `./scripts/pre-commit.sh` (or `--no-api` for quick check)
2. Update this file with any significant changes
3. Add entries to CHANGELOG.md
4. Update ROADMAP.md if goals changed
5. If dependencies were updated, update `docs/MAINTENANCE.md` with any new deprecation warnings
6. Commit changes if appropriate
