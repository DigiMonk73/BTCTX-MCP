# StartOS packaging capabilities with start-sdk 2.0.9: research report

Research date: 2026-09-23. Read-only; nothing in any repository was modified.

## 0. Sources and version landscape (read this first)

| Label used below | What it is | Where |
|---|---|---|
| **SDK** | Installed `@start9labs/start-sdk` **2.0.9** (npm `latest` = 2.0.9, verified with `npm view`) | `/home/user/btctx-startos/node_modules/@start9labs/start-sdk/` |
| **CORE** | Its bundled `@start9labs/start-core` (types, osBindings) | `…/start-sdk/node_modules/@start9labs/start-core/` |
| **DOCS209** | Packaging guide at git tag `start-sdk/v2.0.9` (commit f8fb04b, 2026-07-24) | `/tmp/claude-0/st209/projects/start-sdk/docs/src/` |
| **DOCSLIVE** | Branch `live-docs` (commit 129714d, 2026-09-23). This is the branch `start-cli s9pk init-workspace` clones (`MONOREPO_BRANCH = "live-docs"`, `shared-libs/crates/start-core/src/s9pk/init.rs:61`), and it is what docs.start9.com serves. Its SDK is **2.0.10 (NOT on npm; `npm view …@2.0.10` 404s)**, "StartOS 0.4.0". | `/tmp/claude-0/stlive/projects/start-sdk/docs/src/`, StartOS user docs in `/tmp/claude-0/stlive/projects/start-os/docs/src/` |
| **MASTER** | `master` (commit 304926d). SDK **3.0.0, unreleased**, targets StartOS 0.4.0.2. Has breaking changes. Also has the Rust source of start-cli / StartOS. | `/tmp/claude-0/st/` |
| **HELLO**, **REG** | `hello-world-startos` and `startos-registry-startos`, both on SDK 2.0.9 | `/tmp/claude-0/hello`, `/tmp/claude-0/reg` |
| start-cli | Local binary reporting `start-cli 2.1.0` | `/tmp/claude-0/start-cli` |

Other version facts:
- The StartOS tag `start-os/v0.4.0.1` (commit fdb27c7, 2026-07-26) has SDK `package.json` version 2.0.10. SDK 2.0.9's `OSVersion` constant is still `0.4.0-beta.10` (`SDK/lib/StartSdk.js:74`). So a 2.0.9 package declares `osVersion: 0.4.0-beta.10`, and it installs on 0.4.0.x.
- **The reusable CI workflows are referenced `@master`**, so they run the MASTER versions of `.github/workflows/*.yml` and install the **latest released start-cli**, not one matched to 2.0.9 (`st/.github/actions/setup-build-env/action.yml`, "Install start-cli" step).
- Throughout this report, "(3.0.0)" marks something that changes in the unreleased SDK. Plan for it, but do not code against it yet.

---

## 1. Manifest (`startos/manifest/index.ts` via `setupManifest`)

Type: `SDKManifest` in `CORE/types/ManifestTypes.d.ts:3-144`. `buildManifest` in `SDK/lib/manifest/setupManifest.js:24-63` fills in defaults and computed fields.

### Required fields (no `?` in the type)
| Field | Notes |
|---|---|
| `id` | Unique package id, lowercase with hyphens. `start-os` is reserved (DOCS209 manifest.md:57). |
| `title` | Display name. |
| `license` | SPDX id. The LICENSE file is packed separately (see §12). |
| `packageRepo`, `upstreamRepo`, `marketingUrl` | Strings (URLs). All three are required. |
| `donationUrl` | `string \| null`. Required key, nullable. |
| `description: { short, long }` | `T.LocaleString` (`string \| Record<locale,string>`). TSDoc limits: short ≤ 80 chars, long ≤ 500 chars (ManifestTypes.d.ts:40-43). Convention is `manifest/i18n.ts` with `en_US, es_ES, de_DE, pl_PL, fr_FR` (HELLO `startos/manifest/i18n.ts`). |
| `images` | `Record<ImageId, SDKImageInputSpec>` |
| `volumes` | `string[]`, at least one (ManifestTypes.d.ts:81-85) |
| `dependencies` | `Record<id, { description, optional, metadata \| s9pk }>` (CORE `osBindings/DepInfo.d.ts`). Use `{}` for none. |

