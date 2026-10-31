# Maintenance Guide

Routine upkeep: dependency updates, security advisories, deprecations, and
the yearly IRS form update. For how the test suite works, see
[TESTING.md](TESTING.md).

**Last reviewed:** 2026-10-18

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
runs `--due` weekly, all year, and opens an issue (label `claude`) when the
IRS publishes a new year's drafts (ship them as the preview) or its final
forms.

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
pip install --require-hashes -r backend/requirements.txt
pip install -r requirements-dev.txt ./mcp_server
```

---

## Scheduled checks

GitHub runs these (the owner, 2026-10-31: after 2.0.0 the routine checks cost
no Claude tokens and no time on the owner's Mac). Each leaves its result in an
issue or a pull request, which the week's work starts from.

| What | When | Where it shows |
|---|---|---|
| Monday report (`monday-report.yml`) | Mondays, 13:07 UTC | one issue, "Monday report: what needs attention", edited in place |
| Start9 watch (`start9-watch.yml`) | Mondays, 08:23 UTC | an issue labelled `start9` for each new thing |
| IRS forms watch (`irs-forms-watch.yml`) | Mondays, 14:00 UTC | an issue labelled `claude` |
| Price history watch (`price-history-watch.yml`) | the 3rd of each month | an issue labelled `claude`, if Bitstamp changed |
| Dependabot (`dependabot.yml`) | monthly | grouped pull requests into `staging` |

GitHub reads a schedule, and `dependabot.yml`, only from the default branch
(`main`): a change to any of them takes effect once `main` is fast-forwarded
to `develop`. `workflow_dispatch` runs a workflow by hand from the Actions tab,
once the file is on `main` too.

### The Monday report

`.github/workflows/monday-report.yml` runs `scripts/monday-report.sh` from
`develop` (so a fix to the script needs no release) with the job's own token,
read access to the code and write access to issues, and nothing else: no secret
of its own, no trigger a stranger can pull. Start9's fork and the mirror are
public, so the same token reads them. It opens the issue "Monday report: what
needs attention" if none is open, and otherwise edits that one in place (a body
edit sends no notification; close the issue once it has been read, and the next
Monday opens a new one). It lists:

- **Open `tax-figures` issues:** number, title, age and who has it (the
  `claude` or `owner` label), oldest first. A figure could be wrong, so these
  come first.
- **Outside reports with no answer:** open issues on this repository, on
  Start9's fork (Start9-Community/BTCTX-StartOS) and on the mirror
  (DigiMonk73/BTCTX-StartOS) that someone other than the owner or a bot opened
  and the owner hasn't commented on. An answer is promised within a week
  (AGENTS.md, "Bugs and security"); the ones past it are marked. The mirror's
  Issues are off, and the report says if that changes.
- **Open `start9` issues:** what `start9-watch.yml` and the owner's own notes
  have opened that nobody has taken yet.

A title is someone else's text, so the report shows it in a code span and cut
to 100 characters: it can't link, mention or refer to anything. The report
never names security advisories, not even how many are waiting: a public count
would hint at a problem that isn't fixed yet (`SECURITY.md`). It says nothing
about CI, open pull requests or Dependabot's: the Actions and Pull requests
tabs show them. If a repository can't be read (a renamed fork), the report
says so and the run fails after it has published, so a lasting break doesn't go
unnoticed.

`scripts/monday-report.sh --dry-run` prints the report and what it would do,
and changes nothing (it needs `gh` signed in and `jq`).
`backend/tests/test_monday_report.py` runs it against a stand-in `gh`.

---

## Updating a dependency

**Pinning.** Everything we name to ship or build with is pinned exactly, so
it changes only by pull request:

- Python: `==` in `backend/requirements.in` (the app),
  `desktop/requirements.in` (the Mac app's build tools),
  `.github/release-tools/requirements.in` (what `release.yml` builds the
  connector with) and `requirements-dev.txt` (test and CI tools).
- Each `requirements.in` has a lock beside it, `requirements.txt`, compiled
  by `make lock` (`uv pip compile`): every package, indirect ones too, at a
  fixed version with its hashes, for Linux and macOS and Python 3.11 and up
  (`--universal`). What ships installs only from a lock, with
  `--require-hashes`: the Docker image (wheels only, `--only-binary :all:`),
  the Mac app (`desktop/build-mac.sh` installs both locks; `desktop/`'s is
  held to `backend/`'s versions) and the connector's PyPI build. The CI jobs
  that run the app install the same lock; only the dev tools and the
  connector under test install without hashes.
- JavaScript: `frontend/package-lock.json` and `startos/package-lock.json`
  (`npm ci` installs exactly what they hold).
- Docker base images: tag and digest (`python:3.13-slim@sha256:…`). One
  package moves on its own: the final stage upgrades the base's
  `ca-certificates` from Debian's security archive (#638), and the build
  checks the one thing that matters, that neither the system's store nor
  certifi's holds the distrusted emSign ECC Root CA - G3.
- GitHub Actions: a full commit SHA with the release as a comment
  (`actions/checkout@<sha> # v7.0.1`): a tag can be moved, a commit can't.
