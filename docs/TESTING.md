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
| Lint | `make lint` | Python: ruff with all Pyflakes rules (undefined names, unused imports/variables) + bare `except`. Frontend: ESLint with zero warnings + TypeScript | secs |
| Unit + integration | `make test-fast` | ~285 tests: FIFO lots, gains, fees, holding period, 1099-DA boxes, tax timezone, imports, IRS templates, auth, MCP tools | ~1.5 min |
| Full suite | `make test` | Adds the 250-transaction stress tests (`@pytest.mark.slow`) | ~3 min |
| Smoke | `make smoke` | Starts the **real server** and walks it like a user: login → buy → move to cold storage → sell → MCP import → every report → logout | ~15 s |
| Dependency audit | `make audit-deps` | No known-vulnerable Python/npm packages | secs |
| Everything | `make check` | All of the above | ~4 min |

## When they run

- **Before every `git push`** (`.githooks/pre-push`): lint, static
  Docker/StartOS checks (`backend/tests/pre_commit_tests.py`), fast tests,
  smoke, frontend lint + type check. A failure blocks the push. Emergency bypass:
  `git push --no-verify`.
- **On GitHub, every push/PR** (`.github/workflows/ci.yml`): Python 3.10 and 3.11
  full suite, frontend build, smoke test, Docker image build + smoke test
  against the running container, dependency audit.
- **On pushes to `main`** (or manually from the Actions tab): builds the macOS
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

## Smoke-testing a live instance

```bash
python scripts/smoke_test.py --url http://127.0.0.1:8080
```

Only against an **empty** instance (a fresh Docker container, never your real
data) — it creates transactions.

## Yearly IRS templates

`python scripts/irs_new_year.py YEAR --check` verifies an installed year's
templates; `backend/tests/test_irs_templates.py` runs the same checks for
every bundled year on each test run. See docs/IRS_ANNUAL_FORM_UPDATE.md.
