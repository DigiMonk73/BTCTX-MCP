# Hardening, then redesign: plan

Written 2026-09-25 at the end of the v0.9.1 session, for the sessions that carry
it out. Read `CLAUDE.md` first; this file assumes it.

**Goal.** First make BitcoinTX's calculations and flows provably solid (v0.9.2),
then give the UI a modern, clean look without changing what it does (a later
release). The owner wants to drop Koinly and rely on BitcoinTX's Form 8949, so
correctness comes first.

**Not in scope.** New features. Functional changes other than bug fixes. The
column-mapping, specific-lot and multi-year items in `ROADMAP.md`.

## Ground rules

- Each phase ends at a **gate**: stop, report to the owner what was done and
  found, and wait for their OK before the next phase.
- A bug fix gets a test that fails on the old code (`CLAUDE.md`). Any fix that
  changes tax results for existing data (gains, basis, proceeds, dates) is
  described to the owner **before** it is made, with what changes and whether a
  Recalculate Ledger is needed.
- Never touch the owner's real data. Tests use temp databases and stubbed prices.
- Keep `make check-fast` green on every push. New dependencies follow
  `docs/MAINTENANCE.md`.
- Work on the session's branch. Merge to `main` and release only with the
  owner's OK (release steps: `CLAUDE.md` → Releasing, `startos/UPDATING.md`).

## Where things stand (v0.9.1)

