# v1.0.3 plan: AI keys for every edition, connector auto-update, doc fixes

> **Temporary file. Delete it in the v1.0.3 release commit** (and remove its
> line from `MEMORY.md` if a memory points here). It is a working plan, not
> documentation: once v1.0.3 ships, the CHANGELOG, READMEs and code are the
> record.

Written 2026-09-27 from the owner's brief ("Part A / B / C", pasted in the
session that wrote this) and a read of the code at `9f5d071`. Nothing in this
plan is built yet. The owner's decisions (section 1) were recorded the same
day: backup option A, `API_KEY` removed, a password in the connector's config
refused, and no PyPI (the connector installs from GitHub `main`).

**How to use it.** Section 1 holds the decisions (all made). Work on
`develop` (`CLAUDE.md`, "Branches"). Start a session with:

> Read `docs/V1_0_3_PLAN.md` and `CLAUDE.md`. Implement the plan as written
> (with my edits), Part A first, and stop if anything in the code contradicts
> the plan.

Contents:
1. Decisions and options (read this)
2. PyPI (deferred, not part of v1.0.3)
3. How it works today (background)
4. Part A: the AI key, step by step
5. Part B: connector auto-update from `main`, version check
6. Part C: doc fixes
7. Wording rules
8. Tests
9. Verification before release (including the Docker run)
10. Release steps and what to report

---

## 1. Decisions and options

Each item says what the plan does (**Plan**) and why, then the alternatives.
Items marked **Decided** were the owner's choices; the others follow
directly from the brief.

### 1.1 What "make a backup" does with the AI key — Decided: A

**The problem.** The brief says the AI key may create "the same backup the
app's Backup button makes, saved where the app normally saves backups". Those
two halves don't describe one thing today:

- The **Backup button** (Settings → Backup & Restore) asks you for a backup
  password, encrypts the whole database with it (`.btx` file, AES with a key
  derived from the password, plus an integrity check), and streams the file
  to your browser, which saves it in your Downloads folder. Nothing is kept on
  the server.
- The only backups the app **saves on the server** are the automatic copies in
  the `backups/` folder next to the database (`/data/backups/` in Docker and
  StartOS, `~/Library/Application Support/BitcoinTX/backups/` on the Mac). The
  app makes one before every database upgrade and every restore. They are
  plain copies of the database file (not encrypted), readable only by the
  owner (mode 600), and only the newest 5 are kept.

So there are three ways to give the AI a backup ability:

**Option A — a server-side copy in `backups/` (Plan, recommended).**
A new tool, `backup_ledger`, asks BitcoinTX to copy the database into the
`backups/` folder, named e.g. `btctx-ai-2026-10-02T14-03-11.db`. The AI gets
back the file name and time, never the file itself.

- *Pros:* no password is involved, so none can leak through the AI; the copy
  stays on the same machine as the database, exactly as protected as the
  database itself (same owner-only permissions); on StartOS, StartOS backups
  include it automatically; useful as a safety net before the AI makes a big
  batch of changes ("back up, then import these 40 rows").
- *Cons:* it is not encrypted (but neither is the live database next to it,
  so an attacker who can read one can read the other); it protects against
  mistakes, not against losing the machine; the files take disk space.
- *Details:* AI copies are kept separately from the pre-upgrade copies: their
  own name prefix and their own limit (keep the newest **3**), so an AI
  asking for backups can never push the pre-upgrade copies out. Restoring
  one stays login-only (Settings → Backup & Restore doesn't list server
  copies today; restoring from them is a manual file copy, documented in
  `docs/MAINTENANCE.md`). A limit of one backup per minute stops a runaway AI
  from churning the folder.

**Option B — an encrypted `.btx` saved on your computer.**
The connector (which runs on your computer) calls the same endpoint as the
Backup button and saves the `.btx` in a folder on your computer.

- *Pros:* identical to the Backup button's file; off the server, so it
  survives losing the server.
