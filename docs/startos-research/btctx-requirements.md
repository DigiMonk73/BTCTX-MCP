# What BitcoinTX needs from its StartOS package (app-side inventory)

Source of truth: DigiMonk73/BTCTX-MCP @ main (6a773f2), wrapper DigiMonk73/BTCTX-StartOS @ 325492e (v0.8.0:1, start-sdk 2.0.9).

## Runtime facts
- One process: `uvicorn backend.main:app --host 0.0.0.0 --port 80` (Dockerfile CMD; wrapper main.ts repeats it).
- Data: volume `main` at /data
  - /data/btctx.db (SQLite, DATABASE_FILE; image default since v0.8.0)
  - /data/.btctx_secret_key (session signing key, 0600, auto-generated)
  - /data/backups/*.db (app's pre-upgrade/pre-restore copies, 0600; grow by one per schema upgrade/restore — no retention yet)
  - /data/.startos-wrapper.json (wrapper store: generated admin password) — at volume root `/.startos-wrapper.json`
- Schema: app migrates itself at startup (Alembic, backend/migrate.py); refuses a DB newer than the code.
  `backend.database.create_tables()` = init_db (migrate + seed) — used by wrapper's setCredentialsScript.
- Auth: session cookie login; optional `API_KEY` env enables X-API-Key for most API routes (not imports/backup).
  `/api/users/setup-status` public; default account admin/password until claimed; wrapper sets random password on install.
- Outbound network: BTC price APIs (CoinGecko, Kraken, CoinDesk). irs.gov not needed at runtime (templates bundled).
- No health endpoint today (only `GET /` serves SPA). → ADD `GET /api/health` (no auth): DB reachable + schema at head + version.
- Logging: backend/database.py forces `logging.basicConfig(level=DEBUG)` → noisy StartOS logs (httpcore, DEBUG spam). → ADD LOG_LEVEL env, default INFO.
- Version: VERSION file (0.8.0). Desktop spec also carries it.

## User-facing needs on StartOS
1. Web UI (http :80 behind StartOS TLS).
2. Connecting an AI (MCP): the MCP server runs on the user's computer, needs BTCTX_URL (the StartOS LAN https URL),
   username/password, and the StartOS root CA (BTCTX_CA_BUNDLE) or BTCTX_VERIFY_TLS=false.
   → Candidate action "Connect an AI assistant": shows the service URL(s), and ready-to-paste Claude Desktop JSON /
     `claude mcp add` command (masked password). Big usability win; no one else would think to do it.
   → Maybe a separate `api` interface type for MCP clients (same port, path /api) so the URL is discoverable.
3. Credentials: Show (exists), Reset (exists, requires stopped).
4. Recalculate Ledger (exists in app UI; could be a StartOS action for post-update task).
5. After update from <0.8.0: user should click Recalculate once → candidate: a StartOS *task* created by the
   0.8.0 migration ("Recalculate ledger after upgrade"), instead of relying on release notes.
6. Backups: StartOS volume backups. SQLite consistency while running → pre-backup hook to snapshot the DB
   (sqlite backup API) if StartOS doesn't stop the service for backups. Consider excluding /data/backups/ or pruning.
7. Restore: app's own encrypted restore stays; StartOS restore restores volume.
8. Tax timezone: set in app UI (auto from browser). Nothing needed.
9. Health: web UI ready + DB/schema ok (via /api/health).
10. Tor/clearnet: default LAN; public exposure is a user choice — instructions should warn (financial data; login required).

## Upgrade path constraints
- Package id stays `btctx`; version graph continues after 0.8.0:1 (existing installs: 0.3.x…0.8.0:1).
- Existing installs' data layout must be untouched.
- Signing: every past release used a fresh throwaway key in CI; confirm sideload updates don't require same key.

## Repo integration constraints (monorepo)
- Package lives in BTCTX-MCP subdirectory (e.g. `startos/`), its own package.json/node_modules.
- Image: `dockerBuild` from repo Dockerfile (same commit) vs `dockerTag` of GHCR built earlier in the same release run.
- One release: VERSION → GHCR image + mac .app/.dmg + btctx.s9pk + GitHub release.
- Mirror to DigiMonk73/BTCTX-StartOS for Marketplace (automated sync?).
