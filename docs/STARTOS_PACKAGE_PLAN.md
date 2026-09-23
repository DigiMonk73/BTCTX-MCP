# StartOS package in the main repo — design plan

Status: **proposal for review** (nothing built yet). Date: 2026-09-23.

Goal: build the StartOS package (`btctx.s9pk`) from this repository, next to
the macOS app and the Docker image, using everything the current StartOS SDK
offers, closing the gaps found against Start9's own packages. Then mirror the
package into `DigiMonk73/BTCTX-StartOS` so it can go to the Start9 community
marketplace later.

Research behind this plan (sources cited there, file/line level):
- SDK capabilities: start-sdk 2.0.9 source + CHANGELOG, Start9's packaging
  guide (`start-technologies` branches `start-sdk/v2.0.9`, `live-docs`, `master`).
- 17 current Start9Labs packages (actual-budget, vaultwarden, nextcloud,
  filebrowser, lnbits, uptime-kuma, immich, btcpayserver, mempool, …), the
  hello-world template, and 3 apps that package StartOS in their own repo
  (epochbtc/satd, mmalmi/nostr-vpn, heatpunk/blisspoint).

---

## 1. Where the StartOS platform is now

| | Version | Notes |
|---|---|---|
| StartOS (stable) | 0.4.0.1 | services run in LXC containers; the Docker image is converted to a squashfs at pack time |
| start-sdk on npm | **2.0.9** (declares StartOS ≥ 0.4.0-beta.10) | what every Start9 package pins, exactly |
| Start9 docs (`live-docs`) | describe SDK 2.0.10 | not on npm yet |
| start-sdk `master` | 3.0.0, unreleased, targets StartOS 0.4.0.2 | breaking: `emulateMissing`, `z.looseObject`, `sdk.action.run` input as function |
| start-cli | 2.1.0 | packs only inside a *packaging workspace* (parent dir with `.startos/`) |

Plan: build on **2.0.9 pinned exactly**; add a weekly check that opens an
issue when npm has a newer SDK, so 2.0.10/3.0.0 are adopted deliberately.

## 2. Repository layout

```
BTCTX-MCP/
├── VERSION                      # one version for app, image, mac app, s9pk
├── Dockerfile                   # the image StartOS runs
├── backend/ frontend/ mcp_server/ desktop/
└── startos/                     # ← the StartOS package (was DigiMonk73/BTCTX-StartOS)
    ├── package.json             # pins @start9labs/start-sdk 2.0.9
    ├── Makefile                 # includes the SDK's s9pk.mk
    ├── tsconfig.json            # extends the SDK base
    ├── icon.svg  instructions.md  README.md  UPDATING.md  AGENTS.md  LICENSE
    └── startos/                 # package source (SDK convention)
        ├── manifest/ (index.ts, i18n.ts)
        ├── i18n/ (index.ts, dictionaries/)
        ├── actions/  init/  versions/  fileModels/
        ├── main.ts  interfaces.ts  backups.ts  dependencies.ts  sdk.ts  utils.ts  index.ts
```

`startos/` is self-contained (its own `package.json`/`node_modules`), so the
mirror repo is exactly `startos/` at its root.

Why not keep the separate repo as the source: one commit changes app +
package together (e.g. a schema change and its StartOS task), one version,
one release, no cross-repo tag pinning. Precedent: epochbtc/satd does exactly
this and mirrors to `satd-startos` for Start9's registry.

## 3. Image: how StartOS gets BitcoinTX

Recommendation: **`dockerTag: 'ghcr.io/digimonk73/btctx-mcp:v<VERSION>'`**,
written into the manifest from `VERSION` at build time (a tiny generated
`startos/startos/manifest/version.ts`).

- The release pipeline already builds and publishes that exact image
  (amd64 + arm64) from the same commit first, then packs the s9pk.
- The manifest is identical in the main repo and the mirror; Start9's review
  expects a package repo that *pulls* the app, not one containing it.
- Alternative (`dockerBuild` from `../Dockerfile`) works in the main repo but
  can't work in the mirror, so the two would differ. Not worth it.

Arches: `x86_64`, `aarch64` (riscv64 not built; add later if wanted).

## 4. The package — features

