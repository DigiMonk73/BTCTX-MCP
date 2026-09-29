# Changelog

All notable changes to BitcoinTX are documented in this file.

## [Unreleased]

### Fixes
Found testing the published 1.2.1 on a StartOS VM (2026-09-29).
- **The Sats Converter no longer shows "BTC Price: $0.00" without a
  price.** With prices off it says "Prices off", after an error or for a
  day with no stored price "No price", and the USD field empties instead of
  keeping an old figure (BTC and sats still convert).
- **My Mempool not answering is an error, not "Prices off".** With your
  Mempool chosen but missing or not answering (and the fallback off), the
  Dashboard said "Prices off"; it now says "Error", and hovering it shows
  why (e.g. install and start Mempool). The message lost its doubled
  brackets.
- **Clearer messages when no price is stored.** A transfer's missing fee
  value now names the form's **Fee value (USD)** field (and `fee_usd` for
  imports), and a new Spent withdrawal without proceeds is no longer told
  to "edit that transaction".
- **The complete tax report says where its prices come from.** It claimed
  "the average market value at the time of disposal"; it now says values
  are the ones entered, a blank one comes from that day's stored daily
  price, and dates are in the tax timezone (named).
- **Privacy fixes from an audit of 1.2.1** (`docs/temp/privacy-audit.md`):
  - The AI connector no longer writes request addresses to the AI app's
    log files; past-price lookups named your transaction dates there.
  - An `.onion` mempool address needs the proxy: it's refused without one
    (it was looked up through the normal DNS, which then saw the name).
  - An encrypted backup no longer passes through a plain copy in the
    system's temp folder, and a restore's decrypted file is owner-only from
    the moment it's written.
  - Making reports no longer logs how many transactions, disposals and
    lots each year has (now only at the DEBUG log level).
- **Keyboard focus shows in the Mac app on older macOS.** On Safari before
  15.4 (macOS 10.15 to 12.2) no focus ring was drawn at all; the browser's
  own ring now stays there, and newer versions keep the gold one.
- **AI connector fixes from a bug hunt (2026-09-29):**
  - Changing a transaction's date with the AI reads it as adding one does:
    a date alone is midday in your tax timezone, a time without a timezone
    is a time there. It was read as UTC, so in the US a sale moved to Jan 1
    landed on Dec 31, in the previous tax year.
  - Finding transactions by date with the AI uses days in your tax
    timezone: a 9 pm Dec 31 entry in Chicago is on Dec 31, not Jan 1.
  - Pay the AI adds as an Income deposit into Bank or Exchange USD is no
    longer valued at the BTC price ($5,000 became $250 million of income);
    likewise a Spent or Gift withdrawal from a USD account. Only BTC
    accounts are valued at the day's BTC price, and the preview (and the
    CSV import) no longer says such a USD entry will be.
  - A time ending in " UTC" (`2025-01-01 03:00:00 UTC`) given to the AI is
    read as UTC, as the CSV import reads it; it was read in the tax
    timezone, hours off and sometimes in the wrong tax year.
  - When BitcoinTX's address redirects (e.g. `http://` to `https://`), the
    connector says so and which address to set in `BTCTX_URL`, instead of
    failing with an unclear error or a blank price. It still never follows
    a redirect, so the AI key only goes to that address.

Found in a bug hunt of the imports (2026-09-29):
- **Export CSV then Import CSV keeps the order of same-time entries.** The
  import put them in a fixed type order (moves before sales), which could
  change which coins a sale used and its gain; rows at the same time now
  go in the file's order (the export's is the ledger's).

## [v1.2.1] - 2026-09-28 - Fixes from testing 1.2.0: prices stay off until you choose, restore keeps your login, reports say why

### Fixes
- **Adding transactions before choosing a price source no longer turns
  public price sites on.** Since 1.1.0, an install with transactions but no
  price choice yet was taken for one from before 1.1.0 (when public sites
  were on by default), so its next restart, e.g. an update, switched it to
  **Public price sites** and asked them for prices, although you never
  chose that. Now only an install that stored past prices before 1.1.0
  keeps public sites; any other stays unasked until you choose. If you
  added entries before answering the price question and BitcoinTX has
  restarted since, check **Settings → Privacy & Network** (on StartOS, the
  Price Source & Privacy action decides instead). Found testing the 1.2.0
  package on a StartOS VM.
- **The complete tax report works with price lookups off.** It looked up
  the Jan 1 BTC price even when nothing was held then, and a missing price
  failed the whole report; a missing Dec 31 price valued the holdings at
  $0. Holdings with no price for that day now read "not priced", and the
  rest of the report is unchanged.
- **The complete tax report's Beginning of Year Holdings were wrong**
  whenever BTC had moved or been sold in earlier years: lots were counted
  twice (in the checklist's ledger, 1.8797 BTC on Jan 1, 2024 instead of
  the 0.9898 held on Dec 31, 2023). They are now taken the same way as the
  year-end holdings, so Jan 1 always matches the previous Dec 31. Only this
  section of that report was affected: IRS forms and gains were right.
- **Export CSV now imports back to the same ledger.** The export had no
  column for a BTC fee's USD value, a gift's fair market value or the
  Broker form override (all added after the export was written), so a
  re-import priced every BTC fee again at that day's price, changing gains,
  lost Broker form choices and failed outright with price lookups off. The
  export, the import and the template now share one list of columns, with
  three new optional ones at the end: `fee_usd`, `fmv_usd` and
  `broker_reporting`. Older CSV files import as before. A CSV import a row
  can't be saved from (e.g. a BTC fee with no price to value it) now says
  why instead of answering with a server error. The CSV import guide
  describes the new columns and no longer calls a BTC deposit's basis
  optional.
- Deleting a transaction that later ones depend on (a buy whose BTC a later
  sell or transfer spends) is refused and changes nothing. Before, it showed
  an error but deleted the row anyway, and every later save then failed
  until the row was entered again. The message now says why: "Not deleted:
  later transactions depend on this one. …".
- Restoring a backup made before 0.9.2 with the wrong password now always
  says "Wrong password?". About 1 time in 256 it said the file wasn't a
  BitcoinTX backup instead (the live database was never touched either way).

- **The log is readable again.** Every health check (StartOS asks every 30
  seconds) logged two database lines, half of a running install's log. It
  now logs nothing.

- Loading the dashboard asked for the live price twice (the dashboard and
  the sidebar converter at the same moment). Requests at the same moment
  now share one.

- The dashboard's **BTC Cost Basis** is now labeled **Avg. Cost per BTC**:
  it always was the average cost of one bitcoin you hold, not your total
  cost.

- The login page shows **Create account** only on a fresh install that
  still has the default login. Once the account is set up, that page
  resets it (deleting every transaction, after asking for the current
  password), which the link didn't say; Settings still has Reset
  Username & Password.

- **A report that can't be made now says why.** Reports showed only "Failed
  to generate the report" and dropped the reason. They now show it, and
  when an old withdrawal's network fee (or a Spent withdrawal's proceeds)
  has no USD value and no price is available, the message names that
  transaction, e.g. "Withdrawal of 0.01 BTC on 2024-06-01: its network fee
  has no USD value (edit that transaction to enter it)".

- **Restoring a backup file in the app keeps your current login.** It
  brought back the backup's username and password, so a password changed
  since stopped working, and on StartOS Show Credentials showed one that
  no longer logged in. Like the AI key, the login in use now stays; the
  ledger and settings come from the backup. StartOS's own backups were
  never affected (they restore the login and the ledger together).

- With prices off, the dashboard's Unrealized Gains/Losses said
  "Loading..." forever; it now says "Prices off" (or "No price" when a
  lookup failed).

- When public price sites go through a proxy that's down (e.g. Tor
  stopped), the error says so and asks whether Tor is running, instead of
  only "No public site answered".

- Deleting a transaction asks "Are you sure?" once, not twice.

- **Export CSV** has a fourth new optional column, `fee_usd_typed`: whether
  a BTC fee's USD value was typed (yes) or that day's price (no). A
  re-import marked every fee value as typed, so editing such a
  transaction's date later kept the old value instead of pricing it
  again. Files without the column import as before.

- A missing file (the browser's `/favicon.ico`, an outdated script after an
  update) is a 404 instead of the app's page.

- **Sats Converter:** a price you type in Manual mode is no longer replaced
  by the starting price arriving late (on a slow server it could land after
  you had typed yours).

### Development
- `docs/AGENT-TESTS.md`: the release tests an AI agent runs on a StartOS VM
  before each release (install, actions, the update from the last release,
  backups, price sources, TLS, the MCP connector, the Mac app), against a
  14-transaction ledger whose every figure is known, with its known issues.
- Dependabot opens weekly pull requests against `develop`, grouped per
  directory (Python in `backend/`, `mcp_server/` and the dev tools, npm in
  `frontend/` and `startos/`, GitHub Actions). It leaves the StartOS SDK and its service
  packages, `@playwright/test` and the deferred upgrades alone
  (`docs/MAINTENANCE.md`, "Dependabot").
- First updates taken: uvicorn 0.54.0; vitest 5.0.2,
  eslint-plugin-react-refresh 0.5.7, globals 17 (frontend); prettier, ncc and
  the Node types (StartOS package build); GitHub Actions on their current
  majors (Node 24).
- The release job downloads its two artifacts by name, so a Docker build
  record can't get mixed in.
- `make preview` runs the checked-out code in a browser on a throwaway
  database with offline test prices; `make docker-smoke` builds the Docker
  image locally and runs CI's container checks on it (`docs/TESTING.md`).

## [v1.2.0] - 2026-09-28 - StartOS: your own Mempool and Tor in one action, translated package; connector on PyPI

### StartOS: your own Mempool and Tor, chosen in one action
- **New action: Price Source & Privacy.** Choose **My Mempool on this
  server**, **Public price sites** (optionally **over Tor**), **Off**, or
  **Choose in BitcoinTX**. A fresh install asks right after Show
  Credentials; updating installs get an optional reminder. What you choose
  there shows read-only in the app (Settings → Privacy & Network).
