# Releasing

Read before any release step, and before `main` moves. 2.0.0 is
released (2026-10-31), so the paragraph on 2.0's pre-releases and its
release is history, kept as it was.

Moved word for word from `AGENTS.md` on 2026-11-04 (#903); `AGENTS.md`
now keeps a map of where each part lives. Where the text below says
"this file", it means `AGENTS.md` and the files its map names, and a
section named in quotes ("Branches", "Reviews") is found through that
map.

## Releasing

Full steps, the package version and the signing/mirror secrets:
`startos/UPDATING.md`. In short:

2.0's pre-releases and its release follow `docs/temp/2.0-accounts.md`,
7.4's B10a and B10b: their version bumps go into `2.0`, not
`develop`; a pre-release, an alpha and later a beta (#251's decision
28), is published from `prerelease/v2.0.0-alpha.N` or
`prerelease/v2.0.0-beta.N`; and for the release, `develop` takes
nothing from the last `develop` merge until `2.0` is in it. A
pre-release's `VERSION` is `2.0.0-alpha.N` or `2.0.0-beta.N`, its
`current.ts` the same with `:0` (never a package-only revision: a fix
is the next pre-release), and `release.yml` publishes it as `release/`
does a release, but as a GitHub pre-release (the Mac app "BitcoinTX
Preview", the image's own tag only, the connector `btctx-mcp==2.0.0aN`
or `2.0.0bN`), with no mirror and no Start9 step:
`scripts/release-version.sh`, `image-tags.sh` and `mac-app.sh` hold
the rules.

1. In a pull request of its own into `develop` ("Branches"): bump
   `VERSION`, the version in
   `desktop/BitcoinTX.spec`, the image tag in
   `startos/startos/manifest/index.ts`, `startos/startos/versions/current.ts`
   and `mcp_server/pyproject.toml` (`backend/tests/test_versions_agree.py`
   fails until they agree), and run `make prices` (the hourly price
   history's new hours; the release refuses one more than 14 days old).
   Move the CHANGELOG's Unreleased section to the
   version and clear the ticked items from `docs/ROADMAP.md`. Minor bump
   when a new tax year's forms are added. The StartOS release notes
   (`current.ts`) repeat each `tax-figures` fix: what was wrong, which tax
   years, what to do. Once it has merged, wait for CI on
   `develop`. Run `docs/AGENT-TESTS.md` (an agent on a StartOS VM) on that
   commit's CI artifacts; a blocker FAIL stops the release. Meanwhile a
   fresh Claude, one that didn't write the release, reads every doc
   against what it ships (owner's rule, 2026-10-10): the READMEs,
   `startos/instructions.md`, the store descriptions
   (`startos/startos/manifest/i18n.ts`), the actions' text
   (`startos/startos/i18n/dictionaries/`), `mcp_server/AI_SETUP.md` and
   the AI guide (`guide.py`), `docs/`, `SECURITY.md`, the app's on-screen
   text (Settings, the form hints, `frontend/src/utils/aiSetup.ts`), and
   the CHANGELOG's new section against the pull requests merged since the
   last release, with the StartOS release notes (`current.ts`) against
   it. Anything stale is fixed by pull request before step 2: nothing is
   released, or sent to Start9, with stale docs. Such a fix changes
   wording only, so the agent tests aren't run again; a change to what
   the app or the connector does isn't a docs fix.
2. Fast-forward `main` to GitHub's `develop` ("Branches") and push: `.github/workflows/image.yml`
   publishes `ghcr.io/digimonk73/btctx-mcp:vX.Y.Z` (never overwritten) and
   `:main`.
3. Push a branch `release/vX.Y.Z` from `main`, and delete it once the
   release is out: `.github/workflows/release.yml` builds the
   macOS `.dmg` + `.zip` and `btctx.s9pk` (signed with the `DEV_KEY` secret if
   set), publishes the AI connector to PyPI as `btctx-mcp==X.Y.Z` (trusted
   publishing, GitHub environment `pypi`, no token; skipped for `-N`
   revisions), creates the tag and one GitHub release (with `SHA256SUMS` of
   its files and a GitHub build attestation of each: once it's out, check
   one file with `gh attestation verify`, as the README shows), and pushes
   `startos/` to DigiMonk73/BTCTX-StartOS's `main` if the `MIRROR_TOKEN`
   secret is set.
   There, Start9's Tag and Release workflow tags it `v<upstream>_<revision>`
   and releases it (needs the mirror's `DEV_KEY` secret and
   `REFERENCE_REGISTRY` variable).
4. Once Start9 has forked the mirror, a release reaches them **only as a
   pull request** from the mirror's `main` to their fork: nobody but Start9
   can change the fork, and the mirror is never edited by hand. The release
   run opens an issue here, "Send vX.Y.Z to Start9", with the one-click link
   and steps for the owner; or open it yourself with the owner's OK
   (`gh pr create -R <fork> --head DigiMonk73:main`, the fork from
   `scripts/start9-pull.sh --fork`). While a pull request of ours is still
   open there, it carries the new release too, and no issue is opened.
5. Check the landing page (DigiMonk73/btctx-site: `index.html`, screenshots in `img/`). Its
   download buttons, release-notes link and Docker `:latest` follow the
   release by themselves; its words don't. Update what the release made
   wrong (action names, StartOS steps, features) in a commit there, shown
   to the owner first: it's public. The pictures too, every release: run
   `make site-shots` (AGENT-TESTS REF-1 already took them), put the changed
   ones in `docs/images/` by pull request (the README's) and in btctx-site's
   `img/`, then fast-forward `main` to `develop` (docs only, see Branches),
   since GitHub shows the README from `main`: so the two always match.
6. **Hand over to a new lead** (the owner, 2026-11-04; this step is new
   since the move from `AGENTS.md`). Once the release is out and sent to
   Start9, the outgoing maintenance lead rewrites #41 for the next lead
   (dated), edits #869's comment "Kickoff prompt for the lead session"
   in place, proposes the new lead as a session card named by its
   release ("Lead · maintenance after <release>", for example after
   2.0.1) for the owner to start, and archives itself once the new lead
   says it has read the kickoff: `docs/MAINTENANCE-LEAD.md`, "The
   handoff at each release".

The mirror (DigiMonk73/BTCTX-StartOS) is the repo Start9 forks into
Start9-Community; their fork is then the package's upstream for the
registry. The mirror is generated: never edit it directly, change `startos/`
here. It updates at releases (plus a `next` branch kept by Start9's
`syncNext` workflow), and **stays current between them** (owner's rule): when
a change to `startos/` is docs only (its root-level `*.md`), fast-forward
`main` and run `scripts/sync-startos-mirror.sh --push` right away. The
mirror's Tag and Release ignores root-level `*.md`, so nothing is rebuilt;
check the sync's commit lists only those files. Anything else in `startos/`
(code, `icon.*`, `assets/`, workflows) waits for a release. Once Start9 has
forked, such a sync also needs its pull request to their fork (or rides in
one of ours still open), or Start9 never gets it. Before a release, bring
Start9's changes to their fork back into `startos/` with
`scripts/start9-pull.sh` (`--apply` on a branch cut from `develop`, then a
pull request into `develop`), or the sync undoes them;
the release workflow's first job stops if you haven't (`--check`). By hand: `scripts/sync-startos-mirror.sh --push`;
if the mirror's own workflow can't release,
`scripts/mirror-startos-release.sh vX.Y.Z <path to btctx.s9pk>`. If
`MIRROR_TOKEN` expires, the mirror job skips with a notice (renewal:
`startos/UPDATING.md`).
