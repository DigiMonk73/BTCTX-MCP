# AGENTS.md

Context for AI assistants working on this repo: Claude Code, and any other
agent that reads `AGENTS.md` (`CLAUDE.md` only points here). Keep it current
and short; history belongs in `docs/CHANGELOG.md`.

## What this is

BitcoinTX: a self-hosted, single-user Bitcoin portfolio and tax tracker
(double-entry ledger, per-wallet FIFO lots or the coins chosen in a
wallet, IRS Form 8949 / Schedule D), with an MCP server for optional
AI-assisted entry. Its parts, data model and key files:
`docs/ARCHITECTURE.md`.

## What's at stake

- BitcoinTX holds the owner's real tax records, and its figures go on IRS
  forms: a wrong number is a real-world problem. So a change to tax figures
  gets the full review, the re-check and every figures check, and moves a
  figure only on purpose, with a plain-words before-and-after the owner
  approves ("Reviews": the figures rule). The owner isn't asked to judge
  code: Claude is.
- The owner's real ledger is the installed Mac app's data. Never test on it,
  run a script against it or point the AI connector at it; use temp
  databases, `make preview` or the StartOS test VM, and run a Mac build
  only with `desktop/run-test-build.sh` (its own data folder and port).
- Other people install BitcoinTX from Start9's community registry: a
  release that breaks an update or loses data hurts users who trust it.
- Start9's reviewers and users care about privacy: no price is asked of
  anyone until the owner picks a price source, and no request names a day
  ("Prices" under Tax invariants).

## Before you change…

- **Tax figures, login, the database: read these first.** Before
  changing `backend/` (above all `backend/services/`, the reports,
  prices, IRS forms, `backend/migrations/`), `testdata/`, `scripts/`,
  `mcp_server/`, Docker or the frontend's API and forms, read
  `docs/TAX-INVARIANTS.md`, `docs/SECURITY-RULES.md` and
  `docs/ARCHITECTURE.md`'s "Data model"; then "Reviews" (the figures
  rule). A rule in `.claude/rules/` repeats this for those paths.
- **Any code**: follow `docs/CODE_STYLE.md` (one job per function, comments
  say why, the same idioms everywhere).
- **Any text**: say "multiple wallets, exchanges or accounts", never
  "several" (the owner, 2026-10-18; released history keeps its words;
  `test_disclaimer.py` checks it).
- **Database paths, file storage, env vars, Docker**: read `docs/STARTOS_COMPATIBILITY.md`.
  Everything persistent lives in the directory of `DATABASE_FILE`.