- **Your Mempool on the same server now just works.** BitcoinTX reaches it
  inside StartOS, so there's no address to copy, no https certificate that
  fails, and no LAN address that can change. This replaces the 1.1.0 advice
  to turn on the fallback for `.local`/https addresses (which, with the
  fallback off, meant no prices at all). Mempool and Tor are optional
  dependencies, only while you use them.
- **Tor for public sites:** with the Tor service installed, requests to
  public price sites go through it, so they never see your IP address. If
  Tor stops, those requests fail rather than go out directly.
- **Old default logins retired.** An install from before generated passwords
  that still had admin/password gets a generated password at this update,
  and StartOS asks you to copy it (Show Credentials) before starting.
- **Translated:** every action, task and message of the package in Spanish,
  German, Polish and French (the app itself stays English, US tax forms).
- The package follows Start9's conventions for the community registry: its
  mirror (DigiMonk73/BTCTX-StartOS) runs Start9's standard build and release
  workflows, and changes Start9 makes to their fork come back with
  `scripts/start9-pull.sh`.

### Price settings the server can set
- `BTCTX_PRICE_SOURCE`, `BTCTX_MEMPOOL_URL`, `BTCTX_MEMPOOL_FALLBACK` and
  `BTCTX_PROXY_URL` (Docker too): when set, they replace Settings →
  Privacy & Network, which shows them read-only; your stored settings come
  back once they're removed. An invalid value turns lookups off. See
  docs/STARTOS_COMPATIBILITY.md.
