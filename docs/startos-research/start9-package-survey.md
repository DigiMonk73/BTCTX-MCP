# StartOS packaging research: BitcoinTX vs current Start9 packages

Date: 2026-09-23. Read-only research. Clones live in `/tmp/claude-0/pkgs/` (plus `/tmp/claude-0/hello`, `/tmp/claude-0/reg`).
Our wrapper: `/home/user/btctx-startos` (start-sdk 2.0.9, HEAD `325492e`).

## 0. What was examined

| Package (clone path under /tmp/claude-0/pkgs) | last commit | SDK | Why relevant |
|---|---|---|---|
| actual-budget-startos | 2026-09-04 | 2.0.9 | **Closest analog**: finance app, 1 volume, generated admin password, critical task on install, `dockerBuild` from submodule |
| lnbits-startos | 2026-09-19 | 2.0.9 | Python/uvicorn + SQLite, `dockerBuild`, SQLite+bcrypt password reset, health-check gracePeriod |
| uptime-kuma-startos | 2026-09-16 | 2.0.9 | SQLite, reset-password action, **DB-migration health check**, root CA extraction |
| vaultwarden-startos | 2026-09-13 | 2.0.9 | SQLite, 1 volume, tasks (critical + important), config actions, 2 images (one `dockerBuild`) |
| filebrowser-startos | 2026-09-18 | 2.0.9 | reset admin (only-stopped), install task, EOL-notice task pattern |
| gitea-startos | 2026-08-30 | 2.0.9 | SQLite, riscv64, `withInput` admin create/reset, ui + api interfaces |
| searxng-startos | 2026-09-21 | 2.0.9 | config action with InputSpec + prefill + FileHelper YAML, `dynamicSelect` of own URLs |
| nextcloud-startos | 2026-09-19 | 2.0.9 | pg_dump + rsync backups; **extra `api` interface on same port with a path** |
| immich-startos | 2026-09-18 | 2.0.9 | pg_dump backups, hardware variants |
| btcpayserver-startos | 2026-09-21 | 2.0.9 | pg_dump, 4 images |
| mempool-startos | 2026-08-31 | 2.0.9 | backup scope reasoning |
| jellyfin-startos, nostr-rs-relay-startos, ghost-startos, bitcoind-startos | 2026-08/09 | 2.0.9 | `dockerBuild`, riscv64, tests (`bitcoind-startos/test/`) |
| /tmp/claude-0/hello (hello-world-startos), /tmp/claude-0/reg (startos-registry-startos) | 2026-08-17 / – | 2.0.9 | template |
| start-technologies (monorepo) | 2026-09-23 | – | reusable CI workflows + packaging guide at `projects/start-sdk/docs/src/` |
| service-pipeline | **2024-01-31 (stale, 0.3.5-era)** | – | old submission README |
| Community: remcoros/pushtx-startos, Start9-Community/chama-startos | – | 2.0.x | `dockerBuild` community examples |
| App repos with in-tree packaging: epochbtc/satd, mmalmi/nostr-vpn, heatpunk/blisspoint, paulscode/hashgg | – | 2.0.9 / 1.0.0 | Q4 |

`Start9Labs/actual-startos` does not exist (clone failed); `actual-budget-startos` is the real one.
All 17 Start9Labs packages cloned are on **start-sdk 2.0.9, pinned exactly** (`"2.0.9"`, not `^2.0.9`).

## 1. Common patterns vs our wrapper

