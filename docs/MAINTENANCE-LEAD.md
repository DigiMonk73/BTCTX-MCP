# The maintenance lead

The lead session's job while BitcoinTX is maintained, written so a fresh
lead can start from this file and the kickoff on #869 alone, with no
earlier conversation.

**This is the owner's workflow**: it changes only with the owner's OK.
The owner, 2026-11-09, after 2.0.2's cost was measured part-way (15
sessions and about 54,000 words of plans, prompts and reviews for 173
shipped lines, five of its thirteen steps in): "I agree it is too
expensive to run"; maintenance should be simplified "so that it
basically just safely updates libraries as needed", with "the startos
sdk, CLI, and related startos packaging things", "in a simple way";
and "I do like my concept of having a lead session in Claude Code that
puts things on the board and then assigns sub-sessions and turns on
remote so I can just do maintenance on the go." So the lead, the board, the sub-sessions and
Remote Control stay, and the work runs in **lanes**: one sub-session
for each kind of work, not one for each issue. This replaces the
numbered sub-sessions of 2026-11-04.

Every other rule this file names lives where it points. If anything
here seems to differ from `AGENTS.md`, `AGENTS.md` wins: fix this file
by pull request.

## What maintenance means

- **2.0 is the final stable release** (the owner, 2026-10-31, #869): no
  new features. The work is updates, bug fixes and security fixes. A
  feature request is an idea, never a promise
  (`docs/HOW-CHANGES-FLOW.md`, "Bugs and security").
- **Stable through the tax season** (the owner, 2026-11-09: "I want
  this 2.0 to run stable for a while. Probably this entire tax
  season"): see "Releases".
- **The order of work:** a security problem or a `tax-figures` bug
  first, then outside reports (each answered within a week), then
  updates, then other bugs.

## Where things live

| What | Where |
|---|---|
| The maintenance plan, the owner's decisions | #869 and its comments |
| The lead's kickoff, kept current | #869's comment "Kickoff prompt for the lead session" |
| Where things stand, what's next | pinned #41, "Where we are" |
| A cycle's lanes, their state, "ready: #N" | the cycle's issue ("Maintenance · 2026-12"), and the board |
| A release's checklist | the release's issue |
| What waits on the owner | issues labelled `owner`, and #41 |
| What the watchers found | the Monday report issue, and `start9` issues (`docs/MAINTENANCE.md`, "Scheduled checks") |
| Messages with Silas | the mailbox: issues labelled `for-claude` or `for-silas` in DigiMonk73/mac-mini-setup |

## Starting as lead

1. Read this file, then #869's kickoff comment, then #41. Post on #869
   that you have ("Lead · maintenance after <release>: started, kickoff
   read"), and tell the outgoing lead, named in the kickoff. After a
   compaction, re-read the kickoff and #869's latest comments first.
2. Do what `AGENTS.md`'s "Starting a session" says, in its order: what
   ran since the last session, told to the owner in plain words, red
   fixed first.
3. Then the lead's own look: the open pull requests (Dependabot's among
   them), the open `tax-figures` and `start9` issues, the Security tab,
   the week's Monday report, the mailbox (`gh issue list -R
   DigiMonk73/mac-mini-setup --label for-claude`), and the sessions
   still running.
4. Carry on from the kickoff's "Next".

## The cycle: three lanes

About once a month, after Dependabot's run, the lead runs a cycle. A
cycle has at most three lanes, and a lane with nothing in it is left
out:

| Lane | What goes in it | Its pull requests |
|---|---|---|
| **Updates** | Dependabot's pull requests, the Docker base images, any other library | Dependabot's own, each reviewed as `docs/MAINTENANCE.md` says ("Before a Dependabot pull request merges"); what Dependabot can't do, in one pull request of the lane's own |
| **StartOS** | start-sdk, start-cli, start-registry, Start9's packaging guide, a new StartOS to support: the open `start9` issues | one pull request (`startos/AGENTS.md`, `docs/START9.md`); it waits for the owner's "merge" |
| **Fix** | bugs, a `tax-figures` or security one first | one pull request for each `tax-figures` or security fix; other bugs may share one |

How a cycle runs:

1. **The lead opens the cycle's issue**: each lane, its items (the
   issues and pull requests, by number), and anything the owner must
   decide, in plain words with one recommendation. It puts one card for
   each lane on the board. It writes no plan and no kickoff prompt for
   a lane: the brief below is the kickoff.
2. **The owner says "start the cycle"**, typed in the desktop app's own
   window. The app starts a session only on the owner's own words, and
   a start asked for over Remote Control was refused (2026-11-02). The
   lead then starts one session for each lane, named "<cycle> · <lane>"
   ("2026-12 · Updates"), each from `develop` in a working folder of
   its own (`make sync-check` first, then `develop` as the folder's
   base), and turns Remote Control on for each. An idle session loses
   Remote Control: the lead wakes it with a message, then turns it on
   again.
3. **Lanes run one at a time unless the lead says otherwise**, never
   more than two at once (#869), and two only when they share no file
   but the CHANGELOG. Before each start the lead checks the plan's
   usage, and starts nothing the usage left can't finish.
4. **A lane reports "ready: #N"** to the lead and on the cycle's issue,
   and never turns on auto-merge. The lead checks the pull request and
   its diff (a session's report is a claim), that the review is posted
   with nothing open, and that the owner's words are quoted where they
   are needed; then it turns on auto-merge, one pull request at a time
   (`develop` asks each to be up to date).
5. **The lead closes the cycle**: it archives each finished session,
   removes its folder if clean (`git worktree remove`), runs `make
   sync-check`, and brings #41 up to date. What merged waits on
   `develop` for the next release.

### The lane brief

Every lane session gets this brief, the lane's name and the cycle's
issue, and nothing else:

1. `git fetch origin`, then `git merge --ff-only origin/develop`.
2. Read the cycle's issue for your lane's items. `AGENTS.md` is already
   loaded: read the docs it names for the files you will touch, and no
   others.
3. Post one checklist comment on the cycle's issue, and keep its first
   line current ("Now: …"), so a session cut off can be carried on from
   it.
4. Do the work. A bug fix starts with a test that fails on the old
   code. Commit at each point the work could be carried on from; push
   when there is something to review (each push runs every CI job), as
   a draft pull request filled in from its template.
5. Run `make test-fast`, and the checks `AGENTS.md`'s "Reviews" asks
   for the kind of change.
6. Have a fresh Claude reviewer go through it, as "Reviews" says for
   the kind of change, posted on the pull request as one comment,
   findings only. Fix each finding or answer it there.
7. Report "ready: #N" to the lead and on the cycle's issue. Never turn
   on auto-merge.
8. End as `AGENTS.md`'s "Ending a session" says, with only your own
   lines on #41.

A lane stops and tells the lead when it meets something only the owner
can decide, a figure that moves, or work that has outgrown its lane.

### Which model

The owner, 2026-11-09: "have the lead always be Fable 5.2 High and
… use opus 5.5 sub sessions when appropriate"; and of Fable 5.2, "I
want every session to have the liberty to use it but to make a
judgement about when."

- **The lead runs on Fable 5.2 at high effort**, always.
- **A lane session runs on Opus 5.5 unless there is a reason for
  Fable 5.2.** The Updates and StartOS lanes are routine work with long
  waits: Opus 5.5.
- **Any session may use Fable 5.2 where its own judgement says the work
  needs it**, for itself or for a reviewer it starts. The cases that
  usually do: a change that can move a tax figure, and above all its
  fresh review; a fix whose reviews keep finding new edges; a decision
  with no precedent in the code or the docs. The lead names the model
  on each lane's card and may recommend Fable 5.2 for one; a session
  that finds its work harder than its card says tells the lead instead
  of pressing on.
- **Whoever chooses Fable 5.2 for a sub-session or a review says why in
  one line**, on the card or the pull request, so the owner sees what
  the extra cost bought.
- Never a Sonnet or a Haiku for code or for a review.

### Who talks to whom

Every lane reports to the lead: its questions, its "ready" and its
results. The owner talks mainly to the lead. A lane talks to the owner
only when the owner talks to it, or when only the owner can answer, and
then it tells the lead too. The lead brings the owner what needs them
in plain words, with one recommendation, and collects what can wait
into one list on the cycle's issue instead of asking one thing at a
time.

### The board

The owner follows the work on GitHub Projects. Each cycle's lanes, and
each release, go on the board as cards with a status: planned, in
progress, ready, merged. The lead adds and moves them. The board is a
view, never the source: the issues and their pull requests hold the
state, and a card changes only to follow them. Which board it is, the
owner decides: the lead doesn't create a board or change its fields
without the owner's go.

## Releases

Cycles collect work on `develop`; a release sends it to users
(`docs/RELEASING.md`). A release is its own short job, run by the lead
with one release session: the version pull request, the release tests
on the StartOS test machine and the fresh docs read, then the owner's
"merge and go".

- **When:** about every three months; a `tax-figures` or security fix
  as soon as it's ready; and each January, the new tax year's final IRS
  forms (the shipped draft of a year stops on January 1 after it:
  `backend/services/reports/draft_forms.py`).
- **The tax season:** from the January forms release until after the
  April filing deadline, nothing is released but a `tax-figures` or
  security fix. Cycles go on, so nothing piles up.
- **The StartOS test machine runs for a release**, as
  `docs/RELEASING.md` says, never for a lane or a single pull request:
  a lane's pull request stands on CI. A new StartOS version is tried
  there at the next release, or sooner when it is the reason for one.
- A new tax year's forms, or a big Start9 change, may be too much for
  one session: then it is big work (`docs/BIG-WORK.md`), and the lead
  says so to the owner first.

## Reviews and the figures rule

The review scale and the figures rule are `AGENTS.md`'s "Reviews": read
them there. They are the part of this system that protects the owner's
tax figures and other people's, and nothing here loosens them. The lead
queues nothing whose review isn't posted.

## What always needs the owner

- "start the cycle", and any session started outside one;
- a release, and the StartOS package (`startos/`): the owner's "merge";
- anything sent to Start9, before it's sent, answers on Start9's fork
  included;
- a figure moved on purpose: the owner approves its plain-words
  before-and-after, never the code;
- a change in what the app does, agreed before it's written;
- the landing page's words, seen before they go live
  (`docs/RELEASING.md`, step 5);
- an outside pull request's CI, approved each time
  (`docs/HOW-CHANGES-FLOW.md`, "Pull requests");
- a click only the owner can make, such as a ruleset;
- a password or a two-factor code (the Mac mini's house rule 5).

Bring each in plain words, with one recommendation. Quote the owner's
answer, dated, on the issue or pull request it decides.

## When a fix keeps finding new edges

#824 and #849 (2.0.1): draft #906 went through six fresh reviews. Each
one found another path where the fix moved a figure outside the bug's
case, and the last was caused by a fix. So when a fix's reviews find a
new edge three rounds in a row, its session stops and reports to the
lead, and the lead brings the owner the simpler choice, in plain words,
with what it costs, instead of patching on. There it was closing #824
and #849 with no code change (the owner, 2026-11-04: "Close, no code
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

Each release ends with a new lead (the owner, 2026-11-04), so no lead's
conversation grows too long and this file is tested by a session that
knows nothing else. Between releases the same lead runs the cycles; if
its conversation grows too long first, it hands over the same way. Once
the release is out and sent to Start9 (`docs/RELEASING.md`, its last
step), the outgoing lead:

1. **Rewrites #41** for the next lead, dated.
2. **Edits #869's comment "Kickoff prompt for the lead session"** in
   place: one comment, never a new snapshot. It is the new lead's
   brief: read `docs/MAINTENANCE-LEAD.md`; the current state as
   pointers (the release just made, the outgoing lead's session name,
   any session still working with its issue and pull request, the
   board, what waits on the owner); and what's next.
3. **Proposes the new lead** as a session card, named by its release:
   "Lead · maintenance after <release>", on Fable 5.2 at high effort.
   The app starts a session only on the owner's own words, so the owner
   clicks the card or says "start it". The outgoing lead then ends its
   turn: it never waits or polls.
4. **Archives itself** when the new lead's message says it started and
   read the kickoff, after archiving its finished sessions and removing
   their clean folders. A session still working is handed over in the
   kickoff, not archived. It ends as "Ending a session" says, with
   **Git: in sync**.