- *Cons:* **it needs a backup password, and the only way to give one is
  through the AI**: you type it in the chat, or the AI makes one up and tells
  you. Either way the password passes through the AI's model, and with a
  cloud AI it reaches the provider, next to the encrypted file's name. That
  undermines both the encryption and the point of this release (no secrets
  through the AI). A password in the connector's config file would avoid the
  chat but is one more secret in a plain-text file.

**Option C — no backups with the AI key.**

- *Pros:* smallest change; nothing new to secure.
- *Cons:* goes against the brief; the AI can't take a safety copy before a
  large import, so the user has to remember to press Backup first.

**Decided: A** (owner, 2026-09-27). It gives the safety net the brief wants
without routing any secret through the AI.

### 1.2 The optional `API_KEY` setting — Decided: remove it

`API_KEY` is an environment setting (unset by default) that, when set, lets
any request with the header `X-API-Key: <value>` act as you on almost every
route (not delete-all, backup/restore, CSV and River import, tax timezone
or the debug routes, which are login-only). It predates the MCP server ("e.g., Telegram
bot" in a code comment); no documentation tells anyone to set it.

- *Remove (Plan):* one key system instead of two. It's an unlimited key kept
  in plain text in an environment variable, exactly the kind of secret this
  release takes away from the AI. Anyone relying on it (unlikely: it's
  undocumented) would use an AI key instead, which is limited and revocable.
- *Fold it in:* make `API_KEY` a second way to supply the AI key. Two ways to
  configure the same thing, and a key that can't be revoked from Settings.
- *Leave it:* the brief allows it, but it would remain a stronger key than
  the AI key, which defeats the purpose of limiting the AI key.

Decided (owner, 2026-09-27: nobody else uses it). Breaking change, stated in
the CHANGELOG ("`API_KEY` is gone; use an AI key").
Tests that set `backend.main.API_KEY` (in `test_entry_import.py`,
`test_network_settings.py`, `test_review.py`, `test_security.py`) switch to the
AI key.

### 1.3 Recalculate with the AI key — Plan: allowed

`POST /api/transactions/recalculate` rebuilds ledger lines, lots and gains
from your saved transactions. It never changes what you entered; running it
twice gives the same result. So it isn't "destructive" in the brief's sense,
and the existing `recalculate_ledger` tool keeps working. The **Ledger
Review "Fix these"** action (`POST /api/review/fee-prices`), which *changes*
stored fee values, stays login-only.

### 1.4 What the key may do — Plan: an allow-list

Today the Mac key works on every route except a few blocked one by one. The
plan flips that: the key works **only** on routes listed in one place
(`AI_KEY_ROUTES` in `backend/services/ai_key.py`), matched by method and
route template. Any other route answers **403** with "The AI key can't do
this. Log in to BitcoinTX to do it." New routes added later are closed to the
key unless someone adds them on purpose.

The list (exactly what the MCP tools use, plus health and backup):

| Method | Route | Tool |
|---|---|---|
| GET | `/api/health` | version check (no auth anyway) |
| GET | `/api/transactions`, `/api/transactions/{id}` | `list_transactions`, update/delete lookups |
| PUT | `/api/transactions/{id}` | `update_transaction` |
| DELETE | `/api/transactions/{id}` | `delete_transaction` |
| POST | `/api/transactions/recalculate` | `recalculate_ledger` |
| POST | `/api/import/entries/preview`, `/api/import/entries/execute` | `preview_transactions`, `add_transactions` |
| GET | `/api/calculations/accounts/balances`, `/api/calculations/average-cost-basis` | `get_portfolio` |
| GET | `/api/bitcoin/price`, `/api/bitcoin/price/history` | `get_portfolio`, `get_btc_price` |
| GET | `/api/settings/tax-timezone` | `get_portfolio` (read only) |
| GET | `/api/review` | `review_ledger` |
| POST | `/api/backup/ai-copy` (new) | `backup_ledger` (Option A) |

Refused with 403 even with a valid key (one test per category): login and
logout, password or username change (`/api/users/...`), AI key
create/new/revoke, AI on/off, restore, backup download (`.btx`), CSV export,
CSV and River import, delete-all, account changes, Ledger Review fixes, tax
timezone and Privacy & Network changes, the debug routes, reports.

Reports (PDF/CSV) are left off the list because no tool uses them. Adding
them later is one line, if a tool ever needs them.

### 1.5 Mac app — Plan: keep the automatic key, localhost only

The Mac app keeps writing the owner-only `mcp.json` itself, and its key keeps
working only from the Mac itself. The Mac app does **not** get the
"Create AI key" buttons: an AI on another computer reaching a Mac app isn't a
supported setup (the app only listens on 127.0.0.1). One key model with two
ways of delivering the key: a file on the Mac, a copy-once key elsewhere.

### 1.6 Old connectors pinned to v1.0.2 — a limit code can't remove

The web login must keep accepting your password (that's how you use the
app). A connector from v1.0.2 or earlier, with a password in its config,
logs in exactly like a browser does, so v1.0.3's server can't tell them
apart and can't refuse it. What closes this: the new connector ignores
passwords (1.7), and the rotation note (section 6) tells Docker and StartOS
users to change their BitcoinTX password after switching to a key. The
CHANGELOG says this plainly.

### 1.7 Password in the connector's config — Decided: refuse

`BTCTX_PASSWORD` set at all (an old setup, or a key added but the password
left behind): the connector makes no request, and every tool answers with
the one line from the brief: "BitcoinTX no longer uses your password for AI
access. Create an AI key in BitcoinTX Settings and replace BTCTX_PASSWORD
with BTCTX_AI_KEY in your AI app's settings, then delete the password from
that file." Refusing (rather than working and nagging) is the owner's choice
(2026-09-27): it's the surest way to get the password out of the file, and
it is one code path.

### 1.8 Defaults and upgrades — from the brief

- New installs, every edition: AI access **off**, no key.
- Existing Mac installs: keep the stored switch (off unless you turned it on,
  since v1.0.2).
- Existing Docker/StartOS installs: off and no key until you create one (they
  never had a stored setting, so nothing to migrate).

### 1.9 Connector distribution — Decided: GitHub `main`, no PyPI

The owner doesn't want another service to run (2026-09-27). The connector
installs from this repository's `main` branch:

`uvx --from "git+https://github.com/DigiMonk73/BTCTX-MCP.git@main#subdirectory=mcp_server" btctx-mcp`

On every start, uvx asks GitHub which commit `main` is at and rebuilds when
it moved (checked 2026-09-27 with uv 0.11.10: each run queries
`api.github.com/repos/digimonk73/btctx-mcp/commits/main`). `main` only moves
at releases (`CLAUDE.md`, "Branches", set up the same day), so users get each
released connector by restarting their AI app, and never half-finished work.
Like today's pinned install, it needs `git` on the user's computer. A pinned
`@vX.Y.Z` stays documented under "Pin a version".

---

## 2. PyPI (deferred, not part of v1.0.3)

Not needed for v1.0.3 (1.9). Kept for later: publishing to PyPI would drop
the `git` requirement and make installs faster (`uvx btctx-mcp@latest`). It
needs the owner's PyPI account with two-factor login, one release job
(`pypa/gh-action-pypi-publish`, skipped on `-N` package-only revisions since
PyPI never accepts a version twice), and a GitHub environment `pypi`.

PyPI "trusted publishing" lets GitHub Actions upload the `btctx-mcp` package
with no password or token stored anywhere: PyPI trusts a specific workflow in
a specific repository. For a project that doesn't exist on PyPI yet you
register a *pending* publisher once. The name `btctx-mcp` was free on
2026-09-27.

1. Go to **https://pypi.org** and log in (create an account if you don't
   have one; turn on two-factor authentication, which PyPI requires).
