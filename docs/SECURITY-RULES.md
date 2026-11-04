# Security rules

What protects the owner's data, login and ledger. Read them before
changing a router, login or sessions, the AI key or the connector,
backups and restores, imports and uploads, error handling, the
reports' text, or anything that reaches the network.

Moved word for word from `AGENTS.md` on 2026-11-04 (#903); `AGENTS.md`
now keeps a map of where each part lives. Where the text below says
"this file", it means `AGENTS.md` and the files its map names, and a
section named in quotes ("Branches", "Reviews") is found through that
map.

## Security rules

- All API routers require login (or the AI key, below) except
  `POST /api/users/register`, `GET /api/users/setup-status`,
  `POST /api/users/reset-account`, `GET /api/health` (status, version,
  schema only) and login. User routes may only touch the logged-in user.
- `SECRET_KEY` values in `secret_key.PUBLIC_DEFAULTS` are ignored, and so is
  one shorter than 32 characters (the key file is used). Never add a default
  key anywhere.
- The debug router, `DELETE /api/transactions/delete_all`,
  `PUT /api/settings/tax-timezone` and `POST /api/settings/tax-timezone/fill`
  are login-only (never the AI key); tests
  use the first two, the MCP server must not expose bulk delete. API docs
  (`/docs`, `/openapi.json`) only with DEBUG.
- Deleting every transaction (Delete All, and Create account's
  `reset-account` on a ledger with transactions) needs `confirm=DELETE`,
  typed in its dialog, else 409 says what would go; the dialog sends what
  it showed (`transactions`, `first_year`, `last_year`), and a ledger that
  no longer has it is a 409 with the new figure (#377; a swap within the
  same count and years isn't seen, the copy keeps it). reset-account
  checks the setup code or password first. A copy of the database goes to
  `backups/` before it (`btctx-before-delete-all-…`, newest 5, apart from
  the other copies; no copy, nothing deleted): `services/wipe.py`, #256.
  reset-account's delete and its new login are one save (`wipe.delete_all`'s
  `save_with`): a failure leaves both as they were.
- Sessions (`backend/session_auth.py`): each login gets a random session id,
  carried in the cookie; the server keeps the hashes of the open ones in
  `app_settings` (the newest 20). A session not on that list is logged out
  (401), so logout ends that cookie and every copy of it while other
  browsers stay logged in. Sessions also carry a stamp of the password hash:
  changing the password (Settings or `cli set-password`) or resetting the
  account empties the list and ends every other session. A restore keeps
  the other browsers' sessions open when it replaces the database (only
  while the restored account has the same id), never the backup's list;
  the restoring browser logs in again. A route that reads
  `request.session` itself relies on its router's `get_current_user`
  having cleared an ended session first; outside such a router, use
  `require_login`.
