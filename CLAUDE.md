# CLAUDE.md

Context for AI assistants working on this repo. Keep it current and short;
history belongs in `docs/CHANGELOG.md`.

## What this is

BitcoinTX: a self-hosted, single-user Bitcoin portfolio and tax tracker
(double-entry ledger, per-account FIFO lots, IRS Form 8949 / Schedule D).
This repo, **DigiMonk73/BTCTX-MCP**, is the project, including an MCP server
for AI-assisted entry. Work on `develop` (see Branches).

| Part | Where | Notes |
|---|---|---|
| Backend | `backend/` | FastAPI + SQLAlchemy + SQLite, Python ≥ 3.10 |
| Frontend | `frontend/` | React + TypeScript + Vite, served from `frontend/dist` by the backend |
| MCP server | `mcp_server/` | package `btctx-mcp` (on PyPI from 1.2.0, published by `release.yml`); talks to the backend over HTTP with the AI key (bearer), never a password |
| macOS app | `desktop/` | PyInstaller + pywebview, fixed port `127.0.0.1:8765` (`BTCTX_DESKTOP_PORT`) |
| Docker | `Dockerfile` | data on `/data` (`DATABASE_FILE=/data/btctx.db`); image `ghcr.io/digimonk73/btctx-mcp` |
| StartOS package | `startos/` | start-sdk 2.0.9, self-contained (own `package.json`), mirrored to DigiMonk73/BTCTX-StartOS; read `startos/AGENTS.md` |

## Branches

- **`develop`**: all work. Commit and push here (or merge a short-lived
  branch of your own into it).
- **`main`**: released code only; it is what users get (the `:main` Docker
  image; releases are cut from it). Never commit on `main`, never
  force-push or rewind it. It moves only by fast-forwarding to
  `develop` (`git checkout main && git merge --ff-only develop && git push`),
  at a release, or when everything on `develop` not yet on `main` is docs,
  tests or tooling (nothing that ships in the app or the connector).
- **`release/vX.Y.Z`**: pushed from `main` to publish (see Releasing), then
  deleted.

The pre-push hook refuses a push to `main` of anything not already on
`develop`, and `release.yml` refuses a release commit that isn't on `main`.
If unsure which branch to use, use `develop` and ask.

## Before you change…

- **Database paths, file storage, env vars, Docker**: read `docs/STARTOS_COMPATIBILITY.md`.
  Everything persistent lives in the directory of `DATABASE_FILE`.
- **Models / schema**: write an Alembic migration (`docs/MAINTENANCE.md`,
  "Database migrations"). Never call `create_all()` in app code; the
  `test_models_and_migrations_agree` test fails if models and migrations differ.
- **Dependencies**: read `docs/MAINTENANCE.md`.
- **Desktop app**: read `docs/MACOS_DESKTOP_APP.md`. New backend modules need
  a `hiddenimports` entry in `desktop/BitcoinTX.spec`.
- **IRS forms**: read `docs/IRS_FORM_GENERATION.md`; for a new tax year follow
  `docs/IRS_ANNUAL_FORM_UPDATE.md` (`python scripts/irs_new_year.py YEAR`).

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
  A Spent's proceeds are for `amount`, with no fee cut. The transaction's
  own proceeds/basis/gain are the amount's (fee disposals left out).
- **Transfer**: `amount` is what left the source *including* the BTC fee; the
  destination lot gets `amount − fee`, keeping the source lot's acquisition
  date and pro-rated basis. The fee is a disposal.
- **Proceeds**: the user's figure is anchored in `gross_proceeds_usd`; stored
  `proceeds_usd` is net of fees and is re-derived from gross on every recalc
  (never from the previous net, which would subtract the fee again).
  Unpriced "Spent" withdrawals get FMV proceeds.
- **Income deposits** (source Income/Interest/Reward into a BTC account):
  basis = market value at receipt, which is also the reported income. A blank
  or 0 basis is filled from the daily price on create/update
  (`_value_income_deposit`); no price → 422, never $0.
- **River Sells**: River's Received Amount is net of River's fee, so
  `proceeds_usd` (gross) = Received + fee.
- **Prices**: every past-day valuation goes through
  `services/price_history.daily_price` (table `btc_price_daily`, the UTC day's
  00:00 price). Nothing is asked until the owner picks a price source
  (`services/outbound.py`: off / public / own mempool, optional fallback),
  or the server sets it (`BTCTX_PRICE_SOURCE` and co.; StartOS's Price
  Source & Privacy action), which Settings then shows read-only.
  **No request may name the day**: the own mempool server is asked for its
  whole history (hourly 00:00 rows kept), public sites for the whole history
  in fixed blocks once, then only the latest days; the tests check the URLs.
  Stored days never change. Never today's live price, never $0: no price is
  a 422. A BTC fee's USD value is stored in `transactions.fee_usd`
  at save (`fee_usd_manual` when typed) and recalculation only reads it.
- **Holding period**: long-term only when disposed *after* the one-year
  anniversary (IRS "more than one year"), dates taken in the tax timezone.