### Optional fields
`osVersion?` (overrides the SDK's; ManifestTypes.d.ts:49), `hardwareRequirements?: { device?: DeviceFilter[], ram?: number|null }`, `hardwareAcceleration?` (`/dev/dri`, `/dev/nvidia*`), `userspaceFilesystems?` (`/dev/fuse`), `virtualNetworking?` (`/dev/net/tun`), `plugins?: ['url-v0']` (the only PluginId, `CORE/osBindings/PluginId.d.ts`).

- **`hardwareRequirements.ram` is in BYTES.** The 2.0.9 TSDoc says "megabytes" with `ram: 8192` (ManifestTypes.d.ts:109,117). That is wrong: the fix is in the 2.0.10 changelog (`stlive/projects/start-sdk/CHANGELOG.md`, "Fixed" section) and in the DOCSLIVE manifest.md "Minimum RAM" section. Use `ram: 2 * 1024 ** 3`. Raising the floor on a published package cuts smaller hosts off from updates.
- `DeviceFilter = { class: 'processor'|'display', product, vendor, description, capabilities?, driver? }` (`osBindings/DeviceFilter.d.ts`). The old `devices/pattern` shape in the TSDoc is stale.
- **Not fields:** there is no `docs`, `assets`, `instructions` or `icon` manifest field. Those are files found by `start-cli s9pk pack` (§12). `releaseNotes` and `version` come from the VersionGraph (§6). `gitHash`, `sdkVersion`, `canMigrateFrom/To`, `satisfies` and `hardwareRequirements.arch` are computed (setupManifest.js:35-62).

### Images
```ts
images: {
  app: {
    source: { dockerTag: 'ghcr.io/owner/bitcointx:1.2.3' },   // prebuilt
    // or: { dockerBuild: { workdir: '..', dockerfile: '../Dockerfile', buildArgs: { FOO: 'x', BAR: { env: 'BAR' } } } }
    arch: ['x86_64', 'aarch64'],        // any ordering/subset of x86_64|aarch64|riscv64
    emulateMissingAs: 'x86_64',         // or null
    nvidiaContainer: false,
  },
},
```
- `ImageSource = 'packed' | {dockerBuild:{workdir?,dockerfile?,buildArgs?}} | {dockerTag}` (`CORE/osBindings/ImageSource.d.ts`). `BuildArg = string | { env: string }` (`BuildArg.d.ts`); `{env}` reads a build-host environment variable.
- dockerBuild behaviour, from start-cli source (`st/shared-libs/crates/start-core/src/s9pk/v2/pack.rs:520-560`):
  - `workdir` defaults to `.` and `dockerfile` defaults to `<workdir>/Dockerfile`.
  - It runs `docker buildx build <workdir> -f <dockerfile> --platform=linux/<arch> --build-arg ARCH=<arch>` plus the `buildArgs`. Paths are relative to the directory `pack` runs in (the package dir), so `workdir: '..'` builds from a parent directory. The context can sit above the package; this is inferred from the code and was not built.
  - The Dockerfile is listed as a build ingredient, so `make` rebuilds when it changes (pack.rs:480-495).
- `arch` defaults to `['aarch64','x86_64','riscv64']` when omitted (setupManifest.js:26). The template and docs say to list it explicitly and keep it in sync with Makefile `ARCHES` (DOCS209 manifest.md:91,171). HELLO declares riscv64 on purpose as a platform smoke test (HELLO AGENTS.md:30).
- `emulateMissingAs` default is `'x86_64'` if the list includes x86_64, else `arch[0]` (setupManifest.js:27-30). Any image with an `emulateMissingAs` is excluded from the computed `hardwareRequirements.arch` (setupManifest.js:49-57). By default, then, the package does not hard-restrict architecture and falls back to emulation.
  - (3.0.0) `emulateMissingAs` is replaced by `emulateMissing: boolean` (MASTER CHANGELOG 3.0.0).
- Variants (GPU and similar): set `VARIANT`/`TARGETS` in the Makefile and `hardwareRequirements.device` in the manifest. Each variant needs a distinct requirement (DOCS209 manifest.md:190-217). Not relevant for BitcoinTX.

### Removed in 2.0
- `alerts` (install/update/uninstall/restore/start/stop confirmation prompts) was removed with no alias (SDK CHANGELOG.md:171).
- `nestedRuntime` was removed and split into `userspaceFilesystems` and `virtualNetworking` (CHANGELOG.md:170).
- `sdk.serviceInterface.*` and `PackageDataEntry.serviceInterfaces` were removed (CHANGELOG.md:161,175); see §2.

### Volumes and convention
`volumes: ['main']`. DOCSLIVE (file-models.md, "store.json.ts") now says `store.json` belongs on its own volume named **`startos`** that no subcontainer mounts, and that volume must also be backed up (`volumes: ['main','startos']`, `Backups.ofVolumes('main','startos')`). DOCS209 still used `sdk.volumes.main`.

Paths: `sdk.volumes.<id>` gives the host path helpers (StartSdk.d.ts:3084). The on-host path is `/media/startos/volumes/<id>/` (Backups.d.ts `BackupSync.dataPath`).

---

## 2. Interfaces (`startos/interfaces.ts`)

API: `sdk.setupInterfaces(async ({effects}) => receipts[])`, then `sdk.MultiHost.of(effects, hostId)`, then `.bindPort(internalPort, opts)` which returns an `Origin`, then `.export([sdk.createInterface(...)])`.

### `bindPort` options (`CORE/interfaces/Host.d.ts`, `osBindings/AddSslOptions.d.ts`, `BindOptions.d.ts`)
- Known protocols (`knownProtocols`, Host.d.ts): `http`/`ws` (secure null, withSsl https/wss, X-Forwarded headers), `https`/`wss` (secure ssl:true), `ssh`/`dns` (secure ssl:false).
- `{ protocol: 'http'|'https'|'ws'|'wss'|'ssh'|'dns', preferredExternalPort?, addSsl?: Partial<AddSslOptions> }`.
- Raw TCP: `{ protocol: null, preferredExternalPort, addSsl: AddSslOptions|null, secure: {ssl:boolean}|null }`.
- `AddSslOptions` fields:
  - `preferredExternalPort`
  - `addXForwardedHeaders`
  - `alpn: 'reflect'|{specified:[…]}|null` (3.0.0 changes this to a list or null)
  - `upstreamCertValidation?: 'disable'|{certificate}` (added 2.0.0)
  - `auth: ProxyAuth|null`
- **Proxy auth gate** (added 1.3.4, CHANGELOG.md:239; DOCS209 interfaces.md:309-381):
  - `auth: {type:'basic', credentials:[{username,password}], realm}` or `{type:'bearer', tokens:[…], realm}`.
  - The OS reverse proxy checks `Authorization` before forwarding. Basic auth forwards `X-Forwarded-User`.
  - Only valid on http/https/ws/wss.
  - Read the secret reactively in `setupInterfaces` (`storeJson.read(s=>s.pw).const(effects)`) so rotation re-runs the handler.
  - Relevant to MCP: a Bearer-token gate on a separate MCP binding is possible at the OS layer.
- TLS model (DOCS209 interfaces.md:265-283):
  - StartOS terminates TLS and proxies **plain HTTP** into the container. Do not configure in-container HTTPS.
  - Hard-code `https://` for any browser-facing absolute URL.
  - Rewrap mode is `https` with `addSsl`; passthrough is `secure:{ssl:true}` with no `addSsl` (DOCSLIVE interfaces.md "Serving Your Own TLS").
- `secure` semantics on raw TCP (DOCSLIVE interfaces.md "Choosing secure"): `null` means never exposed off-box except via `addSsl`.
- `bindPortRange({internalStartPort, externalStartPort, numberOfPorts})` covers 2–500 ports and exports exactly one `api` interface via `createRangeInterface` (CHANGELOG.md:138).

### `createInterface` (StartSdk.d.ts:2562-2590)
`{ name, id, description, type: 'ui'|'api'|'p2p', masked, schemeOverride: {ssl,noSsl}|null, username: string|null, path: string, query: Record<string,string> }`.
- `type` is only a label. `'ui'` gives the user an "open in new tab" launch; `'api'` shows a copyable connection string (DOCSLIVE recipe-api-interface.md).
- `masked: true` hides URLs that carry credentials.
- `username`, `path` and `query` are baked into the displayed URL. `username` is unrelated to the `auth` gate (DOCS209 interfaces.md:346-347).
- (3.0.0) adds `preferredLauncherAddress`.

### Multiple interfaces
- Same port: `origin.export([ui, admin])` (DOCS209 interfaces.md:48-86). One binding can back several interfaces (`BindInfo.interfaces` map, `osBindings/BindInfo.d.ts`).
- Separate ports: a separate `MultiHost` per port (interfaces.md:88-160).
- For BitcoinTX, a web UI plus an MCP HTTP endpoint could be:
  - (a) one port with `ui` at `path:''` and `api` at `path:'/mcp'`, or
  - (b) a second binding and `MultiHost` for MCP with `type:'api'`, `masked:true`, and optionally `addSsl.auth` bearer.
- Setting up (b) is straightforward to write, but it has not been built or tested here (unverified).

```ts
export const setInterfaces = sdk.setupInterfaces(async ({ effects }) => {
  const web = await sdk.MultiHost.of(effects, 'ui-multi').bindPort(80, { protocol: 'http' })
  const ui = sdk.createInterface(effects, { name: i18n('Web UI'), id: 'ui', description: i18n('…'),
    type: 'ui', masked: false, schemeOverride: null, username: null, path: '', query: {} })
  const mcp = sdk.createInterface(effects, { name: i18n('MCP Server'), id: 'mcp', description: i18n('…'),
    type: 'api', masked: true, schemeOverride: null, username: null, path: '/mcp', query: {} })
  return [await web.export([ui, mcp])]
})
```

### Conditional exports (DOCSLIVE interfaces.md "Conditional exports")
The handler is not additive: anything not exported on a pass is revoked (`clearBindings`/`clearServiceInterfaces({except})`). Gate on the narrowest value, and an early `return []` revokes everything. (3.0.0) adds `MultiHost.retire()`/`retirePort()`.

### How URLs reach users (StartOS user docs)
- Interfaces tab, per-gateway tables (`stlive/projects/start-os/docs/src/interfaces.md`). Address kinds are IPv4, IPv6, Domain and mDNS (`.local`).
- LAN addresses are on by default. Public IPv4 is **off** by default. IPv6 GUA has a Local/Public dropdown.
- Certificate authority is Root CA, Let's Encrypt, or None.
- **Tor is not built in.** The user installs the Tor service and adds onions per interface; they appear as plugin addresses (`start-os/docs/src/tor.md`; DOCS209 interfaces.md:12-15 warns never to claim a service "is on Tor").
- Public domains (clearnet) use a router or **StartTunnel** gateway. StartTunnel is a WireGuard "virtual private router" on a VPS, recognized as an inbound/outbound gateway (`start-os/docs/src/gateways.md:9-35`, `clearnet.md:12-34`).
- Private domains cover LAN/VPN.
- A public domain is added per binding. Other bindings on the same host get it off by default (DOCSLIVE interfaces.md:9-10).

### Reading own addresses
`sdk.host.getOwn(effects, hostId, map?, eq?)` returns a reactive FilledHost with `.const()`, `.once()`, `.watch()`, `.onChange()`, `.waitFor()` (StartSdk.d.ts:136-183). Interfaces sit at `host.bindings[port].interfaces[id]`, and `addressInfo` is pre-filled with `.format('urlstring'|'url'|'hostname-info')`, `.filter({kind,visibility,…})`, `.matchesAny`, `.nonLocal`, `.public`, `.bridge`, `.toUrl` (`CORE/util/filledAddress.d.ts:19-139`). Filter kinds: `mdns|domain|ip|ipv4|ipv6|localhost|link-local|bridge|plugin`.

Real usage in REG `startos/init/setHostnames.ts:6-26`:
```ts
const hosts = await sdk.host.getOwn(effects, 'ui-multi', h =>
  Object.values(h?.bindings ?? {}).flatMap(b => Object.values(b.interfaces)).find(i => i.id === 'ui')
    ?.addressInfo.nonLocal.format('hostname-info').map(x => x.hostname) ?? []).const()
```
Doc inconsistency: DOCS209 main.md:147 uses `h.hostname.value`, but `HostnameInfo.hostname` is a `string` (`osBindings/HostnameInfo.d.ts`). REG uses `h.hostname`.

Related helpers: `sdk.host.getBridgeAddress` (2.0.8/2.0.9, for dependencies), `sdk.getOsIp` (`10.0.3.1`), `sdk.getContainerIp`, `sdk.getSslCertificate`/`getSslKey`, `sdk.getSystemSmtp`, `sdk.getOutboundGateway`.

---

## 3. Actions (`startos/actions/`)

- Constructors (StartSdk.d.ts:229-334):
  - `sdk.Action.withoutInput(id, metadata, run)`
  - `sdk.Action.withInput(id, metadata, inputSpec, prefill, run)`
- `metadata` can be an object or `async ({effects}) => …`. It can be reactive (`.const(effects)`) to change name, warning or visibility live.
- Register with `sdk.Actions.of().addAction(a).addAction(b)`; order is display order.
- `ActionMetadata` (`osBindings/ActionMetadata.d.ts`):
  - `name`, `description`
  - `warning: string|null`. For a no-input action it turns into a confirm dialog (DOCSLIVE recipe-admin-credentials.md "Confirm before rotating").
  - `visibility: 'enabled'|'hidden'|{disabled: reason}`
  - `allowedStatuses: 'only-running'|'only-stopped'|'any'`. The TSDoc says "all" but the type is `'any'`.
  - `group: string|null` for grouped headers.
  - `access?: 'public'|'dependent'|'user'` (default `user`; added 2.0.0, CHANGELOG.md:144)
- Results (`ActionResultV1`): `{version:'1', title, message|null, result: null | {type:'single', value, copyable, qr, masked} | {type:'group', value: [{name, description, type:'single'|'group', …}]}}`.
  - DOCS209 actions.md:97-109 shows `name/description` on a top-level single result; the type does not have them.
  - The message is rendered as HTML (REG listPackages.ts:61 comment).
  - (3.0.0) adds `launchable` and `multiline` result types.
- Errors: DOCSLIVE actions.md says errors thrown from a handler are shown to the user as the failure alert, so wrap them in `i18n()`.
- Input specs:
  - `sdk.InputSpec.of({...})` with `Value.*` builders: `text, textarea, number, toggle, select, multiselect, color, datetime, list, object, union, hidden, file, triState` plus a `dynamic*` variant of each (`CORE/actions/input/builder/value.d.ts`). `List.text/obj/dynamicText`, `Variants.of`.
  - Text options: `masked, placeholder, minLength, maxLength, patterns[{regex,description}], inputmode, immutable, generate: {charset,len}, default: string|{charset,len}|null, footnote` (value.d.ts:165-215).
  - `Value.file` exists (`{extensions, required}` returning `{path, commitment}`), but no doc covers it. Its UI support is unverified.
  - Built-in SMTP spec: `sdk.inputSpecConstants.smtpInputSpec`, `smtpShape`, `smtpPrefill` (DOCS209 actions.md:307-474).
- Running actions from code: `sdk.action.run({effects, actionId, input})` (StartSdk.d.ts:70-75). (3.0.0) changes `input` to a function.

### Tasks (prompt the user to run an action)
- `sdk.action.createOwnTask(effects, action, 'critical'|'important'|'optional', { reason?, replayId?, when?, input? })`
- `sdk.action.createTask(effects, packageId, action, severity, opts)`
- `sdk.action.clearTask(effects, ...replayIds)`

(StartSdk.d.ts:76-84; `CORE/actions/index.d.ts:14-33`.)
- **critical blocks the service from starting until done.** Important is prominent but non-blocking. Optional is least prominent (DOCS209 tasks.md:24-28).
- Idempotent: the default replayId is `<pkg>:<action>`.
- `input:{kind:'partial', accept:[…], set:{…}}` with `when:{condition:'input-not-matches', once}` (the 2.0.0 split; CHANGELOG.md:158).
- If you rename an action, clear the old replay key in a migration (DOCSLIVE tasks.md "Retiring a replay key").

Canonical admin-credential pattern (DOCS209 init.md:65-145; DOCSLIVE recipe-admin-credentials.md). This fits BitcoinTX's username/password login:
```ts
export const watchCredentials = sdk.setupOnInit(async effects => {
  const pw = await storeJson.read(s => s.adminPassword).const(effects)
  if (!pw) await sdk.action.createOwnTask(effects, setAdminPassword, 'critical',
    { reason: i18n('Set the admin password before signing in') })
})
// setAdminPassword = sdk.Action.withoutInput('set-admin-password', async ({effects}) => ({…warning when already set…}),
//   async ({effects}) => { const p = utils.getDefaultString({charset:'a-z,A-Z,0-9', len:32}); …apply…;
//   return { version:'1', title, message, result:{ type:'group', value:[{type:'single',name:'Username',…},
//   {type:'single',name:'Password',value:p,masked:true,copyable:true,qr:false,description:null}] } } })
```
- Warning: never hand-write a password hash into app config in an unverified format. Apply it through the app's own CLI/API, via `SubContainer.withTemp` in the action, and verify that a real login works (DOCSLIVE recipe-admin-credentials.md).
- Rotation and reset follow the same action (recipe-reset-password.md).

---

## 4. Daemons, oneshots and health checks (`startos/main.ts`)

`main = sdk.setupMain(async ({effects}) => sdk.Daemons.of(effects).addDaemon(...)...)`. Types are in `SDK/lib/mainFn/Daemons.d.ts`.

- `addDaemon(id, { subcontainer, exec, ready, requires: [ids] })`
  - `subcontainer = sdk.SubContainer.of(effects, {imageId, sharedRun?}, sdk.Mounts.of().mountVolume({volumeId, subpath, mountpoint, readonly, type?:'file', idmap?}), name)`. This is lazy since 2.0.0.
  - `exec: { command: string[] | sdk.useEntrypoint(cmdOverride?), env?, cwd?, user?, runAsInit?, sigtermTimeout? (default 30_000 ms), onStdout?, onStderr? }` or `{ fn: async (sub, abort) => ExecCommandOptions|null }` (Daemons.d.ts:88-126).
- `ready: { display: string|null, fn: () => HealthCheckResult, gracePeriod? (default 10_000 ms; failures shown as "starting"), trigger? }` (Daemons.d.ts:37-80).
- Result states: `success | loading | disabled | starting | waiting | failure`. `loading` and `failure` need a message (`osBindings/SetHealth.d.ts`).
- `addOneshot(id, {subcontainer, exec, requires})` runs to exit 0 on every start. Use it for `chown`, app schema migrations (e.g. alembic), and the like.
- `addHealthCheck(id, {ready, requires})` is a standalone check; dependents can reference it.
- Any entry can be given as a factory that returns `null` to skip it.
- `requires` sets start ordering and readiness gating (Daemons.d.ts:136-160).
- Built-in checks (StartSdk.d.ts:2648-2664):
  - `checkPortListening(effects, port, {successMessage, errorMessage})` reads /proc/net.
  - `checkWebUrl(effects, url, {timeout=1000,…})` succeeds on **any** HTTP response, whatever the status (`SDK/lib/health/checkFns/checkWebUrl.js`).
  - `runHealthScript(cmd, sub, …)` succeeds on exit 0.
- Triggers:
  - Default is 1 s while pending, then 30 s.
  - `sdk.trigger.cooldownTrigger(ms)` and `statusTrigger(defaultMs, {success, loading, …})`.
- Other:
  - `Daemons.runUntilSuccess(timeout)` is for bootstrap during init/actions.
  - `Daemons.dynamic(effects, fn)` is for runtime-varying daemon sets (2.0.4 breaking signature, CHANGELOG.md:87-107).
  - `SubContainer.withTemp(effects, image, mounts, name, fn)` runs one-off commands; `sub.exec`/`execFail`.
- Reactivity:
  - `fileModel.read(map).const(effects)` inside `setupMain` re-runs main and restarts the daemons whose spec changed.
  - `.once()` does not react.
  - `.onChange`, `.watch`, `.waitFor` are also available (DOCS209 main.md:104-135; file-models.md:115-166).
- Logs: a daemon's stdout/stderr go to the service logs (DOCSLIVE init.md "When it times out" tip). No log configuration API was found.
- Choosing between oneshot, init and migration: see the DOCSLIVE main.md table. App-level DB migrations such as `alembic upgrade` belong in a **oneshot**, not in `migrations.up`.

---

## 5. Backups (`startos/backups.ts`)

`export const { createBackup, restoreInit } = sdk.setupBackups(async ({effects}) => sdk.Backups.ofVolumes('main'))` (HELLO backups.ts). API is in `SDK/lib/backup/Backups.d.ts`.

- Builders:
  - `Backups.ofVolumes(...ids)`
  - `ofSyncs({dataPath:'/media/startos/volumes/<v>/…', backupPath:'/media/startos/backup/…', options?, backupOptions?, restoreOptions?, weight?})`
  - `withOptions({exclude, delete})`
  - `withPgDump(...)`, `withMysqlDump(...)`
- Chainable methods: `.addVolume(id, {options, backupOptions, restoreOptions, weight})`, `.addSync(...)`, `.setOptions`, `.setBackupOptions`, `.setRestoreOptions`.
- Exclusions use `SyncOptions = { delete: boolean, exclude: string[] }` (rsync patterns). The default is `{delete:true, exclude:[]}` (Backups.js:70-73). Example: `sdk.Backups.ofVolumes('main').setOptions({ exclude: ['cache', '*.tmp'] })`.
- Hooks: `setPreBackup(fn, weight?)`, `setPostBackup`, `setPreRestore`, `setPostRestore`. `fn(effects, phase: PhaseHandle)` (2.0.7).
- Progress weights: each rsync sync defaults to 80 (`DEFAULT_SYNC_WEIGHT`) and each hook to 10 (`DEFAULT_HOOK_WEIGHT`). A hook's phase exists only if the hook is set (CHANGELOG.md:46-61).
- **StartOS always stops the service for the backup and restarts it only if it had been running** (DOCS209 recipe-backups.md:3,10). A plain `ofVolumes` copy of a SQLite file therefore runs against a quiescent DB, including any `-wal`/`-shm` files, which are copied as normal volume files. A pre-backup `sqlite3 .backup` snapshot is therefore **not required**. It is possible if wanted: `setPreBackup(async (effects) => sdk.SubContainer.withTemp(effects, {imageId:'app'}, mounts, 'snap', s => s.execFail([...])))`. That usage is inferred from the API and has not been tested.
- Restore runs during init (`restoreInit` must be first in `setupInit`). Afterwards `setupOnInit` handlers see `kind === 'restore'`, and migrations run from the restored data version.

---

## 6. Init, uninit, versions and migrations

```ts
export const init = sdk.setupInit(restoreInit, versionGraph, setInterfaces, setDependencies, actions, /* custom setupOnInit handlers */)
export const uninit = sdk.setupUninit(versionGraph)
```
(HELLO `startos/init/index.ts`.)

- Handlers run in the order given. Tasks that reference actions must come after `actions` (DOCS209 versions.md:293-305).
- `setupOnInit(async (effects, kind, progress) => …)` where `kind` is `'install' | 'update' | 'restore' | null` (null = container rebuild or server boot) (DOCS209 init.md:1-63).
- **Init handlers are reactive** (DOCSLIVE init.md "Init Handlers Are Reactive"):
  - A `.const()` inside a handler re-runs that handler for the life of the container.
  - `kind` stays at its original value across re-runs.
  - Guard one-time secrets with "generate only if absent".
- Guard patterns:
  - `if (kind !== 'install') return` for install-only work.
  - `if (!kind) return` for install, update or restore, but not rebuild.
  - Seed file models with `merge(effects, {})`.
- If init fails (for example a `runUntilSuccess` timeout), StartOS restores the volumes from its pre-op backup, reverts the update or removes the failed install (DOCSLIVE init.md "When it times out").
- Progress: add phases on the shared `FullProgressTracker` with `progress.addPhase(name, weight)` and `setTotal`/`setDone`/`complete` (DOCS209 init.md:289-369).

### Versions (ExVer `upstream[-pre]:downstream`, optional `#flavor:`)
- `startos/versions/current.ts` exports `current = VersionInfo.of({ version:'1.2.3:0', releaseNotes:{en_US:…,…}, migrations:{ up: async ({effects, progress}) => {}, down: IMPOSSIBLE, other?: {'<range>': {up?, down?}} } })`. `.satisfies(v)` is available (`SDK/lib/version/VersionInfo.d.ts`).
- Wire it up with `VersionGraph.of({ current, other: [historicalVersions] })`.
- Upgrades from older versions: for every version whose `up` is not IMPOSSIBLE, the graph synthesizes a range vertex `<X` (or `>=prev && <X`). **Any lower installed version, declared or not and sideloaded or not, migrates to `current` in one hop** by running `current.up` once (DOCS209 versions.md:151-168).
- `canMigrateFrom`/`To` are derived; you do not author them.
- Rule (DOCSLIVE versions.md): a migration belongs forever to the version that introduced it. Before bumping, spin the old `current.ts` off into `vX.Y.Z_N.ts` and add it to `other`. Bumping in place over a migration silently deletes that migration.
- A fresh install does not run `up`.
- Git tag convention: `v<upstream>_<downstream>` (e.g. `v1.2.3_0`). The CI `extract-version` action derives it the same way (`st/.github/actions/extract-version/action.yml`).
- StartOS 0.3.x (v1 s9pk) to 0.4 upgrades: StartOS converts v1 packages (`s9pk/mod.rs` "Converting Package to V2"). I found no packaging-guide page on migrating data from a 0.3.5 package. **Unverified.**

---

## 7. File models, secrets and reactivity

- Factories:
  - `FileHelper.json(path, zodShape)`, `.yaml(path, shape, yamlOptions?)`, `.toml`, `.ini(path, shape, iniOpts?)`, `.env(path, shape)` (KEY=VALUE), `.xml(path, shape, opts?)`, `.string(path)`, `.raw(path, toFile, fromFile, validate)` (`SDK/lib/util/fileHelper.d.ts:88-115`).
  - `path = { base: sdk.volumes.<id>, subpath: 'store.json' }`.
  - Import `z` from `@start9labs/start-sdk`: objects are loose and keep unknown keys. (3.0.0) switches to `z.looseObject`.
- Reads: `.read(map?, eq?).once()`, `.const(effects)`, `.onChange(effects, cb)`, `.watch(effects)`, `.waitFor(effects, pred)`. A missing file returns `null`.
- Writes: prefer `.merge(effects, partial)` over `.write` (DOCS209 file-models.md:168-214). Give every key a `.catch(default)`.
- Secrets best practice:
  - Generate with `utils.getDefaultString({charset:'a-z,A-Z,0-9', len:N})`, never a hand-written RNG.
  - Do it in an install-only `setupOnInit` (internal secrets) or in an action (user-facing credentials).
  - Store them in `store.json` on a dedicated `startos` volume that is not mounted into the app, and back that volume up (DOCSLIVE file-models.md "store.json.ts").
  - Pass secrets to the app via `exec.env` or a generated config file.
- Prefer modelling the app's own config file directly over "store + env" when the app reads a config file (file-models.md "Design Guidelines").

---

## 8. Notifications, logs, properties, instructions, icons, i18n

- **Notifications** (1.5.0+, StartOS ≥0.4.0-beta.9): `sdk.notification.create(effects, {level:'success'|'info'|'warning'|'error', title, message, data?: markdown})`. They are not idempotent, so gate them. Use them sparingly (DOCS209 notifications.md; StartSdk.d.ts:86-127).
- **Properties/metrics:** there is no "properties" API in 2.0.9 (none in StartSdk.d.ts). Use actions that return results, or health checks with `loading` messages. There is no metrics API.
- **Logs:** daemon stdout/stderr go to the service logs (see §4).
- **instructions.md** is **required** at the package root: pack fails without it (pack.rs:265-280). It is shown in the service's Instructions tab. Its `## Documentation` bullets must be exactly `- [Title](URL) — words`, because Start9's support indexer parses them (DOCSLIVE writing-instructions.md).
- **README.md** is optional but packed into the s9pk if present (pack.rs:282-290). Its audience is AI/support agents (DOCSLIVE writing-readmes.md).
- **Icon:** a file named `icon.*` at the package root (svg/png/jpg/webp, ≤ 40 KiB; DOCS209 manifest.md:81-87). Pack errors on none or on several (pack.rs:195-228).
- **LICENSE** is required and packed as LICENSE.md (pack.rs:230,760).
- **assets/** must exist and is packed as `assets.squashfs`; `--no-assets` opts out (pack.rs:293-297,875-883). Mount it with `sdk.Mounts.of().mountAssets({...})`.
- **i18n:** `setupI18n(defaultDict, translations, 'en_US')` gives `i18n(key, params?)`, with `${name}` interpolation (`SDK/lib/i18n/index.d.ts`; REG listPackages.ts:60). The dictionary maps English strings to numeric ids and translations map ids per locale (HELLO `startos/i18n/dictionaries/*`). Wrap every user-facing string: action names and warnings, task reasons, health messages, interface names, and action-handler throws.

---

## 9. Signing, keys and sideloading

- start-cli (current, MASTER source, "1.1.0+" naming) has two keys:
  - The **identity key** `~/.startos/id.key.pem` (formerly `developer.key.pem`, auto-renamed; `developer/mod.rs:17-40`) authenticates to registries and servers.
  - The **workspace build key** `.startos/build.key.pem` (formerly `build-key`) signs every s9pk. `ctx.build_key()` walks **up from cwd** to the nearest `.startos/build.key.pem` and errors if there is no workspace (`context/cli.rs:214-223`; `s9pk/init.rs:20-26,599-614`; pack.rs:789).
- 2.0.9's `s9pk.mk` `check-init` still tests `~/.startos/developer.key.pem` and runs `start-cli init-key` (s9pk.mk:117-121). This is cosmetic and fixed in 2.0.10.
- **Registry publishing requires an authorized signer.** `registry package add` succeeds only if the uploader key is a registry admin or is in the package's `authorized` signer map, with a matching version range (`registry/package/add.rs:88-120`). Signers are managed with `start-cli registry package signer add|remove|list <id> <signer>` (start-os cli-reference.md:925-942). A package id is therefore effectively tied to its authorized signing keys on each registry.
- **Sideload/update on a device:** the OS verifies the s9pk signature and records its signer as `developer_key` (`service/mod.rs:699,752`; `service_map.rs:231,310`). I found **no code rejecting an update signed by a different key**. That comes from code inspection only; no device test was done.
- Sideloading is done from the StartOS UI ("Sideload") or with `make install`/`start-cli package install -s <file>` after `start-cli auth login` (DOCS209 makefile.md:167-199; start-os sideloading.md).
- **Start9 CI signing (MASTER workflows):**
  - The `DEV_KEY` secret (PEM) is written to `~/.startos/id.key.pem` and copied to `.startos/build.key.pem` in the checkout. The same key both signs the s9pk and authenticates registry writes (`st/.github/workflows/build.yml:81-101`; `release.yml` equivalent steps).
  - PR builds without `DEV_KEY` generate a throwaway key with `start-cli init-key`.
  - In the Community pipeline the fork's `DEV_KEY` is Start9's, per the satd README (§11). Not verified in Start9's settings.

---

## 10. Build and release

`s9pk.mk` (SDK root; include it from the Makefile after overrides):

| Target | Effect (s9pk.mk line) |
|---|---|
| `make` / `all` | `$(TARGETS)`, which defaults to `$(ARCHES)`. The default `ARCHES ?= x86 arm riscv` (15-19); override with `ARCHES := x86 arm`. |
| `x86`/`arm`/`riscv` | `start-cli s9pk pack --arch=<a> -o <id>_<arch>.s9pk` (67-79) |
| `universal` | Single multi-arch `<id>.s9pk` (61,71-74) |
| `install` | `start-cli s9pk select` picks the best `*.s9pk`, then `start-cli package install -s` (84-91). Needs workspace `.startos/config.yaml` `host.default` or `-H`. |
| `publish` | For each `*.s9pk`, `start-cli s9pk publish` (S3 upload plus registry index). **Requires s3cmd** (93-105). |
| `print-TARGETS` | Used by CI to fan out a matrix (58-59) |
| `clean` | (131-133) |

Build steps: `npm ci` → `npm run check` (tsc) → `lint.mjs` → `npm run build` (ncc into `javascript/`) → pack (123-129). The package id is scraped with awk from `startos/manifest/index.ts` (line 4). Required tools: start-cli, npm, git, jq, and a running Docker plus squashfs-tools (DOCS209 environment-setup.md).

### Start9 reusable workflows (package repo calls them `@master`)
- `build.yml`
  - Inputs: `FREE_DISK_SPACE`. Secret: `DEV_KEY` (optional).
  - Runs `npm ci`, discovers `make -s print-TARGETS`, and runs one job per target (arm targets on `ubuntu-24.04-arm`). Artifacts are the `*.s9pk` files.
- `release.yml`
  - Inputs: `TAG`, `FREE_DISK_SPACE`, `RELEASE_REGISTRY`, `S3_S9PKS_BASE_URL`. Secrets: `DEV_KEY` (required), `S3_ACCESS_KEY`, `S3_SECRET_KEY`.
  - Builds the matrix, creates a GitHub Release with the s9pks and changelog from the manifest `releaseNotes`, and removes an existing same version from the registry.
  - Publishes one of two ways: via S3 (`start-cli --registry R --s9pk-s3base S s9pk publish`, plus GitHub mirrors), or with no S3 via `start-cli registry package add <s9pk> --url <GitHub release asset URL>`.
- `tagAndRelease.yml`
  - Adds a required `REFERENCE_REGISTRY` input.
  - On a master push it skips if the version already exists in the reference registry, otherwise force-pushes the tag and calls release.yml.
- `syncNext.yml` keeps a `next` branch.
- The template callers are in HELLO `.github/workflows/`. The template `build.yml` now passes no DEV_KEY.

**Can a non-Start9 repo use them?** Mechanically yes. They are public reusable workflows referenced as `Start9Labs/start-technologies/.github/workflows/*.yml@master`, and third-party repos (e.g. remcoros/*, MostroP2P/mostro-startos) include `s9pk.mk` the same way. My claim about GitHub allowing public reusable workflows from any repo is general GitHub knowledge; I did not check it here. Constraints:
1. They hard-code the **repo root**: `npm ci`, `make` and `*.s9pk` at the checkout root, and `extract-version` reads `startos/manifest/index.ts` and `startos/versions/current.ts` relative to the root. There is no `working-directory` input.
2. Publishing needs your own registry, where your `DEV_KEY` public key is an authorized signer, plus optional S3.
3. They track `@master` and the latest start-cli, so they can change under you.

### Getting into the community registry (DOCSLIVE publishing.md)
1. Email submissions@start9.com with a public repo.
2. Start9 forks it into **Start9-Community** and reviews it as a PR on the fork. The fork becomes upstream.
3. A merged PR auto-builds and publishes to **community-beta** (`https://community-beta-registry.start9.com`).
4. You ask by email or issue for promotion to **community** (`https://community-registry.start9.com`).

Alternatives: self-host `startos-registry` (REG), or just ship `.s9pk` files on GitHub Releases for sideloading.

---

## 11. Package in a subdirectory of the app repo?

The tooling allows it. Evidence:
- `s9pk.mk` uses paths relative to the package dir; `GIT_DIR := git rev-parse --git-dir` works in subdirectories and worktrees (s9pk.mk:4-14).
- `pack` takes an optional PATH (default cwd).
- `GitHash` runs `git rev-parse HEAD` in the package dir. Note that `git status --porcelain` there covers the **whole** repo, so any uncommitted app change marks the build `-modified` (`s9pk/git_hash.rs:19-45`).
- The signing key is found by walking **up** to the nearest `.startos/build.key.pem` (init.rs:599-614). It can live above the repo, e.g. `~/work/.startos/`, and must never be committed.
- `init-workspace` **refuses to run inside a package repo** and suggests the parent (init.rs:118-134). "Package repo" is detected by walking up for a `package.json` containing `@start9labs/start-sdk` or a `startos/manifest/` dir (init.rs:450-483). BitcoinTX's root `package.json` has no start-sdk. Create the workspace at, or above, the directory that contains the repo.
- dockerBuild can point at the app repo: `workdir: '../..'`, `dockerfile: '../../Dockerfile'` (§1).

Caveats:
- Start9's **reusable CI workflows assume the package is at the repo root** (§10).
- Start9's registry **expects one repository per package**. The real-world example **epochbtc/satd** keeps its package in `contrib/packaging/startos/`:
  - Its README says the package is "published from its own repository (`epochbtc/satd-startos`) — Start9's registry expects one repository per package". `contrib/packaging/sync-store.sh` copies the subdirectory into a clean clone of that repo.
  - Its `.github/workflows/` inside the subdirectory are "inert here, since GitHub only runs workflows at a repository's root" and gated on `github.repository_owner == 'Start9-Community'`.
  - Its monorepo CI runs only `npm ci`, `npm run check` and `npm run build` with `working-directory: contrib/packaging/startos`.
  - (`/tmp/claude-0/epochbtc_satd/contrib/packaging/startos/README.md:1-12,205-230`; `.github/workflows/appliance.yml:240-262`.)
- A second example is `btcblake2b/wallet` at `packaging/start9/` (found via GitHub code search; not inspected).
- DOCSLIVE project-structure.md ("The Package Repo Is Not a Fork of the Application") argues against copying app source into a package repo. A subdirectory package inside the app repo is the inverse case and is not addressed there.

---

## 12. Things I could not verify
- Runtime behaviour on a real StartOS 0.4.0.1 box: nothing was installed. That includes UI rendering of `Value.file`, multiple interfaces on one binding, and the proxy `auth` gate with an MCP client.
- Whether StartOS 0.4.0.1 enforces signer continuity on sideloaded updates. Code shows none (§9).
- Migration of data from 0.3.5-era packages (§6).
- Whether Start9-Community CI uses Start9's own DEV_KEY. Asserted by the satd README and implied by the workflows, not confirmed by Start9 docs.
- Community-registry policy on monorepo or subdirectory packages beyond satd's statement.
