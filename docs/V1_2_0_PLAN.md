# v1.2.0 plan: StartOS integration, translations, Start9 CI, then submit

> **Temporary file. Delete it in the v1.2.0 release commit** (and the memory
> that points here). A working plan, not documentation: once v1.2.0 ships,
> the CHANGELOG, READMEs and code are the record.

Written 2026-09-27, after v1.1.0 (price source setting, date-free price
history, PDF fix, security tightening, connector pinned). Approved by the
owner as release 2 of a two-release plan to ready BitcoinTX for Start9's
community marketplace. The owner's own use comes first; contributing to the
community is the bonus. Work on `develop` (CLAUDE.md "Branches").

Start a session with:

> Read `docs/V1_2_0_PLAN.md` and `CLAUDE.md`. Implement the plan, and stop
> if anything in the code contradicts it.

## 0. The owner's mempool address (answered 2026-09-27)

The address the owner uses is **`https://<server LAN IP>:<port>`** (a high
port, 5xxxx); without the port it doesn't reach mempool. `.onion` untested.
So StartOS serves it over https with its own root CA, which BitcoinTX's
outbound client doesn't trust: in 1.0.3 it most likely never answered and
the public sites were used silently. Confirm on 1.1.0 with the fallback off
(the log shows "Own mempool server … CERTIFICATE_VERIFY_FAILED" if so).
Item 1 (bridge address, plain http inside StartOS) removes both the
certificate and the LAN IP (which can change with DHCP). The earlier
question, kept for context:


The owner connected their mempool on StartOS with **a `.local` address with
the port on the end** and it "worked" in 1.0.3. Likely it was `https://…
.local:PORT`, which BitcoinTX can't verify (its outbound client doesn't trust
the StartOS root CA; `outbound.own_node_client` uses the default CA bundle),
and 1.0.3 then quietly fell back to public sites. 1.1.0 no longer falls back
unless "Fall back to public price sites" is on (the StartOS instructions say
to turn it on for an https address for now). **Ask the owner for the exact
format of every address type** StartOS shows for mempool (LAN `.local`, IP,
Tor, bridge, http vs https, ports) and whether BitcoinTX's log shows
"Own mempool server … failed". Item 1 below makes this moot on StartOS, but
the answer decides whether a CA option is also worth adding for other setups.

## 1. Mempool and Tor from StartOS (no forced dependency)

Research (2026-09-27, start-sdk 2.0.9; sources in the session that wrote
this): service-to-service calls use `sdk.host.getBridgeAddress(effects,
{packageId, hostId, internalPort, ssl?}).const()` → `10.0.3.1:<assigned
port>`, plain http, null while the package is absent (heals on restart).
Never hardcode ports or use `<id>.startos` names.
- mempool-startos (`Start9Labs/mempool-startos`, mempool v3.3.1): host
  `main`, internal port 8080, http; nginx forwards `/api/v1/*`. Historical
  prices are on by default (indexing on). Precedent for calling it:
  am-i-exposed-startos `main.ts` (ssl:false, waits for its `webui` health).
- Tor (`tor-startos`): a SOCKS5 proxy for other services, host `socks`,
  port 9050, bridge-only. mempool-startos has a "Route External Requests
  Over Tor" toggle. Use `fallbackPort: 9050` so the proxy stays set when Tor
  is gone (fails closed, like am-i-exposed).
- Optional dependencies: manifest `dependencies: { mempool: { description,
  optional: true, metadata: { title, icon } } }` (description is a locale
  object); `dependencies.ts` returns a dependency **only when the user chose
  it** (mempool `dependencies.ts` pattern). Nothing is forced on others.
- StartOS also has a built-in per-service **Set Outbound Gateway** (VPN) —
  document it, nothing to build.

