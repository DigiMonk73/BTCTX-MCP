# Testing

Every layer runs **without internet and without a running server**: tests use a
temporary SQLite database, an in-process test client, and stubbed BTC prices
(set `BTCTX_LIVE_PRICES=1` to hit the real price APIs). Nothing ever touches
your real database.

## One-time setup

```bash
pip install --require-hashes -r backend/requirements.txt
pip install -r requirements-dev.txt ./mcp_server
cd frontend && npm ci && cd ..
make hooks          # installs the pre-push gate
```

## The layers

| Layer | Command | What it proves | Time |
|---|---|---|---|
| Lint | `make lint` | Python: ruff with all Pyflakes rules (undefined names, unused imports/variables), bare `except`, and in the app code modern syntax (`list[str]`, `X | None`) and a size limit per function (complexity 10, 12 branches, 50 statements, 6 returns; `docs/CODE_STYLE.md`). Frontend: ESLint with zero warnings and a size limit (complexity 15 per function, 400 lines per file; tests exempt) + TypeScript + Vitest unit tests (`src/**/*.test.ts`: form ↔ API mapping, local time, the AI setup prompt, River rows, dashboard totals, the transaction list's pages, server error messages) | secs |
| Unit + integration | `make test-fast` | ~650 tests (backend and MCP server): FIFO lots, gains, fees, holding period, 1099-DA boxes, tax timezone, imports, IRS templates, auth, the AI key, MCP tools | ~1 min |
| Full suite | `make test` | Adds the slow tests (`@pytest.mark.slow`): 250-transaction stress tests and property tests | ~3 min |
| Smoke | `make smoke` | Starts the **real server** and walks it like a user: login → buy → move to cold storage → sell → MCP import → every report → logout | ~15 s |
| Click-through (e2e) | `make e2e` | Playwright drives the real UI in Chromium, in Chicago and Tokyo time: first run, login, every transaction type, edit/delete, the list, dashboard figures, River and CSV imports, every report download, Settings, the widgets. Each test gets its own server on a temp database with stubbed prices | ~5 min |
| Docker | `make docker-smoke` | Builds the image from this checkout and runs CI's container checks on it locally: first-run setup code, smoke test, data on `/data`, health, maintenance CLI | ~5 min |
| Dependency audit | `make audit-deps` | No known-vulnerable Python/npm packages | secs |
| Everything but e2e | `make check` | lint, test, smoke, audit-deps (run `make e2e` separately) | ~4 min |
| Agent release tests | `docs/AGENT-TESTS.md` | An AI agent (or a person) runs the packaged app on a StartOS VM, before each release: install, actions and tasks, the update from the last release, backups, price sources, TLS, a real MCP client, and the Mac app, against a 14-transaction ledger with every figure known | ~4 h |

## When they run

- **Before every `git push`** (`.githooks/pre-push`): lint, static
  Docker/StartOS checks (`backend/tests/pre_commit_tests.py`), fast tests,
  smoke, frontend lint + type check + Vitest (if `frontend/node_modules`
  exists), StartOS package format, type check, lint, bundle and manifest check
  (if `startos/node_modules` exists). A failure blocks the push. Emergency bypass:
  `git push --no-verify`.
- **On GitHub, every push/PR** (`.github/workflows/ci.yml`): Python 3.10 and 3.11
  full suite, frontend build, smoke test, click-through tests (Chromium and WebKit), Docker image build + smoke test
  against the running container, dependency audit, StartOS package checks and
  an x86_64 `btctx.s9pk` packed from this commit's image.
- **Weekly:** `startos-sdk-check.yml` opens an issue when a newer start-sdk or
  start-cli is out; `irs-forms-watch.yml` opens one when the IRS publishes
  new draft forms (to ship as the preview) or the final forms for a new year.
- **On every branch push** (or manually from the Actions tab): builds the macOS
  app, launches it, checks its API answers on `127.0.0.1:8765`, and attaches the
  zipped `.app` to the run.

## Writing a new test

Tests for a bug fix should fail on the old code and pass on the new one. Use
the shared fixtures in `backend/tests/conftest.py`:

```python
def test_my_fix(auth_client):              # logged-in client, temp database
    r = auth_client.post("/api/transactions", json={...})
    assert r.status_code == 200
```

Mark anything slower than ~5 s with `@pytest.mark.slow`.

## Property tests and golden years

- `backend/tests/test_invariants_property.py` (Hypothesis): random valid
  ledgers must keep the tax invariants (balances = lots, gain = proceeds −
  basis, basis conservation, holding periods, Form 8949 = Schedule D = the
  complete report, recalculation and entry order change nothing). 8 examples
  in the fast set, 120 in the slow set. A failure prints the smallest ledger
  that breaks it.
- `backend/tests/test_golden_years.py`: three tax years worked out by hand
  in the docstring, with the exact Form 8949 rows, boxes and Schedule D lines.
  If a change moves one of these numbers, it changes users' tax forms.

## Before/after equivalence check

For a change that must not change behaviour (a refactor, a cleanup, a type
hint pass), compare everything the app produces with a release:

```bash
python scripts/equivalence_check.py            # against v1.2.2-1, ~5 min
python scripts/equivalence_check.py --bench    # plus recalculation time (fails if >5% slower)
python scripts/equivalence_check.py --against v1.3.0
```

It checks out the release in a temporary git worktree and snapshots both
it and this checkout on the same inputs:
- **Ledgers:** the golden ledger, the 65-transaction seed ledger, and 40
  random ledgers from the property test's generator (fixed seeds, in UTC,
  Chicago and Tokyo time).
- **Bad inputs:** each invalid API payload, CSV row and file in
  `scripts/equivalence_inputs.py`.

