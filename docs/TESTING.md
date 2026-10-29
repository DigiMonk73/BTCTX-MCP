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
| Lint | `make lint` | Python: ruff with all Pyflakes rules (undefined names, unused imports/variables), bare `except`, and in the app code modern syntax (`list[str]`, `X | None`) and a size limit per function (complexity 10, 12 branches, 50 statements, 6 returns; `docs/CODE_STYLE.md`). Frontend: ESLint with zero warnings and a size limit (complexity 15 per function, 400 lines per file; tests exempt) + TypeScript + Vitest unit tests (`src/**/*.test.ts`: form ↔ API mapping, local time, the AI setup prompt, River rows, dashboard totals, the transaction list's pages, server error messages; and in jsdom, `*.test.tsx`, components mounted against a stubbed server, `src/test/`: the transaction form, its account pickers and coin picker, Settings' accounts, the import from an exchange, the past-year question, the dashboard…) | secs |
| Unit + integration | `make test-fast` | Every test but the slow ones (backend and MCP server), on every core: FIFO lots, gains, fees, holding period, 1099-DA boxes, tax timezone, imports, IRS templates, the printed forms read back (`test_printed_forms.py`), auth, the AI key, MCP tools | ~2 min |
| Full suite | `make test` | Adds the slow tests (`@pytest.mark.slow`): 250-transaction stress tests, the property tests' long runs, and every reference row saved again (#352) | ~10 min |
| Smoke | `make smoke` | Starts the **real server** and walks it like a user: login → buy → move to cold storage → sell → MCP import → every report → logout | ~15 s |
| Click-through (e2e) | `make e2e` | Playwright drives the real UI in Chromium, in Chicago and Tokyo time: first run, login, every transaction type, edit/delete, the list, dashboard figures, River and CSV imports and the import from any exchange, every report download, Settings and its wallets, exchanges and banks, the past-year question, the coin picker, the widgets. Each test gets its own server on a temp database with stubbed prices | ~5 min |
| Docker | `make docker-smoke` | Builds the image from this checkout and runs CI's container checks on it locally: first-run setup code, smoke test, data on `/data`, the app as its own user `btctx`, health, maintenance CLI. `scripts/docker_update_check.sh <image>` runs CI's update from the published 1.2.8 image, whose `/data` is root's (#202) | ~5 min |
| Dependency audit | `make audit-deps` | No known-vulnerable Python/npm packages | secs |
| Everything but e2e | `make check` | lint, test, smoke, audit-deps (run `make e2e` separately) | ~6 min |
| Agent release tests | `docs/AGENT-TESTS.md` | An AI agent (or a person) runs the packaged app on a StartOS VM, before each release: install, actions and tasks, the update from the last release, backups, price sources, TLS, a real MCP client, and the Mac app, against a 14-transaction ledger with every figure known | ~4 h |

## When they run

- **Before every `git push`** (`.githooks/pre-push`): first the branch
  rules (`.githooks/branch-rules.sh`: AGENTS.md, "Branches"), then lint, static
  Docker/StartOS checks (`backend/tests/pre_commit_tests.py`), fast tests,
  smoke, frontend lint + type check + Vitest (if `frontend/node_modules`
  exists), StartOS package format check (`npm run format:check`), then type
  check, lint and bundle (the SDK's `make javascript/index.js`, which from
  start-sdk 3.1.0 formats instead of checking) and manifest check (if `startos/node_modules`
  exists and `start-cli` is on `PATH`). A failure blocks the push. Emergency bypass:
  `git push --no-verify`.
