# Big work

The owner's standard for work that won't fit one session; in
maintenance, the yearly bump. Where it names the 2.0 build (`2.0`, its
steps on #251), that is history: 2.0.0 is released (2026-10-31), and
the words are kept as they were.

Moved word for word from `AGENTS.md` on 2026-11-04 (#903); `AGENTS.md`
now keeps a map of where each part lives. Where the text below says
"this file", it means `AGENTS.md` and the files its map names, and a
section named in quotes ("Branches", "Reviews") is found through that
map.

## Big work: a main session and numbered sessions

The owner's standard for big work (2026-10-12, first used for the stable
release, #143): work that won't fit one session, has parts that can run
at once, or needs the owner's decisions between steps (a release, a
redesign, research then build). A single fix or a docs change stays in
one session. Claude suggests this setup when a request is that big.

- **The main session** talks it through with the owner, then writes the
  plan down on GitHub, where every session and the owner can see it:
  - an umbrella issue with the goal, the decisions and the order;
  - an issue per session with its checklist (what "done" means, and the
    "owner" points where it stops); a plan and its build may share one;
  - on each, a comment "Kickoff prompt for this session" that stands on
    its own: how to start (from `develop`: see below), the rules that
    matter most, the job, and what it waits for;
  - on the umbrella, an index of the prompts: the order, and what each
    session waits for.
- **Starting one:** the desktop app's one-click card (`start_session`), or
  the kickoff prompt pasted into a new session. Each title starts with
  its number ("6 · Build hourly prices (#144)").
- **Every session starts from `develop`** (`2.0` during the 2.0 build:
  its plan says how). When the lead starts one with a working folder of
  its own, it runs `make sync-check` first (the start tool cuts the
  folder from a local branch; `make sync-check` brings local `main`,
  `develop` and `2.0` (when there is one) up to GitHub's, and a `git
  fetch` alone moves only `origin/develop`), then names `develop` as the
  folder's base (the start tool's `source_branch`): otherwise the folder
  may be cut from `main`, which lacks everything not yet released. Each
  kickoff prompt then says: before any work, `git fetch origin`, then
  `git merge --ff-only origin/develop`, which brings the folder up to
  `develop` and refuses rather than lose anything (`git rev-list --count
  HEAD..origin/develop` then prints 0). A folder that already has
  commits of its own, or one the fast-forward refuses, takes `git merge
  origin/develop`, never a rebase.
- **A bug found on the way gets its own session** (the owner,
  2026-10-16: "We want to get every thing fixed by you spinning up new
  sessions for bugs we find"). When anyone finds one during big work (a
  session, a review, a test, the owner), it's filed as usual ("Bugs and
  security"); then the lead adds a session for it to the umbrella (its
  issue, kickoff prompt and footprint; bugs found together may share
  one), starts it as the merge plan allows, and has the release wait for
  it, unless the owner leaves it for a later release. Two cases stay as
  "Bugs and security" says: a bug in an open pull request, found by its
  review or its tests, is fixed in that pull request; and a security
  problem goes to a draft advisory, never onto the umbrella or any
  issue, and its fix is released the same day rather than held for the
  release.
- **Planned ahead, detailed just in time** (the owner, 2026-10-22): the
  plan gives every session its scope, "Done when", footprint and owner
  points up front; a session's micro-steps are written only when it
  starts, as its issue's checklist, with its "Done when" tests written
  first and seen to fail; after each merge the lead re-plans the next
  one or two sessions against what merged, and takes anything that
  touches an owner's decision to the owner first.
- **Each session** first posts or refreshes its checklist on its issue,
  ticks the boxes there as it goes, and writes its decisions there. It
  carries on from its own issue, not from #41's "Next". After a
  compaction it re-reads its issue and its open pull request before
  anything else. It stops at the "owner" points. At its end it does what
  "Ending a session" says, except that on #41 it adds only its own lines,
  re-reading #41 just before it edits, since other sessions edit it too.
  No plan mode by default: plan mode's plan stays in that session, while
  the issue's checklist is seen by all.
- **The main session** carries the owner's decisions to the sessions, on
  their issues or by a message to one that's running. The owner's
  "merge", or OK on a before-and-after, is quoted on its pull request,
  with the date, by the session the owner said it to. The main session starts the next session when what it
  waits for is done, and keeps #41's "Next", linking to the umbrella
  issue instead of repeating its order.
- **The footprint and merge plan** (owner, 2026-10-12): planned up front,
  so conflicts are few and expected. On the umbrella issue the main
  session lists, for each session:
  - **its footprint:** the files and areas it expects to touch;
  - **its hot spots, shared with other sessions:** `docs/CHANGELOG.md`,
    `testdata/reference_ledger.json` and `reference_figures.json`,
    `scripts/independent_figures.py`, migrations, `docs/AGENT-TESTS.md`,
    the i18n dictionaries;
  - **any migration numbers reserved for it** (for example 0011, then
    0012 with `down_revision` 0011: Alembic can't load a parent that isn't
    there, so the second is written on the current head until 0011 is on
    `develop`, then re-pointed);
  - **the merge order** between sessions.

  A session whose footprint grows says so on its issue before it merges,
  and the main session checks it against the others.
- **Running sessions at once:** only when they share no hot spot other
  than the CHANGELOG; sessions that share one run one after the other,
  unless the plan names which merges second. The one that merges second
  merges `develop` in (never a rebase), keeps both CHANGELOG entries,
  merges the reference ledger's rows by hand, reruns
  `make reference-figures` (never hand-merging the figures) and checks
  that the diff shows only the two sessions' intended moves, and checks
  the migration numbering.
- **Stacking within a session:** at most two pull requests on the same
  files; wait until the first has merged before starting a third, since
  each squash makes the next one conflict.
- **The lead runs the merges** (the owner, 2026-10-17: "You, as lead,
  run every merge from one queue on the umbrella; sessions report ready
  instead of turning on auto-merge"). A session never turns on
  auto-merge: once a pull request's review (and re-check, where
  "Reviews" asks one) has nothing open, it posts "ready: #N" on the
  umbrella issue (and tells the lead, if it's running), so a new lead
  finds it too. The lead keeps the queue on the umbrella issue (the
  order, what each needs, its state). For each ready pull request into
  `develop` (or `2.0` during the 2.0 build), it checks that the owner's
  "merge", or the OK the figures rule asks for, is quoted on it where
  one is needed (none for a change that moves no figure: "Reviews", the
  figures rule), then turns on auto-merge (`gh pr merge N --auto
  --squash --match-head-commit <sha>`). `develop` asks a pull request to
  be up to date (`2.0` didn't), so the lead brings the next one up to
  date (`gh pr update-branch N`) once the one before has merged, and
  GitHub merges it when its checks pass again; the lead plans that order
  when it hands out the work. On a conflict or red checks, or where
  "Running sessions at once" has the session merge `develop` in itself,
  its session, or one the lead starts for it, does that and fixes what
  broke (a session still working on that branch pulls before its next
  push). Dependabot's pull requests, and any other merge into `develop`
  while big work runs, go through the same queue. (#413 merged on checks
  run before #416 changed the sentence its test expected, and `develop`
  broke: #417. `develop`'s up-to-date rule, on since 2026-10-17, now
  stops that.)
- **The main session's own handoff:** the main session (the "lead")
  keeps a comment "Kickoff prompt for the lead session" on the umbrella
  issue, edited in place after every change, never left as a snapshot:
  its role and duties, how to start, and a short current state as
  pointers (the running sessions and their open pull requests, what to
  watch, decisions not yet on an issue). Session status stays in the
  index, what waits on the owner on #41 and the `owner` issues, and
  decisions on their issues. After a compaction, the main session
  re-reads that comment and the index first. The owner keeps it as long
  as it works well; when it grows too long, the owner starts a new main
  session from that comment and archives the old one. A new main session
  finds the running sessions in the session list and on the issues,
  since sessions an earlier one started don't send it their end notices.