- The log now says where each download of past prices came from ("Price
  history from your mempool server: N days", "… from public site bitstamp"),
  so you can check no public site was asked.

### Fixes
- **Recalculate Ledger (StartOS action, `python -m backend.cli`) can look up
  a missing day's price.** The maintenance commands never read the price
  settings, so they behaved as if no source was chosen.

### AI connector on PyPI
- The connector is published to PyPI as
  [`btctx-mcp`](https://pypi.org/project/btctx-mcp/) with every release, by
  trusted publishing (no token is stored anywhere). The setup prompt,
  configurations, StartOS action and docs now install it with
  `uvx btctx-mcp==X.Y.Z`, still pinned to your BitcoinTX version; nothing
  needs `git` on your computer any more. Versions before 1.2.0 stay
  installable from GitHub (`uvx --from "git+…@vX.Y.Z#subdirectory=mcp_server" btctx-mcp`).

## [v1.1.0] - 2026-09-27 - Privacy: choose your price source, no dates in lookups; security tightening

### Privacy: you choose where prices come from, and no lookup reveals a date
- **Nothing is contacted until you choose.** A fresh install asks, right
  after the first login, where Bitcoin prices come from: **My mempool
  server**, **Public price sites**, or **Off** (Settings → Privacy &
  Network). Before that the dashboard says "Prices off". Installs from
  before 1.1.0 keep what they did.
- **Your own mempool server** now also gives past prices (its hourly record
  at 00:00 UTC), and it's used *only*: the public sites are asked when it
  can't answer only if you turn on **Fall back to public price sites**. A
  mempool server on your network is reached directly, not through the proxy
  (an .onion still is).
- **Past prices never reveal your dates.** Before, a missing day started a
  ~1,000-day download that began exactly 500 days before it, so the site
  could work out the date, and the Coinbase backup never covered the day,
  so BitcoinTX often asked for the day by name. Now the public sites send
  the whole daily history once, in the same requests for every install, and
  after that only "the latest days". The single-day lookups (CoinGecko,
  Kraken, CoinDesk) are gone. Days before 2011-08-18 (Bitstamp's first) have
  no public price: type the value in.
- The live price is asked at most once a minute however many tabs are open,
  and the sidebar converter doesn't ask while its tab is hidden.
- **Correction:** the 1.0.3 README, StartOS docs and website said that
  download kept lookups from pointing at your dates; it didn't, as above.
- **StartOS:** a mempool address starting with `https` (the `.local` ones)
  doesn't answer BitcoinTX yet (it can't check StartOS's own certificate);
  1.0.3 then quietly used the public sites. Turn on **Fall back to public
  price sites** with such an address for now; a direct connection inside
  StartOS comes next.

### Security
- **PDF reports can't be made to fetch anything.** Text stored in a
  transaction (for example from an imported file or an AI) could make the
  server contact any web address while drawing a report, skipping the
  proxy. Report text is now escaped and the PDF library may fetch nothing
  remote. A deposit's source must be one of the listed values. The IRS forms
  (filled by a different tool) are unchanged.
- **Docker/source first run: a setup code.** Until you set your own login,
  logging in with admin/password or claiming the account needs a one-time
  code from the log (`docker logs`) or `/data/setup-code.txt`, so nobody
  else on the network can claim it first. An older install that still uses
  admin/password: the login page asks for the code; log in, then change the
  password in Settings (your transactions are untouched).
- **Login protection:** repeated wrong passwords make everyone wait longer
  (1 s up to 5 min); new passwords need at least 12 characters (existing
  ones still work); changing the password needs the current one.
- **Requests from other sites are refused:** a page on another site (or
  another app on the same server) can't make your browser restore a backup
  or import a file. Cross-origin requests (CORS) are off unless configured.
- A restore refuses files over 1 GiB and unreasonable key-strength settings;
  two old example session keys from the project's history are refused; an
  empty session key file is replaced.
- CSV exports can't start a spreadsheet formula; Docker and StartOS keep no
  access log (request paths can hold dates), and transaction dates left the
  normal log.

### AI connector
- The setup texts pin the connector to your BitcoinTX version (`@vX.Y.Z`)
  instead of following `main`: your AI app runs exactly that code and
  fetches nothing new at each start. After an update, every tool reply says
  which version to set. (PyPI will come once publishing is set up.)

## [v1.0.3] - 2026-09-27 - Security: AI keys for every edition

### AI keys instead of passwords
- **The AI connector no longer uses your password.** On Docker and StartOS,
  **Settings → Connect an AI Assistant** now has the **Let AI assistants use
  BitcoinTX** switch (off by default) and **Create AI key**: a key shown
  once, which you paste into your AI app's settings. **New key** replaces
  it, **Revoke** deletes it. BitcoinTX stores only a hash of it. The Mac app
  keeps its automatic key file.
- **The key can do only what the AI tools need:** read the ledger, add,
  change or delete single entries, recalculate, and make a backup copy. It
  can't log in, change the username or password, restore or download a
  backup, export or import files, delete everything, apply Ledger Review
  fixes, open reports or change settings: those answer 403 (an allow-list,
  so anything added later is closed to the key too).
- **New AI tool `backup_ledger`:** a copy of the database in BitcoinTX's
  `backups` folder on your server before a big change (the newest 3 are
  kept, apart from the pre-upgrade copies; one a minute).
- **A restore keeps the current AI key and switch**, so an old backup can't
  bring back a key you revoked.
- **The connector refuses a password.** While `BTCTX_PASSWORD` is in its
  settings, every tool says how to switch to a key and sends nothing.
- **Breaking:** the undocumented `API_KEY` setting (`X-API-Key` header) is
  gone; use an AI key.
- The StartOS **Connect an AI Assistant** action no longer shows your login;
  its configuration has a `YOUR_BITCOINTX_AI_KEY` placeholder.

### AI connector updates itself
- The setup prompt, configs and docs install the connector from this repo's
  `main` branch, which now holds released code only: uvx checks it each time
  the AI app starts, so you never edit a version again. Pinning `@vX.Y.Z`
  still works.
- The connector has the app's version number, and when the two differ every
  tool reply starts with a line saying so and what to do (restart the AI
  app, or update BitcoinTX).

**If you use an AI assistant with BitcoinTX on Docker or StartOS:** your AI
app's settings file held your BitcoinTX password in plain text. After
upgrading: (1) in BitcoinTX, Settings → Connect an AI Assistant, turn on AI
access and create an AI key; (2) in your AI app's settings, replace
`BTCTX_PASSWORD` (and `BTCTX_USERNAME`) with `BTCTX_AI_KEY` set to that key,
and delete the password; (3) change your BitcoinTX password (Settings →
Reset Username & Password), or on StartOS run **Reset Login Credentials**,
because the old one sat in that file. Mac app users: nothing to do.

### Documentation
- The MCP README no longer says a local model means "nothing leaves your
  computer": what the AI reads stays there, but BitcoinTX still looks up
  prices unless Live data is off. It also says a preview can look up prices.
- **Correction:** v0.9.2 said past-day price requests "no longer name
  individual transaction dates", and the README said lookups "don't reveal
  your transaction dates". A missing day is filled by one download of about
  1,000 days, but if that download fails BitcoinTX asks CoinGecko, Kraken or
  CoinDesk for the single day, which names it. The README now says so; Live
  data off sends no request at all.
- The StartOS listing says BitcoinTX sends your ledger nowhere (instead of
  "your ledger stays on your server", which a cloud AI would contradict), in
  all five languages. The README and StartOS docs list every outside service
  (single-day fallback and block-height sources included).
- `docs/startos-research/btctx-requirements.md` (it described v0.8.0) moved to
  `docs/archive/`.

### Development
- Work now happens on `develop`; `main` holds released code only and moves
  by fast-forwarding to `develop` (`CLAUDE.md`, "Branches"). The pre-push
  hook refuses a push to `main` of anything not already on `develop`, and
  any delete, rewind or force-push of `main`; the release workflow refuses a
  release commit that isn't on `main`.

## [v1.0.2-1] - 2026-09-27 - StartOS package: translated listing, ready for the Start9 Community Registry

Package-only update; BitcoinTX itself is unchanged.

- The StartOS store listing and release notes are also in Spanish, German,
  Polish and French. The app stays in English and produces US (IRS) tax
  forms, which the listing says.
- The listing's website link points to the BitcoinTX site.
- The package README names no versions (Start9's rule): old upgrade paths
  are described by what changed.

## [v1.0.2] - 2026-09-26 - AI privacy: cloud or local model, Mac AI access off by default

### AI assistant privacy
- **Settings → Connect an AI Assistant** now opens with a warning: the AI's
  model reads what BitcoinTX hands it (transactions, balances, gains) and
  whatever you paste, and with a cloud AI (Claude, Grok…) that goes to the
  provider. It points to local-model apps (LM Studio, Goose with Ollama).
- The AI setup guide tells the AI to say this before it installs anything;
  the MCP README has a "Privacy: cloud or local model" section with LM Studio
  and Goose setup; the README and the StartOS instructions carry the warning.
- **Mac app: AI assistant access is now off by default**, including on
  installs upgraded from 0.9.2–1.0.1 that never touched the switch. If you
  use an AI with the Mac app, turn on **Settings → Connect an AI Assistant →
  Let AI assistants use BitcoinTX** once; until then the AI gets "AI
  assistant access is turned off". A line under the switch says what it
  allows. The docs say AI entry is optional, what the switch
  does, and that Docker/StartOS have no switch (the server logs in with the
  password).
- StartOS: the MCP API address, the Connect an AI Assistant action and the
  package description say the same, and name LM Studio. Text only; AI access
  on StartOS still works by username and password, as before.

### Documentation
- Install from the release downloads (macOS `.dmg`, `btctx.s9pk`, the
  `ghcr.io/digimonk73/btctx-mcp` image) instead of building; README features
  now include Ledger Review, stored price history and Privacy & Network; the
  upgrade steps use Ledger Review; price and outbound-request sources updated.
- The AI's ledger guide: income with no price available is refused (ask the
  user), a withdrawal's BTC fee is taxable even for Gift, Donation and Lost,
  River's Received is net of its fee, and when to use `review_ledger`.
- Mac app docs: the port-busy dialog replaces the old random-port fallback,
  the MCP server needs no settings, Gatekeeper steps for macOS 15.
- Developer docs: test counts and what `make check` covers, `make e2e`, the
  weekly workflows, new modules in `CLAUDE.md`, missing pinned packages,
  network-fee disposals on withdrawals in the IRS docs, frozen StartOS ids.
  The finished hardening/redesign and StartOS package plans moved to
  `docs/archive/`; the roadmap lists only open work.

### Releases
- The release workflow now also publishes each version's `btctx.s9pk` as a
  release on the StartOS mirror (DigiMonk73/BTCTX-StartOS), marked Latest,
  so the mirror's releases page stays current with no work in that repo
  (`scripts/mirror-startos-release.sh`).
- The mirror's only branch is now `main` (was `master`, plus four stale
  branches); the sync script and the mirror's CI follow it.

## [v1.0.1] - 2026-09-26 - Settings layout fix

### Fixes
- **Settings** (windows wider than 900 px): "Your own mempool server" and
  "Proxy for outside requests" squeezed their label and help into a column
  one word wide, with the field drawn on top; the Reset Username & Password
  fields (and, slightly, the Tax Timezone drop-down) sat above their row.
  Rows with text fields now show the label and help first and the fields
  below, up to 440 px wide; Tax Timezone keeps its drop-down on the right,
  level with its title. A click-through test checks every Settings row at
  desktop, tablet and phone widths. (Layout only: no figures change.)

## [v1.0.0] - 2026-09-26 - Look and feel: the polish, ready for everyday use

### Look and feel
Same app, same layout, calmer. No tax figure changes; no Recalculate Ledger
needed.
- **Numbers** have thousands separators and a real minus sign ($80,000.00,
  −$1,373.21); gains and losses carry a sign. Dashboard labels lose their
  trailing colons.
- **Transactions** is one list: an icon for each type, the type and account
  over a grey line with the time, source and fee, the gain written out
  ("Gain +$7,000.00 · +350.00% · Long-term"), and the BTC that moved on the
  right with its dollar value under it.
- **Reports**: Tax year is a drop-down, from your first transaction's year to
  this year. Years without IRS forms in this version can't be picked for the
  IRS Reports (the Complete Tax Report and Transaction History work for any
  year). New `GET /api/reports/years`.
- **One set of buttons** everywhere: a gold primary (one per section), grey
  secondary, quiet text, and red-text destructive. Settings no longer shows
  eight gold buttons side by side.
- **One input style** with a gold focus ring, labels above, no spinner arrows
  on number fields; file pickers, checkboxes and the Manual/Auto/Date switch
  match.
- **Nothing moves on hover.** Cards and buttons no longer lift, the report
  choices no longer grow, the transaction panel and toasts fade instead of
  sliding; Reduce Motion is honored.
- **Colors** checked for WCAG AA contrast: gains and losses in the list were
  4.0:1 and 2.7:1 and are now 8.4:1 and 6.4:1; field borders went from 1.75:1
  to 3.2:1.
- **Small windows**: at the Mac app's 800 × 600 the sidebar keeps the Sats
  Converter and a whole calculator (it used to cut the calculator in half);
  on a phone the sidebar hides and the pages stack.
- Icons from Lucide (ISC license, `lucide-react` 1.48.0), bundled with the
  app. The stylesheets went from about 3,900 lines to 1,300: shared tokens in
  `styles/theme.css`, shared buttons, inputs and cards in
  `styles/components.css`, and page files that only lay them out.

## [v0.9.2] - 2026-09-26 - Hardening: price history, withdrawal fees, Ledger review, privacy settings

### Before you upgrade: what changes existing figures
Upgrading changes no stored figure. Two fixes change figures **the next time
the ledger is recalculated**, which is Recalculate Ledger (Settings) *or any
add, edit or delete*:
- **Lost** withdrawals: their loss becomes $0 (like a gift).
- **Withdrawals with a BTC network fee**: the fee becomes its own small
  disposal at its value; a spend's proceeds no longer have the fee taken out.
Back up first, then open **Settings → Ledger review**: "Figures that
Recalculate Ledger would change" lists each affected transaction, old -> new,
without changing anything (`python -m backend.cli review` prints the same).
Transfer fees that look priced at the live price are fixed only when you
press **Fix these**. New entries only: a BTC deposit that isn't income needs
a basis (0 allowed); blank Spent proceeds are valued at the day's price.

### Added
- **Ledger review** (Settings, `GET /api/review`, `python -m backend.cli
  review`, and the AI assistant tool `review_ledger`): a read-only list of
  saved transactions worth a second look after this upgrade: Spent
  withdrawals saved with $0 proceeds, Lost withdrawals still carrying a loss,
  and BTC deposits (not income) with a $0 or blank cost basis. Each row says
  what looks odd and what would change. It changes nothing.
- **Local BTC price history.** Every past-day valuation (income, spends,
  gifts, network fees, the form's price Refresh, import autofill) reads one
  stored daily price. A missing day is filled by one download of about
  1,000 days around it (Bitstamp, then Coinbase, then Kraken), so requests no
  longer name individual transaction dates, and stored days work offline.
- **Fee value (USD)** on transfers and BTC withdrawals: a BTC network fee's
  dollar value is stored when you save it (fee x that day's price), or you can
  type it; a typed value is kept. Also `fee_usd` in the API and the AI tools.

### Fixes
- **The Mac app could come up on a random port after a quick relaunch**, and
  then AI assistants couldn't reach it (they look on 127.0.0.1:8765). The
  check that decided "port busy" failed while the previous run's connections
  were still closing (TIME_WAIT), and one failed check meant a random port for
  the whole session, silently. The app now binds 8765 itself the way the
  server does, retries for up to 10 seconds, and never switches ports on its
  own: if another program really holds the port, a dialog offers Retry, Use
  Another Port (this session, with a banner saying AI assistants can't
  connect) or Quit. Opening the app twice brings the running copy forward. The
  app now keeps a log at `~/Library/Logs/BitcoinTX/BitcoinTX.log`.
- **A "Spent" withdrawal entered with blank proceeds was saved at $0**, a
  loss of its whole cost basis, instead of its value at that day's BTC price
  (the rule for spends without proceeds, which imports already followed): the
  form sent 0 for a blank. Blank now means "not given" everywhere in the form:
  Spent proceeds, a gift's FMV and an income deposit's basis start blank and
  are filled from that day's price; a 0 you type stays 0. New entries only.
  Spends saved before with $0 can't be told apart from a real $0:
  the new Ledger review lists them (read-only) so you can check.
- **A BTC deposit that isn't income now needs its cost basis.** A MyBTC,
  Gift or N/A deposit left blank was saved with a $0 basis, so all of it
  became gain when sold (the CSV import only warned). The form, the API and
  the CSV, River and AI imports now ask for it; type 0 if it's really
  unknown. Income, Interest and Reward deposits are still valued at the day's
  price. New entries only; the Ledger review lists existing ones with a $0 or
  blank basis.
- **"Lost" withdrawals no longer count as a capital loss.** They recorded a
  loss of their cost basis, which the dashboard and the tax report's summary
  included, although Form 8949 leaves Lost out. They are now treated like a
  Gift: no gain, no loss. **Run Recalculate Ledger** (Settings) to update
  Lost withdrawals saved before; the Ledger review lists them.
- The transfer form showed the network fee's USD value at a made-up
  $30,000 price; the estimate is gone. The sats converter rounded BTC to 5
  decimals (1,000 sats); it now shows every satoshi.
- **Backup download and restore didn't check for a login.** Their router is
  meant to be login-only, but both endpoints skipped the check, so a client
  with the optional `API_KEY` could download or replace the whole database.
  Both now need a login.
- **Stricter input, clear messages.** The API, CSV and AI imports now refuse
  what the ledger would record wrongly: amounts of 0 or less, negative fees,
  basis or proceeds, more decimals than a satoshi (or a cent for USD accounts,
  exponent notation included), amounts too large to store (one used to be
  saved and then break the transaction list), unknown accounts, dates before
  3 January 2009 or in the future, a BTC withdrawal without a purpose (it got
  $0 proceeds: a loss of its whole basis on Form 8949), a Sell without
  proceeds, a fee in the wrong currency. A malformed optional number in an
  import is now an error instead of being dropped. An edit is checked as the
  whole transaction.
- **Form 8949 left out "Gift"/"Donation"/"Lost" only when capitalized exactly
  that way**; a "gift" entered through the API or an import printed on the
  form with its basis. Purposes are now stored in one spelling and matched in
  any case.
- **The complete tax report's capital-gains summary could disagree with Form
  8949 and Schedule D**: it totaled whole transactions by their first lot's
  holding period (a sale across short- and long-term lots went all to one
  side), left out transfer fees and counted the basis of gifts. It is now
  built from the same disposals as the forms. The forms themselves were right.
- **CSV import dates**: a date without a timezone was read as UTC, so
  "2024-01-01" landed on 31 December 2023 in a US tax timezone. Dates now
  follow the tax timezone (Settings), and a date alone means noon that day.
  A USD transfer's fee can be imported (it used to insist on BTC). The CSV
  instructions PDF said to include fees in a Buy's basis and gave the Sell
  proceeds after fees; both are before the fee (the fee column is applied
  once).
- **The Mac app refused today's price in the evening** in the Americas (it
  compared a UTC date with the local date): an income deposit left blank got
  an error and FMV Refresh failed.
- **Security**: deleting every transaction, the debug routes and the tax
  timezone setting are login-only (the optional `API_KEY` reached them).
  Changing the password or resetting the account now ends every other
  session (you'll be asked to log in once after upgrading). Empty usernames
  and passwords are refused. The API docs pages are off unless DEBUG is set.
- **A past value could be priced at today's price, or another day's.** When
  the day's price lookup failed, a transfer's network fee (on every
  recalculation) and a Spent withdrawal without proceeds used the live price,
  silently, so old gains could change and saving failed offline. And for
  dates more than about two years back, the lookup could return a price from
  about two years later (the Kraken fallback took the first day it returned).
  Now only the exact day's price is used; if there is none, BitcoinTX says so
  and asks for the value, never $0 or today's price. A fee's dollar value is
  stored with the transaction, so recalculating never prices it again.
  **Existing figures don't change on upgrade**: stored fee values are kept.
  The Ledger review lists transfer fees more than 5% off that day's price
  (probably priced live), with a **Fix these** button (or
  `python -m backend.cli review --fix-fee-prices`) that changes only those and
  recalculates, and income deposits more than 5% off, for you to check.
- **A withdrawal's network fee is now its own disposal**, as a transfer's
  always was (it's a small sale of BTC at its value). A spend's proceeds are
  what you received for the BTC spent; before, the fee was taken out of them
  (a $1,000 spend with a fee reported $990.10). A gift's, donation's or lost
  withdrawal's network fee now shows on Form 8949 too. **This changes
  existing figures once the ledger is recalculated** (Recalculate Ledger, or
  any add, edit or delete). Settings → Ledger review lists every transaction
  whose figures would change, old -> new, before you do.
- **Double-clicking Save added the transaction twice.** It now saves once.
- River import checked against a real River export: a Buy's Sent Amount is
  the subtotal with River's fee on top (basis = Sent + Fee), and timestamps
  are UTC, both as BitcoinTX reads them. Whether a send's Sent Amount
  includes the network fee is still being checked (v0.9.3).
- The River import warns when a row's Fee Currency isn't what BitcoinTX
  reads it as. The tax report shows a gift's value as "not given" instead of
  $0 when none was entered.

### Privacy
- **Fonts ship with the app.** The page loaded Inter and Outfit from Google
  Fonts, which told Google every time BitcoinTX opened. Nothing the page
  loads comes from anywhere but BitcoinTX now, and in a browser a
  Content-Security-Policy enforces it.
- Responses now carry no-referrer, nosniff and no-framing headers, and the
  session cookie is marked Secure when BitcoinTX is reached over HTTPS
  (StartOS).
- The database file and downloaded backups are readable by their owner only.
- **Backups are stronger**: 600,000 PBKDF2 iterations (was 100,000) and an
  integrity check, so a wrong password or a damaged file is reported clearly.
  Backups made by earlier versions still restore. A backup made by 0.9.2
  can't be restored by 0.9.1 or earlier.
- A log message no longer includes a fee amount.
- **Settings → Privacy & network.** Turn live data off (BitcoinTX then asks
  no public service for anything: no live price or block height, and past
  prices come only from those already stored), use your own mempool server
  for the live price and block height, and send every outside request
  through a proxy such as Tor (`socks5h://127.0.0.1:9050`). Public services
  stay the default.

### AI assistant (MCP)
- **The Mac app no longer needs your password in an AI app's settings.** It
  writes `~/Library/Application Support/BitcoinTX/mcp.json` (readable only by
  you) with its address and an AI assistant key, and the MCP server reads it
  by itself. Setup is one line with nothing secret in it (Settings → Connect an
  AI Assistant). The key works only from this computer and never for backup,
  restore, imports or deleting everything. Settings can turn AI access off or
  reset the key; the MCP server picks up a new key by itself. StartOS and
  Docker keep the username/password setup.
- **If you set up the MCP server with your password before:** remove the
  `BTCTX_URL`, `BTCTX_USERNAME` and `BTCTX_PASSWORD` lines from its
  configuration (for Grok Build, `~/.grok/config.toml`), or remove the server
  and add it again with the new one-line command. Check that a read such as
  `get_portfolio` works, then change your BitcoinTX password, since the old
  one sat in a plain-text file.
- `mcp_server/AI_SETUP.md` now tells the AI where the StartOS certificate
  comes from (the **Connect an AI Assistant** action's Root CA certificate,
  saved as `btctx-root-ca.crt`) and which password StartOS uses. The Settings
  prompt on a StartOS address already said "the guide explains"; it didn't.

### Tests
- Playwright click-through tests of every UI flow (`make e2e`; CI runs them in
  Chromium in Chicago and Tokyo time, and in WebKit). Form controls got proper
  labels for this (accessibility only).
- Property tests (Hypothesis): random valid ledgers keep the tax invariants.
  Golden years: three tax years worked out by hand, with exact Form 8949 rows
  and Schedule D lines. See `docs/TESTING.md`.

## [v0.9.1] - 2026-09-25 - Connect an AI Assistant in Settings, River sell fee, edit time, income basis

### Fixes
- **River import double-counted the fee on Sells.** River's Received Amount is
  what landed after River's fee (receipt: subtotal − fee = received), but it
  was stored as the gross, so the fee was subtracted a second time: proceeds
  and the Exchange USD balance came out short by the fee. Proceeds are now
  Received + fee. Sells imported before this fix keep the old figure; correct
  them by setting the proceeds to Received + fee.
- **Editing a transaction shifted its time by the UTC offset** (5 hours in
  CDT): the edit form showed the UTC time as local time and saved it back as
  local. It also dropped the seconds. A new transaction's default time had the
  same mix-up. The form now shows and saves local time, seconds included.
- **Income deposits entered without a cost basis were saved at $0**, which
  left them out of the income on the tax report and overstated the gain when
  the BTC was later sold. A Deposit with source Income, Interest or Reward
  into a BTC account, entered by hand or by CSV with a blank or 0 basis, is
  now valued at that day's BTC price, as River import and the MCP server
  already did; it isn't saved when no price is available. Editing such a
  deposit saved at $0 values it.
- The MCP `get_btc_price` tool says which moment its daily price is (00:00
  UTC) and to pass a transaction's UTC date.

### Distribution
- Releases signed with the `DEV_KEY` secret no longer fail to pack the s9pk
  when the secret ends with a newline or carries trailing spaces: the key is
  rewritten in the strict PEM form start-cli requires.

### AI assistant (MCP)
- **Settings → Connect an AI Assistant**: a setup prompt to paste into your AI
  app, with this server's address and your username filled in and the MCP
  server pinned to this release, plus a ready-made Claude Desktop config and
  `claude mcp add` command. Works for the macOS app, Docker and StartOS. The
  password is never shown or put in the prompt: the AI writes a placeholder
  you replace in the configuration file.
- `mcp_server/AI_SETUP.md`: setup instructions written for an AI assistant
  (Claude Code, Claude Desktop, Grok Build, other MCP clients), which the
  prompt points to.

## [v0.9.0] - 2026-09-23 - StartOS package in this repo, health check, maintenance CLI

### StartOS package
- The StartOS package now lives in this repository (`startos/`, start-sdk
  2.0.9) and is mirrored to DigiMonk73/BTCTX-StartOS. Installs of the old
  package (0.3.x through 0.8.0:1) update in place.
- New actions: **Connect an AI Assistant** (MCP address, login, the StartOS
  root CA, a ready-to-paste Claude Desktop config and `claude mcp add`
  command) and **Recalculate Ledger**. Updating from before 0.8.0 raises a
  Recalculate Ledger task.
- New **MCP API** interface (`…/api`), which the MCP server accepts as
  `BTCTX_URL`.
- Fresh installs prompt for Show Credentials before the first start.
- The database upgrade runs as its own startup step; the health check uses
  `/api/health`.
- The generated login moved from the app's volume to a separate package
  volume; both are backed up.
- Downgrades are refused (an older app can't open a migrated database).
- New vector icon.

### Distribution
- One release workflow (`release/vX.Y.Z` branch) produces the GHCR image, the
  macOS app as an unsigned `.dmg` plus the `.zip`, and `btctx.s9pk`, all on one
  GitHub release; the s9pk is signed with the `DEV_KEY` secret when it exists
  and `startos/` is mirrored to BTCTX-StartOS when `MIRROR_TOKEN` exists
  (`scripts/sync-startos-mirror.sh` by hand otherwise).
- CI checks the package and packs an x86_64 s9pk from every commit's image;
  a weekly job opens an issue when a newer start-sdk is on npm.

### Added
- `GET /api/health` (no login): 200 when the database answers at the current
  schema, 503 otherwise, with the app version. Used by the StartOS package and
  the CI container checks.
- `python -m backend.cli` maintenance commands: `migrate` (schema upgrade +
  defaults), `set-password [--username NAME] [--password-stdin]` (through the
  app's own hashing; the password never goes on the command line) and
  `recalculate` (rebuild the ledger). The StartOS package uses them instead of
  editing SQLite directly.
- Frontend unit tests (Vitest) for the transaction form's mapping to and
  from the API, run by the pre-push hook and CI. The mapping moved to
  `frontend/src/utils/transactionForm.ts`.

### Changed
- Logging defaults to INFO instead of DEBUG; set `LOG_LEVEL` (DEBUG, INFO,
  WARNING, ERROR) to change it.
- Only the newest 5 automatic database copies (taken before a schema upgrade
  or a restore) are kept in `<data dir>/backups/`; older ones are deleted.
- The app version (`VERSION`) ships inside the Docker image and the macOS app.
- The complete tax report no longer rebuilds the ledger inside the request
  to take its start- and end-of-year snapshots (33 writes for a small ledger,
  holding the database write lock, then discarded). The snapshots replay on
  an in-memory copy of the database; the report writes nothing.

## [v0.8.0] - 2026-09-23 - MCP server, schema migrations, tax fixes

### Distribution
- Multi-arch (amd64 + arm64) Docker image published to
  `ghcr.io/digimonk73/btctx-mcp` on every push to main; `:v0.8.0` is fixed.
  The StartOS package (DigiMonk73/BTCTX-StartOS v0.8.0:0) runs this image.
- Tax year 2026: the IRS draft Form 8949 and Schedule D were checked against
  the app (`scripts/irs_new_year.py --draft`, run weekly in CI): identical
  field layout to 2025, every field the app fills exists, box order matches.

### Added — MCP server (AI-assisted entry)
- **`mcp_server/`**: an MCP server (`btctx-mcp`) that lets an AI assistant
  (Claude Desktop, Claude Code, any MCP client) add transactions from pasted
  text or plain English: exchange emails, wallet history, explorer pages. Tools:
  guide, preview, add, list, update, delete (single), portfolio, BTC price.
  Runs locally over stdio and logs in to BitcoinTX with the user's credentials.
  See `mcp_server/README.md`.
- **JSON entry import API** (session-auth only):
  `POST /api/import/entries/preview` and `POST /api/import/entries/execute`.
  - Preview validates with the CSV importer's rules, dedups against the ledger
    with the River engine (exact → skipped, near-match → flagged), auto-fills
    FMV-derived USD values (Income/Interest/Reward basis, Spent proceeds,
    Gift/Donation FMV), then **dry-runs the real create path and rolls it
    back**: returns simulated realized gain/holding period per row, rejected
    rows (e.g. not enough BTC), balances afterward, and existing sales whose
    gains change due to backdating.
  - Execute is atomic with the same exact-duplicate guard and returns the
    created transaction ids.
- **`POST /api/transactions/recalculate`** (and MCP tool `recalculate_ledger`):
  rebuild all lots, disposals and gains from the transactions. **Run once after
  upgrading** so the fixes below reach existing data.
- New tests: `test_entry_import.py` (20), `test_transfer_fees.py` (5),
  `test_disposal_proceeds.py` (11), and 10 MCP end-to-end tests
  (`mcp_server/tests/`).

### IRS forms: yearly update tooling
- `scripts/irs_new_year.py YYYY`: downloads the final forms, rejects drafts and
  wrong-year PDFs, verifies field names and box order, diffs against the prior
  year, installs, and runs the template tests.
- A new year folder fails tests until its config is explicitly verified
  (`verified_years`), so it can't silently inherit last year's layout.
- `IRS forms watch` workflow checks irs.gov weekly Nov–Mar for new final forms.

### macOS desktop app
- Listens on a fixed local port, `http://127.0.0.1:8765` (override with
  `BTCTX_DESKTOP_PORT`; falls back to a random port if taken), so the MCP
  server can connect. Still bound to localhost only.
- PyInstaller spec lists the River/entry import modules; bundle version 0.8.0.

### Security (account takeover — upgrade recommended)
- **`/api/users` had no authentication.** Anyone who could reach the app
  could list users, change the password, or delete the account. Changing or
  deleting now requires being logged in as that user. First-run setup and
  re-registration use `POST /api/users/reset-account`, which the server allows
  only while the login is still the shipped `admin`/`password`, or with the
  current password (previously the "override password" was checked only in
  the browser). `GET /api/users/setup-status` is the only public user route.
- **Forgeable login cookies.** Without a `SECRET_KEY` env var (the Docker and
  StartOS default) sessions were signed with `default_secret_key`, published
  in this repo, so anyone could mint a valid login cookie. The macOS app used
  another published key. Now a random key is generated per install and stored
  next to the database (`.btctx_secret_key`, mode 600); an explicit
  `SECRET_KEY` still wins unless it is one of the published values.
  Existing users are logged out once after upgrading.

### Security / dependencies
- fastapi 0.141.1, starlette 1.7.0, pydantic 2.13.5, uvicorn 0.53.0 (starlette CVEs)
- cryptography 50.0.1, pypdf 6.19.0, sqlalchemy 2.0.54, python-dotenv 1.2.3
- axios 1.20.0 (high-severity advisories), react-hook-form, react-router-dom,
  eslint/typescript-eslint patch updates; `npm audit` clean
- Docker frontend build stage: node:18 (EOL) → node:22
- **Python 3.9 is no longer supported** (3.10+; Docker uses 3.11)

### Added — tax timezone
- **Settings → Tax Timezone** (auto-set from your browser on first login;
  `BTCTX_TIMEZONE` env var as a fallback). Tax years, Form 8949 dates,
  holding-period anniversaries, the reports and year-to-date totals now use
  it — a 10 pm Dec 31 sale in New York is no longer counted in the next
  year. Timestamps are still stored in UTC. Changing it recalculates.
- AI/MCP entries without a timezone are read in the tax timezone (a bare date
  means midday that day).

### Fixed — tax report placeholders
- The complete tax report valued year-end BTC at a hardcoded demo price
  ($94,153.13) and reported a hardcoded $4,000 profit in its asset summary.
  It now uses the real Dec 31 price and the year's actual gains/losses, and
  year-end holdings exclude activity after Dec 31.
- The complete tax report dropped transactions in the last second of the year.

### Changed — no more pdftk (Java)
- IRS forms are now filled and flattened in pure Python (pypdf). pdftk is no
  longer needed on macOS (`brew install pdftk-java` step gone), in Docker
  (image drops the Java runtime) or in CI. Output compared page-by-page with
  pdftk: Schedule D pixel-identical, Form 8949 identical except sub-pixel
  text placement in the description column.
- A field name missing from an IRS template now raises an error instead of
  being silently dropped (which produced blank forms).

### Changed — Form 1099-DA boxes (IRS broker reporting, 2025+)
- Exchange (River) sells are now reported in **Box H/K** for 2025 (on a
  1099-DA, basis not reported) and in **Box G/J** from 2026 for lots bought on
  the exchange on/after 2026-01-01 (covered, basis reported). Self-custody
  spends and network fees stay in **I/L**. Each box gets its own Form 8949
  page, and Schedule D now fills lines 1b, 2, 3, 8b, 9 and 10 as applicable
  (previously only 3 and 10).

### Fixed
- **Holding period off by one day.** Anything held 365+ days was long-term,
  so a sale on the one-year anniversary (or on day 365 in a leap year) got the
  long-term rate. IRS rule: long-term only when held MORE than one year —
  disposed after the anniversary date. Two old tests asserted the wrong
  answer and were corrected. Run the recalculation once to update existing
  sales.
- **IRS Form 8949 boxes.** No Part checkbox was ever checked (the IRS requires
  one), and the box letter was written into column (f) "Code(s)", which is for
  adjustment codes. For 2025 the app also used Box C/F, which the 2025 form
  reserves for non-digital assets. Now exactly one box is checked per Part —
  C/F for 2024, **I/L** (digital assets not on a 1099) for 2025+ — and column
  (f) is blank. Verified by filling the real IRS templates and reading every
  field back (`test_irs_templates.py`, runs for every bundled year).
- **BTC Transfer fees counted two ways.** The ledger treated a Transfer's
  `amount` as what left the source (fee included, as the UI's "amount sent"
  field does), but cost-basis lots took `amount + fee` from the source. Lots
  and balances drifted apart by every transfer fee, and sending a whole
  balance failed with "Not enough BTC". Lots now use the ledger/UI convention;
  a fee larger than the amount is rejected with a clear message. River
  imports (whose amounts exclude the fee) are converted at execute and in
  dedup, so re-imports still match. Dashboard balances do not change.
- **Proceeds shrank on every recalculation.** Stored `proceeds_usd` is the
  net value, but Sells from CSV/River/API (no `gross_proceeds_usd`) and every
  Spent withdrawal with a BTC fee re-derived net from that already-net value,
  losing the fee again on each backdated insert, edit or delete. The user's
  gross is now always recorded on create and on proceeds edits, and rows
  saved by older versions recover their gross on the next recalculation, so
  they stop shrinking. (Losses that already happened can't be undone
  automatically — compare old Sells/Spends against exchange records.)
- **River/CSV "Spent" withdrawals without proceeds became fake losses.** They
  were saved with $0 proceeds, realizing the full cost basis as a capital
  loss. They are now valued at the day's BTC price (as the CSV importer's
  warning always claimed), fetched once and stored. Existing rows are
  repaired on the next recalculation. An explicit $0 entered in the form is
  still respected.
- The transaction edit form now loads a withdrawal's gross proceeds, so
  re-saving an edit no longer nets the fee again.
- **Docker data could be lost on update.** The image never set
  `DATABASE_FILE`, so a plain `docker run -v …:/data` kept the database inside
  the container. The image now defaults to `/data/btctx.db`; CI checks the
  database and session key land on the volume. (StartOS was unaffected: its
  wrapper sets the same path.)
- **Form 1099-DA covered-lot cutoff** compared the acquisition time in UTC, so
  a lot bought on the evening of Dec 31, 2025 in the US counted as covered
  (Box G/J) while its printed acquisition date said 12/31/2025. It now uses
  the tax-timezone date.
- **Filled IRS forms were ~5 MB per Form 8949 sheet.** Flattening left the old
  field appearance streams in the file. Output is now ~0.3 MB per sheet and
  renders pixel-identically.
- `.env.example`'s placeholder `SECRET_KEY` was a publicly known value that
  would have been used as-is; it is now rejected like the other public
  defaults, and the example leaves the key unset (auto-generated).

### Added — per-transaction Form 1099-DA override
- A Sell or Spent withdrawal can record what the broker actually reported
  ("Broker form" in the transaction form; `broker_reporting` in the API and
  the MCP `update_transaction` tool): not on a broker form, proceeds only, or
  proceeds and basis. That picks the Form 8949 box for that sale (2025+:
  I/L, H/K, G/J; 2024 and earlier: C/F, B/E, A/D) instead of the default
  rules. Left on Automatic, nothing changes.
- The first real schema migration (0003): existing databases gain the column
  automatically on upgrade.

### Added — schema migrations
- The database schema is now managed by **Alembic migrations**
  (`backend/migrations/`), run automatically at every start. Before this, new
  tables were created on startup but new columns and indexes never reached
  existing databases.
- **Existing databases are adopted automatically**: checked against the v0.7.0
  schema, repaired where that's safe (databases from before Jan 2026 get the
  foreign-key indexes they never received), then upgraded. Verified against a
  database written by the real v0.7.0 code, in tests and in the Docker image.
- **Automatic backup** to a `backups/` folder next to the database before any
  schema change (or restore). Upgrades run in a single transaction: a failure
  leaves the database exactly as it was.
- A database from a newer BitcoinTX is refused with a clear message instead of
  being opened by older code.
- **Restoring an older backup now upgrades it** before it replaces the live
  database. Restores are validated first (wrong password, not a database, or
  from a newer version leave the live data untouched), swapped in atomically,
  and the database being replaced is kept in `backups/`. Encrypted backups are
  now taken with SQLite's backup API (consistent even while the app writes).

### Added
- **Settings → Recalculate Ledger** button (same as the MCP
  `recalculate_ledger` tool) for applying calculation fixes after an upgrade.

### Housekeeping
- Removed legacy scripts that drove a live server (one sent `delete_all` to
  port 8000), superseded IRS field-dump tools, `scripts/pre-commit.sh`,
  `baseline-pdfs/`, `clean_env.py` and the legacy Makefile targets. Finished
  design plans moved to `docs/archive/`.
- Lint: ruff enforces all Pyflakes rules and ESLint runs with zero warnings.
- Tests: two test files used soft assertions that logged failures without
  failing (108 checks); they now fail properly, which exposed one wrong
  holding-period expectation (fixed). Several tests that asserted nothing now
  check what their names claim.
- pytest moved out of `backend/requirements.txt` (it was installed in the
  Docker image) into `requirements-dev.txt`, upgraded to 9.1.1; the dependency
  audit now covers both files with no exceptions.
- Docs rewritten for the current code: README, CLAUDE.md, IRS form
  generation and yearly update, macOS app, StartOS, maintenance, testing.

---

## [v0.7.0] - 2026-06-10 - River CSV Import

### Added — River CSV Import
- **Import from River** (Settings page): upload a River bitcoin-activity CSV
  (river.com → Taxes & Documents) and merge it into a live ledger — unlike the
  onboarding CSV import, no empty-database requirement.
  - Adapter maps every River row pattern: Buy, Sell, Interest/Income (BTC
    interest on the River cash balance), tagged Withdrawals, and untagged
    on-chain sends/receives (default to cold-storage Transfers, flippable to
    Withdrawal/Deposit per row).
  - **Dedup engine**: rows already in the ledger are matched (exact BTC amount,
    compatible type, ±48h) and skipped; near-matches (transfers within ±20%)
    are flagged for review and excluded by default. Re-importing overlapping
    date ranges is safe and idempotent.
  - Buy funding source (Bank vs Exchange USD) defaults from a file-recurrence
    heuristic and is always a one-click toggle in the preview — by design the
    user is the final classifier on every import.
  - Interest/Income deposits get fair-market-value cost basis auto-filled from
    the historical BTC price (3-source failover), marked "est." and editable.
  - Atomic execute: all-or-nothing with server-side re-validation and a
    double-submit guard.
  - New endpoints `POST /api/import/river/preview` and
    `POST /api/import/river/execute` (session-auth only).
- 20 new tests (`backend/tests/test_river_import.py`, synthetic fixtures);
  suite now **184 tests**. Verified against a real 1,197-row River export
  (100% row coverage) and a live import reconciled to River's balance to the
  exact satoshi and cent.
- New runbook `docs/IRS_ANNUAL_FORM_UPDATE.md` for adding each year's IRS form
  templates (official IRS URL patterns, MD5 verification, field-diff procedure,
  per-year config and test checklist). `docs/IRS_FORM_GENERATION.md`'s stale
  update section now points to it.

---

## [v0.6.0] - 2026-06-10 - 2026 Modernization

### 2026 Modernization (June 2026)

#### Security / Dependencies (conservative pass: React 18 + Vite 6 retained)
- **Backend**: fastapi 0.115.8→0.121.3, starlette pinned 0.49.3 (CVE-2025-62727 HIGH StaticFiles Range-header DoS, CVE-2025-54121), python-multipart 0.0.20→0.0.32 (CVE-2026-42561 HIGH + 2), cryptography 44.0.2→46.0.7 (CVE-2026-26007 HIGH), pypdf 5.4.0→6.13.1 (~20 DoS CVEs; 5.x line unmaintained), reportlab 4.4.7→4.4.10 (4.5.x deliberately skipped — PDF output drift risk), uvicorn 0.49.0, sqlalchemy 2.0.50, requests ==2.34.2, python-dotenv 1.2.2, pytest 8.4.2; pydantic deliberately held at 2.12.5. Deferred majors documented in MAINTENANCE.md "Deferred Updates".
- **Frontend**: vite 6.4.3 (4 dev-server CVEs), axios 1.17.0 (CVE-2026-25639), react-router-dom 7.17.0 (SPA open-redirect/XSS), typescript 5.9.3, eslint 9.39.4; removed obsolete @types/react-router-dom; `npm audit` now reports 0 vulnerabilities.
- **Desktop**: pyinstaller >=6.20.0, pywebview >=6.2.1 (rebuild + save_file bridge check due at next .app build).

#### Fixed
- **2025 Form 8949 row capacity**: the 2025 IRS template holds 11 rows per page (2024: 14); the hardcoded 14-row chunking would have silently dropped rows 12-14 on 2025 filings (pdftk ignores unknown fields). Row capacity is now part of the year-specific field config.
- **Form 8949 multi-page handling**: overflow pages were numbered continuously (f1_, f2_, f3_...), but templates only define Page1 (Part I/short-term) and Page2 (Part II/long-term) fields — a second short-term chunk landed in the long-term table and later chunks vanished. Short/long chunks are now paired onto shared template-copy sheets, matching the paper form.
- Bundled 2025 templates verified MD5-identical to the final irs.gov releases (no draft markers).
- **Desktop app launch failure** (broken since 2026-02-14, exposed by the first .app build since January): the launcher's backend-readiness probe polled `/api/accounts/` expecting HTTP 200, but router-level auth (added Feb 2026) returns 401 — the probe spun for 30s and the app exited before ever creating a window (Dock dot, no UI). Probe now polls the unauthenticated SPA root.

#### Changed (behavior-preserving backend quality pass)
- Dead code removed (unused `fill_8949_multi_page`, legacy `AccountType` enum, duplicate `get_db`, debug prints, no-op `group_id` write); duplication consolidated (CSV upload validation, debug serializers, deposit aggregation, Schedule D field mapping); N+1 queries fixed in the transaction-history report (was 4 Account queries per row) and account balances; root-logger `basicConfig` calls replaced with module loggers.

#### UI Polish (existing dark theme, CSS-only)
- Design tokens: easing curves, letter-spacing, layered shadows, missing `--color-text-dim` defined; tabular numerals on all financial figures; gold active-nav underline; dashboard card hover lift; transaction date-heading hairlines; side-panel slide-in animation; `prefers-reduced-motion` support; theme-matched scrollbars; login.css duplicated rule blocks removed; stale pre-rebrand colors tokenized. Browser-verified at 1440/800/768/480px; layout, breakpoints, and 44px touch targets unchanged.

#### Testing
- New `backend/tests/test_2025_forms.py` (6 tests) incl. an 11-row capacity regression test; suite now **164 tests** (was 158).
- New PDF baseline gate `baseline-pdfs/regen_and_diff.sh`: regenerates all three reports against a frozen seed dataset and text-diffs them against committed baselines (run after every modernization phase; output verified equivalent throughout — a documented price-provider variant baseline covers live BTC-price variance in transfer-fee valuations).

### Test Isolation & Backups (February 2026)
- Test suite isolated from the production database (FastAPI TestClient + temp SQLite via dependency override; no running backend needed for most tests)
- Daily encrypted-safe SQLite backup script `scripts/backup-db.sh` (cron 3 AM, 60-day retention)

### Added
- **PDF Content Verification Test Suite**: `backend/tests/test_pdf_content.py` with 23 new tests
  - Uses `pypdf` to extract and verify actual PDF content, not just file generation
  - Complete Tax Report tests: year, sections, capital gains, ending balance, income, long/short-term
  - IRS Form tests: Schedule D present, Form 8949, proceeds, tax year, long-term section, page count
  - Transaction History tests: CSV headers, transaction data, types, PDF content
  - Edge case tests: empty year, large amounts ($7.5M), small BTC precision (0.00012345), same-day sales
  - Data accuracy tests: gain calculation, FIFO cost basis tracking, income totals
  - Total pytest tests: **158** (was 135)

### Fixed
- **test_seed_data_integrity.py**: Made tests self-contained with fixture that creates test data if database is empty
- **Disposal test logic**: Fixed to correctly skip USD transfers (only BTC transfers require lot disposals)

---

## [v0.5.5] - 2025-01-17 - Transaction Edit Fix

### Fixed
- **Transaction editing in macOS desktop app**: Fixed bug where editing transactions would fail with "Not enough BTC" error
  - Root cause: Backend's `update_transaction_record()` had flawed lot logic when backdating transactions
  - The partial re-lot (`recalculate_subsequent_transactions`) ran before full scorched earth, using stale lot balances
  - Fix: Simplified update flow to use only full scorched earth (`recalculate_all_transactions`)
  - This also fixes potential edge cases in Docker/web deployments with specific transaction histories

### Improved
- **PUT response validation**: Edit form now validates backend response before showing success
- **Realized gain display on edit**: Edit transactions now show realized gain in success toast (matching create behavior)

### Technical Notes
- **Files Modified:** `backend/services/transaction.py`, `frontend/src/components/TransactionForm.tsx`
- **Documentation:** `docs/archive/edit-tx-bug-mac.md` - Full investigation and fix details
- **Tests:** All 135 pytest tests pass, 17/17 pre-commit tests pass

---

## [v0.5.4] - 2025-01-16 - Buy from Bank Feature

> **Rollback Tags:** If issues arise, rollback to `pre-bank-buy` (develop) or `pre-bank-buy-master` (master)

### Added
- **Buy from Bank**: Buy transactions can now originate from Bank account (auto-buy support)
  - New "From Account" dropdown in Buy form: Exchange USD (default) or Bank (auto-buy)
  - CSV import accepts `Bank` as source for Buy transactions
  - FIFO cost basis tracking works correctly - lots land in Exchange BTC pool regardless of USD source
  - Backend validation relaxed to allow `from_account = Bank (1) OR Exchange USD (3)`
  - 5 new tests in `TestBuyFromBank` class covering basic flow, FIFO order, CSV import, backward compatibility
  - Documentation: `docs/archive/BUY_FROM_BANK_FEATURE.md`

### Technical Notes
- **Risk Level:** LOW - FIFO logic uses `to_account_id` (unchanged), not `from_account_id`
- **Backward Compatible:** Existing Buy transactions and CSVs continue to work unchanged
- **Files Modified:** `transaction.py`, `csv_import.py`, `TransactionForm.tsx`, `global.d.ts`, `test_stress_and_forms.py`

---

## [v0.5.3] - 2025-01-17 - Comprehensive Test Suite & Desktop Fixes

### Added
- **Comprehensive Test Suite**: `backend/tests/test_stress_and_forms.py` with 46 new pytest tests
  - Volume/stress testing (250+ transactions, backdating cascades, multi-year)
  - Edge cases: holding period boundaries (364/365/366 days), satoshi precision, $100M amounts
  - Account-specific FIFO verification (Exchange vs Wallet isolation)
  - All deposit sources tested: MyBTC, Gift, Income, Interest, Reward
  - All withdrawal purposes tested: Spent, Gift, Donation, Lost (with correct tax treatment)
  - IRS Form 8949 validation: multi-page (15/30 disposals), non-taxable exclusions
  - Schedule D totals verification
  - Total pytest tests: 131 (was 84)
- **macOS Desktop App**: Native macOS application using PyInstaller + pywebview
  - Self-contained `.app` bundle (~61MB) with embedded FastAPI backend
  - Data persists in `~/Library/Application Support/BitcoinTX/btctx.db`
  - Automated build script: `desktop/build-mac.sh`
  - PyInstaller spec with all hidden imports configured
  - Dynamic port allocation for backend server
  - Dark mode support, resizable window (1280x800 default, 800x600 min)
  - pdftk detection with user warning dialog if missing
  - Files added: `desktop/entrypoint.py`, `desktop/BitcoinTX.spec`, `desktop/build-mac.sh`, `desktop/requirements.txt`, `desktop/README.md`
  - Documentation: `docs/MACOS_DESKTOP_APP.md`
- **Mobile Responsiveness Overhaul**: Comprehensive mobile-friendly UI updates
  - Transaction panel: responsive width, fixed overlay positioning on mobile
  - Login page: fluid width for small screens
  - Navigation: CSS grid layout for mobile (3-column at 768px, 2-column at 480px)
  - Touch targets: minimum 44px for all interactive elements
  - Transaction list: mobile labels via CSS `::before` pseudo-elements
  - Added `:active` states for touch feedback across all interactive elements
  - Files modified: `transactionPanel.css`, `login.css`, `transactions.css`, `app.css`, `converter.css`, `reports.css`, `dashboard.css`, `settings.css`, `theme.css`, `transactionForm.css`
- **Frontend Design System Refactor**: Major code quality and architecture improvements
  - Custom hooks: `useAccounts`, `useApiCall`, `useBtcPrice` for reusable logic
  - Toast notification system with `ToastContext` for user feedback
  - Error boundaries (`ErrorBoundary.tsx`) for graceful error handling
  - Centralized theme system (`theme.css`) with CSS variables
  - Barrel exports via `hooks/index.ts`
- **CSV Export**: Export all transactions as a CSV file matching the import template format
  - Creates clean roundtrip: Export → Edit → Re-import
  - File naming: `btctx_transactions_YYYY-MM-DD.csv`
  - New endpoint: `GET /api/backup/csv`
- **CSV Import Instructions PDF**: Downloadable PDF guide for CSV import feature
  - New endpoint: `GET /api/import/instructions`
- **Pre-Commit Test Suite**: 17 tests for catching regressions
  - Run with: `./scripts/pre-commit.sh` or `python backend/tests/pre_commit_tests.py`

### Changed
- **Sidebar brand layout**: Changed from horizontal to vertical stack (logo above title)
- **Logout button**: Removed lock emoji, simplified to text-only
- **Logout link color**: Changed from dark red (#811922) to brighter red (#cf4655) to fix font rendering issue on macOS dark backgrounds
- **Pydantic V1 → V2 Migration**: Updated all deprecated Pydantic patterns
  - Replaced `@validator` with `@field_validator` + `@classmethod`
  - Replaced `class Config` with `model_config = ConfigDict(...)`
  - Replaced `orm_mode` with `from_attributes`
  - Replaced `.from_orm()` with `.model_validate()`
  - Replaced `.dict()` with `.model_dump()`
  - Eliminates all Pydantic deprecation warnings
  - Documentation: `docs/archive/PYDANTIC_MIGRATION.md`

### Fixed
- **pdftk path resolution for macOS desktop**: Added centralized `pdftk_path.py` module
  - PyInstaller bundles don't inherit system PATH, breaking pdftk detection
  - New module checks known Homebrew locations (`/opt/homebrew/bin/pdftk`, `/usr/local/bin/pdftk`)
  - Caches resolved path for performance
  - Updated `pdf_utils.py`, `pdftk_filler.py`, `reports.py` to use new module
- **Reports page desktop downloads**: Reports now download correctly in macOS desktop app
  - Updated `Reports.tsx` to use desktop-aware download utility
  - Added PyWebView API TypeScript types to `global.d.ts`
- **macOS desktop app downloads**: Settings page downloads (backup, CSV export, templates) now work correctly in the desktop app
  - Added `desktopDownload.ts` utility that detects pywebview environment
  - Uses native file save dialog via `window.pywebview.api.save_file()` when running in desktop app
  - Falls back to standard browser download for web/Docker deployment
  - File: `frontend/src/utils/desktopDownload.ts`
- **Lint errors fixed**: Removed unused variables in `useBtcPrice.ts` and `Settings.tsx`
- **Form 8949 non-taxable exclusion**: Gift, Donation, and Lost disposals now correctly excluded
- **Proceeds degradation fix**: Fixed bug where `proceeds_usd` could degrade during recalculation
- **None-to-Decimal conversion**: Fixed TypeError in report generation after Pydantic V2 migration
  - `.model_dump()` includes keys with `None` values, breaking `Decimal(tx_data.get("key", default))`
  - Changed to `Decimal(tx_data.get("key") or default)` pattern in `transaction.py`
- **FIFO lot disposal now account-specific**: Fixed bug where selling/withdrawing BTC would consume lots from all accounts globally instead of only from the source account. This ensures correct cost basis tracking when BTC is held across multiple accounts.
- **SPA routing in Docker**: Fixed browser refresh returning 404 on client-side routes
  - Added custom exception handler to serve `index.html` for non-API 404s
  - React Router now handles `/dashboard`, `/transactions`, `/settings`, etc. on page refresh
  - API routes still return proper JSON errors
  - File: `backend/main.py`

### Files Added
- `backend/tests/test_stress_and_forms.py` - Comprehensive stress testing and IRS form validation (46 tests)
- `backend/services/reports/pdftk_path.py` - Centralized pdftk path resolution for macOS desktop compatibility
- `frontend/src/utils/desktopDownload.ts` - Desktop app file download utility with pywebview integration
- `frontend/src/hooks/useAccounts.ts` - Account fetching and caching hook
- `frontend/src/hooks/useApiCall.ts` - Generic API call hook with loading/error states
- `frontend/src/hooks/useBtcPrice.ts` - BTC price fetching hook
- `frontend/src/hooks/index.ts` - Barrel exports for hooks
- `frontend/src/components/ErrorBoundary.tsx` - React error boundary component
- `frontend/src/components/Toast.tsx` - Toast notification component
- `frontend/src/components/ToastContainer.tsx` - Toast container component
- `frontend/src/contexts/ToastContext.tsx` - Toast context provider
- `frontend/src/styles/theme.css` - Centralized CSS variables and theming
- `frontend/src/styles/toast.css` - Toast notification styles
- `frontend/src/styles/errorBoundary.css` - Error boundary styles
- `backend/tests/pre_commit_tests.py` - Pre-commit test suite
- `scripts/pre-commit.sh` - Shell script wrapper for pre-commit tests

---

## [v0.5.0] - 2025-01-14 - Backend Refactoring & Test Suite

### Major Backend Refactoring

#### Code Modernization
- **Removed passlib dependency**: Direct bcrypt usage for password hashing
  - `User.set_password()` and `User.verify_password()` now use bcrypt directly
  - Added 72-byte password limit validation (bcrypt requirement)
  - Eliminates passlib deprecation warnings
- **Replaced deprecated `Query.get()`**: Updated to `Session.get()` pattern
  - 10 occurrences in `transaction.py`
  - 1 occurrence in `debug.py`
  - 1 occurrence in `test_seed_data_integrity.py`
- **Replaced `@app.on_event` deprecation**: Migrated to FastAPI lifespan context manager
- **Removed duplicate import**: Fixed `from_orm` duplicate in `form_8949.py`

#### Performance Improvements
- **Added `joinedload` eager loading**: Optimized `compute_sell_summary_from_disposals()`
  - Prevents N+1 queries when loading `LotDisposal.lot` relationships
- **Added database indexes on foreign keys**:
  - `LedgerEntry.transaction_id`, `LedgerEntry.account_id`
  - `BitcoinLot.created_txn_id`
  - `LotDisposal.lot_id`, `LotDisposal.transaction_id`

#### Code Organization
- **Created `backend/constants.py`**: Centralized account ID constants
  - `ACCOUNT_BANK`, `ACCOUNT_WALLET`, `ACCOUNT_EXCHANGE_USD`, `ACCOUNT_EXCHANGE_BTC`
  - `ACCOUNT_BTC_FEES`, `ACCOUNT_USD_FEES`, `ACCOUNT_EXTERNAL`
  - Replaced magic numbers throughout codebase
- **Deleted dead files**:
  - `backend/create_account_db.py` (unused)
  - `backend/create_db.py` (replaced with inline command)
- **Updated Makefile**: `create-db` target now uses inline Python command

### CSV Import/Export Fixes
- **Fixed CSV export `proceeds_usd`**: Now falls back to `proceeds_usd` when `gross_proceeds_usd` is None
- **Relaxed CSV import validation**: Now matches transaction service rules
  - Deposit: External → any internal account (BTC or USD)
  - Withdrawal: any internal account → External
  - Transfer: between internal accounts of same currency

### Testing

#### Comprehensive Test Suite (`backend/tests/test_everything.py`)
78 automated tests covering:
- Database seeding with 65 test transactions
- All API endpoints (accounts, transactions, calculations, debug)
- All report generation (Complete Tax Report, IRS Forms, Transaction History)
- CSV export/import roundtrip verification
- FIFO integrity (lots, disposals, account balance matching)
- Gains/losses calculations and income tracking
- All transaction types, withdrawal purposes, deposit sources
- Holding period verification (short-term vs long-term)

Run with: `python3 backend/tests/test_everything.py`

#### Authentication Test Suite (`backend/tests/test_password_migration.py`)
Comprehensive auth tests:
- Password hashing and verification
- 72-byte bcrypt limit enforcement
- Unicode and special character passwords
- Login/logout endpoint tests
- Session persistence tests
- Protected endpoint authentication
- Backward compatibility with existing hashes

Run with: `pytest backend/tests/test_password_migration.py -v`

#### Updated Seed Data (`backend/tests/transaction_seed_data.json`)
- 65 transactions across 2023-2025
- All 5 deposit sources: MyBTC, Gift, Income, Interest, Reward
- All 4 withdrawal purposes: Spent, Gift, Donation, Lost
- Short-term and long-term gains coverage
- USD and BTC deposits to various accounts

### Dependency Updates

| Package | Old Version | New Version |
|---------|-------------|-------------|
| pydantic | 2.10.6 | 2.12.5 |
| uvicorn | 0.34.0 | 0.40.0 |
| sqlalchemy | 2.0.37 | 2.0.45 |
| httpx | 0.24.1 | 0.28.1 |
| requests | 2.28.1 | 2.32.0 |
| python-multipart | 0.0.6 | 0.0.20 |
| python-dateutil | 2.8.2 | 2.9.0 |
| itsdangerous | 2.1.2 | 2.2.0 |
| reportlab | 3.6.12 | 4.4.7 |
| pytest | 8.1.1 | 8.3.5 |

### Removed Dependencies
- `passlib` - replaced with direct bcrypt
- `typer` - unused
- `python-jose` - unused
- `pandas` - unused
- `weasyprint` - unused
- `pdfkit` - unused
- `jinja2` - unused (beyond FastAPI's built-in)
- `pycryptodome` - unused

### Files Added
- `backend/constants.py` - Centralized account ID constants
- `backend/tests/test_everything.py` - Comprehensive test suite (78 tests)
- `backend/tests/test_password_migration.py` - Authentication tests

### Files Modified
- `backend/models/user.py` - Direct bcrypt, 72-byte limit
- `backend/models/transaction.py` - FK indexes
- `backend/database.py` - Direct bcrypt for default user
- `backend/main.py` - Lifespan context manager
- `backend/services/transaction.py` - Query.get(), joinedload, constants
- `backend/routers/backup.py` - proceeds_usd fallback, constants
- `backend/routers/debug.py` - Query.get()
- `backend/services/csv_import.py` - Relaxed validation, constants
- `backend/services/reports/form_8949.py` - Removed duplicate import
- `backend/tests/register_default_user.py` - Direct bcrypt
- `backend/requirements.txt` - Updated all versions
- `Makefile` - Updated create-db target

### Files Deleted
- `backend/create_account_db.py`
- `backend/create_db.py`

---

## [v0.4.0] - 2025-01-12

### Added
- **CSV Template Import**: Bulk transaction import from CSV files
  - Download CSV template with exact column structure
  - Preview parsed transactions before importing
  - Full validation with error/warning display
  - Atomic import (all-or-nothing) with rollback on failure
  - Requires empty database (Phase 1 - no merge complexity)

### Endpoints
- `GET /api/import/template` - Download blank CSV template
- `GET /api/import/status` - Check if database is empty
- `POST /api/import/preview` - Parse and preview CSV (no DB writes)
- `POST /api/import/execute` - Execute atomic import

### Files Added
- `backend/schemas/csv_import.py` - Pydantic request/response models
- `backend/services/csv_import.py` - Parsing, validation, and import logic
- `backend/routers/csv_import.py` - API endpoints

### Fixed
- **Atomic imports**: Added `auto_commit` parameter to `create_transaction_record()`
  - Bulk imports now use `auto_commit=False` to defer commit until all succeed
  - Prevents partial imports on validation failures
- **Async event loop conflict**: Fixed `get_btc_price()` during CSV import
  - Used `ThreadPoolExecutor` to run async price fetches in separate threads
  - Fixes "Cannot run the event loop while another loop is running" error

---

## [v0.3.2] - 2025-01-10

### Fixed
- **Backup restore redirect**: Fixed "Not Found" error after successful backup restore
  - After restoring a backup, the session cookie still referenced the old user_id
  - Backend now clears session after restore (`request.session.clear()`)
  - Frontend redirects to `/login` instead of reloading the page
  - Users now see success message and are redirected to login properly

---

## [v0.3.1] - 2025-01-10

### Fixed
- **Backup/restore in Docker/StartOS**: Fixed `backup.py` to use `DATABASE_FILE` environment variable
  - Previously used hardcoded path `backend/bitcoin_tracker.db` which didn't match Docker's `/data/btctx.db`
  - Backup and restore now work correctly in containerized environments
- **Backup file cleanup race condition**: Fixed temp file deletion before streaming complete
  - Now uses FastAPI `BackgroundTasks` to delete temp file after response completes

### Documentation
- **StartOS container architecture**: Comprehensive documentation in `docs/STARTOS_COMPATIBILITY.md`
  - Two-repository architecture explanation
  - Volume mounts and data persistence
  - DATABASE_FILE environment variable
  - Common mistakes to avoid

---

## [v0.3.0] - 2025 IRS Form Support

### Added
- **Multi-year IRS form support**: Users can now generate IRS reports for both 2024 and 2025 tax years
- Year-based template folder structure (`backend/assets/irs_templates/2024/`, `2025/`)
- `get_template_path(year, form_name)` - Dynamic template path selection
- `get_supported_years()` - Returns list of available tax years
- `get_8949_field_config(year)` - Year-specific Form 8949 field naming
- `get_schedule_d_field_config(year)` - Year-specific Schedule D field naming
- 2025 IRS Form 8949 and Schedule D templates
- Comprehensive test dataset (40 transactions spanning 2023-2025)

### Fixed
- **Schedule D field mapping**: Changed from Line 1b/8b to Line 3/10 for self-tracked crypto
  - Self-custody Bitcoin uses Box C (short-term) and Box F (long-term) - not reported on 1099
  - Line 3 for short-term totals from Box C, Line 10 for long-term totals from Box F
- **Complete Tax Report generation**: Fixed Transfer lot restoration in `_partial_relot_strictly_after()`
  - Transfer transactions now properly restore source lot balances during year-boundary recalculations
  - Uses LIFO to reverse FIFO consumption when rebuilding transactions

### Changed
- `map_8949_rows_to_field_data()` now accepts `year` parameter for correct field naming
- `map_schedule_d_fields()` now accepts `year` parameter
- `fill_8949_multi_page()` now accepts `year` parameter
- `_verify_templates_exist()` now validates year-specific template availability
- IRS reports endpoint returns helpful error for unsupported years

### Technical Details
- 2024 Form 8949: `Table_Line1`, fields `f1_3` (not zero-padded)
- 2025 Form 8949: `Table_Line1_Part1`/`Part2`, fields `f1_03` (zero-padded for row 1)
- Schedule D Line 3 (Row3): Short-term from Box C/I (self-tracked, no 1099)
- Schedule D Line 10 (Row10): Long-term from Box F/L (self-tracked, no 1099)

---

## [v0.2.0-beta] - StartOS Packaging Complete

### Added
- `docs/` directory for project documentation
- `CLAUDE.md` - AI assistant context file (root directory for auto-detection)
- `docs/CHANGELOG.md` - This file
- `docs/ROADMAP.md` - Future goals and planned features
- `docs/STARTOS_COMPATIBILITY.md` - Docker requirements for StartOS packaging

### Changed
- Updated `README.md` with current Docker instructions and accurate tech stack

---

## [2025-01-10] - Docker Compatibility & Cleanup

### Fixed
- **PDF generation paths**: Changed relative paths to absolute paths in `backend/routers/reports.py`
  - IRS Form 8949 and Schedule D templates now load correctly regardless of working directory
  - Added `_verify_pdftk_installed()` and `_verify_templates_exist()` pre-flight checks

- **BTC price fetching in Docker**: Fixed `get_btc_price()` in `backend/services/transaction.py`
  - Previously made HTTP calls to `localhost:8000` which failed in Docker (port 80)
  - Now calls bitcoin service functions directly via import

- **Python 3.9 compatibility**: Added `from __future__ import annotations` to:
  - `backend/schemas/transaction.py`
  - `backend/services/user.py`
  - Fixes `TypeError: unsupported operand type(s) for |` for union type syntax

### Changed
- Cleaned up 63 stale branches across repositories
- Established `master`/`develop` branch workflow

### Infrastructure
- Docker image published to `b1ackswan/btctx:latest`
- All repositories synced

---

## [Pre-2025] - Initial Development

### Features
- Double-entry accounting system for BTC transactions
- FIFO cost basis tracking with BitcoinLot/LotDisposal models
- IRS Form 8949 and Schedule D PDF generation
- Dashboard with holdings, balances, and gains
- Transaction entry form (Deposit, Withdraw, Transfer, Buy, Sell)
- Historical BTC price fetching (CoinGecko, Kraken, CoinDesk)
- Session-based authentication
- CSV/PDF transaction history export