- Login, reset-account and password changes are throttled
  (`services/login_throttle.py`, per client and global; 429 + Retry-After).
  A try counts as a failure from when it arrives (`check()`) until it's
  right (`succeeded()`).
  A browser that got one of them right gets a device cookie (`btc_device`,
  a year, signed with the secret key, bound to the current password) and is a
  client of its own: other clients' failures, its address's count (behind
  a proxy, everyone's) and the global cap don't stop it; its own failures
  slow it. Logging out keeps it; a new password voids every earlier one.
  New passwords need 12+ characters; a change needs the current password.
  A login with a username that doesn't exist checks a stand-in hash all the
  same (`models/user.password_matches`), so its time says nothing about
  which names exist.
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
  `CORS_ALLOW_ORIGINS` is set. A logged-in change a browser sent without
  the page's `X-BitcoinTX-Page` (every request of `frontend/src/api.ts`
  names the build's VERSION), or from another major version, is a 409,
  "BitcoinTX was updated: reload the page." (`PageVersionMiddleware`, 2.0
  spec 5.13): a 1.x page left open over the upgrade would save a Buy or
  Sell into the first exchange. Scripts, the connector and the tests'
  clients send no browser header and pass. The Mac app answers only requests addressed
  to `127.0.0.1`, `localhost` or `[::1]` (421 otherwise;
  `security_headers.LocalAddressOnlyMiddleware`). No server of ours, the
  Mac app's, the Docker image's or StartOS's (which runs the image's
  command), takes a client's address from `X-Forwarded-For`
  (`desktop/entrypoint.py`; the Dockerfile's `--no-proxy-headers`).
- Report PDFs: every ledger string passes `reports/safe_text.py` (escaped for
  ReportLab, which may open no file and fetch nothing; a character its
  built-in fonts can't draw prints "?", by ReportLab's own rule, and an
  account's name keeps to Windows-1252, Western European letters, #722); CSV text cells can't start a
  formula, and the csv module writes every CSV, so a line break stays in its
  cell; a purpose or source kept as written is one line, and a fee currency
  is USD or BTC.
- Every answer under `/api/` says `Cache-Control: no-store`
  (`security_headers.py`): exports and the ledger's JSON stay out of the
  browser's disk cache. A new encrypted backup's password needs 12+
  characters (`routers/backup.py`); a restore takes an older, shorter one.
- An error nobody expected is said and logged without its own text (it can
  hold SQL with a transaction's date, or a server path): one fixed sentence
  in the answer, the error's type in the log at ERROR, its trace only at
  DEBUG (`backend/unexpected_errors.py`: `log_unexpected`). An error no
  route handled in a request answers `UNEXPECTED` (500) through
  `UnexpectedErrorMiddleware`, which doesn't raise it again, so the server
  logs no trace (#430; the tests fail on one unless marked
  `unexpected_error`). An id a request sends that can reach a query is a
  `database.RowId` (SQLite's 64-bit integers), or as tightly bound (Ledger
  Review's `ids`, a chosen coin's `acquired_txn_id`: `chosen_coins.LARGEST_ID`):
  one beyond is a 422 naming it, never bound into a query
  (an `OverflowError`'s 500, #744). A save a restore's swap refused
  answers `REPLACED` (503, `database.was_replaced`, Python 3.11+) and is logged as a
  warning, and so is one that waited past the 5 s for SQLite's write lock
  (`BUSY`, 503, `database.is_busy`, #478). A connection goes back to the
  pool with nothing left open (`database._end_what_a_failed_commit_left_open`):
  a COMMIT that failed busy is never saved by the next request on it
  (#580's re-check). Two kinds still show an error
  in full, to the owner only: a failure that stops BitcoinTX starting
  (`init_db`, a migration),
  whose text is then the only diagnosis, and a `backend/cli.py` command's
  error (StartOS's migrate oneshot; its Set Login Credentials and
  Recalculate Ledger actions show only the `error:` line, never the SQL
  values a database error carries below it, #465). The
  imports' `routers/csv_import.import_failure`
  (busy, 503, when the database was locked: `database.is_busy`; else
  `IMPORT_FAILED`), `reports.IRS_FORMS_FAILED`, `backup.RESTORE_FAILED`,
  the AI preview's dry run (`entry_import.SIMULATION_BUSY` or
  `SIMULATION_FAILED`) and Ledger Review's (`review.DRY_RUN_FAILED`) say
  their own. A refusal raised on purpose (an `HTTPException`, the backup's
  or the ledger's own words) keeps them. Never `logger.exception` or
  `exc_info=True` above DEBUG. Text that holds no ledger data may stay in
  a warning: a network error (httpx; no URL names a day), a server path,
  SQL without its parameters, words the code chose.
- The MCP server authenticates with the AI key (`backend/services/ai_key.py`,
  `Authorization: Bearer`), never a password; there is no other API key. Mac
  app: the key is in the owner-only `mcp.json`, a new one at every start (the
  connector reads the file again on a 401), and works only from localhost.
  Docker/StartOS: the owner creates, replaces or revokes it in Settings (shown
  once). Only its SHA-256 is stored; a restore keeps the current key and
  switch (and the login and price settings in use: an in-app restore never
  brings back a backup's password or its price source), and the exchange
  import's mappings in use beside the backup's (#656: a restore loses
  none, and hands no mapping id out twice). An in-app restore
  takes a backup's data, never its database: a backup holding anything but
  ordinary tables and indexes (no generated column, no index on an
  expression or with a WHERE) is refused, and the database that goes
  live is made by BitcoinTX's own migrations with only the rows of its
  own tables and columns copied in, one login, and these settings written
  and read back before it replaces the live one. The settings are read from the live
  database at the swap, under its write lock held until the new one is in
  place (`backup._swap`), so a change saved before is kept and a save that
  waits for the lock is refused in plain words (SQLite does so in its
  rollback-journal mode: `database.init_db` puts back in it a database an
  earlier restore left in write-ahead-log mode, a restore tries again, and
  stops while something else keeps it in that mode); any failure leaves
  the live database as it was and answers in plain words, never SQL
  (`services/backup.restore_backup`, `routers/backup._write_kept`).
  It works only while AI access is on (off by default) and only on
  `AI_KEY_ROUTES`, the routes the MCP tools call, compared with the template
  of the route the request matched (`main.route_template`), never its URL;
  any other route is 403. Every router is mounted with `main.include()`,
  which notes its routes' templates (a router mounted otherwise is closed
  to the key). A new MCP tool that needs a route adds it there on purpose
  (a test checks the tools and the list agree). The key may read the
  account list (`GET /api/accounts/`, the connector's names, 2.0's #350),
  never add, hide or delete an account. A write from a connector older
  than 2.0 (no `X-BitcoinTX-Connector` header) to a ledger with more than
  one wallet or more than one exchange, hidden ones counted, is refused,
  409 (`ai_key.from_an_old_connector`, #354): its guide put a second
  wallet's coins in Wallet. Its reads go on. Never allow the
  key on login, users, key or switch settings, backup download/restore, CSV
  export, file imports (CSV, River, any exchange's), delete-all, Ledger Review fixes,
  settings changes (the Mempool certificate's trust, #188, included) or
  debug.
- Before the AI key's first change in an hour (an edit, a deletion,
  Recalculate Ledger, or an import holding a row dated before the ledger's
  latest, which recalculates it: each can move stored figures, #336, #414)
  an AI copy is made (`backups/…-ai-before-changing-…db`; no copy, no
  change), never for the owner's; it is written under a temporary name and
  renamed once complete, one at a time, so a failed or unfinished copy never
  counts as the hour's. Of the AI copies BitcoinTX keeps the newest 3 and,
  for a week (today and the 6 UTC days before), the oldest and the first
  copy of each day made before the AI changed anything that day
  (`migrate._ai_copies_held`): at most 11. A confirmed past-year write
  with the key makes a fresh one first, whatever the hour (2.0, #352).
- The JSON entry import (`routers/entry_import.py`) holds SQLite's write
  lock while it works, and the owner's saves wait only 5 s for it. An add's
  duplicate check and its writes hold it as one (`entry_import.write_rows`;
  River's and the CSV import's check too, `csv_import.execute_import`'s
  `check`), so the same rows sent twice at once are saved once (#454);
  their prices are found first, with the lock free. With the key a
  request takes at most `AI_MAX_ROWS` (500) rows, and its rows dated before
  the ledger's latest entry, each replaying the whole ledger, at most
  `AI_MAX_REPLAYED` (1,000) entries in all (one such row always), about 1 s.
  The preview reads the price year files its rows may need before its dry
  run (`hourly_prices.read_year_files`), so finding which price filled each
  value (#208) reads no file under the lock.
- A JSON body whose text (or a key) holds a lone surrogate (`"\ud800"`)
  is refused, 422 naming the field, before the route runs
  (`main.refuse_text_that_isnt_text`, #313): it can't be saved or quoted
  back. Every logged-in router lists it after its login check
  (`main.LOGGED_IN`; a new router uses it too), so an anonymous request
  gets its 401 and never costs a walk. It checks only routes that take a
  JSON body, as FastAPI reads one. The login and `/api/users` routes
  have their own check (#210): a login or current password that isn't text
  is a wrong one; a new username or password, a 422. Form data is each
  route's own to check (a backup's password: `backup._require_text_password`).
- Every request body is limited before anything reads it
  (`backend/body_limit.py`, just inside the security headers, before the
  cross-site check, sessions and routers): FastAPI
  reads and parses a body before the login check, login and Create account
  included. Over 5 MB it's 413, at once from Content-Length or as soon as a
  chunked body passes it; once the answer has started (a file being sent
  reads the body to see the client leave, from Starlette 1.8), the rest is
  thrown away instead and the answer completes (`body_limit._Counted`).
  A route taking a file is listed in `main.py` with its own file limit
  (plus room for the form) and keeps checking the file itself: the CSV,
  River and other exchanges' files 5 MB, read at most to the limit and
  one byte; the
  restore 1 GiB, copied in 1 MiB pieces until past it. That larger
  allowance is for a logged-in owner's file: only a request whose
  session cookie is validly signed, unexpired, holds a `user_id` and names
  a session still open gets it. A new upload route goes in that list.