| Area | What (nearly) every current Start9 package does | BitcoinTX wrapper | Gap? |
|---|---|---|---|
| SDK pin | `"@start9labs/start-sdk": "2.0.9"` exact (`maintaining-a-package.md` "Bumping the SDK": `--save-exact`) | `^2.0.9` | minor |
| Icon | `icon.svg`, ≤ 40 KiB (actual-budget 1006 B). Docs: `project-structure.md` "icon.svg: Maximum size is 40 KiB"; `new-package-checklist.md` "Replace icon.svg with a real icon (≤ 40 KiB). Fetch the upstream asset — never ship an invented one." (ghost still ships icon.png) | `icon.png` 512x512, **364 KB** | **YES** (9x over limit; not enforced by `start-cli s9pk pack` as far as I can see in `start-core/src/s9pk/v2/pack.rs` — review/registry rule, enforcement unverified) |
| License field | SPDX, e.g. `'MIT'`, `'Apache-2.0'`, `'AGPL-3.0'` (`manifest.md` "License") | `'mit'` (lnbits also lowercase) | minor |
| i18n | `startos/i18n/{index.ts,dictionaries/default.ts,translations.ts}`, `startos/manifest/i18n.ts`; every user string wrapped `i18n('...')`; 5 locales en_US/es_ES/de_DE/pl_PL/fr_FR; releaseNotes an object per locale | none; plain strings | **YES** (review checks "localization": `publishing.md`) |
| Versions layout | `versions/current.ts` (export `current`) + `index.ts` with `other: []`; only versions whose `up` does real work kept as `vX.Y.Z_N.ts`; `down: IMPOSSIBLE` | 16 files `v0_1_0_0.ts`…`v0_8_0_1.ts`, **all with empty `up`**, most with empty `down` (not IMPOSSIBLE) | **YES** (see §2.7; the empty `down` from 0.8.x would allow a downgrade onto an Alembic-migrated DB) |
| Git tags | `v{upstream}_{rev}` e.g. `v0.8.0_1`; push individually (`versions.md` "Git Tag Conventions") | `v0.8.0`, `v*` | YES |
| Init | `sdk.setupOnInit(async (effects, kind) => …)` modules (`seedFiles`, `setup`, `task…`) in `sdk.setupInit(restoreInit, versionGraph, seedFiles, setInterfaces, setDependencies, actions, …)` | plain async `firstBoot(effects, kind)` in `setupInit` | cosmetic (works) |
| Store file | `startos/fileModels/store.json.ts` → `FileHelper.json({ base: sdk.volumes.main, subpath: 'store.json' }, zodShape)`, seeded with `.merge(effects, {})` on every init | `/.startos-wrapper.json`, written only on install | minor |
| Credentials | generated password in store.json + "Get/Show" action + **critical task on install** (`sdk.action.createOwnTask(effects, getAdminPassword, 'critical', {reason})`) – actual-budget, filebrowser, nextcloud, vaultwarden | Show + Reset actions, **no task** | **YES** |
| Reset password | action generating password, writing via upstream CLI or sqlite in `SubContainer.withTemp` (uptime-kuma `allowedStatuses:'any'`, lnbits `only-running`, filebrowser `only-stopped`) | Reset (only-stopped) via python+bcrypt — already good | no |
| Health check | `checkPortListening` or `checkWebUrl`, i18n messages; `gracePeriod` when startup is slow (lnbits 75 s); extra `addHealthCheck` for long migrations (uptime-kuma) | `checkWebUrl` localhost:80, no gracePeriod, no migration check | small |
| Backups | SQLite apps (actual, vaultwarden, uptime-kuma, gitea, lnbits, searxng): plain `sdk.Backups.ofVolumes('main')` — **no hooks**, because "StartOS always runs the backup with the service stopped" (`recipe-backups.md`). Hooks/dumps only for Postgres/MySQL sidecars (`withPgDump`/`withMysqlDump`). Exclusions via `.setOptions({ exclude: [...] })` (bitcoind incl. `'**/*-journal'`) | `ofVolumes('main')` | **NO gap** for consistency. Optional: decide whether `/data/backups/` pre-upgrade copies should be excluded |
| Interfaces | 1 `ui` interface on a MultiHost; extra `api` interfaces where a client protocol exists (nextcloud WebDAV path, gitea SSH) | 1 ui | optional (MCP API interface) |
| Actions beyond creds | config forms (searxng `set-config`, vaultwarden `manageSmtp`, `setPrimaryUrl`), maintenance (bitcoind reindex, mempool clearBackendCache, btcpay resyncNbx) | none | optional (see §2) |
| Arches | `['x86_64','aarch64']` + Makefile `ARCHES := x86 arm`; riscv64 only when upstream image has it (gitea, bitcoind) | same | no (riscv64 only if our image adds linux/riscv64) |
| hardwareRequirements | usually omitted | `{}` | no |
| Docs files | `README.md` (AI/admin reference, packed into s9pk, **no version numbers**, "Quick Reference for AI Consumers" YAML), `instructions.md` (end-user, `## Documentation` bullets `- [Title](URL) — words`), `UPDATING.md`, `AGENTS.md`, `CLAUDE.md` = one line `@AGENTS.md` | README is a build guide; instructions.md has version-specific section "Updating to 0.8.0" and no `## Documentation`; no UPDATING.md; no AGENTS.md; large CLAUDE.md | **YES** |
| `assets/` | `assets/.gitkeep` (required dir) | `assets/ABOUT.md` | no |
| Prettier | `prettier` block in package.json (same config as ours) | same | no |
| CI | 4 thin callers of `Start9Labs/start-technologies/.github/workflows/*.yml@master`: build.yml (PR), tagAndRelease.yml (merge→tag→build→publish), release.yml (manual tag), syncNext.yml; secrets `DEV_KEY` (+ optional `S3_ACCESS_KEY/S3_SECRET_KEY`), vars `RELEASE_REGISTRY`, `REFERENCE_REGISTRY`, `S3_S9PKS_BASE_URL` | hand-rolled ci.yml/release.yml; **`start-cli init-key` each release ⇒ random signing key every release**; upstream-check.yml (nice, not in Start9 repos) | **YES** (signing identity) |
| Tests | rare (bitcoind `test/*.test.ts` with `node --experimental-strip-types --test`; satd has 5 test files) | none | optional |
| Dependencies | `{}` when none | `{}` | no |