Legend: ✅ have today · 🆕 new · 🔧 fix

### 4.1 Interfaces
- ✅ **Web UI** — `ui`, port 80, StartOS terminates TLS.
- 🆕 **MCP API** — second interface on the same port, type `api`, path `/api`,
  so StartOS shows a copyable base URL for AI clients (LAN `.local`, IP, and
  any domain the user adds). Same app login; no extra proxy auth.

### 4.2 Startup (daemons)
- 🆕 **`migrate` oneshot** runs `python -m backend.cli migrate` (Alembic
  upgrade + seed) before the web daemon starts (`requires`). StartOS shows it
  as its own step; a long migration no longer looks like a hung web server.
  (Start9 guide: "app schema migrations belong in a oneshot".)
- 🔧 **Health check** — `checkWebUrl` on a new `GET /api/health` (DB readable,
  schema at head), not just "the page loads". `gracePeriod` sized for startup.

### 4.3 Credentials
- ✅ Random admin password generated on install.
- 🆕 **Critical install task → "Show Credentials"** (the pattern used by
  actual-budget, vaultwarden, filebrowser, nextcloud). Replaces the install
  alert that SDK 2.0 removed; the service starts once the user has seen them.
- ✅ **Reset Login Credentials** (service stopped).
- 🔧 Set the password through an app CLI (`python -m backend.cli
  set-password`) instead of the wrapper editing SQLite directly — a stable
  contract that goes through the app's own hashing and user rules.
- 🔧 Wrapper secrets move from `/data/.startos-wrapper.json` (inside the app's
  volume) to `store.json` on a separate `startos` volume the app never
  mounts (current Start9 docs). A version migration moves existing installs.

### 4.4 Actions
| Action | Status | What it does |
|---|---|---|
| Show Credentials | ✅ | username + password (masked, copyable) |
| Reset Login Credentials | ✅ | new random password (only when stopped) |
| **Connect an AI Assistant** | 🆕 | the MCP base URL(s), username, password, StartOS root CA (copyable PEM), a ready-to-paste Claude Desktop JSON and `claude mcp add …` command. Turns the fiddliest setup step into copy-paste. |
| **Recalculate Ledger** | 🆕 | runs the app's recalculation (`python -m backend.cli recalculate`); also the target of the post-update task |

### 4.5 Tasks (prompts in the StartOS UI)
- 🆕 Install → **critical** "Show Credentials".
- 🆕 Update from any version before 0.8.0 → **important** "Recalculate
  Ledger" (calculation fixes in 0.8.0 only reach old data after a recalc).
  Today that's only a sentence in release notes.

### 4.6 Backups
- ✅ `Backups.ofVolumes('main', 'startos')`. StartOS stops the service before
  backing up, so the SQLite file is consistent — no snapshot hook needed
  (confirmed in SDK source and every SQLite-based Start9 package).
- 🔧 App keeps only the newest N pre-upgrade copies in `/data/backups/`
  (they are also inside every StartOS backup).

### 4.7 Versions and upgrades
- Same package id **`btctx`**: installs of the old BTCTX-StartOS package
  update in place.
- 🔧 Version graph pruned to the Start9 convention: `current.ts` plus only
  versions whose migration does real work. **`down: IMPOSSIBLE`** — today's
  empty `down` would let a user downgrade onto a database the newer app has
  already migrated (the app would then refuse to start).
- Versioning: `<VERSION>:<wrapper revision>` (e.g. `0.9.0:0`); a
  packaging-only change bumps the revision.

### 4.8 Presentation and docs (Start9 review checklist)
- 🔧 `icon.svg` ≤ 40 KiB (ours is a 545 KB raster inside an SVG).
- 🆕 i18n: `manifest/i18n.ts` + `i18n/` dictionary; en_US complete and
  es_ES/de_DE/pl_PL/fr_FR (Start9 checks localization).
- 🔧 `instructions.md` with the `## Documentation` link list Start9's
  support indexer parses; README as the AI/admin reference (no versions,
  "Quick Reference for AI Consumers"); `UPDATING.md`; `AGENTS.md`.
- `license: 'MIT'` (SPDX).

