# AGENTS.md

This is a StartOS service-package repository — it builds a `.s9pk` for StartOS.

Develop it inside a StartOS packaging workspace created by `start-cli s9pk init-workspace`,
which provides the packaging guide and agent context one level up. If you're reading this in a
bare clone with no workspace, the full guide is at <https://docs.start9.com/packaging>.

## This repo

- **Two homes.** The package is developed in `startos/` of
  [DigiMonk73/BTCTX-MCP](https://github.com/DigiMonk73/BTCTX-MCP) (by pull request into `develop`),
  mirrored to [DigiMonk73/BTCTX-StartOS](https://github.com/DigiMonk73/BTCTX-StartOS),
  and reaches [Start9-Community/BTCTX-StartOS](https://github.com/Start9-Community/BTCTX-StartOS)
  only as a pull request from that mirror. A change made on the Start9 fork must be
  taken back with BTCTX-MCP's `scripts/start9-pull.sh` before the next mirror sync,
  or the sync undoes it (BTCTX-MCP's `docs/STARTOS-PACKAGE.md`, "After Start9 forks
  the mirror"). The app's side of the contract with this
  package (its CLI, paths and variables) is BTCTX-MCP's `docs/STARTOS_COMPATIBILITY.md`.
- **Ids are frozen:** package `btctx`, host `ui-multi`, interfaces `webui` and `mcp`,
  actions `price-source`, `set-credentials`, `recalculate-ledger` and `connect-ai`,
  volumes `main` and `startos`. Sideloaded installs from 0.3.x on depend on them.
- **The package version is `<VERSION>:<revision>`**, `<VERSION>` being BTCTX-MCP's
  root `VERSION` file and the image tag `v<VERSION>`. `down` stays `IMPOSSIBLE`: an
  older app refuses a newer database.
- **Never translate the app's own screen names** (`Settings > Ledger Review`) anywhere
  the package is translated (the i18n dictionaries, the release notes in `versions/`,
  the store listing): the app is English-only, so a translated name points at a screen
  that doesn't exist.
- **Release notes** (`versions/`) keep Start9's rule
  ([Versions](https://docs.start9.com/packaging/versions.html), "Release Notes"), never
  restated here, and add ours: each `tax-figures` fix (BTCTX-MCP's label for a figure
  that could be wrong) says what the user saw, which tax years and what to do, never
  which BitcoinTX versions had it; with every new `VERSION`, the AI connector's new
  version, as BitcoinTX's Settings > Connect an AI Assistant gives it; last, the
  CHANGELOG link. BTCTX-MCP's `backend/tests/test_startos_updating_915.py` checks the
  notes for an issue number, the SDK or start-cli, and a StartOS version.
- **Checks:** `npm run format:check && rm -rf javascript && make javascript/index.js && node scripts/check-manifest.mjs`
  (`make` type-checks, lints and bundles; from start-sdk 3.1.0 it formats
  instead of checking, so the format check comes first).