### GAP LIST (prioritised)

1. **Icon**: replace 364 KB `icon.png` with an `icon.svg` (or ≤ 40 KiB png/webp) sourced from upstream BitcoinTX branding.
2. **Stable signing key**: release.yml runs `start-cli init-key`, so every release is signed by a fresh key. Start9 CI writes `secrets.DEV_KEY` to `~/.startos/developer.key.pem` and copies it to `.startos/build-key` (`start-technologies/.github/workflows/release.yml` lines ~105-120). Add a `DEV_KEY` repo secret (generate once). Whether StartOS rejects sideloaded updates with a changed key: unverified; registries definitely key on it.
3. **Install task for credentials**: `createOwnTask(effects, showCredentials, 'critical' | 'important', {reason})` on `kind === 'install'`.
4. **Version graph cleanup + `down: IMPOSSIBLE`**: collapse to `current.ts` + `other: []`; the current empty `down` functions (e.g. `v0_8_0_1.ts`) advertise downgrades onto a DB that Alembic already migrated forward.
5. **i18n**: add `startos/i18n/` + `manifest/i18n.ts` + per-locale releaseNotes (5 locales).
6. **Docs set**: AGENTS.md (short, repo-specific) + CLAUDE.md `@AGENTS.md`; UPDATING.md (how to bump `ghcr.io/digimonk73/btctx-mcp` tag); README rewritten to the "Writing READMEs" shape (no versions, Quick Reference YAML); instructions.md: add `## Documentation` bullets, remove "Updating to 0.8.0" (belongs in releaseNotes).
7. **Tag convention** `v0.8.0_1` (tagAndRelease computes this automatically).
8. **Reusable CI** (optional unless submitting to Start9-Community, where the fork gets them anyway).
9. Exact SDK pin, SPDX `'MIT'`.
10. Nice-to-have features: MCP/API interface + connection-info action, root-CA action, migration health check / gracePeriod, maintenance actions (§2).

Not gaps (do not add): DB-consistency backup hooks (service is stopped during backup), `properties` (0.3.x concept; replaced by actions in 0.4 — no 2.x package has properties), riscv64 (image has none), hardwareRequirements.

## 2. Features worth copying (with source snippets)

