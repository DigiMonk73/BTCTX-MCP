# Privacy and leak audit: BitcoinTX 1.2.1 (2026-09-29)

Part of `stabilization-plan.md`, step 4. Every way data or metadata leaves
the machine or sits on disk, with a verdict. Code read on `develop`
(1.2.1 plus the VM-test fixes, 8858dd5); live checks on the StartOS VM
(`~/code/btctx-vm-lab/scenarios/agent-test-1.2.1-published.md`).
"Checked" means Claude re-read the code or saw it on the VM, not only the
audit agent. Go through the "decide" items with the owner one at a time;
lasting results go to the code, CHANGELOG or docs, then delete this file.

Verdicts: **no leak** (verified) · **leak** (real, not documented) ·
**documented only** (real, the app warns) · **fix proposed**.

## The short answer

The core promise holds: **no request ever names a transaction date**,
**nothing is contacted until the owner picks a price source** (and nothing
at all when it's Off), **Tor fails closed** (seen on the VM: every request
failed, none went direct), the browser talks only to the app itself, and
secrets are never logged. What's left is smaller: five real leaks, all
minor, and some things that are only documented.

## Summary

| # | Item | Verdict | One line | Checked |
|---|---|---|---|---|
| 1a | One HTTP client factory (`outbound.py`) | no leak | a test enforces it; the Mac app only calls 127.0.0.1 | |
| 1b | Unset or Off, and at startup | no leak | nothing contacted, incl. MCP tools, reports, review, import autofill | VM (PRC-1) |
| 1c | Date-free URLs, fallbacks included | no leak | fixed history blocks and "latest" requests | VM (Bitstamp URLs) |
| 1d | Timing seen by price sites | **documented** (Settings, StartOS); block height cached 60 s | they can tell when the app is open (price every 2 min while a page is visible) and when a recent entry is priced | |
| 1e | Hosts named in Settings | **fixed** (all named, plus timing; test guards new hosts) | mempool.space, Coinbase and Kraken's history are contacted but never named | yes |
| 1f | User-Agent `python-httpx/0.28.1` | no leak | the same for every install; don't add a version | |
| 1g | socks5 vs socks5h, fail closed | no leak | the hostname goes to the proxy either way; no direct retry | VM (PRC-3) |
| 1h | `.onion` mempool address with no proxy | **fixed** (was: leak) | accepted, then looked up through normal DNS | yes |
| 1i | Clearnet mempool server bypasses Tor | documented only | Settings says only `.onion` uses the proxy | |
| 1j | In-app restore brings back the backup's price settings | **fixed** (owner: keep the settings in use) | an old "public, no proxy" backup turns lookups on again, directly; the code does it on purpose (the AI key and login, by contrast, stay) | yes |
| 1k | CoinGecko refuses VPN and Tor addresses | **fixed** (owner: Kraken first, CoinGecko fallback) | CloudFront 403 from a VPN IP and from Tor; every live price then costs two sites (CoinGecko, Kraken) | VM + curl |
| 2 | Browser: CSP, headers, cookie, storage, links, Mac webview | no leak | strict CSP, no-referrer, HttpOnly cookie, no browser storage, only self-hosted fonts | VM (SEC-3, SEC-7) |
| 3a | Service logs | **counts fixed**; httpx URLs remain (minor) | no secrets or dates, but per-year counts at INFO, whole rows at DEBUG, every outbound URL (httpx) | VM (log read) |
| 3b | Encrypted backup file | **fixed** (owner: hidden, typed twice, no minimum) | good crypto (AES-256 + HMAC, PBKDF2 600k); the password is typed into a plain `prompt()`, shown, not confirmed, no minimum | yes |
| 3c | Temporary plain copy while backing up | **fixed** | a plain SQLite snapshot in the system temp folder (0700, deleted after); the restore's staging file is chmod'ed after writing | yes |
| 3d | Plain copies in `<data>/backups/` | documented only | up to 5 pre-upgrade/pre-restore + 3 AI copies, unencrypted, outlive deleted entries; in the docs, not the app | |
| 3e | Deleted rows stay in the SQLite file | leak (minor) | no `secure_delete`, no VACUUM | |
| 3f | File permissions | no leak | database, secret key, setup code, `mcp.json`: 0600 | VM (`/data` listing) |
| 3g | Docker `/data` is `chmod 777` | fix proposed | cosmetic in a root-only container | |
| 3h | StartOS backup contents | documented only | the database, secret key, plain copies, and `store.json` with the generated password in clear (stale once changed) | |
| 4a | What the AI provider sees | documented only | the whole ledger through the tools, plus the tax timezone; warned in four places | VM (AI-1) |
| 4b | Setup prompt contains the server address | documented only | a LAN or `.onion` address and the app version go to the provider when pasted | VM |
| 4c | AI key over `http://` | **warned** (owner: connector warns once) | no scheme check in the connector; the README's own example is `http://192.168.1.50:8080` | |
| 4d | Connector logs | **fixed** (was: leak) | the MCP SDK logs at INFO, so httpx writes `…/price/history?date=2024-03-05` into the AI app's log files | yes |
| 4e | `uvx` fetches from PyPI | documented only (partly) | PyPI sees the IP, time and exact version | |
| 5a | StartOS interfaces | no leak | only HTTPS is offered on the LAN; plain HTTP only inside the server (lo, lxcbr0); nothing public unless the owner turns it on | VM (host bindings) |
| 5b | Docker publishes plain HTTP on all interfaces | **fixed** (README: 127.0.0.1 + HTTPS note) | README uses `-p 8080:80` with no warning: password, cookie and ledger in clear on the LAN | yes |
| 5c | `/api/health` version; `server: uvicorn` | fix proposed (low) | version fingerprinting from the LAN or Tor | VM (SEC-3) |

