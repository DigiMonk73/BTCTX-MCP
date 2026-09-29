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
- The owner hasn't done the box test yet (`startos-box-test-v1.2.2.md`,
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

## Progress (2026-09-29)

- [x] 1. Baseline: all green (693 pytest, 45 vitest, smoke, audit, Docker,
      e2e Chromium 127 + WebKit 90, CI 11/11). No flaky tests; the two red
      CI runs of 2026-09-28 were a reworded message, fixed the next commit.
- [~] 2. VM, on the published 1.2.1: Track A all PASS except the steps that
      need a password typed (owner: `~/code/btctx-vm-lab/owner-checks.sh`),
      BAK-5 BLOCKED (no second disk), PRC-4 partial (no Mempool). Track B
      1.2.0 → 1.2.1 and 1.1.0 → 1.2.1 PASS (data identical). Track C
      skipped (the Mac's app holds the owner's real ledger). Report:
      `~/code/btctx-vm-lab/scenarios/agent-test-1.2.1-published.md`.
- [x] 3. Bug hunt: VM findings fixed (8858dd5); two hunt agents found ~20
      real bugs, all fixed on `develop` with tests, M2 by the owner's
      decision (a same-amount Buy at another price: saved, flagged).
      The slow property test's rare "stuck" failure was the test's own
      shuffled entry (fixed in the test). Full suite 747, e2e 219 green.
- [x] 4. Privacy audit: `privacy-audit.md`. Plain bug fixes done
      (348616a); the owner decided the rest on 2026-09-29 (restore keeps
      price settings, Docker on 127.0.0.1 + connector http warning, backup
      password typed twice, Kraken first + block height cached, all sites
      named + timing, secure delete, copies noted, no server header, /data
      700, PyPI note). Left as documented: clearnet mempool bypasses Tor
      (1i), httpx URLs in the log (3a), StartOS backup contents (3h), the AI
      provider sees the ledger (4a/4b), `/api/health` shows the version (5c).
- [x] The owner's one UI change: the calculator ends level with the Realized
      Gains/Losses card; the converter's modes are one height.
- [x] 1.2.2 released 2026-09-29 (the owner's go-ahead): RC d478bc3 passed CI
      11/11 and the VM checks (updates from 1.2.1 and 1.1.0, fresh install).
- [ ] Left: the owner's password checks on the VM
      (`~/code/btctx-vm-lab/owner-checks.sh`, against the installed 1.2.1),
      then a 1.2.2 release candidate through `docs/AGENT-TESTS.md` when the
      owner decides to release.

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