2. Top right: your username → **Your account** → **Publishing** (left menu).
3. Under **Add a new pending publisher**, pick the **GitHub** tab and fill in
   exactly:
   - **PyPI Project Name:** `btctx-mcp`
   - **Owner:** `DigiMonk73`
   - **Repository name:** `BTCTX-MCP`
   - **Workflow name:** `release.yml`
   - **Environment name:** `pypi`
4. Click **Add**. That's all. The first release that runs the new job
   creates the project on PyPI and makes you its owner.

The session that adds the job also creates the GitHub environment `pypi` on
BTCTX-MCP (Settings → Environments, or `gh api`). It needs no secrets; it
just has to exist for the name to match. If this file is gone by then, these
steps are in its git history (deleted in the v1.0.3 release commit).

---

## 3. How it works today (background)

- `backend/main.py` `get_current_user` accepts, in order: a logged-in session;
  `X-API-Key` equal to the `API_KEY` env setting; the AI assistant key
  (`backend/services/mcp_key.py`), which exists only in the Mac app
  (`BTCTX_MCP_FILE` set by the launcher), works only from 127.0.0.1 and only
  while AI access is on (off by default since v1.0.2).
- Some routes then insist on a session themselves: backup and restore, CSV and
  River import (`_require_auth` in `routers/backup.py` and
  `routers/csv_import.py`), delete-all, tax timezone, the AI access settings,
  the debug router (`require_login`).
