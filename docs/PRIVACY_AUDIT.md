# Privacy and leak audit

## Every request BitcoinTX can make (1.2.8, re-checked for 1.2.9)

The stable candidate's privacy audit (#151; develop 72ba76f, 2026-10-12,
re-checked on 16bf055, 2026-10-13; for 1.2.9 on b785a00b, 2026-10-16,
below the table). It supersedes the 1.2.1 table below
where they differ (Coinbase and CoinGecko are gone, hourly prices are
new); the 1.2.1 audit stays as the record of its fixes. When a change
touches what leaves the machine, check it against this table and update
it.

**Result: nothing goes out before the owner chooses, no request names a date or an hour, Tor carries every request to a public site whenever it's set (except Bitstamp's fixed history blocks once the owner answers Yes to downloading them without Tor, #241: below), the download checks its fingerprints and never changes a stored price, and nothing goes to Coinbase or CoinGecko.** Each row is pinned by the tests named (all in `backend/tests/` unless said), and was also observed: Claude drove a real app (temp database) through the price paths under 13 choices with a recording fake internet (table at the end).

**What every request to a public site reveals:** the server's IP address (unless Tor, or a VPN such as StartOS's Set Outbound Gateway), the time (that BitcoinTX is open, or that a price was needed just then), and a generic client (`python-httpx`, the same for every install). Never a ledger date, hour, amount or address.

