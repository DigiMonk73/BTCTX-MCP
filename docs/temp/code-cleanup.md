# Code cleanup: plan and checklist

Approved by the owner on 2026-09-29. Each box is ticked in the commit that
does it (with the matching box in `docs/temp/TODO.md`); the file is deleted
when all is done (`docs/temp/README.md`).

## Context

BitcoinTX 1.2.2-1 is stable. The owner wants code that reads like a carefully
maintained professional project: the long functions divided into named steps,
no filler comments, one set of idioms. **The one rule: no change in
behaviour.** Figures, PDFs, CSVs, API answers, MCP tool outputs, messages and
the database stay the same, and the existing tests pass without being edited.
This is tax software, so a cleanup that moves one cent has failed.

The baseline is the release users run: tag `v1.2.2-1`. Since then only docs
have changed.

Owner's decisions (2026-09-29):
- **`is_locked`** is not exported. Nothing in the app can lock a transaction:
  there is no button, the API ignores the flag, and the AI can't set it. The
  guard test lists it as not exported, with that reason. The half-built lock
  feature is a separate to-do (Findings).
- **`review.fee_price_changes`** narrowing is a fix, not a cleanup, because it
  changes what happens when a lookup fails unexpectedly. It gets its own
  commit after the cleanup, labelled as a fix, with a test.

## 1. Scope

The "Code cleanup" items in `docs/temp/TODO.md` all checked out against the
code today, except one number: old-style type hints are in 46 app files (55
counting tests), not 44. Measured today, app code only, with no tests or
migrations:

| Function | Lines | Complexity (ruff C901) |
|---|---|---|
| `generate_comprehensive_tax_report` | 510 | 35 |
| `generate_csv_instructions_pdf` | 395 | 103 statements |
| `csv_import._validate_row` | 276 | 32 |
| `build_ledger_entries_for_transaction` | 215 | 22 |
| `get_gains_and_losses` | 179 | 22 |
| `adapt_river_rows` | 149 | 14 |
| `generate_template_csv` | 147 | not over the limit |
| `update_transaction_record` | 128 | 31 |
| `maybe_transfer_bitcoin_lot` | 121 | 15 |
| `map_8949_rows_to_field_data` | 117 | 11 |
| `maybe_dispose_lots_fifo` | 113 | 16 |
| `create_transaction_record` | 112 | 11 |
| `_generate_pdf` (transaction history) | 109 | not over the limit |
| `execute_river_import` | 106 | 11 |
| `_validate_type_specific` | 105 | 16 |
| `parse_csv_file` | 102 | not over the limit |

Added to the scope:
- **The guard test**: every `Transaction` column is either in the CSV export or
  on an explicit "not exported, because…" list. The list: `id` (the import
  makes new ids); `created_at` and `updated_at` (set when a row is saved);
  `realized_gain_usd` and `holding_period` (recalculated from the lots); net
  `proceeds_usd` (recalculated from the gross, which is exported); and
  `is_locked` (nothing in the app can set it). A new column fails the test
  until someone decides.
- **Everything else over the limits**, so the limit can be switched on:
  - `_validate_transaction` (27) and `_enforce_transaction_type_rules` (17)
  - `csv_import._validate_accounts_for_type` (17)
  - `river_import.annotate_duplicates` (16)
  - the MCP `update_transaction` body (16; its 15 parameters are the tool's
    parameters and stay as they are)
  - the MCP client's `request` (13)
  - `migrate.adopt_unversioned` (13)
  - `fill_pdf_form` (12)
  - `review.build_review`, `entry_import.simulate` and
    `price_history.public_history` (11 each)
  - `routers/backup.export_transactions_csv` (98 lines)
  - the tools `scripts/smoke_test.run` and `scripts/irs_new_year.main` and
    `verify`
- **Filler across the app code**:
  - The file-path first line in about 45 module docstrings
    (`backend/services/x.py`, `# FILE: …`).
  - The `# ---- Section ----` banners in about 20 files.
  - History notes ("(NEW)", "used to", "no longer", "remains unchanged since").
  - Comments that repeat the next line.