- The connector (`mcp_server/btctx_mcp/client.py`) logs in with
  `BTCTX_USERNAME`/`BTCTX_PASSWORD` when both are set (session cookie via
  `/api/login`), otherwise reads the Mac key file.
- StartOS's **Connect an AI Assistant** action (`startos/startos/actions/connectAi.ts`)
  reads the generated password from `store.json` and puts it into the
  ready-made Claude Desktop config and `claude mcp add` command.
- The connector is installed from GitHub at a pinned tag
  (`git+https://github.com/DigiMonk73/BTCTX-MCP.git@vX.Y.Z#subdirectory=mcp_server`);
  its package version is still `0.1.0` (`mcp_server/pyproject.toml`).
- `/api/health` returns `{"status", "version", "schema"}` without login.

---

## 4. Part A: the AI key, step by step

### 4.1 Backend: `backend/services/ai_key.py` (rename of `mcp_key.py`)

Rename the module (update imports, `desktop/BitcoinTX.spec` hiddenimports, the
CLAUDE.md key-files table and security rules). Keep the stored setting names
(`mcp_key_sha256`, `mcp_access` in `app_settings`) so existing Mac installs
keep their key and switch.

- **Key format:** `btctx_ak_` + `secrets.token_urlsafe(32)` (32 random bytes,
  43 characters). The Mac file's existing key (no prefix) stays valid until
  reset; new Mac keys get the prefix too.
- **Storage:** only the SHA-256 hex digest, as now. Compare the digests with
  `hmac.compare_digest`.
- **Modes:** `mode()` returns `"mac"` when `BTCTX_MCP_FILE` and
  `BTCTX_DESKTOP` are set (as `enabled()` does now), else `"server"`.
- **Mac:** `sync()` and `rotate()` as today (file written owner-only; key
  accepted only from 127.0.0.1/::1).
- **Server:** `create_key(db) -> str` makes a new key, stores its hash
  (replacing any old one, so the old key stops working), and returns the key
  (shown once, never stored). `revoke(db)` deletes the hash. No
  localhost rule.
- **Switch:** `access_on(db)` unchanged (`== "on"`). Refusal message becomes
  "AI access is turned off in BitcoinTX Settings." (brief wording) for both
  modes.
- **Allow-list check:** `key_may_use(method, route_path) -> bool` against
  `AI_KEY_ROUTES` (section 1.4). `route_path` is the matched route's template
  (`request.scope["route"].path`), so `/api/transactions/{transaction_id}`
  matches every id.