- **Models / schema**: write an Alembic migration (`docs/MAINTENANCE.md`,
  "Database migrations"). Never call `create_all()` in app code; the
  `test_models_and_migrations_agree` test fails if models and migrations differ.
  On `2.0`, 2.0's migrations take ids from 0100 and come after 1.x's.
  Until the first 2.0 pre-release (v2.0.0-alpha.1, 2026-10-24), each
  `develop` merge re-pointed the first one's `down_revision` to 1.x's
  head; since then their ids and parents are fixed, and a later 1.x
  migration comes into `2.0` by an Alembic merge revision, never by
  re-pointing (#251, decision 3). On `develop`, 1.x numbers its
  migrations on from its own head as always.
- **Dependencies**: read `docs/MAINTENANCE.md`. Pins live in the
  `requirements.in` files; after an edit, `make lock` recompiles the locks.
- **Desktop app**: read `docs/MACOS_DESKTOP_APP.md`. New backend modules need
  a `hiddenimports` entry in `desktop/BitcoinTX.spec`.
- **IRS forms**: read `docs/IRS_FORM_GENERATION.md`; for a new tax year follow
  `docs/IRS_ANNUAL_FORM_UPDATE.md` (`python scripts/irs_new_year.py YEAR`).
- **StartOS package** (`startos/`): it always keeps Start9's packaging rules
  (<https://docs.start9.com/packaging>: layout, README headings,
  `instructions.md`, no `TODO.md`), since Start9 reviews it against them. Read
  `startos/AGENTS.md`; `backend/tests/test_startos_conformance.py` checks what
  a script can. When Start9's guide changes, update the package and the test.
  What else Start9's rules cover: "Start9".

**Where the rest of this file went** (#903), word for word, for the
pointers that still name its sections (`AGENTS.md, "Prices"`):

| Section | Now in |
|---|---|
| "What this is" (its parts), "Data model" ("The past-year warning"), "Key files" | `docs/ARCHITECTURE.md` |
| "Tax invariants" and its rules ("Prices", "Lot cost", "Transfer"…) | `docs/TAX-INVARIANTS.md` |
| "Security rules" | `docs/SECURITY-RULES.md` |
| "Testing" | `docs/TESTING.md`, at its end |
| "Releasing" | `docs/RELEASING.md`: read it before any release step |
| "Start9" | `docs/START9.md`: read it before any Start9 step |
| "Big work" ("The lead runs the merges"…) | `docs/BIG-WORK.md` |
| The maintenance lead's job, and its handoff at each release (new) | `docs/MAINTENANCE-LEAD.md` |
| "Who does what", "Branches", "Pull requests", "Working through GitHub", "Bugs and security", "Starting a session", "Ending a session" | `docs/HOW-CHANGES-FLOW.md`, "The detailed rules" |
| "What's at stake", "Before you change…", "Reviews" | here, word for word |

## Who does what

- **The owner** (DigiMonk73) decides: releases, anything sent to Start9,
  changes in what the app does or computes (agreed before they're
  written), and any figure moved on purpose (by its plain-words
  before-and-after, never by reading code). The owner is not a
  professional developer: explain in plain words, with one
  recommendation.
- **Claude Code** is the developer: code, tests, dependencies, releases,
  docs.
- **Grok** is a second set of eyes (`docs/GROK-REVIEW.md`), never the
  developer: it writes only a job the owner names, outside tax figures,
  login and security, the database and StartOS, and never merges. A
  Grok finding is a claim until Claude checks it, and every Grok-written
  change gets a fresh Claude review.

Each AI signs what it posts on GitHub ("— Claude", "— Grok"…); Claude's
commits carry its `Co-Authored-By` line.

## Reviews

Before a pull request merges, a fresh Claude reviewer goes through it,
without anyone having to ask: a separate agent with no memory of writing the
change, working read-only, that checks the diff and verifies its claims
(runs the tests, looks things up) instead of trusting them. How far it goes
depends on the change:

| Change | Review |
|---|---|
| Docs, process, tooling | One review; another round only for a blocker |
| App code | A review, then a re-check of the fixes |
| Tax figures or what the app computes, the database | A review and a re-check, plus every figures check: the reference ledger's figures (`test_seed_ledger.py`), the independent second calculation (`scripts/independent_figures.py`) and the before-and-after comparison of what the app produces (`scripts/equivalence_check.py`); the database also a backup and restore tried on a 1.x ledger. Then the figures rule, below |
| The StartOS package, releases, anything sent to Start9 | A review and a re-check; then the owner's "merge" in chat (for Start9: before it's sent) |

**The figures rule.** Be extremely careful with anything that affects
figures; the owner isn't asked to review code:

- **No figure moves**, and every check is green: Claude merges, without
  asking the owner. This is for changes not meant to move any figure (a
  refactor, a dependency, wording, a screen).
- **A figure moves on purpose** (a `tax-figures` fix, a new rule): before
  it merges, the owner gets a plain-words before-and-after on the pull
  request and in chat: which figures, for which ledgers and tax years, by
  how much, why, and the tax rule behind it. The owner approves that
  explanation, not the code. What counts is the intent, not whether the
  test ledgers happen to show it: a fix meant to change any user's figure
  (a duplicate check, a price, a box) gets the before-and-after even when
  `equivalence_check` finds no difference, shown on a ledger built to
  show it.
- **A figure moves that nobody meant to move**: stop, find out why and fix
  it; never ask the owner to judge it. If the move turns out to be right
  (a bug the change uncovered), it becomes a figure moved on purpose,
  above.

A new tax year's IRS forms (or the next year's draft preview) follow it
too: the printed forms are checked (`test_printed_forms.py`, and a look at
each new form, docs/IRS_ANNUAL_FORM_UPDATE.md). Adding a year moves no
existing figure, so Claude merges it; if the new forms put existing data in
a different box or line, that's a figure moved on purpose, above. The
release that ships them keeps the owner's "merge".

