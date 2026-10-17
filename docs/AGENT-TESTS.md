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
7. Budget: about 3 hours for Track A, 45 minutes for Track B, 45
   minutes for Track C, and 15 minutes for REF.

## What CI already proves (don't redo)

| Layer | Where | Covers |
|---|---|---|
| ~1,700 unit and integration tests | `make test-fast` | FIFO, fees, proceeds, holding period, tax timezone, 1099-DA boxes, imports, the printed forms read back, auth, AI key, MCP tools |
| Golden years and property tests | `backend/tests/test_golden_years.py`, `test_invariants_property.py` | the hand-worked ledger used below, and random ledgers keeping every invariant |
| Click-through | `frontend/e2e/` (Chromium and WebKit, Chicago and Tokyo) | every transaction type, edit and delete, list, dashboard, River and CSV imports, every report download, Settings, widgets |
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
| Mac app | the same CI run, artifact `BitcoinTX-macOS` (Track C) |
| MCP connector | not on PyPI until the release, so run it from the commit: `uvx --from "git+https://github.com/DigiMonk73/BTCTX-MCP@$SHA#subdirectory=mcp_server" btctx-mcp` |

After the release is published, repeat INS-1 to INS-7 and AI-7 to AI-8
with the published `btctx.s9pk` and `uvx btctx-mcp==X.Y.Z`. That confirms
the published files are the ones you tested.

### The machine

- **StartOS VM** (x86_64, 4 GB RAM or more, a second virtual disk for
  BAK-5). Finish StartOS setup, then snapshot it as `clean`. Tracks A and B
  each start from `clean`.
- **Optional services on the VM:** Tor (PRC-3, PRC-3b). Mempool (PRC-4) needs a
  synced Bitcoin node, so skip it unless the VM has one.
- **Your browser runs in `America/New_York`.** The transaction form reads
  times in the browser's timezone, and the expected figures assume New York.
  With Playwright use `timezoneId: "America/New_York"`; otherwise set the
  OS timezone. AUTH-3 checks it.
