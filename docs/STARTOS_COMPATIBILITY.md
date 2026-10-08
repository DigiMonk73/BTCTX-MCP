# Docker & StartOS: Container Layout and Data Persistence

> Read this before changing database paths, file storage, ports, or
> environment handling. The StartOS package (`startos/`) depends on the
> contracts below.

## One repository, three artifacts

| Part | Where | Produces |
|------|-------|----------|
| App | `backend/`, `frontend/`, `Dockerfile` | image `ghcr.io/digimonk73/btctx-mcp:vX.Y.Z` (amd64 + arm64) |
| macOS app | `desktop/` | `BitcoinTX-macOS.dmg` / `.zip` |
| StartOS package | `startos/` (start-sdk 3.0.3, StartOS 0.4.0.2 or later) | `btctx.s9pk`, which runs the image above |

All three carry the version in `VERSION` (checked by
`backend/tests/test_versions_agree.py`). `startos/` is self-contained and is
mirrored as-is to [DigiMonk73/BTCTX-StartOS](https://github.com/DigiMonk73/BTCTX-StartOS),
the repository Start9's community registry forks. How the package
works: `startos/README.md`; how to release and bump it, and how Start9's
changes come back here: `startos/UPDATING.md`.

## The Docker image

`Dockerfile` is a two-stage build:

1. `node:22-slim`: `npm ci && npm run build` in `frontend/`
2. `python:3.11-slim`: `pip install --require-hashes --only-binary :all: -r
   backend/requirements.txt` (the lock, wheels only), copies
   `backend/` to `/app/backend` and the built frontend to `/app/frontend/dist`,
   creates `/data`, sets `ENV DATABASE_FILE=/data/btctx.db`, and runs
   `uvicorn backend.main:app --host 0.0.0.0 --port 80`.

No system packages are installed: IRS forms are filled in pure Python (pypdf).

```
/app/backend/          application code (ephemeral, replaced on update)
/app/frontend/dist/    built React app
/data/                 volume mount point (persistent)
  ├── btctx.db             SQLite database
  ├── .btctx_secret_key    per-install session signing key (mode 600)
  ├── setup-code.txt       one-time first-run code while the account still has
  │                        the default login (mode 600; deleted once claimed;
  │                        never on StartOS, whose login is set before the first start)
  └── backups/             automatic copies taken before a schema upgrade,
                           a restore, or asked for with the AI key (mode 600;
                           only created when needed)
```

On every start the app migrates `btctx.db` to the current schema
(`backend/migrate.py`, scripts in `backend/migrations/`), copying it to
`/data/backups/` first when there is anything to change. An update is
therefore: pull the new image, restart. A newer database than the image
understands (after a downgrade) is refused with a clear error rather than
opened.

## Data persistence

Containers are ephemeral: anything written outside a mounted volume is lost
when the container is replaced. The image stores its data in `/data`, so mount a
volume there. StartOS mounts its persistent volume (`main`) at `/data`.

### DATABASE_FILE

`backend/database.py` (and `backend/services/backup.py`, which must match)
reads `DATABASE_FILE`; a relative path is resolved against the repo root.

| Environment | Database path | Set by |
|-------------|---------------|--------|
| Local development | `backend/bitcoin_tracker.db` | Default in code (or `.env`) |
| Docker (standalone) | `/data/btctx.db` | Image default (`ENV` in `Dockerfile`) |
| StartOS | `/data/btctx.db` | Image default; the wrapper also sets the same value |
| macOS app | `~/Library/Application Support/BitcoinTX/btctx.db` | `desktop/entrypoint.py` |

An `-e DATABASE_FILE=...` at run time still overrides the image default.
Standalone run, with the data on a named volume:

```bash
docker build -t btctx . && docker run -d -p 127.0.0.1:8080:80 -v btctx-data:/data btctx
```

Without a `-v` mount, `/data` lives in the container and is lost when the
container is removed.

### Session secret key

`backend/secret_key.py` uses the `SECRET_KEY` env var if set (ignoring known
public placeholder values); otherwise it generates a random key once and stores
it as `.btctx_secret_key` in the database's folder. In the container that is
`/data/.btctx_secret_key`, so it
persists across updates and is included in volume backups. Nothing needs to be
configured.

### Rules

1. All persistent data goes under the directory of `DATABASE_FILE` (`/data`).
2. Never hardcode a database path; derive it from `DATABASE_FILE`.
3. Temporary files (report generation, uploads) use `tempfile`, not paths
   under `/app`.
4. Test path/storage changes in Docker, not just local dev.
5. Settings (tax timezone, Privacy & Network, AI key state) and the daily
   price history are rows in the database (`app_settings`,
   `btc_price_daily`), not files. The one exception is the price settings
   below, which the server may set instead.
6. A test install may also hold the IRS's draft forms, in
   `irs-draft-forms/` (docs/IRS_FORM_GENERATION.md, "Draft forms on a test
   install"); a normal install never has that folder.

### Price settings set by the server

`backend/services/outbound.py` reads these at startup (and every CLI
command does). When `BTCTX_PRICE_SOURCE` is set they replace Settings →
Privacy & Network, which shows them read-only (`GET /api/settings/network`
says `"managed": true`; a change is 409); the stored settings stay untouched
underneath and come back once the variable is gone.

| Variable | Values |
|----------|--------|
| `BTCTX_PRICE_SOURCE` | `off`, `public` or `mempool`; unset or empty: Settings decide |
| `BTCTX_MEMPOOL_URL` | the mempool server, `http(s)://host:port`; may be empty with `mempool` (then nothing answers but the fallback, and the app says Mempool isn't available) |
| `BTCTX_MEMPOOL_FALLBACK` | `on`/`off` (also true/false, 1/0, yes/no): ask public sites when the mempool server can't answer |
| `BTCTX_PROXY_URL` | proxy for public sites, e.g. `socks5h://10.0.3.1:9050` |

An invalid value turns price lookups off (an error in the log says which).
The StartOS package sets them from its Price Source & Privacy action, with
Mempool's and Tor's bridge addresses (`startos/startos/priceSource.ts`; a test
checks the names agree). Docker users may set them the same way.

## Contracts the StartOS package depends on

Change these only together with the package (`startos/`):

- **Entry point and port:** `backend.main:app`, plain HTTP on port 80.
- **Health:** `GET /api/health` (no login) answers 200 with
  `{"status": "ok", "version", "schema"}` when the database is reachable at
  the current schema, 503 otherwise. The package's health check requires 200.
- **App location:** code at `/app` in the image, `VERSION` at `/app/VERSION`.
- **Maintenance CLI** (`backend/cli.py`, run from `/app`):
  - `python -m backend.cli migrate`: schema upgrade + default user/accounts;
    the package runs it as a oneshot before the web server starts.
  - `python -m backend.cli set-password [--username NAME] --password-stdin`:
    sets the first user's password through the app's own bcrypt hashing
    (also `BTCTX_NEW_PASSWORD` env; at least 12 characters); used by
    Set Login Credentials. Never takes the password as an
    argument. With `--if-default` it changes only a login still on
    `admin` / `password`, printing `Password set for user 'admin'.` when it
    did and `Not the default login: nothing changed.` otherwise; the update
    to 1.2.0 uses it to retire old default logins.
  - `python -m backend.cli recalculate`: rebuilds the ledger; the Recalculate
    Ledger action (run with the price variables above, as it may look up a
    missing day's price).
  - `python -m backend.cli review [--fix-fee-prices]`: the read-only Ledger
    Review; not used by the package.
  Each command migrates first, so it works on an empty volume. Exit 0 on
  success, 1 with a message on stderr on failure.
- **Price settings:** the `BTCTX_*` variables above.
- **Logging:** `LOG_LEVEL` env (default INFO).
- **Volume:** data at `/data`, database path from `DATABASE_FILE`. Only the
  newest 5 automatic copies are kept in `/data/backups/`.
- `backend.database.create_tables()` stays as an alias of `init_db()` for
  packages from before the CLI (0.8.0:1 and older).

### Image tags

`.github/workflows/image.yml` publishes `ghcr.io/digimonk73/btctx-mcp`
(amd64 + arm64) on every push to `main`: `:v<VERSION>` and `:latest` the first
time a VERSION is seen (version tags are never overwritten; a fix is a new
patch version), plus `:main` and `:sha-<sha>`. The StartOS package (mirrored
to DigiMonk73/BTCTX-StartOS) pins `:v<VERSION>` in
`startos/startos/manifest/index.ts`.

StartOS backups cover both package volumes (`main`: database, secret key,
pre-upgrade copies; `startos`: the package's `store.json`). The app also has
its own password-encrypted backup (Settings, or `POST /api/backup/download` /
`/api/backup/restore`), which covers the database only.

## Testing checklist

CI (`.github/workflows/ci.yml`) already builds the image, checks that
`btctx.db` and `.btctx_secret_key` are created in `/data`, and runs
`scripts/smoke_test.py` against the running container. For changes to paths or
storage, also check by hand:

```bash
docker build -t btctx:test .
docker run -d --name btctx-test -p 127.0.0.1:8080:80 -v btctx-test-data:/data btctx:test

# Database, key and backup service all point at /data
docker exec btctx-test ls -la /data/
docker exec btctx-test python -c "from backend.services.backup import DB_PATH; print(DB_PATH)"

# End-to-end against the EMPTY test container (it creates transactions)
python scripts/smoke_test.py --url http://127.0.0.1:8080

# Persistence: data (and your login) survive a restart
docker restart btctx-test

# Clean up
docker rm -f btctx-test && docker volume rm btctx-test-data
```

To test encrypted backup/restore by hand, log in first (backup routes need a
session):

```bash
curl -c jar -H 'content-type: application/json' \
  -d '{"username":"admin","password":"..."}' http://localhost:8080/api/login
curl -b jar -X POST -F password=test123 http://localhost:8080/api/backup/download -o backup.btx
curl -b jar -X POST -F password=test123 -F file=@backup.btx http://localhost:8080/api/backup/restore
```

## Quick reference

| What | Value |
|------|-------|
| Docker image | `ghcr.io/digimonk73/btctx-mcp:vX.Y.Z` (pinned by `startos/`) |
| Architectures | `linux/amd64`, `linux/arm64` |
| Entry point | `backend.main:app` |
| Port | 80 |
| Data volume | `/data` |
| Database | `/data/btctx.db` (image default of `DATABASE_FILE`) |
| Session key | `/data/.btctx_secret_key` (auto-generated) or `SECRET_KEY` env |
| Health | `GET /api/health` (200 = database at current schema) |
| Maintenance | `python -m backend.cli migrate \| set-password \| recalculate` |
| Price settings | `BTCTX_PRICE_SOURCE`, `BTCTX_MEMPOOL_URL`, `BTCTX_MEMPOOL_FALLBACK`, `BTCTX_PROXY_URL` (optional) |
| MCP server | Set `BTCTX_URL` to the StartOS address; see [mcp_server/README.md](../mcp_server/README.md) |
