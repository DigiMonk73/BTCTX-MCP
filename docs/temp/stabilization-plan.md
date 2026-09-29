# Stabilization after 1.2.1: test everything, fix bugs, no new features

The owner's goal (2026-09-28): a **stable version with no new features for
a while**. Only bug fixes (and the one small UI change the owner will
describe), each with a test that fails on the old code, on `develop`.
Releases (1.2.2, …) only when the owner says so. Delete this file when the
work is done; lasting results go to the CHANGELOG, docs or the code.

## Working with the owner

- Not a software engineer: plain language, short answers, one decision at a
  time with a recommendation (AskUserQuestion works well).
- Only the owner types passwords (StartOS, BitcoinTX logins, `start-cli auth
  login`). Never enter them; run Show Credentials with its output discarded.
- Verify before acting on any outside bug report (Grok Bot's reviews were
  partly wrong). Report honestly: real / already fixed / not a bug.
- Merging PRs needs the owner's go-ahead in chat (auto mode blocks it
  otherwise).

## Where things stand

- **v1.2.1** released 2026-09-28 (GitHub release, `ghcr.io/digimonk73/btctx-mcp:v1.2.1`,
  PyPI `btctx-mcp==1.2.1`, StartOS mirror `v1.2.1_0`). `develop` = 1.2.1 plus
  react-hook-form 7.89 (Dependabot #21).
- The owner hasn't done the box test yet (`startos-box-test-v1.2.1.md`,
  mainly My Mempool, which the VM can't test).
- Dependabot opens weekly PRs against `develop` (`docs/MAINTENANCE.md`).

## Tools

- Repo tests: `make check`, `make test` (incl. slow), `make e2e`
  (`E2E_WEBKIT=1` adds WebKit, what the Mac app renders with),
  `make docker-smoke`, `make preview` (`docs/TESTING.md`).
- **StartOS VM lab, outside the repo:** `~/code/btctx-vm-lab` (read its
  README; `./vm.sh start|stop|install|action|url|logs|cli|reset --yes`).
  Scenarios with expected results in `scenarios/`. Hard-won details:
  `start-cli` needs `--root-ca`; actions with input need the `eventId` from
  `get-input` (vm.sh does it); `package attach` runs commands in the app's
  container but doesn't forward stdin's end (pass a script base64 in the
  command); package commands answer ~20 s after boot.
- Release candidates for the VM (ARM): CI's s9pk is x86_64 only. Build the
  arm64 image on the Mac with a blank `DOCKER_CONFIG` (the keychain
  credential helper hangs in agent shells; see `scripts/docker_smoke.sh`),
  then `make arm` in `startos/` with a throwaway key in `~/code/.startos/`
  (delete it after). StartOS accepts it as an update over DEV_KEY installs.
- The full release walk on the VM: `docs/AGENT-TESTS.md` (golden ledger with
  hand-worked figures, Tracks A, B, C).

## Plan

1. **Baseline:** `make check`, `make test`, `make e2e` (with WebKit if it
   runs), `make docker-smoke`, CI green. Note anything flaky and find out
   why (one flaky test was a real race in the converter).
2. **VM:** `docs/AGENT-TESTS.md` Track A on a fresh install (reset from
   "StartOS clean") and Track B (update from 1.1.0 and 1.2.0); Track C (the
   Mac app) if feasible. Record results in the lab's `scenarios/`.
3. **Bug hunt** where bugs hid before: tax-year and timezone boundaries,
   BTC fees on transfers and withdrawals, imports (River, CSV, the MCP entry
   import), restore, recalculation after edits and deletes, the MCP tools
   through a real MCP client with an AI key, two tabs at once, Safari 15
   CSS (the Mac app's WebKit).
4. **Privacy and leak audit.** Be honest, including leaks that are only
   documented rather than prevented. Check every way data or metadata leaves
   the machine:
   - outbound requests (`services/outbound.py` and every caller): what each
     reveals (IP, timing, which sites), that no request names a date, that
     Tor fails closed, DNS through the proxy (socks5h), the sidebar's
     2-minute live-price polling, the daily "latest days" downloads;
   - the browser: CSP, no third-party fonts or scripts (`privacy.e2e.ts`),
     referrer, cookies;
   - at rest: logs (no transaction dates or amounts), backups (encrypted),
     CSV and PDF exports, the database file's permissions, the session key;
   - the AI path: what the MCP connector sends to the AI provider (documented
     in the app), `uvx` fetching from PyPI;
   - StartOS and Docker: interfaces exposed, what a StartOS backup contains.
   Write the findings to `docs/temp/privacy-audit.md` (leak / no leak /
   documented only / fix proposed), then go through them with the owner one
   at a time.
5. **Fixes:** each with a failing-then-passing test, CHANGELOG under
   Unreleased, pushed to `develop`. No release until the owner says.
