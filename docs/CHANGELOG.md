# Changelog

All notable changes to BitcoinTX are documented in this file.

## [Unreleased]

### Added
- Frontend unit tests (Vitest) for the transaction form's mapping to and
  from the API, run by the pre-push hook and CI. The mapping moved to
  `frontend/src/utils/transactionForm.ts`.

### Changed
- The complete tax report no longer rebuilds the ledger inside the request
  to take its start- and end-of-year snapshots (33 writes for a small ledger,
  holding the database write lock, then discarded). The snapshots replay on
  an in-memory copy of the database; the report writes nothing.

## [v0.8.0] - 2026-09-23 - MCP server, schema migrations, tax fixes

### Distribution
- Multi-arch (amd64 + arm64) Docker image published to
  `ghcr.io/digimonk73/btctx-mcp` on every push to main; `:v0.8.0` is fixed.
  The StartOS package (DigiMonk73/BTCTX-StartOS v0.8.0:0) runs this image.
- Tax year 2026: the IRS draft Form 8949 and Schedule D were checked against
  the app (`scripts/irs_new_year.py --draft`, run weekly in CI): identical
  field layout to 2025, every field the app fills exists, box order matches.

### Added — MCP server (AI-assisted entry)
- **`mcp_server/`**: an MCP server (`btctx-mcp`) that lets an AI assistant
  (Claude Desktop, Claude Code, any MCP client) add transactions from pasted
  text or plain English: exchange emails, wallet history, explorer pages. Tools:
  guide, preview, add, list, update, delete (single), portfolio, BTC price.
  Runs locally over stdio and logs in to BitcoinTX with the user's credentials.
  See `mcp_server/README.md`.
- **JSON entry import API** (session-auth only):
  `POST /api/import/entries/preview` and `POST /api/import/entries/execute`.
  - Preview validates with the CSV importer's rules, dedups against the ledger
    with the River engine (exact → skipped, near-match → flagged), auto-fills
    FMV-derived USD values (Income/Interest/Reward basis, Spent proceeds,
    Gift/Donation FMV), then **dry-runs the real create path and rolls it
    back**: returns simulated realized gain/holding period per row, rejected
    rows (e.g. not enough BTC), balances afterward, and existing sales whose
    gains change due to backdating.
  - Execute is atomic with the same exact-duplicate guard and returns the
    created transaction ids.
- **`POST /api/transactions/recalculate`** (and MCP tool `recalculate_ledger`):
  rebuild all lots, disposals and gains from the transactions. **Run once after
  upgrading** so the fixes below reach existing data.
- New tests: `test_entry_import.py` (20), `test_transfer_fees.py` (5),
  `test_disposal_proceeds.py` (11), and 10 MCP end-to-end tests
  (`mcp_server/tests/`).

### IRS forms: yearly update tooling
- `scripts/irs_new_year.py YYYY`: downloads the final forms, rejects drafts and
  wrong-year PDFs, verifies field names and box order, diffs against the prior
  year, installs, and runs the template tests.
- A new year folder fails tests until its config is explicitly verified
  (`verified_years`), so it can't silently inherit last year's layout.
- `IRS forms watch` workflow checks irs.gov weekly Nov–Mar for new final forms.

### macOS desktop app
- Listens on a fixed local port, `http://127.0.0.1:8765` (override with
  `BTCTX_DESKTOP_PORT`; falls back to a random port if taken), so the MCP
  server can connect. Still bound to localhost only.
- PyInstaller spec lists the River/entry import modules; bundle version 0.8.0.

### Security (account takeover — upgrade recommended)
- **`/api/users` had no authentication.** Anyone who could reach the app
  could list users, change the password, or delete the account. Changing or
  deleting now requires being logged in as that user. First-run setup and
  re-registration use `POST /api/users/reset-account`, which the server allows
  only while the login is still the shipped `admin`/`password`, or with the
  current password (previously the "override password" was checked only in
  the browser). `GET /api/users/setup-status` is the only public user route.
- **Forgeable login cookies.** Without a `SECRET_KEY` env var (the Docker and
  StartOS default) sessions were signed with `default_secret_key`, published
  in this repo, so anyone could mint a valid login cookie. The macOS app used
  another published key. Now a random key is generated per install and stored
  next to the database (`.btctx_secret_key`, mode 600); an explicit
  `SECRET_KEY` still wins unless it is one of the published values.
  Existing users are logged out once after upgrading.

### Security / dependencies
- fastapi 0.141.1, starlette 1.7.0, pydantic 2.13.5, uvicorn 0.53.0 (starlette CVEs)
- cryptography 50.0.1, pypdf 6.19.0, sqlalchemy 2.0.54, python-dotenv 1.2.3
- axios 1.20.0 (high-severity advisories), react-hook-form, react-router-dom,
  eslint/typescript-eslint patch updates; `npm audit` clean
- Docker frontend build stage: node:18 (EOL) → node:22
- **Python 3.9 is no longer supported** (3.10+; Docker uses 3.11)

### Added — tax timezone
- **Settings → Tax Timezone** (auto-set from your browser on first login;
  `BTCTX_TIMEZONE` env var as a fallback). Tax years, Form 8949 dates,
  holding-period anniversaries, the reports and year-to-date totals now use
  it — a 10 pm Dec 31 sale in New York is no longer counted in the next
  year. Timestamps are still stored in UTC. Changing it recalculates.
