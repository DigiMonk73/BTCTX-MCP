# How changes flow

The whole path a change takes, from this computer to GitHub, to a release,
to Start9's app store, and back. Written for the owner, who isn't a
professional coder, and for every AI session, so both remember it the same
way. The detailed rules are in `AGENTS.md` ("Branches", "Releasing",
"Start9", "Pull requests"); this page is the map. Words in *italics* are in
the glossary at the end.

## The picture

Our changes go **out**:

```
this computer ──push──▶ short branch ──pull request──▶ develop
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

- **`develop`**: where all work lands, by pull request.
- **`main`**: released code only, what users get. It moves only by
  *fast-forwarding* to `develop`: at a release, or when everything new is
  only docs, tests or tooling. Never pulled from Start9.
- **Short branches**: one per change (`claude/...`), deleted by GitHub
  when its pull request merges.

## 1. An everyday change

1. A change in what the app does for the owner is agreed with them
   before it's written.
2. Claude works on this computer, in its own folder (a *worktree*), and
   runs the tests.
3. Claude pushes a short branch to GitHub and opens a pull request into
   `develop`.
4. GitHub runs the full set of tests. A fresh Claude reviewer reads the
   change; Claude fixes what it finds, or answers it on the pull request.
5. Once the review has nothing open:
   - **ordinary changes**: Claude turns on *auto-merge*, and GitHub merges
     it when the tests pass;
   - **tax figures or what the app computes, the database, the StartOS
     package, anything that goes to Start9, and releases**: they wait for
     the owner to say **"merge"**.

## 2. A release

1. A pull request into `develop` raises the version number everywhere and
   moves the CHANGELOG's "Unreleased" part under the new version.
2. When it has merged and the tests pass on `develop`, an AI agent runs the
   release tests (`docs/AGENT-TESTS.md`) on a StartOS test machine. A
   blocker failure stops the release.
3. `main` catches up with `develop`. That publishes the Docker image
   (`ghcr.io/digimonk73/btctx-mcp:vX.Y.Z`).
4. A `release/vX.Y.Z` branch starts the release on GitHub. It:
   - checks first that Start9's own changes are back in `startos/`
     (section 4), and stops if not;
   - builds the Mac app and the StartOS package (and the Docker image, if
     step 3 hasn't yet);
   - publishes the AI connector to PyPI (not for a package-only fix, a
     version like `v1.2.4-1`);
   - creates the GitHub release with everything attached;
   - copies `startos/` to the mirror (if the `MIRROR_TOKEN` secret is set).
5. Delete the `release/vX.Y.Z` branch afterwards.

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
   Claude writes in `docs/temp/` for that release (deleted when done).
5. When satisfied, the owner asks Start9, in an issue on their copy, to
   **promote** it to the main store (`https://community-registry.start9.com`).
   Claude drafts that request. Promotion is the owner's call.

**Docs-only changes to `startos/` between releases** don't wait: `main`
catches up, the mirror is synced right away, and that too needs a pull
request to Start9's copy (or rides in one of ours still open there).

## 4. When Start9 changes their copy

Start9 sometimes changes the package themselves: a review (like
[their review of 2026-10-05](https://github.com/Start9-Community/BTCTX-StartOS/pull/1),
brought back in #48), template updates about monthly, *SDK* updates.

1. Claude runs `scripts/start9-pull.sh --apply` on a short branch. It
   copies their changes into `startos/` here.
2. Claude checks and tests it, and opens a pull request into `develop`
   (never straight into `main`).
3. Their change then goes out with our next release (sections 2 and 3),
   so the two copies match again.

**This must happen before our next release or mirror sync**, or our copy
would undo their work. Both check it and stop if it was skipped.

## 5. Keeping this computer and GitHub the same

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

1. Every change goes into `develop` by pull request. Never commit on
   `main`.
2. `main` comes only from our own `develop`, never from Start9.
3. Never edit the mirror by hand: it's a copy, overwritten by each sync.
4. Start9's changes come back through `develop` before our next release.
5. Their copy changes only by their merge: we send pull requests.
6. Nothing stays only on this computer at the end of a session.

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