- **Tools on your machine:** curl, Python 3.10+, [uv](https://docs.astral.sh/uv/),
  Node 20+ (for the MCP Inspector) and a PDF text extractor such as
  `pdftotext` or pypdf.
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

### The golden ledger

Fourteen transactions over 2023–2025 whose results were worked out by
hand (`backend/tests/test_golden_years.py`). Every USD value is typed in,
including the two BTC fees' values and the income's basis, so the results
don't depend on the market price or on which price source is on.

Enter them in Transactions > **Add transaction**, then **Save
transaction**. **Date & Time** is New York time. Leave any field not
listed at its default.

| # | Date & Time | Transaction Type | Fields | Toast after saving |
|---|---|---|---|---|
| 1 | 2023-01-15 12:00 | Deposit | Account `Bank Account`, Amount `100000` | Transaction created successfully! |
| 2 | 2023-02-01 12:00 | Buy | From Account `Bank (auto-buy)`, Amount USD `23000`, Amount BTC `1` | Transaction created successfully! |
| 3 | 2023-03-01 12:00 | Buy | `Bank (auto-buy)`, Amount USD `12000`, Amount BTC `0.5` | Transaction created successfully! |
| 4 | 2023-06-01 12:00 | Transfer | From Account `Exchange`, From Currency `BTC`, Amount (From) `0.6`, Amount (To) `0.5998`, Fee value (USD) `10`. Check: To Account shows `Wallet`, Fee (BTC) shows `0.0002` | Transaction created successfully! |
| 5 | 2023-09-10 12:00 | Sell | Amount BTC `0.5`, Gross Proceeds (USD) `13000`, Fee (USD) `10` | Transaction created! Realized Gain: +$1,390.00 |
| 6 | 2023-12-31 23:30 | Withdrawal | Account `Bitcoin Wallet`, Amount `0.01`, Purpose `Spent`, Proceeds (USD) `400` | … Realized Gain: +$170.00 |
| 7 | 2024-02-02 12:00 | Sell | Amount BTC `0.3`, Gross Proceeds (USD) `15000` | … Realized Gain: +$7,800.00 |
| 8 | 2024-03-02 12:00 | Sell | Amount BTC `0.1`, Gross Proceeds (USD) `6000` | … Realized Gain: +$3,600.00 |
| 9 | 2024-05-01 12:00 | Deposit | Account `Bitcoin Wallet`, Amount `0.02`, Source `Income`, Cost Basis (USD) `1000` | Transaction created successfully! |
| 10 | 2024-06-01 12:00 | Withdrawal | Account `Bitcoin Wallet`, Amount `0.1`, Purpose `Gift`, FMV (USD) `6700` | Transaction created successfully! |
| 11 | 2025-01-10 12:00 | Buy | `Bank (auto-buy)`, Amount USD `20000`, Amount BTC `0.2` | Transaction created successfully! |
| 12 | 2025-04-01 12:00 | Sell | Amount BTC `0.05`, Gross Proceeds (USD) `4000` | … Realized Gain: −$1,000.00 |
| 13 | 2025-05-01 12:00 | Withdrawal | Account `Bitcoin Wallet`, Amount `0.1`, Purpose `Spent`, Proceeds (USD) `9000` | … Realized Gain: +$6,700.00 |
| 14 | 2025-06-01 12:00 | Withdrawal | Account `Bitcoin Wallet`, Amount `0.01`, Purpose `Spent`, Fee (BTC) `0.0001`, Fee value (USD) `5`, Proceeds (USD) `1000` | … Realized Gain: +$765.00 (the $5 fee comes off the proceeds, #157) |

What each row does: #4 moves lot A's BTC to the Wallet, and its fee is a
disposal. #6 is 04:30 UTC on Jan 1, 2024, but counts in 2023 because the tax
timezone is New York. #8 is sold one day after the one-year anniversary, so
it's long-term. #14's fee is its own disposal.

**Expected figures** (tax timezone `America/New_York`):

| Where | Expected |
|---|---|
| Dashboard > Portfolio Overview | Bank (USD) $45,000.00 · Exchange (USD) $37,990.00 · Exchange (BTC) 0.15000000 BTC · Wallet (BTC) 0.39970000 BTC · Total BTC 0.54970000 BTC · Avg. Cost per BTC $44,993.81 |
| … Unrealized Gains/Losses (needs a price) | (current price − 44,993.81) × 0.5497, within $0.01 |
| Dashboard > Realized Gains/Losses (FIFO) | Short-Term Gains +$9,365.40 · Short-Term Losses −$1,000.00 · Net Short-Term +$8,365.40 · Long-Term Gains +$11,067.70 · Long-Term Losses $0.00 · Net Long-Term +$11,067.70 · Total Net Capital Gains +$19,433.10 |
| Dashboard > Income & Fees | Income (earned) $1,000.00 (0.02000000 BTC) · Interest (earned) $0.00 (0.00000000 BTC) · Rewards (earned) $0.00 (0.00000000 BTC) · Total Income $1,000.00 · Gifts (received) $0.00 (0.00000000 BTC) · Rebates (received) $0.00 (0.00000000 BTC) · Fees (USD) $10.00 · Fees (BTC) 0.00030000 BTC · Total Fees in USD (approx) = 10 + 0.0003 × price |
| Form 8949 2024 (IRS Reports) | Part I, box C: `0.30000000 BTC · 03/01/2023 · 02/02/2024 · 15000.00 · 7200.00 · 7800.00`. Part II, box F: `0.10000000 BTC · 03/01/2023 · 03/02/2024 · 6000.00 · 2400.00 · 3600.00` |
| Schedule D 2024 | line 3: 15000.00 / 7200.00 / 7800.00 · line 10: 6000.00 / 2400.00 / 3600.00 |
| Form 8949 2025 | Part I, box H: `0.05000000 BTC · 01/10/2025 · 04/01/2025 · 4000.00 · 5000.00 · (1000.00)`. Part II, box L, three rows: `0.10000000 BTC · 02/01/2023 · 05/01/2025 · 9000.00 · 2300.00 · 6700.00`, `0.00010000 BTC · 02/01/2023 · 06/01/2025 · 5.00 · 2.30 · 2.70`, `0.01000000 BTC · 02/01/2023 · 06/01/2025 · 995.00 · 230.00 · 765.00` |
| Schedule D 2025 | line 2: 4000.00 / 5000.00 / (1000.00) · line 10: 10000.00 / 2532.30 / 7467.70 |
| Complete Tax Report 2023 (no IRS forms for 2023 in the app) | 1. Summary › Capital gains and losses: Short-term 4 disposals, Proceeds $13,400.00, Cost basis $11,834.60, Net gain $1,565.40; Long-term 0, all $0.00 (the cover's Net capital gain is the same $1,565.40). 2. Capital gains and losses lists, as Proceeds / Cost basis / Gain: 06/01/2023 0.0002 BTC ($10.00 / $4.60 / $5.40), 09/10/2023 0.4 and 0.1 BTC, and 12/31/2023 0.01 BTC ($400.00 / $230.00 / $170.00). 5. Holdings at year end, lot by lot: 0.58980000 BTC at cost $13,565.40 and 0.40000000 BTC at $9,600.00, total 0.98980000 / $23,165.40, "Average cost: $23,404.12 per BTC"; each Market value = quantity × the price the report states, "the price at the hour the tax year ended (2024-01-01 05:00 UTC)" (midnight in New York; "…'s 00:00 UTC price" where there was no hourly price) |
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


def call(method, path, body=None):
    req = urllib.request.Request(URL + path, method=method, headers={"Content-Type": "application/json"},
                                 data=None if body is None else json.dumps(body).encode())
    try:
        with web.open(req) as r:
            return json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path}: {e.code} {e.read().decode()[:300]}")


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

- **INS-1** Sideload `btctx_x86_64.s9pk` (StartOS > Sideload). Expect: it
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
  `ERROR` or `Traceback`.
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
  Settings > Tax Timezone reads "Current: America/New_York": a login adopts
  the browser's timezone while the ledger is empty (#334).
- **AUTH-4** Expect the card "Bitcoin prices" on the Dashboard only (not on
  other pages), nothing chosen, its status line "Not chosen yet: nothing is
  contacted." Choose **Nobody**, then **Use this**. Expect: no page reload,
  the card is gone. Settings > Privacy & Network shows the card with
  **Nobody** chosen, editable, "Fully offline: nothing is contacted.",
  "You chose this on … in the first-run question.", and no "Set in
  StartOS" banner.
- **AUTH-4b** Settings > **About BitcoinTX**. Expect, in order: the
  warning "Important: one wallet, one exchange." with its notice (one
  self-custody wallet and one exchange account; since 2025 the IRS figures
  cost basis wallet by wallet); the disclaimer "BitcoinTX is software, not
  tax, legal or financial advice. …"; "Version X.Y.Z" (the release
  candidate's, as in INS-7); and the links **release notes**, **Report a
  problem**, **open bugs** and **Report it privately**.
- **AUTH-5** Header **Logout**. Expect: the confirm "Are you sure you want
  to log out?", then the login page. Opening `$URL/dashboard` redirects to
  login. Log back in.

### GLD: the golden ledger through the UI (price source Nobody)

- **GLD-1** Enter the 14 golden transactions. Expect: each toast as in
  the table.
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
  - Deposit to `Bitcoin Wallet`, Amount `0.001`, Source
    `Income`, Cost Basis blank. Expect the error to contain "No BTC price is
    stored for 2025-07-01" and "Enter this Income deposit's USD value at
    receipt as its cost basis."
  - Transfer from `Exchange` `BTC`, Amount (From) `0.01`, Amount (To)
    `0.0099`, Fee value (USD) blank. Expect the error to contain "No BTC
    price is stored for 2025-07-01" and "For the network fee".
  - Withdrawal from `Bitcoin Wallet`, `0.001`, `Spent`, Proceeds blank.
    Expect "No BTC price is stored for 2025-07-01".
  - Deposit to `Bitcoin Wallet`, Source `MyBTC`, Cost Basis blank. Expect
    the form to refuse it: "Enter this deposit's cost basis (type 0 if
    unknown)."
  - Sell 5 BTC for `500000`. Expect "Not enough BTC to sell 5.00000000
    BTC".
- **GLD-5** Edit #3 (the 2023-03-01 Buy). Expect: "Edit Transaction", with
  the Transaction Type select disabled. Change Amount USD to `13000` and
  click **Update transaction**. Expect: #5 now Gain +$1,190.00, #7
  +$7,200.00, #8 +$3,400.00. Change it back to `12000`. Expect: #5
  +$1,390.00, #7 +$7,800.00, #8 +$3,600.00. Every edit recalculates the
  whole ledger.
- **GLD-6** Delete #9 (the income deposit). Expect the confirm "Are you
  sure you want to delete this transaction?" and the toast "Transaction
  deleted successfully!". Wallet (BTC) 0.37970000. Re-enter #9, which
  makes it a backdated entry. Expect: every golden figure is back, Wallet
  0.39970000.
- **GLD-6b** Add a Deposit into Exchange BTC, Source **MyBTC**, `0.01` BTC
  on `2025-04-01`, cost basis `500`. Expect a **Date originally acquired**
  field (it isn't there for Income or for a Bank deposit); enter
  `2023-03-14` and save. Edit it: the field shows 03/14/2023 (the date
  entered, #185), and saving the edit unchanged keeps it. Ledger Review shows "Nothing to review." and no
  "Reminder: My BTC and Gift deposits counted from their deposit date". Delete it. Expect:
  every golden figure as before.
- **GLD-6c** A rebate (bitcoin back for spending). Open **Add
  transaction**, Deposit, and pick Account `Bitcoin Wallet`: expect the
  hint "One self-custody wallet: see Settings → About." under it. Switch to
  Account `Exchange`, Currency `BTC`, Source **Rebate**, `0.0001` BTC on `2025-04-01`, cost basis
  `6`, and save. Expect: Exchange (BTC) 0.15010000, and in Income & Fees
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
  "Using these forms" (before 7, "Notes"), for the preparer, with the
  one-wallet line and the disclaimer. RPT-6 checks the values once
  prices are on.

### TZ: tax timezone

- **TZ-1** Settings > Tax Timezone: select `Asia/Tokyo`, then **Save**.
  Expect the toast "Tax timezone set to Asia/Tokyo. Gains were
  recalculated." In Tokyo, #6 falls on Jan 1, 2024 and every other date
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
- **TZ-2** Set it back to `America/New_York`. Expect: every golden figure
  is back.
- **TZ-2b** A date stays the date entered (#185). Add a Deposit into
  Exchange BTC, Source **MyBTC**, `0.01` BTC on `2025-04-01`, cost basis
  `500`, **Date originally acquired** `2023-03-14`. Set the tax timezone
  to `Pacific/Kiritimati`, then edit the deposit: the field still shows
  03/14/2023; save it unchanged. Set the tax timezone back to
  `America/New_York` and edit it again: still 03/14/2023. Delete it.
  Expect: every golden figure as before.

### REV: Ledger Review and Recalculate

- **REV-1** Settings > Ledger Review > **Check again**. Expect: "Nothing to
  review." (no prices stored yet).
- **REV-2** Settings > **Recalculate**. Expect: "Recalculated 14
  transaction(s)." and figures unchanged.
- **REV-3** StartOS action **Recalculate Ledger**, once with the service
  running and once stopped. Expect its warning, then "Ledger Recalculated",
  and figures unchanged afterwards. Start the service again.
- **REV-4** (#255, still Nobody) Add a Withdrawal from Wallet, purpose
  **Gift**, `0.001` BTC, yesterday 12:00, FMV (USD) left blank. Expect: it
  saves, and **Edit** shows FMV blank, no Refresh button beside it, and
  "Its fair market value when it left. Leave blank to use the BTC price
  when that hour began (that day's, where there's no hourly price). Unless
  BitcoinTX already has that hour's price, type it: you chose Nobody."
  (#208: where a blank value's price comes from.) Ledger Review > **Check again** lists it
  under "Gifts, donations and lost coins with a $0 or blank value" ("Value
  blank: the tax report lists it as not given (no price stored for that
  day)."). Delete the gift; Check again: "Nothing to review."

### PRC: price sources

- **PRC-1** While Nobody: the service log has no lines starting "BTC price
  history from" or "Price history from your mempool server".
- **PRC-2** Action **Price Source & Privacy**: choose **Public price
  sites**, with Tor off. Expect: "Price Source Saved" and a service restart.
  Then:
  - Settings > Privacy & Network reads "Set in StartOS. To change it:
    BitcoinTX › Actions › Price Source & Privacy.", with **Public price
    sites** marked "✓ Chosen" (not "Recommended"), no choices to click and no Save button. Its
    status line reads "Newer prices from public price sites. Last price …"
    once the Dashboard has shown a price.
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
  - Ledger Review > **Check again**. Expect exactly one item: "Income and
    rebate values you typed, far from that hour's price: 1", which is #9.
    Its $1,000.00 is made up, so this is correct. Every golden value is
    typed, so "Values priced at the day's price that the hour would
    change" is absent. Any other item is a FAIL.
- **PRC-2b** (#255, right after PRC-2) Add the REV-4 gift again (FMV
  blank). Expect: **Edit** shows its FMV filled, 0.001 × the BTC price when
  that hour began (to the cent), and "From the price: …" naming that hour
  and the price site. Change the amount to `0.002` and save: the FMV
  doubles (± a cent). Type `50` in FMV and save: Edit shows "Typed: you
  typed this value; it's kept as it is." Delete the gift.
- **PRC-2c** (#260, right after PRC-2b) Settings > Tax Timezone: `Asia/Tokyo`,
  **Save**. Expect: the Dashboard's price line ("From public price sites
  (…) · h:mm am/pm") and Settings' "Last price h:mm am/pm" show New York
  time (the browser's timezone), not Tokyo's; the Transactions list's
  times don't move. Ledger Review > **Check again** reads "Dates in
  Asia/Tokyo.": its dates stay in the tax timezone. Set it back to
  `America/New_York` (every golden figure back, as in TZ-2).
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
  Bitstamp is the price history's only site since #161 (and the live
  price's fallback), and PRC-2 already downloaded the history without Tor,
  so check Bitstamp through Tor directly, with Tor on your machine (the
  VM's Tor isn't reachable from it; Bitstamp sees a Tor exit either way):
  `curl -s --socks5-hostname 127.0.0.1:9050
  'https://www.bitstamp.net/api/v2/ticker/btcusd/'` and the same with
  `'https://www.bitstamp.net/api/v2/ohlc/btcusd/?step=86400&limit=2'` each
  return JSON, not a 403.
  Stop Tor, wait a minute (the live price is cached for 60 seconds) and
  reload. Expect the Dashboard price to read "No answer": requests must fail
  rather than go out directly. The sidebar reads "BTC Price: no answer" with
  "Is Tor running?" and **Type a price** (#208). Start Tor: the price is back.
- **PRC-3b** (needs Tor on the VM; right after PRC-3, Tor running) The
  hourly price history's one-time download over real Tor (#144). It was
  only tested with stubs and a direct download while it was built.
  - With the service running (no download runs after PRC-2), remove the
    hourly files: `start-cli package attach btctx -n btctx -- rm -rf
    /data/btc-prices` (they're downloaded again). Restart the service, with
    **Public price sites** and **Use Tor** still
    set.
  - Expect in the service log, newest year first, one line per year:
    "Hourly BTC prices for YYYY from Bitstamp: N hours, checked". Each year
    takes up to a minute.
  - After two or three such lines, stop Tor. Within about 30 seconds expect
    "Hourly BTC prices: the download from Bitstamp failed: …". After that
    line, **no "checked" line may appear until Tor is started and the
    service restarted**: a request must fail rather than go out directly
    (as PRC-3's "No answer"); one then is a blocker FAIL. (A "checked" line
    just before the failed line can be a year that finished as Tor
    stopped.)
  - Start Tor, then restart the service. Expect the download to resume:
    "checked" lines only for the years not yet checked (a year already
    saved is never downloaded again; one cut off part-way is downloaded
    whole), down to 2013.
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
- **PRC-4** (needs Mempool) Action: **My Mempool on this server**.
  Expect: a price and block height, the log line "Price history from
  your mempool server: N days", and in Settings > Privacy & Network **My
  own Mempool** marked "✓ Chosen" and "Recommended" (#208). Without Mempool installed, StartOS shows
  the dependency as missing and the price error says to install and start
  Mempool.
- **PRC-4b** (needs internet, not Mempool) The app's own-mempool path,
  with a public Mempool instance, since the VM can't run Mempool (it needs
  a synced node). Checked 2026-10-12: BitcoinTX's own code gets the price,
  the block height and 939 days of history from it.
  - Action **Price Source & Privacy**: **Decide in BitcoinTX instead**. Then
    Settings > Privacy & Network: **My own Mempool**, address
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
  Still with **Decide in BitcoinTX instead**: in Settings > Privacy &
  Network, **My own Mempool**, address `https://<the VM's LAN IP>` (the
  VM's own StartOS address, by IP: a `.local` name doesn't resolve inside
  the service), fallback off. Save.
  - Expect the status line to say the Mempool's certificate isn't trusted,
    and **Trust this server** to show the server's name, its root
    certificate's name ("… Local Root CA") and a SHA-256 fingerprint.
  - Press it. Expect the certificate check to pass: the status line first
    says "Newer prices will come from your Mempool.", then, within a minute
    or two (after the next live-price request), "Your Mempool didn't answer
    at HH:MM." (StartOS's address isn't a Mempool), not the certificate
    message. The certificate message after
    trusting is a FAIL.
  - **Forget this server's certificate**: the certificate message comes
    back.
  - Afterwards choose **Nobody** in Settings > Privacy & Network, clear the
    address, and save: PRC-5 expects the app's own choice to be Nobody (from
    AUTH-4) and a blank address.
- **PRC-5** Action: **Decide in BitcoinTX instead**. Expect: Settings > Privacy &
  Network is editable again and shows the app's own choice (**Nobody**, from
  AUTH-4). Choose **My own Mempool** and leave the address blank. Expect
  **Save** off, with "Enter your Mempool's address." beside it.
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

- **AI-1** Settings > Connect an AI Assistant. Expect: **Let AI assistants
  use BitcoinTX** unticked, a **Create AI key** button, and the privacy
  warning "Your data goes to the AI's model." with its "More" link.
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
  that run `uvx btctx-mcp==X.Y.Z` with `YOUR_BITCOINTX_AI_KEY`. Settings >
  Setup prompt contains the same version and `$URL` (the connector accepts
  the address with or without `/api`).
- **AI-8** List the connector's tools with the MCP Inspector CLI. In
  Inspector 2.8.0 the server command comes first, then `--`, then the
  Inspector's own options:

  ```bash
  MCP="uvx --from git+https://github.com/DigiMonk73/BTCTX-MCP@$SHA#subdirectory=mcp_server btctx-mcp"
  mcp() { npx -y @modelcontextprotocol/inspector@2.8.0 --cli $MCP -- \
            -e BTCTX_URL=$API -e BTCTX_AI_KEY=$KEY -e BTCTX_CA_BUNDLE=$PWD/ca.crt "$@"; }
  mcp --method tools/list
  ```

  Expect 11 tools: `get_ledger_guide`, `get_portfolio`,
  `list_transactions`, `get_btc_price`, `review_ledger`,
  `preview_transactions`, `add_transactions`, `update_transaction`,
  `delete_transaction`, `recalculate_ledger`, `backup_ledger`. The calls
  below are `mcp --method tools/call --tool-name <name> --tool-arg key=value`
  (a value may be JSON). Any MCP client works; the Inspector is simply the
  scriptable one.
- **AI-9** `get_portfolio`. Expect: balances equal to the Dashboard, and no
  notice that the connector and app versions differ. `list_transactions`
  returns 14 rows. `review_ledger` returns the same item as Ledger Review
  in PRC-2. `get_ledger_guide` returns the guide text.
- **AI-10** `preview_transactions` with
  `transactions=[{"date":"2025-07-01","type":"Buy","amount":"0.01","from_account":"Bank","to_account":"Exchange BTC","cost_basis_usd":"1000","fee_amount":"0","fee_currency":"USD"}]`.
  Expect: status `ready`, the date normalized to `2025-07-01T16:00:00Z`
  (a date alone means noon in the tax timezone), and the ledger still has
  14 rows. Preview a copy of #2 (`"date":"2023-02-01T12:00:00-05:00"`, Buy,
  `1.0`, Bank → Exchange BTC, basis `23000`). Expect: status `duplicate`,
  `matched_transaction_id` = #2's id. Preview it again with
  `"not_a_duplicate_of"` set to that id: status `ready`. Preview it
  without that at `2023-02-01T12:05:00-05:00`: status
  `possible_duplicate`, a warning
  "Same BTC amount as tx #… (Buy 1.00000000 BTC), recorded 5 minutes
  earlier: it may be the same transaction. Saved unless you remove it."
  (#253). Preview an income with its value left out
  (`{"date":"2025-07-01T14:30:00Z","type":"Deposit","amount":"0.001","from_account":"External","to_account":"Wallet","source":"Income"}`).
  Expect `simulated.from_price`: `values` `["cost_basis_usd"]`, `at`
  `2025-07-01T14:00:00Z` with `moment` `hour` (or the day's 00:00 with
  `day`), the price's `source` and `usd_per_btc`, which times 0.001 is the
  filled value (#208). Then `add_transactions` with the first
  row. Expect: it appears in the UI list. Run `update_transaction` with
  `transaction_id=<its id>` and `cost_basis_usd=1100`. Expect: the UI shows
  $1,100.00. `delete_transaction` removes it. Expect: 14 rows and every
  golden figure unchanged.
- **AI-11** `recalculate_ledger`: success, figures unchanged.
  `backup_ledger`: success, naming a file in the app's backups folder.
  `get_btc_price` with `date=2024-05-01`: a price above $0.
- **AI-12** Settings **New key** and confirm. Expect: MCP calls with the
  old key fail with "AI key not accepted: it was replaced or revoked, or
  was copied wrong."; the new key works. **Revoke**: the new key fails the
  same way. **Create AI key** again (use this key from now on), untick AI
  access, and expect calls to fail with "AI access is turned off in
  BitcoinTX Settings.". Tick it again.
- **AI-13** Call `get_portfolio` with `-e BTCTX_PASSWORD=x` added. Expect:
  the call fails with "BitcoinTX no longer uses your password for AI
  access. …", and nothing reaches the app.
- **AI-14** (judgment, optional) In a real AI app (Claude Desktop, Grok or
  LM Studio) set up with the AI-7 configuration, paste: "Bought 0.01 BTC on
  River for $1,000 on July 1 2025, fee $10". Expect: the assistant shows a
  preview and asks before saving; after "yes" the row exists. Ask it to
  delete that row. Report whether it previewed before saving.

### BAK and IMP: backups and imports

- **BAK-1** Settings > Backup & Restore > **Export CSV**. Expect: the file
  `btctx_transactions_<date>.csv`, the header
  `date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency,source,purpose,notes,fee_usd,fmv_usd,broker_reporting,fee_usd_typed,cost_basis_typed,acquired_at,proceeds_typed,price_moment,fmv_typed`
  and 14 rows. #4's `fee_usd` is `10.00` and #14's is `5.00`. The toast "CSV
  export downloaded." appears.
- **BAK-2** Download Encrypted Backup: type `backup-pass-123` in both
  password boxes (hidden as typed), then **Download**. Different entries
  in the two boxes say "The two passwords don't match." and download
  nothing. Expect: the file `bitcoin_backup.btx` and "Backup
  downloaded."
- **IMP-1** Data Management > **Template** and **Instructions**. Expect:
  `btctx_import_template.csv`, whose header is the same as BAK-1's, and
  `BitcoinTX_CSV_Import_Guide.pdf`, which opens.
- **IMP-2** Choose BAK-1's CSV, then **Preview**. Expect it refused on a
  non-empty ledger: "Database has 14 existing transaction(s). Please delete
  all transactions before importing, or start with a fresh database."
- **IMP-3** Round trip. **Delete** (Delete All Transactions). Expect a
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
  listing one `btctx-before-delete-all-….db`. Save this file as
  `fee-account.csv`:

  ```csv
  date,type,amount,from_account,to_account
  2024-01-05T12:00:00Z,Deposit,1,External,BTC Fees
  ```

  Choose it, then **Preview**. Expect it refused at Preview, before any
  Import (#266): "0 valid / 1 total rows", "Row 2 (to_account): Invalid
  account 'btc fees'. Must be one of: Bank, Wallet, Exchange USD, Exchange
  BTC, External." and **Import 0 Transactions** disabled. **Cancel**
  (it clears the chosen file). Then choose BAK-1's CSV again and
  **Preview**. Expect "14 valid / 14 total rows". Click **Import 14 Transactions** and
  confirm. Expect "Successfully imported 14 transaction(s)." and **every
  golden figure**: the file carries the fees' USD values, so nothing is
  priced again.
- **BAK-3** Before restoring, click **New key** and keep the new key (the
  backup holds an older one). **Restore from Backup** with BAK-2's file and
  the password `wrong-pass`. Expect "Failed to restore backup." with the
  ledger unchanged. Then restore with `backup-pass-123`. Expect "✅ Database
  successfully restored. Log in again with your current username and
  password.", then the login page. Log in with the login in use before the
  restore (a restore never brings back the backup's password).
  Expect: every golden figure, and the key made just before the restore
  still works (a restore never brings back an older key).
- **IMP-4** River import. Save this file as `river.csv`:

  ```csv
  Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag
  2026-01-05 12:00:00,25.00,USD,0.00030000,BTC,,,Buy
  2026-02-03 15:30:00,148.50,USD,0.00180000,BTC,1.50,USD,Buy
  2026-02-10 16:00:00,0.00050000,BTC,55.00,USD,0.55,USD,Sell
  ```

  Settings > Import from River > River CSV file, then **Preview**. Expect:
  "3 new", "3 rows in file", and each Buy row showing the **Bank** /
  **Exchange USD** toggle. Click **Import 3 Transaction(s)** and confirm
  "Import 3 transaction(s) from River into your ledger?". Expect "Imported 3
  transaction(s)." The Sell shows Gain +$5.00 (net proceeds $55.00 = River's
  $55.00 received, which is after River's $0.55 fee; basis 0.0005 × $100,000
  from lot C). Preview the same file again. Expect: "3 already in ledger" and
  "0 new". Click **Show 3 already-imported row(s)**. Expect each row's
  Import box unticked but clickable, and "Tick one to import it anyway, if
  it's another transaction." (#253). Leave them unticked and **Cancel**.
  Preview the file with its first row's time changed to `2026-01-06
  09:00:00`. Expect "2 already in ledger", "1 need review" and that row
  ticked, its note "Same BTC amount as tx #… (Buy 0.00030000 BTC),
  recorded 21 hours earlier: it may be the same transaction". **Cancel**.
- **IMP-5** Preview a CSV that isn't a River export, for example
  `date,type,amount` plus one row. Expect "This does not look like a River
  bitcoin-activity CSV. Missing columns: …".
- **BAK-4** Restore BAK-2's backup again, which removes the River rows.
  Expect every golden figure.

### SEC: the live install from outside

- **SEC-1** Without a session, `curl --cacert ca.crt -o /dev/null -w "%{http_code}"`
  on `$API/transactions`, `$API/settings/network` and `$API/reports/years`.
  Expect: 401 for each.
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
  - with neither header: expect 200.

  Then `POST $API/logout` with `-b jar` (no `-c`, so the jar keeps the
  cookie) and `GET $API/transactions` with it again. Expect: 401 (logging
  out ends that session, for every copy of its cookie), while the app in
  the browser, a session of its own, stays logged in.
- **SEC-6** `GET $API/users/setup-status`. Expect `setup_code_required`
  false.
- **SEC-7** While using the app, record the browser's network requests
  (Playwright `page.on("request")` or devtools). Expect: every request goes
  to `$URL`'s own origin, with no fonts, CDNs or analytics.
- **SEC-8** Password rules (Settings > Account > Reset Username &
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

- **BAK-5** (needs the second virtual disk) Create a StartOS backup of
  BitcoinTX, then uninstall BitcoinTX (its data goes with it). Restore it
  from the backup. Expect: no Set Login Credentials task; the service
  starts; the LCK-2 password logs in; every golden figure; Tax Timezone
  America/New_York; the price source as PRC-6 left it; the AI key from BAK-3
  still works.

### EXP: exploratory (30 minutes)

Use the app as a new owner would, looking for anything wrong: wording that
contradicts itself or the docs (`startos/instructions.md`, `README.md`),
layout broken at phone width (375 px) and at 1440 px, keyboard-only use,
double-clicks on Save, very long or odd input (emoji, 21,000,000 BTC,
negative numbers, far-future dates), and the back button mid-flow. Report
each finding with steps, what you expected and what happened, and a
severity: blocker (wrong tax figure, data loss, security), major, or minor.

### END: destructive checks, then uninstall

- **END-1** Delete #2 (the 2023-02-01 Buy that #4, #5 and #6 depend on).
  Expect it refused with "Failed to delete transaction: Not deleted: later
  transactions depend on this one. Not enough BTC to transfer 0.60000000
  (including fee 0.00020000)", and the ledger unchanged: 14 rows and every
  golden figure. Then add a $1 deposit to `Bank Account` and delete it.
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
  `fresh` shows an empty ledger.
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
  figures, and the output of `curl $API/health`.
- **UPG-2** Sideload `btctx_x86_64.s9pk` over it. Expect: it updates in
  place, starts healthy, and `$API/health` shows `X.Y.Z` and its
  schema. The same login works; from 1.2.8, the browser shows the login
  page once first (every session from before the update ends, #221). Every UPG-1 figure is identical. The AI key
  still works. Any tasks raised are only the ones this release's CHANGELOG
  entry announces. If StartOS refuses the update because the CI package's
  signing key differs from the release's, mark UPG BLOCKED and run it after
  the release with the published `btctx.s9pk`.
- **UPG-3** Ledger Review. Expect "Figures that Recalculate Ledger would
  change" to be absent (count 0), unless this release's CHANGELOG says a
  recalculation changes figures. Then its items must be exactly the ones
  described there.
- **UPG-4** (optional) Sideload the previous release over the new one.
  Expect: refused, or a service that won't start with "database schema is
  …" in its health check. Record which. Sideload the new one again and
  expect every figure intact.
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
- **UPG-6** (#145, confirm once) A pass of its own, after UPG-5: restore
  the VM's `clean` snapshot, sideload the previous release (1.2.7) and set
  its login as in UPG-1. Under 1.2.7: action **Choose in BitcoinTX**, then
  in the app Settings > Privacy & Network choose **Public price sites** and
  save. Sideload the candidate and log in. Expect on the Dashboard the card "Please confirm where
  BitcoinTX gets prices", **Public price sites** selected with "Your
  current choice", its status line "Waiting for you to confirm: nothing is
  contacted until you do.", Current Bitcoin Price "Confirm your choice",
  and the sidebar "waiting for you". The service log has no new line
  starting "BTC price history from", "Latest BTC prices from" or "Hourly
  BTC prices" before you confirm. Press **Confirm**: the card goes away without a reload and a
  price appears. Restart the service: not asked again. Settings shows
  "You chose this on … in the first-run question." Set the action back to
  **Public price sites**.
- **UPG-7** (#145, the package asks once) A pass of its own: restore the
  VM's `clean` snapshot, sideload the previous release (1.2.7), set its
  login as in UPG-1, start it, and never run **Price Source & Privacy**.
  Sideload the candidate. Expect the task **Price Source & Privacy**,
  important (not critical): "Prices are now hourly. Check who BitcoinTX
  asks for newer ones.", and beside it 1.2.8's **Recalculate Ledger**
  (important). The service keeps running. Dismiss both tasks (`start-cli
  package action clear-task btctx choose-price-source`, then
  `recalculate-after-0.8.0`), then restart the service and the server:
  neither comes back (#365).
- **UPG-8** (#143, a beta user may skip a release) A pass of its own:
  restore the VM's `clean` snapshot, sideload the published 1.2.5:0
  (`btctx.s9pk` of the v1.2.5 GitHub release), set it up as in UPG-1 (its
  action may name the choices differently), then sideload the candidate.
  Expect UPG-2 and UPG-3 to hold from 1.2.5:0: it updates in place, every
  recorded figure is identical, the login and the AI key still work. UPG-3's
  exceptions are the CHANGELOG entries of 1.2.6, 1.2.7 and this release.

## Track C: the Mac app (only on a Mac)

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
- **MAC-4** Settings > Connect an AI Assistant. Expect: **Reset key**
  instead of Create, and no "No AI key yet" line (#238: the app wrote its
  key at start); the Setup prompt says no key or address is needed; and
  a "Grok Build command" box. Tick **Let AI assistants use BitcoinTX**,
  then run the connector with no settings at all (as in AI-8, but with
  nothing after `--` except the method options; on a Mac with BitcoinTX
  installed, plus `-e BTCTX_MCP_FILE=DATA/mcp.json`, as above). Expect: 11 tools, and
  `get_portfolio` matches the Dashboard. **Reset key**: the connector keeps
  working (it re-reads `mcp.json`).
- **MAC-5** Quit and reopen within 5 seconds. Expect: the same port and no
  banner. Opening it again while it's open brings the window forward, with
  no second copy. With the MCP Inspector (or an AI app) left open across the
  quit and reopen, its next call still works: `mcp.json` has a new key and
  the connector picks it up by itself.
- **MAC-6** Quit, reopen and log in. Expect: the data is still there.
- **MAC-7** Your own mempool server, as PRC-4b. Settings > Privacy &
  Network: **My own Mempool**, `https://mempool.emzy.de`, fallback off,
  save. Expect the Dashboard's price and block height. Then the Sats
  Converter's **Date** mode on a past day. Expect a price, and in
  `DATA/logs/run-test-build.out` "Price history from your mempool server:
  N days" with N in the hundreds (only if no daily price was stored yet:
  this build has asked no public site). Set it back to **Nobody** and clear
  the address.

## REF: the reference ledger and the landing page's pictures (every run)

From the release commit's checkout (REPO), on this computer: no VM or Mac
build needed, and no real data anywhere. LAB is `~/code/btctx-vm-lab`
written out; X.Y.Z is this release, P.Q.R the previous one. The commands
are in docs/TESTING.md, "The reference test ledger" and "The landing
page's pictures".

- **REF-1** The landing page's pictures:
  `make site-shots SITE_SHOTS_DIR=LAB/runs/site-shots-X.Y.Z`. Expect four
  PNGs: `dashboard.png`, `transactions.png` and `reports.png` at 2940 ×
  1734, and `settings.png` at about 1730 × 1570. Settings shows
  `btctx-mcp==X.Y.Z` and `~/Library/Application Support/BitcoinTX/mcp.json`.
  The Dashboard's Income & Fees card has every line the app's card has.
  Compare each with DigiMonk73/btctx-site's `img/` (`cmp`) and list which
  changed. A changed picture is not a FAIL: the release's landing-page
  step (AGENTS.md, "Releasing", step 5) publishes them, shown to the owner
  first.
- **REF-2** This release's reference database. Make an empty database with
  the smoke test's login (`scripts/smoke_test.py`, SMOKE_USER and
  SMOKE_PASSWORD): `DATABASE_FILE=LAB/ledgers/reference-vX.Y.Z.db python -m
  backend.cli set-password --username SMOKE_USER --password-stdin`. Serve it
  with no price source saved in it (`BTCTX_SMOKE_PRICE_SOURCE=unset python
  scripts/smoke_test.py --serve 8791 LAB/ledgers/reference-vX.Y.Z.db`, in
  the background) and load the reference ledger with
  `scripts/seed_ledger.py --url http://127.0.0.1:8791 --user SMOKE_USER
  --password-stdin`. Expect "111 transactions loaded" (or the count in
  `testdata/reference_ledger.json`). Stop the server. On a copy:
  `python scripts/reference_figures.py --db <copy> --compare
  testdata/reference_figures.json`. Expect "No figure moved.". Save its
  figures beside it: `python scripts/reference_figures.py --db <copy> >
  LAB/ledgers/reference-vX.Y.Z.json`.
- **REF-3** The previous release's database, upgraded. Copy
  `LAB/ledgers/reference-vP.Q.R.db`, then `DATABASE_FILE=<copy> python -m
  backend.cli migrate` and `python scripts/reference_figures.py --db <copy>
  --compare LAB/ledgers/reference-vP.Q.R.json`. Expect no number moved
  (an update leaves stored figures alone; a figure this release adds, which
  the older file lacks, isn't counted); a report's wording may differ where
  the CHANGELOG says it changed. Then `DATABASE_FILE=<copy> python
  -m backend.cli recalculate` and compare again. Expect no difference,
  unless this release's CHANGELOG says a recalculation changes figures:
  then exactly those, and nothing else. BLOCKED when there is no previous
  database (the first is v1.2.7's).

---

## Report

One file per run, `agent-test-report-X.Y.Z.md`:

```markdown
# BitcoinTX X.Y.Z agent test report
Commit: <SHA> · Date: <date> · Agent: <name/model> · StartOS: <version> · VM arch: x86_64
Tracks run: A, B, C, REF (say which were skipped and why)

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

Found while this document was written (v1.2.0). Report these as KNOWN.
Delete a line when its fix is merged into `develop`, since release
candidates are built from it.

None at present.
