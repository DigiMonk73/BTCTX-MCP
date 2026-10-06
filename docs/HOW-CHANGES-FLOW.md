# How changes flow

The whole path a change takes, from this computer to GitHub, to a release,
to Start9's app store, and back. Written for the owner, who isn't a
professional coder, and for every AI session, so both remember it the same
way. The detailed rules are in `AGENTS.md` ("Branches", "Releasing",
"Start9"); this page is the map.

## The picture

Our changes go **out**:

```
this computer ──push──▶ short branch ──pull request──▶ develop ──release──▶ main
      main ──release copies startos/──▶ mirror ──pull request──▶ Start9's copy
      Start9's copy ──Start9 merges──▶ Community Beta ──owner asks──▶ main store
```

Start9's changes come **back**:

```
Start9's copy ──scripts/start9-pull.sh──▶ short branch ──pull request──▶ develop
      (then they go out again with our next release)
```

## The three repositories

| Repository | What it is | Who changes it |
|---|---|---|
| **DigiMonk73/BTCTX-MCP** (this one) | The source of truth: the app, the AI connector, the Mac app, and the StartOS package in `startos/` | Us, only by pull request into `develop` |
| **DigiMonk73/BTCTX-StartOS** (the mirror) | A copy of `startos/` and nothing else, made at each release | Only the release (a script). Never edit it by hand |
| **Start9-Community/BTCTX-StartOS** (Start9's copy) | What Start9 builds and publishes in their app store | Only Start9. We send pull requests; they merge |

So Start9's copy decides what is *in their app store*. Everything else,
including our own changes to the StartOS package, starts here.

## Our branches

- **`develop`**: where all work lands, by pull request.
- **`main`**: released code only. It moves only by catching up with
  `develop` at a release (or when only docs, tests or tooling changed).
  Never pulled from Start9.
- **Short branches**: one per change (`claude/...`), deleted by GitHub
  when its pull request merges.

## 1. An everyday change

1. Claude works on this computer, in its own folder (a "worktree"), and
   runs the tests.
2. Claude pushes a short branch to GitHub and opens a pull request into
   `develop`.
3. GitHub runs the full set of tests. A fresh Claude reviewer reads the
   change; Claude fixes what it finds.
4. The pull request merges into `develop`:
   - **ordinary changes** merge by themselves once the tests pass
     (auto-merge);
   - **tax figures, the database, the StartOS package, anything that goes
     to Start9, and releases** wait for the owner to say **"merge"**.

## 2. A release

1. A pull request into `develop` raises the version number everywhere.
2. `main` catches up with `develop` (a fast-forward: no new commits on
   `main` itself).
3. A `release/vX.Y.Z` branch starts the release on GitHub. It builds the
   Docker image, the Mac app and the StartOS package, publishes the AI
   connector, and creates the GitHub release.
4. The release copies `startos/` to the mirror and opens an issue here:
   **"Send vX.Y.Z to Start9"**.

## 3. Sending a release to Start9

1. Open the "Send vX.Y.Z to Start9" issue and click its link. GitHub shows
   a ready pull request from the mirror to Start9's copy.
2. Click **Create pull request**. Only Start9 can change their copy, so a
   pull request is the only way in.
3. Start9 reviews and merges it. Their merge goes to **Community Beta**
   (`https://community-beta-registry.start9.com`).
4. The owner tests the beta on their own server (a checklist in
   `docs/temp/`), then asks Start9, in an issue on their copy, to
   **promote** it to the main store (`https://community-registry.start9.com`).
   Claude drafts that request. Promotion is the owner's call.

## 4. When Start9 changes their copy

Start9 sometimes changes the package themselves: a review (like
2026-10-05's), template updates about monthly, SDK updates.

1. Claude runs `scripts/start9-pull.sh --apply` on a short branch. It
   copies their changes into `startos/` here.
2. Claude checks and tests it, and opens a pull request into `develop`
   (never straight into `main`).
3. Their change then goes out with our next release (sections 2 and 3),
   so the two copies match again.

**This must happen before our next release**, or our copy would undo their
work. The release checks it and stops if it was skipped.

## 5. Keeping this computer and GitHub the same

- `make sync-check` answers "is everything on this computer also on
  GitHub?". It ends with **IN SYNC** or **NOT IN SYNC** and a list.
- Every session runs it when it starts and when it ends, and Claude's last
  message ends with **"Git: in sync"** (or what isn't, and why).
- At the end, Claude also tidies up: `scripts/sync-check.sh --tidy`
  deletes branches whose work is on GitHub, and Claude removes old session
  folders that are clean and whose pull request merged.

## The rules that keep it safe

1. Every change goes into `develop` by pull request. Never commit on
   `main`.
2. `main` comes only from our own `develop`, never from Start9.
3. Never edit the mirror by hand: it's a copy, overwritten at each release.
4. Start9's changes come back through `develop` before our next release.
5. Their copy changes only by their merge: we send pull requests.
6. Nothing stays only on this computer at the end of a session.