### 2.1 Critical task on install to collect the password — actual-budget
`/tmp/claude-0/pkgs/actual-budget-startos/startos/init/bootstrapServer.ts`
```ts
await sdk.action.createOwnTask(effects, getAdminPassword, 'critical', {
  reason: i18n('Retrieve the admin password'),
})
```
README of that package explains: "`critical` suspends the ordinary controls, so a fresh install shows only this prompt rather than a start button." Softer alternative: `'important'` (vaultwarden `init/taskToggleSignups.ts`, gitea `main.ts:172`). For us: in `firstBoot`, after `setAdminCredentials`, `await sdk.action.createOwnTask(effects, showCredentials, 'critical', { reason: 'Copy your BitcoinTX login' })`.

### 2.2 setupOnInit + store.json seeding — actual-budget
`startos/init/initializeService.ts`
```ts
export const seedFiles = sdk.setupOnInit(async (effects, kind) => {
  if (kind === 'install') {
    await storeJson.merge(effects, {
      adminPassword: utils.getDefaultString({ charset: 'a-z,A-Z,0-9', len: 24 }),
    })
  } else {
    await storeJson.merge(effects, {})
  }
})
```

### 2.3 Health check for long DB migrations — uptime-kuma
`/tmp/claude-0/pkgs/uptime-kuma-startos/startos/main.ts` (marker written by `versions/v2.4.0_1.ts` up-migration)
```ts
if (!existsSync(MIGRATION_MARKER)) return daemons
return daemons.addHealthCheck('migration', {
  ready: {
    display: i18n('Database Migration'),
    fn: async () => {
      try {
        const res = await fetch(`${uiUrl}/api/entry-page`)
        if (res.ok) { rm(MIGRATION_MARKER, { force: true }); return { result: 'success', message: i18n('Database migration complete') } }
      } catch {}
      return { result: 'loading', message: i18n('Database migration in progress. This may take a long time. Do NOT restart.') }
    },
  },
  requires: [],
})
```
Simpler alternative used by lnbits (`startos/main.ts`): `ready: { display, gracePeriod: 75_000, fn: ... }`. BitcoinTX runs Alembic at startup, so a gracePeriod is cheap insurance.

### 2.4 Config action with InputSpec, prefill, FileHelper — searxng
`/tmp/claude-0/pkgs/searxng-startos/startos/actions/setConfig.ts`
```ts
const { InputSpec, Value } = sdk
export const inputSpec = InputSpec.of({
  instance_name: Value.text({ name: i18n('Instance Name'), description: ..., required: true, default: 'My SearXNG' }),
  enable_metrics: Value.toggle({ name: i18n('Enable Stats'), description: ..., default: false }),
})
export const setConfig = sdk.Action.withInput('set-config',
  async () => ({ name: i18n('Config'), description: ..., warning: null, allowedStatuses: 'any', group: null, visibility: 'enabled' }),
  inputSpec,
  async () => { const y = await settingsYaml.read().once(); return y ? { instance_name: y.general.instance_name, ... } : {} },
  async ({ effects, input }) => settingsYaml.merge(effects, { general: { instance_name: input.instance_name, ... } }),
)
```
BitcoinTX candidates: default tax timezone, log level, or "allowed MCP hostnames" (see 2.6) written into store.json and passed as env in main.ts. Only worth it if the app reads env/config (it currently configures via its own Settings UI).

### 2.5 Extra `api` interface on the same port with a path — nextcloud
`/tmp/claude-0/pkgs/nextcloud-startos/startos/interfaces.ts`
```ts
const webdav = sdk.createInterface(effects, {
  name: i18n('WebDAV'), id: 'webdav', description: i18n('Addresses for WebDAV syncing'),
  type: 'api', masked: false, schemeOverride: null, username: null,
  path: '/remote.php/dav/', query: {},
})
const uiReceipt = await uiMultiOrigin.export([ui, webdav])
```
For BitcoinTX: an `api` interface (e.g. id `api`, path `/api/`) gives the MCP user a copyable base URL for every address (LAN `.local`, IP, Tor, custom domain) instead of guessing.