- AI/MCP entries without a timezone are read in the tax timezone (a bare date
  means midday that day).

### Fixed — tax report placeholders
- The complete tax report valued year-end BTC at a hardcoded demo price
  ($94,153.13) and reported a hardcoded $4,000 profit in its asset summary.
  It now uses the real Dec 31 price and the year's actual gains/losses, and
  year-end holdings exclude activity after Dec 31.
- The complete tax report dropped transactions in the last second of the year.

### Changed — no more pdftk (Java)
- IRS forms are now filled and flattened in pure Python (pypdf). pdftk is no
  longer needed on macOS (`brew install pdftk-java` step gone), in Docker
  (image drops the Java runtime) or in CI. Output compared page-by-page with
  pdftk: Schedule D pixel-identical, Form 8949 identical except sub-pixel
  text placement in the description column.
- A field name missing from an IRS template now raises an error instead of
  being silently dropped (which produced blank forms).

### Changed — Form 1099-DA boxes (IRS broker reporting, 2025+)
- Exchange (River) sells are now reported in **Box H/K** for 2025 (on a
  1099-DA, basis not reported) and in **Box G/J** from 2026 for lots bought on
  the exchange on/after 2026-01-01 (covered, basis reported). Self-custody
  spends and network fees stay in **I/L**. Each box gets its own Form 8949
  page, and Schedule D now fills lines 1b, 2, 3, 8b, 9 and 10 as applicable
  (previously only 3 and 10).

### Fixed
- **Holding period off by one day.** Anything held 365+ days was long-term,
  so a sale on the one-year anniversary (or on day 365 in a leap year) got the
  long-term rate. IRS rule: long-term only when held MORE than one year —
  disposed after the anniversary date. Two old tests asserted the wrong
  answer and were corrected. Run the recalculation once to update existing
  sales.
- **IRS Form 8949 boxes.** No Part checkbox was ever checked (the IRS requires
  one), and the box letter was written into column (f) "Code(s)", which is for
  adjustment codes. For 2025 the app also used Box C/F, which the 2025 form
  reserves for non-digital assets. Now exactly one box is checked per Part —
  C/F for 2024, **I/L** (digital assets not on a 1099) for 2025+ — and column
  (f) is blank. Verified by filling the real IRS templates and reading every
  field back (`test_irs_templates.py`, runs for every bundled year).
- **BTC Transfer fees counted two ways.** The ledger treated a Transfer's
  `amount` as what left the source (fee included, as the UI's "amount sent"
  field does), but cost-basis lots took `amount + fee` from the source. Lots
  and balances drifted apart by every transfer fee, and sending a whole
  balance failed with "Not enough BTC". Lots now use the ledger/UI convention;
  a fee larger than the amount is rejected with a clear message. River
  imports (whose amounts exclude the fee) are converted at execute and in
  dedup, so re-imports still match. Dashboard balances do not change.
- **Proceeds shrank on every recalculation.** Stored `proceeds_usd` is the
  net value, but Sells from CSV/River/API (no `gross_proceeds_usd`) and every
  Spent withdrawal with a BTC fee re-derived net from that already-net value,
  losing the fee again on each backdated insert, edit or delete. The user's
  gross is now always recorded on create and on proceeds edits, and rows
  saved by older versions recover their gross on the next recalculation, so
  they stop shrinking. (Losses that already happened can't be undone
  automatically — compare old Sells/Spends against exchange records.)
- **River/CSV "Spent" withdrawals without proceeds became fake losses.** They
  were saved with $0 proceeds, realizing the full cost basis as a capital
  loss. They are now valued at the day's BTC price (as the CSV importer's
  warning always claimed), fetched once and stored. Existing rows are
  repaired on the next recalculation. An explicit $0 entered in the form is
  still respected.
- The transaction edit form now loads a withdrawal's gross proceeds, so
  re-saving an edit no longer nets the fee again.
- **Docker data could be lost on update.** The image never set
  `DATABASE_FILE`, so a plain `docker run -v …:/data` kept the database inside
  the container. The image now defaults to `/data/btctx.db`; CI checks the
  database and session key land on the volume. (StartOS was unaffected: its
  wrapper sets the same path.)
- **Form 1099-DA covered-lot cutoff** compared the acquisition time in UTC, so
  a lot bought on the evening of Dec 31, 2025 in the US counted as covered
  (Box G/J) while its printed acquisition date said 12/31/2025. It now uses
  the tax-timezone date.
- **Filled IRS forms were ~5 MB per Form 8949 sheet.** Flattening left the old
  field appearance streams in the file. Output is now ~0.3 MB per sheet and
  renders pixel-identically.
- `.env.example`'s placeholder `SECRET_KEY` was a publicly known value that
  would have been used as-is; it is now rejected like the other public
  defaults, and the example leaves the key unset (auto-generated).

### Added — per-transaction Form 1099-DA override
- A Sell or Spent withdrawal can record what the broker actually reported
  ("Broker form" in the transaction form; `broker_reporting` in the API and
  the MCP `update_transaction` tool): not on a broker form, proceeds only, or
  proceeds and basis. That picks the Form 8949 box for that sale (2025+:
  I/L, H/K, G/J; 2024 and earlier: C/F, B/E, A/D) instead of the default
  rules. Left on Automatic, nothing changes.
