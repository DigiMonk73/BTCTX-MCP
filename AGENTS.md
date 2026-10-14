# AGENTS.md

Context for AI assistants working on this repo: Claude Code, and any other
agent that reads `AGENTS.md` (`CLAUDE.md` only points here). Keep it current
and short; history belongs in `docs/CHANGELOG.md`.

## What this is

BitcoinTX: a self-hosted, single-user Bitcoin portfolio and tax tracker
(double-entry ledger, per-account FIFO lots, IRS Form 8949 / Schedule D).
This repo, **DigiMonk73/BTCTX-MCP**, is the project, including an MCP server
for AI-assisted entry. Work goes into `develop` by pull request (see
Branches).

| Part | Where | Notes |
|---|---|---|
| Backend | `backend/` | FastAPI + SQLAlchemy + SQLite, Python ≥ 3.10 |
| Frontend | `frontend/` | React + TypeScript + Vite, served from `frontend/dist` by the backend |
| MCP server | `mcp_server/` | package `btctx-mcp` (on PyPI from 1.2.0, published by `release.yml`); talks to the backend over HTTP with the AI key (bearer), never a password |
| macOS app | `desktop/` | PyInstaller + pywebview, fixed port `127.0.0.1:8765` (`BTCTX_DESKTOP_PORT`) |
| Docker | `Dockerfile` | data on `/data` (`DATABASE_FILE=/data/btctx.db`); image `ghcr.io/digimonk73/btctx-mcp` |
| Landing page | DigiMonk73/btctx-site | <https://digimonk73.github.io/btctx-site/>, `index.html` with screenshots in `img/`, on GitHub Pages; the manifest's `marketingUrl` and the connector's Homepage. Its download links follow the latest release by themselves; its text and screenshots don't (Releasing, step 5) |
| StartOS package | `startos/` | start-sdk 3.0.6 (StartOS 0.4.0.2 or later), self-contained (own `package.json`), mirrored to DigiMonk73/BTCTX-StartOS; read `startos/AGENTS.md` |

## What's at stake

- BitcoinTX holds the owner's real tax records, and its figures go on IRS
  forms: a wrong number is a real-world problem. So a change to tax figures
  gets the full review, the before-and-after comparison and the owner's
  "merge" ("Reviews").
- The owner's real ledger is the installed Mac app's data. Never test on it,
  run a script against it or point the AI connector at it; use temp
  databases, `make preview` or the StartOS test VM, and run a Mac build
  only with `desktop/run-test-build.sh` (its own data folder and port).
- Other people install BitcoinTX from Start9's community registry: a
  release that breaks an update or loses data hurts users who trust it.
- Start9's reviewers and users care about privacy: no price is asked of
  anyone until the owner picks a price source, and no request names a day
  ("Prices" under Tax invariants).

## Who does what

- **The owner** (DigiMonk73) decides: releases, anything sent to Start9,
  and changes in what the app does or computes. The owner is not a
  professional developer: explain in plain words, with one recommendation.
