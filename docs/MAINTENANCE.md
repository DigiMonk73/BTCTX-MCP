# Maintenance Guide

Routine upkeep: dependency updates, security advisories, deprecations, and
the yearly IRS form update. For how the test suite works, see
[TESTING.md](TESTING.md).

**Last reviewed:** 2026-09-23

---

## Yearly: IRS forms

Once the IRS publishes the **final** Form 8949 and Schedule D for a new tax
year (usually December–January):

```bash
python scripts/irs_new_year.py YYYY
```

It downloads the forms from irs.gov, refuses drafts and wrong-year PDFs,
checks every field name the app writes, checks the checkbox order, diffs field
names against the previous year, installs the templates under
`backend/assets/irs_templates/YYYY/`, and runs
`backend/tests/test_irs_templates.py`. Then add the year to `verified_years`
in `get_8949_field_config()` (`backend/services/reports/form_8949.py`).
Other options: `YYYY --check` (verify an installed year), `YYYY --from-dir DIR`
(use PDFs you downloaded yourself).

The **IRS forms watch** workflow (`.github/workflows/irs-forms-watch.yml`)
runs `--watch` weekly November–March and fails (emailing the repo owner) when a
new final year is out.

Full runbook, including what to do when the IRS renames fields:
[IRS_ANNUAL_FORM_UPDATE.md](IRS_ANNUAL_FORM_UPDATE.md).

---

## Checks to run

```bash
make test        # full hermetic suite (temp DB, stubbed prices, no server)
make test-fast   # same minus slow stress tests
make smoke       # real server on a temp DB, driven end to end
make lint        # ruff + frontend eslint/tsc/vitest
make e2e         # Playwright click-through (Chromium, Chicago + Tokyo time)
make audit-deps  # pip-audit + npm audit
make check       # lint, test, smoke, audit-deps (CI also runs e2e, StartOS and Docker/macOS builds)
```

`make hooks` installs the pre-push gate (`.githooks/pre-push`). Install dev
tools with:

```bash
pip install -r backend/requirements.txt -r requirements-dev.txt ./mcp_server
```

---

## Updating a dependency

Python dependencies are **exact-pinned** (`==`) in `backend/requirements.txt`
so Docker, macOS and CI builds are reproducible. Desktop-only packages
(`pyinstaller`, `pywebview`) are in `desktop/requirements.txt` with `>=`
minimums; dev tools (`ruff`, `pip-audit`) are in `requirements-dev.txt`.
Frontend packages are in `frontend/package.json` / `package-lock.json`.

1. Read the package changelog for breaking changes.
2. Edit the version, then `pip install -r backend/requirements.txt`.
3. Run `make check`.
4. If the package affects PDFs (pypdf, reportlab), open a generated Form 8949,
   Schedule D and Complete Tax Report and look at them. `make test` covers
   field-level content, not layout.
5. If it's a new package used by the backend, add it to `hiddenimports` in
   `desktop/BitcoinTX.spec`.
6. Commit one package (or one coupled group) per commit, e.g.
   `deps: update sqlalchemy 2.0.54 → 2.0.55`.

To roll back, restore the previous `backend/requirements.txt` from git,
reinstall, and rerun `make check`.

### When to update

- **Immediately:** security advisories (`make audit-deps`, also run in CI),
  bugs that affect us.
- **Periodically:** patch/minor versions (`pip list --outdated`,
  `npm outdated` in `frontend/`).
- **Deliberately:** major versions, after reading the changelog.

### Dependabot

`.github/dependabot.yml` opens pull requests against `develop` every week:
one grouped PR per directory for minor and patch updates (`backend/`,
`mcp_server/`, `frontend/`, `startos/`), majors one per PR, and one PR for
the GitHub Actions in `.github/workflows/`. CI runs on each. Treat them like
a hand update: read the changelogs, follow the steps above for PDF packages,
merge into `develop`. Nothing reaches `main` before a release.