- **Never log the key.** Refusals log the reason and client address only.
- **Backup (Option A):** `ai_backup(db_path) -> Path` using the same safe
  SQLite copy as `migrate.backup_sqlite` (label `ai`), then prune AI copies to
  3. Change `migrate.prune_backups` to prune per label, so AI copies and
  pre-upgrade copies never evict each other. One per minute (compare with the
  newest AI copy's time; answer 429 with "A backup was made less than a
  minute ago." otherwise).

### 4.2 Backend: `backend/main.py`

- Delete `API_KEY` and the `X-API-Key` branch of `get_current_user`.
- `get_current_user`: session first (unchanged). Then a key
  (`Authorization: Bearer …`): if valid **and** `key_may_use(request.method,
  route)`, return `"ai_key"`; valid but not allowed → 403 "The AI key can't do
  this. Log in to BitcoinTX to do it."; invalid, revoked or AI off → 401 with
  the reason.
- `/api/login` is unaffected (password only); add a test that a key-only
  request to it creates no session.

### 4.3 Backend: routes

- `routers/settings.py`:
  - `GET /api/settings/ai-access` → `{"mode": "mac"|"server", "on": bool,
    "has_key": bool, "key_file": str|null}` (login or key? **login only**;
    the frontend is the only user).
  - `PUT /api/settings/ai-access` (on/off): every edition, login only.
  - `POST /api/settings/ai-key` (create or replace): server mode, login only,
    returns `{"key": "btctx_ak_…"}` once.
  - `DELETE /api/settings/ai-key` (revoke): server mode, login only.
  - `POST /api/settings/ai-access/reset-key`: Mac only, as today.
- `routers/backup.py`: `POST /api/backup/ai-copy`, allowed for a session or the
  key; returns `{"file": "btctx-ai-…db", "created": "…"}`. The existing
  `/download`, `/restore` and `/csv` stay session-only.
- Remove the `api_key_user` special cases wherever they exist.

### 4.4 Frontend: Settings → Connect an AI Assistant

`frontend/src/components/ConnectAiSetting.tsx`, `utils/aiSetup.ts`:

- The switch **Let AI assistants use BitcoinTX** on every edition, with the
  existing line under it (reworded, no Mac-only claim).
- Server mode:
  - No key: **Create AI key**.
  - Key exists: **New key** (replaces; confirm "Your AI app stops working
    until you paste the new key") and **Revoke** (confirm).
  - After create/new: a panel showing the key once, with **Copy** and "This
    is the only time BitcoinTX shows this key. Paste it into your AI app's
    settings now." It disappears when you leave the page.
- The setup prompt and hand configs use `BTCTX_AI_KEY` with a placeholder
  `YOUR_BITCOINTX_AI_KEY` (the key is never put in the prompt, since the
  prompt goes into the AI chat). Order: **config file first** (Claude Desktop
  / LM Studio JSON), then the `claude mcp add` / `grok mcp add` command with
  a note that commands land in shell history.
- Mac mode: as today, minus the Mac-only wording.
- e2e (`frontend/e2e/settings.e2e.ts`): create, copy, new key replaces
  (old one 401), revoke (401), switch off (401 with the message), key shown
  only once (reload shows no key).

### 4.5 Connector: `mcp_server/btctx_mcp/`

- `client.py`:
  - Read only `BTCTX_URL`, `BTCTX_AI_KEY`, `BTCTX_VERIFY_TLS`,
    `BTCTX_CA_BUNDLE` (and `BTCTX_MCP_FILE` on the Mac).
  - Send `Authorization: Bearer <key>` on every request; drop `/api/login`
    and the session cookie.
  - No `BTCTX_AI_KEY`: fall back to the Mac key file (as today).
  - `BTCTX_USERNAME`/`BTCTX_PASSWORD` set: section 1.7.
  - Never print or log the key; errors quote status and BitcoinTX's message
    only.
- `server.py`: new tool `backup_ledger` (Option A; annotations: not
  read-only, not destructive, idempotent false); every tool's reply can carry
  a leading notice line (password notice, version notice, section 5.3).
- `guide.py`: mention `backup_ledger` ("offer a backup before a large
  import or before deleting") and that a 403 means "the user must do this in
  BitcoinTX itself".
- Unknown 403 → "BitcoinTX refused: the AI key can't do this. Ask the user to
  do it in BitcoinTX."

### 4.6 StartOS package (`startos/` only)

- `actions/connectAi.ts`: stop reading `store.json`. Show:
  - the MCP address(es) and the root CA certificate (as now);
  - "Create an AI key in BitcoinTX: open the Web UI → Settings → Connect an AI
    Assistant → Create AI key. BitcoinTX shows it once.";
  - the Claude Desktop / LM Studio JSON **first**, with
    `"BTCTX_AI_KEY": "<paste the key you created in BitcoinTX Settings>"`
    and the `uvx --from "git+…@main#subdirectory=mcp_server" btctx-mcp`
    line (5.2);
  - then the `claude mcp add` command with the same placeholder, marked
    "puts the key in your shell history; prefer the file above".
  - Drop the Username and Password fields from this action (Show
    Credentials still shows them for logging in to the web UI).
- `i18n/dictionaries/default.ts`: replace the changed strings, keep ids where
  the meaning is the same, add ids for new strings. Action strings stay
  English (the app is English-only); the listing's translated long
  description is updated in all five languages (section 6, item C4).
- `instructions.md` and `README.md`: AI section rewritten (key, switch, config
  file first, rotation note). No versions named.
- `versions/current.ts`: `1.0.3:0` with release notes in all five languages
  (what changed, and the rotation steps).

### 4.7 Rotation note (CHANGELOG under v1.0.3, README, StartOS instructions and release notes)

> **If you use an AI assistant with BitcoinTX on Docker or StartOS:** your
> AI app's settings file held your BitcoinTX password in plain text. After
> upgrading: (1) in BitcoinTX, Settings → Connect an AI Assistant, turn on AI
> access and create an AI key; (2) in your AI app's settings, replace
> `BTCTX_PASSWORD` (and `BTCTX_USERNAME`) with `BTCTX_AI_KEY` set to that key,
> and delete the password; (3) change your BitcoinTX password (Settings →
> Reset Username & Password), or on StartOS run **Reset Login Credentials**,
> because the old one sat in that file. Mac app users: nothing to do.

---

## 5. Part B: connector auto-update from `main`, version check

### 5.1 Connector version

Connector version = app version: `mcp_server/pyproject.toml` `version`
becomes the `VERSION` value (1.0.3), and `backend/tests/test_versions_agree.py`
checks it with the others. Release step 1 in `startos/UPDATING.md` and
`CLAUDE.md` gains "and `mcp_server/pyproject.toml`". No release job changes:
the connector is published by fast-forwarding `main` (1.9).

### 5.2 Recommended setup line everywhere

`uvx --from "git+https://github.com/DigiMonk73/BTCTX-MCP.git@main#subdirectory=mcp_server" btctx-mcp`
with env `BTCTX_URL` and `BTCTX_AI_KEY` (Mac: no env). uvx checks `main` each
time the AI app starts it (1.9), so users never edit a version. Keep
`git+https://github.com/DigiMonk73/BTCTX-MCP.git@vX.Y.Z#subdirectory=mcp_server`
only under "Pin a version". Update: `README.md`, `mcp_server/README.md`,
`mcp_server/AI_SETUP.md`, `frontend/src/utils/aiSetup.ts` (+ its Vitest),
the StartOS action and i18n, `startos/instructions.md`,
`startos/README.md`, the site (`btctx-site` AI section, optional).

The setup prompt in Settings still links to `AI_SETUP.md` at the app's
version tag (the guide must match the app), but installs from `@main`.

### 5.3 Version-mismatch warning

- The connector knows its version (`importlib.metadata.version("btctx-mcp")`).
- At startup it reads `/api/health`; if BitcoinTX didn't answer, it tries
  again on the first tool call.
- If the versions differ, every tool reply (including `get_ledger_guide`)
  starts with: "Your BitcoinTX connector is vA but the app is vB. Restart your
  AI app to update the connector (or change the pinned version)." Warn only;
  the tool still runs.
- Tests: same version → no line; different → the line on a normal tool and
  on `get_ledger_guide`; BitcoinTX down at start, up later → checked on first
  call.

---

## 6. Part C: doc fixes (from the review of 44e8b54)

Line numbers are as of `9f5d071`; search for the quoted text.

- **C1** `mcp_server/README.md` ~73: "**Local model:** nothing leaves your
  computer." → "**Local model:** what the AI reads stays on your machine.
  BitcoinTX itself still contacts price services unless Live data is off
  (Settings → Privacy & Network)."
- **C2** `README.md` ~38–39 ("lookups don't reveal your transaction dates")
  and `docs/CHANGELOG.md` v0.9.2 entry (~127: "requests no longer name single
  transaction dates" in the P1 wording). Verified in
  `backend/services/price_history.py`: a missing day triggers one bulk
  download starting 500 days before it (about 1,000 days), and if that fails,
  a **single-day lookup** (CoinGecko, Kraken, CoinDesk) that does name the
  date. README → "Past-day prices are stored locally and stored days work
  offline. A missing day is filled by one download of about 1,000 days, so
  most lookups don't reach an outside service at all; if that download
  fails, BitcoinTX asks for the single day. Turn Live data off to send
  none." Don't edit the old CHANGELOG entry; add a **Correction** bullet under
  v1.0.3 that says what v0.9.2 overstated.
- **C3** `mcp_server/README.md` security notes (~199): replace the key-use
  list with section 1.4's allowed and refused lists, in plain words.
- **C4** `startos/startos/manifest/i18n.ts` long description: "your ledger
  stays on your server" → "BitcoinTX sends your ledger nowhere; a local model
  keeps AI entry on your own hardware (a cloud AI sends what it reads to its
  provider)." Same change in es_ES, de_DE, pl_PL, fr_FR.
- **C5** `mcp_server/README.md` ~17: after "The MCP server itself sends
  nothing anywhere else", add: "BitcoinTX looks up prices from outside
  services when a preview fills in a value, unless Live data is off."
- **C6** `README.md` tech table (~180) and `startos/README.md` Network Access
  (~86): name the single-day fallback (CoinGecko, Kraken, CoinDesk) for a
  missing past day, and the block-height sources (Blockchain.info,
  Blockstream, mempool.space).
- **C7** `docs/startos-research/btctx-requirements.md`: outdated (describes
  v0.8.0: "No health endpoint today", `API_KEY`…). Move it to `docs/archive/`
  with a one-line "Archived: describes v0.8.0" note.
- **C8** Remove every line saying key auth or the AI switch is Mac-only, or
  that Docker/StartOS use a password for AI. Known places: `README.md`
  (~103–113, ~132–137), `mcp_server/README.md` (~10–13, ~51, ~79–82, the
  Configure section, the Claude Desktop/Code examples), `mcp_server/AI_SETUP.md`
  (whole "server install" path: section 2B and 3), `startos/instructions.md`
  (~33, ~45), `startos/README.md` (~93, ~115), `docs/MACOS_DESKTOP_APP.md`,
  `desktop/README.md`, `CLAUDE.md` security rules, the frontend strings in
  `ConnectAiSetting.tsx`, and the site's AI section. Search for
  "password", "Mac only", "Mac app only", "BTCTX_PASSWORD", "logs in with".

---

## 7. Wording rules (all docs and UI)

- Never say "your data stays on this computer" or "nothing is sent
  anywhere". Say: BitcoinTX sends your ledger nowhere; what the AI reads goes
  to wherever its model runs; the app contacts price services unless Live
  data is off.
- Say plainly what a stolen key can do: **read the ledger, add or change
  entries, and make a backup; it cannot log in, change the password,
  restore, or delete everything, and you can revoke it in Settings.**
- Sentence case, plain verbs, no "Mac only" for the key or the switch.

---

## 8. Tests (each fails on the old code)

Backend (`backend/tests/test_ai_key.py`, new; plus edits):
- Server mode: create → key works on an allowed route; key starts with
  `btctx_ak_` and is ≥ 50 characters; only its SHA-256 is in `app_settings`.
- New key → old key 401; revoke → 401; AI off → 401 with "AI access is
  turned off in BitcoinTX Settings."; default on a fresh install is off with
  no key.
- One 403 test per refused category (section 1.4): login/session, user
  change, key create/revoke, AI on/off, restore, `.btx` download, CSV export,
  CSV import, River import, delete-all, account change, Ledger Review fix,
  tax timezone change, network settings change, debug.
- Backup works with the key: `POST /api/backup/ai-copy` makes a file in
  `backups/`, mode 600; a fourth AI copy prunes the oldest AI copy but no
  pre-upgrade copy; a second call within a minute → 429.
- `API_KEY` is gone: an `X-API-Key` header grants nothing.
- Mac mode unchanged: file key works from 127.0.0.1, refused from another
  address.
- `test_versions_agree.py`: `mcp_server/pyproject.toml` version = `VERSION`.

Connector (`mcp_server/tests/`):
- Password only → every tool returns the migration line and makes no
  request with the password (assert no `/api/login` call).
- Key + password → the same migration line, no request made (1.7).
- Key sent as Bearer; key never appears in logs or error text.
- Version match/mismatch (section 5.3); `backup_ledger` returns the file name.

Frontend: Vitest for `aiSetup.ts` (`@main` git line, `BTCTX_AI_KEY` placeholder,
config file first); e2e as in 4.4.

StartOS: `npm run check`, lint, build, `check-manifest`; a check (grep test in
`backend/tests/pre_commit_tests.py` or a small script) that `connectAi.ts`
doesn't reference `storeJson` or `adminPassword`.

---

## 9. Verification before release

1. `make check` green (lint, full tests, smoke, audit), plus `make e2e`.
2. StartOS checks (`cd startos && npm ci && npx prettier --check startos &&
   npm run check && npm run lint && npm run build && node scripts/check-manifest.mjs`).
3. **Manual Docker run** (record the commands and outputs in the session):
   ```bash
   docker build -t btctx:test .
   docker run -d --name btctx-t -p 8099:80 -v btctx-t:/data btctx:test
   # log in, claim the account, turn AI access on, create a key (via the API
   # with a session cookie, or the UI)
   ```
   - (a) connector with `BTCTX_PASSWORD` set → the migration line;
   - (b) connector with the created key → `get_portfolio`, `add_transactions`
     and `backup_ledger` work; the backup file is in the volume's `backups/`;
   - (c) revoke the key → 401; new key, AI off → 401 with the message;
   - (d) with a valid key: `POST /api/backup/restore`, `DELETE
     /api/transactions/delete_all`, `PUT /api/settings/network`,
     `POST /api/import/river/…` → 403.
   Then `docker rm -f btctx-t && docker volume rm btctx-t`.
4. Mac app: build (`./desktop/build-mac.sh`) and check the key file still
   works (CI's macOS job covers launch).

---

## 10. Release steps and what to report

1. On `develop`: bump `VERSION` (1.0.3), `desktop/BitcoinTX.spec`, the StartOS manifest
   image tag, `startos/startos/versions/current.ts` (`1.0.3:0`),
   `mcp_server/pyproject.toml`; move the CHANGELOG's Unreleased section to
   `## [v1.0.3] - <date> - Security: AI keys for every edition`.
2. Delete this file in the same commit.
3. Push `develop` and wait for CI; then fast-forward `main` to `develop`,
   push, and wait for the image build. From here the connector installs
   v1.0.3 for everyone (1.9).
4. Push `release/v1.0.3` from `main`. Confirm: the GitHub release (dmg, zip,
   s9pk), the GHCR image `:v1.0.3`, the BTCTX-StartOS sync and its Latest
   release, and that a fresh `uvx --from "git+…@main…" btctx-mcp` reports
   connector 1.0.3.
5. Delete the `release/v1.0.3` branch (keep only `main` and `develop`).
6. Report: commit ids, the `API_KEY` decision (section 1.2), the backup
   option used, anything unfinished.
7. Optional follow-ups: update the landing page (`~/code/btctx-site`) AI
   section for keys and the `@main` install line; update the Start9 submission
   if it's already been sent.