- **Claude Code** is the developer: code, tests, dependency updates,
  releases, docs, and a read-only report each Monday of what needs
  attention (a scheduled task on the owner's Mac).
- **Grok** is a second set of eyes, never the developer (its
  roles and passes: `docs/GROK-REVIEW.md`):
  - Grok Bot on the web brainstorms from links the owner gives it
    ("Working through GitHub");
  - Grok in Cursor is the finder: it reviews a pull request when the
    owner asks, and runs the release pass and the monthly area;
  - Grok (in Cursor or Grok Build) writes only a job the owner names,
    outside tax figures, login and security, the database and StartOS
    (the manual names the files), and never merges.

  A Grok finding is a claim until Claude checks it, and every
  Grok-written change gets a fresh Claude review.

Everything goes through GitHub under the owner's account, so each AI ends
what it posts there with its name ("— Claude", "— Claude (reviewer)",
"— Grok", "— Grok (Cursor)", "— Grok (Build)"), and Claude's commits
carry its `Co-Authored-By` line.

## Branches

- **`develop`**: all work, arriving by pull request
  (`gh pr create --base develop`) from a short-lived branch named for the
  change ("Pull requests"). Never commit on a local `develop`: GitHub
  refuses the push.
- **`main`**: released code only; it is what users get (the `:main` Docker
  image; releases are cut from it). Never commit on `main`, never
  force-push or rewind it. It moves only by fast-forwarding to GitHub's
  `develop` (`git fetch origin && git checkout main && git merge --ff-only
  origin/develop && git push`), at a release, or when everything on
  `develop` not yet on `main` is docs, tests or tooling (nothing that ships
  in the app or the connector).
- **`release/vX.Y.Z`**: pushed from `main` to publish (see Releasing), then
  deleted.

The pre-push hook refuses a push to `main` of anything not already on
GitHub's `develop`, and `release.yml` refuses a release commit that isn't on
`main`. GitHub's rulesets (Settings → Rules; only the owner changes them)
add: `main` can't be deleted or force-pushed ("Protect main", also on the
mirror); `develop` can't either, and takes changes only by pull request,
squash-merged, once the 10 required checks of `ci.yml` have passed
("Protect develop": every job except the macOS build and the macOS
dependency audit, which run but aren't required).
Renaming or removing a CI job (changing a Python version in the test matrix
renames one) blocks every pull request until the owner updates that list; a
new job isn't required until it's added there. If unsure, branch from
`develop` and ask.

## Before you change…

- **Any code**: follow `docs/CODE_STYLE.md` (one job per function, comments
  say why, the same idioms everywhere).
- **Database paths, file storage, env vars, Docker**: read `docs/STARTOS_COMPATIBILITY.md`.
  Everything persistent lives in the directory of `DATABASE_FILE`.
- **Models / schema**: write an Alembic migration (`docs/MAINTENANCE.md`,
  "Database migrations"). Never call `create_all()` in app code; the
  `test_models_and_migrations_agree` test fails if models and migrations differ.
- **Dependencies**: read `docs/MAINTENANCE.md`. Pins live in the
  `requirements.in` files; after an edit, `make lock` recompiles the locks.
- **Desktop app**: read `docs/MACOS_DESKTOP_APP.md`. New backend modules need
  a `hiddenimports` entry in `desktop/BitcoinTX.spec`.
- **IRS forms**: read `docs/IRS_FORM_GENERATION.md`; for a new tax year follow
  `docs/IRS_ANNUAL_FORM_UPDATE.md` (`python scripts/irs_new_year.py YEAR`).
- **StartOS package** (`startos/`): it always keeps Start9's packaging rules
  (<https://docs.start9.com/packaging>: layout, README headings,
  `instructions.md`, no `TODO.md`), since Start9 reviews it against them. Read
  `startos/AGENTS.md`; `backend/tests/test_startos_conformance.py` checks what
  a script can. When Start9's guide changes, update the package and the test.
  What else Start9's rules cover: "Start9".

## Data model

```
Transaction (user input)
  → LedgerEntry (double-entry lines)
  → BitcoinLot (BTC acquisitions, per account)
  → LotDisposal (FIFO consumption, with basis/proceeds/gain per lot)
```

Fixed account IDs: Bank 1, Wallet 2, Exchange USD 3, Exchange BTC 4,
BTC Fees 5, USD Fees 6, External 99.

Schema: Alembic migrations in `backend/migrations/versions/` (0001 = the
v0.7.0 schema). `backend/migrate.py` runs them at every start and on restored
backups: fresh DBs are built from 0001, pre-migration DBs are repaired to the
baseline and stamped, a copy goes to `<db dir>/backups/` before any change,
and a schema newer than the code is refused. `database.create_tables` is an
alias of `init_db` kept for the StartOS wrapper.

Every create/update/delete runs `recalculate_all_transactions` ("scorched
earth"): all ledger lines, lots and disposals are rebuilt in timestamp order.
So derived values must be recomputable from the Transaction row alone.

## Tax invariants (each has regression tests; don't break them)

- **Withdrawal fee**: a BTC network fee on a withdrawal is on top of `amount`
  and is its own disposal (`lot_disposals.is_fee`, oldest BTC first) at
  `fee_usd`, taxable even for Gift/Donation/Lost and never broker-reported.
  A Spent's fee is a cost of the spend (Treas. Reg. §1.1001-7(b)(2)(ii)(A),
  #157, all years): its proceeds are the gross for `amount` less `fee_usd`,
  so the spend and its fee together realize the gross (a fee worth more
  than the gross takes only the gross). The transaction's own
  proceeds/basis/gain are the amount's (fee disposals left out).
- **Transfer**: `amount` is what left the source *including* the BTC fee; the
  destination lot gets `amount − fee`, keeping the source lot's acquisition
  date and pro-rated basis. The fee is a disposal. A BTC account to itself
  (Wallet → Wallet, Exchange BTC → Exchange BTC: a consolidation, or a move
  between pooled wallets, #159) needs a fee and records only it: no lot moves.
- **Proceeds**: the user's figure is anchored in `gross_proceeds_usd`; stored
  `proceeds_usd` is net of fees and is re-derived from gross on every recalc
  (never from the previous net, which would subtract the fee again).
  Unpriced "Spent" withdrawals get FMV proceeds at the hour's price, marked
  (`proceeds_from_price`) like an income value: an edit of the amount or
  hour (or a blank sent) prices them again; a change of purpose or type,
  or a typed value (never the form's echo), makes them typed. A spend's
  proceeds and fee value share one price: one priced again while the other
  keeps the day's price takes the day's too (`_keeps_a_day_price`).
- **Income deposits** (source Income/Interest/Reward into a BTC account):
  basis = market value at receipt, which is also the reported income. A blank
  or 0 basis is filled from the hour's price on create/update
  (`_value_at_receipt`); no price → 422, never $0. A value from the price
  is marked (`cost_basis_from_price`) and priced again when an edit changes
  the account, amount, UTC hour or type, or moves it from a source not valued
  at receipt (Reward to Rebate keeps it; a type change makes it typed); a
  typed one is kept, and the form's echo of a priced value isn't a typed one
  (`_revalue_income_deposit`). Income (report, dashboard) counts only
  deposits into Wallet or Exchange BTC (`constants.BTC_ACCOUNTS`): a USD
  deposit is dollars, whatever value it carries.
- **Rebates** (source Rebate, #98: card sats-back, shopping cash-back): valued
  like income deposits (`constants.VALUED_AT_RECEIPT`: the same filling,
  marking and re-pricing), but never income: not in the report's or the
  dashboard's income, listed apart in the report (`rebates`) and on the
  dashboard (`rebates_received`, #129). Reward stays income (mining,
  staking, bonuses).
- **Inherited** (source Inherited, #154): basis = value on the date of death
  (IRC §1014), the deposit's required `acquired_at`, which also dates its lot;
  valued like income deposits but on that date (`VALUED_AT_RECEIPT`: typed, or
  that day's price, priced again when the date of death changes; the date is
  the one entered: `acquired_at`'s date in the tax timezone, not its UTC day,
  `transaction.date_of_death`, #177), never income. Every disposal of its
  coins is long-term (§1223(9)) with INHERITED in Form 8949 column (b):
  `bitcoin_lots.inherited`, kept through transfers. Ledger Review doesn't
  compare its value with the day's price (an estate's value can rightly
  differ).
- **River Sells**: River's Received Amount is net of River's fee, so
  `proceeds_usd` (gross) = Received + fee.
- **Prices**: every valuation goes through `services/hourly_prices.price_at`
  (#144): the opening price of the moment's UTC hour (the tax timezone never
  changes the hour), else the UTC day's 00:00 price
  (`services/price_history.daily_price`, table `btc_price_daily`); the
  moment is recorded in `transactions.price_moment` ("hour" or "day"; none
  when every value is typed). A value priced before hourly prices stays at
  the day until an edit prices it again or the owner applies Ledger
  Review's check (#144); a recalculation never re-prices. Holdings at a
  tax year's start and end are valued at `price_at` of that bound (the
  hour the tax year ends, in the tax timezone), and the Complete Tax
  Report lists the year's priced values with the price each used.
  Nothing is asked until the owner picks a
  price source (`services/outbound.py`: off / public / own mempool,
  optional fallback),
  or the server sets it (`BTCTX_PRICE_SOURCE` and co.; StartOS's Price
  Source & Privacy action), which Settings then shows read-only. From
  1.2.8, prices stored while the server sets it never count as a choice
  (it stores `unset`), and a CLI command never makes one (#134).
  **No request may name the day**: the own mempool server is asked for its
  whole history (hourly 00:00 rows kept), public sites for the whole history
  in fixed blocks once, then only the latest days; the tests check the URLs.
  The same for the hourly prices (`services/hourly_prices.py`, #144): the
  year files in fixed 1,000-hour blocks from 1 January, every year, newest
  first (checked against `MANIFEST.csv`), and after them Bitstamp's fixed
  blocks from the hour after the files; never the hour asked.
  Stored days and hours never change. Never today's live price, never $0: no price is
  a 422. A BTC fee's USD value is stored in `transactions.fee_usd`
  at save (`fee_usd_manual` when typed) and recalculation only reads it.
- **Holding period**: long-term only when disposed *after* the one-year
  anniversary (IRS "more than one year"), dates taken in the tax timezone.
  It runs from the lot's acquisition date: a My BTC or Gift deposit's date
  originally acquired (`acquired_at`) when given, else the deposit's date;
  FIFO (oldest acquisition first, per account) and 8949 column (b) follow it.
  Inherited coins are long-term whatever the dates (above).
- **Tax timezone**: timestamps are stored in UTC. The tax timezone (Settings,
  `app_settings` table, fallback env `BTCTX_TIMEZONE`, default UTC) decides
  tax-year bounds, 8949 dates and the holding period. Helpers in
  `backend/services/tax_time.py`. Never slice a year with naive UTC dates.
- **Form 8949 boxes** (`form_8949.py`): ≤2024 C/F; 2025+ exchange Sells H/K
  (1099-DA without basis); 2026+ Sells of lots bought on the exchange on/after
  2026-01-01 and never moved G/J; self-custody spends and fees I/L. A
  Sell/Withdrawal's `broker_reporting` (none/proceeds/basis) overrides those
  rules for that transaction. One sheet per box, line 2 totals that sheet's
  rows, Schedule D line per box, column (f) blank.

## Key files

| File | Purpose |
|---|---|
| `backend/main.py` | app, session middleware, router mounting, `get_current_user` |
| `backend/migrate.py`, `backend/migrations/` | schema migrations run at startup, adoption of pre-migration DBs, pre-upgrade backups |
| `backend/secret_key.py` | per-install key in `.btctx_secret_key` that signs the session and device cookies (never a hardcoded key) |
| `backend/services/transaction.py` | ledger, lots, FIFO, fees, proceeds, recalculation |
| `backend/services/tax_time.py` | tax timezone helpers |
| `backend/services/price_history.py` | stored daily BTC prices (`btc_price_daily`); date-free downloads from the own mempool or public sites |
| `backend/services/hourly_prices.py` | the price when an hour began (#144): stored hours (`btc_price_hourly`), the year files (verified download into `<data dir>/btc-prices/`), a mempool server's live hours, Bitstamp's fixed blocks after the files; else the day's price, marked as such |
| `backend/services/price_files.py`, `scripts/price_history.py`, `backend/assets/btc_prices/` | the hourly price history (#144): Bitstamp's hourly opens from 2013, one fingerprint per year in `MANIFEST.csv` (closed years pinned by `test_price_files.py`); `make prices` refreshes it, cross-checked against Bitfinex and Kraken |
| `backend/services/mempool_trust.py` | a home server's root certificate the owner trusts for their own Mempool (#188): home-network https addresses only, that address only, never public sites; login only |
| `backend/services/outbound.py` | the only HTTP client factory for outside services, each request with a deadline and each answer a size limit (`BoundedClient`) (one exception, not the app: `cli install-draft-forms` fetches the IRS drafts on a test install); Privacy & network settings (price source unset/off/public/mempool, fallback, proxy for public sites), or the server's `BTCTX_*` overrides |
| `backend/services/review.py` | read-only Ledger review (`/api/review`, `cli review`, MCP `review_ledger`); `hourly_review.py`, its check of values priced at the day and the owner's apply (login only, a backup first) |
| `backend/services/first_run.py`, `login_throttle.py` | first-run setup code (default login); login throttling, and the device cookie of a browser that logged in |
| `backend/services/reports/safe_text.py` | ReportLab text escaping, no remote fetches |
| `backend/services/ai_key.py` | the AI key: Mac key file or created in Settings, hash only, on/off switch, `AI_KEY_ROUTES` allow-list |
| `backend/services/entry_import.py` | JSON entry import used by the MCP server: validate, FMV autofill, dedup, dry run |
| `backend/services/river_import.py`, `csv_import.py` | file imports |
| `backend/services/reports/form_8949.py` | 8949/Schedule D data, boxes, field maps per year |
| `backend/services/reports/pdf_form_filler.py` | fill + flatten IRS PDFs with pypdf |
| `backend/services/reports/draft_forms.py` | next year's IRS draft forms: the shipped preview (`assets/irs_templates/drafts/`, until January 1 after its year) and a test install's (`<data dir>/irs-draft-forms/`, `cli install-draft-forms`) |
| `backend/services/reports/reporting_core.py` | complete tax report data |
| `backend/services/reports/complete_tax_report.py`, `pdf_layout.py`, `frontend/src/utils/disclaimer.ts` | Complete Tax Report PDF (section 6 "Using these forms", the rebates table); the one disclaimer and one-wallet wording (`test_disclaimer.py` keeps them the same) |
| `backend/routers/user.py` | setup-status / reset-account (claim the default `admin`/`password`) |
| `mcp_server/btctx_mcp/server.py`, `guide.py` | MCP tools and the ledger guide the AI reads |
| `mcp_server/AI_SETUP.md`, `frontend/src/utils/aiSetup.ts` | setup guide an AI follows to install the MCP server; the Settings prompt and configs that point to it |
| `frontend/src/styles/theme.css`, `components.css` | design tokens, and the only button/input/card/badge styles (`.btn-primary`, `.input`, `.card`…); page stylesheets only lay these out. Safari 15 CSS only (Mac app WebKit) |
| `backend/cli.py` | maintenance CLI (migrate, set-password, recalculate, review); the StartOS package relies on it |
| `backend/security_headers.py` | CSP (browsers, not the Mac webview), no-referrer, nosniff, no framing; Secure cookies over HTTPS; the cross-site guard; the Mac app answers only at 127.0.0.1 or localhost |
| `backend/session_auth.py` | the open sessions (an id per login, the newest 20 kept in `app_settings`; logout ends one) and the stamp of the password hash (a password change ends all others) |
| `frontend/e2e/`, `frontend/playwright.config.ts` | Playwright click-through specs; projects chicago, tokyo, webkit |
| `scripts/sync-startos-mirror.sh`, `start9-pull.sh`, `mirror-startos-release.sh` | StartOS mirror sync; taking back Start9's changes to their fork; the mirror's release by hand |
| `scripts/sync-check.sh` (`make sync-check`) | is everything on this computer also on GitHub; brings `main`/`develop` down; `--tidy` deletes branches already on GitHub |
| `scripts/irs_new_year.py` | yearly IRS template download + verification |
| `scripts/smoke_test.py` | end-to-end run against a real server |
| `testdata/reference_ledger.json`, `reference_figures.json` | the one reference test ledger (2023–2026, every 8949 box, rebates, dates originally acquired) and every figure it gives; `test_seed_ledger.py` fails if one moves (`make reference-figures` accepts a meant change) |
| `scripts/seed_ledger.py`, `reference_figures.py` | load that ledger into an empty server over the API (refuses the Mac app); a database's figures, or `--compare` them |
| `scripts/independent_figures.py` | a second calculation of that ledger's tax figures (8949, Schedule D, gains, income, rebates, gifts, year-end lots) from the rules, never the app's code; `test_independent_figures.py` fails on a difference in them |
| `frontend/e2e/shots/site.ts`, `testdata/showcase_ledger.json` | the README's (`docs/images/`) and landing page's four pictures (`make site-shots`), from a small typical portfolio |

## Security rules

- All API routers require login (or the AI key, below) except
  `POST /api/users/register`, `GET /api/users/setup-status`,
  `POST /api/users/reset-account`, `GET /api/health` (status, version,
  schema only) and login. User routes may only touch the logged-in user.
- `SECRET_KEY` values in `secret_key.PUBLIC_DEFAULTS` are ignored. Never add a
  default key anywhere.
- The debug router, `DELETE /api/transactions/delete_all` and
  `PUT /api/settings/tax-timezone` are login-only (never the AI key); tests
  use the first two, the MCP server must not expose bulk delete. API docs
  (`/docs`, `/openapi.json`) only with DEBUG.
- Sessions (`backend/session_auth.py`): each login gets a random session id,
  carried in the cookie; the server keeps the hashes of the open ones in
  `app_settings` (the newest 20). A session not on that list is logged out
  (401), so logout ends that cookie and every copy of it while other
  browsers stay logged in. Sessions also carry a stamp of the password hash:
  changing the password (Settings or `cli set-password`) or resetting the
  account empties the list and ends every other session. A restore keeps
  the other browsers' sessions open before it (only while the restored
  account has the same id), never the backup's list; the restoring browser
  logs in again. A route that reads `request.session` itself
  relies on its router's `get_current_user` having cleared an ended session
  first; outside such a router, use `require_login`.
- Login, reset-account and password changes are throttled
  (`services/login_throttle.py`, per client and global; 429 + Retry-After).
  A browser that got one of them right gets a device cookie (`btc_device`,
  a year, signed with the secret key, bound to the current password) and is a
  client of its own: other clients' failures, its address's count (behind
  a proxy, everyone's) and the global cap don't stop it; its own failures
  slow it. Logging out keeps it; a new password voids every earlier one.
  New passwords need 12+ characters; a change needs the current password.
- While the account has the default login (before it's claimed: Docker,
  source and the Mac app alike), logging in with it and claiming it need
  the one-time setup code (`services/first_run.py`,
  `<data dir>/setup-code.txt`, 0600). A server prints it to the log; the Mac
  app never logs it: its window reads the file (`desktop/desktop_api.py`,
  `setup_code()`, only for the app's own pages) and its login page has the
  owner choose a username and password, keeping the ledger (PATCH, never
  reset-account: `frontend/src/utils/ownLogin.ts`). StartOS never has the
  default.
- Non-GET requests a browser marks as from another site (`Sec-Fetch-Site`,
  else `Origin`) are refused (`security_headers.py`); no CORS unless
  `CORS_ALLOW_ORIGINS` is set. The Mac app answers only requests addressed
  to `127.0.0.1`, `localhost` or `[::1]` (421 otherwise;
  `security_headers.LocalAddressOnlyMiddleware`), and its server never takes
  a client's address from `X-Forwarded-For` (`desktop/entrypoint.py`).
- Report PDFs: every ledger string passes `reports/safe_text.py` (escaped for
  ReportLab, which may fetch nothing remote); CSV text cells can't start a
  formula, and the csv module writes every CSV, so a line break stays in its
  cell; a purpose or source kept as written is one line, and a fee currency
  is USD or BTC.
- The MCP server authenticates with the AI key (`backend/services/ai_key.py`,
  `Authorization: Bearer`), never a password; there is no other API key. Mac
  app: the key is in the owner-only `mcp.json`, a new one at every start (the
  connector reads the file again on a 401), and works only from localhost.
  Docker/StartOS: the owner creates, replaces or revokes it in Settings (shown
  once). Only its SHA-256 is stored; a restore keeps the current key and
  switch (and the login and price settings in use: an in-app restore never
  brings back a backup's password or its price source). An in-app restore
  takes a backup's data, never its database: a backup holding anything but
  ordinary tables and indexes is refused, and the database that goes live is
  made by BitcoinTX's own migrations with only the rows of its own tables
  and columns copied in, one login, and these settings written and read back
  before it replaces the live one; any failure leaves the live database as
  it was and answers in plain words, never SQL
  (`services/backup.restore_backup`, `routers/backup._write_kept`).
  It works only while AI access is on (off by default) and only on
  `AI_KEY_ROUTES`, the routes the MCP tools call; any other route is 403. A
  new MCP tool that needs a route adds it there on purpose (a test checks the
  tools and the list agree). Never allow the key on login, users, key or
  switch settings, backup download/restore, CSV export, file imports (CSV,
  River), delete-all, Ledger Review fixes, settings changes (the Mempool
  certificate's trust, #188, included) or debug.
- Before the AI key's first change in an hour (an edit or a deletion) an AI
  copy is made (`backups/…-ai-before-changing-…db`; no copy, no change),
  never for the owner's; it is written under a temporary name and renamed
  once complete, one at a time, so a failed or unfinished copy never counts
  as the hour's. Of the AI copies BitcoinTX keeps the newest 3 and, for a
  week (today and the 6 UTC days before), the oldest and the first copy of
  each day made before the AI changed anything that day
  (`migrate._ai_copies_held`): at most 11.
- The JSON entry import (`routers/entry_import.py`) holds SQLite's write
  lock while it works, and the owner's saves wait only 5 s for it. With the
  key a request takes at most `AI_MAX_ROWS` (500) rows, and its rows dated
  before the ledger's latest entry, each replaying the whole ledger, at most
  `AI_MAX_REPLAYED` (1,000) entries in all (one such row always), about 1 s.
- Every request body is limited before anything reads it
  (`backend/body_limit.py`, just inside the security headers, before the
  cross-site check, sessions and routers): FastAPI
  reads and parses a body before the login check, login and Create account
  included. Over 5 MB it's 413, at once from Content-Length or as soon as a
  chunked body passes it. A route taking a file is listed in `main.py` with
  its own file limit (plus room for the form) and keeps checking the file
  itself: the restore 1 GiB, the CSV and River files 5 MB. That larger
  allowance is for a logged-in owner's file: only a request whose session
  cookie is validly signed, unexpired and holds a `user_id` gets it. A new
  upload route goes in that list.

## Testing (see `docs/TESTING.md`)

```bash
make hooks       # once: pre-push gate
make test-fast   # ~1,700 hermetic tests (backend + MCP), ~3 min
make test        # + slow stress and property tests
make smoke       # real server, temp DB
make e2e         # Playwright click-through (Chromium, Chicago + Tokyo), ~5 min
make preview     # this checkout in a browser, 127.0.0.1:8777, throwaway data (launch.json "preview")
make site-shots  # the README's and landing page's pictures, into docs/images/ (each release)
make reference-figures  # accept moved figures of the reference test ledger (owner's merge if tax)
make prices      # the hourly price history's new hours (each release's bump PR; online)
make docker-smoke  # build the image here + CI's container checks
make check       # lint + test + smoke + audit-deps (CI adds e2e, StartOS, Docker, macOS)
```

Tests never touch a real database or the network (temp SQLite, stubbed BTC
prices). **Test data:** a check that needs a full ledger uses the reference
test ledger (`testdata/reference_ledger.json`, loaded by
`scripts/seed_ledger.py`), never a new one built for the occasion. When the
app gains a kind of transaction or a report part, add a row there (its
`why` says what for) and run `make reference-figures`. The coverage tests
in `test_seed_ledger.py` fail by themselves for a new transaction type,
deposit source, withdrawal purpose or broker-reporting choice (they take
the app's own lists); a new account route or report part goes into their
`ROUTES` or report-part checks too.

A bug fix gets a test that fails on the old code. Lint is ruff with
all Pyflakes rules, modern syntax and a size limit per function (app
code), and ESLint with zero warnings and a size limit per function and
file; `docs/CODE_STYLE.md` has the rest.

A command that waits for another command must not search for its own
text. `pgrep -f` can match the waiter's own command line (always on Linux)
or another waiter's, so the wait never ends and the session stalls. Wait on
the process you started, or read the log it writes. A poll on a local
command gives up after 20 minutes and then reads whatever log is there.

## Releasing

Full steps, the package version and the signing/mirror secrets:
`startos/UPDATING.md`. In short:

1. In a pull request into `develop`: bump `VERSION`, the version in
   `desktop/BitcoinTX.spec`, the image tag in
   `startos/startos/manifest/index.ts`, `startos/startos/versions/current.ts`
   and `mcp_server/pyproject.toml` (`backend/tests/test_versions_agree.py`
   fails until they agree), and run `make prices` (the hourly price
   history's new hours; the release refuses one more than 14 days old).
   Move the CHANGELOG's Unreleased section to the
   version and clear the ticked items from `docs/ROADMAP.md`. Minor bump
   when a new tax year's forms are added. The StartOS release notes
   (`current.ts`) repeat each `tax-figures` fix: what was wrong, which tax
   years, what to do. Once it has merged, wait for CI on
   `develop`. Run `docs/AGENT-TESTS.md` (an agent on a StartOS VM) on that
   commit's CI artifacts; a blocker FAIL stops the release. Meanwhile a
   fresh Claude, one that didn't write the release, reads every doc
   against what it ships (owner's rule, 2026-10-10): the READMEs,
   `startos/instructions.md`, the store descriptions
   (`startos/startos/manifest/i18n.ts`), the actions' text
   (`startos/startos/i18n/dictionaries/`), `mcp_server/AI_SETUP.md` and
   the AI guide (`guide.py`), `docs/`, `SECURITY.md`, the app's on-screen
   text (Settings, the form hints, `frontend/src/utils/aiSetup.ts`), and
   the CHANGELOG's new section against the pull requests merged since the
   last release, with the StartOS release notes (`current.ts`) against
   it. Anything stale is fixed by pull request before step 2: nothing is
   released, or sent to Start9, with stale docs. Such a fix changes
   wording only, so the agent tests aren't run again; a change to what
   the app or the connector does isn't a docs fix.
2. Fast-forward `main` to GitHub's `develop` ("Branches") and push: `.github/workflows/image.yml`
   publishes `ghcr.io/digimonk73/btctx-mcp:vX.Y.Z` (never overwritten) and
   `:main`.
3. Push a branch `release/vX.Y.Z` from `main`, and delete it once the
   release is out: `.github/workflows/release.yml` builds the
   macOS `.dmg` + `.zip` and `btctx.s9pk` (signed with the `DEV_KEY` secret if
   set), publishes the AI connector to PyPI as `btctx-mcp==X.Y.Z` (trusted
   publishing, GitHub environment `pypi`, no token; skipped for `-N`
   revisions), creates the tag and one GitHub release (with `SHA256SUMS` of
   its files and a GitHub build attestation of each: once it's out, check
   one file with `gh attestation verify`, as the README shows), and pushes
   `startos/` to DigiMonk73/BTCTX-StartOS's `main` if the `MIRROR_TOKEN`
   secret is set.
   There, Start9's Tag and Release workflow tags it `v<upstream>_<revision>`
   and releases it (needs the mirror's `DEV_KEY` secret and
   `REFERENCE_REGISTRY` variable).
4. Once Start9 has forked the mirror, a release reaches them **only as a
   pull request** from the mirror's `main` to their fork: nobody but Start9
   can change the fork, and the mirror is never edited by hand. The release
   run opens an issue here, "Send vX.Y.Z to Start9", with the one-click link
   and steps for the owner; or open it yourself with the owner's OK
   (`gh pr create -R <fork> --head DigiMonk73:main`, the fork from
   `scripts/start9-pull.sh --fork`). While a pull request of ours is still
   open there, it carries the new release too, and no issue is opened.
5. Check the landing page (DigiMonk73/btctx-site: `index.html`, screenshots in `img/`). Its
   download buttons, release-notes link and Docker `:latest` follow the
   release by themselves; its words don't. Update what the release made
   wrong (action names, StartOS steps, features) in a commit there, shown
   to the owner first: it's public. The pictures too, every release: run
   `make site-shots` (AGENT-TESTS REF-1 already took them), put the changed
   ones in `docs/images/` by pull request (the README's) and in btctx-site's
   `img/`, then fast-forward `main` to `develop` (docs only, see Branches),
   since GitHub shows the README from `main`: so the two always match.

The mirror (DigiMonk73/BTCTX-StartOS) is the repo Start9 forks into
Start9-Community; their fork is then the package's upstream for the
registry. The mirror is generated: never edit it directly, change `startos/`
here. It updates at releases (plus a `next` branch kept by Start9's
`syncNext` workflow), and **stays current between them** (owner's rule): when
a change to `startos/` is docs only (its root-level `*.md`), fast-forward
`main` and run `scripts/sync-startos-mirror.sh --push` right away. The
mirror's Tag and Release ignores root-level `*.md`, so nothing is rebuilt;
check the sync's commit lists only those files. Anything else in `startos/`
(code, `icon.*`, `assets/`, workflows) waits for a release. Once Start9 has
forked, such a sync also needs its pull request to their fork (or rides in
one of ours still open), or Start9 never gets it. Before a release, bring
Start9's changes to their fork back into `startos/` with
`scripts/start9-pull.sh` (`--apply` on a branch cut from `develop`, then a
pull request), or the sync undoes them;
the release workflow's first job stops if you haven't (`--check`). By hand: `scripts/sync-startos-mirror.sh --push`;
if the mirror's own workflow can't release,
`scripts/mirror-startos-release.sh vX.Y.Z <path to btctx.s9pk>`. If
`MIRROR_TOKEN` expires, the mirror job skips with a notice (renewal:
`startos/UPDATING.md`).

## Start9

The whole flow, in plain steps for the owner and every session:
`docs/HOW-CHANGES-FLOW.md` (keep it in step with this file).

- **Start9's rules win for everything Start9 governs** (owner's rule,
  2026-10-10). That is:
  - the StartOS package: `startos/`, including `instructions.md` and
    `startos/README.md`, which Start9's support agent reads; and the
    mirror;
  - which pages the `## Documentation` links in `instructions.md` name
    (Start9's support indexer crawls them: `writing-instructions.md`,
    "Choosing documentation URLs"). The pages themselves, the root README
    and `mcp_server/README.md`, stay the app's own, but what they say
    about StartOS must agree with the package;
  - everything we send to Start9's fork: pull requests, comments,
    promotion requests.

  The app itself, its Docker image and the Mac app follow our own rules.
  - Before deciding anything Start9 governs, read the guide's page. Name
    it in the pull request or comment; if no page covers the question,
    say so.
  - The guide is in `start-technologies/projects/start-sdk/docs/src/`
    beside the main checkout (`~/code/start-technologies`, on `live-docs`:
    the published guide), or at <https://docs.start9.com/packaging>.
  - Where our habits differ, Start9's rule wins there. It doesn't replace
    the owner's call on what is sent, promoted or merged: where the guide
    would change one of the owner's decisions, ask the owner.
- Start9's fork, Start9-Community/BTCTX-StartOS, is where the package is
  built and published; how a change reaches it is under "Releasing".
- Each merge there publishes to Community Beta
  (`https://community-beta-registry.start9.com`). The owner tests it on
  their server, then asks Start9 in an issue on the fork to promote it to
  `https://community-registry.start9.com`. Promotion is the owner's call.
- Start9 sends changes too (template updates about monthly, SDK bumps),
  which `scripts/start9-pull.sh` brings back.

## Working through GitHub

One home for each kind of information, so nothing is kept twice:

| What | Where |
|---|---|
| How we work | this file |
| Where things stand | pinned issue #41, "Where we are": in flight, next for Claude, waiting on Start9 or the owner |
| To-dos, work under way, questions | GitHub issues on this repo, one per task |
| Bugs (the known issues) | public GitHub issues labelled `bug` ("Bugs and security") |
| Security problems | private GitHub security advisories until fixed (`SECURITY.md`) |
| A change | one branch and one pull request into `develop` |
| What's done | `docs/CHANGELOG.md` and the merged pull requests |
| What's next overall | `docs/ROADMAP.md`: checkboxes, ticked when done, cleared at the release that ships them |
| The StartOS package's own to-dos | GitHub issues labelled `start9` (Start9's template keeps no `TODO.md` in the package) |

- **Labels say who has an issue:** `claude` (Claude is on it), `owner`
  (needs the owner: a decision, a test, a click), `ask-grok` (waiting for
  Grok Bot's view), `start9` (the package, Start9's fork or registry); the
  workflows label the issues they open. Labels for what an issue is:
  `bug` (confirmed), `unconfirmed` (a report not yet reproduced),
  `tax-figures` (a figure could be wrong), `security` (hardening, and a
  fix's follow-up once released: never an unfixed vulnerability),
  `enhancement`. A pull request that finishes one says `Closes #N`, and Claude closes the issue when it merges: GitHub
  closes issues by itself only for pull requests into the default branch,
  `main`.
- **A closing word next to an issue number closes it.** In a commit message
  or a pull request, never put "close", "fix" or "resolve" (any form, any
  case, with or without a colon) right before an issue reference (`#N`,
  `owner/repo#N` or an issue's link) unless that commit finishes it.
  GitHub closes the issue when the commit reaches `main`, even months
  later at a release. #165's commit put "fixes:" right before #41 and
  closed the pinned "Where we are" when 1.2.8 fast-forwarded `main`.
  Write "for #N", "on #N" or "(#N)" instead.
- **A long checklist** for work under way may live in `docs/temp/<topic>.md`
  (`docs/temp/README.md`), deleted when done. No other notes, plan or status
  files, and no project status in an AI tool's private memory: it goes in
  an issue, where everyone sees it (private details never do, see below).
- **Asking Grok Bot:** Claude writes the question as a comment that stands
  on its own (what, why, links) on an issue or pull request and adds
  `ask-grok`; the owner gives Grok Bot the link. Grok's answer comes back as
  a comment ending "— Grok" (the owner posts it there, or pastes it into
  their chat with Claude, who posts it), and Claude takes the label off.
- **This repository is public, and so is everything in it:** commits, pull
  requests, issues, the CHANGELOG. Never put the owner's ledger figures,
  personal data, keys, passwords or server addresses in any of them.

## Bugs and security

BitcoinTX is public, its StartOS package is in Start9's Community Beta,
and its figures go on tax returns: users must be able to see every known
bug. These are the public promises of `SECURITY.md`, `CONTRIBUTING.md`
and the README's "Reporting problems"; keep them.

- **Every bug in code on `develop` or in a release becomes a public issue
  as soon as it's verified,** whoever finds it: Claude, Grok, the owner, a
  user, Start9.
  - Findings in the review of an open pull request are fixed in that pull
    request instead.
  - Verify it before filing: reproduce it, or quote the evidence. Say what
    was verified and what wasn't. A report from Grok or a user is a claim
    to check, not a finding.
  - Label it `bug`, plus `tax-figures` when a figure could be wrong.
  - The issue stands on its own: what happens, how to reproduce it, what
    it affects, who found it.
  - Never personal data or the owner's figures; use a test ledger.
  - Fix it as fast as its risk allows. `tax-figures` bugs come first.
- **User reports** arrive labelled `unconfirmed`.
  - Reproduce them, or ask for steps (never for real data).
  - Then relabel `bug`, or close with the reason.
  - Answer within a week.
- **Feature requests** arrive labelled `enhancement`: an idea, never a
  promise (owner's rule, 2026-10-10).
  - Answer within a week: thank them, say it's recorded, promise nothing.
  - The owner decides; until then it carries `owner`. Yes: it goes on
    `docs/ROADMAP.md`, and the issue stays open until the pull request
    that ships it says `Closes #N`. No: close it as "not planned", with a
    kind one-line reason. Not sure: it stays open.
- **Reports and ideas belong in this repository.**
  - The mirror is a copy: its Issues are off, and its description points
    here.
  - Issues users open on Start9's fork are reports too, and the Monday
    report lists them. GitHub can't move an issue between accounts, so,
    with the owner's OK (it's sent to Start9): answer it there and, when
    the work belongs here, open an issue here that links to it.
- **A security problem is never public before its fix.**
  - Outsiders report it privately (Security tab, "Report a vulnerability").
    Claude files its own as a draft advisory ("New draft security
    advisory"), also one found while reviewing: never a pull request
    comment.
  - Test the fix privately with `make check`. GitHub's temporary private
    fork runs no CI and skips the branch rules.
  - Then send it as an ordinary pull request into `develop`, with a
    neutral title, so CI and the review run, and release it the same day.
    Ask Start9 to merge and promote it at once.
  - Publish the advisory (what, which versions, what to do) only once the
    fixed version is available, on StartOS too.
  - Aim to acknowledge a report within 7 days.
  - An advisory titled "Conduct:" is a code-of-conduct report: answer it,
    then close it, never publish it.
- **A fix:**
  - says `Closes #N`, with a test that fails without it;
  - gets a CHANGELOG entry naming the issue.
  - For a `tax-figures` bug, the entry tells users what was wrong, which
    versions and which tax years or transactions it affected, and what to
    do (for example, Ledger Review, then Recalculate Ledger). The release
    repeats it in the StartOS release notes ("Releasing", step 1).
- **The Monday report** lists:
  - open `tax-figures` issues;
  - outside reports with no answer, here, on Start9's fork or on the
    mirror;
  - how many security advisories are waiting (never their details);
  - the latest Grok pass, as Claude recorded it on #41: how many of its
    findings Claude confirmed and how many it didn't, and the next
    monthly area (`docs/GROK-REVIEW.md`).

## Reviews

Before a pull request merges, a fresh Claude reviewer goes through it,
without anyone having to ask: a separate agent with no memory of writing the
change, working read-only, that checks the diff and verifies its claims
(runs the tests, looks things up) instead of trusting them. How far it goes
depends on the change:

| Change | Review |
|---|---|
| Docs, process, tooling | One review; another round only for a blocker |
| App code | A review, then a re-check of the fixes |
| Tax figures or what the app computes, the database, the StartOS package or anything that reaches Start9, releases | A review and a re-check, plus the before-and-after comparison of what the app produces (`scripts/equivalence_check.py`) when figures could move; then the owner's "merge" |

Claude posts the review on the pull request, then fixes every finding (a bug
fix with a test that fails on the old code) or answers it there with the
evidence. Grok in Cursor is a second set of eyes when the owner asks
(`docs/GROK-REVIEW.md`): it never replaces the fresh Claude review, and its
comments end "— Grok (Cursor)".

## Pull requests

Every change, Claude's included, goes into `develop` by pull request, filled
in from `.github/pull_request_template.md`: what and why, a plain-words line
for the owner, how it was tested, the risk. Once the review has nothing
open, Claude turns on GitHub's auto-merge (`gh pr merge N --auto --squash
--match-head-commit <sha>`), and GitHub squashes it, one commit per change,
when the 10 required checks pass (if they already have, GitHub refuses
`--auto`; the same command without `--auto` merges it at once). The owner
allowed `gh pr merge` in this project's local Claude settings for that.
These pull requests get auto-merge only after the owner's "merge" in chat:
a change in tax figures or what the app computes, the database, the StartOS
package or anything that reaches Start9, and releases. A change in what the
app does for the owner is agreed with them before it's written, not at
merge time. Dependabot's pull requests go the same way, after Claude has
read their changelogs; what else they need before merging, and what to do
when one breaks something: `docs/MAINTENANCE.md`, "Before a Dependabot pull
request merges" and the two sections after it.

A branch that falls behind `develop` gets `develop` merged into it, never a
rebase: a pushed branch is not rewritten, and the squash keeps `develop`
clean anyway.

## Big work: a main session and numbered sessions

The owner's standard for big work (2026-10-12, first used for the stable
release, #143): work that won't fit one session, has parts that can run
at once, or needs the owner's decisions between steps (a release, a
redesign, research then build). A single fix or a docs change stays in
one session. Claude suggests this setup when a request is that big.

- **The main session** talks it through with the owner, then writes the
  plan down on GitHub, where every session and the owner can see it:
  - an umbrella issue with the goal, the decisions and the order;
  - an issue per session with its checklist (what "done" means, and the
    "owner" points where it stops); a plan and its build may share one;
  - on each, a comment "Kickoff prompt for this session" that stands on
    its own: how to start, the rules that matter most, the job, and
    what it waits for;
  - on the umbrella, an index of the prompts: the order, and what each
    session waits for.
- **Starting one:** the desktop app's one-click card (`spawn_task`), or
  the kickoff prompt pasted into a new session. Each title starts with
  its number ("6 · Build hourly prices (#144)").
- **Each session** first posts or refreshes its checklist on its issue,
  ticks the boxes there as it goes, and writes its decisions there. It
  carries on from its own issue, not from #41's "Next". After a
  compaction it re-reads its issue and its open pull request before
  anything else. It stops at the "owner" points. At its end it does what
  "Ending a session" says, except that on #41 it adds only its own lines,
  re-reading #41 just before it edits, since other sessions edit it too.
  No plan mode by default: plan mode's plan stays in that session, while
  the issue's checklist is seen by all.
- **The main session** carries the owner's decisions to the sessions, on
  their issues or by a message to one that's running. A "merge" is
  quoted on its pull request, with the date, by the session the owner
  said it to. The main session starts the next session when what it
  waits for is done, and keeps #41's "Next", linking to the umbrella
  issue instead of repeating its order.
- **The footprint and merge plan** (owner, 2026-10-12): planned up front,
  so conflicts are few and expected. On the umbrella issue the main
  session lists, for each session:
  - **its footprint:** the files and areas it expects to touch;
  - **its hot spots, shared with other sessions:** `docs/CHANGELOG.md`,
    `testdata/reference_ledger.json` and `reference_figures.json`,
    `scripts/independent_figures.py`, migrations, `docs/AGENT-TESTS.md`,
    the i18n dictionaries;
  - **any migration numbers reserved for it** (for example 0011, then
    0012 with `down_revision` 0011: Alembic can't load a parent that isn't
    there, so the second is written on the current head until 0011 is on
    `develop`, then re-pointed);
  - **the merge order** between sessions.

  A session whose footprint grows says so on its issue before it merges,
  and the main session checks it against the others.
- **Running sessions at once:** only when they share no hot spot other
  than the CHANGELOG; sessions that share one run one after the other,
  unless the plan names which merges second. The one that merges second
  merges `develop` in (never a rebase), keeps both CHANGELOG entries,
  merges the reference ledger's rows by hand, reruns
  `make reference-figures` (never hand-merging the figures) and checks
  that the diff shows only the two sessions' intended moves, and checks
  the migration numbering.
- **Stacking within a session:** at most two pull requests on the same
  files; merge the first before starting a third, since each squash makes
  the next one conflict.
- **The main session's own handoff:** the main session (the "lead")
  keeps a comment "Kickoff prompt for the lead session" on the umbrella
  issue, edited in place after every change, never left as a snapshot:
  its role and duties, how to start, and a short current state as
  pointers (the running sessions and their open pull requests, what to
  watch, decisions not yet on an issue). Session status stays in the
  index, what waits on the owner on #41 and the `owner` issues, and
  decisions on their issues. After a compaction, the main session
  re-reads that comment and the index first. The owner keeps it as long
  as it works well; when it grows too long, the owner starts a new main
  session from that comment and archives the old one. A new main session
  finds the running sessions in the session list and on the issues,
  since sessions an earlier one started don't send it their end notices.

## Starting a session

Run `make sync-check`: it brings local `main` and `develop` down from
GitHub and says whether anything exists only on this computer: work not
committed in any working folder, branches or commits not on GitHub,
stashes. Another session's unpushed branch may show up: it's theirs. Then read issue #41
(`gh issue view 41`), the open pull requests and issues (`gh pr list`,
`gh issue list`), and carry on from #41's "Next for Claude". Project status
comes from there, not from an AI tool's memory.

## Ending a session

Run `make check-fast` (or push, which runs it), update `docs/CHANGELOG.md`
and the issues worked on, rewrite #41's body for the next session (dated),
and update this file if architecture, invariants or the way we work changed.
Last, run `make sync-check` (or `scripts/sync-check.sh --tidy`, which also
deletes local branches already on GitHub, safe while other sessions run:
never a checked-out branch or a working folder), then remove old session
folders by hand: only clean ones whose pull request merged and that no
running session uses (`git worktree remove`; the owner's choice,
2026-10-06). End the message to the
owner with its answer in one line: **Git: in sync** (everything on GitHub),
or what is only on this computer and why. The owner can't see where work
is, so this line is how they know.