- **Tax timezone**: timestamps are stored in UTC. The tax timezone (Settings,
  `app_settings` table, fallback env `BTCTX_TIMEZONE`, default UTC) decides
  tax-year bounds, 8949 dates and the holding period. Helpers in
  `backend/services/tax_time.py`. Never slice a year with naive UTC dates.
- **Form 8949 boxes** (`form_8949.py`): ≤2024 C/F; 2025+ exchange Sells H/K
  (1099-DA without basis); 2026+ Sells of lots bought on the exchange on/after
  2026-01-01 and never moved G/J; self-custody spends and fees I/L. A
  Sell/Withdrawal's `broker_reporting` (none/proceeds/basis) overrides those
  rules for that transaction. One sheet per box, Schedule D line per box,
  column (f) blank.

## Key files

| File | Purpose |
|---|---|
| `backend/main.py` | app, session middleware, router mounting, `get_current_user` |
| `backend/migrate.py`, `backend/migrations/` | schema migrations run at startup, adoption of pre-migration DBs, pre-upgrade backups |
| `backend/secret_key.py` | per-install session key in `.btctx_secret_key` (never a hardcoded key) |
| `backend/services/transaction.py` | ledger, lots, FIFO, fees, proceeds, recalculation |
| `backend/services/tax_time.py` | tax timezone helpers |
| `backend/services/price_history.py` | stored daily BTC prices (`btc_price_daily`); date-free downloads from the own mempool or public sites |
| `backend/services/outbound.py` | the only HTTP client factory for outside services; Privacy & network settings (price source unset/off/public/mempool, fallback, proxy for public sites), or the server's `BTCTX_*` overrides |
| `backend/services/review.py` | read-only Ledger review (`/api/review`, `cli review`, MCP `review_ledger`) and the explicit fee-value fix |
| `backend/services/first_run.py`, `login_throttle.py` | first-run setup code (default login); login throttling |
| `backend/services/reports/safe_text.py` | ReportLab text escaping, no remote fetches |
| `backend/services/ai_key.py` | the AI key: Mac key file or created in Settings, hash only, on/off switch, `AI_KEY_ROUTES` allow-list |
| `backend/services/entry_import.py` | JSON entry import used by the MCP server: validate, FMV autofill, dedup, dry run |
| `backend/services/river_import.py`, `csv_import.py` | file imports |
| `backend/services/reports/form_8949.py` | 8949/Schedule D data, boxes, field maps per year |
| `backend/services/reports/pdf_form_filler.py` | fill + flatten IRS PDFs with pypdf |
| `backend/services/reports/reporting_core.py` | complete tax report data |
| `backend/routers/user.py` | setup-status / reset-account (claim the default `admin`/`password`) |
| `mcp_server/btctx_mcp/server.py`, `guide.py` | MCP tools and the ledger guide the AI reads |
| `mcp_server/AI_SETUP.md`, `frontend/src/utils/aiSetup.ts` | setup guide an AI follows to install the MCP server; the Settings prompt and configs that point to it |
| `frontend/src/styles/theme.css`, `components.css` | design tokens, and the only button/input/card/badge styles (`.btn-primary`, `.input`, `.card`…); page stylesheets only lay these out. Safari 15 CSS only (Mac app WebKit) |
| `backend/cli.py` | maintenance CLI (migrate, set-password, recalculate, review); the StartOS package relies on it |
| `backend/security_headers.py` | CSP (browsers, not the Mac webview), no-referrer, nosniff, no framing; Secure cookie over HTTPS |
| `backend/session_auth.py` | session stamp of the password hash (a password change ends other sessions) |
| `frontend/e2e/`, `frontend/playwright.config.ts` | Playwright click-through specs; projects chicago, tokyo, webkit |
| `scripts/sync-startos-mirror.sh`, `start9-pull.sh`, `mirror-startos-release.sh` | StartOS mirror sync; taking back Start9's changes to their fork; the mirror's release by hand |
| `scripts/irs_new_year.py` | yearly IRS template download + verification |
| `scripts/smoke_test.py` | end-to-end run against a real server |

## Security rules

- All API routers require login (or the AI key, below) except
  `POST /api/users/register`, `GET /api/users/setup-status`,
  `POST /api/users/reset-account`, `GET /api/health` (status, version,
  schema only) and login. User routes may only touch the logged-in user.
- `SECRET_KEY` values in `secret_key.PUBLIC_DEFAULTS` are ignored. Never add a
  default key anywhere.
- The debug router, `DELETE /api/transactions/delete_all` and
  `PUT /api/settings/tax-timezone` are login-only (never the AI key); tests
  use the first two, the MCP server must not expose bulk delete. Sessions carry a stamp of the password hash
  (`backend/session_auth.py`): changing the password or resetting the account
  ends every other session. API docs (`/docs`, `/openapi.json`) only with DEBUG.
- Login, reset-account and password changes are throttled
  (`services/login_throttle.py`, per client and global; 429 + Retry-After).
  New passwords need 12+ characters; a change needs the current password.
