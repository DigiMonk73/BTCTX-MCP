# The maintenance lead

The lead session's job while BitcoinTX is maintained, written so a fresh
lead can start from this file and the kickoff on #869 alone, with no
earlier conversation. The owner, 2026-11-04: "after each release, in
this case 2.0.1, each Lead maintenance session should kick off a new
lead that itself uses sub sessions, and each new lead session needs to
understand our maintenance system."

This file adds the lead's role and its handoff; every rule it names
lives where it points. If anything here seems to differ from
`AGENTS.md`, `AGENTS.md` wins: fix this file by pull request.

## What maintenance means

- **2.0 is the final stable release** (the owner, 2026-10-31, #869): no
  new features. The work is updates, bug fixes and security fixes. A
  feature request is an idea, never a promise
  (`docs/HOW-CHANGES-FLOW.md`, "Bugs and security").
- **The order of work:** a security problem first, then `tax-figures`
  bugs, then outside reports (each answered within a week), then
  Dependabot, then other bugs (#869, "A weekly rhythm").
- **Releases** come about every three months; a `tax-figures` or
  security fix goes out when it's ready (the owner, 2026-10-31).
- A new tax year's forms each January, or a big Start9 change, is the
  yearly bump: big work (`docs/BIG-WORK.md`).

## Where things live

| What | Where |
|---|---|
| The maintenance plan, the owner's decisions | #869 and its comments |
| A release's plan, its sessions, the merge queue, "ready: #N" | the release's umbrella issue (2.0.1's is #869 itself) |
| A release's steps at a glance | the board ("The board", below) |
| The lead's kickoff, kept current | #869's comment "Kickoff prompt for the lead session" |
| Where things stand, what's next | pinned #41, "Where we are" |
| What waits on the owner | issues labelled `owner`, and #41 |
| One task | one issue, with its checklist |
| What the watchers found | the Monday report issue, and `start9` issues (`docs/MAINTENANCE.md`, "Scheduled checks") |
| Messages with Silas | the mailbox: issues labelled `for-claude` or `for-silas` in DigiMonk73/mac-mini-setup |

The rest of "one home for each kind of information":
`docs/HOW-CHANGES-FLOW.md`, "Working through GitHub".

## Starting as lead

1. Read this file, then #869's kickoff comment, then #41, and post on
   #869 that you have ("Lead · maintenance after 2.0.1: started, kickoff
   read"): the outgoing lead waits for that line. After a compaction,
   re-read the kickoff and #869's latest comments first.
2. Do what `AGENTS.md`'s "Starting a session" says, in its order
   (`docs/HOW-CHANGES-FLOW.md` has it in full): what ran overnight (the
   pull requests into `develop`, their checks, CI on `develop`), told to
   the owner in plain words, red fixed first; then the next pull request
   waiting behind one that merged.
3. Then the lead's own look:
   - the open pull requests (`gh pr list`), Dependabot's among them.
     Until `staging` is deleted (#901), a Dependabot pull request into
     `staging` is moved onto `develop` (`docs/HOW-CHANGES-FLOW.md`,
     "Pull requests");
   - the open `tax-figures` and `start9` issues, the Security tab and
     the week's Monday report;
   - the mailbox: `gh issue list -R DigiMonk73/mac-mini-setup --label
     for-claude`;
   - the sessions still running, from the app's session list and their
     issues: sessions an earlier lead started send it no end notices.
4. Carry on from the kickoff's "Next" and the queue on the release's
   umbrella issue. A lead that has just taken over begins the release
   cycle, below, at its first step.

## The release cycle

The same steps every release, so the work stays safe, consistent and
repeatable (the owner, 2026-11-04):

1. **Choose the next release's scope.** The new lead goes through the
   open issues: bugs, `tax-figures`, `security` (hardening only: an
   unfixed vulnerability is a draft advisory, never an issue), `start9`,
   Dependabot's pull requests, outside reports and the `owner` items.
   It decides what goes into the next maintenance release (2.0.2 after
   2.0.1, and so on), in "What maintenance means"'s order, and brings
   that scope to the owner in plain words, with one recommendation. The
   owner agrees it; then the release gets its milestone and its umbrella
   issue, with the scope and the owner's words, dated.
2. **Plan it in detail.** The lead starts a planning session that writes
   the release's plan on its umbrella issue, broken into steps, each
   step into micro-steps. For each step: what "done" means, its
   footprint, its owner points, its review ("Reviews") and its tests,
   written first and seen to fail. The plan follows `docs/BIG-WORK.md`'s
   (the footprint and merge plan, the kickoff per session, the index),
   and after each merge the lead re-plans the next one or two steps
   against what merged ("Planned ahead, detailed just in time").
3. **Start every session at once, while the owner is at the Mac.** Once
   the plan's steps are on the umbrella issue and the board, the lead
   asks the owner, at the Mac, to say "start them", then starts every
   session the release needs in one go, one per issue or step. The app
   starts a session only on the owner's own words, and a start over
   Remote Control was refused (2026-11-02); once they all exist, the
   owner can work with them remotely. Waiting is the default: each
   brief says to post its checklist, read what it needs, then wait for
   the lead's "go" message before writing code. An idle session costs
   nothing.
4. **Run it.** The lead sends "go" in the plan's order, to the one or
   two the merge plan allows (below), merges from the queue, then
   releases (`docs/RELEASING.md`). Before the handoff it archives every
   session and removes their clean folders.
5. **Hand over.** The release ends with the handoff (below), and the new
   lead starts again at step 1.

### The board

The owner follows the work on GitHub Projects. Each release's issues go
on the board with a status for each step: planned, in progress, ready,
merged. The lead keeps it current as steps start, report ready and
merge. Like the 2.0 board (project 2), it is a view, never the source:
the issues and their pull requests hold the plan and the state, and a
card changes only to follow them. Which board it is, the owner decides;
the lead doesn't create or change one without the owner's go.

## Working through numbered sub-sessions

The lead plans, triages, talks with the owner and runs the merges; the
work itself runs in sub-sessions. A question, a read or a comment stays
with the lead. How a session is set up, started and run is
`docs/BIG-WORK.md`, which the points below follow.

- **Name each one** by its release, its step number and its issue, so
  the owner can find it from a phone: "2.0.2 · 3 · Fix #NNN". Its issue
  holds its checklist, "Done when" and the points where it stops for
  the owner.
- **Start it with the app's start tool, from `develop`:** run `make
  sync-check` first, and name `develop` as the base of its own working
  folder (`docs/BIG-WORK.md`, "Every session starts from `develop`").
  The app starts a session only on the owner's own words, so a
  release's sessions are started together (the release cycle, step 3);
  one added later is offered as a card the owner clicks, or started on
  their words.
- **A brief that stands on its own:** the issue, the goal, "Done when",
  the files it may touch, what not to touch, the review its change
  needs ("Reviews"), the owner's points, the first commands (`git
  fetch origin`, then `git merge --ff-only origin/develop`), and "wait
  for the lead's go before writing code".
- **At most two working at once**, the rest waiting for their "go", and
  two work together only when they share no file or hot spot but
  `docs/CHANGELOG.md` (`docs/BIG-WORK.md`, "Running sessions at once").
- **All code work on Opus 5.5 or a later Opus release**, never a Sonnet
  (the owner, 2026-11-01, #869).
- **Sessions report "ready: #N"** on the release's umbrella issue and to
  the lead, and never turn
  on auto-merge.
- **The lead merges from one queue** on that issue, one pull request at a time
  where files overlap: it checks the review is posted with nothing open,
  and the owner's words quoted where they're needed, then turns on
  auto-merge; once one merges, it brings the next up to date
  (`docs/BIG-WORK.md`, "The lead runs the merges").
- **A session's report is a claim:** the lead checks the pull request
  and its diff before telling the owner it's done.
- **A bug found on the way** is reported to the lead, which files it
  and, on the owner's words, adds a session for it, as the plan allows
  (`docs/BIG-WORK.md`, "A bug found on the way").
- **When a session is done** (its pull request merged, or closed), the
  lead archives it and removes its folder, if clean, with `git worktree
  remove` (never another session's, never one in use), then runs `make
  sync-check`.

## Reviews and the figures rule

The review scale and the figures rule are `AGENTS.md`'s "Reviews": read
them there. The lead names in each brief which review the change needs,
and queues nothing whose review isn't posted.

## What always needs the owner

- a release, and the StartOS package (`startos/`): the owner's "merge";
- anything sent to Start9, before it's sent;
- a figure moved on purpose: the owner approves its plain-words
  before-and-after, never the code;
- a change in what the app does, agreed before it's written;
- a click only the owner can make, such as a ruleset;
- a password or a two-factor code (the Mac mini's house rule 5).

Bring each in plain words, with one recommendation. Quote the owner's
answer, dated, on the issue or pull request it decides.

## When a fix keeps finding new edges

#824 and #849 (2.0.1): draft #906 went through six fresh reviews. Each
one found another path where the fix moved a figure outside the bug's
case, and the last was caused by a fix. When reviews keep finding new
edges, stop patching: bring the owner the simpler choice, in plain
words, with what it costs. There it was closing #824 and #849 with no
code change, since Ledger Review already lists the one figure the bug
can affect and corrects it (the owner, 2026-11-04: "Close, no code
change").

## The Mac mini's house rules

`~/AGENTS.md` (kept in DigiMonk73/mac-mini-setup) binds every assistant
on the Mac mini; read it when you start. In short: the owner decides;
Claude is the chief engineer (the owner, 2026-11-04); Silas is the
second opinion, and his finding is a claim until Claude checks it; only
Silas starts jobs; Claude and Silas talk through the mailbox, and a
message never carries the owner's approval. Where it is stricter than
this repository, it wins.

## The handoff at each release

Each release ends with a new lead (the owner, 2026-11-04). Once the
release is out and sent to Start9 (`docs/RELEASING.md`, its last step),
the outgoing lead:

1. **Rewrites #41** for the next lead, dated.
2. **Edits #869's comment "Kickoff prompt for the lead session"** in
   place: one comment, kept current, never a new snapshot (if it doesn't
   exist yet, the first handoff writes it). It is the new lead's brief:
   read `docs/MAINTENANCE-LEAD.md`; the current state as pointers (the
   release just made, the sessions still running with their issues and
   pull requests, the queue, the board, what waits on the owner); and
   what's next: the release cycle's step 1.
3. **Proposes the new lead** as a session card, named by its release:
   "Lead · maintenance after 2.0.1". The app starts a session only on
   the owner's own words, so the owner clicks the card or says "start
   it".
4. **Archives itself** once the new lead has posted on #869 that it
   started and read the kickoff, and after its own sub-sessions are archived and
   their folders removed. It ends as "Ending a session" says, with
   **Git: in sync**.
