# CLAUDE.md

Context for AI assistants working on this repo. Keep it current and short;
history belongs in `docs/CHANGELOG.md`.

## What this is

BitcoinTX: a self-hosted, single-user Bitcoin portfolio and tax tracker
(double-entry ledger, per-account FIFO lots, IRS Form 8949 / Schedule D).
This repo, **DigiMonk73/BTCTX-MCP**, forks
[BitcoinTX-org/BTCTX](https://github.com/BitcoinTX-org/BTCTX) and adds an MCP
server for AI-assisted entry plus tax and security fixes. Work on `main`.

| Part | Where | Notes |
|---|---|---|
| Backend | `backend/` | FastAPI + SQLAlchemy + SQLite, Python ≥ 3.10 |
| Frontend | `frontend/` | React + TypeScript + Vite, served from `frontend/dist` by the backend |
| MCP server | `mcp_server/` | package `btctx-mcp`; talks to the backend over HTTP with a session login |
| macOS app | `desktop/` | PyInstaller + pywebview, fixed port `127.0.0.1:8765` (`BTCTX_DESKTOP_PORT`) |
| Docker | `Dockerfile` | data on `/data` (`DATABASE_FILE=/data/btctx.db`); image `ghcr.io/digimonk73/btctx-mcp` |
| StartOS package | `startos/` | start-sdk 2.0.9, self-contained (own `package.json`), mirrored to DigiMonk73/BTCTX-StartOS; read `startos/AGENTS.md` |

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
  00:00 price; bulk download on a miss). Never today's live price, never $0:
  no price is a 422. A BTC fee's USD value is stored in `transactions.fee_usd`
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
| `backend/services/price_history.py`, `outbound.py` | stored daily BTC prices; the only HTTP client factory for outside services |
| `backend/services/review.py` | read-only Ledger review (`/api/review`, `cli review`, MCP `review_ledger`) and the explicit fee-value fix |
| `backend/services/entry_import.py` | JSON entry import used by the MCP server: validate, FMV autofill, dedup, dry run |
| `backend/services/river_import.py`, `csv_import.py` | file imports |
| `backend/services/reports/form_8949.py` | 8949/Schedule D data, boxes, field maps per year |
| `backend/services/reports/pdf_form_filler.py` | fill + flatten IRS PDFs with pypdf |
| `backend/services/reports/reporting_core.py` | complete tax report data |
| `backend/routers/user.py` | setup-status / reset-account (claim the default `admin`/`password`) |
| `mcp_server/btctx_mcp/server.py`, `guide.py` | MCP tools and the ledger guide the AI reads |
| `mcp_server/AI_SETUP.md`, `frontend/src/utils/aiSetup.ts` | setup guide an AI follows to install the MCP server; the Settings prompt and configs that point to it |
| `scripts/irs_new_year.py` | yearly IRS template download + verification |
| `scripts/smoke_test.py` | end-to-end run against a real server |

## Security rules

- All API routers require login except `POST /api/users/register`,
  `GET /api/users/setup-status`, `POST /api/users/reset-account`,
  `GET /api/health` (status, version, schema only) and login.
  User routes may only touch the logged-in user.
- `SECRET_KEY` values in `secret_key.PUBLIC_DEFAULTS` are ignored. Never add a
  default key anywhere.
- The debug router, `DELETE /api/transactions/delete_all` and
  `PUT /api/settings/tax-timezone` are login-only (never the `API_KEY` or the
  AI assistant key); tests use the first two, the MCP server must not expose
  bulk delete. Sessions carry a stamp of the password hash
  (`backend/session_auth.py`): changing the password or resetting the account
  ends every other session. API docs (`/docs`, `/openapi.json`) only with DEBUG.
- Mac app only: the MCP server authenticates with the AI assistant key from
  `mcp.json` (`backend/services/mcp_key.py`), never a password. The key works
  only from localhost, only when `BTCTX_DESKTOP`/`BTCTX_MCP_FILE` are set, and
  never for backup/restore, CSV/River import, delete-all or the key settings.

## Testing (see `docs/TESTING.md`)

```bash
make hooks       # once: pre-push gate
make test-fast   # ~285 hermetic tests, ~1.5 min
make test        # + slow stress tests
make smoke       # real server, temp DB
make check       # everything CI runs except Docker/macOS builds
```

Tests never touch a real database or the network (temp SQLite, stubbed BTC
prices). A bug fix gets a test that fails on the old code. Lint is ruff with
all Pyflakes rules and ESLint with zero warnings.

## Releasing

Full steps, the package version and the signing/mirror secrets:
`startos/UPDATING.md`. In short:

1. Bump `VERSION`, the version in `desktop/BitcoinTX.spec`, the image tag in
   `startos/startos/manifest/index.ts` and `startos/startos/versions/current.ts`
   (`backend/tests/test_versions_agree.py` fails until they agree). Move the
   CHANGELOG's Unreleased section to the version. Minor bump when a new tax
   year's forms are added.
2. Merge to `main`: `.github/workflows/image.yml` publishes
   `ghcr.io/digimonk73/btctx-mcp:vX.Y.Z` (never overwritten) and `:main`.
3. Push a branch `release/vX.Y.Z`: `.github/workflows/release.yml` builds the
   macOS `.dmg` + `.zip` and `btctx.s9pk` (signed with the `DEV_KEY` secret if
   set), creates the tag and one GitHub release, and mirrors `startos/` to
   DigiMonk73/BTCTX-StartOS if the `MIRROR_TOKEN` secret is set
   (`scripts/sync-startos-mirror.sh` does it by hand).

## Ending a session

Run `make check-fast` (or push, which runs it), update `docs/CHANGELOG.md`,
and update this file if architecture or invariants changed.