- start-cli, which packs the StartOS package in CI and the release: a
  release and its SHA-256 from the release notes (`START_CLI_VERSION`,
  `START_CLI_SHA256` in `ci.yml` and `release.yml`), checked before it runs.
  It follows Start9's newest (`startos/UPDATING.md`, "Bumping the SDK").
- The exception is the AI connector (`mcp_server/pyproject.toml`): it is
  installed next to other software, so its dependencies take ranges, each
  capped below the next major version (`httpx>=0.27,<1`), except `tzdata`,
  timezone data numbered by year, which is meant to float. Its build
  backend takes a capped range too (`setuptools>=77,<85`); the release
  builds with the locked setuptools, which must stay inside it.

The CI runtimes and GitHub's runner images follow their release line: the
Python tests run on 3.11 (the oldest supported, from source and the AI
connector) and 3.13 (Docker, StartOS and the Mac app), both in "CI
passed", and the other jobs on 3.13 and `node-version: 24`. Dependabot proposes the updates
(below). The Mac build uses the `pip` its venv comes with and installs no
`wheel`; proxy-tools (under pywebview), published only as source, is built
with the locked setuptools (`--no-build-isolation`), since pip doesn't check
the hashes of what it fetches for an isolated build.

1. Read the package changelog for breaking changes.
2. Edit the version in the `requirements.in`, run `make lock` (it needs `uv`,
   from `requirements-dev.txt`), then
   `pip install --require-hashes -r backend/requirements.txt`.
3. Run `make check`.
4. If the package affects PDFs (pypdf, reportlab, Pillow), open a generated
   Form 8949, Schedule D and Complete Tax Report and look at them. `make test`
   also reads the printed forms back (`test_printed_forms.py`), but not how the
   page looks. Compare them with the old version's too: load the reference
   test ledger (`scripts/seed_ledger.py`) into a throwaway server
   (`scripts/smoke_test.py --serve`) from `develop`'s environment and from
   the update's, print the same years' PDFs from each, and compare them byte
   for byte (the forms) and by text (the reports, whose "Generated" time
   differs). `scripts/equivalence_check.py` can't: it runs both sides in one
   environment, so it never sees a package change (#571).
5. If it's a new package used by the backend, add it to `hiddenimports` in
   `desktop/BitcoinTX.spec`.
6. Commit one package (or one coupled group) per commit, e.g.
   `deps: update sqlalchemy 2.0.54 → 2.0.55`.

To roll back, `git revert` the update's commit (it brings back the pins and any
test the update changed, such as ReportLab 5's refusal tests in
`test_hardening_edges.py`), reinstall, and rerun `make check`.

The indirect packages move only when a lock is recompiled and a pin needs
it, so they are refreshed once a month, after the month's Dependabot pull
requests: Claude runs `make lock LOCK_ARGS=--upgrade` in a pull request
reviewed like any update (sooner for a security fix in one).
`test_pinning.py` fails when a lock is older than its pins, lacks hashes or
the `make lock` command, or when the Mac lock and the backend's disagree.

### When to update

- **Immediately:** security advisories (`make audit-deps`, also run in CI),
  bugs that affect us.
