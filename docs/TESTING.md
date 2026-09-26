# Testing

Every layer runs **without internet and without a running server**: tests use a
temporary SQLite database, an in-process test client, and stubbed BTC prices
(set `BTCTX_LIVE_PRICES=1` to hit the real price APIs). Nothing ever touches
your real database.

## One-time setup

```bash
pip install -r backend/requirements.txt -r requirements-dev.txt ./mcp_server
cd frontend && npm ci && cd ..
make hooks          # installs the pre-push gate
```

## The layers

| Layer | Command | What it proves | Time |
|---|---|---|---|
| Lint | `make lint` | Python: ruff with all Pyflakes rules (undefined names, unused imports/variables) + bare `except`. Frontend: ESLint with zero warnings + TypeScript + Vitest unit tests (`src/**/*.test.ts`: form ↔ API mapping) | secs |
| Unit + integration | `make test-fast` | ~285 tests: FIFO lots, gains, fees, holding period, 1099-DA boxes, tax timezone, imports, IRS templates, auth, MCP tools | ~1.5 min |
| Full suite | `make test` | Adds the 250-transaction stress tests (`@pytest.mark.slow`) | ~3 min |
| Smoke | `make smoke` | Starts the **real server** and walks it like a user: login → buy → move to cold storage → sell → MCP import → every report → logout | ~15 s |
| Click-through (e2e) | `make e2e` | Playwright drives the real UI in Chromium, in Chicago and Tokyo time: first run, login, every transaction type, edit/delete, the list, dashboard figures, River and CSV imports, every report download, Settings, the widgets. Each test gets its own server on a temp database with stubbed prices | ~5 min |
| Dependency audit | `make audit-deps` | No known-vulnerable Python/npm packages | secs |
| Everything | `make check` | All of the above | ~4 min |

## When they run

- **Before every `git push`** (`.githooks/pre-push`): lint, static
  Docker/StartOS checks (`backend/tests/pre_commit_tests.py`), fast tests,
  smoke, frontend lint + type check. A failure blocks the push. Emergency bypass:
  `git push --no-verify`.
- **On GitHub, every push/PR** (`.github/workflows/ci.yml`): Python 3.10 and 3.11
  full suite, frontend build, smoke test, click-through tests (Chromium and WebKit), Docker image build + smoke test
  against the running container, dependency audit.
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
data) — it creates transactions.

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
