# Docker & StartOS: Container Layout and Data Persistence

> Read this before changing database paths, file storage, ports, or
> environment handling. The StartOS wrapper depends on the contracts below.

## Two repositories

| Repo | Contents | Produces |
|------|----------|----------|
| This repo ([BitcoinTX-org/btctx-org](https://github.com/BitcoinTX-org/btctx-org)) | Backend, frontend, `Dockerfile`, all app logic | Docker image `b1ackswan/btctx:vX.Y.Z` (+ `:latest`) |
| Wrapper ([PlebRick/BTCTX-StartOS](https://github.com/PlebRick/BTCTX-StartOS)) | StartOS manifest, startup/backup procedures, actions; no app code | `.s9pk` package |

The wrapper tells StartOS how to run our image: which volume to mount, which
environment variables to set, how to health-check, and how to back up. The
wrapper-side details below describe that repo; check it for the current
source.

## The Docker image

`Dockerfile` is a two-stage build:

1. `node:22-slim`: `npm ci && npm run build` in `frontend/`
2. `python:3.11-slim`: `pip install -r backend/requirements.txt`, copies
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
  └── backups/             automatic copies taken before a schema upgrade
                           or a restore (mode 600; only created when needed)
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
docker build -t btctx . && docker run -d -p 8080:80 -v btctx-data:/data btctx
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
    (also `BTCTX_NEW_PASSWORD` env); used on install and by Reset Login
    Credentials. Never takes the password as an argument.
  - `python -m backend.cli recalculate`: rebuilds the ledger; the Recalculate
    Ledger action.
  Each command migrates first, so it works on an empty volume. Exit 0 on
  success, 1 with a message on stderr on failure.
- **Logging:** `LOG_LEVEL` env (default INFO).
- **Volume:** data at `/data`, database path from `DATABASE_FILE`. Only the
  newest 5 automatic copies are kept in `/data/backups/`.
- `backend.database.create_tables()` stays as an alias of `init_db()` for
  packages from before the CLI (0.8.0:1 and older).

### Image for this fork

The wrapper at DigiMonk73/BTCTX-StartOS runs
`ghcr.io/digimonk73/btctx-mcp:vX.Y.Z`, published by
`.github/workflows/image.yml` (amd64 + arm64) the first time `VERSION` on
`main` holds a new version. Version tags are never overwritten. The contract
below still applies to it.

### Docker tag contract

The wrapper pins our image by version tag, and a daily job compares its pinned
tag with Docker Hub to detect releases. Every release must:

1. **Use an exact version tag:** `b1ackswan/btctx:vX.Y.Z`, matching the git
   release tag and `^v[0-9]+\.[0-9]+\.[0-9]+$` (no `-rc` / `-beta`).
2. **Never overwrite a version tag.** If a build needs fixing, cut a new patch
   version.
3. **Be multi-arch:** `linux/amd64` and `linux/arm64` in one manifest list.
4. **Treat `:latest` as convenience only:** push it with the version tag, never
   on its own.

`scripts/release-docker.sh` enforces all four (it refuses a bad tag pattern, a
missing git tag, or a tag that already exists on Docker Hub):

```bash
git tag vX.Y.Z && ./scripts/release-docker.sh vX.Y.Z
```

## Wrapper overview (PlebRick/BTCTX-StartOS)

| File | Purpose |
|------|---------|
| `startos/manifest.ts` | Package metadata, volume `main`, architectures |
| `startos/procedures/main.ts` | Mounts `main` at `/data`, runs uvicorn with `DATABASE_FILE=/data/btctx.db`, health check |
| `startos/procedures/backups.ts` | StartOS backup of the whole `main` volume |
| `startos/procedures/interfaces.ts` | Network interfaces |
| `startos/procedures/actions/*.ts` | Actions such as showing or resetting the admin credentials |

StartOS backups cover the whole volume (database and secret key). The app
also has its own password-encrypted backup (Settings, or
`POST /api/backup/download` / `/api/backup/restore`), which covers the
database only.

If the wrapper's `manifest.ts` declares only `aarch64`, the package won't
install on x86_64 servers even though the image supports both; the fix belongs
in the wrapper (`images.main.arch` and `hardwareRequirements.arch`).

## Testing checklist

CI (`.github/workflows/ci.yml`) already builds the image, checks that
`btctx.db` and `.btctx_secret_key` are created in `/data`, and runs
`scripts/smoke_test.py` against the running container. For changes to paths or
storage, also check by hand:

```bash
docker build -t btctx:test .
docker run -d --name btctx-test -p 8080:80 -v btctx-test-data:/data btctx:test

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
| Docker image | `b1ackswan/btctx:vX.Y.Z` (pinned by wrapper; `:latest` also pushed) |
| Architectures | `linux/amd64`, `linux/arm64` |
| Entry point | `backend.main:app` |
| Port | 80 |
| Data volume | `/data` |
| Database | `/data/btctx.db` (image default of `DATABASE_FILE`) |
| Session key | `/data/.btctx_secret_key` (auto-generated) or `SECRET_KEY` env |
| MCP server | Set `BTCTX_URL` to the StartOS address; see [mcp_server/README.md](../mcp_server/README.md) |