### 2.6 MCP-specific actions — epochbtc/satd (in-app-repo package)
`/tmp/claude-0/pkgs/app-satd/contrib/packaging/startos/startos/actions/{mcpToken.ts,mcpHostnames.ts,caCertificate.ts}` and `interfaces.ts` (dedicated MCP host with `addSsl`). Pattern: an action that returns a copyable secret/cert with a "Not generated yet — start the service once" fallback:
```ts
if (!token) return { version: '1', title: i18n('Not generated yet'), message: i18n('... Start the service once, then run this action again.'), result: null }
return { version: '1', title: i18n('MCP Token'), message: i18n('Send this as `Authorization: Bearer <token>` ...'),
  result: { type: 'single', name: i18n('MCP Token'), description: i18n('Bearer token'), value: token, copyable: true, qr: false, masked: true } }
```
satd also documents that StartOS's reverse proxy passes `Host` unchanged, so an MCP DNS-rebinding allowlist must be told the `.local` name, which "no effect exposes" (`mcpHostnames.ts` comment).

### 2.7 Getting the StartOS root CA (for the MCP client to trust `https://….local`) — uptime-kuma
`/tmp/claude-0/pkgs/uptime-kuma-startos/startos/main.ts`
```ts
const [, , rootCa] = await sdk.getSslCertificate(effects, ['127.0.0.1']).const()
```
An action "MCP Connection Info" could return a group: API URL(s) from `sdk.host.getOwn(...)` (searxng `setConfig.ts` shows `iface.addressInfo.nonLocal.format()`), username `admin`, and the root CA PEM (copyable) — replacing the manual "trust your server's certificate" steps in our instructions.md. (Using `getSslCertificate` inside an action rather than main: API exists on sdk; behaviour in action context unverified.)

### 2.8 Version graph per current guide
`/tmp/claude-0/pkgs/actual-budget-startos/startos/versions/{index.ts,current.ts}`
```ts
export const versionGraph = VersionGraph.of({ current, other: [] })
// current.ts
export const current = VersionInfo.of({
  version: '26.9.0:0',
  releaseNotes: { en_US: `...`, es_ES: `...`, de_DE: `...`, pl_PL: `...`, fr_FR: `...` },
  migrations: { up: async ({ effects }) => {}, down: IMPOSSIBLE },
})
```
Guide (`start-technologies/projects/start-sdk/docs/src/versions.md`): "A version earns a declared node only when it introduced a migration… `other: []` already yields the widest possible range (`<=current`)." Note: `index.ts` exports `versionGraph` (ours exports `versions`) and `startos/index.ts` does `buildManifest(versionGraph, sdkManifest)`.

