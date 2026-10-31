# Agent release tests

What an AI agent (or a person) runs on a real install before each release:
the packaged app on a StartOS VM, driven through its web UI, its StartOS
actions and a real MCP client, against a ledger whose every figure is known
in advance. Point the agent at this file and give it the inputs under
[Setup](#setup).

CI already tests the tax engine, every form, every transaction type and
the whole UI on every pull request (see below). This walk tests what CI can't
reach: the `.s9pk` on a real StartOS, TLS through StartOS's proxy, the
actions and tasks, backups, updating from the last release, real price
sources and a real MCP client. It touches every feature once, with exact
expected values, so a broken package shows as a wrong number, not a
feeling.

## Rules for the agent

1. **Throwaway installs only.** A StartOS VM restored from a clean
   snapshot, never a server with anyone's real ledger: these tests delete
   everything.
2. **A check passes only when what you saw equals the Expect text.** Write
   the observed value into the report next to each ID. "Looks right" is
   not a result. Amounts must match to the cent and the satoshi;
   formatting (`1,000.00` vs `1000.00`, `−` vs `-`) doesn't matter.
3. **Don't fix, skip or reinterpret.** If you can't do a step, mark it
   BLOCKED with the reason and carry on. Stop early only where a step says
   STOP.
4. **On FAIL**, record the exact text or a screenshot, the steps since the
   last check that passed, and carry on.
5. Items under [Known issues](#known-issues) are expected to fail. Report
   them as KNOWN, not as new findings. If one passes, say so: it was fixed.
6. Work in the order given. Later sections assume the state earlier ones
   left.
7. Budget: about 4 hours for Track A, 1 hour 15 minutes for Track B, 45
   minutes for Track C, and 20 minutes for REF. From 2.0 on, a release
   that comes from 1.x (2.0 and its pre-releases) adds about 1½ hours
   for WAY, and a pre-release about 1½ hours for BETA. 2.0.0 adds about
   an hour for CB, once Start9 has merged it.

## What CI already proves (don't redo)

| Layer | Where | Covers |
|---|---|---|
| Unit and integration tests (every test but the slow ones, backend and MCP server) | `make test-fast` | FIFO, fees, proceeds, holding period, tax timezone, 1099-DA boxes, imports, the printed forms read back, auth, AI key, MCP tools |
| Golden years and property tests | `backend/tests/test_golden_years.py`, `test_invariants_property.py` | the hand-worked ledger used below, and random ledgers keeping every invariant |
| Click-through | `frontend/e2e/` (Chromium and WebKit, Chicago and Tokyo) | every transaction type, edit and delete, list, dashboard, River's, other exchanges' and CSV imports, every report download, Settings, widgets |
| Smoke | `scripts/smoke_test.py`, also against the Docker image | the real server end to end |
| Packaging | `ci.yml` | Docker image, StartOS package checks and an x86_64 `.s9pk`, macOS app build and launch |

**T0 (gate):** CI is green on the release-candidate commit, meaning every
job on that commit's run in the Actions tab. If it isn't, STOP: the release
isn't ready for this walk.

## Setup

### Inputs

| Item | Where |
|---|---|
| Release candidate | the `develop` commit that bumps `VERSION` to the new version (call it `X.Y.Z`, the commit `$SHA`) |
| `btctx_x86_64.s9pk` | that commit's CI run, artifact `btctx-s9pk-x86_64` (`gh run download <run id> -n btctx-s9pk-x86_64`) |
| Previous release's `btctx.s9pk` | the latest release on https://github.com/DigiMonk73/BTCTX-MCP/releases (Track B) |
| Mac app | the same CI run, artifact `BitcoinTX-macOS` (Track C); for a pre-release `BitcoinTX-Preview-macOS`, holding `BitcoinTX Preview.app` |
| MCP connector | not on PyPI until the release, so run it from the commit: `uvx --from "git+https://github.com/DigiMonk73/BTCTX-MCP@$SHA#subdirectory=mcp_server" btctx-mcp` |
| The last 1.x release (2.0 and its pre-releases: Track B, AI-15, AI-16, MAC-UPG, WAY) | v1.2.10 (or a later 1.x, if one comes out first; the steps name 1.2.10) on https://github.com/DigiMonk73/BTCTX-MCP/releases: its `btctx.s9pk` and `BitcoinTX-macOS.zip`; its Docker image `ghcr.io/digimonk73/btctx-mcp:v1.2.10`; its connector `uvx btctx-mcp==1.2.10` |
| A pre-release (BETA) | the GitHub pre-release `v2.0.0-alpha.N` or `v2.0.0-beta.N` (never "Latest"): its `btctx.s9pk`, `BitcoinTX-Preview-macOS.zip`, the image `ghcr.io/digimonk73/btctx-mcp:v2.0.0-beta.N` (or `-alpha.N`) and the connector `uvx btctx-mcp==2.0.0bN` (an alpha's `2.0.0aN`); for BETA-2 also the pre-release before it |

After the release is published, repeat INS-1 to INS-7 and AI-7 to AI-8
with the published `btctx.s9pk` and `uvx btctx-mcp==X.Y.Z`. That confirms
the published files are the ones you tested.

2.0's Track B starts from the last 1.x release: the previous release
GitHub marks "Latest" is still a 1.x while 2.0 is in pre-releases, and is
1.2.10 when 2.0.0 comes out.

To walk a published pre-release (or any build that isn't the tip), use
this file as it is at that build's tag or commit (`git show
v2.0.0-alpha.N:docs/AGENT-TESTS.md`, or `git show
$SHA:docs/AGENT-TESTS.md`): its steps quote that build's screens, and a
later commit can change both together. A step that reads as a FAIL there
may have been corrected since: the tip's CHANGELOG, under Development,
names the release walk's corrections.

### The machine

- **StartOS VM** (x86_64, 4 GB RAM or more, a second virtual disk for
  StartOS backups: BAK-5, UPG-5b, WAY, BETA-1). Finish StartOS setup, then
  snapshot it as `clean`. Tracks A and B each start from `clean`. A
  StartOS backup and its restore ask for the VM's StartOS password: the
  person who set up the VM types it (an agent never stores it); without
  them, mark those steps BLOCKED.
- **Optional services on the VM:** Tor (PRC-3, PRC-3b). Mempool (PRC-4) needs a
  synced Bitcoin node, so skip it unless the VM has one.
- **Your browser runs in `America/New_York`.** The transaction form reads
  times in the browser's timezone, and the expected figures assume New York.
  With Playwright use `timezoneId: "America/New_York"`; otherwise set the
  OS timezone. AUTH-3 checks it.
- **Tools on your machine:** curl, Python 3.11+, [uv](https://docs.astral.sh/uv/),
  Node 20+ (for the MCP Inspector), a PDF text extractor such as
  `pdftotext` or pypdf, and, for WAY-6 and BETA-5, Docker.
- **Shell variables:** `URL` is the Web UI's https address from the
  service's Interfaces (for example `https://adjective-noun.local`), and
  `API=$URL/api`. Save StartOS's root CA as `ca.crt`: the Connect an AI
  Assistant action shows it (AI-7), or download it from System > About this
  Server. Every `curl` below uses `--cacert ca.crt`; with it on your
  browser's trust list, the browser needs no exceptions.

#### On an Apple-silicon Mac (UTM), as run on 2026-09-28

- StartOS's **aarch64** ISO (its release notes link it, with SHA-256 sums)
  runs at full speed in UTM (QEMU backend, hypervisor on, UEFI, 4 cores,
  8 GB, a 40 GB disk, shared network). The released `btctx.s9pk` is
  universal; CI's release-candidate artifact is x86_64 only, so on this VM
  pack an aarch64 one from the commit (`startos/UPDATING.md`, "Building
  locally").
- The installer answers at `start.local`; the server gets a new random name
  when setup finishes. For the `clean` snapshot, stop the VM and duplicate
  it in UTM (an APFS clone, no extra space).
- `start-cli` (the release CI uses, `start-cli_aarch64-macos`) drives the
  VM once the owner has run `start-cli -H $URL auth login`. It needs
  `--root-ca ca.crt`; installs from a registry need
  `-r https://registry.start9.com` (e.g. Tor); `package install -s` sideloads
  (a dropped progress socket is harmless: `package list` shows it
  installing); an action with input needs the `eventId` from
  `package action get-input` passed to `package action run --event-id`,
  with the input as JSON on stdin (`null` for none).
- On StartOS 0.4.1 or later, `package install` needs `--trust` (start-cli
  2.6.0 or later) for a package no enabled keyring signed: our own packages,
  and anything from Community Beta, which only Start9's community build key
  signs. Without it: "Signer(s) not accepted". On StartOS's own web page, a
  Community Beta install stays blocked until **Start9 Alpha** is on for
  service packages (System > Trusted keyrings). The Community Registry's
  1.2.10 needs neither.

### Settings, one section at a time (2.0)

From 2.0, Settings shows its sections closed, each a button with its title
and a one-line summary: **Account** (log out, username and password, Tax
Timezone, Recalculate Ledger), **Wallets, exchanges and banks**, **Ledger
Review**, **Privacy & Network**, **Connect an AI Assistant**, **Data
Management**, **Import from an exchange**, **Backup & Restore** and **About
BitcoinTX**. Opening one closes the one open before, and this browser
remembers the open one. "Settings, open **X**" below means: Settings in
the sidebar, then the button **X** (if it isn't open already). A 1.x
release (Track B before its update, WAY) shows every section at once.

### The golden ledger

Fourteen transactions over 2023–2025 whose results were worked out by
hand (`backend/tests/test_golden_years.py`). Every USD value is typed in,
including the two BTC fees' values and the income's basis, so the results
don't depend on the market price or on which price source is on.

Enter them in Transactions > **Add transaction**, then **Save
transaction**. **Date & Time** is New York time. Leave any field not
listed at its default.

From 2.0, a save, an edit or a delete that changes an earlier tax year
asks first (#352): a dialog names the years and what changes, with
**Save anyway (a copy is made first)** and **Cancel** (a delete's says
**Delete anyway**). Every golden row is in an earlier year, so the first
add of each year asks "This adds to tax year 2023, which you may already
have filed…"; tick **Don't ask again for adds to 2023 while this page is
open** and click **Save anyway**, and that year's next adds save without
asking. Edits and deletes always ask; a reload asks again. Each confirmed
save leaves a copy, `btctx-pre-change-past-year-….db`, in the data folder's
`backups`. The other writes that can change an earlier year ask the same
way (#353): the Tax Timezone's **Save** (Settings, **Account**), an
exchange's 1099-DA switch (MLT-4), an exchange file's import (River's or
another's: one question for the file), and, with the AI key, `add_transactions`, `update_transaction`,
`delete_transaction` and `recalculate_ledger`, whose answer is then
`saved: false` with the years, the changes and a `confirm` to call the
tool again with (`update_transaction` also takes it as `confirm_move`). PYW checks the
dialog's own rules.

In the form, an account picker starts blank whenever more than one
account fits, and names accounts as Settings does (`Bank`, `Wallet`,
`Exchange USD`, `Exchange BTC`); with one exchange, a Buy has no
**Exchange** field and a Sell's **Exchange** is filled in.

| # | Date & Time | Transaction Type | Fields | Toast after saving |
|---|---|---|---|---|
| 1 | 2023-01-15 12:00 | Deposit | Account `Bank`, Amount `100000` | Transaction created successfully! |
| 2 | 2023-02-01 12:00 | Buy | Paid from `Bank`, Amount USD `23000`, Amount BTC `1` | Transaction created successfully! |
| 3 | 2023-03-01 12:00 | Buy | Paid from `Bank`, Amount USD `12000`, Amount BTC `0.5` | Transaction created successfully! |
| 4 | 2023-06-01 12:00 | Transfer | From Account `Exchange BTC` (From Currency shows `BTC`), To Account `Wallet`, Amount (From) `0.6`, Amount (To) `0.5998`, Fee value (USD) `10`. Check: Fee (BTC) shows `0.0002` | Transaction created successfully! |
| 5 | 2023-09-10 12:00 | Sell | Amount BTC `0.5`, Gross Proceeds (USD) `13000`, Fee (USD) `10` | Transaction created! Realized Gain: +$1,390.00 |
| 6 | 2023-12-31 23:30 | Withdrawal | Account `Wallet`, Amount `0.01`, Purpose `Spent`, Proceeds (USD) `400` | … Realized Gain: +$170.00 |
| 7 | 2024-02-02 12:00 | Sell | Amount BTC `0.3`, Gross Proceeds (USD) `15000` | … Realized Gain: +$7,800.00 |
| 8 | 2024-03-02 12:00 | Sell | Amount BTC `0.1`, Gross Proceeds (USD) `6000` | … Realized Gain: +$3,600.00 |
| 9 | 2024-05-01 12:00 | Deposit | Account `Wallet`, Amount `0.02`, Source `Income`, Cost Basis (USD) `1000` | Transaction created successfully! |
| 10 | 2024-06-01 12:00 | Withdrawal | Account `Wallet`, Amount `0.1`, Purpose `Gift`, FMV (USD) `6700` | Transaction created successfully! |
| 11 | 2025-01-10 12:00 | Buy | Paid from `Bank`, Amount USD `20000`, Amount BTC `0.2` | Transaction created successfully! |
| 12 | 2025-04-01 12:00 | Sell | Amount BTC `0.05`, Gross Proceeds (USD) `4000` | … Realized Gain: −$1,000.00 |
| 13 | 2025-05-01 12:00 | Withdrawal | Account `Wallet`, Amount `0.1`, Purpose `Spent`, Proceeds (USD) `9000` | … Realized Gain: +$6,700.00 |
| 14 | 2025-06-01 12:00 | Withdrawal | Account `Wallet`, Amount `0.01`, Purpose `Spent`, Fee (BTC) `0.0001`, Fee value (USD) `5`, Proceeds (USD) `1000` | … Realized Gain: +$765.00 (the $5 fee comes off the proceeds, #157) |

What each row does: #4 moves lot A's BTC to the Wallet, and its fee is a
disposal. #6 is 04:30 UTC on Jan 1, 2024, but counts in 2023 because the tax
timezone is New York. #8 is sold one day after the one-year anniversary, so
it's long-term. #14's fee is its own disposal.

**Expected figures** (tax timezone `America/New_York`):

| Where | Expected |
|---|---|
| Dashboard > Portfolio Overview | Bank (USD) $45,000.00 · Exchange (USD) $37,990.00 · Exchange (BTC) 0.15000000 BTC · Wallet (BTC) 0.39970000 BTC · Total BTC 0.54970000 BTC · Avg. Cost per BTC $44,993.81 (with one account of each kind, no line has a caret; with more, the totals stay these) |
| … Unrealized Gains/Losses (needs a price) | current price × 0.5497 − 24,733.10, within $0.01 (each account's value to the cent less its cost, #770) |
| Dashboard > Realized Gains/Losses (Per-wallet FIFO) | Short-Term Gains +$9,365.40 · Short-Term Losses −$1,000.00 · Net Short-Term +$8,365.40 · Long-Term Gains +$11,067.70 · Long-Term Losses $0.00 · Net Long-Term +$11,067.70 · Total Net Capital Gains +$19,433.10 |
| Dashboard > Income & Fees | Income (earned) $1,000.00 (0.02000000 BTC) · Interest (earned) $0.00 (0.00000000 BTC) · Rewards (earned) $0.00 (0.00000000 BTC) · Total Income $1,000.00 · Gifts (received) $0.00 (0.00000000 BTC) · Rebates (received) $0.00 (0.00000000 BTC) · Fees (USD) $10.00 · Fees (BTC) 0.00030000 BTC · Total Fees in USD (approx) = 10 + 0.0003 × price |
| Form 8949 2024 (IRS Reports) | Part I, box C: `0.30000000 BTC · 03/01/2023 · 02/02/2024 · 15000.00 · 7200.00 · 7800.00`. Part II, box F: `0.10000000 BTC · 03/01/2023 · 03/02/2024 · 6000.00 · 2400.00 · 3600.00` |
| Schedule D 2024 | line 3: 15000.00 / 7200.00 / 7800.00 · line 10: 6000.00 / 2400.00 / 3600.00 |
| Form 8949 2025 | Part I, box H: `0.05000000 BTC · 01/10/2025 · 04/01/2025 · 4000.00 · 5000.00 · (1000.00)`. Part II, box L, three rows: `0.10000000 BTC · 02/01/2023 · 05/01/2025 · 9000.00 · 2300.00 · 6700.00`, `0.00010000 BTC · 02/01/2023 · 06/01/2025 · 5.00 · 2.30 · 2.70`, `0.01000000 BTC · 02/01/2023 · 06/01/2025 · 995.00 · 230.00 · 765.00` |
| Schedule D 2025 | line 2: 4000.00 / 5000.00 / (1000.00) · line 10: 10000.00 / 2532.30 / 7467.70 |
| Complete Tax Report 2023 (no IRS forms for 2023 in the app) | 1. Summary › Capital gains and losses: Short-term 4 disposals, Proceeds $13,400.00, Cost basis $11,834.60, Net gain $1,565.40; Long-term 0, all $0.00 (the cover's Net capital gain is the same $1,565.40). 2. Capital gains and losses lists, as Proceeds / Cost basis / Gain: 06/01/2023 0.0002 BTC ($10.00 / $4.60 / $5.40), 09/10/2023 0.4 and 0.1 BTC, and 12/31/2023 0.01 BTC ($400.00 / $230.00 / $170.00). 5. Holdings at year end, lot by lot: 0.58980000 BTC at cost $13,565.40 and 0.40000000 BTC at $9,600.00, total 0.98980000 / $23,165.40, "Average cost: $23,404.12 per BTC"; each Market value = quantity × the price the report states, "the price at the hour the tax year ended (2024-01-01 05:00 UTC)" (midnight in New York; "…'s 00:00 UTC price" where there was no hourly price) |
| Complete Tax Report, end of section 2: "Sales by exchange" (Exchange · Sends Form 1099-DA · Boxes · Rows · Proceeds · Cost basis · Gain (loss)) | 2023: `Exchange · — · C · 2 · $12,990.00 · $11,600.00 · $1,390.00`. 2024: `Exchange · — · C, F · 2 · $21,000.00 · $9,600.00 · $11,400.00` (no Form 1099-DA before 2025: "—"). 2025: `Exchange · Yes · H · 1 · $4,000.00 · $5,000.00 · ($1,000.00)`. Each row of section 2's list names its account under its kind ("Sale" / "Exchange BTC", "Spend" / "Wallet") |
| Complete Tax Report 2025, 6. Using these forms | "This year's boxes: H and L", "Schedule D: lines 2 and 10"; the Bitcoin-only figures: line 7 ($1,000.00), line 15 $7,467.70, line 16 $6,467.70, "Line 16 isn't a loss, so line 21 doesn't apply." |
| Complete Tax Report 2024 | 1. Summary › Bitcoin holdings, January 1, 2024: 0.98980000 BTC, Avg cost per BTC $23,404.12 (the same BTC as the 2023 report's year end). Summary › Income: Income $1,000.00, Total $1,000.00. 3. Income: 05/01/2024 Income 0.02000000 BTC $1,000.00. 4. Gifts, donations and lost coins: 06/01/2024 Gift 0.10000000 BTC, Fair market value $6,700.00. 5. Holdings at year end, lot by lot: 0.48980000 BTC at $11,265.40 and 0.02000000 BTC at $1,000.00, total 0.50980000 / $12,265.40 |
| Transaction History CSV | 2023: 6 rows (the Dec 31 spend is in it, stamped `2024-01-01T04:30:00+00:00`) · 2024: 4 rows · 2025: 4 rows |

**Loading it through the API.** Track B, and anywhere a step says "load
the golden ledger", uses this script. It refuses a ledger that isn't
empty. Save it as `golden_loader.py` and run:
`BTCTX_URL=$URL BTCTX_USER=<username> BTCTX_PASSWORD=<password> BTCTX_CA=ca.crt python3 golden_loader.py`.
Expect `14 transactions loaded; tax timezone America/New_York`.

```python
# Loads the golden ledger into an EMPTY BitcoinTX through its API.
import http.cookiejar
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

LEDGER = [
    {"type": "Deposit", "timestamp": "2023-01-15T17:00:00Z", "from_account_id": 99, "to_account_id": 1, "amount": "100000", "fee_amount": "0", "fee_currency": "USD", "source": "N/A"},
    {"type": "Buy", "timestamp": "2023-02-01T17:00:00Z", "from_account_id": 1, "to_account_id": 4, "amount": "1.0", "cost_basis_usd": "23000", "fee_amount": "0", "fee_currency": "USD"},
    {"type": "Buy", "timestamp": "2023-03-01T17:00:00Z", "from_account_id": 1, "to_account_id": 4, "amount": "0.5", "cost_basis_usd": "12000", "fee_amount": "0", "fee_currency": "USD"},
    {"type": "Transfer", "timestamp": "2023-06-01T16:00:00Z", "from_account_id": 4, "to_account_id": 2, "amount": "0.6", "fee_amount": "0.0002", "fee_currency": "BTC", "fee_usd": "10"},
    {"type": "Sell", "timestamp": "2023-09-10T16:00:00Z", "from_account_id": 4, "to_account_id": 3, "amount": "0.5", "gross_proceeds_usd": "13000", "fee_amount": "10", "fee_currency": "USD"},
    {"type": "Withdrawal", "timestamp": "2024-01-01T04:30:00Z", "from_account_id": 2, "to_account_id": 99, "amount": "0.01", "proceeds_usd": "400", "fee_amount": "0", "fee_currency": "BTC", "purpose": "Spent"},
    {"type": "Sell", "timestamp": "2024-02-02T17:00:00Z", "from_account_id": 4, "to_account_id": 3, "amount": "0.3", "gross_proceeds_usd": "15000", "fee_amount": "0", "fee_currency": "USD"},
    {"type": "Sell", "timestamp": "2024-03-02T17:00:00Z", "from_account_id": 4, "to_account_id": 3, "amount": "0.1", "gross_proceeds_usd": "6000", "fee_amount": "0", "fee_currency": "USD"},
    {"type": "Deposit", "timestamp": "2024-05-01T16:00:00Z", "from_account_id": 99, "to_account_id": 2, "amount": "0.02", "cost_basis_usd": "1000", "fee_amount": "0", "fee_currency": "BTC", "source": "Income"},
    {"type": "Withdrawal", "timestamp": "2024-06-01T16:00:00Z", "from_account_id": 2, "to_account_id": 99, "amount": "0.1", "fee_amount": "0", "fee_currency": "BTC", "purpose": "Gift", "fmv_usd": "6700"},
    {"type": "Buy", "timestamp": "2025-01-10T17:00:00Z", "from_account_id": 1, "to_account_id": 4, "amount": "0.2", "cost_basis_usd": "20000", "fee_amount": "0", "fee_currency": "USD"},
    {"type": "Sell", "timestamp": "2025-04-01T16:00:00Z", "from_account_id": 4, "to_account_id": 3, "amount": "0.05", "gross_proceeds_usd": "4000", "fee_amount": "0", "fee_currency": "USD"},
    {"type": "Withdrawal", "timestamp": "2025-05-01T16:00:00Z", "from_account_id": 2, "to_account_id": 99, "amount": "0.1", "proceeds_usd": "9000", "fee_amount": "0", "fee_currency": "BTC", "purpose": "Spent"},
    {"type": "Withdrawal", "timestamp": "2025-06-01T16:00:00Z", "from_account_id": 2, "to_account_id": 99, "amount": "0.01", "proceeds_usd": "1000", "fee_amount": "0.0001", "fee_currency": "BTC", "fee_usd": "5", "purpose": "Spent"},
]

URL = os.environ["BTCTX_URL"].rstrip("/")
tls = ssl.create_default_context(cafile=os.environ.get("BTCTX_CA") or None)
web = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                                  urllib.request.HTTPSHandler(context=tls))


def call(method, path, body=None, confirm=None):
    query = "" if confirm is None else "?confirm=" + urllib.parse.quote(confirm)
    req = urllib.request.Request(URL + path + query, method=method, headers={"Content-Type": "application/json"},
                                 data=None if body is None else json.dumps(body).encode())
    try:
        with web.open(req) as r:
            return json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        answer = e.read().decode()
        asked = _fingerprint(answer) if e.code == 409 and confirm is None else None
        if asked is not None:  # 2.0's past-year warning: every row here is in an earlier tax year
            return call(method, path, body, asked)
        sys.exit(f"{method} {path}: {e.code} {answer[:300]}")


def _fingerprint(answer):
    """The past-year warning's `confirm`, sent back once; None for any other 409."""
    try:
        asked = json.loads(answer).get("confirm")
    except (ValueError, AttributeError):
        return None
    return asked if isinstance(asked, str) else None


call("POST", "/api/login", {"username": os.environ["BTCTX_USER"], "password": os.environ["BTCTX_PASSWORD"]})
if call("GET", "/api/transactions"):
    sys.exit("The ledger is not empty: load the golden ledger only into an empty test install.")
call("PUT", "/api/settings/tax-timezone", {"timezone": "America/New_York", "chosen": True})
for tx in LEDGER:
    call("POST", "/api/transactions", tx)
print(len(call("GET", "/api/transactions")), "transactions loaded; tax timezone America/New_York")
```

---

## Track A: fresh install of the release candidate

Start from the `clean` snapshot.

### INS: install

- **INS-1** Sideload `btctx_x86_64.s9pk` (StartOS > Sideload; StartOS 0.4.1
  and later ask "Install untrusted software?": **Install anyway**). Expect: it
  installs, and the service page shows version `X.Y.Z`.
- **INS-2** Expect two critical tasks: **Set Login Credentials** and
  **Price Source & Privacy** ("Choose who BitcoinTX asks for newer Bitcoin
  prices, or nobody"). The service can't be started until both have run.
- **INS-3** Run **Set Login Credentials** (the service is still stopped).
  Expect: no warning (there is no login to replace yet), then title "Login
  Credentials", username `admin`, a 24-character password, and a message
  that it is shown only now. The critical task clears. Record the password.
- **INS-4** Run **Price Source & Privacy**. Choose **Decide in BitcoinTX
  instead** and leave both toggles off. Expect: "Price
  Source Saved"; the task clears.
- **INS-5** Start the service. Expect: the health check **Web Interface**
  reads "BitcoinTX is ready" within a minute. The service log has no
  `ERROR` or `Traceback`. From 1.2.9 (#202), BitcoinTX isn't root: `start-cli
  package attach btctx -n btctx -- sh -c 'find /data \! -user btctx -o \! -group btctx; awk
  "\$2 ~ /:0050\$/ && \$4 == \"0A\" {print \$8}" /proc/net/tcp'` prints only
  `10001` (no file that isn't btctx's; port 80's listener is uid 10001).
- **INS-6** Interfaces. Expect: **Web UI** and **MCP API**, where MCP
  API's address is the Web UI's address plus `/api`.
- **INS-7** `curl --cacert ca.crt $API/health`. Expect: HTTP 200 and JSON
  with exactly `status` (`ok`), `version` (`X.Y.Z`) and `schema`. No other
  fields.

### AUTH: login and account

- **AUTH-1** Open the Web UI. Expect: "Welcome to BitcoinTX" and "Sign in",
  with no **Setup Code** field (StartOS never keeps the default login). The
  **Show password** toggle reveals the typed password.
- **AUTH-2** Log in with the wrong password, then with `admin` /
  `password`. Expect both times: "Invalid username or password."
- **AUTH-3** Log in with the INS-3 credentials. Expect: the Dashboard.
  Settings, open **Account**: Tax Timezone reads "Current:
  America/New_York": a login adopts the browser's timezone while the
  ledger is empty (#334).
- **AUTH-4** Expect the card "Bitcoin prices" on the Dashboard only (not on
  other pages), nothing chosen, its status line "Not chosen yet: nothing is
  contacted." Choose **Nobody**, then **Use this**. Expect: no page reload,
  the card is gone. Settings, open **Privacy & Network**: the card with
  **Nobody** chosen, editable, "Fully offline: nothing is contacted.",
  "You chose this on … in the first-run question.", and no "Set in
  StartOS" banner.
- **AUTH-4b** Settings, open **About BitcoinTX**. Expect, in order: the
  warning in bold "Important: add each wallet and exchange." and its
  notice, word for word: "Add each wallet, exchange and bank you use in
  Settings, under Wallets, exchanges and banks. From 2025, cost basis is
  figured wallet by wallet and account by account; unless you identify the
  coins you sell, first in, first out within each, by the date first
  acquired (Treas. Reg. §1.1012-1(j)). Cost basis is per-wallet FIFO: each
  wallet and exchange uses its own oldest coins first for a sale, spend or
  transfer, unless you choose other coins in one of your own wallets. If
  you kept multiple wallets or exchanges together in BitcoinTX 1.x, years
  before you added them were figured together: ask a tax professional
  whether an earlier return needs a change."; the
  disclaimer "BitcoinTX is software, not tax, legal or financial advice.
  …"; "Version X.Y.Z" (the release candidate's, as in INS-7); and the
  links **release notes**, **Report a problem**, **open bugs** and
  **Report it privately**. 1.x's one-wallet warning is gone.
- **AUTH-5** Header **Logout**. Expect: the confirm "Are you sure you want
  to log out?", then the login page. Opening `$URL/dashboard` redirects to
  login. Log back in.

### GLD: the golden ledger through the UI (price source Nobody)

- **GLD-1** Enter the 14 golden transactions, confirming the past-year
  dialog as above. Expect: each toast as in the table.
- **GLD-2** Transactions list. Expect: 14 rows, grouped by day, newest
  first under **Sort by date**. **Last added** puts #14 first. Items per page
  `10` gives "Page 1 of 2", and **Next »** / **« Prev** move between the
  pages. The group **Dec 31, 2023** holds #6 as "Withdrawal · Wallet",
  "11:30 PM · Spent", "Gain +$170.00 · +73.91% · Short-term".
- **GLD-3** Dashboard. Expect: the Portfolio, Realized and Income & Fees
  figures above. Current Bitcoin Price reads "Offline", with "You chose
  Nobody: no live price." under it; Unrealized Gains/Losses reads
  "Offline"; the sidebar reads "BTC Price: offline" with **Type a price**.
  Total Fees reads "N/A" (label "Total Fees in USD").
- **GLD-4** Without prices, try to add each of these, all dated 2025-07-01
  12:00. Expect each to be refused, with the transaction count still 14:
  - Deposit to `Wallet`, Amount `0.001`, Source
    `Income`, Cost Basis blank. Expect the error to contain "No BTC price is
    stored for 2025-07-01" and "Enter this Income deposit's USD value at
    receipt as its cost basis."
  - Transfer from `Exchange BTC` to `Wallet`, Amount (From) `0.01`, Amount
    (To) `0.0099`, Fee value (USD) blank. Expect the error to contain "No BTC
    price is stored for 2025-07-01" and "For the network fee".
  - Withdrawal from `Wallet`, `0.001`, `Spent`, Proceeds blank.
    Expect "No BTC price is stored for 2025-07-01".
  - Deposit to `Wallet`, Source `MyBTC`, Cost Basis blank. Expect
    the form to refuse it: "Enter this deposit's cost basis (type 0 if
    unknown)."
  - Sell 5 BTC for `500000`. Expect "Not enough BTC to sell 5.00000000
    BTC".
- **GLD-5** Edit #3 (the 2023-03-01 Buy). Expect: "Edit Transaction", with
  the Transaction Type select disabled. Change Amount USD to `13000` and
  click **Update transaction**. Expect the past-year dialog "Change an
  earlier tax year?": "This changes the figures of tax years 2023 and
  2024, which you may already have filed. Confirm to save it: a copy of
  your ledger is made first.", then, under "Tax year 2023":
  `2023-03-01 12:00 · Buy · 0.50000000 BTC — basis 12000.00 -> 13000.00;
  cost of the lots it made 12000.00 -> 13000.00.` and `2023-09-10 12:00 ·
  Sell · 0.50000000 BTC — basis 11600.00 -> 11800.00; gain 1390.00 ->
  1190.00; taxable gain incl. network fees 1390.00 -> 1190.00.`; under
  "Tax year 2024": `2024-02-02 12:00 · Sell · 0.30000000 BTC — basis
  7200.00 -> 7800.00; gain 7800.00 -> 7200.00; taxable gain incl. network
  fees 7800.00 -> 7200.00.` and `2024-03-02 12:00 · Sell · 0.10000000 BTC
  — basis 2400.00 -> 2600.00; gain 3600.00 -> 3400.00; taxable gain incl.
  network fees 3600.00 -> 3400.00.`; no "Don't ask again" box (an edit);
  **Cancel** focused. Click **Save anyway (a copy is made first)**.
  Expect: #5 now Gain +$1,190.00, #7
  +$7,200.00, #8 +$3,400.00. Change it back to `12000`. Expect: #5
  +$1,390.00, #7 +$7,800.00, #8 +$3,600.00. Every edit recalculates the
  whole ledger.
- **GLD-6** Delete #9 (the income deposit). Expect the confirm "Are you sure
  you want to delete this transaction?", then the past-year dialog: "This
  changes the figures of tax year 2024, …" and one line, `2024-05-01 12:00 ·
  Deposit (Income) · 0.02000000 BTC — Deleted: income 1000.00; basis
  1000.00; cost of the lots it made 1000.00.` (the gift of 2024-06-01 takes
  older coins, so nothing else moves). Click **Delete anyway (a copy is made
  first)**. Expect the toast "Transaction deleted successfully!" and Wallet
  (BTC) 0.37970000 BTC. Re-enter #9, which makes it a backdated entry: the
  dialog says "This changes the figures of tax year 2024, …" with `… —
  Added: income 1000.00; basis 1000.00; cost of the lots it made 1000.00.`
  (none if GLD-1's "Don't ask again for adds to 2024" still holds: the page
  wasn't reloaded since). Expect: every golden figure is back, Wallet
  0.39970000.
- **GLD-6b** Add a Deposit into Exchange BTC, Source **MyBTC**, `0.01` BTC
  on `2025-04-01`, cost basis `500`. Expect under Source "Coins moved here
  from another wallet or exchange you track in BitcoinTX are a Transfer,
  not a Deposit: a deposit would count them in both accounts." (#705), and
  a **Date originally acquired** field (it isn't there for Income or for a
  Bank deposit); enter
  `2023-03-14` and save. Edit it: the field shows 03/14/2023 (the date
  entered, #185), and saving the edit unchanged keeps it. Ledger Review shows "Nothing to review." and no
  "Reminder: My BTC and Gift deposits counted from their deposit date". Delete it. Expect:
  every golden figure as before.
- **GLD-6c** A rebate (bitcoin back for spending). Open **Add
  transaction**, Deposit, and pick Account `Wallet`: expect the hint "A
  wallet is one set of keys: add each one you use in Settings → Wallets,
  exchanges and banks." under it, and under Source (still N/A) the line
  "Coins moved here from another wallet or exchange you track in
  BitcoinTX are a Transfer, …". Switch to Account `Exchange BTC`
  (Currency shows `BTC`; the wallet hint goes), Source **Rebate** (the
  Transfer line goes too), `0.0001` BTC on
  `2025-04-01`, cost basis `6`, and save. Expect: Exchange (BTC)
  0.15010000 BTC, and in Income & Fees
  Rebates (received) $6.00 (0.00010000 BTC) with Total Income unchanged
  ($1,000.00): a rebate isn't income. Complete Tax
  Report 2025, section 3: the deposit is under "Rebates (not income)", not
  under Income. Edit it, Source **Reward**: the cost basis stays `6`, and
  Rewards (earned) reads $6.00 (0.00010000 BTC), Total Income $1,006.00,
  Rebates (received) $0.00. Change it back to **Rebate** (Total Income
  $1,000.00), then delete it.
  Expect: every golden figure as before.
- **GLD-7** Open **Add transaction**, type an Amount, then click outside the
  panel. Expect: "Discard changes?". **Go back** keeps the panel; **Discard
  changes** closes it with nothing saved.

### RPT: reports (price source Nobody)

- **RPT-1** Reports. Expect the **Tax year** list to hold the ledger's
  years (2023–2025) and the current year. Select **IRS Reports**: 2023
  shows "2023 (no IRS forms yet)" and can't be chosen.
- **RPT-2** IRS Reports, 2024, **Export**. Expect: the file
  `IRSReports(Form8949,ScheduleD,etc.)_2024.pdf`, 4 pages, flattened (no
  editable fields). The Form 8949 and Schedule D figures match the
  expected-figures table. Box C is ticked on the Part I page and box F on
  Part II. Column (f) is blank.
- **RPT-3** The same for 2025. Expect: box H ticked on Part I and box L
  on Part II, with the 2025 rows and lines above.
- **RPT-3b** The draft preview (until January 1 after the preview's year;
  in 2026: the 2026 draft). With **IRS Reports** selected, the year shows as
  "2026 – IRS draft (preview, not for filing)" and choosing it shows the
  warning not to file it. **Export**: every page of the PDF says "DRAFT — DO
  NOT FILE" and none is the IRS's cover note ("the draft you are looking for
  begins on the next page"). From January 1 after its year, the year shows
  "(no IRS forms yet)" and the note says to update BitcoinTX.
- **RPT-4** Transaction History for 2023, 2024 and 2025. Expect the files
  `TransactionHistory_<year>.csv` with 6, 4 and 4 data rows.
  Then Transaction History 2023 with Format **PDF**: expect
  `TransactionHistory_2023.pdf`, landscape, the same 6 transactions, and
  "Page 1 of N" at the foot of each page.
- **RPT-5** Complete Tax Report 2023 and 2024, with Nobody and no stored
  prices. Expect: both generate. Every holdings value (Beginning of Year
  and End of Year) reads "not priced", with the note "No BTC price for
  when YYYY ended: not priced" (and for 2024 "No BTC price is stored for
  2024-01-01, so the holdings aren't valued …"). Never $0.00. Every other
  figure is as in the expected-figures table. Section 7, "Notes", says how
  a blank value is priced (Bitstamp's hourly opening price, or your
  Mempool server's) and that the IRS approves no price source, and ends
  with "Values from the BTC price": "None of YYYY's values: each was
  entered with its transaction" (every golden value is typed). Each report has section 6,
  "Using these forms" (before 7, "Notes"), for the preparer; under "Before
  filing", the bullet "From 2025, cost basis is figured wallet by wallet
  and account by account; unless you identify the coins you sell, first
  in, first out within each, by the date first acquired (Treas. Reg.
  §1.1012-1(j)). BitcoinTX uses per-wallet FIFO. BitcoinTX records no Rev.
  Proc. 2024-28 allocation." (1.x's one-wallet bullet is gone; in a year
  with chosen coins it adds those), and the disclaimer; in 7, "Notes",
  "Cost basis is per-wallet FIFO: each wallet and exchange uses its own
  oldest coins first for a sale, spend or transfer, unless you choose other
  coins in one of your own wallets. An exchange's own order of coins can
  give other figures." Section 2 of each report
  ends with "Sales by exchange", as in the expected-figures table (2025's
  report too). RPT-6 checks the values once prices are on.

### TZ: tax timezone

- **TZ-1** Settings, open **Account**, Tax Timezone: select `Asia/Tokyo`,
  then **Save**.
  Expect the past-year dialog first (#353): "Change an earlier tax year?",
  its words naming the tax years from 2023 on, and #6 among the changes
  with "tax year 2023 -> 2024". **Cancel**: Current still reads
  America/New_York and no figure moves. **Save** again and **Save anyway (a copy is made first)**.
  Expect the toast "Tax timezone set to Asia/Tokyo. Gains were
  recalculated." and one more `btctx-pre-change-past-year-….db` in
  `backups`. In Tokyo, #6 falls on Jan 1, 2024 and every other date
  moves one day later. Expect:
  - IRS Reports 2024, Schedule D line 3: 15400.00 / 7430.00 / 7970.00.
    Box C has two rows: `0.01000000 BTC · 02/02/2023 · 01/01/2024 · 400.00 ·
    230.00 · 170.00` and `0.30000000 BTC · 03/02/2023 · 02/03/2024 ·
    15000.00 · 7200.00 · 7800.00`.
  - Line 10 unchanged: 6000.00 / 2400.00 / 3600.00, dated 03/02/2023 →
    03/03/2024.
  - 2025 lines unchanged, dates one day later (for example 01/11/2025 →
    04/02/2025).
  - Dashboard Total Net Capital Gains still +$19,433.10.
- **TZ-2** Set it back to `America/New_York` (the dialog asks again: **Save
  anyway**). Expect: every golden figure is back.
- **TZ-2b** A date stays the date entered (#185). Add a Deposit into
  Exchange BTC, Source **MyBTC**, `0.01` BTC on `2025-04-01`, cost basis
  `500`, **Date originally acquired** `2023-03-14`. Set the tax timezone
  to `Pacific/Kiritimati` (**Save anyway** in the dialog), then edit the
  deposit: the field still shows 03/14/2023; save it unchanged. Set the
  tax timezone back to `America/New_York` (**Save anyway**) and edit it
  again: still 03/14/2023. Delete it.
  Expect: every golden figure as before.

### REV: Ledger Review and Recalculate

- **REV-1** Settings, open **Ledger Review**, **Check again**. Expect:
  "Nothing to review." (no prices stored yet).
- **REV-2** Settings, open **Account**, Recalculate Ledger's
  **Recalculate**. Expect: "Recalculated 14 transaction(s)." and figures
  unchanged.
- **REV-3** StartOS action **Recalculate Ledger**, once with the service
  running and once stopped. Expect its warning, then "Ledger Recalculated",
  and figures unchanged afterwards. Start the service again.
- **REV-4** (#255, still Nobody) Add a Withdrawal from Wallet, purpose
  **Gift**, `0.001` BTC, yesterday 12:00, FMV (USD) left blank. Expect: it
  saves, and **Edit** shows FMV blank, no Refresh button beside it, and
  "Its fair market value when it left. Leave blank to use the BTC price
  when that hour began (that day's, where there's no hourly price). Unless
  BitcoinTX already has that hour's price, type it: you chose Nobody."
  (#208: where a blank value's price comes from.) Settings, open **Ledger
  Review**, **Check again**: it lists it
  under "Gifts, donations and lost coins with a $0 or blank value" ("Value
  blank: the tax report lists it as not given (no price stored for that
  day)."). Delete the gift; Check again: "Nothing to review."

### ACC: wallets, exchanges and banks (2.0; price source Nobody)

From 2.0 the owner adds each wallet, exchange and bank in Settings. What
ACC adds stays for the rest of Track A: a second wallet, `Coldcard`, and a
second exchange, `Kraken` (its accounts `Kraken USD` and `Kraken BTC`), both
unused, so every golden figure stays as it is. A row in **Wallets,
exchanges and banks** reads its name, its kind and its balance.

- **ACC-1** Settings. Expect the nine sections in the order of
  "Settings, one section at a time" above, all closed but **Ledger Review**,
  which REV-4 left open (Settings remembers the section last open in this
  browser); close it. Expect the summary under **Wallets, exchanges and
  banks** to read "1 wallet · 1 exchange · 1 bank". Open it.
  Expect three groups, Wallets, Exchanges and Banks, each with its button
  (**Add a wallet**, **Add an exchange**, **Add a bank**) and one row:
  `Wallet` Wallet 0.39970000 BTC, `Exchange` Exchange $37,990.00 ·
  0.15000000 BTC, `Bank` Bank $45,000.00; no BTC Fees or USD Fees. Open
  **Ledger Review**: Wallets, exchanges and banks closes. Reload: Ledger
  Review is still the open one. Open Wallets, exchanges and banks again.
- **ACC-2** Open Wallet's row. Expect a **Name** field holding `Wallet`,
  **Rename** off (nothing to send), and under it "A CSV file names each
  account as it was named when the file was saved, and an import matches
  those names to your accounts as they're named then: a file saved before
  this rename names this account by its old name. In a file, 'Wallet'
  still means this account."; **Hide**, no **Delete**, and "This account
  has transactions, so it can't be deleted. Hide it instead: its history
  stays."; no 1099-DA box (a wallet). Rename it `Phone wallet`. Expect the
  row `Phone wallet`, #6 on Transactions as "Withdrawal · Phone wallet",
  and the dashboard's Wallet (BTC) still 0.39970000 BTC. Rename it back to
  `Wallet`. Then rename Bank to `Wallet`: refused with "'Wallet' always
  means your first wallet in files (CSV, River, BitcoinTX 1.x): choose
  another name.", and Bank keeps its name.
- **ACC-3** **Add a wallet**. Expect a **Name** field with the help text
  "A wallet is one set of keys: every address it makes is part of it. A
  backup of the same keys (a seed phrase, or another device with the same
  keys) isn't a second wallet. If you use multiple wallets, add each one:
  since 2025 the IRS figures cost basis wallet by wallet." and, since
  Wallet has transactions, the note "Years before you add this wallet were
  figured with your wallets together, as BitcoinTX 1.x did. Move coins
  into it with a Transfer dated when they really moved. Cost basis is
  per-wallet FIFO: each wallet and exchange uses its own oldest coins
  first for a sale, spend or transfer, unless you choose other coins in
  one of your own wallets. A Transfer dated in an earlier year can change
  that year's figures and later ones (BitcoinTX shows which years before
  it saves), and BitcoinTX doesn't allocate your cost basis to each wallet
  as of January 1, 2025 (Rev. Proc. 2024-28), nor record an allocation you
  made: its figures from 2025 on follow its own history. A tax
  professional can compare that with yours (your 2024 Complete Tax Report
  lists each account's lots at the end of 2024) and tell you whether an
  earlier return needs a change." Name `wallet`, **Add**: refused with
  "'wallet' always means your first wallet in files (CSV, River,
  BitcoinTX 1.x): choose another name." Name `Coldcard`, **Add**. Expect
  the form closed, the row `Coldcard` Wallet 0.00000000 BTC (opened: a
  **Delete** button and "It has no transactions."), and the summary "2
  wallets · 1 exchange · 1 bank".
- **ACC-4** **Add an exchange**. Expect the help text "BitcoinTX keeps an
  exchange's dollars and bitcoin as two accounts, 'name USD' and 'name
  BTC'.", the question "Does this exchange send you a Form 1099-DA?" with
  **Yes** chosen and **No** beside it, under them "An exchange in the US
  sends one for your sales from 2025; one outside the US usually doesn't.
  It decides the Form 8949 box, not the gain." (#708), and the note of
  ACC-3 for an exchange (it begins "Years before you add this exchange
  were figured with your exchange accounts together"). Leave **Yes**.
  Type `Kraken`: the help text reads "… two accounts, 'Kraken USD' and
  'Kraken BTC'." **Add**. Expect the row `Kraken` Exchange $0.00 ·
  0.00000000 BTC and the summary "2 wallets · 2 exchanges · 1 bank".
  **Add an exchange** `kraken` again: refused with "An exchange named
  'kraken' already exists."; **Cancel**. Open Kraken's row: **This
  exchange sends me a Form 1099-DA** ticked (on by default), with "An
  exchange in the US sends one for your sales from 2025; one outside the
  US usually doesn't. It decides the Form 8949 box, not the gain."
  Exchange's row has the same box, ticked; Wallet's, Coldcard's and Bank's
  have none.
- **ACC-5** **Add a bank** `Credit union`. Expect no help text and no
  note, then the row `Credit union` Bank $0.00. Open it, **Hide**. Expect
  the row gone from the list, **Show hidden (1)** under Banks, and the
  summary "2 wallets · 2 exchanges · 1 bank · 1 hidden". In **Add
  transaction**, a Deposit's Account doesn't offer `Credit union`; close
  the panel. Back in Settings, **Show hidden (1)**: the row `Credit union`
  Bank Hidden $0.00, its details saying "Hidden: left out of the lists you
  pick an account from. It has no transactions."; **Show**: back in the
  list, and no **Show hidden** left. Open it, **Delete**: BitcoinTX's own
  dialog (#651), "Delete Credit union? This deletes the bank Credit union.
  Only an account with no transactions can be deleted, and it has none. An
  account with transactions can be hidden instead: its history stays.";
  **Delete Credit union**. Expect the row gone and the summary "2 wallets ·
  2 exchanges · 1 bank".
- **ACC-6** Dashboard. Expect Portfolio Overview's Wallet (BTC) 0.39970000
  BTC with a caret after its label, Settings' chevron: pressed (anywhere
  on the line), the caret turns over as a Settings section's does, and the
  line lists `Wallet` 0.39970000 BTC and `Coldcard` 0.00000000 BTC under
  it, `Wallet` with "Cost basis" under its amount and, with a price,
  "Unrealized" and its gain (#709); `Coldcard`, holding none, with no cost.
  Exchange (USD) $37,990.00 with a caret, listing `Exchange` $37,990.00 and
  `Kraken` $0.00, with no cost; Exchange (BTC) 0.15000000 BTC with a caret,
  listing `Exchange` 0.15000000 BTC with its cost basis and `Kraken`
  0.00000000 BTC. `Wallet`'s and `Exchange`'s costs add up to $24,733.10,
  Avg. Cost per BTC × Total BTC to the cent, and their gains add up to
  Unrealized Gains/Losses exactly (#770).
  Bank (USD) $45,000.00, with no caret. Reload: the open lines stay open.
  Every golden figure.
- **ACC-7** **Add transaction**, Transfer, From Account `Exchange BTC`.
  Expect To Account blank, offering under "Wallets" `Wallet` and
  `Coldcard`, and under "Exchanges" `Kraken BTC` and `Exchange: consolidate
  within the same exchange`. Choose the last. Expect under it "Only the
  network fee is recorded: it's a disposal of your oldest coins at the
  fee's value (Form 8949, box I or L; C or F before 2025). Your coins, their
  dates and cost basis stay as they are." and "Moving coins to another
  exchange? Choose that exchange's BTC account as To Account. Not listed?
  Add the exchange, or show it if it's hidden, in Settings → Wallets,
  exchanges and banks." Choose From Account `Wallet`: To Account is blank again, and
  among its choices is `Wallet: consolidate within the same wallet`.
  Choose it. Expect under it, after the fee's line, "Moving coins to
  another of your wallets? Choose that wallet as To Account. Not listed?
  Add it, or show it if it's hidden, in Settings → Wallets, exchanges and
  banks."
  Close the panel with **Discard changes**.

### CHO: choosing which coins leave a wallet (2.0; price source Nobody)

A spend dated today, so no past-year dialog asks; deleted at the end, so
every golden figure is back.

- **CHO-1** **Add transaction**, Withdrawal, From Account `Wallet`,
  purpose Spent, dated today, Amount `0.001` BTC, network fee `0.00001`
  BTC with its value `1`, proceeds `100`. Expect the coins that will leave
  listed, oldest first. Choose **Choose which coins leave**: a line for
  each purchase or deposit Wallet holds, filled oldest first, with
  **Oldest first** and **Highest cost first** offered (the spend is dated
  today), and "Choose coins only if you decided which coins to send by the
  time they left, and your records from then show which purchases they
  were (…). Otherwise the IRS counts the oldest coins as the ones that left
  (Treas. Reg. §1.1012-1(j)). …". Empty the oldest line and type `0.00101`
  on the newest one's, the 05/01/2024 Income deposit (0.02 BTC): the
  running total adds up, and Save is enabled. Save, and open the spend
  again: "Chosen on <today>.".
- **CHO-2** Reports, Complete Tax Report for this year. Expect the cover's
  Cost basis method "Per-wallet FIFO, with the coins you chose in your
  wallets", and at the end of section 2 "Coins you chose": the spend,
  Wallet, "Spent, 0.00101000 BTC", Chosen on today's date (no star), and
  05/01/2024 with 0.00101000 BTC and its cost, $50.50.
  Ledger Review lists no "Reminder: coins chosen after they left" for it
  (chosen the same day). Delete the spend; the Dashboard is as before.

### MLT: a second exchange (2.0; price source Nobody)

A Buy and a Sell at Kraken in 2025, each through the past-year dialog, an
edit of each that keeps Kraken's accounts, and Kraken's 1099-DA switch,
which moves its sale from box H to box I; then both are deleted, so every
golden figure is back. Reload the page first, so the dialog asks for every
add (GLD-1's "Don't ask again" lasts only while the page is open).

- **MLT-1** Add a Buy dated 2025-02-01 12:00. Expect an **Exchange** field
  (with one exchange there is none), blank, offering `Exchange` and
  `Kraken`, and **Paid from** reading "Choose the exchange first". Choose
  `Kraken`: **Paid from** offers `Kraken USD` and `Bank`, blank.
  Choose `Bank`, Amount USD `6000`, Amount BTC `0.1`, and save.
  Expect the dialog "This changes the figures of tax year 2025, which you
  may already have filed. Confirm to save it: a copy of your ledger is made
  first." with one line, `2025-02-01 12:00 · Buy · 0.10000000 BTC — Added:
  basis 6000.00; cost of the lots it made 6000.00.` (2025 has later rows,
  so it isn't "This adds"). **Save anyway**: the toast "Transaction
  created successfully!".
- **MLT-2** Add a Sell dated 2025-03-01 12:00. Expect its **Exchange**
  blank, offering `Exchange` and `Kraken`. Choose `Kraken`, Amount BTC
  `0.05`, Gross Proceeds (USD) `4500`, and save. Expect the dialog's line
  `2025-03-01 12:00 · Sell · 0.05000000 BTC — Added: proceeds 4500.00;
  basis 3000.00; gain 1500.00; taxable gain incl. network fees 1500.00.`:
  half of Kraken's own lot, never the Exchange's coins. **Save anyway**:
  the toast "Transaction created! Realized Gain: +$1,500.00". On
  Transactions the two rows read "Buy · Kraken" and "Sell · Kraken";
  **Filter transactions** `Kraken` (under Exchanges) keeps those two, with
  "2 of 16 transactions"; **All accounts** shows the 16.
- **MLT-3** Edit the Sell. Expect its **Exchange** reading `Kraken`, not
  `Exchange`. Gross Proceeds `4600`, **Update transaction**: the dialog's
  line `2025-03-01 12:00 · Sell · 0.05000000 BTC — proceeds 4500.00 ->
  4600.00; gain 1500.00 -> 1600.00; taxable gain incl. network fees 1500.00
  -> 1600.00.`; **Save anyway**. Edit the Buy. Expect **Exchange**
  `Kraken` and **Paid from** `Bank`. Amount USD `6200`,
  **Update transaction**: two lines, `2025-02-01 12:00 · Buy · 0.10000000
  BTC — basis 6000.00 -> 6200.00; cost of the lots it made 6000.00 ->
  6200.00.` and `2025-03-01 12:00 · Sell · 0.05000000 BTC — basis 3000.00
  -> 3100.00; gain 1600.00 -> 1500.00; taxable gain incl. network fees
  1600.00 -> 1500.00.`; **Save anyway**. Expect the Sell at Gain
  +$1,500.00, and **Filter transactions** `Kraken` still showing both (the
  edits kept Kraken's accounts). Dashboard: Bank (USD) $38,800.00;
  Exchange (USD) $42,590.00, listing `Exchange` $37,990.00 and `Kraken`
  $4,600.00; Exchange (BTC) 0.20000000 BTC, listing `Exchange` 0.15000000
  BTC and `Kraken` 0.05000000 BTC; Total BTC
  0.59970000 BTC; Avg. Cost per BTC $46,411.71; Short-Term Gains
  +$10,865.40, Net Short-Term +$9,865.40, Total Net Capital Gains
  +$20,933.10. Settings: Kraken's row $4,600.00 · 0.05000000 BTC, with no
  **Delete**.
- **MLT-4** Settings, open **Wallets, exchanges and banks**, then Kraken's
  row: untick **This exchange sends me a Form 1099-DA**. Expect the dialog
  "This changes the figures of tax year 2025, …" with one line,
  `2025-03-01 12:00 · Sell · 0.05000000 BTC — Form 8949 box H -> I.`, and
  the box still ticked behind it. **Cancel**: still ticked. Untick it
  again, **Save anyway**: unticked. No gain moves (the dashboard as in
  MLT-3).
- **MLT-5** The boxes. IRS Reports 2025, **Export**. Expect 5 pages: box
  H's Part I (#12's row, as in the expected-figures table), box L's Part
  II (its three rows), box I's Part I, ticked, with `0.05000000 BTC ·
  02/01/2025 · 03/01/2025 · 4600.00 · 3100.00 · 1500.00`, then Schedule D:
  line 2 4000.00 / 5000.00 / (1000.00), line 3 4600.00 / 3100.00 /
  1500.00, line 10 10000.00 / 2532.30 / 7467.70. Complete Tax Report 2025:
  section 1's capital gains, Short-term 2 disposals, $8,600.00 / $8,100.00,
  net $500.00, and Total 5, $18,600.00 / $10,632.30, net $7,967.70;
  section 2's first row `03/01/2025 · 02/01/2025 · Sale / Kraken BTC · I ·
  Short · 0.05000000 · $4,600.00 · $3,100.00 · $1,500.00`; "Sales by
  exchange" `Exchange · Yes · H · 1 · $4,000.00 · $5,000.00 ·
  ($1,000.00)` and `Kraken · No · I · 1 · $4,600.00 · $3,100.00 ·
  $1,500.00`; section 6, "This year's boxes: H, I and L", "Schedule D:
  lines 2, 3 and 10", and the Bitcoin-only figures line 7 $500.00, line
  15 $7,467.70, line 16 $7,967.70.
- **MLT-6** Delete the Kraken Sell, then the Buy: each the confirm, then
  the dialog with **Delete anyway (a copy is made first)** and its line,
  `2025-03-01 12:00 · Sell · 0.05000000 BTC — Deleted: proceeds 4600.00;
  basis 3100.00; gain 1500.00; taxable gain incl. network fees 1500.00.`,
  then `2025-02-01 12:00 · Buy · 0.10000000 BTC — Deleted: basis 6200.00;
  cost of the lots it made 6200.00.` Tick Kraken's 1099-DA box again:
  saved at once, with no dialog (Kraken has no sale left). Expect 14 rows,
  every golden figure, and Kraken's row $0.00 · 0.00000000 BTC with
  **Delete** offered again. Keep Kraken: AI-15, IMP-4b to IMP-6 and END-2 use it.

### PYW: the past-year dialog's own rules (2.0; price source Nobody)

GLD, TZ and MLT meet the dialog; this checks what it keeps and when it
doesn't ask. With the AI key, AI-10 checks the same warning (`saved:
false`, then `confirm`). The newest copy in `backups`: `start-cli package
attach btctx -n btctx -- sh -c 'ls -t /data/backups | head -1'`.

- **PYW-1** Reload the page. Add a Deposit to `Wallet`, Source `MyBTC`,
  `0.01` BTC on 2025-07-01 12:00, Cost Basis (USD) `500`, and save. Expect
  the dialog "This adds to tax year 2025, which you may already have
  filed. Confirm to save it: a copy of your ledger is made first."
  (nothing is dated after it), one line, `2025-07-01 12:00 · Deposit
  (MyBTC) · 0.01000000 BTC — Added: basis 500.00; cost of the lots it made
  500.00.`, the box "Don't ask again for adds to 2025 while this page is
  open" unticked, and **Cancel** focused. Note the newest copy. **Cancel**:
  the form stays open, nothing is saved (14 rows), and the newest copy is
  the same. Save again, tick the box, **Save anyway (a copy is made
  first)**: saved, and the newest copy is a new
  `btctx-pre-change-past-year-<UTC time>.db`.
- **PYW-2** Add the same deposit dated 2025-07-02 12:00. Expect no
  dialog: it saves at once (the page confirmed it, as ticked), with a
  newer copy. Edit the first, Cost Basis `600`. Expect the dialog all the
  same (an edit always asks): "This changes the figures of tax year 2025,
  …", `2025-07-01 12:00 · Deposit (MyBTC) · 0.01000000 BTC — basis 500.00
  -> 600.00; cost of the lots it made 500.00 -> 600.00.`, and no "Don't
  ask again" box. **Save anyway**. Delete each: the confirm, then the
  dialog, with **Delete anyway (a copy is made first)** (the first's line
  ends "— Deleted: basis 600.00; cost of the lots it made 600.00.").
  Reload, and add the 2025-07-01 deposit again: the dialog asks (the tick
  lasted while the page was open). **Cancel**, and discard the form.
- **PYW-3** What never asks. A Deposit of `1` into `Bank` dated 2025-07-01
  12:00 saves with no dialog (dollars move no tax figure), and so does a
  Deposit to `Wallet`, `MyBTC`, `0.01` BTC dated today 12:00, Cost Basis
  `500` (this tax year); neither makes a copy. Delete both: no dialog.
  Expect 14 rows and every golden figure.

### PRC: price sources

- **PRC-1** While Nobody: the service log has no lines starting "BTC price
  history from" or "Price history from your mempool server".
- **PRC-2** Action **Price Source & Privacy**: choose **Public price
  sites**, with Tor off. Expect: "Price Source Saved" and a service restart.
  Then:
  - Settings, open **Privacy & Network**: it reads "Set in StartOS. To change
    it: BitcoinTX › Actions › Price Source & Privacy.", with **Public price
    sites** marked "✓ Chosen" (not "Recommended"), no choices to click and no
    Save button. Its status line reads "Newer prices from public price sites.
    Last price …" once the Dashboard has shown a price.
  - Dashboard: a price above $0 and "Block Height: N" with N > 900,000.
    Unrealized Gains/Losses and Total Fees (approx) match the formulas in
    the expected-figures table.
  - The service log has a line "BTC price history from public site …: N
    days".
  - The hourly price history downloads in the background after the choice
    above (about a minute). Logged in, ask
    `GET $API/bitcoin/price/history?at=2025-07-01T16:00:00Z` (12:00 New
    York, GLD-4's time) every 30 seconds until it answers `"moment":
    "hour"`; it's within a few percent of the Sats Converter's **Date** mode
    price for 2025-07-01. If after five minutes it still says `"day"` and
    the service log has "Hourly BTC prices for 2025 from Bitstamp aren't
    used", that's by design (Bitstamp's data no longer gives the shipped
    fingerprint): use the `"day"` answer below, and note it.
  - Then repeat the first GLD-4 deposit (Income, blank basis). Expect:
    saved with Cost Basis = 0.001 × that price and `price_moment` equal to
    the answer's `moment`. Delete it.
  - The Complete Tax Report now values the holdings (RPT-6).
  - Settings, open **Ledger Review**, **Check again**. Expect exactly one
    item: "Income and rebate values you typed, far from that hour's price:
    1", which is #9.
    Its $1,000.00 is made up, so this is correct. Every golden value is
    typed, so "Values priced at the day's price that the hour would
    change" is absent. Any other item is a FAIL.
- **PRC-2b** (#255, right after PRC-2) Add the REV-4 gift again (FMV
  blank). Expect: **Edit** shows its FMV filled, 0.001 × the BTC price when
  that hour began (to the cent), and "From the price: …" naming that hour
  and the price site. Change the amount to `0.002` and save: the FMV
  doubles (± a cent). Type `50` in FMV and save: Edit shows "Typed: you
  typed this value; it's kept as it is." Delete the gift.
- **PRC-2c** (#260, right after PRC-2b) Settings, open **Account**, Tax
  Timezone: `Asia/Tokyo`, **Save**, and **Save anyway** in the past-year
  dialog. Expect: the Dashboard's price line ("From public price sites (…)
  · h:mm am/pm") and **Privacy & Network**'s "Last price h:mm am/pm" show
  New York time (the browser's timezone), not Tokyo's; the Transactions list's
  times don't move. **Ledger Review**'s **Check again** reads "Dates in
  Asia/Tokyo.": its dates stay in the tax timezone. Set it back to
  `America/New_York` (**Save anyway**; every golden figure back, as in TZ-2).
- **RPT-6** Complete Tax Report 2023 and 2024. Expect the values in the
  expected-figures table.
- **WID-1** The sidebar widgets. Sats Converter **Auto** shows the
  dashboard's price, and under it where it came from and when, in short
  ("Kraken · 2:04 pm"; pointing at it shows the Dashboard's words).
  **Manual** with `50000`: USD `100` gives BTC `0.002` and Sats `200000`.
  Calculator: `7 * 6 =` shows `42`, and **C** clears it.
- **PRC-3** (needs Tor on the VM) Action: **Public price sites** plus
  **Use Tor**. Expect: a price on the Dashboard, and under the sidebar's
  Auto price "Kraken, through Tor · …" (or Bitstamp).
  Through Tor, Bitstamp refuses BitcoinTX's requests (#241). Check it still
  does, with Tor on your machine (the VM's Tor isn't reachable from it;
  Bitstamp sees a Tor exit either way): `curl -s -o /dev/null -w '%{http_code}'
  --socks5-hostname 127.0.0.1:9050
  'https://www.bitstamp.net/api/v2/ohlc/btcusd/?step=86400&limit=2'` gives
  403 (or a 302 to a "Loading" page). If it gives 200 with JSON, Bitstamp
  no longer refuses Tor: note it (PRC-3b's question then never comes).
  Stop Tor, wait a minute (the live price is cached for 60 seconds) and
  reload. Expect the Dashboard price to read "No answer": requests must fail
  rather than go out directly. The sidebar reads "BTC Price: no answer" with
  "Is Tor running?" and **Type a price** (#208). Start Tor: the price is back.
- **PRC-3b** (needs Tor on the VM; right after PRC-3, Tor running) The
  hourly price history through Tor, and the one-time download without Tor
  the owner agrees to (#241).
  - With the service running, remove the hourly files: `start-cli package
    attach btctx -n btctx -- rm -rf /data/btc-prices` (they're downloaded
    again). Restart the service, with **Public price sites** and **Use
    Tor** still set.
  - **Refused, and asked:** expect in the service log "Hourly BTC prices:
    the download from Bitstamp failed: Client error '403 Forbidden' …" (or
    a redirect), and no "checked" line. On the Dashboard, a card "Bitcoin
    price history" asks "Download the price history once without Tor?",
    and Settings' **Privacy & Network** asks the same. Nothing may go out
    directly before an answer: a "checked" line now is a blocker FAIL.
  - **No:** answer **No, keep everything on Tor** on the Dashboard. Expect the
    card to go, and **Privacy & Network** to show "Bitstamp's price history
    without Tor: no, since … (answered on the Dashboard)". Restart the
    service: still no question and no "checked" line.
  - **Yes:** in Settings' **Privacy & Network**, **Download it without Tor**.
    Expect at once "Bitstamp's price history without Tor: yes, since …
    (answered in Settings)", then "Hourly BTC prices: Bitstamp's fixed blocks for the year files go
    without Tor (agreed on …)" and, newest year first, one line per year:
    "Hourly BTC prices for YYYY from Bitstamp: N hours, checked". Each year
    takes a few seconds.
  - **Everything else stays on Tor:** meanwhile the sidebar still reads
    "Kraken, through Tor". Stop Tor, wait a minute and reload: the
    Dashboard price reads "No answer" (the live price never goes direct),
    while the year lines keep coming. Start Tor again.
  - **The newer hours:** add a Buy dated yesterday with its cost basis left
    blank, or `GET $API/bitcoin/price/history?at=<yesterday's 12:00 UTC>`.
    Expect "Hourly BTC prices: Bitstamp's fixed blocks for the hours after
    the year files go without Tor (agreed on …)" and an answer with
    `"moment": "hour"`.
  - When it ends, `/data/btc-prices` holds a `YYYY.csv` for each line of
    `backend/assets/btc_prices/MANIFEST.csv` of the tested commit, except
    a year logged as "aren't used", and no `.partial` file. Each file's
    SHA-256 (`sha256sum` in the service) equals its line's `sha256`, which
    the app already checked: a difference is a blocker FAIL. A line "Hourly
    BTC prices for YYYY from Bitstamp aren't used" means Bitstamp's data no
    longer gives that year's fingerprint: note it (as in PRC-2); it isn't
    the download's fault.
  - Logged in, `GET $API/bitcoin/price/history?at=2020-03-12T14:00:00Z`
    answers `"moment": "hour"`.
  - Put it back for the later tests: in **Privacy & Network**, **Keep it on Tor
    instead**.
- **PRC-4** (needs Mempool) Action: **My Mempool on this server**.
  Expect: a price and block height, the log line "Price history from
  your mempool server: N days", and in Settings' **Privacy & Network** **My
  own Mempool** marked "✓ Chosen" and "Recommended" (#208). Without Mempool installed, StartOS shows
  the dependency as missing and the price error says to install and start
  Mempool.
- **PRC-4b** (needs internet, not Mempool) The app's own-mempool path,
  with a public Mempool instance, since the VM can't run Mempool (it needs
  a synced node). Checked 2026-10-12: BitcoinTX's own code gets the price,
  the block height and 939 days of history from it.
  - Action **Price Source & Privacy**: **Decide in BitcoinTX instead**. Then
    Settings, open **Privacy & Network**: **My own Mempool**, address
    `https://mempool.emzy.de` (mempool.space refuses the lab's address),
    **If it can't answer, ask public price sites** off. Save.
  - Expect: the Dashboard shows a price and a block height. Logged in,
    `GET $API/bitcoin/price/history?at=<an hour after the last_hour of the
    tested commit's MANIFEST.csv, e.g. today's 00:00 UTC>` answers a price
    with `"moment": "hour"`, from the server's recorded hours (`"day"`:
    note it).
  - **Nothing goes to public sites without the fallback:** save the address
    `https://mempool.invalid` (still fallback off). Expect
    `GET $API/bitcoin/price` to answer 502, "Your Mempool didn't answer,
    and the backup (public price sites) is off. …", and the Dashboard's
    price to read "No answer": BitcoinTX asked no public site
    instead. A price shown instead is a blocker FAIL. Then save
    `https://mempool.emzy.de` again.
  - StartOS's **My Mempool on this server** (the internal connection to
    the Mempool service) can't be tested here: the owner checks it on
    their own server during the soak (#143, section 5). The Mac app's own
    check is MAC-7.
  - Then go on to PRC-4c.
- **PRC-4c** (#188, #193) **Trust this server** against a real StartOS
  certificate: the VM's own, from StartOS's own authority (an Ed25519
  leaf), where the release before only had a test server with a private CA.
  Still with **Decide in BitcoinTX instead**: in Settings' **Privacy &
  Network**, **My own Mempool**, address `https://<the VM's LAN IP>` (the
  VM's own StartOS address, by IP: a `.local` name doesn't resolve inside
  the service), fallback off. Save.
  - Expect the status line to say the Mempool's certificate isn't trusted,
    and **Trust this server** to show the server's name, its root
    certificate's name ("… Local Root CA") and a SHA-256 fingerprint,
    with where to check it (#204): the fingerprint must be the one the
    VM's own StartOS shows as Root CA in About this server.
  - Press it. Expect the certificate check to pass: the status line first
    says "Newer prices will come from your Mempool.", then, within a minute
    or two (after the next live-price request), "Your Mempool didn't answer
    at HH:MM." (StartOS's address isn't a Mempool), not the certificate
    message. The certificate message after
    trusting is a FAIL.
  - **Forget this server's certificate**: the certificate message comes
    back.
  - Afterwards, in **Privacy & Network**, clear the address, then choose
    **Nobody** (which hides the address field, and keeps an address left
    in it), and save: PRC-5 expects the app's own choice to be Nobody (from
    AUTH-4) and a blank address.
- **PRC-5** Action: **Decide in BitcoinTX instead**. Expect: Settings'
  **Privacy & Network** is editable again and shows the app's own choice
  (**Nobody**, from AUTH-4). Choose **My own Mempool** and leave the address
  blank. Expect **Save** off, with "Enter your Mempool's address." beside it.
- **PRC-5b** (#145) Still with **Decide in BitcoinTX instead**: in the app choose
  **My own Mempool** (address `https://mempool.emzy.de`), tick **If it
  can't answer, ask public price sites**, and save. PRC-2 already
  downloaded the hourly history, so expect the card's first line "Hourly
  prices, 2013 to …: downloaded and checked." (a year PRC-2 recorded as
  not matching shows "Bitstamp's prices for YYYY didn't match…": record
  which). Choose **Nobody**: the line keeps "downloaded and checked". The
  download's progress line ("Downloading the hourly history from Bitstamp:
  N of M years, each checked.") is seen during PRC-2, right after its
  save: note it there if the card is open.
- **PRC-6** Set the action back to **Public price sites** for the rest of
  Track A.

### AI: AI access and the MCP connector

Set `KEY` to the key from AI-3, and use
`H="Authorization: Bearer $KEY"` in the curl commands.

- **AI-1** Settings, open **Connect an AI Assistant**. Expect: **Let AI
  assistants use BitcoinTX** unticked, a **Create AI key** button, and the
  privacy warning "Your data goes to the AI's model." with its "More" link.
- **AI-2** `curl --cacert ca.crt -H "Authorization: Bearer btctx_ak_bogus" $API/transactions`.
  Expect: 401.
- **AI-3** **Create AI key**. Expect: a key starting `btctx_ak_`, the
  notes "This is the only time BitcoinTX shows this key." and "Then turn on
  AI access above", and a **Copy** button. Reload the page. Expect: the key
  is gone, with **New key** and **Revoke** in its place.
- **AI-4** With AI access still off: `curl --cacert ca.crt -H "$H" $API/transactions`.
  Expect: 401, "AI access is turned off in BitcoinTX Settings."
- **AI-5** Tick **Let AI assistants use BitcoinTX**. Expect the toast "AI
  assistants can use BitcoinTX." The same curl then returns 200 with 14
  transactions.
- **AI-6** The key is refused everywhere else. Each of these returns 403
  with "The AI key can't do this. Log in to BitcoinTX to do it.", and the
  ledger still has 14 rows afterwards:
  `DELETE $API/transactions/delete_all`, `GET $API/backup/csv`,
  `POST $API/backup/download` (form field `password=x`),
  `PUT $API/settings/network` (JSON `{"price_source":"off"}`),
  `GET $API/reports/years`, `POST $API/settings/ai-key`.
  `GET $API/users/` returns 401.
- **AI-7** StartOS action **Connect an AI Assistant**. Expect: "MCP address
  (BTCTX_URL)" = `$API`, a "Root CA certificate" (save it as `ca.crt` if you
  haven't), and a "Claude Desktop configuration" and "Claude Code command"
  that run `uvx btctx-mcp==X.Y.Z` with `YOUR_BITCOINTX_AI_KEY`, under the
  server name `bitcointx` (an alpha's or a beta's: `bitcointx-preview`, with
  `btctx-mcp==2.0.0aN` or `2.0.0bN`, #721). Settings' **Connect an AI
  Assistant**: its Setup prompt contains the same server name, version and
  `$URL` (the connector accepts the address with or without `/api`).
- **AI-8** List the connector's tools with the MCP Inspector CLI. In
  Inspector 2.8.0 the server command comes first, then `--`, then the
  Inspector's own options:

  ```bash
  MCP="uvx --from git+https://github.com/DigiMonk73/BTCTX-MCP@$SHA#subdirectory=mcp_server btctx-mcp"
  mcp() { npx -y @modelcontextprotocol/inspector@2.8.0 --cli $MCP -- \
            -e BTCTX_URL=$API -e BTCTX_AI_KEY=$KEY -e BTCTX_CA_BUNDLE=$PWD/ca.crt "$@"; }
  mcp --method tools/list
  ```

  Expect 12 tools: `get_ledger_guide`, `get_portfolio`,
  `list_transactions`, `get_btc_price`, `review_ledger`,
  `preview_transactions`, `add_transactions`, `update_transaction`,
  `get_coins_moved`, `delete_transaction`, `recalculate_ledger`,
  `backup_ledger`. The calls
  below are `mcp --method tools/call --tool-name <name> --tool-arg key=value`
  (a value may be JSON). Any MCP client works; the Inspector is simply the
  scriptable one.
- **AI-9** `get_portfolio`. Expect: balances equal to the Dashboard, and no
  notice that the connector and app versions differ; from 2.0, `accounts`
  lists the user's seven, each with `id`, `name`, `kind`, `currency`,
  `exchange` and `hidden`: Bank, Wallet, Coldcard, Exchange USD, Exchange
  BTC, Kraken USD and Kraken BTC (`exchange` "Exchange" or "Kraken"), and
  no fee account. `list_transactions`
  returns 14 rows. `review_ledger` returns the same item as Ledger Review
  in PRC-2. `get_ledger_guide` returns the guide text.
- **AI-10** `preview_transactions` with
  `transactions=[{"date":"2025-07-01","type":"Buy","amount":"0.01","from_account":"Bank","to_account":"Exchange BTC","cost_basis_usd":"1000","fee_amount":"0","fee_currency":"USD"}]`.
  Expect: status `ready`, the date normalized to `2025-07-01T16:00:00Z` (a
  date alone means noon in the tax timezone), `past_years` naming 2025 with a
  `confirm` (#353), and the ledger still has 14 rows. Preview a copy of #2
  (`"date":"2023-02-01T12:00:00-05:00"`, Buy, `1.0`, Bank → Exchange BTC,
  basis `23000`). Expect: status `duplicate`, `matched_transaction_id` = #2's
  id. Preview it again with `"not_a_duplicate_of"` set to that id: status
  `ready`. Preview it without that at `2023-02-01T12:05:00-05:00`: status
  `possible_duplicate`, a warning "Same BTC amount as tx #… (Buy 1.00000000
  BTC), recorded 5 minutes earlier: it may be the same transaction. Saved
  unless you remove it." (#253). Preview an income with its value left out
  (`{"date":"2025-07-01T14:30:00Z","type":"Deposit","amount":"0.001","from_account":"External","to_account":"Wallet","source":"Income"}`).
  Expect `simulated.from_price`: `values` `["cost_basis_usd"]`, `at`
  `2025-07-01T14:00:00Z` with `moment` `hour` (or the day's 00:00 with `day`),
  the price's `source` and `usd_per_btc`, which times 0.001 is the filled
  value (#208). Then `add_transactions` with the first row. Expect `saved:
  false`, `detail` "This adds to tax year 2025, which you may already have
  filed. Confirm to save it: a copy of your ledger is made first.", `years`
  `[2025]`, one change whose `change` is "Added: basis 1000.00; cost of the
  lots it made 1000.00.", a `confirm`, and a `to_confirm` beginning "Nothing
  was saved: this would change the figures of tax years the user may already
  have filed." (the ledger still has 14 rows); call it again with that
  `confirm`. Expect: it appears in the UI list. Run `update_transaction` with
  `transaction_id=<its id>` and `cost_basis_usd=1100`: `saved: false` again,
  `detail` "This changes the figures of tax year 2025, …", the change "basis
  1000.00 -> 1100.00; cost of the lots it made 1000.00 -> 1100.00."; send it
  again with `confirm` set to its `confirm`. Expect: the UI shows
  $1,100.00. `delete_transaction`: `saved: false`, the change "Deleted: basis
  1100.00; cost of the lots it made 1100.00."; it removes the row once sent
  again with its `confirm`. Expect: 14 rows, every golden figure unchanged,
  and an AI copy (`btctx-ai-before-changing-….db` in `backups`) made before
  each confirmed call.
- **AI-11** `recalculate_ledger`: success with nothing to confirm (REV-2
  recalculated this ledger, so nothing is pending), figures unchanged.
  `backup_ledger`: success, naming a file in the app's backups folder.
  `get_btc_price` with `date=2024-05-01`: a price above $0.
- **AI-12** In **Connect an AI Assistant**, **New key** and confirm. Expect:
  MCP calls with the old key fail with "AI key not accepted: it was replaced
  or revoked, or was copied wrong."; the new key works. **Revoke**: the new
  key fails the same way. **Create AI key** again (use this key from now on),
  untick AI access, and expect calls to fail with "AI access is turned off in
  BitcoinTX Settings.". Tick it again.
- **AI-13** Call `get_portfolio` with `-e BTCTX_PASSWORD=x` added. Expect:
  the call fails with "BitcoinTX no longer uses your password for AI
  access. …", and nothing reaches the app.
- **AI-14** (judgment, optional) In a real AI app (Claude Desktop, Grok or
  LM Studio) set up with the AI-7 configuration, paste: "Bought 0.01 BTC on
  River for $1,000 on July 1 2025, fee $10". Expect: the assistant shows a
  preview and asks before saving; after "yes" the row exists. Ask it to
  delete that row. Report whether it previewed before saving.
- **AI-15** (from 2.0) A 1.x connector can't tell Coldcard from Wallet, so
  once the ledger has two wallets (or two exchanges, hidden ones counted)
  BitcoinTX refuses its writes; reads go on. Run the last 1.x connector:

  ```bash
  MCP1="uvx btctx-mcp==1.2.10"
  mcp1() { npx -y @modelcontextprotocol/inspector@2.8.0 --cli $MCP1 -- \
             -e BTCTX_URL=$API -e BTCTX_AI_KEY=$KEY -e BTCTX_CA_BUNDLE=$PWD/ca.crt "$@"; }
  ```

  Expect `tools/list` to give 1.2.10's 11 tools (no `get_coins_moved`), and every tool's answer
  to start with "Your BitcoinTX connector is v1.2.10 but BitcoinTX is vX.Y.Z. In
  your AI app's settings, change btctx-mcp==1.2.10 in its uvx command to
  btctx-mcp==X.Y.Z, then restart the AI app." `get_portfolio` lists the
  Dashboard's balances, Coldcard and Kraken's included; `list_transactions`
  returns 14 rows; `preview_transactions` with AI-10's first row answers
  `ready`. `add_transactions` with that row fails with "BitcoinTX returned
  409: This AI connector is older than BitcoinTX 2.0 and can't tell your
  wallets or exchanges apart. Update it (btctx-mcp 2.0 or later), then try
  again.", and so does `recalculate_ledger`; the ledger still has 14 rows
  and no new `btctx-ai-before-changing-….db`. Hide Coldcard and Kraken in
  Settings: `recalculate_ledger` is still refused (hidden accounts count).
  Show both again. The candidate's connector (`mcp`) makes the same
  `recalculate_ledger` call: success, as in AI-11.
- **AI-16** (from 2.0) The other way round: the candidate's connector on
  the last 1.x. From 2.0.0's release an AI app running `uvx btctx-mcp`
  without a version gets 2.0.0, while a StartOS server may still run
  1.2.10 from Start9's Community Registry. A pass of its own, on the VM
  from `clean` (or on WAY-6's Docker 1.2.10, on a volume of its own):
  sideload 1.2.10's `btctx.s9pk`, do its tasks (Price Source & Privacy:
  **Decide in BitcoinTX instead**), start it, run `golden_loader.py`,
  create an AI key and turn AI access on (1.x's Settings shows every
  section). Run the candidate's connector as `mcp` (Inputs; a
  pre-release's `uvx btctx-mcp==2.0.0bN`) against it: `API`, `KEY` and
  `ca.crt` set to this 1.2.10's (on WAY-6's Docker, with WAY-6's own
  container stopped first: `API` `http://127.0.0.1:8792/api`, and `mcp`
  without its `-e BTCTX_CA_BUNDLE=…`). Expect:
  - every tool's answer, or its error, to start with "Your BitcoinTX
    connector is v<connector> but BitcoinTX is v1.2.10. Update BitcoinTX,
    or set the connector back to v1.2.10 in your AI app's settings."
    (`<connector>` as PyPI writes it: `2.0.0b2` for beta.2, `2.0.0` at the
    release);
  - `tools/list` to give the candidate's 12 tools; `get_portfolio` 1.x's
    four accounts (Bank, Wallet, Exchange USD, Exchange BTC) and the
    Dashboard's balances; `list_transactions` 14 rows; `review_ledger` an
    answer; `preview_transactions` with AI-10's first row `ready`;
  - an account 1.x doesn't have refused in plain words:
    `preview_transactions` with that row's `to_account` `Coldcard` fails
    with "Unknown account 'Coldcard'. This BitcoinTX is older than 2.0 and
    has only these accounts: Bank, Wallet, Exchange USD, Exchange BTC, and
    External.";
  - a choice of coins refused before anything is written, in plain words
    naming BitcoinTX's version (#834): `add_transactions` with
    `[{"date":"<today>","type":"Withdrawal","amount":"0.001","from_account":"Wallet","to_account":"External","purpose":"Spent","proceeds_usd":"100","fee_amount":"0","fee_currency":"BTC","chosen_coins":[{"acquired_txn_id":9,"btc":"0.001"}]}]`
    fails, and the ledger still has 14 rows; `update_transaction` with
    `{"transaction_id":14,"chosen_coins":[{"acquired_txn_id":9,"btc":"0.0101"}]}`
    fails the same way; `get_coins_moved` with `{"transaction_id":14}`
    says so too, never "405: Method Not Allowed";
  - `add_transactions` with AI-10's first row saved (`imported_count` 1):
    a row 1.x knows is still 1.x's to save. Delete it with
    `delete_transaction`.

  A crash, a trace, or a write whose answer says something other than
  what was saved is a blocker FAIL.

### BAK and IMP: backups and imports

- **BAK-1** Settings, open **Backup & Restore**, **Export CSV**. Expect:
  the file `btctx_transactions_<date>.csv`, the header
  `date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency,source,purpose,notes,fee_usd,fmv_usd,broker_reporting,fee_usd_typed,cost_basis_typed,acquired_at,proceeds_typed,price_moment,fmv_typed`
  and 14 rows. #4's `fee_usd` is `10.00` and #14's is `5.00`. Settings'
  message line says "CSV export downloaded."
- **BAK-2** Download Encrypted Backup: type `backup-pass-123` in both
  password boxes (hidden as typed), then **Download**. Different entries
  in the two boxes say "The two passwords don't match." and download
  nothing; so does `backup-pass` in both (11 characters: "The password is
  too short. At least 12 characters.", #204). Expect: the file
  `bitcoin_backup.btx` and "Backup downloaded."
- **IMP-1** Settings, open **Data Management**: **Template** and
  **Instructions**. Expect: `btctx_import_template.csv`, whose header is the
  same as BAK-1's, and `BitcoinTX_CSV_Import_Guide.pdf`, which opens.
- **IMP-2** Choose BAK-1's CSV, then **Preview**. Expect it refused on a
  non-empty ledger: "Database has 14 existing transaction(s). Please delete
  all transactions before importing, or start with a fresh database."
- **IMP-3** Round trip. In **Data Management**, **Delete** (Delete All
  Transactions). Expect a
  dialog "Delete all transactions?" (not the browser's confirm, #256)
  saying "This deletes 14 transactions, 2023–2025", that BitcoinTX first
  keeps a copy in its data folder (in `backups`, unencrypted), and offering
  **Download a backup first**; **Delete 14 transactions** stays disabled
  until `DELETE` is typed (`delete` doesn't do). **Cancel**, then log in
  with curl as in SEC-4 (`-c jar`) and send
  `curl --cacert ca.crt -s -w '\n%{http_code}\n' -b jar -X DELETE $API/transactions/delete_all`:
  expect 409, "This deletes all 14 transactions, 2023–2025. To go ahead,
  confirm with DELETE.", and still 14 transactions. Then **Delete** again,
  type `DELETE`, **Delete 14 transactions**. Expect
  "Deleted 14 transactions, 2023–2025. A copy of the database from before
  is kept in BitcoinTX's data folder (in backups, unencrypted).", an empty
  Dashboard, and `start-cli package attach btctx -n btctx -- ls /data/backups`
  listing one `btctx-before-delete-all-….db`. **Wallets, exchanges and
  banks** still lists Coldcard and Kraken, at $0.00 and 0.00000000 BTC
  (Delete All deletes transactions, never accounts). Save this file as
  `fee-account.csv`:

  ```csv
  date,type,amount,from_account,to_account
  2024-01-05T12:00:00Z,Deposit,1,External,BTC Fees
  ```

  Choose it, then **Preview**. Expect it refused at Preview, before any
  Import (#266): "0 valid / 1 total rows", "Row 2 (to_account): Invalid
  account 'BTC Fees'. Must be one of your accounts (Bank, Wallet, Exchange
  USD, Exchange BTC, Coldcard, Kraken USD, Kraken BTC) or External." (your
  accounts as the app lists them, by id; never a fee account) and
  **Import 0 Transactions** disabled. **Cancel**
  (it clears the chosen file). Then choose BAK-1's CSV again and
  **Preview**. Expect "14 valid / 14 total rows". Click **Import 14 Transactions** and
  confirm. Expect "Successfully imported 14 transaction(s)." and **every
  golden figure**: the file carries the fees' USD values, so nothing is
  priced again.
- **BAK-3** Before restoring, in **Connect an AI Assistant** click **New
  key** and keep the new key (the backup holds an older one). In **Backup &
  Restore**, **Restore from Backup** with BAK-2's file and
  the password `wrong-pass`. Expect "Restore failed: ❌ Failed to decrypt
  backup. Wrong password, or the file is damaged or isn't a BitcoinTX
  backup." with the ledger unchanged. Then restore with `backup-pass-123`. Expect "✅ Database
  successfully restored. Log in again with your current username and
  password.", then the login page. Log in with the login in use before the
  restore (a restore never brings back the backup's password).
  Expect: every golden figure, Coldcard and Kraken in **Wallets, exchanges
  and banks** (the backup's accounts), and the key made just before the
  restore still works (a restore never brings back an older key).
- **IMP-4** River import. Save this file as `river.csv`:

  ```csv
  Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag
  2026-01-05 12:00:00,25.00,USD,0.00030000,BTC,,,Buy
  2026-02-03 15:30:00,148.50,USD,0.00180000,BTC,1.50,USD,Buy
  2026-02-10 16:00:00,0.00050000,BTC,55.00,USD,0.55,USD,Sell
  ```

  Settings, open **Import from an exchange** (River's file, **Exchange
  file** `River`, is its first choice). Expect, from 2.0 (two exchanges
  and two wallets), before the file and **Preview**: **Exchange** with
  none chosen ("Choose an exchange"), `Exchange` and `Kraken` offered,
  "The exchange this file is from: its buys, sells and balances go
  there.", the line "Recorded this exchange's trades in another one
  before 2.0? …", and **Wallet for sends and receives** with `Wallet`
  chosen and `Coldcard` offered, "This file's sends to your wallet go into
  it, and its receives come from it."; **Preview** greyed, "Choose the
  exchange first." under it (#707, #773). Choose `Exchange`, leave the
  wallet. River CSV file, then **Preview**.
  Expect: "3 new", "3 rows in file", and each Buy row showing the
  **Bank** / **Exchange USD** toggle. Click **Import 3 Transaction(s)**
  and confirm "Import 3 transaction(s) from River into your ledger?" (run
  in a later year, when 2026 is an earlier tax year, the preview first
  says "Rows dated in tax year 2026 can change the figures of that year
  and later ones…" and the import asks in the past-year dialog: **Save
  anyway**, #353). Expect "Imported 3 transaction(s)." The Sell shows
  Gain +$5.00 (net proceeds $55.00 = River's $55.00 received, which is
  after River's $0.55 fee; basis 0.0005 × $100,000 from lot C). Preview
  the same file again (choose `Exchange` again first: an import or
  **Cancel** asks each file's exchange anew, #707). Expect: "3 already in ledger" and
  "0 new". Click **Show 3 already-imported row(s)**. Expect each row's
  Import box unticked but clickable, and "Tick one to import it anyway, if
  it's another transaction." (#253). Leave them unticked and **Cancel**.
  Preview the file with its first row's time changed to `2026-01-06
  09:00:00` (`Exchange` chosen again). Expect "2 already in ledger", "1 need review" and that row
  ticked, its note "Same BTC amount as tx #… (Buy 0.00030000 BTC),
  recorded 21 hours earlier: it may be the same transaction". **Cancel**.
- **IMP-4b** (from 2.0) River with two exchanges and two wallets. Save this
  file as `river2.csv` (a buy, a sale and a send to a wallet, all at
  Kraken):

  ```csv
  Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag
  2026-03-03 15:30:00,148.50,USD,0.00180000,BTC,1.50,USD,Buy
  2026-03-10 16:00:00,0.00050000,BTC,55.00,USD,0.55,USD,Sell
  2026-03-15 10:00:00,0.00100000,BTC,,,,,
  ```

  In **Import from an exchange** choose **Exchange** `Kraken` and **Wallet for
  sends and receives** `Coldcard`, then the file, then **Preview**.
  Expect "3 new", "3 rows in file", and the rows: the Buy with the **Bank**
  / **Kraken USD** toggle (**Bank** pressed: no earlier sale in the file
  leaves Kraken dollars to pay it, #655) and "→ Kraken BTC"; the Sell
  "Kraken BTC → Kraken USD"; the send a Transfer, "Kraken BTC → Coldcard".
  Click **Import 3 Transaction(s)** and confirm (the past-year dialog too,
  in a year after 2026). Expect "Imported 3 transaction(s)." and the Sell
  at Gain +$13.33: River's $55.00 net, less $41.67, the cost of 0.0005 of Kraken's own 0.0018 BTC
  lot ($148.50 plus its $1.50 fee), where IMP-4's same sale at the
  Exchange took lot C (+$5.00). Dashboard: Wallet (BTC) lists `Coldcard`
  0.00100000 BTC; Exchange (USD) `Kraken` $55.00 and Exchange (BTC)
  `Kraken` 0.00030000 BTC; **Filter transactions** `Coldcard` shows only the
  Transfer. Preview the file again with the same choices: "3 already in
  ledger", "0 new"; **Cancel**.
- **IMP-5** (from 2.0) A second exchange's file through the importer for
  any exchange, into a ledger with rows: Kraken's made-up sample
  `testdata/exchange_files/kraken_ledgers.csv` (the tested commit's: 20
  rows of 2025 in Kraken's published "ledgers" format; times in UTC). In
  **Import from an exchange**, **Exchange file** `Kraken`. Expect the hint
  "kraken.com → profile icon → Documents → Create export → Ledgers, from
  your first day to today, all assets, types and fields, CSV (a .zip
  holds ledgers.csv).", the warning "Read as Kraken publishes its file,
  not yet checked against a real one: check the preview's rows against
  your file before you import them.", and the file's field "Kraken CSV
  file". Choose
  **Exchange** `Kraken` and **Wallet for sends and receives** `Coldcard`,
  the file, then **Preview**. Expect "6 new", "0 already in ledger", "20
  rows in file"; the note "Rows dated in tax year 2025 can change the
  figures of that year and later ones you may already have filed:
  BitcoinTX shows what changes, and asks, before it imports them." (none,
  and no dialog below, if the walk runs in 2025); and "Warnings (8):":
  - "Row 9 is Kraken's pending copy of a deposit or withdrawal (no txid),
    whose completed row is read: left out."
  - "Rows 2 and 21 move dollars, not bitcoin: left out."
  - "Rows 12 and 13 move coins between Kraken's own balances (spot,
    staking, earn): left out."
  - "Rows 15 and 16 are ETH, not bitcoin (BitcoinTX tracks bitcoin only):
    left out."
  - "Rows 17 and 18 trade bitcoin for ETH: add each by hand (bitcoin given
    up as a Withdrawal, purpose Spent, at its dollar value: a disposal,
    IRS Notice 2014-21): left out."
  - "Rows 19 and 20 are a withdrawal Kraken sent back (they add up to
    nothing): left out."
  - "Row 11: From your wallet, oldest coins first: you can choose the coins
    after the import."
  - "Row 14: 0.0000012345 BTC is rounded to 0.00000123 BTC: BitcoinTX
    counts whole satoshis."

  The six rows: two Buys (rows 4 and 8) "→ Kraken BTC", each with the
  **Bank** / **Kraken USD** toggle: row 4 **Bank** pressed (no earlier sale
  has left Kraken dollars to pay it, #655), row 8 **Kraken USD** pressed (the
  row-5 sale covers it); a Sell (row 5)
  "Kraken BTC → Kraken USD"; two Transfers, "Kraken BTC → Coldcard" (row
  10) and "Coldcard → Kraken BTC" (row 11); a Reward Deposit (row 14)
  "External → Kraken BTC". Leave them as they are. **Import 6
  Transaction(s)**: the confirm "Import 6 transaction(s) from Kraken into
  your ledger?", then the past-year dialog, "This changes the figures of
  tax year 2025, which you may already have filed. Confirm to save it: a
  copy of your ledger is made first.", with these lines:
  - `2025-01-03 05:15 · Buy · 0.00500000 BTC — Added: basis 500.00; cost
    of the lots it made 501.30.`
  - `2025-02-10 03:00 · Sell · 0.00200000 BTC — Added: proceeds 209.45;
    basis 200.52; gain 8.93; taxable gain incl. network fees 8.93.`
  - `2025-02-15 07:30 · Buy · 0.00098000 BTC — Added: basis 100.00; cost
    of the lots it made 101.49.`
  - `2025-03-01 04:05 · Transfer · 0.00201500 BTC — Added: taxable gain
    incl. network fees <F − 1.50>; cost of the lots it made 200.52.`, where
    F is the 0.000015 BTC fee's value: 0.000015 × the price
    `GET $API/bitcoin/price/history?at=2025-03-01T09:00:00Z` answers, to
    the cent;
  - `2025-03-05 13:45 · Transfer · 0.00100000 BTC — Added: cost of the
    lots it made 100.26.`
  - `2025-03-12 20:00 · Deposit (Reward) · 0.00000123 BTC — Added: income
    (Reward) <V>; basis <V>; cost of the lots it made <V>.`, V being
    0.00000123 × the price at
    `2025-03-13T00:00:00Z`, to the cent.

  (From 2027 the dialog names tax years 2025 and 2026, and also lists IMP-4b's
  Sell, now of the 2025 buy's coins (among its changes: gain 13.33 -> 4.87,
  short-term to long-term, box G -> K, date acquired 03/03/2026 ->
  01/03/2025), and IMP-4b's Transfer (cost of the lots it made 83.33 ->
  100.26).) **Save anyway (a copy is made first)**. Expect "Imported 6
  transaction(s)." On Transactions, **Filter transactions** `Kraken`: "9 of 26
  transactions", the six with IMP-4b's three. The rows: the 0.005 BTC Buy,
  Bank → Kraken BTC, at a cost of $500.00 and a fee of $1.30 (its
  **Edit**: Amount USD 500, Fee (USD) 1.30); the Sell, Gain +$8.93 ($209.45
  net of its $0.55 fee, less $200.52, the cost of 0.002 of Kraken's own 0.005
  BTC, bought for $500.00 plus its $1.30 fee); the 0.00098 BTC Buy, $100.00
  and a $1.49 fee; the Transfer of 0.002015 BTC, Kraken BTC → Coldcard, its
  fee 0.000015 BTC; the Transfer of 0.001 BTC, Coldcard → Kraken BTC; and the
  Reward of 0.00000123 BTC into Kraken BTC. IMP-4b's 2026 Sell now shows Gain
  +$4.87, not +$13.33: Kraken's oldest coins are now the 2025 buy's, and
  0.0005 of them cost $50.13 (lots per exchange, first in, first out).
  Dashboard: Exchange (USD) lists `Kraken` at no dollars below zero,
  Exchange (BTC) `Kraken` 0.00326623 BTC and Wallet (BTC) `Coldcard`
  0.00200000 BTC.
  Preview the file again with the same choices: "6 already in ledger", "0 new"; **Cancel**.
- **IMP-6** (from 2.0) Another exchange's file, its columns matched by
  hand. Save this file as `example.csv` (B5b's click-through test's):

  ```csv
  Exported by Example Exchange
  When,Type,Coins,Dollars,Charge,Charge In,Ref,State
  2025-04-01 09:00,Bought,0.01000000,"1,010.00",10.00,USD,r-1,done
  2025-04-03 09:00,Withdrew,0.00200000,,0.00001000,BTC,r-3,done
  2025-04-04 09:00,Bought,0.01000000,"1,010.00",10.00,USD,r-4,waiting
  ```

  **Exchange file** `Another exchange: match its columns`, with the hint
  "Choose the file, then say which of its columns holds what: you can save
  it for next time."; choose the file ("Exchange CSV file"). Expect the
  table "The file's first rows" with its three rows, captioned "Row 2 of
  the file names its columns."; **Kind of row** `Type`, **Status (if
  any)** `State` and **Row id (if any)** `Ref` already chosen from their
  names, and "“Bought” is" already `Buy`; "Still to match: Date, Bitcoin
  amount."; and **Preview** off. Choose **Date** `When`, **Bitcoin
  amount** `Coins`, **Dollar amount (if any)** `Dollars`, **Fee (if any)**
  `Charge` and **Fee currency (if any)** `Charge In`; "“Withdrew” is"
  `Send out`; under "A completed row's status" tick
  `done`; tick "A buy's dollars include its fee (the total paid)". Expect
  the "Still to match" line gone. With **Exchange** `Kraken` and **Wallet
  for sends and receives** `Coldcard`, **Preview**: "3 rows in file", "2
  new", the warning "Row 5 is waiting, not completed: left out.", a Buy
  of 0.01 BTC "→ Kraken BTC" and a Transfer of 0.002 BTC "Kraken BTC →
  Coldcard". **Mapping's name** `Example Exchange`, **Save this mapping**:
  the toast "Saved “Example Exchange”." and **Exchange file** showing it,
  under "Your mappings". **Preview**, then **Import 2 Transaction(s)**:
  the confirm "Import 2 transaction(s) from Example Exchange into your
  ledger?", then the past-year dialog's lines `2025-04-01 05:00 · Buy ·
  0.01000000 BTC — Added: basis 1000.00; cost of the lots it made
  1010.00.` and `2025-04-03 05:00 · Transfer · 0.00201000 BTC — Added:
  taxable gain incl. network fees <F − 1.01>; cost of the lots it made
  200.60.` (F: 0.00001 × the price at `2025-04-03T09:00:00Z`). **Save
  anyway**: "Imported 2 transaction(s).", the Buy's cost basis $1,000.00
  and its fee $10.00 (the $1,010.00 paid held the fee). IMP-4b's 2026 Sell
  now shows Gain +$3.22: the Transfer took the rest of Kraken's 2025-01-03
  lot, so the Sell's coins are now the 2025-02-15 buy's. (From 2027 the
  dialog names 2025 and 2026 and also lists IMP-4b's Sell, among its
  changes basis 50.13 -> 51.78, gain 4.87 -> 3.22 and date acquired
  01/03/2025 -> 02/15/2025, and its Transfer, cost of the lots it made
  100.26 -> 102.14.) Reload: **Exchange
  file** still lists `Example Exchange` under "Your mappings".
- **IMP-7** Preview a CSV that isn't the chosen exchange's, for example
  `date,type,amount` plus one row. With **Exchange file** `River`, expect
  "This does not look like a River bitcoin-activity CSV. Missing columns:
  …"; with `Kraken`, "This does not look like a file for “Kraken”. Missing
  columns: txid, refid, time, asset, fee" (no row number: it's the file's
  header). Nothing is saved.
- **BAK-4** Restore BAK-2's backup again, which removes the rows IMP-4 to
  IMP-6 imported. Expect every golden figure, Coldcard and Kraken at $0.00
  and 0.00000000 BTC, and **Exchange file** still listing `Example
  Exchange` under "Your mappings": a restore keeps the mappings saved
  since the backup, beside the backup's own (it had none), while it takes
  the backup's rows (#656).

### SEC: the live install from outside

- **SEC-1** Without a session, `curl --cacert ca.crt -o /dev/null -w "%{http_code}"`
  on `$API/transactions`, `$API/settings/network` and `$API/reports/years`.
  Expect: 401 for each. `curl --cacert ca.crt -s -D - -o /dev/null
  $API/reports/years` shows `401` and `cache-control: no-store` (#204: the
  header reaches the browser through StartOS's proxy).
- **SEC-2** `$URL/openapi.json`. Expect: 404. `$URL/docs` and `$URL/redoc`
  show the app itself (its login page or Dashboard, like any unknown
  path), never the API documentation.
- **SEC-3** `curl --cacert ca.crt -sI $URL/`. Expect these headers:
  `content-security-policy` (including `frame-ancestors 'none'`),
  `referrer-policy: no-referrer`, `x-content-type-options: nosniff`,
  `x-frame-options: DENY`.
- **SEC-4** Log in with curl:
  `curl --cacert ca.crt -si -c jar -X POST $API/login -H 'Content-Type: application/json' -d '{"username":"…","password":"…"}'`.
  Expect: `set-cookie: btc_session_id=…` with the attributes `HttpOnly`,
  `SameSite=lax` and `Secure`, in any letter case (StartOS serves over
  HTTPS); and `set-cookie: btc_device=…` (the login throttle's device
  cookie) with `HttpOnly`, `SameSite=lax`, `Secure` and
  `Max-Age=31536000`.
- **SEC-5** With that cookie (`-b jar`), `POST $API/transactions/recalculate`:
  - with `-H 'Sec-Fetch-Site: cross-site'`: expect 403;
  - with `-H 'Origin: https://evil.example'`: expect 403;
  - with neither header: expect 200;
  - from 2.0, as a page of the same site that doesn't say its version (a
    1.x page left open over the update), `-H 'Sec-Fetch-Site:
    same-origin'`: expect 409 and `{"detail":"BitcoinTX was updated: reload
    the page."}`; with `-H 'X-BitcoinTX-Page: 1.2.10'` added, the same 409;
    with `-H 'X-BitcoinTX-Page: X.Y.Z'` instead, 200 (any page of the
    server's major version is taken).

  Then `POST $API/logout` with `-b jar` (no `-c`, so the jar keeps the
  cookie) and `GET $API/transactions` with it again. Expect: 401 (logging
  out ends that session, for every copy of its cookie), while the app in
  the browser, a session of its own, stays logged in.
- **SEC-6** `GET $API/users/setup-status`. Expect `setup_code_required`
  false.
- **SEC-7** While using the app, record the browser's network requests
  (Playwright `page.on("request")` or devtools). Expect: every request goes
  to `$URL`'s own origin, with no fonts, CDNs or analytics.
- **SEC-8** Password rules (Settings, open **Account**: Reset Username &
  Password). Open a second browser session (a new profile or incognito)
  logged in as well. Then:
  - an 11-character new password: expect "The new password is too short.
    At least 12 characters.";
  - no current password: expect "Enter your current password to change
    your username or password.";
  - new username `tester`, new password `tester-password-1`, the current
    password: expect "Credentials updated successfully.".

  The second session's next action lands on the login page. Log in as
  `tester`. Nothing in StartOS shows a password again: Set Login
  Credentials only makes a new one.
- **SEC-9** Last in Track A's security checks, because it makes you wait.
  First log in with the current login (SEC-8's `tester` /
  `tester-password-1`) into a fresh jar (`-c jar9`): SEC-8's password
  change made SEC-4's `btc_device` count as none. Then, without a cookie
  jar, send wrong passwords to `$API/login` in quick succession, at most
  eight. Expect: from the sixth or seventh on, HTTP 429 with a
  `Retry-After` header and "Too many failed attempts. Try again in N
  second(s).". At once, the correct login without a jar: expect 429 too
  (every request comes from StartOS's proxy, one address). With the fresh
  jar (`-b jar9`, its `btc_device` cookie): expect 200 at once (a browser
  that logged in before isn't stopped by others' failures). After waiting
  that long, the correct login without a jar works.

### LCK: locked out

- **LCK-1** With the service running, expect **Set Login Credentials**
  unavailable: it runs only while stopped.
- **LCK-2** Stop the service, run **Set Login Credentials**. Expect its
  warning "This replaces your current username and password. Your
  transactions are not touched.", then "Login Credentials" with `admin`
  and a new password; record it. Start the service. Expect: `tester` no
  longer logs in; `admin` with the new password does; every golden figure
  is intact.

### BAK (StartOS backup)

- **BAK-5** (needs the second virtual disk and the VM's StartOS password)
  Create a StartOS backup of BitcoinTX: System › Create Backup, the second
  disk, select BitcoinTX, the password ("Master password needed"), **Create
  Backup**. Then uninstall BitcoinTX (its data goes with it). Restore it
  from the backup: System › Restore Backup, the disk, the server, the
  password, BitcoinTX "Ready to restore", **Restore selected**. Expect: no
  Set Login Credentials task; the service
  starts; the LCK-2 password logs in; every golden figure; Tax Timezone
  America/New_York; the price source as PRC-6 left it; the AI key from BAK-3
  still works; **Wallets, exchanges and banks** with Coldcard and Kraken
  (Kraken's 1099-DA box ticked). INS-5's check that BitcoinTX isn't root
  passes too (from 1.2.9, #202).

### EXP: exploratory (30 minutes)

Use the app as a new owner would, looking for anything wrong: wording that
contradicts itself or the docs (`startos/instructions.md`, `docs/USING.md`,
`README.md`),
layout broken at phone width (375 px) and at 1440 px, keyboard-only use,
double-clicks on Save, very long or odd input (emoji, 21,000,000 BTC,
negative numbers, far-future dates; from 2.0, an account named with 40
characters, in the pickers, the dashboard's lists and the Complete Tax
Report, and a name with an emoji or a letter outside Western European
alphabets refused with the report's reason, #722), and the back button
mid-flow. Report
each finding with steps, what you expected and what happened, and a
severity: blocker (wrong tax figure, data loss, security), major, or minor.

### END: destructive checks, then uninstall

- **END-1** Delete #2 (the 2023-02-01 Buy that #4, #5 and #6 depend on).
  Expect it refused with "Failed to delete transaction: Not deleted: later
  transactions depend on this one. Not enough BTC to transfer 0.60000000
  (including fee 0.00020000)", and the ledger unchanged: 14 rows and every
  golden figure. Then add a $1 deposit to `Bank` and delete it.
  Expect both to work: a refused delete leaves the ledger usable.
- **END-2** Log out, then open `$URL/register` (the login page shows no
  link to it once the account is claimed).
  Expect: a **Current Password** field and no Setup Code. Enter a new
  username `fresh`, a 12+ character password and a wrong current password:
  expect it refused, with no dialog. Then the right one. Expect a dialog
  (not the browser's confirm, #256) "Create a new account and delete every
  transaction?" saying "This deletes 14 transactions, 2023–2025", that a
  copy is kept in the data folder, and how to download a backup after
  logging in (a **Log in** link; no download button, not being logged in).
  **Delete 14 transactions** stays disabled until `DELETE` is typed. Type
  it and click it. Expect "Registration successful! Your credentials have
  been updated. A copy of the database from before is kept in BitcoinTX's
  data folder (in backups, unencrypted).", and `ls /data/backups` (as in
  IMP-3) listing one more `btctx-before-delete-all-….db`. Logging in as
  `fresh` shows an empty ledger. From 2.0, Settings' **Wallets, exchanges
  and banks** still lists Coldcard and Kraken (the reset deletes
  transactions, never accounts), each now with **Delete**; Bank's row
  offers none: "Your first bank, wallet and exchange can't be deleted.
  Hide one you don't use."
- **END-3** Uninstall BitcoinTX, then sideload the same `btctx_x86_64.s9pk`
  again (Start9's `publishing.md`: "Uninstall and reinstall to confirm
  teardown works"). Expect a fresh install, as INS-1 and INS-2: the two
  critical tasks, and nothing kept from before. Run them as INS-3 and INS-4
  and start it: `admin` with the new password logs in, `fresh` doesn't, and
  `start-cli package attach btctx -n btctx -- ls /data` lists no `backups`
  folder: a fresh install has made no copy yet, and END-2's
  `btctx-before-delete-all-….db` went with the uninstall.
  Then uninstall it and revert the VM to `clean`.

---

## Track B: update from the previous release

Start from the `clean` snapshot.

- **UPG-1** Sideload the previous release's `btctx.s9pk`. Do its tasks,
  choose **Public price sites** in its Price Source & Privacy action, and
  start it. Run `golden_loader.py` with its credentials. Create an AI key
  and turn AI access on. Record Schedule D 2024 and 2025, the Dashboard
  figures, and the output of `curl $API/health`. From 1.x to 2.0 (2.0 and
  its pre-releases), also: in Settings (1.x shows every section), Download
  Encrypted Backup with `backup-pass-123` and keep the file as
  `golden-1x.btx` (BETA-3, BETA-5); make a StartOS backup of BitcoinTX to
  the second disk, as BAK-5 does (UPG-5b restores it); and leave a browser
  tab logged in on Transactions (UPG-2b).
- **UPG-2** Sideload `btctx_x86_64.s9pk` over it. Expect: it updates in
  place, starts healthy, and `$API/health` shows `X.Y.Z` and its
  schema. The same login works, and a browser logged in before the
  update stays logged in (updating from 1.2.7 or earlier, it shows the
  login page once first: every session from before 1.2.8 ends, #221). Every UPG-1 figure is identical.
  A Complete Tax Report's market values at a year's start and end are
  prices, not stored figures: until the hourly history has downloaded (a
  few minutes after a price source is chosen, or an update) they use the
  day's price, which the report's year-end note says. So before comparing
  them, at UPG-1 and here, wait until, logged in, `GET
  $API/bitcoin/price/status` gives `history.state` `complete`, or the
  service log has PRC-3b's line "aren't used" for a year. The AI key
  still works. Any tasks raised are only the ones this release's CHANGELOG
  entry announces. INS-5's check that BitcoinTX isn't root passes too
  (from 1.2.9: the update hands the old release's root-owned files to
  btctx, #202). If StartOS refuses the update because the CI package's
  signing key differs from the release's, mark UPG BLOCKED and run it after
  the release with the published `btctx.s9pk`.
- **UPG-2b** (from 1.x to 2.0) What the update to 2.0 adds:
  - The service log of the update reads "Migrating 1.2.10:0 -> " and the
    candidate's version, "Backed up the database to
    /data/backups/btctx-pre-2.0-from-0012-<time>.db before upgrading its
    schema", "Running upgrade 0012 -> 0100" and, after it, "Running
    upgrade 0100 -> 0101" (from alpha.3: coin choice's migration);
    `$API/health` shows `"schema": "0101"`; `ls /data/backups` (as in
    IMP-3) lists that copy.
  - The 1.x tab left open: Add Transaction, a Deposit of `1` into its
    `Bank Account`, dated today. Expect the toast "Failed to create
    transaction: BitcoinTX was updated: reload the page." and nothing
    saved. Reload: the 2.0 page (Settings in sections); the same deposit,
    into `Bank`, saves with no dialog. Delete it.
  - Settings, open **Wallets, exchanges and banks**: "1 wallet · 1
    exchange · 1 bank", the rows `Wallet`, `Exchange` and `Bank`, each in
    use. The dashboard's Portfolio Overview has no caret. **About
    BitcoinTX** has AUTH-4b's notice. The Complete Tax Reports end section
    2 with "Sales by exchange", as in the expected-figures table; every
    other figure as UPG-1 recorded.
  - With one wallet and one exchange, a 1.x connector writes as before
    (AI-15's `mcp1`, with UPG-1's key): `list_transactions` returns 14
    rows, and `add_transactions` with
    `[{"date":"<today>","type":"Buy","amount":"0.01","from_account":"Bank","to_account":"Exchange BTC","cost_basis_usd":"1000","fee_amount":"0","fee_currency":"USD"}]`
    saves it (`imported_count` 1), after its version notice. Delete it in
    the UI (this tax year: no dialog).
- **UPG-3** Ledger Review. Expect "Figures that Recalculate Ledger would
  change" to be absent (count 0), unless this release's CHANGELOG says a
  recalculation changes figures. Then its items must be exactly the ones
  described there. From 1.x to 2.0, neither "Transactions naming an
  account that doesn't exist" nor "Transactions in an account made through
  BitcoinTX's old account API" is listed (the golden ledger has no such
  row: REF-4 checks a ledger that has).
- **UPG-4** (optional) Sideload the previous release over the new one.
  Expect: refused, or a service that won't start with "database schema is
  …" in its health check. Record which. Sideload the new one again and
  expect every figure intact. From 1.x to 2.0: refused, in StartOS's words
  (WAY-2 checks them), and 2.0 keeps running.
- **UPG-5** (#134) The source is still set by the action only (UPG-1). No
  `backend.cli` may have been run by hand in Track B before this step: under
  the previous release that saves a choice. Logged in,
  `GET $API/bitcoin/price/history?date=2024-12-31`: expect a USD value, so a
  price is stored. Action **Price Source & Privacy**: **Decide in
  BitcoinTX instead**. Once the service has restarted, expect the card "Bitcoin
  prices" on the Dashboard, nothing chosen, and
  `GET $API/settings/network` (logged in) to say `"price_source":
  "unset"`, `"managed": false`. Public price sites saved by themselves is
  a FAIL. Set the action back to **Public price sites**.
- **UPG-5b** (from 1.x to 2.0; needs UPG-1's StartOS backup and the VM's
  StartOS password) A 1.x StartOS backup restored, then updated (Start9's
  rule for a restore below the current version). Uninstall BitcoinTX (2.0
  and its data go). Restore UPG-1's StartOS backup, as BAK-5 does. Expect
  BitcoinTX back at 1.2.10 (the service page's version, and
  `$API/health`'s `"schema": "0012"`), UPG-1's login, the golden figures
  and 14 rows. Sideload `btctx_x86_64.s9pk` over it. Expect UPG-2 and
  UPG-2b's log lines and schema again: it updates in place, every UPG-1
  figure identical, the login and the UPG-1 AI key working.
- **UPG-6** (#145, confirm once) A pass of its own, after UPG-5: restore
  the VM's `clean` snapshot, sideload 1.2.7 (`btctx.s9pk` of the v1.2.7
  GitHub release, the last before #145; not the previous release) and set
  its login as in UPG-1. Under 1.2.7: action **Choose in BitcoinTX**, then
  in the app Settings > Privacy & Network choose **Public price sites** and
  save. Sideload the candidate and log in. Expect on the Dashboard the card "Please confirm where
  BitcoinTX gets prices", **Public price sites** selected with "Your
  current choice", its status line "Waiting for you to confirm: nothing is
  contacted until you do.", Current Bitcoin Price "Confirm your choice",
  and the sidebar "waiting for you". The service log has no new line
  starting "BTC price history from", "Latest BTC prices from" or "Hourly
  BTC prices" before you confirm. Press **Confirm**: the card goes away without a reload and a
  price appears. Restart the service: not asked again. Settings, open
  **Privacy & Network**: "You chose this on … in the first-run question."
  Set the action back to
  **Public price sites**.
- **UPG-7** (#145, the package asks once) A pass of its own: restore the
  VM's `clean` snapshot, sideload 1.2.7 (`btctx.s9pk` of the v1.2.7 GitHub
  release, the last before #145; not the previous release), set its
  login as in UPG-1, start it, and never run **Price Source & Privacy**.
  Sideload the candidate. Expect the task **Price Source & Privacy**,
  important (not critical): "Prices are now hourly. Check who BitcoinTX
  asks for newer ones.", and beside it **Recalculate Ledger** (important;
  1.2.8's migration makes it due, and so do 1.2.9's and any later one
  that asks for it: one task). The service keeps running. Dismiss both tasks (`start-cli
  package action clear-task btctx choose-price-source`, then
  `recalculate-after-0.8.0`), then restart the service and the server:
  neither comes back (#365).
- **UPG-8** (#143, a beta user may skip a release) A pass of its own:
  restore the VM's `clean` snapshot, sideload the published 1.2.5:0
  (`btctx.s9pk` of the v1.2.5 GitHub release), set it up as in UPG-1 (its
  action may name the choices differently), then sideload the candidate.
  Expect UPG-2 and UPG-3 to hold from 1.2.5:0: it updates in place, every
  recorded figure is identical, the login and the AI key still work. UPG-3's
  exceptions are the CHANGELOG entries of every release after 1.2.5
  (1.2.6 to the previous release) and of this release.

## WAY: back to 1.x (2.0 and its pre-releases)

2.0 can't be downgraded in place, and 1.x can't read a 2.0 database or
backup, so what was entered in 2.0 is lost on the way back. These are the
ways back the release notes (StartOS) and the README's "Going back to
1.x" (Docker, the Mac app) give, as B9 tried them on StartOS 0.4.0.3 (2026-10-24; the
StartOS backup's own way back, WAY-1's backup and WAY-3's restore, is
recorded on #357 once tried).
WAY-1 to WAY-5 run in order on one VM, from the `clean` snapshot, and need
the second disk and the VM's StartOS password; WAY-6 needs Docker on your
machine, WAY-7 a Mac. Below, `<2.0>` is the candidate's version and
`<1.x>` 1.2.10's, as StartOS writes them.

- **WAY-1** Sideload 1.2.10's `btctx.s9pk`, do its tasks (Price Source &
  Privacy: **Decide in BitcoinTX instead**), start it and run
  `golden_loader.py`. Record the Dashboard figures. In Settings (1.x
  shows every section), Download Encrypted Backup with `backup-pass-123`,
  kept as `way-1x.btx`. Make a StartOS backup of BitcoinTX to the second
  disk (BAK-5's steps). Sideload `btctx_x86_64.s9pk`. Expect: it updates
  in place, at the same address and with the same login, with UPG-2b's log
  lines ("0012 -> 0100", then "0100 -> 0101") and `"schema": "0101"`;
  every recorded figure the same, and the
  reports the same plus "Sales by exchange". Add a Deposit of `1` into
  `Bank` dated today (a row only 2.0 has). Settings, open **Backup &
  Restore**: Download Encrypted Backup with `backup-pass-123`, kept as
  `way-2x.btx`.
- **WAY-2** Sideload 1.2.10's `btctx.s9pk` over it. Expect it refused:
  "This service cannot be downgraded from <2.0> to <1.x>: it provides no
  migration path back to <1.x>, so the data it has now cannot be carried
  over. To return to <1.x>, uninstall the service — which deletes its data
  — and restore a backup made while it was running <1.x>." (`start-cli`
  shows it cut short), and 2.0 still running with its 15 rows.
- **WAY-3** (First run in beta.2's gate, #806, with the VM's StartOS
  password typed by the person who set up the VM; the release repeats it.) Back by the StartOS backup. Uninstall
  BitcoinTX (its data goes), then restore WAY-1's StartOS backup (BAK-5's
  steps). Expect
  BitcoinTX at 1.2.10, `$API/health` with `"schema": "0012"`, WAY-1's
  login, the recorded figures and 14 rows: the 2.0 deposit is gone.
- **WAY-4** 1.x refuses a 2.0 backup. In this 1.2.10's Settings, Restore
  from Backup with `way-2x.btx` and `backup-pass-123`. Expect "Restore
  failed: This backup can't be restored: it was made by a newer version of
  BitcoinTX. Update BitcoinTX, or restore a backup made with this
  version." (HTTP 400), and the ledger unchanged: 14 rows.
- **WAY-5** Back by BitcoinTX's own backup, when the StartOS backup is
  gone. Sideload `btctx_x86_64.s9pk` (it updates this 1.2.10 to 2.0 in
  place), then uninstall it (its data goes). Sideload 1.2.10's
  `btctx.s9pk`, run its tasks (Set Login Credentials gives a new
  password), start it, log in, and in Settings restore `way-1x.btx` with
  `backup-pass-123`. Expect "✅ Database successfully restored. Log in
  again with your current username and password.", then the login page;
  the new login works, and the recorded figures and 14 rows are back.
  Then uninstall it and revert the VM to `clean`.
- **WAY-6** Docker, on your machine, on a volume of its own (never one
  with real data). Start 1.2.10:

  ```bash
  docker volume create btctx-way
  docker run -d --name btctx-way -p 127.0.0.1:8792:80 -v btctx-way:/data ghcr.io/digimonk73/btctx-mcp:v1.2.10
  ```

  Claim it: open `http://127.0.0.1:8792/register` and create an account
  (a username, a 12+ character password and the setup code `docker logs
  btctx-way` prints). Run `golden_loader.py` with
  `BTCTX_URL=http://127.0.0.1:8792` (no `BTCTX_CA`): "14 transactions
  loaded; tax timezone America/New_York". Record the Dashboard figures;
  `curl http://127.0.0.1:8792/api/health` shows `1.2.10` and `"schema":
  "0012"`. Then `docker rm -f btctx-way` and start the candidate's image
  the same way on the same volume (a pre-release:
  `ghcr.io/digimonk73/btctx-mcp:v2.0.0-beta.N`; a release candidate:
  `docker build -t btctx-candidate REPO`). Expect `docker logs` to say
  "Backed up the database to /data/backups/btctx-pre-2.0-from-0012-<time>.db
  before upgrading its schema", the health `"schema": "0101"`, the same
  login and the same figures. The way back, the copy run by the 1.x image
  itself (as its own user, `btctx`):

  ```bash
  docker rm -f btctx-way
  docker run --rm -v btctx-way:/data ghcr.io/digimonk73/btctx-mcp:v1.2.10 sh -c 'cp /data/backups/btctx-pre-2.0-from-0012-*.db /data/btctx.db && rm -f /data/btctx.db-journal /data/btctx.db-wal /data/btctx.db-shm'
  docker run -d --name btctx-way -p 127.0.0.1:8792:80 -v btctx-way:/data ghcr.io/digimonk73/btctx-mcp:v1.2.10
  ```

  Expect the health's `1.2.10` and `"schema": "0012"`, the login, and
  every recorded figure. A copy root makes as a new file (`docker rm -f
  btctx-way`, then `docker run --rm --entrypoint sh -v btctx-way:/data
  ghcr.io/digimonk73/btctx-mcp:v1.2.10 -c 'rm -f /data/btctx.db && cp
  /data/backups/btctx-pre-2.0-from-0012-*.db /data/btctx.db'`: `ls -l`
  shows it root's) stops a container started with `--user 10001:10001`
  ("unable to open database file", B9's trial), while one started without
  `--user` hands the file back to `btctx` and runs. (A `cp` over the
  existing `btctx.db` keeps its owner, so it starts either way.) Then `docker rm -f btctx-way` and `docker
  volume rm btctx-way`.
- **WAY-7** The Mac app, on test builds only (Track C's rules: never the
  installed app's folder). Unpack 1.2.10's `BitcoinTX-macOS.zip` into a
  temp folder (UNPACKED1X) and start it with
  `REPO/desktop/run-test-build.sh --app UNPACKED1X/BitcoinTX.app --fresh
  --background` (an app older than the script gets a test home too).
  Choose its login as MAC-3 does, run `golden_loader.py` with
  `BTCTX_URL=http://127.0.0.1:8766` and that login, record the Dashboard
  figures, and quit. Start the candidate's app (Track C's UNPACKED; for a
  pre-release, `BitcoinTX Preview.app`) with the script, without `--fresh`.
  Expect `curl http://127.0.0.1:8766/api/health` with `"schema": "0101"`,
  the same figures, and `ls DATA/backups` listing
  `btctx-pre-2.0-from-0012-….db`. Quit it. The way back: `cp
  DATA/backups/btctx-pre-2.0-from-0012-*.db DATA/btctx.db && rm -f
  DATA/btctx.db-journal DATA/btctx.db-wal DATA/btctx.db-shm`, then start
  UNPACKED1X's app with the script again. Expect `1.2.10`, `"schema":
  "0012"`, the login, and every recorded figure. Quit it.

## Track C: the Mac app (only on a Mac with Apple silicon)

The release's and CI's builds are arm64 only (built on `macos-latest`).

**On a Mac where BitcoinTX is already installed, its data folder is a real
ledger: never install, `open` or run the build's binary by itself there.**
On such a Mac, unpack the artifact in a temp folder (`ditto -x -k
BitcoinTX-macOS.zip .`, then `xattr -cr BitcoinTX.app` if it's quarantined)
and start every launch, the first, each reopen and MAC-5's second one, with
the repository's script (`docs/MACOS_DESKTOP_APP.md`, "Testing a build"):

```bash
REPO/desktop/run-test-build.sh --app UNPACKED/BitcoinTX.app --fresh --background   # the first launch
REPO/desktop/run-test-build.sh --app UNPACKED/BitcoinTX.app --background           # every later one
REPO/desktop/run-test-build.sh --where                                             # prints DATA
```

REPO, UNPACKED and DATA stand for absolute paths (the checkout, the temp
folder, the folder `--where` prints), written out in each command, since a
tool's shell may not keep variables. The script uses the same test folder
and port 8766 on every launch. Then read 8766 for 8765 and DATA for
`~/Library/Application Support/BitcoinTX/` below. The script's first launch
replaces all of MAC-1 (no dmg, no drag, no `open`): expect the app window
and no port banner; the window's title is "BitcoinTX Test". In MAC-4 give the connector `-e BTCTX_MCP_FILE=DATA/mcp.json`
after `--` (the Inspector passes the server nothing from the shell). In MAC-5, a second
launch shows "BitcoinTX Test is already open" without bringing a window forward,
and starts no second copy on 8766. If the installed app appears at any
point, leave it alone, touch nothing in it, and record that.

**A build with an installed app's identity is a hard rule of its own.**
From 2.0.0, the release's build is BitcoinTX itself (bundle id
`org.bitcointx.desktop`), and a pre-release's BitcoinTX Preview is the
tester's installed Preview. Opened by itself, such a build uses that app's
data folder (`~/Library/Application Support/BitcoinTX`, port 8765; the
Preview's own folder and port) and migrates its ledger: a 1.x app can't
read a 2.0 database back. So, on any Mac where that app is installed:

- Every launch goes through the script. Never a double-click, `open` or
  Finder, never a copy in /Applications: the build stays in its temp
  folder (UNPACKED), deleted when the track ends.
- Before each launch, record what answers on 8765 and 8767 (the installed
  BitcoinTX and BitcoinTX Preview): `curl -s --noproxy '*' -m 2
  http://127.0.0.1:8765/api/health`, and the same on 8767. Neither may
  change during the track: a version or schema that moved is a blocker
  FAIL; STOP.
- Before the first launch, check whether the test build shares the
  installed app's web view storage. WebKit keeps a window's cookies by
  bundle id, and a cookie ignores the port, so a test build's login on
  127.0.0.1 could replace the installed app's session or device cookie.
  Note the modification times of
  `~/Library/WebKit/<bundle id>` and `~/Library/HTTPStorages/<bundle id>*`
  (where they exist), launch, log in, quit, and compare; then `ls
  DATA/home/Library` for the test build's own. If the installed app's
  moved, it shares them: the owner quits the installed app before each
  launch and logs in to it again after the track, or the track runs on
  another macOS account. Record which.
- A step that can't keep these rules is BLOCKED, never run another way.

- **MAC-1** Open `BitcoinTX-macOS.dmg`, drag the app to Applications and
  open it: Control-click > Open, or on macOS 15+ System Settings > Privacy
  & Security > **Open Anyway**. Expect: the app window with BitcoinTX, and
  no port banner.
- **MAC-2** `curl http://127.0.0.1:8765/api/health`. Expect: version
  `X.Y.Z`. `ls -l ~/Library/Application\ Support/BitcoinTX/` shows
  `btctx.db` and `mcp.json`, and `mcp.json` is `-rw-------`.
- **MAC-3** First, from Terminal: `curl -s -X POST
  http://127.0.0.1:8765/api/login -H 'content-type: application/json' -d
  '{"username":"admin","password":"password"}'`. Expect 403 and "enter the
  setup code" (the default login works only with the code; the window
  supplies it). `ls -l` of the data folder shows `setup-code.txt` as
  `-rw-------`, and the code itself is in no log: `grep -rc "$(cat
  DATA/setup-code.txt)" DATA/logs` prints only zeros (the installed app:
  `~/Library/Logs/BitcoinTX/`). In the window, expect **Choose your
  username and password** (New Username, New Password, Repeat New
  Password), no Sign in form, no Setup Code field and no Create account
  link. Set username `mac-tester`
  and password `mac-tester-pass-1` twice, click **Continue**. Expect the
  Dashboard (the price question first), and `setup-code.txt` gone. Run
  `golden_loader.py` with `BTCTX_URL=http://127.0.0.1:8765` and those
  credentials. Expect: the golden Dashboard figures. IRS Reports 2025
  **Export** opens a save dialog, then "Saved to: <path>", and the PDF
  matches the 2025 figures.
- **MAC-4** Settings, open **Connect an AI Assistant**. Expect: **Reset key**
  instead of Create, and no "No AI key yet" line (#238: the app wrote its
  key at start); the Setup prompt says no key or address is needed; and
  a "Grok Build command" box. Tick **Let AI assistants use BitcoinTX**,
  then run the connector with no settings at all (as in AI-8, but with
  nothing after `--` except the method options; on a Mac with BitcoinTX
  installed, plus `-e BTCTX_MCP_FILE=DATA/mcp.json`, as above). Expect: 12 tools, and
  `get_portfolio` matches the Dashboard. **Reset key**: the connector keeps
  working (it re-reads `mcp.json`).
- **MAC-5** Quit and reopen within 5 seconds. Expect: the same port and no
  banner. Opening it again while it's open brings the window forward, with
  no second copy. With the MCP Inspector (or an AI app) left open across the
  quit and reopen, its next call still works: `mcp.json` has a new key and
  the connector picks it up by itself.
- **MAC-6** Quit, reopen and log in. Expect: the data is still there.
- **MAC-7** Your own mempool server, as PRC-4b. Settings, open **Privacy &
  Network**: **My own Mempool**, `https://mempool.emzy.de`, fallback off,
  save. Expect the Dashboard's price and block height. Then the Sats
  Converter's **Date** mode on a past day. Expect a price, and in
  `DATA/logs/run-test-build.out` "Price history from your mempool server:
  N days" with N in the hundreds (only if no daily price was stored yet:
  this build has asked no public site). Then clear the address, choose
  **Nobody** (which hides the address field, and keeps an address left in
  it), and save.
- **MAC-UPG** (from 1.x to 2.0) The update a Mac user makes in place:
  2.0.0's `BitcoinTX.app` over 1.2.10's, the same name, bundle id
  `org.bitcointx.desktop` and data folder. The script sets the folder, the
  port and HOME itself, so this proves the migration and the AI setup; the
  folder each version picks by itself is `test_desktop_paths.py`'s. Quit
  every test run. Unpack 1.2.10's `BitcoinTX-macOS.zip` into a temp folder
  (UNPACKED1X) and start it with `REPO/desktop/run-test-build.sh --app
  UNPACKED1X/BitcoinTX.app --fresh --background`. Choose its login as
  MAC-3 does, run `golden_loader.py` with
  `BTCTX_URL=http://127.0.0.1:8766` and that login, and record the
  Dashboard figures, Schedule D 2024 and 2025 and `shasum DATA/mcp.json`
  (never the key itself). Quit it. Start the candidate's app (UNPACKED)
  with the script, without `--fresh`. Expect
  `curl http://127.0.0.1:8766/api/health` with `X.Y.Z` and `"schema":
  "0101"`; `ls DATA/backups` listing one `btctx-pre-2.0-from-0012-….db`;
  the same login; every recorded figure the same; `mcp.json` still
  `-rw-------`, its `shasum` different (a new key at start). Settings,
  open **Connect an AI Assistant**: every command shown runs
  `btctx-mcp==X.Y.Z` under the server name `bitcointx`. Quit it, start it
  again with the script: still one `btctx-pre-2.0-….db` (it migrated
  once). Quit it. For a pre-release the candidate is `BitcoinTX
  Preview.app`, never the same app as 1.2.10's, so the case runs for real
  only at the release: before a beta, run these steps with the Preview to
  check them (the AI setup then `btctx-mcp==2.0.0bN` under
  `bitcointx-preview`).

## BETA: what a tester of an alpha or a beta meets (2.0's pre-releases only)

2.0's pre-releases are GitHub pre-releases, first alphas (`v2.0.0-alpha.N`),
then betas (`v2.0.0-beta.N`; #251's decision 28): never "Latest", never on
Start9's registries, and `uvx btctx-mcp` without a version, the Docker tags
`:latest` and `:main` and the Mac app's download all stay on 1.x. The cases
say "beta"; an alpha's are the same with `alpha` for `beta` (its connector
`2.0.0aN`). Before beta.1, beside Tracks A, B and C, WAY (WAY-3 included)
and REF on its commit's artifacts, run these with the pre-release's own
files (Inputs); before a later one, those of what changed. (Before alpha.1
the gate is CI's full set green on `2.0` and B9's VM trial repeated on that
build: the update over Start9's 1.2.10 and the ways back.) Their names come
from B10a's plan (7.4 of `docs/temp/2.0-accounts.md`, with decision 28's
"BitcoinTX Preview"): a name that differs in the build is a FAIL to report,
not a step to skip.

- **BETA-1** (StartOS VM, from `clean`; needs the second disk and the VM's
  StartOS password) As a tester would: install BitcoinTX from Start9's
  Community Beta registry (`https://community-beta-registry.start9.com`;
  with `start-cli`, `-r` that address; on StartOS 0.4.1 or later, `--trust`
  or Start9 Alpha on, as "On an Apple-silicon Mac" says), do its tasks, start
  it and run `golden_loader.py`; record its version, the Dashboard figures and
  Schedule D 2024 and 2025. Make a StartOS backup of BitcoinTX (BAK-5's
  steps). Sideload the pre-release's `btctx.s9pk`. Expect StartOS to take
  it over Start9's build of 1.x, though our key signed it, not Start9's:
  it updates in place, with UPG-2's and UPG-2b's checks (its log's
  "Migrating …" names the registry's version), and the service page shows
  `2.0.0-beta.N:0`. A refusal is a FAIL (record StartOS's
  words): the beta's way onto a tester's server doesn't work. Expect every
  page of its web app, the login page included, to have the banner
  "BitcoinTX · 2.0.0-beta.N: a test version, not a release" (#670). Then
  back, as WAY-3: uninstall, restore the StartOS backup. Expect the
  version the registry gave, its login, the recorded figures and 14 rows.
  Revert the VM to `clean`.
- **BETA-2** (StartOS VM, from `clean`; from beta.2 on) One pre-release
  to the next: sideload the pre-release before this one, do its tasks,
  run `golden_loader.py`, create an AI key and turn AI access on, add
  Coldcard and Kraken (ACC-3, ACC-4), and record the Dashboard figures,
  Schedule D 2024 and 2025 and `$API/health`. Sideload this pre-release.
  Expect: it updates in place; `$API/health` shows `2.0.0-beta.N`; every
  recorded figure the same; the login and the AI key working; Coldcard and
  Kraken still there; Ledger Review's "Figures that Recalculate Ledger
  would change" absent unless this beta's CHANGELOG section says
  otherwise; and no new `btctx-pre-2.0-….db` (only an update from 1.x
  makes one). At the release (B10b), the same from the last pre-release
  to the release candidate.
- **BETA-3** (a Mac) The pre-release app, "BitcoinTX Preview", only through the
  script (Track C's rules): unpack `BitcoinTX-Preview-macOS.zip` into a temp
  folder (UNPACKED) and start it with `REPO/desktop/run-test-build.sh
  --app "UNPACKED/BitcoinTX Preview.app" --fresh --background`. Expect its
  window, and `curl http://127.0.0.1:8766/api/health` with
  `2.0.0-beta.N`. Expect it to look like a test version (#670): in Finder
  and the Dock its icon has a red PREVIEW band (BitcoinTX's doesn't); a
  banner above the page, "BitcoinTX Preview · 2.0.0-beta.N: a test
  version, apart from your BitcoinTX"; on the login page, "BitcoinTX
  Preview is a separate test app: it starts empty, and BitcoinTX and its
  ledger are still there, as they were."; and `ps -o comm= -p PID` (the
  PID the script printed) ending in `MacOS/BitcoinTX Preview`. Choose its
  login as MAC-3 does. Settings, open **Backup
  & Restore**: Restore from Backup with UPG-1's `golden-1x.btx` and
  `backup-pass-123`. Expect "✅ Database successfully restored. Log in
  again with your current username and password.", then the login page;
  MAC-3's login works; every golden figure; **Wallets, exchanges and
  banks** "1 wallet · 1 exchange · 1 bank". The script sets the folder,
  port and home itself, so the beta's own (its folder `~/Library/Application
  Support/BitcoinTX Preview`, its own port) are B10a's unit tests', not
  checked here: never start the Preview app by itself on a Mac with
  BitcoinTX installed.
- **BETA-4** (with BETA-3's app) The AI setup the pre-release hands out.
  Settings, open **Connect an AI Assistant**. Expect the Setup prompt and
  every command shown (Claude Desktop, Claude Code, Grok Build) to run
  `btctx-mcp==2.0.0bN`, never an unpinned `btctx-mcp` nor 1.x's, under the
  server name `bitcointx-preview` (never `bitcointx`, the installed app's), and
  the prompt to link `v2.0.0-beta.N`'s `AI_SETUP.md`. Tick **Let AI assistants
  use BitcoinTX** and run that connector as MAC-4 does, with
  `MCP="uvx btctx-mcp==2.0.0bN"` and `-e BTCTX_MCP_FILE=DATA/mcp.json`.
  Expect 12 tools, `get_portfolio` matching the dashboard, and no notice
  that the versions differ.
- **BETA-5** (Docker, on your machine) A Docker beta on a new volume,
  with a 1.x backup restored:

  ```bash
  docker volume create btctx-beta
  docker run -d --name btctx-beta -p 127.0.0.1:8793:80 -v btctx-beta:/data ghcr.io/digimonk73/btctx-mcp:v2.0.0-beta.N
  ```

  Expect `curl http://127.0.0.1:8793/api/health` with `2.0.0-beta.N`, and
  above its login page the banner "BitcoinTX · 2.0.0-beta.N: a test
  version, not a release" (#670). Claim it as WAY-6 does (port 8793,
  `docker logs btctx-beta`). Settings,
  open **Backup & Restore**: restore `golden-1x.btx` with
  `backup-pass-123`. Expect the restore's message, then the login page;
  the new login works; every golden figure, and **Wallets, exchanges and
  banks** "1 wallet · 1 exchange · 1 bank". Then `docker rm -f
  btctx-beta` and `docker volume rm btctx-beta`.
- **BETA-6** (a Mac; from beta.2 on, and at the release) A tester keeps
  the ledger they made in the Preview: BitcoinTX's own backup of it,
  restored into the candidate. Only through the script (Track C's rules),
  each app in its own test folder (`BTCTX_TEST_DATA_DIR=<a temp folder>`
  before the script, a different one for each). Unpack the pre-release
  before this one's `BitcoinTX-Preview-macOS.zip` (UNPACKEDPREV) and
  start it with `--fresh`. Choose its login as MAC-3 does, run
  `golden_loader.py` against it, add Coldcard and Kraken (ACC-3, ACC-4),
  and choose coins once as CHO-1 does (the spend saved). Record the
  Dashboard figures, Schedule D 2024 and 2025, and the spend's "Chosen on
  …". Settings, open **Backup & Restore**: Download Encrypted Backup with
  `backup-pass-123`, kept as `preview.btx`. Quit it. Start the candidate's
  app (UNPACKED: a beta's Preview; at the release, `BitcoinTX.app`) in the
  other folder with `--fresh`, and choose its login as MAC-3 does.
  Settings, open **Backup & Restore**: Restore from Backup with
  `preview.btx` and `backup-pass-123`. Expect "✅ Database successfully
  restored. Log in again with your current username and password.", then
  the login page; the candidate's own login works (a restore never brings
  back the backup's); every recorded figure; **Wallets, exchanges and
  banks** with Coldcard and Kraken, Kraken's 1099-DA box as ACC-4 left it;
  the spend still "Chosen on" the same day; and no `btctx-pre-2.0-….db` in
  this folder's `backups` (the backup was 2.0's already). Quit it.

## CB: Community Beta (2.0.0, after Start9 merges)

Once Start9 has merged the release's pull request to their fork, its
build is on the Community Beta registry
(`https://community-beta-registry.start9.com`) beside 1.2.10 on the
Community Registry (`https://community-registry.start9.com`). These are
the updates users make from there, on the VM from `clean`, with the second
disk and the VM's StartOS password. Installing from a registry goes
through StartOS's own Marketplace page if `start-cli` can't read the
registries (with `start-cli`: `-r` the address). On StartOS 0.4.1 or later,
Community Beta's packages are signed only by Start9's community build key:
record what StartOS shows for one, then turn **Start9 Alpha** on for service
packages (System > Trusted keyrings), or use `--trust`.

- **CB-1** 1.2.10 from the Community Registry (Start9's own build),
  updated from Community Beta. Install BitcoinTX from the Community
  Registry, do its tasks, start it and run `golden_loader.py`; record its
  version (`1.2.10:0`), the Dashboard figures and Schedule D 2024 and
  2025. Make a StartOS backup of BitcoinTX (BAK-5's steps). In the
  Marketplace, switch to Community Beta: BitcoinTX's page offers 2.0.0's
  update. Expect, before it downloads, the pre-download alert (its words,
  in English at least; record them). Accept it. Expect Start9's build to
  update in place: UPG-2's and UPG-2b's checks (its log's "Migrating
  1.2.10:0 -> 2.0.0:0", the `btctx-pre-2.0-….db` copy, `"schema":
  "0101"`), every recorded figure the same, and no StartOS task. Then
  back, as WAY-3: uninstall, restore the backup. Expect `1.2.10:0`, its
  login, the recorded figures and 14 rows. Revert the VM to `clean`.
- **CB-2** A tester's beta, sideloaded (our signature), updated from
  Community Beta (Start9's). Sideload the last pre-release's `btctx.s9pk`
  (beta.2's, or a later one), do its tasks, start it and run
  `golden_loader.py`; record its version and the Dashboard figures. In the
  Marketplace's Community Beta, BitcoinTX's page: expect 2.0.0 offered.
  Accept it. Expect it to update in place, every recorded figure the same,
  the login working and no new `btctx-pre-2.0-….db`. If StartOS refuses
  it (another signer), record its words: the testers' note on #532 then
  says to sideload 2.0.0's `btctx.s9pk` from GitHub instead. Revert the
  VM to `clean`.

## REF: the reference ledger and the landing page's pictures (every run)

From the release commit's checkout (REPO), on this computer: no VM or Mac
build needed, and no real data anywhere. LAB is `~/code/btctx-vm-lab`
written out; X.Y.Z is this release, P.Q.R the previous one. The commands
are in docs/TESTING.md, "The reference test ledger" and "The landing
page's pictures".

- **REF-1** The landing page's pictures:
  `make site-shots SITE_SHOTS_DIR=LAB/runs/site-shots-X.Y.Z`. Expect four
  PNGs: `dashboard.png`, `transactions.png` and `reports.png` at 2940 ×
  1734, and `settings.png` about 1730 wide (its height follows the
  **Connect an AI Assistant** section it shows: about 1475 at
  2.0.0-alpha.2). Settings shows
  `btctx-mcp==X.Y.Z` and `~/Library/Application Support/BitcoinTX/mcp.json`.
  The Dashboard's Income & Fees card has every line the app's card has.
  Compare each with DigiMonk73/btctx-site's `img/` (`cmp`) and list which
  changed. A changed picture is not a FAIL: the release's landing-page
  step (AGENTS.md, "Releasing", step 5) publishes them, shown to the owner
  first.
- **REF-2** This release's reference database. Make an empty database with
  the smoke test's login (`scripts/smoke_test.py`, SMOKE_USER and
  SMOKE_PASSWORD): `DATABASE_FILE=LAB/ledgers/reference-vX.Y.Z.db python -m
  backend.cli set-password --username SMOKE_USER --password-stdin`. Store
  the reference ledger's prices in it (from 2.0, #715: the rows valued from a
  stored price take them): `python scripts/seed_ledger.py --store-prices
  LAB/ledgers/reference-vX.Y.Z.db`. Expect "✓ 8 prices stored in …". Serve it
  with no price source saved in it (`BTCTX_SMOKE_PRICE_SOURCE=unset python
  scripts/smoke_test.py --serve 8791 LAB/ledgers/reference-vX.Y.Z.db`, in
  the background) and load the reference ledger with
  `scripts/seed_ledger.py --url http://127.0.0.1:8791 --user SMOKE_USER
  --password-stdin --with-prices`. Expect "✓ 213 transactions loaded into
  http://127.0.0.1:8791 (2023-2026)" (the count in
  `testdata/reference_ledger.json`), with no rows left out. From 2.0 the seed first adds the
  ledger's own accounts through the account API (Coldcard, Jade, Kraken,
  Overseas with its 1099-DA switch off, made as "Offshore", Credit union,
  Savings, Sparrow, Trezor) and stops if one gets another id than the file lists: the
  database must be new, as `set-password` made it. After the rows it
  renames Offshore to Overseas and hides the Jade, as the file lists.
  Stop the server. On a copy:
  `python scripts/reference_figures.py --db <copy> --compare
  testdata/reference_figures.json`. Expect "No figure moved.". Save its
  figures beside it: `python scripts/reference_figures.py --db <copy> >
  LAB/ledgers/reference-vX.Y.Z.json`.
- **REF-3** The previous release's database, upgraded. Copy
  `LAB/ledgers/reference-vP.Q.R.db`, then `DATABASE_FILE=<copy> python -m
  backend.cli migrate` (from 1.x to 2.0 it prints "Database schema: 0012
  -> 0101" and "Copy of the previous database:
  <copy's folder>/backups/btctx-pre-2.0-from-0012-<time>.db") and `python
  scripts/reference_figures.py --db <copy> --compare
  LAB/ledgers/reference-vP.Q.R.json`. Expect no number moved
  (an update leaves stored figures alone; a figure this release adds, which
  the older file lacks, isn't counted); a report's wording may differ where
  the CHANGELOG says it changed. Then `DATABASE_FILE=<copy> python
  -m backend.cli recalculate` and compare again. Expect no difference,
  unless this release's CHANGELOG says a recalculation changes figures:
  then exactly those, and nothing else. BLOCKED when there is no previous
  database (the first is v1.2.7's).
- **REF-4** (from 2.0) An upgraded 1.x ledger's very old rows. B1's
  fixture `backend/tests/fixtures/old_accounts_1x.db` was written by 1.x's
  code: a deposit saved before v0.9.2 into `cold2`, an account made
  through 1.x's account API (id 7), and a deposit naming account 999,
  which doesn't exist. Copy it to a temp folder as `btctx.db`, then
  `DATABASE_FILE=<copy> python -m backend.cli migrate`. Expect "Database
  schema: 0012 -> 0101" and "Copy of the previous database:
  …/backups/btctx-pre-2.0-from-0012-<time>.db". Then
  `DATABASE_FILE=<copy> python -m backend.cli review`. Expect "Ledger
  review (read-only; dates in UTC)", then, in its order:
  - "Transactions naming an account that doesn't exist: 1", its item
    `#6  2024-04-01 12:00  Deposit (MyBTC)  account 999 (missing)
    0.10000000 BTC  Names account 999, which doesn't exist (a BitcoinTX
    before 0.9.2 saved it). It doesn't stop saves.`;
  - "Transactions in an account made through BitcoinTX's old account API:
    1", its item `#4  2024-03-01 12:00  Deposit (MyBTC)  cold2  0.50000000
    BTC  Saved before 0.9.2 into an account made through the old account
    API; 2.0 counts it by that account's currency.`, then "-> BitcoinTX
    1.x left these out of income and some other checks; 2.0 counts them by
    their account's currency, so their figures can differ from your 1.x
    reports. Check each one, and edit it into the right account if needed.
    Saving it, even unchanged, takes it off this list.";
  - "Figures that Recalculate Ledger would change: 0", and every other
    check 0 but "Reminder: My BTC and Gift deposits counted from their
    deposit date: 2" (#1 into Wallet and #4 into cold2).

  `migrate` again: "Database schema is up to date (0101)."

## MAP: the ready-made mappings against real exports (a tester, at 2.0)

Not part of an agent's walk. B5b built every ready-made mapping but
River's (Coinbase, Kraken, Strike, Swan's two, Cash App) from its
exchange's published format, never from a real export, and the screen
says so ("… not yet checked against a real one: check the preview's rows
against your file before you import them."). Before 2.0's release, anyone
who holds a real export of one of them runs MAP-1 for it, on a test
install only (the Preview app through `desktop/run-test-build.sh`, a
throwaway Docker container or the VM), never on their own ledger. The
export stays on their machine: never committed, attached to an issue,
pasted anywhere or given to an AI, and no figure from it is written down.

- **MAP-1** For each mapping a tester can check: Settings, open **Import
  from an exchange**, **Exchange file** that exchange, the file,
  **Preview**. Expect:
  - "N rows in file" equal to the file's data rows, and every row either
    in the preview or named in a warning with its reason ("Row … : left
    out.");
  - each previewed row as the file means it: its date and time (Kraken's,
    Strike's and Swan's in UTC, Cash App's in the zone each date names),
    its type (a buy, a sale, a send as a Transfer or Withdrawal, a receive
    as a Transfer or Deposit, a reward or bitcoin back as a Deposit of its
    source), its bitcoin amount, a buy's dollars before its fee and the
    fee, a sale's dollars and fee, a send's network fee;
  - the unknowns B5b left, each settled one way or the other: Kraken's
    `sale`, `reward` and `conversion` ledger types (left out today, as
    "Kraken's “…” rows, which BitcoinTX doesn't read"); Cash App's
    "Bitcoin Payment" (left out today as a kind the mapping doesn't read);
    Strike's labels for rewards or bitcoin back; whether Swan's and Cash
    App's transaction ids are unique per row (a repeated id is left out:
    "have the id of an earlier row … only the first is read"); the event
    Swan's file names a sale; and whether Coinbase's 2024 file signs
    Quantity Transacted, so that a sale's or a send's bitcoin reads as
    leaving.

  Record each mapping PASS, or FAIL with what differed in words only
  (which kind of row, which column, what was expected). A FAIL becomes a
  public issue labelled `bug` that describes the file's shape, never its
  rows or figures; its fix comes with a made-up row in
  `testdata/exchange_files/` that shows it.

---

## Report

One file per run, `agent-test-report-X.Y.Z.md`:

```markdown
# BitcoinTX X.Y.Z agent test report
Commit: <SHA> · Date: <date> · Agent: <name/model> · StartOS: <version> · VM arch: x86_64
Tracks run: A, B, C, WAY, BETA, REF, MAP (say which were skipped and why)

## Summary
PASS n · FAIL n · KNOWN n · BLOCKED n
Release verdict: GO / NO-GO (NO-GO if any FAIL is a blocker)

## Results
| ID | Result | Observed |
|---|---|---|
| INS-1 | PASS | installed, 1.2.1 |
| GLD-3 | FAIL | Net Short-Term +$8,365.41 (expected +$8,365.40) |
…

## Findings
### F1 (blocker/major/minor): <one line>
Steps: …  Expected: …  Observed: …  Evidence: <screenshot or text>
```

Every FAIL that gets fixed also gets an automated test that fails on the
old code (AGENTS.md), so the next run of this walk has less to catch.

## Known issues

Open bugs a run may meet (the release's CHANGELOG lists them under Known
issues). Report these as KNOWN. Delete a line when its fix is merged into
`develop`, since release candidates are built from it.

None known for 1.2.10 or 2.0.