- **Dead code**: `recalculate_subsequent_transactions` (nothing calls it), and
  anything else found along the way that has no caller and no test.

Not in scope:
- The other broad `except Exception` catches (47 of them). Narrowing any of
  them changes what happens on failure.
- Splitting `transaction.py` into several files. It stays one file, divided
  into named steps. The reasons:
  - Five tests replace its `get_btc_price` by name (a monkeypatch). If code
    moved to another file, those replacements would silently stop applying.
  - The static check (`pre_commit_tests.py`) looks for text in this file.
  - `csv_import.py` imports from it, so new files importing back from it
    would risk circular imports.

## 2. Standards

These go into a new, lasting `docs/CODE_STYLE.md` (with a one-line pointer in
`CLAUDE.md`, so any AI working here follows them), before any code edit.

**Python**
1. A function does one thing, and its name says what: a verb for actions
   (`add_fee_disposal`), a noun for values (`fee_disposals`). Limits:
   complexity 10 (C901), 12 branches (PLR0912), 50 statements (PLR0915),
   6 returns (PLR0911).
2. Dividing a long function into named steps is the point of the cleanup, and
   a step called once is fine when it is a real unit: one PDF section, one
   validation rule, one transaction type's ledger lines. What is not allowed:
   - a wrapper that only renames another call
   - a class or parameter "for later"
   - a helper whose body is shorter than its name
3. Comments say **why**: a tax rule, an IRS line, a past bug, a platform
   limit. They never narrate the next line and never tell the code's history
   ("now", "NEW", "used to"); history belongs in the CHANGELOG and git.
4. A module docstring opens with what the module is for, and never the file's
   path. Public functions get a docstring when the name and signature don't
   say enough; private helpers only when needed.
5. No banner or divider comments. The module is ordered instead: public
   functions first, then helpers in the order they are used. A plain one-line
   comment may title a group.
6. No dead code, no commented-out code, no unused parameters.
7. The same idioms everywhere:
   - Modern hints (`list[str]`, `X | None`).
   - One named constant per money precision (`CENT`, `SATS`), not repeated
     `Decimal("0.01")`, where changing it cannot change a result.
   - Errors keep their exact text.
   - The narrowest `except` in new code.
8. Tests are exempt from the size limits, since a scenario can be long. No
   existing test is edited; new tests follow these rules.

**Frontend (TypeScript/React)**
1. One component per file, doing one job. A form section per transaction type,
   a component per Settings card.
2. The same comment rules as Python.
3. Every label, `htmlFor`/`id`, role, `aria-label`, and each class or id that
   the e2e tests or other components use stays exactly as it is.
4. No new CSS. Moving markup must not change what Safari 15 renders.

**Tooling, switched on last** (once the code meets it):
- ruff:
  - `UP` (modern hints) comes on in the type-hint commit itself.
  - `C901` (max complexity 10), `PLR0911`, `PLR0912` and `PLR0915` come on
    in the final commit, with test folders exempt.
  - `PLR0913` (argument count) stays off: MCP tool and API signatures set
    those.
- ESLint: `complexity` 15 and `max-lines` 400 per file in `src/`.

## 3. Safety net (built before any app code changes)

**Callers and tests: what must stay the same**
- Test-only names stay importable from the same module:
  - `csv_import._validate_row` (called with `(row, 2)`, returns a 4-tuple)
  - `form_8949._determine_box`
  - `routers.backup._copy_at_most`, `AI_COPY_EVERY` and `MAX_RESTORE_BYTES`
  - `transaction.holding_period`
- Names the tests replace:
  - `backend.services.transaction.get_btc_price` (5 tests): every price lookup
    in the engine keeps going through that module name.
  - `backend.routers.csv_import.parse_csv_file` and `.execute_import`.
  - `backend.routers.river_import.annotate_duplicates` and `.execute_import`.

  The router handlers keep calling those module names and stay plain `def`
  (the "imports don't block the server" test relies on that).