- The first real schema migration (0003): existing databases gain the column
  automatically on upgrade.

### Added — schema migrations
- The database schema is now managed by **Alembic migrations**
  (`backend/migrations/`), run automatically at every start. Before this, new
  tables were created on startup but new columns and indexes never reached
  existing databases.
- **Existing databases are adopted automatically**: checked against the v0.7.0
  schema, repaired where that's safe (databases from before Jan 2026 get the
  foreign-key indexes they never received), then upgraded. Verified against a
  database written by the real v0.7.0 code, in tests and in the Docker image.
- **Automatic backup** to a `backups/` folder next to the database before any
  schema change (or restore). Upgrades run in a single transaction: a failure
  leaves the database exactly as it was.
- A database from a newer BitcoinTX is refused with a clear message instead of
  being opened by older code.
- **Restoring an older backup now upgrades it** before it replaces the live
  database. Restores are validated first (wrong password, not a database, or
  from a newer version leave the live data untouched), swapped in atomically,
  and the database being replaced is kept in `backups/`. Encrypted backups are
  now taken with SQLite's backup API (consistent even while the app writes).

### Added
- **Settings → Recalculate Ledger** button (same as the MCP
  `recalculate_ledger` tool) for applying calculation fixes after an upgrade.

### Housekeeping
- Removed legacy scripts that drove a live server (one sent `delete_all` to
  port 8000), superseded IRS field-dump tools, `scripts/pre-commit.sh`,
  `baseline-pdfs/`, `clean_env.py` and the legacy Makefile targets. Finished
  design plans moved to `docs/archive/`.
- Lint: ruff enforces all Pyflakes rules and ESLint runs with zero warnings.
- Tests: two test files used soft assertions that logged failures without
  failing (108 checks); they now fail properly, which exposed one wrong
  holding-period expectation (fixed). Several tests that asserted nothing now
  check what their names claim.
- pytest moved out of `backend/requirements.txt` (it was installed in the
  Docker image) into `requirements-dev.txt`, upgraded to 9.1.1; the dependency
  audit now covers both files with no exceptions.
- Docs rewritten for the current code: README, CLAUDE.md, IRS form
  generation and yearly update, macOS app, StartOS, maintenance, testing.

---

## [v0.7.0] - 2026-06-10 - River CSV Import

### Added — River CSV Import
- **Import from River** (Settings page): upload a River bitcoin-activity CSV
  (river.com → Taxes & Documents) and merge it into a live ledger — unlike the
  onboarding CSV import, no empty-database requirement.
  - Adapter maps every River row pattern: Buy, Sell, Interest/Income (BTC
    interest on the River cash balance), tagged Withdrawals, and untagged
    on-chain sends/receives (default to cold-storage Transfers, flippable to
    Withdrawal/Deposit per row).
  - **Dedup engine**: rows already in the ledger are matched (exact BTC amount,
    compatible type, ±48h) and skipped; near-matches (transfers within ±20%)
    are flagged for review and excluded by default. Re-importing overlapping
    date ranges is safe and idempotent.
  - Buy funding source (Bank vs Exchange USD) defaults from a file-recurrence
    heuristic and is always a one-click toggle in the preview — by design the
    user is the final classifier on every import.
  - Interest/Income deposits get fair-market-value cost basis auto-filled from
    the historical BTC price (3-source failover), marked "est." and editable.
  - Atomic execute: all-or-nothing with server-side re-validation and a
    double-submit guard.
  - New endpoints `POST /api/import/river/preview` and
    `POST /api/import/river/execute` (session-auth only).
- 20 new tests (`backend/tests/test_river_import.py`, synthetic fixtures);
  suite now **184 tests**. Verified against a real 1,197-row River export
  (100% row coverage) and a live import reconciled to River's balance to the
  exact satoshi and cent.
- New runbook `docs/IRS_ANNUAL_FORM_UPDATE.md` for adding each year's IRS form
  templates (official IRS URL patterns, MD5 verification, field-diff procedure,
  per-year config and test checklist). `docs/IRS_FORM_GENERATION.md`'s stale
  update section now points to it.

---

## [v0.6.0] - 2026-06-10 - 2026 Modernization

### 2026 Modernization (June 2026)

#### Security / Dependencies (conservative pass: React 18 + Vite 6 retained)
- **Backend**: fastapi 0.115.8→0.121.3, starlette pinned 0.49.3 (CVE-2025-62727 HIGH StaticFiles Range-header DoS, CVE-2025-54121), python-multipart 0.0.20→0.0.32 (CVE-2026-42561 HIGH + 2), cryptography 44.0.2→46.0.7 (CVE-2026-26007 HIGH), pypdf 5.4.0→6.13.1 (~20 DoS CVEs; 5.x line unmaintained), reportlab 4.4.7→4.4.10 (4.5.x deliberately skipped — PDF output drift risk), uvicorn 0.49.0, sqlalchemy 2.0.50, requests ==2.34.2, python-dotenv 1.2.2, pytest 8.4.2; pydantic deliberately held at 2.12.5. Deferred majors documented in MAINTENANCE.md "Deferred Updates".
- **Frontend**: vite 6.4.3 (4 dev-server CVEs), axios 1.17.0 (CVE-2026-25639), react-router-dom 7.17.0 (SPA open-redirect/XSS), typescript 5.9.3, eslint 9.39.4; removed obsolete @types/react-router-dom; `npm audit` now reports 0 vulnerabilities.
- **Desktop**: pyinstaller >=6.20.0, pywebview >=6.2.1 (rebuild + save_file bridge check due at next .app build).

