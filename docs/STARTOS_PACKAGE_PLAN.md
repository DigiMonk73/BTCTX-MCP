# StartOS package in the main repo — design plan

Status: **approved 2026-09-23** with the decisions in section 9. **Built** on
`feature/startos-package` (steps 1-4 of section 8); step 5, testing on a real
StartOS device, is the checklist in section 11.

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
- 🆕 i18n structure (`manifest/i18n.ts` + `i18n/` dictionary), **en_US only**
  for now (decision 3); other locales can be added before a marketplace submission.
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

## 9. Decisions (made 2026-09-23)

1. **Minimum StartOS 0.4.0-beta.10** — the owner is updating the server to the
   latest StartOS. Build on start-sdk 2.0.9.
2. **Icon:** draw a proper vector BitcoinTX icon, `icon.svg` ≤ 40 KiB (don't
   wrap the existing raster logo).
3. **English only (en_US)** for now: the app produces US tax forms. Keep every
   user-facing string behind `i18n()` with an en_US dictionary so other
   locales can be added later (Start9's marketplace review checks localization;
   revisit before a submission).
4. **Secrets later:** the owner will create `DEV_KEY` and `MIRROR_TOKEN` at home.
   Until then: build and release as today (throwaway key per build; release
   still works), make the workflows use `DEV_KEY` when present and fall back to
   `start-cli s9pk init-workspace` key generation when absent, and run the mirror
   step only when `MIRROR_TOKEN` exists (plus the manual sync script). Write
   the exact setup steps for both secrets in `startos/UPDATING.md`.
5. **Pre-upgrade copies:** app keeps the newest 5 in `/data/backups/`; they are
   included in StartOS backups.
6. **macOS:** release an unsigned `.dmg` (plus the zip). Document the
   right-click → Open first-launch step for unsigned apps.

## 10. Not verified yet (tested during step 5)
- `sdk.getSslCertificate` inside an action (for the root CA in "Connect an
  AI Assistant"); fallback: show the StartOS "Download Root CA" path.
- Sideloaded updates across signing keys.
- MCP from a laptop through the StartOS proxy end to end.

## 11. Checklist for a real StartOS device (owner)

CI proves the package type-checks, lints, bundles, packs (x86_64 from the
image of every commit), and that every earlier version (0.3.x .. 0.8.0:1) has
an update path and no version can downgrade. Only a device can prove the rest.
Sideload `btctx.s9pk` from the release (or the `btctx-s9pk-x86_64` artifact of
a CI run) in StartOS: **Sideload** in the top bar.

**Fresh install**
- [ ] Install shows the "Creating the BitcoinTX database" step, then only the
      critical **Show Credentials** task (no Start button until it has run).
- [ ] Show Credentials shows `admin` and a 24-character password; that login
      works in the Web UI and the first-run registration page does not appear.
- [ ] Start: the **migrate** step finishes, then the "Web Interface" health
      check turns green ("BitcoinTX is ready"). Logs are INFO, not DEBUG.
- [ ] Interfaces lists **Web UI** and **MCP API**; the MCP API address ends in
      `/api`.

**MCP through the StartOS proxy (from a laptop on the LAN)**
- [ ] **Connect an AI Assistant** shows the `https://….local/api` address,
      the login, and a **Root CA certificate** (a PEM starting with
      `-----BEGIN CERTIFICATE-----`). If the certificate is missing, note it:
      `sdk.getSslCertificate` inside an action didn't work, and the message
      points to System > About this Server instead.
- [ ] Save the PEM as `btctx-root-ca.crt`; with uv installed, paste the
      Claude Desktop configuration (with the real path in `BTCTX_CA_BUNDLE`)
      or run the Claude Code command. The assistant's `get_portfolio` works
      and a previewed + added transaction appears in the Web UI.
- [ ] `curl --cacert btctx-root-ca.crt https://<name>.local/api/health`
      returns `{"status":"ok",…}` (proves the CA is the one that signs the
      service's address).

**Update from the current package (0.8.0:1)**
- [ ] With 0.8.0:1 installed and some transactions, sideload the new s9pk:
      it updates in place (also tells us whether a different signing key is
      accepted: 0.8.0:1 was signed with a throwaway key).
- [ ] Show Credentials still shows the password generated by the old package
      (moved from `/data/.startos-wrapper.json` into `store.json`).
- [ ] No Recalculate Ledger task (0.8.0 → 0.9.0 needs none).
- [ ] `/data/backups/` gained a pre-upgrade copy only if the schema changed.
- [ ] Downgrading back to 0.8.0:1 is refused.

**Update from before 0.8.0 (if a 0.7.x install or backup is available)**
- [ ] After updating, an **important** Recalculate Ledger task appears; the
      service still starts. Running the action reports "Recalculated N
      transaction(s)." and the task disappears.

**Backup and restore**
- [ ] Create a StartOS backup, uninstall, restore: transactions, login and
      Show Credentials come back; the service starts without new tasks.

**Uninstall and reinstall**
- [ ] Uninstall, install again: a new password and a new critical task, an
      empty ledger.

**Actions**
- [ ] **Recalculate Ledger** runs while running and while stopped.
- [ ] **Reset Login Credentials** (service stopped): new password works, the
      username is `admin` again, transactions intact.

## 12. Implementation notes (deviations from the plan text)

- Version sources are literals checked by `backend/tests/test_versions_agree.py`
  and `startos/scripts/check-manifest.mjs` instead of a generated
  `version.ts`: the mirror needs no generator, and a VERSION bump fails the
  tests until `current.ts` is updated deliberately (so its migration isn't
  silently re-labelled).
- Version graph: `current` (0.9.0:0, moves the store) plus one declared node,
  0.8.0:0, whose `up` sets the flag behind the Recalculate Ledger task. Paths:
  0.3.x/0.7.x → 0.8.0:0 → 0.9.0:0; 0.8.0:x → 0.9.0:0.
- CI signs its pack with a throwaway key; the signing workspace is created
  above the checkout (`init-workspace` inside the repo writes files there and
  would mark the build `-modified`).
- Package-only revisions release as `vX.Y.Z-N` (branch `release/vX.Y.Z-N`).
- The mirror carries its own `.github/workflows` (from `startos/.github/`,
  inert here); its release workflow runs only on a `release/*` branch or by
  hand, so syncing never produces a second, differently signed s9pk.
- The app repository has no LICENSE file; the package declares MIT (as the
  wrapper always has). Start9's review checks that it matches upstream: add a
  LICENSE to BTCTX-MCP (and check the upstream BitcoinTX-org license) before a
  marketplace submission.