### 4.9 App-side changes this needs (in BTCTX-MCP)
1. `GET /api/health` (no auth): DB reachable, schema at head, version.
2. `LOG_LEVEL` env, default INFO (today DEBUG floods StartOS's log viewer).
3. `python -m backend.cli` with `migrate`, `set-password`, `recalculate`.
4. Retention for `/data/backups/` (keep newest 5).

## 5. Signing

Every package release so far was signed with a fresh throwaway key.
StartOS doesn't appear to reject that for sideloads (read from code, not
tested on a device), but a registry only accepts publishes from the
package's authorized signer, and Start9's CI signs with a fixed `DEV_KEY`.

Plan: one stable developer key, stored as the GitHub secret `DEV_KEY` in
BTCTX-MCP (and in BTCTX-StartOS if it ever builds). **You create the
secret** (I can't set repository secrets from here); I'll give you the
two commands.

## 6. Build and release pipeline (one repo)

- **CI (every push):** existing jobs + a `startos` job: `npm ci`, `tsc`,
  the SDK's lint, bundle, and a manifest check (id `btctx`, version matches
  `VERSION`, arches, no removed fields). No pack here (needs the released image).
- **Release (push `release/vX.Y.Z`):**
  1. image → `ghcr.io/digimonk73/btctx-mcp:vX.Y.Z` (amd64 + arm64)
  2. macOS app → `BitcoinTX-macOS.zip` (later: signed/notarized `.dmg`)
  3. s9pk → packaging workspace (`start-cli s9pk init-workspace`),
     `make universal`, signed with `DEV_KEY`, then `start-cli s9pk inspect`
     sanity check
  4. one GitHub release with the zip, `btctx.s9pk`, and CHANGELOG notes
  5. mirror (below)

## 7. Mirror to DigiMonk73/BTCTX-StartOS

A workflow copies `startos/` to the mirror's root and pushes it, with a
commit message pointing at the source commit. Needs a fine-grained token
with write access to BTCTX-StartOS as a secret (`MIRROR_TOKEN`) — you create
it. Fallback: a `scripts/sync-startos-mirror.sh` you run by hand (satd's
approach). The mirror keeps its own release workflow so it can build on its
own if Start9 forks it.

Marketplace path (when you want it): email submissions@start9.com a link
to BTCTX-StartOS; Start9 forks it into Start9-Community, reviews via PR,
builds to community-beta; you ask to promote to the community registry.

## 8. Build order

1. App-side changes (4.9) + tests. Release as part of the next version.
2. Move the package into `startos/`, adopt the Start9 layout (i18n, docs,
   pruned versions, `down: IMPOSSIBLE`, store volume + migration).
3. New features: MCP interface, migrate oneshot + health, install/update
   tasks, Connect an AI Assistant, Recalculate Ledger.
4. Pipeline: CI job, release job, `DEV_KEY` signing, mirror.
5. Verify on a real StartOS (you): fresh install, update from 0.8.0:1,
   backup + restore, uninstall/reinstall, MCP connection from a laptop.
6. Archive the old wrapper history note in BTCTX-StartOS's README.

Each step lands on a branch with CI green before merging.

## 9. Decisions for you

1. **Minimum StartOS: 0.4.0-beta.10.** What does your server run?
2. **Icon:** (a) I draw a clean vector BitcoinTX icon (≤ 40 KiB), or (b) a
   downsized copy of today's logo embedded in the SVG. Recommend (a).
3. **Translations:** machine-quality es/de/pl/fr now (fixable later), or
   English only until a marketplace submission. Recommend now — Start9 checks.
4. **Secrets you create:** `DEV_KEY` (signing) and `MIRROR_TOKEN` (mirror).
   OK to set these up?
5. **Pre-upgrade copies:** keep the newest 5 and include them in StartOS
   backups (recommended), or exclude `/data/backups/` from backups.
6. **Mac app:** keep the zip for now, or add a `.dmg` (unsigned until you
   have an Apple Developer ID).

## 10. Not verified yet (tested during step 5)
- `sdk.getSslCertificate` inside an action (for the root CA in "Connect an
  AI Assistant"); fallback: show the StartOS "Download Root CA" path.
- Sideloaded updates across signing keys.
- MCP from a laptop through the StartOS proxy end to end.