#### Fixed
- **2025 Form 8949 row capacity**: the 2025 IRS template holds 11 rows per page (2024: 14); the hardcoded 14-row chunking would have silently dropped rows 12-14 on 2025 filings (pdftk ignores unknown fields). Row capacity is now part of the year-specific field config.
- **Form 8949 multi-page handling**: overflow pages were numbered continuously (f1_, f2_, f3_...), but templates only define Page1 (Part I/short-term) and Page2 (Part II/long-term) fields — a second short-term chunk landed in the long-term table and later chunks vanished. Short/long chunks are now paired onto shared template-copy sheets, matching the paper form.
- Bundled 2025 templates verified MD5-identical to the final irs.gov releases (no draft markers).
- **Desktop app launch failure** (broken since 2026-02-14, exposed by the first .app build since January): the launcher's backend-readiness probe polled `/api/accounts/` expecting HTTP 200, but router-level auth (added Feb 2026) returns 401 — the probe spun for 30s and the app exited before ever creating a window (Dock dot, no UI). Probe now polls the unauthenticated SPA root.

#### Changed (behavior-preserving backend quality pass)
- Dead code removed (unused `fill_8949_multi_page`, legacy `AccountType` enum, duplicate `get_db`, debug prints, no-op `group_id` write); duplication consolidated (CSV upload validation, debug serializers, deposit aggregation, Schedule D field mapping); N+1 queries fixed in the transaction-history report (was 4 Account queries per row) and account balances; root-logger `basicConfig` calls replaced with module loggers.

#### UI Polish (existing dark theme, CSS-only)
- Design tokens: easing curves, letter-spacing, layered shadows, missing `--color-text-dim` defined; tabular numerals on all financial figures; gold active-nav underline; dashboard card hover lift; transaction date-heading hairlines; side-panel slide-in animation; `prefers-reduced-motion` support; theme-matched scrollbars; login.css duplicated rule blocks removed; stale pre-rebrand colors tokenized. Browser-verified at 1440/800/768/480px; layout, breakpoints, and 44px touch targets unchanged.

#### Testing
- New `backend/tests/test_2025_forms.py` (6 tests) incl. an 11-row capacity regression test; suite now **164 tests** (was 158).
- New PDF baseline gate `baseline-pdfs/regen_and_diff.sh`: regenerates all three reports against a frozen seed dataset and text-diffs them against committed baselines (run after every modernization phase; output verified equivalent throughout — a documented price-provider variant baseline covers live BTC-price variance in transfer-fee valuations).

### Test Isolation & Backups (February 2026)
- Test suite isolated from the production database (FastAPI TestClient + temp SQLite via dependency override; no running backend needed for most tests)
- Daily encrypted-safe SQLite backup script `scripts/backup-db.sh` (cron 3 AM, 60-day retention)

### Added
- **PDF Content Verification Test Suite**: `backend/tests/test_pdf_content.py` with 23 new tests
  - Uses `pypdf` to extract and verify actual PDF content, not just file generation
  - Complete Tax Report tests: year, sections, capital gains, ending balance, income, long/short-term
  - IRS Form tests: Schedule D present, Form 8949, proceeds, tax year, long-term section, page count
  - Transaction History tests: CSV headers, transaction data, types, PDF content
  - Edge case tests: empty year, large amounts ($7.5M), small BTC precision (0.00012345), same-day sales
  - Data accuracy tests: gain calculation, FIFO cost basis tracking, income totals
  - Total pytest tests: **158** (was 135)

### Fixed
- **test_seed_data_integrity.py**: Made tests self-contained with fixture that creates test data if database is empty
- **Disposal test logic**: Fixed to correctly skip USD transfers (only BTC transfers require lot disposals)

---

## [v0.5.5] - 2025-01-17 - Transaction Edit Fix

### Fixed
- **Transaction editing in macOS desktop app**: Fixed bug where editing transactions would fail with "Not enough BTC" error
  - Root cause: Backend's `update_transaction_record()` had flawed lot logic when backdating transactions
  - The partial re-lot (`recalculate_subsequent_transactions`) ran before full scorched earth, using stale lot balances
  - Fix: Simplified update flow to use only full scorched earth (`recalculate_all_transactions`)
  - This also fixes potential edge cases in Docker/web deployments with specific transaction histories

### Improved
- **PUT response validation**: Edit form now validates backend response before showing success
- **Realized gain display on edit**: Edit transactions now show realized gain in success toast (matching create behavior)

### Technical Notes
- **Files Modified:** `backend/services/transaction.py`, `frontend/src/components/TransactionForm.tsx`
- **Documentation:** `docs/archive/edit-tx-bug-mac.md` - Full investigation and fix details
- **Tests:** All 135 pytest tests pass, 17/17 pre-commit tests pass

