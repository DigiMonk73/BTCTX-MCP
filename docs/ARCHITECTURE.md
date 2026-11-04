# Architecture

What BitcoinTX is made of, the data it keeps and where each part
lives. Read it before a change that spans parts, or to find a file.

Moved word for word from `AGENTS.md` on 2026-11-04 (#903); `AGENTS.md`
now keeps a map of where each part lives. Where the text below says
"this file", it means `AGENTS.md` and the files its map names, and a
section named in quotes ("Branches", "Reviews") is found through that
map.

## What this is

BitcoinTX: a self-hosted, single-user Bitcoin portfolio and tax tracker
(double-entry ledger, per-wallet FIFO lots or the coins chosen in a
wallet, IRS Form 8949 / Schedule D). This repo, **DigiMonk73/BTCTX-MCP**,
is the project, including an MCP server for optional AI-assisted entry
(off until the owner turns it on). Work goes into `develop` by pull
request (see Branches).

| Part | Where | Notes |
|---|---|---|
| Backend | `backend/` | FastAPI + SQLAlchemy + SQLite, Python ≥ 3.11 |
| Frontend | `frontend/` | React + TypeScript + Vite, served from `frontend/dist` by the backend |
| MCP server | `mcp_server/` | package `btctx-mcp` (on PyPI from 1.2.0, published by `release.yml`); talks to the backend over HTTP with the AI key (bearer), never a password |
| macOS app | `desktop/` | PyInstaller + pywebview, fixed port `127.0.0.1:8765` (`BTCTX_DESKTOP_PORT`) |
| Docker | `Dockerfile` | Python 3.13; data on `/data` (`DATABASE_FILE=/data/btctx.db`); runs as its own user `btctx` (uid 10001), never root (`docker-entrypoint.sh`, #202); image `ghcr.io/digimonk73/btctx-mcp` |
| Landing page | DigiMonk73/btctx-site | <https://digimonk73.github.io/btctx-site/>, `index.html` with screenshots in `img/`, on GitHub Pages; the manifest's `marketingUrl` and the connector's Homepage. Its download links follow the latest release by themselves; its text and screenshots don't (Releasing, step 5) |
| StartOS package | `startos/` | start-sdk 3.1.1 (StartOS 0.4.0.2 or later), self-contained (own `package.json`), mirrored to DigiMonk73/BTCTX-StartOS; read `startos/AGENTS.md` |

## Data model

```
Transaction (user input)
  → ChosenCoin (user input too: the coins it chose to leave a wallet, #711)
  → LedgerEntry (double-entry lines)
  → BitcoinLot (BTC acquisitions, per account, each knowing its acquisition)
  → LotDisposal (FIFO consumption, or the coins chosen, with basis/proceeds/gain per lot)
```

Accounts (2.0, #251; the account book, `services/account.py`, read once
per request): your banks, wallets and exchanges, each exchange two
accounts, "*name* USD" and "*name* BTC", of a row of `exchanges` with its
1099-DA switch (asked when it's added, on unless answered No: #708); the
fee accounts BTC Fees 5 and USD Fees 6 (internal: no
transaction names them); External 99 (no row). A new install's first of
each keep their ids forever: Bank 1, Wallet 2, Exchange USD 3, Exchange
BTC 4 (exchange 1, "Exchange"). New accounts take ids from 100, never one
given before (`accounts_last_id`). In a file, the reserved names (Bank,
Wallet, Exchange USD, Exchange BTC, BTC Fees, USD Fees, External) always
mean 1–6 and 99. Whether an account is bitcoin is its currency
(`book.is_btc`), never its id.

Schema: Alembic migrations in `backend/migrations/versions/` (0001 = the
v0.7.0 schema). `backend/migrate.py` runs them at every start and on restored
backups: fresh DBs are built from 0001, pre-migration DBs are repaired to the
baseline and stamped, a copy goes to `<db dir>/backups/` before any change,
and a schema newer than the code is refused. `database.create_tables` is an
alias of `init_db` kept for StartOS packages from before the CLI (0.8.0:1
and older).

Every update and delete, and a create dated before the latest transaction,
runs `recalculate_all_transactions` ("scorched earth"): all ledger lines,
lots and disposals are rebuilt in timestamp order (a create dated last only
adds its own lines and lots, #172). So derived values must be recomputable
from the Transaction row (and the coins it chose) alone.

**The past-year warning** (2.0, #352; `services/past_years.py`): an add,
edit or delete on `/api/transactions` that would change the figures of a
tax year before this one (Ledger Review's snapshot, each disposal's Form
8949 box and column (b) (a gift's, donation's or lost coins' own, on no
Form 8949: their holding period and date acquired, #736), what the report
counts as income or a rebate and as a gift, donation or lost coins, each
row's date and tax year: `services/year_changes.py`)
answers 409 (`detail`, `years`, `changes`, `pending`, `recalc_error`,
`exact`, `timezone`: the one its rows' dates are in, `confirm`; and
`coins_chosen` only beside a write that adds or changes a choice of coins
dated in an earlier tax year, #711) and saves nothing. Sent again with
`?confirm=<fingerprint>`, it's saved under the write lock after a copy (a
"pre-change" one, the newest 5 and the first of each day for a week; a
fresh AI copy with the key), the fingerprint checked again before the
commit, in `hourly_prices.with_prices_found`. The check runs on
`database.scratch_copy` with the lock free, its prices found first; a write
dated in this tax year (`tax_time.current_tax_year`, pinned to 2009 in the
tests) or one moving only dollars saves at once, and past
`past_years.DRY_RUN_SECONDS` (10 s, from the StartOS VM's measurement) the
years come from the write's date. With a login, changes a recalculation
alone would make never ask (the owner's "Don't warn for fixes"); with the
AI key, those in an earlier year do.
`recalculated_by` (`app_settings`) names the BitcoinTX that last
recalculated the whole live ledger (every full replay writes it, a scratch
copy's or a partial one's never): while it matches, nothing is pending. The
scripts and the click-through specs confirm the 409 (`send_confirmed`,
`sendConfirmed`, `saveForm`).
The other writes go through the same `past_years.save`, each a write of
its own (#353; `services/past_year_writes.py`): the AI's import and River's
(one confirm for the batch or file, its duplicate check run inside the
write lock its rows are written under; only the rows that check keeps
count, so a batch sent again asks nothing; the AI's preview gives the
execute's 409 as `past_years`, River's lists the past years its new rows
are dated in as `past_years_dated`), Settings' Save of the tax timezone
(each pass reads dates in its own timezone, so a row whose tax year moves
is listed under both; the timezone in use saved again never asks; the
login's fill is 1.x's, an empty ledger only), an exchange's 1099-DA
switch (`PUT /api/accounts/{id}` `{sends_1099da}`: boxes compared, no
replay) and, with the AI key,
Recalculate Ledger (what it changes is `pending`; with a login it never
asks). The AI connector answers a 409 as the tool's answer (`saved: false`,
the fields, how to confirm: `confirm`, which `update_transaction` also
takes as `confirm_move`), and gives the writes that can answer one, and Ledger
Review, 1,200 s (`client.LONG_TIMEOUT`, from the VM's measurement;
#637).

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
| `backend/services/account.py`, `routers/account.py`, `frontend/src/utils/accounts.ts`, `useAccounts.ts`, `components/LedgerAccounts.tsx` | the account book (2.0, #251): kinds, ids from 100, names, add, rename, hide, delete while unused, each exchange's 1099-DA switch (through the past-year warning); the frontend's copy of the book, loaded once per page and afresh as Settings or its accounts section opens (#720); Settings' "Wallets, exchanges and banks" |
| `backend/services/past_years.py`, `year_changes.py`, `recalculated_by.py`, `past_year_writes.py` | the past-year warning (2.0, #352): its dry run, 409 and confirmed save; what a write changes, year by year; which BitcoinTX last recalculated the ledger; the imports', the tax timezone's, the 1099-DA switch's and the AI's Recalculate Ledger's writes through it (#353) |
| `backend/services/chosen_coins.py` | the coins a transaction chose to leave a wallet (#711): a request's choice checked, stored with when it was saved, the edit rule, the lots a choice may take, `NotHeld`; the engine's hook that hands a form, or the AI's preview, the coins held (`HELD_HOOK`) |
| `backend/services/transfer_coins.py`, `frontend/src/components/transactionForm/LeavingCoins.tsx`, `MovedCoinsTable.tsx` | the coins a Transfer between two bitcoin accounts, or a Withdrawal from a wallet, will take, listed before it saves (#706): its save's own path run on a scratch copy (`past_years.Write.apply`), asked with the body the Save sends; the newest list asked for wins (`transaction.SUPERSEDED`); from a wallet, what it holds then (`held`, through `chosen_coins.HELD_HOOK`); a saved one's, the AI key too (#711, Q4) |
| `frontend/src/components/transactionForm/ChosenCoins.tsx`, `ChosenCoinsTable.tsx`, `frontend/src/utils/chosenCoins.ts` | the form's coin picker (#711, C3): what a wallet holds, a BTC field per purchase, the quick fills (Q3: "Highest cost first" only on a transaction dated today, `dated_today`), the rule's words, the running total; Save waits until it adds up; the form's `chosenCoins`, sent as `chosen_coins` |
| `backend/services/wipe.py`, `frontend/src/components/DeleteAllDialog.tsx` | deleting every transaction: what goes, the typed `DELETE`, the copy first (#256), only what the dialog showed (#377) |
| `backend/services/first_run.py`, `login_throttle.py` | first-run setup code (default login); login throttling, and the device cookie of a browser that logged in |
| `backend/services/reports/safe_text.py` | ReportLab text escaping; ReportLab opens no file and fetches nothing |
| `backend/services/ai_key.py` | the AI key: Mac key file or created in Settings, hash only, on/off switch, `AI_KEY_ROUTES` allow-list |
| `backend/services/entry_import.py` | JSON entry import used by the MCP server: validate, FMV autofill, dedup, dry run |
| `backend/services/river_import.py`, `csv_import.py`, `csv_choices.py` | file imports; the CSV's chosen-coins columns (#711) |
| `backend/services/exchange_import.py`, `exchange_mappings.py`, `exchange_cells.py`, `exchange_kraken.py` | any exchange's CSV (B5b): the mappings (ready-made, the owner's own in `app_settings`), each read into River's rows; what isn't read is named by reason |
| `backend/services/reports/form_8949.py` | 8949/Schedule D data, boxes, field maps per year |
| `backend/services/reports/pdf_form_filler.py` | fill + flatten IRS PDFs with pypdf |
| `backend/services/reports/draft_forms.py` | next year's IRS draft forms: the shipped preview (`assets/irs_templates/drafts/`, until January 1 after its year) and a test install's (`<data dir>/irs-draft-forms/`, `cli install-draft-forms`) |
| `backend/services/reports/reporting_core.py` | complete tax report data |
| `backend/services/reports/complete_tax_report.py`, `pdf_layout.py`, `frontend/src/utils/disclaimer.ts` | Complete Tax Report PDF (section 6 "Using these forms", the rebates table); the one disclaimer and the notice to add each wallet and exchange (`DISCLAIMER`, `ACCOUNTS_NOTICE`; `test_disclaimer.py` keeps them the same as the README's) |
| `backend/routers/user.py` | setup-status / reset-account (claim the default `admin`/`password`) |
| `mcp_server/btctx_mcp/server.py`, `guide.py` | MCP tools and the ledger guide the AI reads |
| `mcp_server/AI_SETUP.md`, `frontend/src/utils/aiSetup.ts` | setup guide an AI follows to install the MCP server; the Settings prompt and configs that point to it |
| `frontend/src/styles/theme.css`, `components.css` | design tokens, and the only button/input/card/badge styles (`.btn-primary`, `.input`, `.card`…); page stylesheets only lay these out. Safari 15 CSS only (Mac app WebKit) |
| `backend/cli.py` | maintenance CLI (migrate, set-password, recalculate, review); the StartOS package relies on it |
| `backend/unexpected_errors.py` | an error nobody expected: a fixed sentence in the answer, its type in the log, its trace at DEBUG (`log_unexpected`, `UnexpectedErrorMiddleware`) |
| `backend/security_headers.py` | CSP (browsers, not the Mac webview), no-referrer, nosniff, no framing, no-store on the API; Secure cookies over HTTPS; the cross-site guard; the Mac app answers only at 127.0.0.1, localhost or [::1] |
| `backend/session_auth.py` | the open sessions (an id per login, the newest 20 kept in `app_settings`; logout ends one) and the stamp of the password hash (a password change ends all others) |
| `frontend/e2e/`, `frontend/playwright.config.ts` | Playwright click-through specs; projects chicago, tokyo, webkit |
| `scripts/sync-startos-mirror.sh`, `start9-pull.sh`, `mirror-startos-release.sh` | StartOS mirror sync; taking back Start9's changes to their fork; the mirror's release by hand |
| `scripts/sync-check.sh` (`make sync-check`) | is everything on this computer also on GitHub; brings `main`/`develop`/`2.0` down; `--tidy` deletes branches already on GitHub |
| `scripts/irs_new_year.py` | yearly IRS template download + verification |
| `scripts/smoke_test.py` | end-to-end run against a real server |
| `testdata/reference_ledger.json`, `reference_figures.json`, `reference_prices.json` | the one reference test ledger (2023–2026 and a 2022 deposit, every 8949 box, rebates, dates originally acquired; from 2.0 its `accounts` list, a hidden and a renamed account, and `"since": "2.0"` rows filling 2.0's dimensions in every year, #702; its `"priced"` rows take their values from the stored-price fixture, `reference_prices.json`, #715) and every figure it gives; `test_seed_ledger.py` fails if one moves (`make reference-figures` accepts a meant change) |
| `testdata/reference_ledger.csv`, `testdata/exchange_files/`, `docs/HAND-TEST.md`, `backend/tests/hand_test_tables.py` | the test pack (#844): that ledger as the app's CSV (`test_reference_csv_844.py`: it survives an export and an import, every figure the same), a made-up file for each exchange importer, the guide for testing them by hand on a throwaway install, and its tables worked out from the app's own answers (`make test-pack`) |
| `scripts/seed_ledger.py`, `reference_figures.py` | load that ledger into an empty server over the API (refuses the Mac app; the `"priced"` rows only with `--with-prices`, after `--store-prices` put the fixture in the test database's file); a database's figures, or `--compare` them |
| `scripts/independent_figures.py` | a second calculation of that ledger's tax figures (8949, Schedule D, gains, Sales by exchange, income, rebates, gifts, lots at each year's start and end) from the rules, never the app's code; `test_independent_figures.py` fails on a difference in them |
| `frontend/e2e/shots/site.ts`, `testdata/showcase_ledger.json` | the README's (`docs/images/`) and landing page's four pictures (`make site-shots`), from a small typical portfolio |
