# Grok's review pass

The finder's manual for BitcoinTX. A fresh Cursor chat, or a fresh Grok
Build session, can run one pass from this file alone. The rules it points
at live in `AGENTS.md` ("Who does what," "Reviews," "Bugs and security,"
"Tax invariants," "Releasing"). It restates no rule in full: each area
names what to check against them.

`docs/HARDENING_FINDINGS.md` is a record of past findings, not this
routine. `docs/PRIVACY_AUDIT.md`'s 1.2.8 table is the checklist for area 3.

## Who does what

- **Claude** writes tax figures, login and security, the database, the
  StartOS package, and releases. Claude checks every finder report in the
  code before it counts, then fixes it. Claude's fresh pull-request review
  stays as `AGENTS.md` describes it.
- **Cursor's Grok, at its highest setting,** is the finder: a second set
  of eyes when the owner asks. Read-only unless the owner names one job
  (see "A small fix"). A finding is a claim until Claude checks it.
  Comments end `— Grok (Cursor)`.
- **Grok Build** is the spare workshop when Claude is out of tokens, for a
  job the owner already chose. It may write docs, tests, and small fixes
  outside the money path, the doors (login and security), the database,
  and StartOS: not in the files of monthly areas 1–4 below, nor
  `backend/migrations/`. A one-line change there is still Claude's.
  Grok never merges. Every change it writes gets a fresh Claude
  review, and Claude or the owner's "merge" lands it. It does not review
  its own change. Comments end `— Grok (Build)`. It does not cut a
  release, move `main`, or send anything to Start9. A Grok Build session
  connected to the owner's BitcoinTX (the AI connector) is the owner's own
  use: never a review or a fix there.
- The finder pass is the high-value use. A Grok-written app change still
  needs a full Claude review, so it saves less than docs, tests, and
  simple fixes.
- After each pass, Claude records it as a comment on issue #41: the area
  or release, the date, how many findings were confirmed and how many
  were not, and the next area. The Monday report repeats the latest. No
  separate scorecard file.

Do not name model versions or speed tiers in this file. They go stale.

## Before you start

`git fetch`, and read `origin/develop`, not a stale checkout. Temp
databases, `make preview`, or the StartOS test VM only. Never the owner's
real Mac ledger, and never the installed app's data. On this machine the
Python to trust is the repo's `.venv`.

Never paste real ledger figures, keys, passwords, server addresses, or the
contents of a private advisory into any AI chat, beyond what the public
code already shows. The repository is public.

No commits unless the owner named one job that this role is allowed to
write. No release, no move of `main`, nothing sent to Start9.

## Release pass

When the owner asks, before a release (a second set of eyes, not a
release gate), read what changed since the last release tag
(`git log --oneline $(git describe --tags --abbrev=0 origin/main)..origin/develop`;
tags look like `v1.2.8`). App
code, the database, prices, auth, backup, the connector, and `startos/`.
Skip a file that only moved words, except the StartOS release notes and
the instructions a user follows.

For each change, ask:

- Does it do what the pull request says?
- What happens when a step fails halfway?
- What can a logged-out, copied, or stale cookie still do?

Report what you did not read.

## Monthly pass

One area, then the next, then start over. Not the whole repo. The owner
names the area (the latest pass on #41 says which is next); if not, ask.

1. **Money.** `backend/services/transaction.py`,
   `backend/services/tax_time.py`,
   `backend/services/reports/form_8949.py`,
   `backend/services/reports/reporting_core.py`, and the reference ledger
   (`testdata/reference_ledger.json`, `scripts/independent_figures.py`).
   Check the tax invariants in `AGENTS.md`. A recalculation must be
   rebuildable from the Transaction row. Dates use the tax timezone.
   Nothing prices at $0.
2. **Doors.** `backend/session_auth.py`,
   `backend/services/login_throttle.py`,
   `backend/services/first_run.py`, `backend/services/backup.py`,
   `backend/services/ai_key.py`, `backend/body_limit.py`,
   `backend/security_headers.py`, and `get_current_user` in
   `backend/main.py`. Login, logout, a copied cookie, a password change,
   restore, the Mac AI key file, and request size. The Mac app answers
   only at `127.0.0.1`, `localhost`, or `[::1]`. The AI key is a bearer
   token on `AI_KEY_ROUTES` only.
3. **Prices and what leaves the machine.**
   `backend/services/hourly_prices.py`,
   `backend/services/price_history.py`, `backend/services/price_files.py`,
   `backend/services/outbound.py`, `backend/services/mempool_trust.py`.
   No request names a day or an hour. Nothing is asked until a price
   source is chosen. A stored day or hour never changes. A sub-cent or
   non-numeric price is not stored. Every outside request is in
   `docs/PRIVACY_AUDIT.md`'s 1.2.8 table.
4. **StartOS.** `startos/`, including `instructions.md` and the release
   notes in `startos/startos/versions/current.ts`. Check them against
   Start9's published guide (`start-technologies` on `live-docs`, or
   <https://docs.start9.com/packaging>). The guide wins for the package.
   Do not describe the service as on Tor or the public internet. The user
   chooses where an interface is reachable.
5. **Imports and the connector.** `backend/services/csv_import.py`,
   `backend/services/river_import.py`, `backend/services/entry_import.py`,
   `mcp_server/btctx_mcp/server.py`, `mcp_server/btctx_mcp/guide.py`,
   `AI_KEY_ROUTES`, and the CSV BitcoinTX writes
   (`backend/services/reports/safe_text.py`, `csv_text`). A CSV cell
   BitcoinTX writes never starts a formula. One transaction per row. The
   connector's tools and the routes the AI key may call have to match. The
   AI key's first edit, delete or recalculation in an hour is preceded by a
   copy (`_copy_before_ai_changes`, `backend/routers/transaction.py`), and
   so is an import holding a row dated before the ledger's latest, which
   recalculates it (#414); any other import makes none (the connector
   offers `backup_ledger`).

## How to report

In the chat, in plain words: what is wrong, which file, who it hits, how
serious, and what you did not check. The owner pastes it to Claude.

A confirmed bug becomes a public issue. A security problem is told to the
owner in the chat only. Claude files a private draft advisory. Do not open
a public issue or a pull-request comment for an unfixed security problem.

## A small fix

Only when the owner names that job, and only outside the money path, the
doors, the database, and StartOS. One function and a test that fails on
the old code. Its own pull request into `develop`, then stop. Grok never
merges. The session that wrote the change does not approve it.

## Do not

- Scan all five areas in one session.
- Review a change you just wrote.
- Test on the real ledger.
- Put this checklist into `AGENTS.md`.
- Invent a price, a form rule, or a StartOS behavior you did not read.

The kind of miss this pass is for: a step that saves a new secret before
the file that holds it is written, so a failed write leaves the app
running with a secret the client no longer has; and a size check that
trusts a signed cookie without asking whether that session is still open.
