# To do

Specific items, one line each. Tick `[x]` when done; ticked items are
cleared at the release that ships them (the CHANGELOG has them then).
Plans get their own file in this folder; what's next overall is in
`docs/ROADMAP.md`; the StartOS package's own items are in `startos/TODO.md`.
Rules: `README.md` here.

## Owner

- [ ] Run the password checks on the VM: `cd ~/code/btctx-vm-lab && ./vm.sh start && bash owner-checks.sh` (backup and restore, login cookie, cross-site refusal, password change, login throttle, Reset Login Credentials); results in `scenarios/owner-checks.log`.
- [ ] Finish the 1.2.2 box test on your own server (`startos-box-test-v1.2.2.md`; My Mempool is done). Install 1.2.2-1: the same app, with the real-logo icon.

## Next

- [ ] When Start9 forks the mirror: check `scripts/start9-pull.sh --fork` finds it (if they made a new repository instead, set the repository variable `START9_FORK`). From then on, each release stops if their changes aren't in `startos/` and opens the "Send vX.Y.Z to Start9" issue with the pull-request link (`startos/UPDATING.md`, "After Start9 forks the mirror").
- [ ] The transaction lock flag (`is_locked`) is half-built: nothing in the app can set it (no button; the API ignores it), yet a locked row refuses edits and deletes, while recalculation, Ledger Review's fee fix and Delete All ignore locks. Decide: finish it (a way to lock, respected everywhere, in the CSV export) or remove it.

## Code cleanup

Owner's request (2026-09-29): long functions made concise or divided, and the
code tidy enough to read as professional throughout. The rule for every item:
**no change in behaviour**. Same figures, PDFs, API and messages; the
existing tests pass unchanged. One area per commit, and a new backend module
gets its `hiddenimports` entry in `desktop/BitcoinTX.spec`. It ships with a
normal release (full CI and the VM tests). The plan and its checklist:
`code-cleanup.md`; the standards: `docs/CODE_STYLE.md`.

- [ ] The equivalence check (`scripts/equivalence_check.py`): every figure, PDF, CSV, API answer and MCP output of this checkout compared with a release's.
- [ ] Guard test: every `Transaction` column is in the CSV export or on a "not exported, because…" list (a new column was once left out of the export).

- [ ] Tax report PDF: split `generate_comprehensive_tax_report` (510 lines, `reports/complete_tax_report.py`) into one function per section, with one shared table-style helper instead of the copy-pasted style blocks.
- [ ] CSV instructions PDF: split `generate_csv_instructions_pdf` (395 lines, `backend/scripts/generate_csv_instructions_pdf.py`) the same way.
- [ ] CSV import (`csv_import.py`): `_validate_row` (276 lines), `generate_template_csv` (147), `_validate_type_specific` (105), `parse_csv_file` (102); one helper for the repeated error-building blocks, one check per field.
- [ ] Ledger engine (`transaction.py`, 1,540 lines): `build_ledger_entries_for_transaction` (215), `update_transaction_record` (128), `maybe_transfer_bitcoin_lot` (121), `maybe_dispose_lots_fifo` (113), `create_transaction_record` (112) into named steps; kept as one file (tests replace its `get_btc_price` by name; see `code-cleanup.md`). The tax-invariant tests are the safety net.
- [ ] Gains: `get_gains_and_losses` (179 lines, `calculation.py`).
- [ ] River import: `adapt_river_rows` (149 lines, `river_import.py`) and the router's `execute_river_import` (106, `routers/river_import.py`).
- [ ] Reports: `map_8949_rows_to_field_data` (117 lines, `form_8949.py`) and `_generate_pdf` (109, `transaction_history.py`).
- [ ] Frontend: split `TransactionForm.tsx` (1,049 lines) into a section per transaction type and `Settings.tsx` (799) into one component per card; `RiverImport.tsx` (486) and `Dashboard.tsx` (470) if it helps.
- [ ] Delete the stray empty `backend/services/ __init__.py` (a leading space in its name, there since the first commit).
- [ ] Remove stale or wordy comments and docstrings: history notes ("remains unchanged since … ghostscript"), comments that repeat the code.
- [ ] Modern type hints (`dict`, `list`, `X | None`) instead of `typing.Dict/List/Optional` in 46 files, with ruff's `UP` rules added to lint so it stays that way.
- [ ] Other functions over the limits: `_validate_transaction`, `_enforce_transaction_type_rules`, `_validate_accounts_for_type`, `annotate_duplicates`, `build_review`, `simulate`, `public_history`, `fill_pdf_form`, `adopt_unversioned`, `export_transactions_csv`, the MCP `update_transaction` body and client `request`, and the scripts `smoke_test.run` and `irs_new_year` `main`/`verify`.
- [ ] Keep it clean: once the long functions are divided, add a lint limit on function size and complexity (ruff `C901` / `PLR0911` / `PLR0912` / `PLR0915`, ESLint `complexity` / `max-lines`) so they can't grow back.
- [ ] After the cleanup, a fix in its own commit (a change in behaviour, owner's OK 2026-09-29): `review.fee_price_changes` catches every error while looking up a day's price; catch only the no-price error, with a test.