---

## [v0.5.4] - 2025-01-16 - Buy from Bank Feature

> **Rollback Tags:** If issues arise, rollback to `pre-bank-buy` (develop) or `pre-bank-buy-master` (master)

### Added
- **Buy from Bank**: Buy transactions can now originate from Bank account (auto-buy support)
  - New "From Account" dropdown in Buy form: Exchange USD (default) or Bank (auto-buy)
  - CSV import accepts `Bank` as source for Buy transactions
  - FIFO cost basis tracking works correctly - lots land in Exchange BTC pool regardless of USD source
  - Backend validation relaxed to allow `from_account = Bank (1) OR Exchange USD (3)`
  - 5 new tests in `TestBuyFromBank` class covering basic flow, FIFO order, CSV import, backward compatibility
  - Documentation: `docs/archive/BUY_FROM_BANK_FEATURE.md`

### Technical Notes
- **Risk Level:** LOW - FIFO logic uses `to_account_id` (unchanged), not `from_account_id`
- **Backward Compatible:** Existing Buy transactions and CSVs continue to work unchanged
- **Files Modified:** `transaction.py`, `csv_import.py`, `TransactionForm.tsx`, `global.d.ts`, `test_stress_and_forms.py`

---

## [v0.5.3] - 2025-01-17 - Comprehensive Test Suite & Desktop Fixes

### Added
- **Comprehensive Test Suite**: `backend/tests/test_stress_and_forms.py` with 46 new pytest tests
  - Volume/stress testing (250+ transactions, backdating cascades, multi-year)
  - Edge cases: holding period boundaries (364/365/366 days), satoshi precision, $100M amounts
  - Account-specific FIFO verification (Exchange vs Wallet isolation)
  - All deposit sources tested: MyBTC, Gift, Income, Interest, Reward
  - All withdrawal purposes tested: Spent, Gift, Donation, Lost (with correct tax treatment)
  - IRS Form 8949 validation: multi-page (15/30 disposals), non-taxable exclusions
  - Schedule D totals verification
  - Total pytest tests: 131 (was 84)
- **macOS Desktop App**: Native macOS application using PyInstaller + pywebview
  - Self-contained `.app` bundle (~61MB) with embedded FastAPI backend
  - Data persists in `~/Library/Application Support/BitcoinTX/btctx.db`
  - Automated build script: `desktop/build-mac.sh`
  - PyInstaller spec with all hidden imports configured
  - Dynamic port allocation for backend server
  - Dark mode support, resizable window (1280x800 default, 800x600 min)
  - pdftk detection with user warning dialog if missing
  - Files added: `desktop/entrypoint.py`, `desktop/BitcoinTX.spec`, `desktop/build-mac.sh`, `desktop/requirements.txt`, `desktop/README.md`
  - Documentation: `docs/MACOS_DESKTOP_APP.md`
- **Mobile Responsiveness Overhaul**: Comprehensive mobile-friendly UI updates
  - Transaction panel: responsive width, fixed overlay positioning on mobile
  - Login page: fluid width for small screens
  - Navigation: CSS grid layout for mobile (3-column at 768px, 2-column at 480px)
  - Touch targets: minimum 44px for all interactive elements
  - Transaction list: mobile labels via CSS `::before` pseudo-elements
  - Added `:active` states for touch feedback across all interactive elements
  - Files modified: `transactionPanel.css`, `login.css`, `transactions.css`, `app.css`, `converter.css`, `reports.css`, `dashboard.css`, `settings.css`, `theme.css`, `transactionForm.css`
- **Frontend Design System Refactor**: Major code quality and architecture improvements
  - Custom hooks: `useAccounts`, `useApiCall`, `useBtcPrice` for reusable logic
  - Toast notification system with `ToastContext` for user feedback
  - Error boundaries (`ErrorBoundary.tsx`) for graceful error handling
  - Centralized theme system (`theme.css`) with CSS variables
  - Barrel exports via `hooks/index.ts`
- **CSV Export**: Export all transactions as a CSV file matching the import template format
  - Creates clean roundtrip: Export → Edit → Re-import
  - File naming: `btctx_transactions_YYYY-MM-DD.csv`
  - New endpoint: `GET /api/backup/csv`
- **CSV Import Instructions PDF**: Downloadable PDF guide for CSV import feature
  - New endpoint: `GET /api/import/instructions`
- **Pre-Commit Test Suite**: 17 tests for catching regressions
  - Run with: `./scripts/pre-commit.sh` or `python backend/tests/pre_commit_tests.py`