- GitHub reads the file from the default branch (`main`): an edit takes
  effect once `main` is fast-forwarded to `develop`.
- Every entry needs `target-branch: develop`, or its PRs target `main`.
  Keep **Dependabot security updates** off in the repository settings:
  `target-branch` doesn't apply to them, so their PRs would target `main`.
  Alerts still show on the Security tab, and the weekly PRs pick up fixed
  versions.
- Ignored: `@playwright/test`, the deferred upgrades below (each rule
  says why; remove it when the upgrade is unblocked), and in `startos/`
  `@start9labs/start-sdk`, `mempool-startos` and `tor-startos`, which are
  bumped by hand (`startos/UPDATING.md`, "Bumping the SDK"), and TypeScript
  6.1 or newer there (the SDK's typescript-eslint needs < 6.1; it moves with
  the SDK).
- `startos/.github/workflows/` (Start9's standard files) is not scanned.

### Audit scope

`make audit-deps` and the CI audit job check `backend/requirements.txt` (what
ships) and `requirements-dev.txt` (test/CI tools) with no exceptions. Test-only
packages belong in `requirements-dev.txt`, never in `backend/requirements.txt`,
which is what the Docker image installs.

---

## Current versions and risk

From `backend/requirements.txt`:

| Package | Pinned | Risk | Notes |
|---------|--------|------|-------|
| `fastapi` | 0.141.1 | Caution | Update together with starlette and pydantic; stay inside fastapi's declared ranges. fastapi ≥ 0.130 requires Python ≥ 3.10 |
| `starlette` | 1.7.0 | Caution | Pinned explicitly. The app uses `lifespan`, not `on_event` |
| `pydantic` | 2.13.5 | Caution | V2-style code throughout (`ConfigDict`, `field_validator`) |
| `uvicorn` | 0.53.0 | Caution | Check starlette compatibility |
| `sqlalchemy` | 2.0.54 | Caution | 2.0-style code; watch for deprecation removals. After updating, the FIFO/lot tests are the ones that matter |
| `httpx` | 0.28.1 | Caution | All outside requests, only through `services/outbound.py`; also used by the MCP server |
| `socksio` | 1.0.0 | Low | SOCKS proxy for httpx (Settings → Privacy & Network, e.g. Tor) |
| `alembic` | 1.20.0 | Caution | Runs at every start (`backend/migrate.py`); after an update run `test_migrations.py` |
| `requests` | 2.34.2 | Low | |
| `python-multipart` | 0.0.32 | Caution | "Patch" releases add hardening limits (header count, boundary size) |
| `bcrypt` | 5.0.0 | Caution | 5.x raises on passwords > 72 bytes; `User.set_password()` rejects them first (`test_password_migration.py`) |
| `cryptography` | 50.0.1 | Low | Encrypted backups; after a major bump, verify an old `.btx` backup still restores |
| `itsdangerous` | 2.2.0 | Low | Session cookie signing |
| `python-dotenv` | 1.2.3 | Low | Only `load_dotenv` is used |
| `python-dateutil` | 2.9.0.post0 | Low | |
| `tzdata` | 2026.4 | Low | Timezone rules for the tax timezone; update yearly |
| `pypdf` | 6.19.0 | High | Fills and flattens the IRS forms (`backend/services/reports/pdf_form_filler.py`) and merges sheets. Majors can change fill behavior |
| `reportlab` | 4.4.10 | High | Complete Tax Report and transaction history PDFs. Stay on 4.4.x (see below) |
| `pytest` | 9.1.1 | Low | Test only (`requirements-dev.txt`) |
| `hypothesis` | 6.168.1 | Low | Test only: property tests |

Frontend (from `frontend/package.json`): React 18, Vite 6, TypeScript 5.9,
ESLint 9, axios 1.20, lucide-react. Docker frontend build and CI use Node 22.
`@playwright/test` is pinned exactly to match the browsers preinstalled in
cloud sessions (see `docs/TESTING.md`): don't bump it on its own. start-sdk:
see `startos/UPDATING.md`.

### Deferred upgrades

Each was skipped deliberately; revisit when the unblock condition is met.
Dependabot ignores each (`.github/dependabot.yml`); drop its rule when you
take the upgrade.

| Package | Deferred to | Why | Unblock when |
|---------|-------------|-----|--------------|
| `reportlab` | 4.5.x | Output drift risk: changes to acroform `None` handling, `cssParse` colors, table bounds errors | Someone compares generated PDFs before/after and accepts the differences |
| `typescript` | 6.0 | Breaking "bridge" release toward TS 7 | typescript-eslint supports it and the ecosystem settles |
| `eslint` | 10.x | Major (eslintrc removal, Node ≥ 20.19) | Move together with `eslint-plugin-react-hooks` 7.x, whose preset shapes our flat config uses |
| `react` / `vite` | 19.x / 7+ | Owner decision to stay on React 18 / Vite 6 (6.4 still gets security backports). `@vitejs/plugin-react` 6 needs Vite 8, so it stays on 4.x | Owner opts in to a migration pass |
| `sqlalchemy` | 2.1.x | Requires Python ≥ 3.11; BitcoinTX supports 3.10 (CI tests it) | Python 3.10 support is dropped (3.10 reaches end of life in October 2026); then run the FIFO/lot and migration tests |

---

## Database migrations

The schema is owned by Alembic migrations in `backend/migrations/versions/`.
Nothing calls `create_all()`: every start runs `backend/migrate.py`, which
backs the database up to `<db dir>/backups/` and upgrades it when a newer
revision exists. Restored backups are upgraded the same way before they
replace the live database.

**Changing the schema** (a new column, table or index):

1. Change the model in `backend/models/`.
2. Generate the migration against a scratch database at the current head:
   ```bash
   DATABASE_FILE=/tmp/scratch.db python -c "from backend.database import init_db; init_db()"
   DATABASE_FILE=/tmp/scratch.db alembic revision --autogenerate --rev-id 0005 -m "add foo to transactions"
   ```
   Use the next number as `--rev-id` (sequential ids keep the history readable).
3. Read the generated file. Autogenerate misses renames (it emits drop + add,
   which loses data) and server defaults; SQLite column changes run as
   `batch_alter_table` (copy, swap), which `env.py` enables. A new NOT NULL
   column needs a `server_default` or a data backfill step.
4. `pytest backend/tests/test_migrations.py`. `test_models_and_migrations_agree`
   fails until models and migrations describe the same schema, and the
   v0.7.0 fixture tests prove old databases still upgrade.
5. Mention it in `docs/CHANGELOG.md`.

**Rules**

- Never edit a migration that has been released; add a new one.
- Migrations must not import from `backend/models` (models keep changing; a
  migration is a frozen snapshot). Use `sa.` types and plain SQL.
- Upgrades must preserve data. `downgrade()` is best effort and not run by
  the app; going back a version means restoring the copy in `backups/`.
- `backend/tests/fixtures/v0_7_0.db` was written by the real v0.7.0 code.
  Don't regenerate it with current code.

## Deprecations

Check for new deprecation warnings after any update:

```bash
python -m pytest -q -m "not slow" -W default 2>&1 | grep -i "deprecat"
```

Fix them before the next major release of the package turns them into errors,
and record anything you can't fix yet in the deferred table above.

---

## Checklist

- [ ] `make audit-deps`, fix or record any advisory
- [ ] `pip list --outdated` and `npm outdated`; take safe patch/minor updates
- [ ] Check for new deprecation warnings
- [ ] Revisit the deferred table
- [ ] `make check`
- [ ] Schema changed? A migration exists and `test_migrations.py` passes
- [ ] Yearly: `python scripts/irs_new_year.py YYYY`, bump `tzdata`
- [ ] Update "Last reviewed" above