### 2.9 Maintenance actions
- bitcoind `actions/reindexBlockchain.ts`, mempool `clearBackendCache.ts`, btcpay `resyncNbx.ts`: one-shot maintenance buttons with `warning` text.
- BitcoinTX candidates: "Recalculate Ledger" (call the app's HTTP endpoint from a `SubContainer.withTemp` or `fetch` to the container), "List/restore pre-upgrade database copy" from `/data/backups/` (only-stopped). The 0.8.0 "click Recalculate Ledger once" instruction could become a one-time `important` task raised by a version migration (filebrowser `init/eolNotice.ts` + `actions/acknowledgeEol.ts` shows a task gated by a store flag).

### 2.10 Backup exclusion syntax (if `/data/backups/` should not be in StartOS backups)
bitcoind `startos/backups.ts`: `sdk.Backups.ofVolumes('main').setOptions({ exclude: ['**/*-journal', ...] })`. Trade-off: excluding `backups/` shrinks backups but loses the "undo an update" copies after a restore. Decision, not a defect.

### 2.11 Reusable CI (verbatim from actual-budget)
`.github/workflows/tagAndRelease.yml`
```yaml
on: { push: { branches: ['master'], paths-ignore: ['*.md'] } }
jobs:
  tag:
    uses: Start9Labs/start-technologies/.github/workflows/tagAndRelease.yml@master
    with:
      REFERENCE_REGISTRY: ${{ vars.REFERENCE_REGISTRY }}   # required
      RELEASE_REGISTRY: ${{ vars.RELEASE_REGISTRY }}
      S3_S9PKS_BASE_URL: ${{ vars.S3_S9PKS_BASE_URL }}
    secrets:
      DEV_KEY: ${{ secrets.DEV_KEY }}                       # required
      S3_ACCESS_KEY: ${{ secrets.S3_ACCESS_KEY }}
      S3_SECRET_KEY: ${{ secrets.S3_SECRET_KEY }}
    permissions: { contents: write }
```
Behaviour (start-technologies `.github/workflows/release.yml`): discovers a build matrix via `make -s print-TARGETS`, builds each arch natively (arm on `ubuntu-24.04-arm`), creates the GitHub release with notes from the manifest, and — only if `RELEASE_REGISTRY` set — publishes via `start-cli registry package add ... --url <gh release asset>` (needs the DEV_KEY to be an authorised signer on that registry). Without a registry it still does GitHub releases, so a self-publisher could adopt it with only `DEV_KEY` + a dummy/own `REFERENCE_REGISTRY` (tagAndRelease errors if it cannot query the reference registry — so it needs a real reachable registry; unverified whether an empty value is tolerated). build.yml (PR) needs no secrets.

## 3. Community-registry submission requirements

Authoritative current source is the packaging guide, **not** service-pipeline (its README still describes `manifest.yaml`, `start-sdk pack`, `submissions@start9labs.com`, last commit 2024-01-31).

From `start-technologies/projects/start-sdk/docs/src/publishing.md`:
- Two options: run your own registry (install `startos-registry` service; `host-registry*.md`) and/or submit to Start9 Community Registry. "Nothing about the packaging workflow requires you to distribute through Start9."
- **Initial submission: email submissions@start9.com with a link to your public GitHub repository.** Start9 **forks it into the Start9-Community GitHub org** and reviews "correctness, conformance, docs, localization, CI"; review lands as a PR on the fork. "**The fork is the upstream from that point on**" — every later version is a PR against the fork.
- Pipeline: PR merged on fork → CI builds, tags, deploys to **community-beta** (https://community-beta-registry.start9.com) → you test → email/issue to promote to **community** (https://community-registry.start9.com). "The go-ahead is yours to give."
- Pre-publish checklist: tag convention `v{upstream}_{rev}`; `tsc --noEmit`, tests and pack green; README current, **no version numbers**; tested end-to-end on StartOS incl. uninstall/reinstall.
- `new-package-checklist.md`: packageRepo/upstreamRepo/marketingUrl/donationUrl filled; LICENSE matches manifest license and **upstream's license** (`project-structure.md`: "should always match the upstream service's license"); i18n descriptions translated; real upstream icon ≤ 40 KiB; README/instructions/UPDATING/AGENTS; install on a box; backup/restore sanity check.
- `service-pipeline/wrapper-testing-procedure.md` (old but still sensible QA list): marketplace list/show (icon, title, short/long description, release notes), instructions "as if you were a five-year-old", health checks with helpful messages, logs clean, every action run, interfaces, donate button, restart, backup → uninstall → restore.
- **Repo naming / layout**: not a stated hard rule, but convention is universal: `<id>-startos` repo (`agent-context.md`: workspace holds `<id>-startos/` package repos), and "**The Package Repo Is Not a Fork of the Application**" (`project-structure.md`): app comes from a published image (default), a git submodule + own Dockerfile, or a Start9-built image. The satd package README states "Start9's registry expects one repository per package" (their interpretation). Since Start9 forks the submitted repo into Start9-Community, a standalone repo is effectively required for the community registry.
- Naming: ids are lowercase-hyphenated; `btctx` is fine. Title/icon must represent the upstream (never an invented logo).
- Review process timing/criteria beyond the above: not documented (unverified).

Implication for BitcoinTX: `packageRepo` = DigiMonk73/BTCTX-StartOS already fits. Upstream is the fork image `ghcr.io/digimonk73/btctx-mcp`; license MIT matches. The fork-of-app concern does not apply (wrapper pulls an image).

## 4. Packages living inside an application's own repository

| Repo | Location | How built / published |
|---|---|---|
| **epochbtc/satd** (`/tmp/claude-0/pkgs/app-satd`) | `contrib/packaging/startos/` (full standard layout incl. its own `.github/workflows` copies, `test/`, README) | Developed in-tree "so it is reviewed and versioned with satd", **published from a separate repo `epochbtc/satd-startos`** via maintainer-run `contrib/packaging/sync-store.sh startos <clone>` (rsyncs the dir, verifies the image pin is a release tag + digest matching the package version, never commits/pushes). Root CI (`.github/workflows/appliance.yml` ~L220-262) runs `npm ci`, type check, tests and `npm run build` in `working-directory: contrib/packaging/startos`. README notes start-cli needs a `.startos/` workspace (config.yaml + build key) in the *parent* dir. manifest `packageRepo: 'https://github.com/epochbtc/satd/tree/master/contrib/packaging/startos'`. |
| **mmalmi/nostr-vpn** (`app-nostr-vpn`) | `startos/` at repo root beside Rust crates; root `Makefile` `include s9pk.mk` (vendored copy) | `dockerBuild: { workdir: '.', dockerfile: './umbrel/Dockerfile' }`; releases via `just release-startos` → `scripts/startos-release.mjs` (pins start-cli 1.1.0); `packageRepo` = app repo. |
| **heatpunk/blisspoint** (`app-blisspoint`) | `startos/` + `sdk-build/` at root | `.github/workflows/release.yml` job `s9pk`: build/push docker image to GHCR, install start-cli, `start-cli s9pk init-workspace` in `$GITHUB_WORKSPACE/..`, **generates a throwaway Ed25519 key each run** (`openssl genpkey -algorithm Ed25519 -out ~/.startos/id.key.pem`), then `start-cli s9pk pack --javascript sdk-build/javascript --icon startos/icon.png --instructions startos/instructions.md --license LICENSE --no-assets -o blisspoint.s9pk`, attaches to GitHub release. |
| paulscode/hashgg (`app-hashgg`) | `startos/` at root, SDK 1.0.0, `dockerBuild` from root Dockerfile | older SDK line |

Takeaway: in-tree packaging works for self-distribution (GitHub release asset / own registry). For the Start9 community registry the working model is satd's: keep the source of truth wherever you like, but mirror into a dedicated `*-startos` repo that Start9 can fork. `start-cli s9pk pack` flags (`--javascript`, `--icon`, `--instructions`, `--license`, `--no-assets`) let a subdirectory package be packed from elsewhere; `dockerBuild.workdir`/`dockerfile` are resolved relative to the package root.

## 5. Miscellaneous observations
- `start-technologies/.github/workflows/release.yml`: "start-cli 0.4.0-beta.10's `s9pk pack` requires a packaging workspace: a `.startos/` dir holding a `build-key`" — CI copies DEV_KEY there. Our release.yml relies on `start-cli init-key` + `make universal`; it evidently works with start-cli 2.1.0 but produces unstable signatures.
- Our upstream-check.yml (daily ghcr tag check → issue) has no equivalent in Start9 repos; Start9 uses UPDATING.md + human/agent bumps. Keep it.
- Start9 README convention: first line blockquote "Everything not listed in this document should behave the same as upstream…", sections Image and Container Runtime / Volume and Data Layout / File Models / Dependencies / Network Access and Interfaces / Installation and First-Run Flow / Actions / Tasks / Health Checks / Backups and Restore / Limitations / Quick Reference for AI Consumers (see `/tmp/claude-0/pkgs/actual-budget-startos/README.md`).
- AGENTS.md convention: short, repo-specific; "Bugs and feature requests are GitHub issues… no TODO.md, NOTES.md, PLAN.md" (actual-budget `AGENTS.md`). Our `docs/PRD.md` would be discouraged by that rule.
- `recipe-admin-credentials.md` lists canary-startos (`watchCredentials.ts` + `setAdminPassword.ts`) as the "cleanest reference" for admin credentials (not cloned; unverified).

Unverified items: icon size enforcement at registry; whether sideload updates with a different signing key are rejected; `getSslCertificate` in action context; tagAndRelease tolerance of an empty REFERENCE_REGISTRY; review SLAs.
