# Code style

How code in this repository is written, for people and AI assistants alike.
Lint enforces what a tool can (`ruff.toml`, `frontend/eslint.config.js`);
the rest is on whoever writes or reviews the change. When a rule and the
surrounding code disagree, follow the rule and fix the code nearby only in a
cleanup commit, never inside a behaviour change.

## Python

1. **A function does one thing, and its name says what**: a verb for an
   action (`add_fee_disposal`), a noun for a value (`fee_disposals`).
   Limits: complexity 10, 12 branches, 50 statements, 6 returns.
2. **Divide a long function into named steps** that are real units: one PDF
   section, one validation rule, one transaction type's ledger lines. A step
   called once is fine. What isn't: a wrapper that only renames another call,
   a class or parameter added "for later", a helper shorter than its name.
3. **Comments say why**: a tax rule, an IRS line, a past bug, a platform
   limit. Never what the next line does, and never the code's history
   ("now", "NEW", "used to", "no longer"); that belongs in the CHANGELOG and
   git. A past bug is a good reason: say what the code prevents, not what
   it once did.
4. **Docstrings.** A module's opens with what the module is for, never its
   file path. A public function gets one when its name and signature don't
   say enough; a private helper only when needed. MCP tool, pydantic schema
   and API route docstrings are user-facing text (the AI and the API docs
   show them): change them only on purpose.
5. **No banner or divider comments** (`# ---- Section ----`). Order the
   module instead: public functions first, then helpers in the order they
   are used. A plain one-line comment may title a group.
6. **No dead code**: no unused function, parameter or import, no
   commented-out code.
7. **One idiom for each thing**:
   - Type hints: `list[str]`, `dict[str, Any]`, `X | None` (ruff `UP`).
   - Money: `Decimal`, with a named constant per precision (`CENT`, `SATS`)
     rather than repeated `Decimal("0.01")`.
   - Errors: `HTTPException` with the exact user-facing text; the tests, the
     frontend and the MCP guide match on it.
   - `except`: the narrowest exception the code expects.
   - Logs: no amounts, dates or addresses at INFO or above
     (`test_privacy.py`); no DEBUG line that only echoes a function's input
     or every row.
8. **Tests** follow the same rules but are exempt from the size limits: a
   scenario can be long. A bug fix gets a test that fails on the old code.

## Frontend (TypeScript/React)

1. One component per file, doing one job: a form section per transaction
   type, a component per Settings card. Pure logic lives in `src/utils/`
   with a Vitest test.
2. The same comment rules as Python.
3. The e2e tests find elements by label, role and text. Every label,
   `htmlFor`/`id`, role and `aria-label` is part of the interface; so are the
   ids and classes other components or tests use (`#transaction-form`,
   `#trigger-form-delete`, `#csv-file-input`, `.settings-option`…).
4. CSS only from `src/styles/theme.css` and `components.css`, and only what
   Safari 15 supports (the Mac app's WebKit).
5. Limits: complexity 15 per function, 400 lines per file.

## Changing code without changing behaviour

A refactor or cleanup must leave every figure, PDF, CSV, API answer, MCP tool
output, message and database row as it was, with the existing tests
unedited. `scripts/equivalence_check.py` compares all of them against a
release (`docs/TESTING.md`). Found a bug on the way? Note it and fix it in
its own commit, with its own test.