Build:
- **App:** env overrides `BTCTX_PRICE_SOURCE`, `BTCTX_MEMPOOL_URL`,
  `BTCTX_MEMPOOL_FALLBACK`, `BTCTX_PROXY_URL` read in `outbound.load()`;
  when set, `GET /api/settings/network` says `managed: true` and Settings /
  the first-login question show them read-only ("set in StartOS: use the
  Price source action"). Tests for precedence.
- **Package** (`startos/startos/`): `store.json` gains `priceSource`
  (`unset|off|public|mempool`), `mempoolFallback`, `useTor`; a new action
  **Price source & privacy** (`sdk.Action.withInput`, `InputSpec`: select
  Off / Public price sites / My Mempool on this server; toggle fallback;
  toggle Tor), prefilled from store.json; an `important` task created on
  install pointing to it (after Show Credentials); `dependencies.ts` adds
  `mempool` (`kind: 'running'`, healthChecks `['webui']`) / `tor` only when
  chosen; `main.ts` resolves the bridge addresses with `.const()` and passes
  `BTCTX_*` in `appEnv`. Pass i18n params as strings (2.0.9 throws on numbers).
- **Old default logins:** an update init that finds the StartOS install
  still on admin/password (installs from before generated passwords) runs a
  new CLI `set-password --if-default` with a generated password and raises
  the critical Show Credentials task (1.1.0 made that login need the setup
  code from the service log).

## 2. Translations

Fill `startos/startos/i18n/dictionaries/translations.ts` for es_ES, de_DE,
pl_PL, fr_FR: every package string (action names/descriptions/messages,
health, interfaces, tasks). Start9's intake review translated all strings
for other packages; "localization" is a review criterion. The app itself
stays English / US tax forms (the listing says so).

## 3. Start9's standard workflows (in the mirror)

Replace `startos/.github/workflows/{ci,release}.yml` with Start9's four thin
callers from `Start9Labs/hello-world-startos`, pointed at `main`:
`build.yml` (PR → `start-technologies/.github/workflows/build.yml@master`),
`tagAndRelease.yml` (push to main, ignores `*.md`; needs variable
`REFERENCE_REGISTRY` and secret `DEV_KEY`), `release.yml` (tag `v*.*`),
`syncNext.yml`. They run in DigiMonk73/BTCTX-StartOS (package at repo root).
Owner's manual step: add `DEV_KEY` (the same key as BTCTX-MCP's secret) and
`REFERENCE_REGISTRY` in the mirror's GitHub settings (look up the value in
the template docs when implementing). Our main-repo `release.yml` keeps
building dmg/zip/s9pk and syncing the mirror.

## 4. Staying in sync with Start9

Submission: email submissions@start9.com with the mirror link. Start9 forks
it into Start9-Community and reviews it as a PR on the fork; "the fork is the
upstream from that point on". Authors then contribute by PRs from their own
fork; Start9 merges them (hours to a day). Start9 changes templates about
monthly (`syncNext`) and bumps SDKs by PRs on forks.
- New `scripts/start9-pull.sh`: fetch Start9-Community's `main`, show the
  diff against `startos/`, apply it on `develop` (so our next mirror sync
  never undoes their changes).
- Release flow after the fork: release here → sync the mirror → open a PR
  from the mirror to their fork. Document in `startos/UPDATING.md` (plus
  Start9's two required sections "Determining the upstream version" and
  "Applying the bump") and CLAUDE.md "Releasing".

## 5. StartOS docs polish

- `instructions.md`: link a StartOS-relevant guide (the main README's
  first-login section describes Docker); Privacy section mentions the new
  action, own mempool, Tor, Set Outbound Gateway; remove the https note
  once item 1 lands.
- Move the one-time "switch from password" notes (instructions.md, the
  Connect an AI action message) into release notes only; release notes end
  with a changelog link; rename version files to `v0.8.0_0.ts` /
  `v0.9.0_0.ts` (exports `v_0_8_0_0`, `v_0_9_0_0`); README "Limitations"
  opens with a sentence; `startos/LICENSE` copyright line = the upstream's.

## 6. Verify, release, submit

- Tests for everything above; `make check`, `make e2e`, StartOS checks.
- Owner tests on the box: fresh install (Show Credentials, then the price
  task), My Mempool (confirm in the log that the bridge address answers and
  no public site is asked), Tor, fallback, backup + restore, update from
  1.1.0, uninstall + reinstall.
- Release v1.2.0 (CLAUDE.md "Releasing"), landing page, then the owner
  emails Start9.

## 7. The connector on PyPI (first published with v1.2.0)

**Done on `develop` (2026-09-27):** the owner set up PyPI (two-factor login
and the pending trusted publisher: GitHub, `btctx-mcp`, DigiMonk73,
BTCTX-MCP, `release.yml`, env `pypi`); the GitHub environment `pypi`, the
`pypi` job in `release.yml`, the package metadata, absolute README links and
the `uvx btctx-mcp==X.Y.Z` setup texts are in. **Left:** confirm at the
v1.2.0 release that PyPI has 1.2.0. The steps, for the record:
- create the GitHub environment `pypi` on BTCTX-MCP (`gh api -X PUT
  repos/DigiMonk73/BTCTX-MCP/environments/pypi`);
- add a `pypi` job to `.github/workflows/release.yml` (needs `check`;
  skipped on `-N` package-only revisions and existing releases; `permissions:
  id-token: write`; `python -m build mcp_server`;
  `pypa/gh-action-pypi-publish@release/v1` with `packages-dir`);
- make `mcp_server/README.md`'s relative links absolute (it becomes the PyPI
  page);
- switch the setup texts (`frontend/src/utils/aiSetup.ts` + tests,
  `startos/.../connectAi.ts`, `mcp_server/AI_SETUP.md`, READMEs) from
  `--from "git+…@vX.Y.Z#subdirectory=mcp_server"` to `uvx btctx-mcp==X.Y.Z`
  (still pinned to the app's version; the mismatch notice's wording follows);
- after the release: `pip index versions btctx-mcp` shows 1.2.0.