Everything the app produces is compared:
- database rows
- every API answer (`/openapi.json` included)
- Form 8949 / Schedule D field values, sheet by sheet
- report PDFs: ReportLab's in invariant mode, compared byte for byte, plus
  their text
- CSV files and import previews
- River and entry imports
- every MCP tool's schema and output
- the CSV instructions PDF

The snapshots are JSON files in `.equivalence/` (gitignored). The release's
is reused for the rest of the day while `scripts/equivalence_*.py` are
unchanged. Any difference is printed as a short diff per item and makes it
exit 1. The API descriptions (text only the API docs show, with DEBUG)
are listed but not counted; MCP tool descriptions are, since the AI reads
them.

For the frontend, `frontend/e2e/ui-snapshot.e2e.ts` records every page and
each variant of the transaction form, as the accessibility tree (the labels,
roles and text the click-through tests find elements by) and as HTML; it is
skipped unless `UI_SNAPSHOT_DIR` is set:

```bash
cd frontend
UI_SNAPSHOT_DIR=/tmp/ui-before npx playwright test ui-snapshot --project=chicago
# change the code; the run rebuilds frontend/dist
UI_SNAPSHOT_DIR=/tmp/ui-after npx playwright test ui-snapshot --project=chicago
diff -r /tmp/ui-before /tmp/ui-after
```

## Click-through tests (Playwright)

Specs live in `frontend/e2e/*.e2e.ts`; the config is
`frontend/playwright.config.ts`. `make e2e` rebuilds `frontend/dist`, then
each test starts `scripts/smoke_test.py --serve` on a fresh temp database
(historical price $50,000, current $60,000, block height 900,000).

- Find elements by role and visible label (`getByRole`, `getByLabel`), never
  by CSS class, so the UI polish can restyle freely. If a control has no
  accessible name, give it a `<label htmlFor>` or `aria-label`.
- Figures are read as numbers (`figure()`, `parseFigure()` in
  `e2e/fixtures.ts`), so thousands separators or a Unicode minus don't break
  them.
- The `tokyo` project reruns the create, edit and list specs in UTC+9; the
  `webkit` project (the Mac app's engine) runs with `E2E_WEBKIT=1` in CI.
- A `test.fail()` marks a known bug the test describes correctly (see
  `docs/HARDENING_FINDINGS.md`); remove it with the fix.
- Cloud sessions have Chromium preinstalled (`PLAYWRIGHT_BROWSERS_PATH`); never
  run `playwright install` there. Elsewhere: `npx playwright install chromium`.
- Failures leave a trace and screenshot in `frontend/test-results/`
  (`npx playwright show-trace …`); CI uploads them as an artifact.

## Smoke-testing a live instance

```bash
python scripts/smoke_test.py --url http://127.0.0.1:8080
```

Only against an **empty** instance (a fresh Docker container, never your real
data) — it creates transactions. `make docker-smoke` does this for an image
built from the checkout (`scripts/docker_smoke.sh --keep` leaves the container
running on 127.0.0.1:8778).

## A full test ledger on any server

```bash
python scripts/seed_ledger.py --url https://host:port --user NAME --password-stdin [--ca root-ca.crt] < password-file
```

`scripts/seed_ledger.py` loads 103 transactions from 2023 to 2026 over the
API: `backend/tests/transaction_seed_data.json` and the rows it lacks, so
that every year has every kind of transaction and every report has entries
in each part (every Form 8949 box of 2024, 2025 and 2026), in any tax
timezone, with every USD
value a price lookup would fill already given. It is the ledger for the
StartOS test VM, and for a box: export it there as CSV (Settings) and
import that into an empty ledger. Neither it nor the test data ships in
any build (the Mac app leaves out `backend/tests/`; Docker never had it). It
loads with the price source Off and contacts nothing but the server. It
refuses a ledger that has transactions, and the Mac app's address
(`127.0.0.1:8765`) outright. `--setup-code` claims a fresh Docker install
first. The app ships the 2026 drafts as a preview until 2027-01-01; to keep
them on a test server after that, or on an older version, install them
there (`python -m backend.cli install-draft-forms`, see
docs/IRS_FORM_GENERATION.md, "Draft forms: the preview, and test
installs"). On the
StartOS test VM, the lab's `tools/vmtest seed` does both.
`backend/tests/test_seed_ledger.py` runs it against the in-process app.

## Trying a branch in a browser

```bash
make preview PY=.venv/bin/python   # http://127.0.0.1:8777
```

`scripts/preview.py` builds the frontend and serves the checked-out code on
a throwaway database (deleted when it stops) with the smoke test's stubbed
offline prices, logged in as the smoke test's account (`SMOKE_USER`,
`SMOKE_PASSWORD` in `scripts/smoke_test.py`). Claude's browser preview starts
it from `.claude/launch.json` ("preview").

## Schema migrations

`backend/tests/test_migrations.py` checks that the migrations and the models
describe the same schema, and upgrades a database written by the real v0.7.0
code (`backend/tests/fixtures/v0_7_0.db`), including older variants and
restored backups. CI also starts the Docker image on that database and checks
the upgrade (`scripts/check_upgraded_instance.py`). Every test database is
built by the migrations, not `create_all()`.

## Yearly IRS templates

`python scripts/irs_new_year.py YEAR --check` verifies an installed year's
templates; `backend/tests/test_irs_templates.py` runs the same checks for
every bundled year on each test run. See docs/IRS_ANNUAL_FORM_UPDATE.md.
`backend/tests/test_draft_forms.py` covers the draft forms (the shipped
preview and its cut-off, a test install's) with a stand-in draft made from
the newest bundled form, and checks the shipped draft itself.