- Released 2026-09-25: Settings → Connect an AI Assistant, and fixes for three
  bugs found by reconciling against River's receipts:
  1. River import subtracted the Sell fee twice (assumed a field's meaning).
  2. The edit form shifted times by the UTC offset (UTC/local mix-up), and new
     transactions defaulted to UTC wall time.
  3. Income deposits entered without a basis were saved at $0 (silent default).
- On `main`, unreleased: `mcp_server/AI_SETUP.md` explains the StartOS
  certificate and password. Ships with v0.9.2.
- Open: does River's CSV "Sent Amount" on a **Buy** include the fee? If it does,
  basis is overstated by the fee on every buy that had one. Needs a River buy
  receipt from the owner; don't guess.
- Test inventory: ~320 backend tests (`backend/tests/`), 19 MCP tests, 25
  frontend unit tests (Vitest, form ↔ API mapping only), a smoke test against
  the real server. **No test drives the UI.**

The three bugs are three patterns. Phase 2 hunts each one everywhere.

## Phase 1: click-through tests (lock the behavior)

Write Playwright end-to-end tests of every user flow against the current UI,
so the later redesign can prove it changed nothing.

- Tooling: `@playwright/test` as a frontend dev dependency, pinned to the
  version preinstalled in cloud sessions (`npx playwright --version`; launch with
  `executablePath: '/opt/pw-browsers/chromium'`, never `playwright install`).
  Serve the real backend on a temp database with stubbed prices; reuse
  `serve()` from `scripts/smoke_test.py`. Add `make e2e` and a CI job.
- Find elements by role and visible label (`getByRole`, `getByLabel`), never by
  CSS class, so the tests survive the redesign. Where the current markup has no
  usable label, adding `aria-label`/`<label>` is allowed (accessibility only, no
  behavior change).
- Run the edit and date tests with `timezoneId: 'America/Chicago'` and once in
  a UTC+ zone (`Asia/Tokyo`); the v0.9.1 time bug was invisible in UTC.
- Flows:
  - First run: claim the default account; login, wrong password, logout.
  - Dashboard: balances and portfolio figures after a known set of entries.
  - Create each type: BTC Deposit with every source (income sources get the
    day's price when the basis is blank), USD Deposit, Withdrawal
    (Spent/Gift/Donation/Lost), Transfer with a BTC fee, Buy from Bank and from
    Exchange USD, Sell with a USD fee, the 1099-DA override.
  - Edit a transaction changing one field: everything else, including the time
    to the second, is unchanged. Delete.
  - Transactions list: order, filters, what each row shows.
  - River import: preview statuses (new / matched / discrepancy), edits, execute,
    re-import skipped. CSV import on an empty database; template and
    instructions downloads.
  - Reports: complete tax report PDF, Form 8949/Schedule D PDF, transaction
    history CSV (assert the downloads and key figures in them).
  - Settings: tax timezone change, Recalculate Ledger, credential reset, backup
    download and restore, CSV export, the Connect an AI Assistant prompt.
  - The calculator and BTC converter widgets.
- The Mac app renders with WebKit. If a CI job can install Playwright's WebKit
  (`npx playwright install --with-deps webkit` on a GitHub runner), run the suite
  there too; cloud sessions have Chromium only.

**Gate 1:** every flow above covered and green locally and in CI.

## Phase 2: the bug hunt

Sweep by pattern, then by invariant. Record every finding in
`docs/HARDENING_FINDINGS.md` (what, where, evidence, verdict, fix/test commit,
or "deferred, owner OK").

1. **Dates and timezones.** Rule: stored in UTC; tax dates, year bounds and
   holding periods in the tax timezone (`backend/services/tax_time.py`); forms
   show and accept the computer's local time. Check every conversion:
   - frontend: `TransactionForm.tsx`, `transactionForm.ts`, `Transactions.tsx`,
     `Dashboard.tsx`, `Settings.tsx`, `RiverImport.tsx`, `BtcConverter.tsx`,
     `utils/format.ts`;
   - backend: `strftime("%Y-%m-%d")`, `.date()` and `replace(tzinfo=…)` in
     `services/transaction.py`, `entry_import.py`, `river_import.py`,
     `csv_import.py`, `bitcoin.py`, `reports/complete_tax_report.py`,
     `schemas/transaction.py`.
   Test Dec 31/Jan 1 in US and UTC+ zones, DST changes, and the one-year
   anniversary on each side of midnight.
2. **Silent defaults.** Every `or 0` / `or Decimal("0")` (about 20 each in
   `services/transaction.py` and `reports/reporting_core.py`, plus
   `form_8949.py`, `calculation.py`, `river_import.py`). For each, decide: is 0
   a real value here, or does it hide missing input that changes a tax number?
   The second kind must be filled, rejected or flagged.
3. **Importer field meanings.** For every column of the River, CSV and MCP
   entry imports, write down what it means and the evidence (a receipt, a
   documented format). Anything assumed without evidence is a finding. The
   River Buy fee question above is the known one.
4. **Invariants under random ledgers.** Add Hypothesis (dev dependency) and
   generate random valid transaction sequences. Assert:
   - each account's balance = its ledger lines = its remaining lots (BTC);
   - cost basis is conserved: a transfer moves basis (less the fee's share),
     never creates or destroys it; every sold satoshi's basis came from a lot;
   - realized gain = proceeds − basis on every disposal; Form 8949 totals =
     Schedule D lines = the complete report;
   - recalculating twice changes nothing; entering the same transactions in a
     shuffled order gives the same result;
   - no lot goes negative; long-term only after the one-year anniversary.
5. **Golden years.** Three or four hand-computed tax years (small, written out
   from the IRS rules in a test docstring) with exact expected 8949 rows,
   boxes and Schedule D lines, including transfers with fees, a sale spanning
   several lots, income, a spend and a year-boundary sale.
6. **API and security.** Every route requires login except those listed in
   `CLAUDE.md`; bad input (negative or huge amounts, too many decimals, future
   dates, unknown accounts) is rejected with a clear message; backup/restore
   round-trips; the MCP server exposes no bulk delete.
7. **Frontend robustness.** Double submit, a failed request, slow price
   lookups, empty states. Found with the Phase 1 tests.

This phase splits well across parallel agents (one per sweep). A multi-agent
workflow may be used only if the owner asks for one ("use a workflow").

**Gate 2:** every sweep done; every finding fixed with a test, or deferred with
the owner's OK.

## Phase 3: reconcile the owner's real data

The original request (2026-09-25): compare River's activity CSV and Koinly's
capital gains reports with BitcoinTX, per transaction and per tax year; explain
every difference (missing transaction, fee treatment, lot selection, price
source, timezone/date); say which side is right; change data only with the
owner's OK; if BitcoinTX calculates wrong, failing test then fix.

This needs the owner's computer: the files are in `~/btctx-reconcile` on their
Mac, plus a copy of `btctx.db` (Mac app: `~/Library/Application
Support/BitcoinTX/btctx.db`). Run it in a local session (Claude Desktop, or
`claude remote-control` in the repo). Never copy the files into the repo.

Known difference to expect: Koinly may use FIFO across all wallets; BitcoinTX
uses FIFO per account, which the IRS requires from 2025 (Treas. Reg.
§1.1012-1(j), Rev. Proc. 2024-28). Check the lots each account held on
2025-01-01 against what the filed returns imply.

**Gate 3:** every difference explained and resolved or accepted by the owner.

## Phase 4: release v0.9.2

Bug fixes only, plus the guide fix already on `main`. Changelog entries say
which fixes change existing figures and whether Recalculate Ledger is needed
(StartOS: raise the Recalculate task in the migration if so). Owner's OK first.

## Phase 5: design system and mockups

Deliverables for the owner's approval, before any production code changes:

- **Tokens:** color (light and dark), type scale, spacing, radii, elevation,
  motion. One accent; gains/losses never shown by color alone.
- **Component inventory:** every control the app uses today (forms, selects,
  date/time input, tables, dialogs, toasts, tabs, the sidebar) mapped to one
  consistent set.
- **Mockups** of the Dashboard, Transactions and the transaction form (Settings
  if time allows), as an HTML page the owner can open.
- **Standards:** WCAG 2.2 AA (contrast, keyboard use, visible focus, labels);
  tabular (fixed-width) digits for BTC and USD, aligned in columns; consistent
  number and date formats; loading, empty and error states on every screen;
  respects reduced motion; works from the Mac app's minimum window (800×600) up,
  and on a phone for StartOS users.
- **Engine limit:** the Mac app runs in WebKit and supports macOS 10.15, whose
  WebKit stops at Safari 15. Use only CSS that Safari 15 supports: no container
  queries, `color-mix()`, CSS nesting or subgrid unless the build compiles them
  away. Tailwind v4 needs Safari 16.4, so it is out unless the owner raises the
  macOS minimum. Plain CSS with custom properties (what the app uses now), plus
  headless React components where they save work, fits.

**Gate 5:** owner approves the tokens and mockups.

## Phase 6: build the redesign

Screen by screen, the Phase 1 tests passing unchanged at every step (only
selectors that the redesign legitimately renames may change, and each such
change is listed). Before/after screenshots of every screen for the owner.
Check in the Mac app build (CI artifact) as well as Chromium. Release when the
owner is happy; they choose the version number.
