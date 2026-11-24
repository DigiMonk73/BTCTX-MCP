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
- **Checks:** `npm run format:check && rm -rf javascript && make javascript/index.js && node scripts/check-manifest.mjs`
  (`make` type-checks, lints and bundles; from start-sdk 3.1.0 it formats
  instead of checking, so the format check comes first).

## Release notes

The notes in `startos/versions/` follow Start9's
[Versions](https://docs.start9.com/packaging/versions.html) page, "Release Notes":
say what a user observes, never how it was done.

- A feature, or a fix by its symptom, and what to do. Never the mechanism, an SDK or
  dependency bump, an issue number or a defect's history ("introduced in…"), and
  never the minimum StartOS: only a server that already meets it is offered the update.
- Every instruction is one a user carries out from StartOS or from BitcoinTX itself.
- Ours, within that: each `tax-figures` fix (BTCTX-MCP's label for a figure that could
  be wrong) is told by what the user sees: what was wrong, which tax years, what to do.
  With every new `VERSION`, the AI connector's new version, as BitcoinTX's Settings >
  Connect an AI Assistant gives it. The notes end with the CHANGELOG link.

BTCTX-MCP's `backend/tests/test_startos_updating_915.py` checks every version after
2.0.2:0 for an issue number, the SDK or start-cli, and a StartOS version.