### Changed
- **Sidebar brand layout**: Changed from horizontal to vertical stack (logo above title)
- **Logout button**: Removed lock emoji, simplified to text-only
- **Logout link color**: Changed from dark red (#811922) to brighter red (#cf4655) to fix font rendering issue on macOS dark backgrounds
- **Pydantic V1 → V2 Migration**: Updated all deprecated Pydantic patterns
  - Replaced `@validator` with `@field_validator` + `@classmethod`
  - Replaced `class Config` with `model_config = ConfigDict(...)`
  - Replaced `orm_mode` with `from_attributes`
  - Replaced `.from_orm()` with `.model_validate()`
  - Replaced `.dict()` with `.model_dump()`
  - Eliminates all Pydantic deprecation warnings
  - Documentation: `docs/archive/PYDANTIC_MIGRATION.md`

### Fixed
- **pdftk path resolution for macOS desktop**: Added centralized `pdftk_path.py` module
  - PyInstaller bundles don't inherit system PATH, breaking pdftk detection
  - New module checks known Homebrew locations (`/opt/homebrew/bin/pdftk`, `/usr/local/bin/pdftk`)
  - Caches resolved path for performance
  - Updated `pdf_utils.py`, `pdftk_filler.py`, `reports.py` to use new module
- **Reports page desktop downloads**: Reports now download correctly in macOS desktop app
  - Updated `Reports.tsx` to use desktop-aware download utility
  - Added PyWebView API TypeScript types to `global.d.ts`
- **macOS desktop app downloads**: Settings page downloads (backup, CSV export, templates) now work correctly in the desktop app
  - Added `desktopDownload.ts` utility that detects pywebview environment
  - Uses native file save dialog via `window.pywebview.api.save_file()` when running in desktop app
  - Falls back to standard browser download for web/Docker deployment
  - File: `frontend/src/utils/desktopDownload.ts`
- **Lint errors fixed**: Removed unused variables in `useBtcPrice.ts` and `Settings.tsx`
- **Form 8949 non-taxable exclusion**: Gift, Donation, and Lost disposals now correctly excluded
- **Proceeds degradation fix**: Fixed bug where `proceeds_usd` could degrade during recalculation
- **None-to-Decimal conversion**: Fixed TypeError in report generation after Pydantic V2 migration
  - `.model_dump()` includes keys with `None` values, breaking `Decimal(tx_data.get("key", default))`
  - Changed to `Decimal(tx_data.get("key") or default)` pattern in `transaction.py`
- **FIFO lot disposal now account-specific**: Fixed bug where selling/withdrawing BTC would consume lots from all accounts globally instead of only from the source account. This ensures correct cost basis tracking when BTC is held across multiple accounts.
- **SPA routing in Docker**: Fixed browser refresh returning 404 on client-side routes
  - Added custom exception handler to serve `index.html` for non-API 404s
  - React Router now handles `/dashboard`, `/transactions`, `/settings`, etc. on page refresh
  - API routes still return proper JSON errors
  - File: `backend/main.py`

### Files Added
- `backend/tests/test_stress_and_forms.py` - Comprehensive stress testing and IRS form validation (46 tests)
- `backend/services/reports/pdftk_path.py` - Centralized pdftk path resolution for macOS desktop compatibility
- `frontend/src/utils/desktopDownload.ts` - Desktop app file download utility with pywebview integration
- `frontend/src/hooks/useAccounts.ts` - Account fetching and caching hook
- `frontend/src/hooks/useApiCall.ts` - Generic API call hook with loading/error states
- `frontend/src/hooks/useBtcPrice.ts` - BTC price fetching hook
- `frontend/src/hooks/index.ts` - Barrel exports for hooks
- `frontend/src/components/ErrorBoundary.tsx` - React error boundary component
- `frontend/src/components/Toast.tsx` - Toast notification component
- `frontend/src/components/ToastContainer.tsx` - Toast container component
- `frontend/src/contexts/ToastContext.tsx` - Toast context provider
- `frontend/src/styles/theme.css` - Centralized CSS variables and theming
- `frontend/src/styles/toast.css` - Toast notification styles
- `frontend/src/styles/errorBoundary.css` - Error boundary styles
- `backend/tests/pre_commit_tests.py` - Pre-commit test suite
- `scripts/pre-commit.sh` - Shell script wrapper for pre-commit tests

---

## [v0.5.0] - 2025-01-14 - Backend Refactoring & Test Suite

### Major Backend Refactoring

#### Code Modernization
- **Removed passlib dependency**: Direct bcrypt usage for password hashing
  - `User.set_password()` and `User.verify_password()` now use bcrypt directly
  - Added 72-byte password limit validation (bcrypt requirement)
  - Eliminates passlib deprecation warnings
- **Replaced deprecated `Query.get()`**: Updated to `Session.get()` pattern
  - 10 occurrences in `transaction.py`
  - 1 occurrence in `debug.py`
  - 1 occurrence in `test_seed_data_integrity.py`
- **Replaced `@app.on_event` deprecation**: Migrated to FastAPI lifespan context manager
- **Removed duplicate import**: Fixed `from_orm` duplicate in `form_8949.py`

#### Performance Improvements
- **Added `joinedload` eager loading**: Optimized `compute_sell_summary_from_disposals()`
  - Prevents N+1 queries when loading `LotDisposal.lot` relationships
- **Added database indexes on foreign keys**:
  - `LedgerEntry.transaction_id`, `LedgerEntry.account_id`
  - `BitcoinLot.created_txn_id`
  - `LotDisposal.lot_id`, `LotDisposal.transaction_id`

#### Code Organization
- **Created `backend/constants.py`**: Centralized account ID constants
  - `ACCOUNT_BANK`, `ACCOUNT_WALLET`, `ACCOUNT_EXCHANGE_USD`, `ACCOUNT_EXCHANGE_BTC`
  - `ACCOUNT_BTC_FEES`, `ACCOUNT_USD_FEES`, `ACCOUNT_EXTERNAL`
  - Replaced magic numbers throughout codebase
- **Deleted dead files**:
  - `backend/create_account_db.py` (unused)
  - `backend/create_db.py` (replaced with inline command)
- **Updated Makefile**: `create-db` target now uses inline Python command

### CSV Import/Export Fixes
- **Fixed CSV export `proceeds_usd`**: Now falls back to `proceeds_usd` when `gross_proceeds_usd` is None
- **Relaxed CSV import validation**: Now matches transaction service rules
  - Deposit: External → any internal account (BTC or USD)
  - Withdrawal: any internal account → External
  - Transfer: between internal accounts of same currency

### Testing

#### Comprehensive Test Suite (`backend/tests/test_everything.py`)
78 automated tests covering:
- Database seeding with 65 test transactions
- All API endpoints (accounts, transactions, calculations, debug)
- All report generation (Complete Tax Report, IRS Forms, Transaction History)
- CSV export/import roundtrip verification
- FIFO integrity (lots, disposals, account balance matching)
- Gains/losses calculations and income tracking
- All transaction types, withdrawal purposes, deposit sources
- Holding period verification (short-term vs long-term)

Run with: `python3 backend/tests/test_everything.py`

#### Authentication Test Suite (`backend/tests/test_password_migration.py`)
Comprehensive auth tests:
- Password hashing and verification
- 72-byte bcrypt limit enforcement
- Unicode and special character passwords
- Login/logout endpoint tests
- Session persistence tests
- Protected endpoint authentication
- Backward compatibility with existing hashes

Run with: `pytest backend/tests/test_password_migration.py -v`

#### Updated Seed Data (`backend/tests/transaction_seed_data.json`)
- 65 transactions across 2023-2025
- All 5 deposit sources: MyBTC, Gift, Income, Interest, Reward
- All 4 withdrawal purposes: Spent, Gift, Donation, Lost
- Short-term and long-term gains coverage
- USD and BTC deposits to various accounts

### Dependency Updates

| Package | Old Version | New Version |
|---------|-------------|-------------|
| pydantic | 2.10.6 | 2.12.5 |
| uvicorn | 0.34.0 | 0.40.0 |
| sqlalchemy | 2.0.37 | 2.0.45 |
| httpx | 0.24.1 | 0.28.1 |
| requests | 2.28.1 | 2.32.0 |
| python-multipart | 0.0.6 | 0.0.20 |
| python-dateutil | 2.8.2 | 2.9.0 |
| itsdangerous | 2.1.2 | 2.2.0 |
| reportlab | 3.6.12 | 4.4.7 |
| pytest | 8.1.1 | 8.3.5 |

### Removed Dependencies
- `passlib` - replaced with direct bcrypt
- `typer` - unused
- `python-jose` - unused
- `pandas` - unused
- `weasyprint` - unused
- `pdfkit` - unused
- `jinja2` - unused (beyond FastAPI's built-in)
- `pycryptodome` - unused

### Files Added
- `backend/constants.py` - Centralized account ID constants
- `backend/tests/test_everything.py` - Comprehensive test suite (78 tests)
- `backend/tests/test_password_migration.py` - Authentication tests

### Files Modified
- `backend/models/user.py` - Direct bcrypt, 72-byte limit
- `backend/models/transaction.py` - FK indexes
- `backend/database.py` - Direct bcrypt for default user
- `backend/main.py` - Lifespan context manager
- `backend/services/transaction.py` - Query.get(), joinedload, constants
- `backend/routers/backup.py` - proceeds_usd fallback, constants
- `backend/routers/debug.py` - Query.get()
- `backend/services/csv_import.py` - Relaxed validation, constants
- `backend/services/reports/form_8949.py` - Removed duplicate import
- `backend/tests/register_default_user.py` - Direct bcrypt
- `backend/requirements.txt` - Updated all versions
- `Makefile` - Updated create-db target

### Files Deleted
- `backend/create_account_db.py`
- `backend/create_db.py`

---

## [v0.4.0] - 2025-01-12

### Added
- **CSV Template Import**: Bulk transaction import from CSV files
  - Download CSV template with exact column structure
  - Preview parsed transactions before importing
  - Full validation with error/warning display
  - Atomic import (all-or-nothing) with rollback on failure
  - Requires empty database (Phase 1 - no merge complexity)

### Endpoints
- `GET /api/import/template` - Download blank CSV template
- `GET /api/import/status` - Check if database is empty
- `POST /api/import/preview` - Parse and preview CSV (no DB writes)
- `POST /api/import/execute` - Execute atomic import

### Files Added
- `backend/schemas/csv_import.py` - Pydantic request/response models
- `backend/services/csv_import.py` - Parsing, validation, and import logic
- `backend/routers/csv_import.py` - API endpoints

### Fixed
- **Atomic imports**: Added `auto_commit` parameter to `create_transaction_record()`
  - Bulk imports now use `auto_commit=False` to defer commit until all succeed
  - Prevents partial imports on validation failures
- **Async event loop conflict**: Fixed `get_btc_price()` during CSV import
  - Used `ThreadPoolExecutor` to run async price fetches in separate threads
  - Fixes "Cannot run the event loop while another loop is running" error

---

## [v0.3.2] - 2025-01-10

### Fixed
- **Backup restore redirect**: Fixed "Not Found" error after successful backup restore
  - After restoring a backup, the session cookie still referenced the old user_id
  - Backend now clears session after restore (`request.session.clear()`)
  - Frontend redirects to `/login` instead of reloading the page
  - Users now see success message and are redirected to login properly

---

## [v0.3.1] - 2025-01-10

### Fixed
- **Backup/restore in Docker/StartOS**: Fixed `backup.py` to use `DATABASE_FILE` environment variable
  - Previously used hardcoded path `backend/bitcoin_tracker.db` which didn't match Docker's `/data/btctx.db`
  - Backup and restore now work correctly in containerized environments
- **Backup file cleanup race condition**: Fixed temp file deletion before streaming complete
  - Now uses FastAPI `BackgroundTasks` to delete temp file after response completes

### Documentation
- **StartOS container architecture**: Comprehensive documentation in `docs/STARTOS_COMPATIBILITY.md`
  - Two-repository architecture explanation
  - Volume mounts and data persistence
  - DATABASE_FILE environment variable
  - Common mistakes to avoid

---

## [v0.3.0] - 2025 IRS Form Support

### Added
- **Multi-year IRS form support**: Users can now generate IRS reports for both 2024 and 2025 tax years
- Year-based template folder structure (`backend/assets/irs_templates/2024/`, `2025/`)
- `get_template_path(year, form_name)` - Dynamic template path selection
- `get_supported_years()` - Returns list of available tax years
- `get_8949_field_config(year)` - Year-specific Form 8949 field naming
- `get_schedule_d_field_config(year)` - Year-specific Schedule D field naming
- 2025 IRS Form 8949 and Schedule D templates
- Comprehensive test dataset (40 transactions spanning 2023-2025)

### Fixed
- **Schedule D field mapping**: Changed from Line 1b/8b to Line 3/10 for self-tracked crypto
  - Self-custody Bitcoin uses Box C (short-term) and Box F (long-term) - not reported on 1099
  - Line 3 for short-term totals from Box C, Line 10 for long-term totals from Box F
- **Complete Tax Report generation**: Fixed Transfer lot restoration in `_partial_relot_strictly_after()`
  - Transfer transactions now properly restore source lot balances during year-boundary recalculations
  - Uses LIFO to reverse FIFO consumption when rebuilding transactions

### Changed
- `map_8949_rows_to_field_data()` now accepts `year` parameter for correct field naming
- `map_schedule_d_fields()` now accepts `year` parameter
- `fill_8949_multi_page()` now accepts `year` parameter
- `_verify_templates_exist()` now validates year-specific template availability
- IRS reports endpoint returns helpful error for unsupported years

### Technical Details
- 2024 Form 8949: `Table_Line1`, fields `f1_3` (not zero-padded)
- 2025 Form 8949: `Table_Line1_Part1`/`Part2`, fields `f1_03` (zero-padded for row 1)
- Schedule D Line 3 (Row3): Short-term from Box C/I (self-tracked, no 1099)
- Schedule D Line 10 (Row10): Long-term from Box F/L (self-tracked, no 1099)

---

## [v0.2.0-beta] - StartOS Packaging Complete

### Added
- `docs/` directory for project documentation
- `CLAUDE.md` - AI assistant context file (root directory for auto-detection)
- `docs/CHANGELOG.md` - This file
- `docs/ROADMAP.md` - Future goals and planned features
- `docs/STARTOS_COMPATIBILITY.md` - Docker requirements for StartOS packaging

### Changed
- Updated `README.md` with current Docker instructions and accurate tech stack

---

## [2025-01-10] - Docker Compatibility & Cleanup

### Fixed
- **PDF generation paths**: Changed relative paths to absolute paths in `backend/routers/reports.py`
  - IRS Form 8949 and Schedule D templates now load correctly regardless of working directory
  - Added `_verify_pdftk_installed()` and `_verify_templates_exist()` pre-flight checks

- **BTC price fetching in Docker**: Fixed `get_btc_price()` in `backend/services/transaction.py`
  - Previously made HTTP calls to `localhost:8000` which failed in Docker (port 80)
  - Now calls bitcoin service functions directly via import

- **Python 3.9 compatibility**: Added `from __future__ import annotations` to:
  - `backend/schemas/transaction.py`
  - `backend/services/user.py`
  - Fixes `TypeError: unsupported operand type(s) for |` for union type syntax

### Changed
- Cleaned up 63 stale branches across repositories
- Established `master`/`develop` branch workflow

### Infrastructure
- Docker image published to `b1ackswan/btctx:latest`
- All repositories synced (BitcoinTX-org, PlebRick backup)

---

## [Pre-2025] - Initial Development

### Features
- Double-entry accounting system for BTC transactions
- FIFO cost basis tracking with BitcoinLot/LotDisposal models
- IRS Form 8949 and Schedule D PDF generation
- Dashboard with holdings, balances, and gains
- Transaction entry form (Deposit, Withdraw, Transfer, Buy, Sell)
- Historical BTC price fetching (CoinGecko, Kraken, CoinDesk)
- Session-based authentication
- CSV/PDF transaction history export