- **Periodically:** patch/minor versions (`pip list --outdated`,
  `npm outdated` in `frontend/`).
- **Deliberately:** major versions, after reading the changelog.

### Dependabot

`.github/dependabot.yml` opens pull requests against `staging` once a month
(the owner, 2026-10-31): one grouped PR per directory for minor and patch
updates (`backend/`, `mcp_server/`, `desktop/`, `.github/release-tools/`, the
dev tools in `requirements-dev.txt`, `frontend/`, `startos/`), majors one per
PR, one PR for the GitHub Actions in `.github/workflows/`, and one for the
Dockerfile's base images when their tags get a new build (Python 3.13 and
Node 24 themselves change only on purpose). CI runs on each. Treat them like
a hand update: read the changelogs, follow the steps above for PDF packages,
merge into `staging` (`develop` takes them with the daily merge,
AGENTS.md, "Branches"). While 2.0 is built on `2.0`, they reach it only
with `develop` (`make catch-up-2.0`, or the lead's `develop` merge), never
by a pull request of their own into `2.0`. Nothing reaches `main` before a
release. Dependabot never merges one by itself: auto-merge is turned on by
hand, after the review (AGENTS.md, "Pull requests").

- GitHub reads the file from the default branch (`main`): an edit takes
  effect once `main` is fast-forwarded to `develop`.
- Every entry needs `target-branch: staging`, or its PRs target `main`.
  Keep **Dependabot security updates** off in the repository settings:
  `target-branch` doesn't apply to them, so their PRs would target `main`.
  Alerts still show on the Security tab, and the monthly PRs pick up fixed
  versions. So a fixed version of a vulnerable package waits up to a month for
  its pull request: `make audit-deps` and the CI audit (each pull request and
  push) show it, and a security fix is taken by hand the same day, as an
  urgent fix (AGENTS.md, "Branches"), never left for the month's run.
- Ignored: `@playwright/test`, the deferred upgrades below (each rule
  says why; remove it when the upgrade is unblocked), and in `startos/`
  `@start9labs/start-sdk`, `mempool-startos` and `tor-startos`, which are
  bumped by hand (`startos/UPDATING.md`, "Bumping the SDK"; the SDK brings
  TypeScript and the other build tools). npm: `@types/node` majors too, since
  it moves with the Node that Docker and CI run. Docker: Python minor and major versions and Node majors, so the
  base images stay `3.13-slim` and `24-slim` and only their digests move.
- The locked directories (`backend/`, `desktop/`, `.github/release-tools/`)
  are `uv` entries: Dependabot edits the pin in `requirements.in` and
  recompiles `requirements.txt` with the command in its header (so the
  header must stay `make lock`'s). `desktop/` updates only pyinstaller,
  pywebview and setuptools (it builds proxy-tools). setuptools is in
  `.github/release-tools/`'s lock too, and the audit reads both locks at
  once, so Dependabot's pull request for one of them fails it: take the
  update in both `requirements.in` files and run `make lock`, in one pull
  request of our own (#759). When a `backend/` PR
  moves a package the Mac lock shares (typing-extensions, cffi…),
  `test_pinning.py` fails on it until `make lock` is run on that branch.
- Dependabot reads a Dockerfile `FROM` only at the start of a line, so the
  Dockerfile isn't indented (`test_pinning.py` checks it).
- `startos/.github/workflows/` (Start9's standard files) is not scanned.
- The dev-tools entry (`/`) would also read `backend/` and `desktop/`, so it
  allows only pytest, pytest-xdist, hypothesis, ruff, pip-audit and uv. A new pinned
  dev tool goes on that list; never one a lock holds (anyio comes from
  `backend/requirements.txt`), or this pip entry would edit the lock.

### Before a Dependabot pull request merges

"CI passed", the one required check, gates every merge, and Claude reads the release notes
first (AGENTS.md, "Pull requests"). Two cases need more than that:

- **The Mac app.** Its build and launch check runs on each pull request,
  but it is not a required check, so auto-merge does not wait for it.
  An update to `backend/` or `desktop/` requirements, or to
  the GitHub Actions (the Mac job uses them too), merges only after that
  run has passed on the pull request's head commit. Claude checks it:
  `gh pr checks <number>` (the "macOS app build + launch check" job). Turn
  on auto-merge only once it is green.
- **Figures and forms.** An update to a package marked High in "Current
  versions and risk" (`pypdf`, `reportlab`), or one that could move a figure
  (`sqlalchemy`, `alembic`, `tzdata`), gets the before-and-after comparison
  in two environments (step 4 of "Updating a dependency":
  `scripts/equivalence_check.py` can't see a package change). An update
  is never meant to move a figure: if none moves, it merges like any
  other; if one does, it stops until the cause is found (AGENTS.md,
  "Reviews", the figures rule).

A Dependabot branch behind `staging` is brought up to date only when it
conflicts (`staging` asks no branch to be up to date), by commenting
"@dependabot rebase" on it, never by merging `staging` into it
(`gh pr update-branch`, or `git merge origin/staging` and a push): Dependabot
stops maintaining a branch once anyone else commits to it. It merges only
once its checks have passed again (AGENTS.md, "Pull requests").

### When an update breaks something

A failing check stops the merge; find out why before anything else.

- **Our code needs a small change:** close Dependabot's pull request and
  make the update in our own, with the fix and a test. (Dependabot stops
  maintaining a branch once someone else commits to it.)
- **The upgrade needs real work, or the release itself is broken:** skip
  it. Add an `ignore` rule to `.github/dependabot.yml` with a one-line
  reason (for the versions that break, e.g. `versions: [">=4.5"]`, so fixes
  below them still come), add a row to "Deferred upgrades" below with an
  "Unblock when" condition, and open an issue labelled `claude` that links
  both. In a grouped pull request, ignore only the package that broke: the
  rest of the group comes back the next month.
- **It would change tax figures or forms:** the owner decides, with the
  before-and-after comparison in front of them.

### Taking a skipped update

When the month's Dependabot pull requests are taken, look at each "Deferred
upgrades" row for a newer release or a fix to the problem. (The Monday report
doesn't: it lists issues, not releases.) A skipped version that
becomes the only one with a security fix fails the audit on every pull
request when the audit scans that package (`make audit-deps`: the app's
Python packages, the dev tools, and high or critical frontend advisories);
for the rest, the Security tab's alerts show it; no workflow reads them, so
look there too. Once the "Unblock when" condition is met,
take the update in a normal pull request with all the checks, remove its
`ignore` rule and its row, and close the issue.

### Audit scope

`make audit-deps` and the CI audit job check the three locks (what ships:
`backend/`, `desktop/` and `.github/release-tools/requirements.txt`, every
package in them) and `requirements-dev.txt` (test/CI tools) with no
exceptions. pip-audit reads only the lock entries for the machine it runs on,
so CI audits on Linux and on macOS (the Mac app's pyobjc packages). Test-only
packages belong in `requirements-dev.txt`, never in `backend/requirements.in`,
which is what the Docker image installs.

---

## Current versions and risk

What each package is pinned to is in `backend/requirements.in` (the test
tools: `requirements-dev.txt`), which Dependabot moves; this table says
what to watch when it does.

| Package | Risk | Notes |
|---------|------|-------|
| `fastapi` | Caution | Update together with starlette and pydantic; stay inside fastapi's declared ranges. fastapi ≥ 0.130 requires Python ≥ 3.10 |
| `starlette` | Caution | Pinned explicitly. The app uses `lifespan`, not `on_event`. From 1.8 it needs Python ≥ 3.11 (#546). After an update, read its middleware, session, `StaticFiles`, `FileResponse` and request-body changes against AGENTS.md's "Security rules" |
| `pydantic` | Caution | V2-style code throughout (`ConfigDict`, `field_validator`) |
| `uvicorn` | Caution | Check starlette compatibility |
| `sqlalchemy` | Caution | 2.0-style code; watch for deprecation removals. After updating, the FIFO/lot tests are the ones that matter |
| `httpx` | Caution | All outside requests, only through `services/outbound.py`, which reads each answer as a stream under a deadline and a size limit (`BoundedClient`: run `test_request_limits.py` after an update); also used by the MCP server |
| `socksio` | Low | SOCKS proxy for httpx (Settings → Privacy & Network, e.g. Tor) |
| `alembic` | Caution | Runs at every start (`backend/migrate.py`); after an update run `test_migrations.py` |
| `requests` | Low | |
| `python-multipart` | Caution | "Patch" releases add hardening limits (header count, boundary size) |
| `bcrypt` | Caution | 5.x raises on passwords > 72 bytes; `User.set_password()` rejects them first (`test_password_migration.py`) |
| `cryptography` | Low | Encrypted backups; after a major bump, verify an old `.btx` backup still restores |
| `itsdangerous` | Low | Signs the session cookie and the login's device cookie (`services/login_throttle.py`) |
| `python-dotenv` | Low | Only `load_dotenv` is used |
| `python-dateutil` | Low | |
| `tzdata` | Low | Timezone rules for the tax timezone, and its `zones` list is the names BitcoinTX accepts (#407): a name a new version dropped, saved before, would count as none chosen where the computer's own zone files lack it (backward links have always been kept); update yearly |
| `pypdf` | High | Fills and flattens the IRS forms (`backend/services/reports/pdf_form_filler.py`) and merges sheets. Majors can change fill behavior |
| `reportlab` | High | Complete Tax Report and transaction history PDFs. Each version is taken after the before-and-after comparison shows both reports the same, object for object, but for the time they were made (5.0.1's: #585; 5.1.0's: #760; 4.5's: #425); a newer one gets the same comparison, and `test_report_safety.py` and `test_hardening_edges.py` with it. ReportLab 5 trusts no host its settings don't name, but still opens any file path it is given: what keeps ledger text from opening or fetching anything is `reports/safe_text.py`, which replaces its two readers in `reportlab.lib.utils` (`open_for_read_by_name`, `rlUrlRead`), so a release that renames them or reads around them fails those tests |
| `pytest` | Low | Test only (`requirements-dev.txt`) |
| `hypothesis` | Low | Test only: property tests. Newer versions need Python 3.11, the minimum since #546: Dependabot proposes them |

Frontend (from `frontend/package.json`): React 19, Vite 8 (its build target
pinned to Safari 15 in `frontend/vite.config.ts`, for the Mac app's WebKit:
Vite 8's own default is Safari 16.4), TypeScript 5.9,
ESLint 10 (with eslint-plugin-react-hooks 7, one of whose React Compiler checks
`frontend/eslint.config.js` turns off, saying why), axios 1, lucide-react;
dev only, Testing Library and jsdom, for the tests that mount the
transaction form (`src/test/renderForm.tsx`, #351).
Docker frontend build and CI use Node 24.
`@playwright/test` is pinned exactly in `frontend/package.json` (1.61 or
later, for Ubuntu 26.04) and bumped only on purpose,
never by Dependabot: a bump runs `npx tsc -b`, `npx tsc -p e2e` (the specs,
which `tsc -b` leaves out), `npm run lint`, `npm test`
and both click-through suites (`npx playwright test --project=chicago
--project=tokyo`, then `E2E_WEBKIT=1 npx playwright test --project=webkit`)
after `npx playwright install chromium webkit`, reads Playwright's release
notes for every version in between, and lets CI's `e2e` jobs (Chromium and
WebKit) decide on Linux. The browsers each version needs come with that
install, so nothing else pins it (cloud sessions: `docs/TESTING.md`). CI's `e2e` job runs on
`ubuntu-latest` (26.04 since October 2026; Playwright supports it from 1.61).
WebKit's suite runs on a Mac only from macOS 15
(Playwright 1.58 and 1.59 dropped 13 and 14). start-sdk: see `startos/UPDATING.md`.

### Deferred upgrades

Each was skipped deliberately; revisit when the unblock condition is met.
Dependabot ignores each (`.github/dependabot.yml`); drop its rule when you
take the upgrade.

| Package | Deferred to | Why | Unblock when |
|---------|-------------|-----|--------------|
| `typescript` | 6.0 | Breaking "bridge" release toward TS 7 | typescript-eslint supports it and the ecosystem settles |
| `sqlalchemy` | 2.1.x | A minor version with breaking changes, not taken in 1.2.9 (#425). Python is no longer in the way: 3.11 is the minimum since #546 | The owner decides to take it. Then run the FIFO/lot and migration tests |

---

## Database migrations

The schema is owned by Alembic migrations in `backend/migrations/versions/`.
Nothing calls `create_all()`: every start runs `backend/migrate.py`, which
backs the database up to `<db dir>/backups/` and upgrades it when a newer
revision exists. A restored backup is upgraded the same way, then only
the rows of the tables and columns the migrations make are copied into a
new database made by the migrations, which replaces the live one
(`services/backup.restore_backup`): a new table or column needs nothing
more for restores.

**Changing the schema** (a new column, table or index):

1. Change the model in `backend/models/`.
2. Generate the migration against a scratch database at the current head:
   ```bash
   DATABASE_FILE=/tmp/scratch.db python -c "from backend.database import init_db; init_db()"
   DATABASE_FILE=/tmp/scratch.db alembic revision --autogenerate --rev-id 0102 -m "add foo to transactions"
   ```
   Use the next number after the head as `--rev-id` (sequential ids keep the
   history readable): 0102 follows 2.0.0's 0101.
3. Read the generated file. Autogenerate misses renames (it emits drop + add,
   which loses data) and server defaults; SQLite column changes run as
   `batch_alter_table` (copy, swap), which `env.py` enables. A new NOT NULL
   column needs a `server_default` or a data backfill step.
4. `pytest backend/tests/test_migrations.py`. `test_models_and_migrations_agree`
   fails until models and migrations describe the same schema, and the
   v0.7.0 fixture tests prove old databases still upgrade.
5. Mention it in `docs/CHANGELOG.md`.

**Rules**

- Never edit a migration that has been released, or published in a 2.0
  pre-release; add a new one.
- Migrations must not import from `backend/models` (models keep changing; a
  migration is a frozen snapshot). Use `sa.` types and plain SQL.
- Upgrades must preserve data. `downgrade()` is best effort and not run by
  the app; going back a version means restoring the copy in `backups/`.
- `backend/tests/fixtures/v0_7_0.db` was written by the real v0.7.0 code.
  Don't regenerate it with current code. Nor `old_accounts_1x.db` (1.x's
  code wrote it: `fixtures/make_old_accounts_db.py`) or `reference_1x.db`
  (the last 1.x release's, `RELEASE` in `fixtures/make_reference_1x_db.py`).

**2.0's migrations** (on the `2.0` branch while 2.0 is built; plan:
`docs/temp/2.0-accounts.md` 5.3 and 7.2):

- Their ids start at 0100, so 1.x, numbering on from its own head on
  `develop`, never takes one of them (Alembic refuses two revisions with one
  id, and no merge revision mends it).
- The first, `0100_exchanges_and_kinds.py`, carries the marker
  `STARTS_2_0 = True`, and only it. `migrate.py` finds it by that marker
  (`first_2_0`) and walks the chain (`revisions_of_2_0`): it and every
  revision above it are 2.0's, every
  other one 1.x's. A database at a 1.x revision (or unversioned) gets its
  copy before the upgrade as the kind `pre-2.0`
  (`backups/btctx-pre-2.0-from-<revision>-<time>.db`), never pruned: the
  way back to 1.x (the README's "Going back to 1.x"; a failed upgrade,
  which changes nothing, removes its own). `test_migrations.py` pins the marker and the chain.
- They always come after 1.x's. Until the first pre-release,
  `v2.0.0-alpha.1`, was published (2026-10-24), a `develop` merge into
  `2.0` that brought a 1.x migration re-pointed `0100`'s `down_revision` to
  1.x's new head (no file renamed, the marker unmoved). Since then (anyone
  may have a 2.0 database), a 1.x migration a `develop` merge brings stays
  as it is and an Alembic merge revision (`alembic merge`) joins it to
  2.0's head; a 2.0 database then upgrades through the 1.x migration too,
  which must run on 2.0's schema. `make catch-up-2.0` stops for the build's
  lead at any 1.x migration (`scripts/catch-up-2.0.sh`).

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