- `get_historical_btc_price` and `get_btc_price` look like duplicates but both
  stay. The tests replace only one of them, so merging them would change what
  those tests check.
- `pre_commit_tests.py` looks for text:
  - `def recalculate_all_transactions`, `order_by`, `timestamp`,
    `tx.proceeds_usd` and `backdated` in `transaction.py`
  - the CSV column names as literals in `routers/backup.py` and `csv_import.py`
  - `NON_TAXABLE_PURPOSES`, `Transaction.purpose` and similar in `form_8949.py`

  That text stays where it is.
- `map_8949_rows_to_field_data` keeps adding each row's columns in order
  a→h: `irs_new_year.py` and a test pair them with "abcdefgh".
- Log lines keep their level and text. `test_privacy` fails if a date appears
  at INFO.

**Coverage.** `coverage` gets installed in the local `.venv` only, not as a
project dependency. Before each area, measure the lines of the functions being
changed. Anything the tests never run gets a characterization test first, in
its own commit. Thin spots already known:
- `generate_template_csv`: only its header is checked.
- The CSV instructions PDF: never tested.
- A locked row's refused edit and delete: never tested, and the check sits
  inside `update_transaction_record`.
- `get_gains_and_losses`: the endpoint is tested, but not every figure.
- `_generate_pdf`: only its text is spot-checked.
- The CLI `review --fix-fee-prices`.

**The equivalence check** (`scripts/equivalence_check.py`, committed and
documented in `docs/TESTING.md`). It snapshots every output, both on
`v1.2.2-1` (in a temporary git worktree, the same day, so dates match) and on
the working copy, then compares them. Snapshots are kept in
`.equivalence/<commit>/`, which is gitignored.

Ledgers:
- the golden ledger (`test_golden_years.LEDGER`, New York time)
- the 65-transaction seed ledger (`transaction_seed_data.json`)
- 40 random ledgers from the property test's `draw_ledger`, fed by a fixed
  seed, in UTC, Chicago and Tokyo time
- a bad-input set: one invalid CSV row per validation rule, and one invalid
  API payload per rule in `_validate_transaction` and `_enforce_*`, to capture
  every error message

Outputs:
- **Database**: every transaction, ledger line, lot and lot disposal, all
  columns except row ids and save times.
- **API**:
  - the transaction list and each transaction
  - the balances, gains-and-losses and average cost basis
  - `/api/review`
  - `/openapi.json` (with DEBUG), which catches any change to routes or types
- **Reports**, for each year:
  - Form 8949 and Schedule D field data, in field order, per sheet
  - the merged IRS PDF's text
  - the complete tax report input (`generate_report_data`) and its PDF
  - the transaction history PDF and CSV
- **CSV**:
  - the export (bytes)
  - the template (bytes)
  - the preview of its own export
  - the preview of the bad rows
- **River**: preview and import of the test fixture file.
- **MCP**:
  - the tool list (names, descriptions, input and output schemas)
  - every tool's output, run the way `mcp_server/tests/test_server.py` runs
    them, against the in-process app
- **The CSV instructions PDF**, regenerated to a temp file.

How the ReportLab PDFs are compared: generated in ReportLab's invariant mode,
then compared as **exact bytes**, plus their text. The IRS PDFs come from
pypdf, which is deterministic; confirm that on day one, and otherwise compare
field values and text. Values that depend on "now" are masked. So are ids and
save times.

It also times recalculation (`--bench`): a 2,000-transaction ledger, the
fastest of 9 runs, old code against new on the same machine (identical code
measured 3–4% apart as a median, so the fastest run is compared). It fails
if the new code is more than 5% slower; a rerun rules out noise.

UI: a Playwright script records the accessibility tree (every label, role and
visible text) of each form variant, Settings, the Dashboard and the River
preview. It runs on the 1.2.2-1 build and the new one, and the two are
compared.

## 4. Unintended consequences and how each is checked