## Details worth reading

- **1d Timing.** The live price is asked every 120 s while any page is
  visible (the sidebar converter), with a 60 s server cache; block height
  on every Dashboard visit, no cache. The "latest days" history download
  runs when the owner values a day newer than the last download, at most
  once a UTC day: it shows *that* a recent entry is being made, not its
  date. IP exposure is documented (Settings, StartOS instructions); timing
  isn't.
- **1h `.onion` without a proxy.** `outbound.save` accepts it and
  `own_node_client` connects directly, so the system resolver (and
  whoever runs it) sees the onion name; the connection then fails.
- **1j Restore.** `routers/backup.py:133` reloads the restored database's
  price source, mempool address and proxy ("The restored database carries
  its own network settings"). Someone who moved to Tor since the backup
  gets direct requests again after restoring it. The AI key and switch are
  kept by `ai_key.carry_over`; the same could be done for these four
  settings. Not an issue when StartOS's action sets them.
- **3a Logs.** `reports.py:106`, `transaction_history.py:129-132,315,441`,
  `reporting_core.py:183` log per-year counts ("Found 4 transactions for
  year=2025 in date range …") at INFO; `LOG_LEVEL=DEBUG` dumps rows.
- **3h StartOS backup.** Volumes `main` and `startos` (`backups.ts`). A
  StartOS-level restore brings back the old login and AI key (unlike the
  in-app restore) — that's StartOS restoring the whole service, expected.
- **4d Connector logs.** Verified: after importing the server, the root
  logger is INFO with a RichHandler and httpx inherits it. Claude Desktop
  keeps MCP server stderr in `~/Library/Logs/Claude/`. The key isn't
  logged; request lines are.
- **5b Docker.** `uvicorn --host 0.0.0.0` inside the container is normal;
  the README's `-p 8080:80` publishes it on every interface. The setup
  code still protects a fresh install, but after that the login travels
  in clear to any LAN client.

## Proposed fixes, smallest safe change each (priority order)

1. **4d** Connector: `logging.getLogger("httpx").setLevel(logging.WARNING)`
   in `mcp_server/btctx_mcp/server.py`, with a test.
2. **1h** `.onion` mempool address needs a proxy: 422 in `outbound.save`
   ("An .onion address needs a Tor proxy"), and `own_node_client` refuses.
3. **1j** Restore keeps the privacy settings in use (like the AI key), or
   at least says in the restore message that they came from the backup.
   Owner decides.
4. **5b / 4c** README: `-p 127.0.0.1:8080:80` plus one line on plain HTTP;
   connector: warn (or refuse without `BTCTX_ALLOW_HTTP=1`) on `http://` to
   a host that isn't loopback.
5. **3b** Backup password: a password field with confirmation and a
   12-character minimum checked on the server.
6. **3c** Snapshot in memory instead of a temp file; create `.restoring`
   with mode 0600 from the start.
7. **1d / 1k** Fewer requests: cache block height 60 s; ask Kraken before
   CoinGecko (or drop CoinGecko, which refuses VPN and Tor users).
8. **1e** Name all the hosts in Settings' help text, plus one line on
   timing.
9. **3e / 3d** `PRAGMA secure_delete=ON`; a Settings note that `backups/`
   holds plain copies.
10. **3a** Per-year count logs to DEBUG; document that DEBUG logs rows.
11. **Low (3g, 5c, 4e)** `chmod 700 /data`; `--no-server-header`; health
    version only to loopback or logged-in callers (the Mac app reads it
    from loopback); one README line on what PyPI sees.

Items 1, 2, 6 and 10 were plain bug fixes: done (commit after cb834be). 3, 4, 5, 7, 8, 9 and 11 change
behaviour or text the owner sees: decide each.