A change in what the app does for the owner is still agreed with them
before it's written.

Claude posts the review on the pull request, then fixes every finding (a bug
fix with a test that fails on the old code) or answers it there with the
evidence. Grok in Cursor is a second set of eyes when the owner asks
(`docs/GROK-REVIEW.md`): it never replaces the fresh Claude review, and its
comments end "— Grok (Cursor)".

## Pull requests

- Every change goes into `develop` by a pull request of its own from a
  short-lived branch, filled in from its template, squash-merged once
  "CI passed" has passed on a branch up to date with `develop`. A branch
  that falls behind gets `develop` merged in, never a rebase
  (Dependabot's: "@dependabot rebase"). Once the review has nothing
  open, Claude turns on auto-merge as "Reviews" allows; in big work a
  session posts "ready: #N" and only the lead does (`docs/BIG-WORK.md`).
  `staging` is retired (#901).
- Never commit on `main` or a local `develop`, never force-push or
  rewind `main`: it moves only by fast-forwarding to GitHub's `develop`,
  at a release or when all it lacks is docs, tests or tooling
  (`docs/RELEASING.md`).
- **A pull request from outside** (anyone but the owner and Dependabot):
  we take only tests or documentation, after a review that reads every
  line, merged exactly as reviewed; anything else is redone by us. Its CI
  runs only after the owner approves it, every time, and no workflow is
  triggered by `pull_request_target` or `workflow_run`.
  `CONTRIBUTING.md` says it to contributors.

## Public, and on GitHub

- The repository is public: never the owner's ledger figures, personal
  data, keys, passwords or server addresses in a commit, an issue or a
  pull request.
- Never put "close", "fix" or "resolve" (any form) right before an issue
  reference unless that commit finishes it: GitHub closes the issue when
  the commit reaches `main`. Write "for #N".
- Where things stand: pinned issue #41; one issue per task, never an AI
  tool's memory. Every verified bug is a public issue (`bug`, plus
  `tax-figures` when a figure could be wrong), except one in an open
  pull request, fixed there. A security problem is never public before
  its fix, not even a pull request comment: a draft advisory.

## Testing

A bug fix gets a test that fails on the old code. Tests never touch a
real database or the network: temp SQLite, stubbed prices, and the
reference test ledger for a full ledger. `make test-fast` before a push;
the rest is in `docs/TESTING.md`. Never wait on a command by searching
for its text (`pgrep -f`): wait on the process you started.

## Start9

Start9's rules win for what Start9 governs (`startos/`: read
`startos/AGENTS.md`; the mirror; what we send Start9), and a
contribution from Start9 is looked at first, never accepted
automatically: `docs/START9.md`.

## Starting a session

First what ran since the last session: the pull requests into `develop`,
their checks and CI on `develop`. Tell the owner in plain words what's
green and red, fix anything red before new work, then bring up to date
the next pull request waiting behind one that merged. Then the Security
tab, the week's report issue and the open `start9` issues. Then
`make sync-check`, #41, the open pull requests and issues, and carry on
from #41's "Next".

## Ending a session

Push (it runs `make check-fast`), then stop: never wait on CI. Update
`docs/CHANGELOG.md`, the issues worked on, #41 (dated), and this file or
the one its map names if a rule changed. Last, `make sync-check`
(`--tidy`) and remove your clean worktrees whose pull request merged;
end the message to the owner with **Git: in sync**, or what is only on
this computer and why.