| Risk | Check |
|---|---|
| Mac app: a new backend module needs `hiddenimports` | None planned. If one is added: an entry in `desktop/BitcoinTX.spec`, and CI's macOS launch job |
| StartOS relies on `backend/cli.py` and `GET /api/health` | Left alone. CI's Docker job runs the CLI |
| API routes and response shapes | `/openapi.json` and every JSON answer identical in the equivalence check |
| MCP tools, their parameters and outputs; `AI_KEY_ROUTES` | Tool list and outputs identical. `ai_key.py` not touched. The tools-vs-routes test |
| User-facing text and errors | Bad-input set, PDF text, CSV bytes identical. MCP guide not touched |
| Database | No column, type, key, default or migration changes (a model's descriptions may). `test_models_and_migrations_agree`; database rows identical |
| Frontend e2e finds elements by label and role | Accessibility-tree comparison. `make e2e`. CI's WebKit run (Safari engine) |
| Type hints are evaluated at import time (FastAPI, pydantic, SQLAlchemy `Mapped`) | Full test suite on Python 3.10 locally (`uv`) and in CI. `openapi.json` and the MCP schemas identical |
| Speed of recalculation | `--bench` on every engine commit and at the end |
| Rounding and dict order | Dict keys in the same order (the JSON is compared as text). `Decimal` sums in the same order |
| The static text checks | `make check-fast` runs `pre_commit_tests.py` |

## 5–6. Order and execution

Every commit:
- covers one area
- is green: `make check-fast`, plus `make test` for engine and report
  commits, and `make e2e` for frontend ones
- reruns the equivalence check, which must come out clean
- is pushed to `develop`
- ticks its TODO box and its box here

A real bug found along the way is noted under Findings and asked about, never
fixed inside a cleanup commit.

**Foundation (no app code changes)**
- [x] This plan in `docs/temp/code-cleanup.md`. `docs/CODE_STYLE.md` and its
      pointer in `CLAUDE.md`. The TODO line fixed (46 files), the guard test
      added, and a new "Next" to-do for the lock flag.
- [x] The equivalence check. The baseline taken on `v1.2.2-1`, and a clean
      first run against the working copy. (The UI snapshot script comes at the
      start of the frontend track.)
- [x] The guard test for Transaction columns (a new test in its own file).

**Low risk**
- [x] Delete the stray `backend/services/ __init__.py`. It never counted as a
      package file (the space in its name), so `backend.services` stays
      exactly what it is today. Checked with CI's macOS and Docker jobs.
- [x] Comments and docstrings. Check: each module's syntax tree, with
      docstrings stripped, is identical before and after, so no code changed.
      Three kinds of docstring are not touched: MCP tools, pydantic schemas
      and API route handlers. They are the texts the AI and the API docs
      show.
      Done for all modules; the comments inside the long functions go with
      their own commits below. MCP tool docstrings untouched; 35 API
      descriptions (route and schema docstrings, shown only with DEBUG)
      corrected, the rest of `openapi.json` identical.
- [x] Modern type hints (`ruff --fix` with `UP`, plus the deprecated imports
      by hand), and `UP` switched on. Python 3.10 run; `openapi.json` and the
      MCP schemas identical. The MCP tools keep `typing.Dict` results (the
      `ToolResult` alias): with `dict` the SDK's output schema drops its
      `{"result": …}` wrapper, which the check caught.

**Reports** (a characterization-test commit first, where coverage is thin)
- [x] Complete tax report: one function per section, plus one table-style
      helper. PDF bytes identical.
- [ ] CSV instructions PDF, divided the same way. Bytes identical; the
      committed `csv_import_instructions.pdf` untouched.
- [x] `map_8949_rows_to_field_data` and the transaction history
      `_generate_pdf`. Field data identical in the same order; PDF bytes
      identical.

**Imports and gains**
- [ ] `csv_import.py`:
  - One helper builds a row error.
  - One check per field.
  - `_validate_type_specific`, `_validate_accounts_for_type`,
    `parse_csv_file` and `generate_template_csv` divided.

  The bad-row messages, previews and template are identical.
- [ ] River import: `adapt_river_rows`, `annotate_duplicates`, and the router's
      `execute_river_import`, which keeps calling the module names the tests
      replace.
- [ ] `get_gains_and_losses`. Same keys in the same order, same rounding, same
      log text.
- [ ] The remaining over-limit functions outside the engine:
  - `build_review`, `simulate`, `public_history`, `fill_pdf_form`
  - the MCP client's `request` and the `update_transaction` body
  - `adopt_unversioned` (with the migration tests as the net)
  - `export_transactions_csv` (the column literals stay in `backup.py`)

  Then the tools: `smoke_test.run`, and `irs_new_year`'s `main` and `verify`.

**Ledger engine** (`transaction.py`; `make test` including the slow property
tests, the equivalence check, and `--bench` on every commit)
- [ ] Characterization tests: a locked row refuses edit and delete; anything
      else coverage shows as unrun.
- [ ] Remove the dead `recalculate_subsequent_transactions`. Give the replay
      step (repeated in the recalculation loop) one name.
- [ ] `build_ledger_entries_for_transaction`: one named step per transaction
      type.
- [ ] `maybe_dispose_lots_fifo` and `maybe_transfer_bitcoin_lot`: FIFO, the
      fee disposal and the moved lot as named steps.
- [ ] `create_transaction_record`, `update_transaction_record`,
      `_validate_transaction` and `_enforce_transaction_type_rules`.

**Frontend** (a separate track; `make e2e` and the UI snapshot on every
commit)
- [ ] The UI snapshot script, and a clean first run of the 1.2.2-1 build
      against itself.
- [ ] `TransactionForm.tsx`: a component per transaction type's fields, plus
      the shared fee fields. `#transaction-form` and `#trigger-form-delete`
      stay.
- [ ] `Settings.tsx`: Account, Data Management, and Backup & Restore as their
      own components. `#csv-file-input`, the `aria-label`s and the
      `.settings-option` layout stay.
- [ ] `RiverImport.tsx` and `Dashboard.tsx`, only if still over the limit.

**Keep it clean**
- [ ] Switch on ruff's `C901`, `PLR0911`, `PLR0912` and `PLR0915`, and
      ESLint's `complexity` and `max-lines`. Update `docs/TESTING.md` and
      `docs/MAINTENANCE.md`.

**After the cleanup (a fix, not a cleanup)**
- [ ] `review.fee_price_changes` catches only the no-price error, with a test
      showing the difference. Its own commit.

## 7. Finish

- [ ] Before/after numbers:
  - the longest functions
  - how many are over 50 lines (41 now) and over 100 (17 now)
  - complexity over 10 (29 now)
  - line counts per file
  - the `transaction.py` size
  - the frontend file sizes
- [ ] A clean equivalence run against `v1.2.2-1`, and `--bench` no slower.
- [ ] CHANGELOG (Unreleased, "Development"). `CLAUDE.md` if the key-files
      table changed.
- [ ] A release **only when the owner says so**: full CI and the StartOS VM
      tests (`docs/AGENT-TESTS.md`).

## Findings (noted, not fixed; each needs the owner's OK)

- **A CSV row with an unexpected `fee_usd_typed` value** (say "maybe")
  crashes the import preview with a server error (500) instead of the
  message "Must be yes, no or blank.": the error is built without its
  `severity` (`csv_import._validate_row`). Found by the equivalence check's
  bad inputs; the check records the 500 as today's answer.

- **The lock flag is half-built.** The owner decided to leave it for later; a
  "Next" to-do will decide between finishing it and removing it. Today:
  - PUT accepts `is_locked` but ignores it.
  - A locked row's figures still change when recalculation runs.
  - Ledger Review's fee fix and Delete All ignore locks.
  - No test checks that a locked row refuses edits.
- **`test_stress_and_forms.py`'s `create_tx` swallows failed saves**, and its
  random numbers are unseeded, so a failure there can hide or be hard to
  repeat. These are test-quality issues, not app bugs.
