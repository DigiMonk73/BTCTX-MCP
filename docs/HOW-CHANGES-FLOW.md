# How changes flow

The whole path a change takes, from this computer to GitHub, to a release,
to Start9's app store, and back. Written for the owner, who isn't a
professional coder, and for every AI session, so both remember it the same
way. The detailed rules are in its second part, "The detailed rules"
("Branches", "Pull requests", "Bugs and security" and the rest, moved
from `AGENTS.md`), and in `docs/RELEASING.md`, `docs/START9.md` and
`docs/BIG-WORK.md`; this first part is the map. Words in *italics* are
in the glossary at the end of this first part.

## The picture

Our changes go **out**:

```
this computer ──push──▶ short branch ──pull request, full tests──▶ develop
develop ──main catches up──▶ main ──release──▶ GitHub release + mirror
mirror ──pull request──▶ Start9's copy ──Start9 publishes──▶ Community Beta
Community Beta ──owner asks Start9──▶ main store
```

Start9's changes come **back**:

```
Start9's copy ──scripts/start9-pull.sh──▶ short branch ──pull request──▶ develop
(then they go out again with our next release)
```

## The three repositories

| Repository | What it is | How it changes |
|---|---|---|
| **DigiMonk73/BTCTX-MCP** (this one) | The source of truth: the app, the AI connector, the Mac app, and the StartOS package in `startos/` | Changes enter by pull request into `develop`; `main` catches up from `develop` |
| **DigiMonk73/BTCTX-StartOS** (the mirror) | A copy of `startos/` and nothing else | Only by `scripts/sync-startos-mirror.sh`: at each release, and right away for a docs-only change to `startos/`. Never edit it by hand |
| **Start9-Community/BTCTX-StartOS** (Start9's copy) | What Start9 builds and publishes in their app store | Only Start9 changes it. We send pull requests; they merge |

So Start9's copy decides what is *in their app store*. Everything else,
including our own changes to the StartOS package, starts here.

(The mirror and Start9's copy also have a `next` branch, which Start9's
workflow keeps up to date by itself. We don't touch it.)

## Our branches

- **`develop`**: where every change goes, each by its own pull request,
  after the full tests have passed on it. GitHub asks each pull request to
  be up to date with `develop` first, so its tests have run on everything
  already merged: pull requests merge one at a time, each brought up to
  date after the one before it merges. Every merge runs the full tests
  again on the result.
- **`staging`**: retired on 2026-11-04 (the owner: "yes go ahead with
  retiring staging branch"). It let many pull requests from the 2.0
  build merge side by side, and `develop` took it once a day. With one
  or two changes at a time, that was more work than it saved. It stays
  until the next release, since GitHub's Dependabot reads its settings
  from `main` and keeps sending its pull requests there until then; then
  the owner deletes it and its safety rule.
- **`main`**: released code only, what users get. It moves only by
  *fast-forwarding* to `develop`: at a release, or when everything new is
  only docs, tests or tooling. Never pulled from Start9.

2.0.0 is released (2026-10-31), so the next two are history:

- **`2.0`**: BitcoinTX 2.0 while it's being built, apart from 1.x, until
  it joins `develop` at its release. Each build step comes in by its own
  pull request, after a tag (a *pin*) marks where `2.0` stood, so any
  step can be undone; `develop`'s latest 1.x work comes in before every
  step. Its safety rules ("Protect 2.0", "Protect 2.0 pins") are the
  owner's to set. The plan and where each step stands: issue #251.
- **`prerelease/v2.0.0-alpha.N`, then `prerelease/v2.0.0-beta.N`**: a 2.0
  alpha, later a beta, for anyone who chooses to test it, published from
  `2.0` with the owner's "release" (section 2b), then deleted.
- **Short branches**: one per change (`claude/...`), deleted by GitHub
  when its pull request merges.

## 1. An everyday change

1. A change in what the app does for the owner is agreed with them
   before it's written.
2. Claude works on this computer, in its own folder (a *worktree*), and
   runs the tests.
3. A fresh Claude reviewer reads the change on this computer, before
   anything is pushed. At the end of the day Claude pushes every finished
   change's short branch and opens its own pull request into `develop`,
   all at once, with the review on it. Then the session stops: nobody
   waits on the tests; the next session reads the results first thing
   and fixes anything red before new work.
4. GitHub runs the full tests on each pull request.
5. Once the review has nothing open:
   - **ordinary changes**: Claude turns on *auto-merge*, and GitHub
     merges it into `develop` when the tests pass. One waiting behind
     another is brought up to date once that one has merged, and its tests
     run again;
   - **tax figures or what the app computes, the database**: every
     figures check too. If no figure moves, Claude merges. If a figure
     moves on purpose, the owner first gets a plain-words before-and-after
     (which figures, by how much, why) and approves that, not the code. A
     figure that moves by mistake is fixed, never put to the owner;
   - **the StartOS package, anything that goes to Start9, and releases**:
     they wait for the owner to say **"merge"**.

## 1b. Big work

A big job (a release, a redesign, research then build) is split up first.
One main session talks it through with the owner and writes the plan on
GitHub: an issue for the whole job, an issue for each numbered session
with its checklist, and a ready-to-paste kickoff prompt on each. The
main session (or the owner) starts each session from a card or its prompt. Each session
begins from the latest `develop` (never `main`, which lacks what isn't
released yet) and works through its own checklist, pull request by pull
request, stopping where the owner decides. A bug found along the way
is filed as usual (section 5) and gets a session to fix it (bugs found
together may share one); the release waits for the fix unless the
owner leaves it for later. As section 5 says, a problem found while
reviewing a pull request is fixed in that pull request, and a security
problem stays private and is released at once. Sessions never merge
their own work: each reports "ready" on the job's issue, where the main
session keeps the queue and turns on auto-merge for each pull request,
so GitHub merges it into `develop` when its tests pass; pull requests
merge one at a time, each brought up to date after the one before has
merged. The plan also says
which files each session will touch and the order their work merges
in, so sessions don't trip over each other. The main session keeps a
ready-to-paste handoff for itself on the job's issue, up to date after
every change, so a fresh main session can take over when this one
grows too long. Details: `AGENTS.md`, "Big work".

## 2. A release

1. A pull request of its own into `develop` raises
   the version number everywhere, adds the newest hours to the price
   history (`make prices`), and moves
   the CHANGELOG's "Unreleased" part under the new version.
2. When it has merged and the tests pass on `develop`, an AI agent runs the
   release tests (`docs/AGENT-TESTS.md`) on a StartOS test machine. A
   blocker failure stops the release.
3. At the same time, a fresh Claude (not the one that wrote the release)
   reads all the docs against what the release ships: the READMEs, the
   StartOS instructions, store descriptions and release notes, the AI
   connector's guide, `docs/`, `SECURITY.md`, the app's on-screen text,
   and the CHANGELOG. Anything out of date is fixed by pull request before
   step 4, so nothing goes out, or to Start9, with stale docs (the owner's
   rule).
4. `main` catches up with `develop`. That publishes the Docker image
   (`ghcr.io/digimonk73/btctx-mcp:vX.Y.Z`).
5. A `release/vX.Y.Z` branch starts the release on GitHub. It:
   - checks first that Start9's own changes are back in `startos/`
     (section 4), and stops if not;
   - builds the Mac app and the StartOS package (and the Docker image, if
     step 4 hasn't yet);
   - publishes the AI connector to PyPI (not for a package-only fix, a
     version like `v1.2.4-1`);
   - creates the GitHub release with everything attached;
   - copies `startos/` to the mirror (if the `MIRROR_TOKEN` secret is set).
6. Delete the `release/vX.Y.Z` branch afterwards.
7. Check the **landing page** (<https://digimonk73.github.io/btctx-site/>,
   repository DigiMonk73/btctx-site). Its download buttons, release-notes
   link and Docker command follow the latest release by themselves; its
   words and screenshots don't. Claude updates what the release made wrong
   (for example an action's new name), and the screenshots, every release:
   `make site-shots` retakes them, and the changed ones go into the
   README's `docs/images/` (then `main` is fast-forwarded, docs only, as
   GitHub shows the README from `main`) and the landing page together. The owner sees the
   landing page before it goes live, since it's public.
8. Once the release is out and sent to Start9, the maintenance lead hands
   over to a new lead: it brings #41 and its kickoff on #869 up to date,
   offers the new lead as a card for the owner to start, and then archives
   itself (`docs/MAINTENANCE-LEAD.md`, "The handoff at each release").

## 2b. A 2.0 alpha or beta (a pre-release)

While 2.0 is tested, anyone who chooses can try it from GitHub: first as
*alphas* (`v2.0.0-alpha.1`, `alpha.2`…), the earliest test versions,
then as *betas* (`v2.0.0-beta.1`…) once the alphas have settled (the
owner's decision 28, #251). Nobody gets one by accident:

1. `develop` comes into `2.0` first, so the pre-release has every 1.x
   fix.
2. A pull request into `2.0` raises the version to `2.0.0-alpha.N` (or
   `2.0.0-beta.N`) everywhere, with its release notes; the build's lead
   merges it (the owner gave the lead the 2.0 build's merges, #251's
   decision 25).
3. The tests: before the first alpha, CI's full set green on `2.0` and
   the StartOS test machine's trial of the update and the ways back
   repeated on that build; before the first beta, all of 2.0's release
   tests, with a fresh read of every doc; before a later one, those of
   what changed and the update from the one before.
4. With the owner's "release", a `prerelease/v2.0.0-alpha.N` (or
   `-beta.N`) branch from `2.0` starts it on GitHub, the same workflow as
   a release, except that:
   - its commit must be on `2.0`, not `main`;
   - the GitHub release is a *pre-release*, never "Latest", so the
     download links that follow the latest release (the landing page's,
     the README's) stay on 1.x;
   - the Docker image gets only its own tag (`:v2.0.0-alpha.N`), never
     `:latest` or `:main`;
   - the AI connector goes to PyPI as a pre-release (`2.0.0aN`, a beta's
     `2.0.0bN`), which only someone asking for that version gets;
   - the Mac app is a separate app, "BitcoinTX Preview"
     (`BitcoinTX-Preview-macOS.dmg`), the same for every alpha and beta,
     with its own ledger, which carries from one to the next, and a red
     "PREVIEW" band on its icon;
   - every page of a pre-release, on a Mac, StartOS or Docker, has a
     banner naming it;
   - nothing goes to the mirror or to Start9.
5. Delete the `prerelease/` branch afterwards. A pre-release's tag can't
   be moved, and its Docker image and AI connector may be out before the
   tag: if its run fails, its failed steps are run again on the same
   commit, or the next try is the next pre-release, never the same branch
   from a newer commit.

Testers report what they find with the "2.0 alpha or beta report" form
(label `pre-release`). GitHub shows a form only once `main` has it: at
the next fast-forward of `main` that is only docs, tests or tooling, else
at the next 1.x release. The owner decides when the betas have run long
enough; then 2.0's release follows section 2, except that its version change
goes into `2.0` (AGENTS.md, "Releasing").

## 3. Sending a release to Start9

1. The release opens an issue here, **"Send vX.Y.Z to Start9"**, with a
   link. Two exceptions: no issue before Start9 had their copy, and no
   issue while a pull request of ours is still open on their copy (that
   pull request then carries the new release too).
2. Open the link: GitHub shows a ready pull request from the mirror to
   Start9's copy. Click **Create pull request**. Only Start9 can change
   their copy, so a pull request is the only way in.
3. Start9 reviews and merges it, then publishes it to **Community Beta**
   (`https://community-beta-registry.start9.com`).
4. The owner tests the beta on their own server, using a checklist
   Claude writes for that release on the issue that plans its promotion
   (1.2.9's: #143, section 5). BitcoinTX's Community Beta builds are
   signed only by that registry's build key, **Github Actions**. On
   StartOS 0.4.1.2 or later, turning it on for **Packages** under
   **System → Trusted Keys** installs them without a warning; on an
   earlier 0.4.1, update StartOS first.
5. When satisfied, the owner asks Start9, in an issue on their copy, to
   **promote** it to the main store (`https://community-registry.start9.com`).
   Claude drafts that request. Promotion is the owner's call.

**Docs-only changes to `startos/` between releases** don't wait: `main`
catches up, the mirror is synced right away, and that too needs a pull
request to Start9's copy (or rides in one of ours still open there).

## 4. When Start9 changes their copy

Start9 sometimes changes the package themselves: a review (like their
review of 2026-10-05, brought back in #48), template updates about monthly,
*SDK* updates.

1. Claude runs `scripts/start9-pull.sh --apply` on a short branch. It
   copies their changes into `startos/` here, and writes down which of
   their commits it took (`scripts/start9-taken`), so later checks only
   look at what they changed after that.
2. Claude checks and tests it, and opens a pull request into `develop`
   (never straight into `main`).
3. Their change then goes out with our next release (sections 2 and 3),
   so the two copies match again.

**This must happen before our next release or mirror sync**, or our copy
would undo their work. Both check it and stop if it was skipped.

## 5. When a bug is found, or an idea arrives

Anyone can find one: Claude, Grok, you, a user, Start9.

1. **It's checked first.** Claude reproduces it, or confirms it from the
   evidence, and says what was confirmed and what wasn't. A user's report
   arrives labelled `unconfirmed` and gets an answer within a week.
2. **Once confirmed, it's a public issue.** Labels: `bug`, plus
   `tax-figures` if a number could be wrong. Users see every known
   problem: the open `bug` issues are the known-issues list, linked from
   the README. Never any personal data or real figures. (A problem found
   while reviewing a pull request is simply fixed in that pull request.)
3. **It's fixed by a pull request** that closes the issue and adds a test
   that fails without the fix. `tax-figures` bugs come first. Their
   release notes tell users what was wrong, which tax years it touched,
   and what to do.

**Feature ideas** get a thank-you and no promise. You decide:
- yes: it goes on the roadmap;
- no: it's closed as "not planned", with a kind reason;
- not sure: it stays open.

Reports and ideas belong in this repository: the mirror's Issues are off.
Users sometimes open issues on Start9's copy. The Monday report lists
them; with your OK, Claude answers there and, if needed, opens an issue
here that links to it.

**Security problems are the exception: never public first.**
1. They're reported privately (the repository's Security tab,
   `SECURITY.md`).
2. The fix is tested privately, then goes through an ordinary pull
   request whose title doesn't give the problem away, and is released at
   once. Start9 is asked to publish it at once too.
3. Only when the fixed version is out is the advisory published, so
   nobody can misuse the problem in the meantime.

## 6. Keeping this computer and GitHub the same

- `make sync-check` answers "is everything on this computer also on
  GitHub?". It ends with **IN SYNC** or **NOT IN SYNC** and a list.
- Every session runs it when it starts and when it ends, and Claude's last
  message ends with **"Git: in sync"** (or what isn't, and why).
- At the end, Claude also tidies up: `scripts/sync-check.sh --tidy`
  deletes branches whose work is on GitHub, and Claude removes old session
  folders that are clean, whose pull request merged, and that no running
  session uses (the owner's choice, 2026-10-06; never another active
  session's folder).

## The rules that keep it safe

1. Every change goes into `develop` by pull request, with the full tests
   on it and on everything already merged. Never commit on `main`.
2. `main` comes only from our own `develop`, never from Start9.
3. Never edit the mirror by hand: it's a copy, overwritten by each sync.
4. Start9's changes come back through `develop` before our next release.
5. Their copy changes only by their merge: we send pull requests.
6. Nothing stays only on this computer at the end of a session.
7. Every confirmed bug is public; a security problem stays private until
   its fix is out.
8. The StartOS package, the mirror, what Start9's support reads, and
   anything we send Start9 follow Start9's packaging guide: Claude checks
   the guide first and says which page it followed. The app itself, its
   Docker image and the Mac app follow our own rules.

## Glossary

- **Auto-merge**: a GitHub switch on a pull request: "merge this by itself
  as soon as every test passes".
- **Fast-forward**: moving a branch forward to include newer commits,
  without adding any of its own. `main` only ever does this.
- **Pull request**: a proposed change, shown with its tests and review,
  waiting to be merged into a branch.
- **Registry**: a StartOS app store. Community Beta is Start9's test
  store; the community registry is the main one.
- **SDK**: Start9's toolkit for building StartOS packages
  (`@start9labs/start-sdk`).
- **Worktree**: a separate folder with its own copy of the project, so
  several sessions can work at once without getting in each other's way.

# The detailed rules

The rules every session follows for how a change gets from a branch to
`develop`, `main` and the issues, and how a session starts and ends.

Moved word for word from `AGENTS.md` on 2026-11-04 (#903); `AGENTS.md`
now keeps a map of where each part lives. Where the text below says
"this file", it means `AGENTS.md` and the files its map names, and a
section named in quotes ("Branches", "Reviews") is found through that
map.

## Who does what

- **The owner** (DigiMonk73) decides: releases, anything sent to Start9,
  changes in what the app does or computes (agreed before they're
  written), and any figure moved on purpose (by its plain-words
  before-and-after, never by reading code). The owner is not a
  professional developer: explain in plain words, with one recommendation.
- **Claude Code** is the developer: code, tests, dependency updates,
  releases, docs, and a read-only report each Monday of what needs
  attention (a scheduled task on the owner's Mac).
- **Grok** is a second set of eyes, never the developer (its
  roles and passes: `docs/GROK-REVIEW.md`):
  - Grok Bot on the web brainstorms from links the owner gives it
    ("Working through GitHub");
  - Grok in Cursor is the finder: it reviews a pull request when the
    owner asks, and runs the release pass and the monthly area;
  - Grok (in Cursor or Grok Build) writes only a job the owner names,
    outside tax figures, login and security, the database and StartOS
    (the manual names the files), and never merges.

  A Grok finding is a claim until Claude checks it, and every
  Grok-written change gets a fresh Claude review.

Everything goes through GitHub under the owner's account, so each AI ends
what it posts there with its name ("— Claude", "— Claude (reviewer)",
"— Grok", "— Grok (Cursor)", "— Grok (Build)"), and Claude's commits
carry its `Co-Authored-By` line.

## Branches

- **`develop`**: where every change goes, each by its own pull request
  (`gh pr create --base develop`) from a short-lived branch named for the
  change ("Pull requests"), squash-merged once "CI passed" has passed on
  the full set (`ci.yml`; the macOS build runs too, as on every pull
  request, not required) on a branch that's up to date with `develop`
  ("Protect develop", below), so a pull request's checks have run on
  everything already merged. So pull requests merge one at a time, each
  falling behind whenever another merges: each is brought up to date with
  `gh pr update-branch N` (which merges `develop` in) or `git merge
  origin/develop` and a push, never a rebase (Dependabot's: "@dependabot
  rebase", "Pull requests"), and merges once its checks pass again
  (auto-merge never updates a branch by itself). Every merge
  into it runs the full set on the result (`ci.yml`'s push trigger), and
  a red `develop` is fixed before anything else merges into it.
  Dependabot targets it. Never commit on a local `develop`: GitHub
  refuses the push.
- **`staging`**: retired (#901; the owner, 2026-11-04: "yes go ahead
  with retiring staging branch"). It let a night's pull requests merge
  side by side on a medium set of checks, and a daily cycle ("develop
  into staging", "staging into develop") carried them on to `develop`.
  In maintenance, with one or two changes at a time, that was overhead,
  so every change now goes straight into `develop`. The pre-push hook
  refuses any push to it but its deletion. GitHub reads `dependabot.yml`
  only from `main`, so until `main` carries the new one (the next
  release) Dependabot still opens its pull requests into `staging`: each
  is moved onto `develop` ("Pull requests"), and the branch stays, or
  Dependabot's run fails. Once `main` has it, the owner deletes the
  "Protect staging" ruleset and the branch (#901).
- **`main`**: released code only; it is what users get (the `:main` Docker
  image; releases are cut from it). Never commit on `main`, never
  force-push or rewind it. It moves only by fast-forwarding to GitHub's
  `develop` (`git fetch origin && git checkout main && git merge --ff-only
  origin/develop && git push`), at a release, or when everything on
  `develop` not yet on `main` is docs, tests or tooling (nothing that ships
  in the app or the connector).
- **`release/vX.Y.Z`**: pushed from `main` to publish (see Releasing), then
  deleted.

2.0.0 is released (2026-10-31), so the next two bullets, `2.0` and its
pre-releases, are history, kept here for now:

- **`2.0`**: BitcoinTX 2.0 being built (#251), until it merges into
  `develop` at its release. Its steps arrive by pull request
  (`gh pr create --base 2.0`), one per step, for which the build's
  lead turns on auto-merge from its queue on #251 ("Big work"),
  squashed, after the tag `pin/2.0-step-<n>` on its tip. `develop`
  comes in before every 2.0 session by a pull request of its own,
  merged with a merge commit (`gh pr merge --merge`), never a rebase
  or a squash. Never commit on a local `2.0`, never force-push it,
  never move or delete a pin. Its branches are named `2.0-…` (git
  refuses `2.0/…`). The plan: `docs/temp/2.0-accounts.md`, section 7;
  the steps and where they stand: #251.
  `make catch-up-2.0` (`scripts/catch-up-2.0.sh`) does that `develop`
  merge when it is clean (no 1.x migration, no change to the reference
  test ledger or its figures, no conflict): GitHub makes the merge commit
  on a branch of its own, `2.0-merge-develop-auto-…`, and its pull request
  merges by itself once its own CI passes, with no review of its own (the
  owner's decision 24, #251). Nothing is opened while a 2.0 step has
  auto-merge on, and a step's pin is never taken while a catch-up has it
  on, so each pin is `2.0`'s tip when its step lands. Anything else stops
  for the build's lead. It also lists a new 1.x release (B1's
  `reference_1x.db` made again from it) and `startos/` changes. The lead
  runs it before every step and nightly at 22:30 (America/Chicago, a
  scheduled task on the Mac mini), so 1.x's fixes reach `2.0` without
  waiting. Never `gh pr update-branch` on a catch-up: its head is the
  merge commit its CI tested.
- **`prerelease/v2.0.0-alpha.N`, then `prerelease/v2.0.0-beta.N`**:
  pushed from `2.0`'s tip to publish a 2.0 pre-release on GitHub, an
  alpha, then a beta (B10a; #251's decision 28), then deleted. A
  pre-release never moves Docker's `:latest` or `:main`, never reaches
  the mirror or Start9, and is never "Latest" on GitHub. Its tag can't
  be moved or deleted ("Protect release tags"), and its image and
  connector may be out before the tag: a failed run's jobs are re-run on
  the same commit, or the next try is the next pre-release (`alpha.N+1`
  or `beta.N+1`); the branch is never pushed again from another commit.

The pre-push hook refuses a push to `main` of anything not already on
GitHub's `develop` (and one that deletes, rewinds or force-pushes `2.0`,
moves or deletes a `pin/2.0-*` tag, or pushes to the retired `staging`),
and `release.yml` refuses a release commit that isn't on `main` and a
pre-release commit that isn't on `2.0`. GitHub's rulesets (Settings → Rules; only the owner changes them)
add: `main` can't be deleted or force-pushed ("Protect main", also on the
mirror); `develop` can't either, and takes changes only by pull request,
squash-merged (the ruleset allows a merge commit too, which the retired
daily cycle used), once `ci.yml`'s one required check, "CI passed", has
passed ("Protect develop"; it needs every job except
the macOS build and the macOS dependency audit, which run but aren't
required; Python tests run on 3.11 and 3.13, both in it, since #546, each
as three shards and a guard that every test ran once, since #814), on
a branch that's up to date with `develop` ("Require branches to be up to
date before merging", on since 2026-10-17, the owner's choice), so a pull
request's checks have run on everything already merged. "Protect 2.0"
guards `2.0`: pull requests only (squash, or a merge commit for a
`develop` merge), "CI passed" required, no up-to-date rule, and no
deletion or force push; "Protect staging", the same for the retired
`staging`, is the owner's to delete (#901). And "Protect 2.0 pins" keeps
each `pin/2.0-*` tag where it was made: created, never moved or deleted.
A job is required by being in "CI passed"'s `needs` (`ci.yml`), so renaming,
splitting or adding one changes no ruleset; only a rename of "CI passed"
itself would. A release tag (`v*`) can't
be moved or deleted by anyone ("Protect release tags", since 2026-10-18,
the owner's choice), so each release's code stays at its tag to roll back
to; the release workflow still creates new ones. If unsure, branch from
`develop` and ask.

## Pull requests

Every change, Claude's included, goes into `develop` by a pull request of
its own ("Branches"). **The nightly
batch** (the owner, 2026-10-22): each change is written and tested on its
own branch during the day, and its fresh review runs there, before any
push; at the end of the day (or a good stopping point) every finished
branch is pushed and gets its own pull request into `develop`, all at
once, with the review posted on it and auto-merge on (one that needs the
owner's "merge", or the figures rule's OK on a before-and-after, gets
auto-merge only after it). Never merge changes into
`develop` locally: each keeps its pull request (its description, checks
and history). Each pull request is filled
in from `.github/pull_request_template.md`: what and why, a plain-words line
for the owner, how it was tested, the risk. Once the review has nothing
open, Claude turns on GitHub's auto-merge (`gh pr merge N --auto --squash
--match-head-commit <sha>`), and GitHub squashes it, one commit per change,
when "CI passed" passes (if it already has, GitHub refuses
`--auto`; the same command without `--auto` merges it at once). `develop`
asks a branch to be up to date ("Branches"), and auto-merge never updates
one by itself, so a batch's pull requests merge one at a time: once one
has merged, the next is brought up to date (`gh pr update-branch N`,
which merges `develop` in, or `git merge origin/develop` and a push; a
Dependabot pull request: comment "@dependabot rebase" instead, since
Dependabot stops maintaining a branch once anyone else commits to it, and
it rewrites only its own branch) and merges once its checks pass again.
After an update, check that auto-merge is still on (`gh pr view N --json
autoMergeRequest`); if it isn't, turn it on again with the new head's
sha. So a batch lands one pull request per full run (about 15 minutes
each), in the order the batch planned: what's left when the session ends
is brought up to date by the next session ("Starting a session"), never
by waiting, and changes that belong together go in one pull request. A
pull request moved onto `develop` (`gh pr edit N --base develop`, say a
Dependabot one opened against `staging` before `main` carried the new
`dependabot.yml`: "Branches") gets a new commit, or is closed and
reopened, so the full set runs: changing the base starts no run. During
big work, sessions report "ready: #N" and the lead turns on auto-merge instead
("Big work", "The lead runs the merges"). The owner
allowed `gh pr merge` in this project's local Claude settings for that.
A change in tax figures or what the app computes, or the database, follows
the figures rule ("Reviews"): auto-merge when no figure moves and every
check is green; after the owner's OK on the before-and-after when a figure
moves on purpose. The StartOS package, releases and anything sent to Start9
get auto-merge only after the owner's "merge" in chat. A change in what the
app does for the owner is agreed with them before it's written, not at
merge time. Dependabot's pull requests go the same way, after Claude has
read their changelogs; what else they need before merging, and what to do
when one breaks something: `docs/MAINTENANCE.md`, "Before a Dependabot pull
request merges" and the two sections after it.

A branch that falls behind its base gets the base merged into it, never a
rebase (a Dependabot branch excepted: "@dependabot rebase", above): a
pushed branch is not rewritten, and the squash keeps `develop` clean
anyway.

**A pull request from outside** (anyone but the owner and Dependabot; the
owner, 2026-10-29, #799; `CONTRIBUTING.md` says it to contributors): we
take only tests or documentation, after a review that reads every line,
merged exactly as reviewed (#626 was one test file). Anything touching
app code, CI, dependencies, the build, StartOS or tax logic is redone by
us, by a pull request of our own. Its CI runs only after the owner
approves it, every time (the repository's setting
`all_external_contributors`, since 2026-10-29: an automated account's one
merged pull request made it no longer "first-time"). No workflow is
triggered by `pull_request_target` or `workflow_run`, so an outside pull
request never gets a secret: keep it so. A contribution verified as
Start9's comes first ("Start9").

## Working through GitHub

One home for each kind of information, so nothing is kept twice:

| What | Where |
|---|---|
| How we work | this file |
| Where things stand | pinned issue #41, "Where we are": in flight, next for Claude, waiting on Start9 or the owner |
| To-dos, work under way, questions | GitHub issues on this repo, one per task |
| Bugs (the known issues) | public GitHub issues labelled `bug` ("Bugs and security") |
| Security problems | private GitHub security advisories until fixed (`SECURITY.md`) |
| A change | one branch and one pull request into `develop` |
| What's done | `docs/CHANGELOG.md` and the merged pull requests |
| What's next overall | `docs/ROADMAP.md`: checkboxes, ticked when done, cleared at the release that ships them |
| The StartOS package's own to-dos | GitHub issues labelled `start9` (Start9's template keeps no `TODO.md` in the package) |

- **Labels say who has an issue:** `claude` (Claude is on it), `owner`
  (needs the owner: a decision, a test, a click), `ask-grok` (waiting for
  Grok Bot's view), `start9` (the package, Start9's fork or registry); the
  workflows label the issues they open. Labels for what an issue is:
  `bug` (confirmed), `unconfirmed` (a report not yet reproduced),
  `pre-release` (a report from a 2.0 alpha or beta, its own form: B10a),
  `tax-figures` (a figure could be wrong), `security` (hardening, and a
  fix's follow-up once released: never an unfixed vulnerability),
  `enhancement`. A pull request that finishes one says `Closes #N`, and Claude closes the issue when it merges: GitHub
  closes issues by itself only for pull requests into the default branch,
  `main`.
- **A closing word next to an issue number closes it.** In a commit message
  or a pull request, never put "close", "fix" or "resolve" (any form, any
  case, with or without a colon) right before an issue reference (`#N`,
  `owner/repo#N` or an issue's link) unless that commit finishes it.
  GitHub closes the issue when the commit reaches `main`, even months
  later at a release. #165's commit put "fixes:" right before #41 and
  closed the pinned "Where we are" when 1.2.8 fast-forwarded `main`.
  Write "for #N", "on #N" or "(#N)" instead.
- **A long checklist** for work under way may live in `docs/temp/<topic>.md`
  (`docs/temp/README.md`), deleted when done. No other notes, plan or status
  files, and no project status in an AI tool's private memory: it goes in
  an issue, where everyone sees it (private details never do, see below).
- **Asking Grok Bot:** Claude writes the question as a comment that stands
  on its own (what, why, links) on an issue or pull request and adds
  `ask-grok`; the owner gives Grok Bot the link. Grok's answer comes back as
  a comment ending "— Grok" (the owner posts it there, or pastes it into
  their chat with Claude, who posts it), and Claude takes the label off.
- **This repository is public, and so is everything in it:** commits, pull
  requests, issues, the CHANGELOG. Never put the owner's ledger figures,
  personal data, keys, passwords or server addresses in any of them.

## Bugs and security

BitcoinTX is public, its StartOS package is in Start9's Community Beta,
and its figures go on tax returns: users must be able to see every known
bug. These are the public promises of `SECURITY.md`, `CONTRIBUTING.md`
and the README's "Reporting problems"; keep them.

- **Every bug in code on `develop` or in a release becomes a public issue
  as soon as it's verified,** whoever finds it: Claude, Grok, the owner, a
  user, Start9.
  - Findings in the review of an open pull request are fixed in that pull
    request instead.
  - Verify it before filing: reproduce it, or quote the evidence. Say what
    was verified and what wasn't. A report from Grok or a user is a claim
    to check, not a finding.
  - Label it `bug`, plus `tax-figures` when a figure could be wrong.
  - The issue stands on its own: what happens, how to reproduce it, what
    it affects, who found it.
  - Never personal data or the owner's figures; use a test ledger.
  - Fix it as fast as its risk allows. `tax-figures` bugs come first.
- **User reports** arrive labelled `unconfirmed`.
  - Reproduce them, or ask for steps (never for real data).
  - Then relabel `bug`, or close with the reason.
  - Answer within a week.
- **Feature requests** arrive labelled `enhancement`: an idea, never a
  promise (owner's rule, 2026-10-10).
  - Answer within a week: thank them, say it's recorded, promise nothing.
  - The owner decides; until then it carries `owner`. Yes: it goes on
    `docs/ROADMAP.md`, and the issue stays open until the pull request
    that ships it says `Closes #N`. No: close it as "not planned", with a
    kind one-line reason. Not sure: it stays open.
- **Reports and ideas belong in this repository.**
  - The mirror is a copy: its Issues are off, and its description points
    here.
  - Issues users open on Start9's fork are reports too, and the Monday
    report lists them. GitHub can't move an issue between accounts, so,
    with the owner's OK (it's sent to Start9): answer it there and, when
    the work belongs here, open an issue here that links to it.
- **A security problem is never public before its fix.**
  - Outsiders report it privately (Security tab, "Report a vulnerability").
    Claude files its own as a draft advisory ("New draft security
    advisory"), also one found while reviewing: never a pull request
    comment.
  - Test the fix privately with `make check`. GitHub's temporary private
    fork runs no CI and skips the branch rules.
  - Then send it as an ordinary pull request into `develop`, with a
    neutral title, so CI and the review run, and release it the same day.
    Ask Start9 to merge and promote it at once.
  - Publish the advisory (what, which versions, what to do) only once the
    fixed version is available, on StartOS too.
  - Aim to acknowledge a report within 7 days.
  - An advisory titled "Conduct:" is a code-of-conduct report: answer it,
    then close it, never publish it.
- **A fix:**
  - says `Closes #N`, with a test that fails without it;
  - gets a CHANGELOG entry naming the issue.
  - For a `tax-figures` bug, the entry tells users what was wrong, which
    versions and which tax years or transactions it affected, and what to
    do (for example, Ledger Review, then Recalculate Ledger). The release
    repeats it in the StartOS release notes ("Releasing", step 1).
- **The Monday report** (`monday-report.yml`; `docs/MAINTENANCE.md`,
  "Scheduled checks") lists:
  - open `tax-figures` issues;
  - outside reports with no answer, here, on Start9's fork or on the
    mirror;
  - open `start9` issues: what Start9 released or changed that the
    StartOS package hasn't followed yet.

  It says nothing about security advisories, not even how many: look at
  the Security tab. The latest Grok pass is on #41.

## Starting a session

**First, what ran overnight** (the owner, 2026-10-22): the night's pull
requests into `develop` and their checks, and the full set on each merge
into `develop` (`gh pr list --base develop`, `gh run list --branch
develop --limit 10`). Tell the owner in plain words what's green and
what's red, and fix anything red first, before any new work; then bring
up to date the next reviewed pull request waiting behind one that merged
("Pull requests"). Then the Security tab (draft advisories, Dependabot's
alerts), the week's Monday report issue and the open `start9` issues.
GitHub runs a schedule only from `main`: until `main` carries
`monday-report.yml` (from 2.0.1's release), run `scripts/monday-report.sh
--dry-run` instead. `start9-watch.yml` already runs from `main`
(startos/UPDATING.md, "Watching Start9").

Then run `make sync-check`: it brings local `main`, `develop` and `2.0`
down from GitHub and says whether anything exists only on this computer: work not
committed in any working folder, branches or commits not on GitHub,
stashes. Another session's unpushed branch may show up: it's theirs. Then read issue #41
(`gh issue view 41`), the open pull requests and issues (`gh pr list`,
`gh issue list`), and carry on from #41's "Next for Claude". Project status
comes from there, not from an AI tool's memory.

## Ending a session

**Push, then stop: never wait on CI** (the owner, 2026-10-22). After the
night's batch is pushed and its pull requests opened (auto-merge on where
allowed), the session ends: no watching, polling or waiting on a pull
request's checks, or the full set on `develop`.
Waiting burns the owner's limits for nothing; the next session reads the
results first thing ("Starting a session"). If something truly must be
watched, say so to the owner, so a scheduled check or Silas does it.

Run `make check-fast` (or push, which runs it), update `docs/CHANGELOG.md`
and the issues worked on, rewrite #41's body for the next session (dated),
and update this file if architecture, invariants or the way we work changed.
Last, run `make sync-check` (or `scripts/sync-check.sh --tidy`, which also
deletes local branches already on GitHub, safe while other sessions run:
never a checked-out branch or a working folder), then remove old session
folders by hand: only clean ones whose pull request merged and that no
running session uses (`git worktree remove`; the owner's choice,
2026-10-06). End the message to the
owner with its answer in one line: **Git: in sync** (everything on GitHub),
or what is only on this computer and why. The owner can't see where work
is, so this line is how they know.