| # | Request | When it can happen | Tor | Tests |
|---|---|---|---|---|
| 1 | **Live price, your Mempool:** `GET <your Mempool>/api/v1/prices` | Your Mempool chosen (and confirmed), a page showing the price open (the sidebar every 2 minutes, the Dashboard); the server asks at most once a minute | Direct: it's on your network (the card says so); an `.onion` only through Tor | `test_network_settings`: `test_your_own_mempool_server_only`, `test_the_live_price_is_asked_once_a_minute`, `test_an_onion_mempool_address_needs_the_proxy`, `test_a_server_set_onion_without_a_proxy_is_never_asked`, `test_mempool_on_startos_through_the_bridge_address` |
| 2 | **Live price, public:** `GET https://api.kraken.com/0/public/Ticker?pair=XBTUSD`, else `GET https://www.bitstamp.net/api/v2/ticker/btcusd/` | Public sites chosen, or your Mempool with its backup when it can't answer; as row 1 | Yes | `test_the_live_price_asks_kraken_first_then_bitstamp`, `test_the_dashboard_and_sidebar_asking_at_once_make_one_request`, `test_your_mempool_with_fallback_asks_the_public_sites_when_it_is_down`, `test_the_proxy_carries_public_requests_and_skips_a_local_mempool` |
| 3 | **Block height:** `GET <your Mempool>/api/blocks/tip/height`; public: `blockchain.info/q/getblockcount`, else `blockstream.info/api/blocks/tip/height`, else `mempool.space/api/blocks/tip/height` | The Dashboard opens; at most once a minute | As rows 1 and 2 | `test_the_block_height_is_asked_at_most_once_a_minute`, `test_your_own_mempool_server_only` |
| 4 | **Past prices, your Mempool:** `GET <your Mempool>/api/v1/historical-price?currency=USD` (its whole history, one request) | A value needs a day or hour that isn't stored; at most every 10 minutes, shared by day and hour lookups | As row 1 | `test_price_history`: `test_mempool_hourly_midnights_are_used_and_nothing_public_is_asked`; `test_hourly_prices`: `test_a_mempool_server_gives_hours_after_the_files_and_the_asked_hour_within_them`, `test_the_day_lookup_after_the_hour_lookup_gets_the_mempool_servers_day` |
| 5 | **Daily history, public:** `GET https://www.bitstamp.net/api/v2/ohlc/btcusd/?step=86400&limit=1000&start=<fixed block from 2011-08-18>` (6 requests today); then "the latest days": the same without `start`, else `https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440` | The whole history once, when a value needs a day that isn't stored (retried after 10 minutes if a block fails); the latest days at most once a UTC day | Yes; the whole history's fixed blocks directly after the owner's Yes (#241, below), the latest days always through Tor | `test_price_history`: `test_the_whole_history_comes_in_the_same_requests_whatever_the_day`, `test_a_new_day_later_asks_only_for_the_latest_days`, `test_the_latest_days_ask_bitstamp_then_kraken_and_nothing_else`, `test_when_bitstamp_is_down_no_other_site_is_asked_and_it_is_tried_again_later`, `test_nothing_is_asked_until_a_source_is_chosen_or_when_off` |
| 6 | **The hourly history's download (#144):** `GET https://www.bitstamp.net/api/v2/ohlc/btcusd/?step=3600&limit=1000&start=<1 January 00:00 UTC + k × 1,000 hours>`, every year from 2013 to the manifest's last hour, newest year first (124 requests today, 0.2 s apart) | In the background once public sites are allowed (Public, or your Mempool with its backup): at start, when the choice is saved, and when a lookup needs a year that isn't here. Each request checks the choice as it is then: none once public sites aren't allowed, through the proxy set then. A year is kept only if it gives the fingerprint in `MANIFEST.csv`; a stored hour is never replaced | Yes (also on the VM over real Tor: release test PRC-3b); directly after the owner's Yes (#241, below) | `test_hourly_prices`: `test_the_year_files_come_in_fixed_blocks_newest_year_first_and_are_checked`, `test_a_year_that_doesnt_give_its_fingerprint_is_never_used`, `test_a_file_that_doesnt_give_its_fingerprint_is_never_read`, `test_nothing_is_downloaded_unless_public_sites_are_allowed`, `test_the_download_stops_when_public_sites_stop_being_allowed`, `test_the_download_stops_at_the_next_request_when_public_sites_stop_being_allowed`, `test_a_proxy_set_during_the_download_carries_the_next_request`, `test_a_stored_hour_wins_over_the_files`, `test_a_stored_hour_is_never_replaced_by_a_source`; `test_price_files`: `test_a_year_is_asked_in_the_same_fixed_blocks_on_every_install` |
| 7 | **Hours after the year files:** the same URL, `start` = the hour after the manifest's last + k × 1,000 hours (the same for every install of a release) | A value needs an hour after the files that your Mempool (if any) doesn't have; at most every 10 minutes; blocks already stored are skipped; the current hour only once it has traded | Yes; directly after the owner's Yes (#241, below) | `test_hours_after_the_files_come_from_bitstamps_fixed_blocks_and_are_stored`, `test_a_block_with_an_hour_missing_is_asked_again`, `test_while_the_mempool_server_answers_bitstamp_isnt_asked`, `test_the_current_hour_comes_from_bitstamp_once_it_has_traded` |
| 8 | **"Trust this server" (#188):** a TLS handshake only (no HTTP request) with your Mempool's `https://` address | When you click Trust this server (to show its root and fingerprint) and when you confirm; only for a home-network address (`.local`, `.lan`, a one-word name, 10.x, 172.16–31.x, 192.168.x); login only | Direct (a home address) | `test_mempool_trust`: `test_a_home_servers_mempool_untrusted_then_trusted_then_forgotten`, `test_a_public_address_is_never_offered`, `test_only_for_your_own_mempool_in_use`, `test_never_with_the_ai_key`, `test_the_trusted_root_is_never_used_for_public_sites` |
| 9 | **IRS draft forms:** `GET https://www.irs.gov/pub/irs-dft/f8949--dft.pdf` and `f1040sd--dft.pdf` | Only when someone runs `python -m backend.cli install-draft-forms` on a test install: no screen, route or AI tool reaches it | Direct (an admin's command, `outbound.py`'s one exception) | `test_draft_forms`: `test_off_by_default`, `test_cli_installs_checks_and_removes_the_drafts`; `test_network_settings`: `test_no_other_module_makes_its_own_http_client` |
| 10 | **The screens:** only the server they came from (`/api`, relative) | Always | n/a | `test_privacy`: `test_the_screens_ask_only_the_server_they_came_from` (new, #196: the Mac app's window has no CSP, so the code must name no other site), `test_fonts_are_bundled_not_fetched_from_google`, `test_every_response_says_no_referrer_nosniff_no_framing` (browsers: `connect-src 'self'`). Links (this repository, uv's docs) open only when clicked |
| 11 | **The AI connector:** only `BTCTX_URL` (your BitcoinTX), never a redirect, the key only to that address | While your AI app uses it | n/a | `mcp_server/tests/test_ai_key_client.py`: `test_a_redirect_is_a_clear_error_and_is_not_followed` |
| 12 | **Nothing else** | | | `test_no_other_module_makes_its_own_http_client` (no backend module makes a client or a raw connection but `outbound.py`); `test_settings_names_every_site_public_prices_may_contact` (#196: every backend module's addresses are the five sites Settings names, never Coinbase or CoinGecko) |

**Bitstamp's history without Tor (#241, the owner's decision of 2026-10-16; 1.2.9):** through Tor, Bitstamp refuses BitcoinTX's requests (a 403 or a "Loading" page), so rows 5 to 7's Bitstamp blocks never arrive. Once Bitstamp has refused through the proxy (never before: a Tor that isn't running is no refusal), the price card asks once, on the Dashboard and in Settings: "Download the price history once without Tor? It's the same download for every install, and names none of your dates; Bitstamp would see this server's address." The answer is recorded (when, and on the Dashboard or in Settings), login only (never the AI key), kept across restarts and by an in-app restore, and changeable in Settings, even while the server sets the choice (StartOS's action: its Use Tor text says so). **No** changes nothing. **Yes**, while a proxy is set and public sites are allowed (checked before each request), sends directly only rows 5 to 7's fixed blocks: `ohlc/btcusd/?step=3600|86400&limit=1000&start=<a block start>`; `outbound.FixedBlocksOnly` refuses anything else on that route before it's sent (another site, Bitstamp without `start`, a `start` that isn't one of those fixed block starts, which no ledger decides). Rows 2, 3 and 5's latest days stay on Tor. Bitstamp then sees this server's IP address and when: the year files once (at start or at the Yes: nothing in them depends on the ledger), the daily history once (when a value first needs a day that isn't stored), and the newer hours at most every 10 minutes when a value needs an hour after the year files (that a recent value is priced, never which hour): what it sees today without Tor. Tests: `test_history_without_tor.py` (every one), `frontend/e2e/price-card.e2e.ts` ("through a Tor Bitstamp refuses"). Observed on the lab VM over Start9's real Tor service: see #389.

**A change of the choice while a lookup is under way (#437; 1.2.9):** a lookup can outlast a save of Settings → Privacy & network (it may wait for your own Mempool for up to 90 seconds before turning to the public sites). Each request is checked against the settings in use just before it's sent: one to a public site goes only while they allow public sites, through the same proxy its client was made with (`outbound.async_client`, also under `history_client`), and one to your Mempool only to the address in use, with the same proxy and trusted root (`outbound.own_node_client`); any other is refused before it's sent (`outbound.ChoiceChanged`). Before, a lookup that started under "your Mempool, with public sites as backup, through Tor" and outlasted a save of Nobody with no proxy asked Bitstamp directly. Tests: `test_choice_at_each_request.py` (every one).

**Nothing before the owner chooses:** a fresh install has the source `unset` and asks nobody (`test_a_fresh_install_asks_nothing_until_the_owner_chooses`, `test_off_or_unchosen_asks_nobody`, `test_entries_made_before_choosing_never_turn_public_sites_on`); a stored choice with no record of when it was made sends nothing until the owner confirms it (`test_price_confirm.py`, the plan's 10 cases); invalid server settings, or an invalid server Tor, ask nobody (`test_invalid_server_settings_turn_lookups_off`, `test_a_bad_server_tor_asks_nobody_and_a_server_set_choice_ignores_it`); a command never makes a choice (#134, `test_10_a_command_and_the_ai_key_never_write_the_record`). On StartOS the price step is critical at install, before the service starts (release test INS-2), and the app asks nothing while it's unset anyway.

**Outside BitcoinTX (for completeness):** StartOS's own screens show the Mempool and Tor dependency icons from GitHub (`startos/startos/dependencies.ts`, commit-pinned; Start9's dependency metadata, `dependencies.md`). Mempool's own exchange-rate requests are Mempool's (its own Tor setting; `instructions.md` says so). The AI app downloads the connector from PyPI (`uvx btctx-mcp==X.Y.Z`). The developer tools (`make prices`, the monthly and IRS watch workflows) run on GitHub or the developer's computer, never in an install.

**Observed (a real app on a temp database, every outside request recorded):** start, save the choice, the status line, the live price twice, the block height, a price and an income deposit at three moments (2019, 2024, three days ago), a day in 2016, a spend, Ledger Review, the 2024 Complete Tax Report.

| Choice | Requests | Where, and through what |
|---|---|---|
| Not chosen; Nobody; StartOS Nobody; StartOS invalid; StartOS "Decide in BitcoinTX" + Tor, nothing chosen | 0 | — |
| Public | 132 | Kraken (live), Blockchain.info (height), Bitstamp 6 daily + 124 hourly blocks; direct |
| Public + Tor; StartOS Public + Tor | 132 | the same, every one through Tor |
| Your Mempool (no backup); StartOS My Mempool | 3 | your Mempool only: live price, height, whole history |
| Your Mempool + backup (± Tor) | 133 | your Mempool 3, direct; Bitstamp 130 (through Tor when set) |
| Your Mempool at an `.onion` + Tor | 3 | your Mempool, through Tor |

In every run: every Bitstamp `start` was one of the fixed block starts, no request carried any of the ledger's dates or hours (as a date, a Unix time, its hour or its day), and none went to Coinbase or CoinGecko.

Re-checked on develop 16bf055 (2026-10-13): every test named above exists, and their files pass (252 backend + 13 connector tests).

**Re-checked for 1.2.9** (#371; develop b785a00b, 2026-10-16, every change since v1.2.8): the table holds as it is. No new kind of request, and `outbound.py`, `hourly_prices.py` and `mempool_trust.py` are unchanged. What changed: more moments for the same lookups (rows 4 to 7), and new answers and screens that ask nobody:
- A gift's, donation's or lost coins' value (#255): left blank, it's filled from the price when it's saved, as a blank income value is, and with no price it stays blank; the AI import fills one too (now lost coins as well), in its preview already; Ledger Review shows a blank or $0 one at its hour's price. Each asks as for an income value. A recalculation never prices it.
- The AI connector's answers and the transactions API (`values_from_price` beside `price_used`) say which price a value came from (#208): read from this install's table and files, never asked.
- The sidebar's new line (#208) says where the live price it already asks for (rows 1 and 2) came from, and reads the settings; the form's new hint reads only the settings and the price status. Neither asks anybody, and neither do the login's tax-timezone fill (#334) or Delete All (#256) (checked with every connection and DNS lookup blocked).
- The AI connector reads its own version from its installed package (#133): no PyPI request; it still asks only your BitcoinTX.

Every test named above still exists, and their files pass on the release's locked dependencies (264 backend + 13 connector tests). Observed again through the paths 1.2.9 changed (the login's timezone fill, a My BTC and an income deposit, a gift, a donation, lost coins and a spend with blank values, the transactions list, Ledger Review, Delete All's count and delete, an AI import preview, the 2024 Complete Tax Report), with the smoke test's fake internet (`scripts/smoke_test.py`), which answers no hourly block: the hourly download stops after its first request, so rows 6 and 7 were seen only that far. Not chosen, Nobody: 0 requests; Public: 7 (Bitstamp's 6 daily blocks and 1 hourly), direct; Public + Tor: the same 7, every one through Tor; your Mempool: 1, its whole history; your Mempool with its backup: that one plus 1 Bitstamp block. Every Bitstamp `start` was a fixed block start, no request named any of the ledger's dates or hours, and none went to Coinbase or CoinGecko.

## The 1.2.1 audit (2026-09-29)

Every way data or metadata leaves the machine or sits on disk, with a
verdict. Code read on `develop` (1.2.1 plus the VM-test fixes, 8858dd5);
live checks on the StartOS VM. "Checked" means Claude re-read the code or
saw it on the VM, not only the audit agent. The fixes shipped in **1.2.2**
(`docs/CHANGELOG.md`, "Privacy"); the owner decided each one that changes
what they see (recorded in the table).

Verdicts: **no leak** (verified) · **leak** (real, not documented) ·
**documented only** (real, the app warns) · **fix proposed**.

### The short answer

The core promise holds: **no request ever names a transaction date**,
**nothing is contacted until the owner picks a price source** (and nothing
at all when it's Off), **Tor fails closed** (seen on the VM: every request
failed, none went direct), the browser talks only to the app itself, and
secrets are never logged. What's left is smaller: five real leaks, all
minor, and some things that are only documented.

### Summary

| # | Item | Verdict | One line | Checked |
|---|---|---|---|---|
| 1a | One HTTP client factory (`outbound.py`) | no leak | a test enforces it; the Mac app only calls 127.0.0.1 | |
| 1b | Unset or Off, and at startup | no leak | nothing contacted, incl. MCP tools, reports, review, import autofill | VM (PRC-1) |
| 1c | Date-free URLs, fallbacks included | no leak | fixed history blocks and "latest" requests | VM (Bitstamp URLs) |
| 1d | Timing seen by price sites | **documented** (Settings, StartOS); block height cached 60 s | they can tell when the app is open (price every 2 min while a page is visible) and when a recent entry is priced | |
| 1e | Hosts named in Settings | **fixed** (all named, plus timing; test guards new hosts) | mempool.space, Coinbase and Kraken's history are contacted but never named | yes |
| 1f | User-Agent `python-httpx/0.28.1` | no leak | the same for every install; don't add a version | |
| 1g | socks5 vs socks5h, fail closed | no leak | the hostname goes to the proxy either way; no direct retry | VM (PRC-3, PRC-3b) |
| 1h | `.onion` mempool address with no proxy | **fixed** (was: leak) | accepted, then looked up through normal DNS | yes |
| 1i | Clearnet mempool server bypasses Tor | documented only | Settings says only `.onion` uses the proxy | |
| 1j | In-app restore brings back the backup's price settings | **fixed** (owner: keep the settings in use) | an old "public, no proxy" backup turns lookups on again, directly; the code does it on purpose (the AI key and login, by contrast, stay) | yes |
| 1k | CoinGecko refuses VPN and Tor addresses | **fixed** (owner: Kraken first, CoinGecko fallback; CoinGecko dropped 2026-10-12, #161: Bitstamp is the fallback) | CloudFront 403 from a VPN IP and from Tor; every live price then costs two sites (CoinGecko, Kraken) | VM + curl |
| 2 | Browser: CSP, headers, cookie, storage, links, Mac webview | no leak | strict CSP, no-referrer, HttpOnly cookie, no browser storage, only self-hosted fonts | VM (SEC-3, SEC-7) |
| 3a | Service logs | **counts fixed**; httpx URLs remain (minor) | no secrets or dates, but per-year counts at INFO, whole rows at DEBUG, every outbound URL (httpx) | VM (log read) |
| 3b | Encrypted backup file | **fixed** (owner: hidden, typed twice; 12+ characters for a new backup since 1.2.9, #204) | good crypto (AES-256 + HMAC, PBKDF2 600k); the password is typed into a plain `prompt()`, shown, not confirmed, no minimum | yes |
| 3c | Temporary plain copy while backing up | **fixed** | a plain SQLite snapshot in the system temp folder (0700, deleted after); the restore's staging file is chmod'ed after writing | yes |
| 3d | Plain copies in `<data>/backups/` | **documented in Settings** | up to 5 pre-upgrade/pre-restore, 5 before Ledger Review's hourly prices, 5 before every transaction is deleted (#256: the deleted ledger itself) + 11 AI copies, unencrypted, outlive deleted entries; in the docs, not the app | |
| 3e | Deleted rows stay in the SQLite file | **fixed** (secure_delete) | no `secure_delete`, no VACUUM | |
| 3f | File permissions | no leak | database, secret key, setup code, `mcp.json`: 0600 | VM (`/data` listing) |
| 3g | Docker `/data` is `chmod 777` | **fixed** (700) | cosmetic in a root-only container | |
| 3h | StartOS backup contents | documented only | the database, secret key, plain copies, and `store.json` with the generated password in clear (stale once changed) | |
| 4a | What the AI provider sees | documented only | the whole ledger through the tools, plus the tax timezone; warned in four places | VM (AI-1) |
| 4b | Setup prompt contains the server address | documented only | a LAN or `.onion` address and the app version go to the provider when pasted | VM |
| 4c | AI key over `http://` | **warned** (owner: connector warns once) | no scheme check in the connector; the README's own example is `http://192.168.1.50:8080` | |
| 4d | Connector logs | **fixed** (was: leak) | the MCP SDK logs at INFO, so httpx writes `…/price/history?date=2024-03-05` into the AI app's log files | yes |
| 4e | `uvx` fetches from PyPI | **documented** (READMEs) | PyPI sees the IP, time and exact version | |
| 5a | StartOS interfaces | no leak | only HTTPS is offered on the LAN; plain HTTP only inside the server (lo, lxcbr0); nothing public unless the owner turns it on | VM (host bindings) |
| 5b | Docker publishes plain HTTP on all interfaces | **fixed** (README: 127.0.0.1 + HTTPS note) | README uses `-p 8080:80` with no warning: password, cookie and ledger in clear on the LAN | yes |
| 5c | `/api/health` version; `server: uvicorn` | **server header fixed**; health version kept (the Mac app and connector read it) | version fingerprinting from the LAN or Tor | VM (SEC-3) |

### Details worth reading

- **1d Timing.** The live price is asked every 120 s while any page is
  visible (the sidebar converter), with a 60 s server cache; block height
  on every Dashboard visit, no cache. The "latest days" history download
  runs when the owner values a day newer than the last download, at most
  once a UTC day: it shows *that* a recent entry is being made, not its
  date. IP exposure is documented (Settings, StartOS instructions); timing
  isn't.
- **1h `.onion` without a proxy.** `outbound.save` accepts it and
  `own_node_client` connects directly, so the system resolver (and
  whoever runs it) sees the onion name; the connection then fails.
- **1j Restore.** `routers/backup.py:133` reloads the restored database's
  price source, mempool address and proxy ("The restored database carries
  its own network settings"). Someone who moved to Tor since the backup
  gets direct requests again after restoring it. The AI key and switch are
  kept by `ai_key.carry_over`; the same could be done for these four
  settings. Not an issue when StartOS's action sets them.
- **3a Logs.** `reports.py:106`, `transaction_history.py:129-132,315,441`,
  `reporting_core.py:183` log per-year counts ("Found 4 transactions for
  year=2025 in date range …") at INFO; `LOG_LEVEL=DEBUG` dumps rows.
- **3h StartOS backup.** Volumes `main` and `startos` (`backups.ts`). A
  StartOS-level restore brings back the old login and AI key (unlike the
  in-app restore) — that's StartOS restoring the whole service, expected.
- **4d Connector logs.** Verified: after importing the server, the root
  logger is INFO with a RichHandler and httpx inherits it. Claude Desktop
  keeps MCP server stderr in `~/Library/Logs/Claude/`. The key isn't
  logged; request lines are.
- **5b Docker.** `uvicorn --host 0.0.0.0` inside the container is normal;
  the README's `-p 8080:80` publishes it on every interface. The setup
  code still protects a fresh install, but after that the login travels
  in clear to any LAN client.

### Outcome (1.2.2)

All eleven proposed fixes were made, smallest safe change each; the "fixed",
"documented" and "warned" verdicts above are their results. Left as they
are, on purpose: 1i (a clearnet mempool server doesn't go through Tor;
Settings says so), 3h (a StartOS backup holds the whole service, as
expected), 4a and 4b (what the AI provider sees; warned in the app and
docs), and the health endpoint's version (5c; the Mac app and the connector
read it). httpx still logs outbound URLs in the app's own service log (3a):
no secrets or dates.