- **On GitHub, every pull request and every push to `develop`, `main`, `staging` or `2.0`** (`.github/workflows/ci.yml`; once per change, not again for the branch push), the full set: Python 3.11 and 3.13
  (Docker's, StartOS's and the Mac app's) full suite, frontend build, smoke test, click-through tests (Chromium and WebKit), Docker image build + smoke test
  against the running container, dependency audit, StartOS package checks and
  an x86_64 `btctx.s9pk` packed from this commit's image.
  - A pull request into `staging` or `2.0` (and only there) runs the
    **medium set**: all of that except the click-through tests, the
    Docker image and the StartOS pack, so a night's batch runs side by
    side. Every merge into `staging` or `2.0` starts the full set on the
    result; a newer run there cancels the older, so the last run tests
    every change merged (a cancelled run's red "CI passed" isn't a
    failure). Every other pull request (into `develop`, `main` or any
    other branch) runs the full set. AGENTS.md, "Branches".
- **Daily** (from the release that brings it to `main`, since GitHub runs a
  schedule only from there; until then each session runs the script, AGENTS.md,
  "Starting a session"): `start9-watch.yml` (`scripts/start9-watch.sh`) opens an issue for
  what Start9 changed that the StartOS package must follow: a newer start-sdk
  or start-cli, a StartOS or start-registry release, changes to their
  packaging guide or shared package workflows, a failed build on the mirror
  or their fork, changes on their fork not taken back (startos/UPDATING.md,
  "Watching Start9").
- **Weekly:** `irs-forms-watch.yml` opens an issue when the IRS publishes
  new draft forms (to ship as the preview) or the final forms for a new year.
  Monthly, `price-history-watch.yml` checks that Bitstamp still gives every
  year of the hourly price history as fingerprinted, and opens an issue if not.
- **On the same runs** (or manually from the Actions tab), not a required check: builds the macOS
  app, launches it, checks its API answers on its own port (`127.0.0.1:8765`;
  a 2.0 pre-release's "BitcoinTX Preview" on one of its own) with its data in
  its own folder (`scripts/mac-app.sh`), and attaches the
  zipped `.app` and an unsigned `.dmg` to the run; `audit-macos` audits the
  Mac app's dependency locks.

## Writing a new test

Tests for a bug fix should fail on the old code and pass on the new one. Use
the shared fixtures in `backend/tests/conftest.py`:

```python
def test_my_fix(auth_client):              # logged-in client, temp database
    r = auth_client.post("/api/transactions", json={...})
    assert r.status_code == 200
```

Mark anything slower than ~5 s with `@pytest.mark.slow`.

"This tax year" is pinned to 2009 in the tests (`tax_time.current_tax_year`,
`conftest.py`), so no save meets the past-year warning by chance; a test of
the warning sets the year with the `tax_year` fixture (`tax_year(2026)`). A
click-through spec that writes into an earlier tax year meets its 409 and
confirms it: `createTx` and `sendConfirmed` for the API, `saveForm` for the
form (`e2e/fixtures.ts`).

## Property tests and golden years

- `backend/tests/test_invariants_property.py` (Hypothesis): random valid
  ledgers must keep the tax invariants (balances = lots, gain = proceeds −
  basis, basis conservation, holding periods, Form 8949 = Schedule D = the
  complete report, recalculation and entry order change nothing). 8 examples
  in the fast set, 120 in the slow set; a second generator does the same over
  multiple wallets, exchanges and banks
  (`test_random_ledgers_over_multiple_accounts_keep_the_invariants`). A
  failure prints the smallest ledger that breaks it.
- `backend/tests/test_golden_years.py`: three tax years worked out by hand
  in the docstring, with the exact Form 8949 rows, boxes and Schedule D lines.
  If a change moves one of these numbers, it changes users' tax forms.

## Before/after equivalence check

For a change that must not change behaviour (a refactor, a cleanup, a type
hint pass), compare everything the app produces with a release:

```bash
python scripts/equivalence_check.py            # against v1.2.2-1, ~5 min
python scripts/equivalence_check.py --bench    # plus recalculation time (fails if >5% slower)
python scripts/equivalence_check.py --against v1.2.10
python scripts/equivalence_check.py --against origin/2.0   # on 2.0: its tip, or a step's pin
```

On `2.0`, compare against `2.0` itself (its tip, or `pin/2.0-step-N`): a
build from before 2.0's coin choice (dc2cab07) refuses the chosen-coins
ledger below, the default release included.

It checks out the release in a temporary git worktree and snapshots both
it and this checkout on the same inputs:
- **Ledgers:** 1.x's golden ledger and random generator, frozen in
  `scripts/equivalence_ledgers_1x.py` (so a release before 2.0 can take
  them), the reference test ledger's 1.x rows
  (`testdata/reference_ledger.json` without its `"since"` rows), 40 random
  ledgers from that generator (fixed seeds, in UTC, Chicago and Tokyo
  time), and a ledger whose wallet chooses its coins
  (`equivalence_inputs.CHOSEN_LEDGER`).
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
is reused while `scripts/equivalence_*.py` are unchanged and it's still the
same day in each of the ledgers' tax timezones (`equivalence_inputs.ZONES`,
#630). Any difference is printed as a short diff per item and makes it
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
- The `tokyo` project reruns the create, edit, list, sidebar-matrix and chosen-coins specs
  in UTC+9. The `webkit` project (the Mac app's engine) runs only with
  `E2E_WEBKIT=1`, which CI sets; without it, it matches no test. Locally:
  `E2E_WEBKIT=1 npx playwright test --project=webkit` (once
  `npx playwright install webkit`). CI's WebKit runs on Linux: what only
  macOS's WebKit does (#456, a cleared date field that blocked Save) shows
  only in that command run on a Mac.
- **Playwright's WebKit crashes ("Page crashed") at the next navigation
  after any reload of a signed-in page** (a second reload, or a `goto`),
  with or without the price card. Real Safari and Chrome reload normally,
  and the Mac app has no reload shortcut (#149). So a WebKit test reloads a
  signed-in page at most once (`settings.e2e.ts`, the first-run test, does
  its reload before choosing only in Chromium). Now and then it also fails
  the reload or `goto` that follows a price choice saved over the API,
  with "WebKit encountered an internal error" (#231). So a test saves one
  with `choosePriceSource()` (`e2e/fixtures.ts`), which then tells the open
  page as the price card does after its own save: the page asks again in
  place, with no page load.
- `test.use({ fakeInternet: true })` swaps the stubbed prices for a fake
  internet (`fake_internet` in `scripts/smoke_test.py`): the app's own
  choice of price source, fallback and proxy runs; each past day has its
  own price (`fakePastPrice()`: $50,000 plus the day's number mod 100), so
  a lookup of the wrong day shows; a host under `.invalid` never answers (a
  mempool server that's down, Tor stopped); a request the app's code never
  makes gets a 404; and `outsideRequests(app)` lists every request the
  server sent out, with its proxy. `e2e/sidebar-matrix.e2e.ts` uses it to
  run the sidebar's converter and calculator under every price-source
  state, checking that nothing is asked before a choice or while off and
  that no request names the day.
- A `test.fail()` marks a known bug the test describes correctly, naming
  its `bug` issue; remove it with the fix.
- Install the browsers once per Playwright version: `npx playwright install
  chromium` (and `webkit` for its project). Claude Code's cloud sessions
  (claude.ai/code) aren't known to ship Playwright's browsers: Anthropic's
  list of their installed tools names none (checked 2026-10-21,
  <https://code.claude.com/docs/en/cloud-environments>, "Installed tools"),
  and Playwright's download hosts aren't on their default network
  allowlist. So in a cloud session, check first (`ls
  "${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"` against the
  builds `npx playwright install --dry-run chromium` names); with no
  matching build, try `npx playwright install chromium`, and if the
  network refuses it, leave the click-through tests to CI.
- Failures leave a trace and screenshot in `frontend/test-results/`
  (`npx playwright show-trace …`); CI uploads them as an artifact.

## Smoke-testing a live instance

```bash
python scripts/smoke_test.py --url http://127.0.0.1:8080 \
  --user NAME --password <12 characters or more> --setup-code XXXX-XXXX-XXXX
```

`--setup-code` claims a fresh install's default login first (the code is in
`docker logs` and `/data/setup-code.txt`); without it the smoke test logs in
as `admin` / `password`, which a fresh install refuses without the code.
Only against an **empty** instance (a fresh Docker container, never your real
data) — it creates transactions. `make docker-smoke` does this for an image
built from the checkout (`scripts/docker_smoke.sh --keep` leaves the container
running on 127.0.0.1:8778).

## The reference test ledger

One made-up ledger is the test data for everything that needs a full one:
`testdata/reference_ledger.json` (2023 to 2026, and a
deposit dated 2022 so 2023 starts holding coins). Every
year has every kind of transaction (each deposit source, Rebate included,
each withdrawal purpose, transfers both ways, cash moves, buys and sells;
the test takes the lists from the app, so a new kind fails it until the
ledger has one), it uses every account route the app offers,
every report has entries in each part (every Form 8949 box of 2024, 2025
and 2026, in any tax timezone), My BTC and Gift deposits carry a date
originally acquired, and inherited coins are sold within a year of the death. Every USD value a price lookup would fill is given, so
it loads with the price source Nobody, but in the rows marked `"priced"`
(#715): they leave their value to a price from the stored-price fixture
(`testdata/reference_prices.json`), so every year's report lists values from
a price and Ledger Review shows its price checks. Each row's `why` says what it is for.
From 2.0 it holds multiple wallets, exchanges or accounts: its `accounts`
list adds two of each kind (wallets Coldcard and Jade, exchanges Kraken and
Overseas, whose 1099-DA switch is off, banks Credit union and Savings) and
a fourth wallet, the Sparrow, and a fifth, the Trezor (only #715's rows use
it), which the seed makes through the account API
before the rows and, after them, names and hides as listed (Overseas is
made as "Offshore" and renamed; the Jade is hidden while it still holds
coins). The rows marked `"since": "2.0"` use them: B7a's in 2026, #702's
in 2022 and from 2024 to 2026, each filling its year's 2.0 dimensions, and #730's in
2025 and 2026, which choose which coins leave a wallet (#711). A row names
the coins it acquired with a `key`, and a later row chooses them by it
(`"chosen_coins": [{"key": …, "btc": …}]`): the seed sends each as the id
the server gave that row, never by position, and stops before sending
anything if a key is defined twice or chosen before its row.
`test_seed_ledger.py` fails if one empties: each deposit source and
withdrawal purpose in more than one wallet and exchange, each account
route between more than one pair of accounts, each exchange's sales in the
boxes its 1099-DA switch gives
(`SALES_BOXES`), every Broker form choice against each switch (a spend's
fee following it), gains and losses of both terms and inherited coins sold
in each forms year (2024 to 2026), holdings at each year's start, a hidden
and a renamed account on the dashboard, and each Ledger Review item a row
can show (it names the others, with why no row can); and chosen coins
for each withdrawal purpose and each move out of a wallet, choices in 2025
and 2026, inherited coins chosen, a spend's coins and a donation's of both
terms, one purchase chosen across two lots, and a choice equal to oldest
first beside choices that aren't. #715's, in the Trezor, take their
values from the stored-price fixture, so every year lists values from a
price; every other value is typed, so the rest loads with the price
source Off. The 2.0 rows go only into 2.0's accounts (the one exception is the last row,
the fee-less split of a pooled wallet, Wallet to the Coldcard), and
#702's (marked `"added": "#702"`) each after that account's last earlier
disposal (Kraken's and Overseas' bitcoin are emptied by the end of 2025);
#730's (`"added": "#730"`) live in the Sparrow, filled only from External,
and send chosen coins to the Jade and Kraken only after each one's last
earlier row; so no older row's figure moves. `test_reference_ledger_354.py`
proves it row by row, 1.x's beside every 2.0 row (the equivalence check's
ledgers leave those out), 1.x's and B7a's beside #702's and #730's, and
those and #702's beside #730's, and that the split moves only those two
wallets' year-end lots and balances.
Neither it nor any test data ships in a build (Docker copies only
`backend/` and `frontend/`; the Mac app leaves out `backend/tests/`).

**Load it into a server** (an empty one; never your real data):

```bash
python scripts/seed_ledger.py --url https://host:port --user NAME --password-stdin [--ca root-ca.crt] < password-file
```

Without `--with-prices` it leaves out the rows marked `"priced"` and says how
many, since a server has no stored price for them (a 422 otherwise); its
figures are then not `reference_figures.json`'s. To load every row, store
the fixture's prices in the test database's file before its server starts,
then seed with `--with-prices`:

```bash
python scripts/seed_ledger.py --store-prices path/to/test/btctx.db
```

It writes only those prices, asks nothing of the network, and refuses an
installed app's data folder however the path is written, a file that isn't
a BitcoinTX database and one holding transactions the seed didn't make.

It refuses a ledger that has transactions, and the Mac app's address
(`127.0.0.1:8765`) outright; the Mac test build's port 8766 is fine. It
stops if an account it makes doesn't get the id the ledger lists (an
install where accounts were added by hand); one a Delete All left is used
again.
`--setup-code` claims a fresh Docker install first. On the StartOS test VM,
the lab's `tools/vmtest seed` loads it and installs the next year's draft
forms (the app ships the IRS's drafts for the year after its newest final forms, as a
preview until January 1 after that year; see
docs/IRS_FORM_GENERATION.md, "Draft forms: the preview, and test installs").
For a box: export it there as CSV (Settings) and import that.

**Its figures can't move unnoticed.** `testdata/reference_figures.json`
holds every figure the app computes from it: each year's Form 8949 rows and
Schedule D lines, the complete tax report's data (holdings at both ends of
the year, gains, income, rebates, gifts, each box) and the dashboard's
totals (`scripts/reference_figures.py`). `backend/tests/test_seed_ledger.py`
loads the ledger into the in-process app and compares, so CI fails on any
change in a figure and names where. After a change meant to move figures:

```bash
make reference-figures      # rewrites testdata/reference_figures.json
```

and the pull request shows the difference. Then the figures rule
(AGENTS.md, "Reviews"): a figure moved on purpose gets the owner's OK on a
plain-words before-and-after, never on code; a figure moved by mistake is
fixed, never accepted here. A change that moves no figure merges on Claude's
review once every figures check is green.

**A second calculation checks them.** `scripts/independent_figures.py`
recomputes the ledger's figures (Form 8949 rows, Schedule D lines, box
totals, each exchange's Sells, the gains summary, income, rebates, gifts,
the lots held at each year's start and end) from the
IRS's and the ledger's documented rules, importing nothing of the app
(#150). `backend/tests/test_independent_figures.py` fails on any difference
in those from `reference_figures.json`, so a change meant to move figures
also changes the rule it follows there, or it was a bug. Three conventions
are shared on purpose (the script's docstring, AGENTS.md "Lot cost"): a
lot's cost claimed as a running total (#100), a disposal's proceeds shared
among its lots as a running total too (#297), and an exact half cent
rounded up:

```bash
python scripts/independent_figures.py --compare --years 2023 2024 2025 2026
```

**Each release's database is kept** in the test lab
(`~/code/btctx-vm-lab/ledgers/reference-vX.Y.Z.db`, with its figures in
`reference-vX.Y.Z.json`), made in the release tests (docs/AGENT-TESTS.md,
REF-2). The next release opens a copy of it and compares (REF-3):

```bash
DATABASE_FILE=<copy> python -m backend.cli migrate
python scripts/reference_figures.py --db <copy> --compare reference-vX.Y.Z.json
```

The stored figures must be identical after the upgrade (a figure the new
version adds, which the older file lacks, isn't counted). Then
`python -m backend.cli recalculate` on the copy, and compare again: what
moves must be what the CHANGELOG says a recalculation changes.

## The landing page's pictures

```bash
make site-shots              # into docs/images/ (or SITE_SHOTS_DIR=...)
```

`frontend/e2e/shots/site.ts` takes the four pictures the README
(`docs/images/`) and DigiMonk73/btctx-site (`img/`) show (`dashboard.png`,
`transactions.png`, `reports.png`, `settings.png`), into `docs/images/`, from
this checkout's app, at the site's size (1470 x 867 at 2x, dark), with the
e2e server's fixed prices ($60,000), so they change only when the app does.
Their ledger is `testdata/showcase_ledger.json`, a small typical portfolio
(the reference ledger's latest entries, built to cover every case, would
show no sales); the Settings picture is in Mac app mode, with the key
file's path shown as `~/Library/...`. The release tests take them (REF-1);
at the release's landing-page step, `make site-shots` in a branch, then the
changed pictures go into `docs/images/` by pull request (then `main` is
fast-forwarded to `develop`, docs only, since GitHub shows the README from
`main`) and into btctx-site's `img/` (shown to the owner first): the two
always match.

## Trying a branch in a browser

```bash
make preview PY=.venv/bin/python   # http://127.0.0.1:8777
```

`scripts/preview.py` builds the frontend and serves the checked-out code on
a throwaway database (deleted when it stops) with the smoke test's stubbed
offline prices, with the smoke test's login (`SMOKE_USER`,
`SMOKE_PASSWORD` in `scripts/smoke_test.py`), which you sign in with.
Claude's browser preview starts it from `.claude/launch.json` ("preview").

## Schema migrations

`backend/tests/test_migrations.py` checks that the migrations and the models
describe the same schema, and upgrades a database written by the real v0.7.0
code (`backend/tests/fixtures/v0_7_0.db`), including older variants and
restored backups. CI also starts the Docker image on that database and checks
the upgrade (`scripts/check_upgraded_instance.py`). Every test database is
built by the migrations, not `create_all()`.

2.0's migrations start at 0100 (`docs/MAINTENANCE.md`, "Database
migrations"), and two databases written by 1.x's own code test the way up
to them: `fixtures/old_accounts_1x.db` (`test_migrations.py`), and
`fixtures/reference_1x.db`, the reference test ledger as the last 1.x
release saved it, with 1.x's figures for it in `reference_1x_figures.json`
(`test_reference_1x.py`: migrated and recalculated, it must give the same
figures). `fixtures/make_reference_1x_db.py` makes it and its figures again for a new 1.x
release or new reference rows.

## Yearly IRS templates

`python scripts/irs_new_year.py YEAR --check` verifies an installed year's
templates; `backend/tests/test_irs_templates.py` runs the same checks for
every bundled year on each test run. See docs/IRS_ANNUAL_FORM_UPDATE.md.
`backend/tests/test_draft_forms.py` covers the draft forms (the shipped
preview and its cut-off, a test install's) with a stand-in draft made from
the newest bundled form, and checks the shipped draft itself.