- While the account has the default login (Docker/source before it's
  claimed), logging in with it and claiming it need the one-time setup code
  (`services/first_run.py`, `<data dir>/setup-code.txt`, printed to the
  log). Not in the Mac app (127.0.0.1 only); StartOS never has the default.
- Non-GET requests a browser marks as from another site (`Sec-Fetch-Site`,
  else `Origin`) are refused (`security_headers.py`); no CORS unless
  `CORS_ALLOW_ORIGINS` is set.
- Report PDFs: every ledger string passes `reports/safe_text.py` (escaped for
  ReportLab, which may fetch nothing remote); CSV text cells can't start a
  formula.
- The MCP server authenticates with the AI key (`backend/services/ai_key.py`,
  `Authorization: Bearer`), never a password; there is no other API key. Mac
  app: the key is in the owner-only `mcp.json` and works only from localhost.
  Docker/StartOS: the owner creates, replaces or revokes it in Settings (shown
  once). Only its SHA-256 is stored; a restore keeps the current key and
  switch. It works only while AI access is on (off by default) and only on
  `AI_KEY_ROUTES`, the routes the MCP tools call; any other route is 403. A
  new MCP tool that needs a route adds it there on purpose (a test checks the
  tools and the list agree). Never allow the key on login, users, key or
  switch settings, backup download/restore, CSV export, imports, delete-all,
  Ledger Review fixes, settings changes or debug.

## Testing (see `docs/TESTING.md`)

```bash
make hooks       # once: pre-push gate
make test-fast   # ~650 hermetic tests (backend + MCP), ~1 min
make test        # + slow stress and property tests
make smoke       # real server, temp DB
make e2e         # Playwright click-through (Chromium, Chicago + Tokyo), ~5 min
make preview     # this checkout in a browser, 127.0.0.1:8777, throwaway data (launch.json "preview")
make docker-smoke  # build the image here + CI's container checks
make check       # lint + test + smoke + audit-deps (CI adds e2e, StartOS, Docker, macOS)
```

Tests never touch a real database or the network (temp SQLite, stubbed BTC
prices). A bug fix gets a test that fails on the old code. Lint is ruff with
all Pyflakes rules and ESLint with zero warnings.

## Releasing

Full steps, the package version and the signing/mirror secrets:
`startos/UPDATING.md`. In short:

1. On `develop`: bump `VERSION`, the version in `desktop/BitcoinTX.spec`,
   the image tag in `startos/startos/manifest/index.ts`,
   `startos/startos/versions/current.ts` and `mcp_server/pyproject.toml`
   (`backend/tests/test_versions_agree.py` fails until they agree). Move the CHANGELOG's Unreleased section to the
   version. Minor bump when a new tax year's forms are added. Push; wait for CI.
   Run `docs/AGENT-TESTS.md` (an agent on a StartOS VM) on that commit's CI
   artifacts; a blocker FAIL stops the release.
2. Fast-forward `main` to `develop` and push: `.github/workflows/image.yml`
   publishes `ghcr.io/digimonk73/btctx-mcp:vX.Y.Z` (never overwritten) and
   `:main`.
3. Push a branch `release/vX.Y.Z` from `main`, and delete it once the
   release is out: `.github/workflows/release.yml` builds the
   macOS `.dmg` + `.zip` and `btctx.s9pk` (signed with the `DEV_KEY` secret if
   set), publishes the AI connector to PyPI as `btctx-mcp==X.Y.Z` (trusted
   publishing, GitHub environment `pypi`, no token; skipped for `-N`
   revisions), creates the tag and one GitHub release, and pushes `startos/`
   to DigiMonk73/BTCTX-StartOS's `main` if the `MIRROR_TOKEN` secret is set.
   There, Start9's Tag and Release workflow tags it `v<upstream>_<revision>`
   and releases it (needs the mirror's `DEV_KEY` secret and
   `REFERENCE_REGISTRY` variable).
4. Once Start9 has forked the mirror: open a PR from the mirror's `main` to
   their fork.

The mirror (DigiMonk73/BTCTX-StartOS) is the repo Start9 forks into
Start9-Community; their fork is then the package's upstream for the
registry. The mirror is generated: never edit it directly, change `startos/`
here. It updates only on releases (plus a `next` branch kept by Start9's
`syncNext` workflow). Before a release, bring Start9's changes to their fork
back into `startos/` with `scripts/start9-pull.sh` (`--apply` on `develop`),
or the sync undoes them. By hand: `scripts/sync-startos-mirror.sh --push`;
if the mirror's own workflow can't release,
`scripts/mirror-startos-release.sh vX.Y.Z <path to btctx.s9pk>`. If
`MIRROR_TOKEN` expires, the mirror job skips with a notice (renewal:
`startos/UPDATING.md`).

## Plans and checklists

Short-lived checklists, plans, to-do lists and feature ideas go in
`docs/temp/` (one file per topic; its README has the rules): check items off,
move anything lasting to the code, CHANGELOG or ROADMAP, then delete the
file. Look there at the start of a session. Never in `startos/`.

## Ending a session

Run `make check-fast` (or push, which runs it), update `docs/CHANGELOG.md`,
and update this file if architecture or invariants changed.
