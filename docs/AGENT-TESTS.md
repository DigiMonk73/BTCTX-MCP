# Agent release tests

What an AI agent (or a person) runs on a real install before each release:
the packaged app on a StartOS VM, driven through its web UI, its StartOS
actions and a real MCP client, against a ledger whose every figure is known
in advance. Point the agent at this file and give it the inputs under
[Setup](#setup).

CI already tests the tax engine, every form, every transaction type and
the whole UI on every push (see below). This walk tests what CI can't
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
7. Budget: about 3 hours for Track A, 45 minutes for Track B, and 45
   minutes for Track C.

## What CI already proves (don't redo)

| Layer | Where | Covers |
|---|---|---|
| ~650 unit and integration tests | `make test-fast` | FIFO, fees, proceeds, holding period, tax timezone, 1099-DA boxes, imports, auth, AI key, MCP tools |
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
- **Optional services on the VM:** Tor (PRC-3). Mempool (PRC-4) needs a
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
| 10 | 2024-06-01 12:00 | Withdrawal | Account `Bitcoin Wallet`, Amount `0.1`, Purpose `Gift` | Transaction created successfully! |
| 11 | 2025-01-10 12:00 | Buy | `Bank (auto-buy)`, Amount USD `20000`, Amount BTC `0.2` | Transaction created successfully! |
| 12 | 2025-04-01 12:00 | Sell | Amount BTC `0.05`, Gross Proceeds (USD) `4000` | … Realized Gain: −$1,000.00 |
| 13 | 2025-05-01 12:00 | Withdrawal | Account `Bitcoin Wallet`, Amount `0.1`, Purpose `Spent`, Proceeds (USD) `9000` | … Realized Gain: +$6,700.00 |
| 14 | 2025-06-01 12:00 | Withdrawal | Account `Bitcoin Wallet`, Amount `0.01`, Purpose `Spent`, Fee (BTC) `0.0001`, Fee value (USD) `5`, Proceeds (USD) `1000` | … Realized Gain: +$770.00 |

What each row does: #4 moves lot A's BTC to the Wallet, and its fee is a
disposal. #6 is 04:30 UTC on Jan 1, 2024, but counts in 2023 because the tax
timezone is New York. #8 is sold one day after the one-year anniversary, so
it's long-term. #14's fee is its own disposal.

**Expected figures** (tax timezone `America/New_York`):

| Where | Expected |
|---|---|
| Dashboard > Portfolio Overview | Bank (USD) $45,000.00 · Exchange (USD) $37,990.00 · Exchange (BTC) 0.15000000 BTC · Wallet (BTC) 0.39970000 BTC · Total BTC 0.54970000 BTC · Avg. Cost per BTC $44,993.81 |
| … Unrealized Gains/Losses (needs a price) | (current price − 44,993.81) × 0.5497, within $0.01 |
| Dashboard > Realized Gains/Losses (FIFO) | Short-Term Gains +$9,365.40 · Short-Term Losses −$1,000.00 · Net Short-Term +$8,365.40 · Long-Term Gains +$11,072.70 · Long-Term Losses $0.00 · Net Long-Term +$11,072.70 · Total Net Capital Gains +$19,438.10 |
| Dashboard > Income & Fees | Income (earned) $1,000.00 (0.02000000 BTC) · Interest and Rewards $0.00 · Total Income $1,000.00 · Gifts (received) $0.00 · Fees (USD) $10.00 · Fees (BTC) 0.00030000 BTC · Total Fees in USD (approx) = 10 + 0.0003 × price |
| Form 8949 2024 (IRS Reports) | Part I, box C: `0.30000000 BTC · 03/01/2023 · 02/02/2024 · 15000.00 · 7200.00 · 7800.00`. Part II, box F: `0.10000000 BTC · 03/01/2023 · 03/02/2024 · 6000.00 · 2400.00 · 3600.00` |
| Schedule D 2024 | line 3: 15000.00 / 7200.00 / 7800.00 · line 10: 6000.00 / 2400.00 / 3600.00 |
| Form 8949 2025 | Part I, box H: `0.05000000 BTC · 01/10/2025 · 04/01/2025 · 4000.00 · 5000.00 · -1000.00`. Part II, box L, three rows: `0.10000000 BTC · 02/01/2023 · 05/01/2025 · 9000.00 · 2300.00 · 6700.00`, `0.00010000 BTC · 02/01/2023 · 06/01/2025 · 5.00 · 2.30 · 2.70`, `0.01000000 BTC · 02/01/2023 · 06/01/2025 · 1000.00 · 230.00 · 770.00` |
| Schedule D 2025 | line 2: 4000.00 / 5000.00 / -1000.00 · line 10: 10005.00 / 2532.30 / 7472.70 |
| Complete Tax Report 2023 (no IRS forms for 2023 in the app) | Capital Gains Summary, Short Term: Number of Disposals 4, Proceeds from Sales $13,400.00, Acquisition Costs $11,834.60, Net Gains $1,565.40; Long Term all $0.00. The disposals list has 06/01/2023 0.0002 BTC ($4.60 / $10.00 / $5.40), 09/10/2023 0.4 and 0.1 BTC, and 12/31/2023 0.01 BTC ($230.00 / $400.00 / $170.00). End of Year Balances: 0.58980000 BTC at cost $13,565.40 and 0.40000000 BTC at $9,600.00, total 0.98980000 / $23,165.40, Avg Cost Basis $23,404.12 per BTC; each Value = quantity × the Dec 31 price the report states |
| Complete Tax Report 2024 | Beginning of Year Holdings: 0.98980000 BTC, Avg Cost Basis $23,404.12 (the same BTC as the 2023 report's End of Year Balances). Income Summary: Income $1,000.00, Total $1,000.00. Income Transactions: 05/01/2024 0.02000000 BTC $1,000.00. Gifts, Donations & Lost Assets: 06/01/2024 0.10000000 BTC, FMV "not given", Gift. End of Year Balances: 0.48980000 BTC at $11,265.40 and 0.02000000 BTC at $1,000.00, total 0.50980000 / $12,265.40 |
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
    {"type": "Withdrawal", "timestamp": "2024-06-01T16:00:00Z", "from_account_id": 2, "to_account_id": 99, "amount": "0.1", "fee_amount": "0", "fee_currency": "BTC", "purpose": "Gift"},
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
call("PUT", "/api/settings/tax-timezone", {"timezone": "America/New_York"})
for tx in LEDGER:
    call("POST", "/api/transactions", tx)
print(len(call("GET", "/api/transactions")), "transactions loaded; tax timezone America/New_York")
```

---

## Track A: fresh install of the release candidate

Start from the `clean` snapshot.

### INS: install

- **INS-1** Sideload `btctx_x86_64.s9pk` (StartOS > Sideload). Expect: it
  installs, and the service page shows version `X.Y.Z`. The install shows the
  phase "Creating the BitcoinTX database".
- **INS-2** Expect two tasks: **Show Credentials** (critical) and **Price
  Source & Privacy** (important).
- **INS-3** Run **Show Credentials**. Expect: title "Login Credentials",
  username `admin`, a 24-character password. The critical task clears.
  Record the password.
- **INS-4** Run **Price Source & Privacy**. Choose **Choose in BitcoinTX
  (Settings > Privacy & Network)** and leave both toggles off. Expect: "Price
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
  Settings > Tax Timezone reads "Current: America/New_York": the first login
  adopts the browser's timezone.
- **AUTH-4** Expect the panel "Where should BitcoinTX get Bitcoin prices?"
  on every page. Choose **Off**, then **Use this**. Expect: the page
  reloads and the panel is gone. Settings > Privacy & Network shows Price
  source **Off**, with the fields editable and no "Set by your server" note.
- **AUTH-5** Header **Logout**. Expect: the confirm "Are you sure you want
  to log out?", then the login page. Opening `$URL/dashboard` redirects to
  login. Log back in.

### GLD: the golden ledger through the UI (price source Off)

- **GLD-1** Enter the 14 golden transactions. Expect: each toast as in
  the table.
- **GLD-2** Transactions list. Expect: 14 rows, grouped by day, newest
  first under **Sort by date**. **Last added** puts #14 first. Items per page
  `10` gives "Page 1 of 2", and **Next »** / **« Prev** move between the
  pages. The group **Dec 31, 2023** holds #6 as "Withdrawal · Wallet",
  "11:30 PM · Spent", "Gain +$170.00 · +73.91% · Short-term".
- **GLD-3** Dashboard. Expect: the Portfolio, Realized and Income & Fees
  figures above. Current Bitcoin Price reads "Prices off". Total Fees reads
  "N/A" (label "Total Fees in USD").
- **GLD-4** Without prices, try to add each of these, all dated 2025-07-01
  12:00. Expect each to be refused, with the transaction count still 14:
  - Deposit to `Bitcoin Wallet`, Amount `0.001`, Source
    `Income`, Cost Basis blank. Expect the error to contain "No BTC price is
    stored for 2025-07-01" and "Enter this Income deposit's USD value at
    receipt as its cost basis."
  - Transfer from `Exchange` `BTC`, Amount (From) `0.01`, Amount (To)
    `0.0099`, Fee value (USD) blank. Expect the error to contain "No BTC
    price is stored for 2025-07-01" and "for the network fee".
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
- **GLD-7** Open **Add transaction**, type an Amount, then click outside the
  panel. Expect: "Discard changes?". **Go back** keeps the panel; **Discard
  changes** closes it with nothing saved.

### RPT: reports (price source Off)

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
- **RPT-4** Transaction History for 2023, 2024 and 2025. Expect the files
  `TransactionHistory_<year>.csv` with 6, 4 and 4 data rows.
- **RPT-5** Complete Tax Report 2023 and 2024, with Off and no stored
  prices. Expect: both generate. Every holdings value (Beginning of Year
  and End of Year) reads "not priced", with the note "No BTC price for
  YYYY-12-31: not priced" (and for 2024 "No BTC price is stored for
  2024-01-01, so the holdings aren't valued …"). Never $0.00. Every other
  figure is as in the expected-figures table. RPT-6 checks the values once
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
  - Dashboard Total Net Capital Gains still +$19,438.10.
- **TZ-2** Set it back to `America/New_York`. Expect: every golden figure
  is back.

### REV: Ledger Review and Recalculate

- **REV-1** Settings > Ledger Review > **Check again**. Expect: "Nothing to
  review." (no prices stored yet).
- **REV-2** Settings > **Recalculate**. Expect: "Recalculated 14
  transaction(s)." and figures unchanged.
- **REV-3** StartOS action **Recalculate Ledger**, once with the service
  running and once stopped. Expect its warning, then "Ledger Recalculated",
  and figures unchanged afterwards. Start the service again.

### PRC: price sources

- **PRC-1** While Off: the service log has no lines starting "BTC price
  history from" or "Price history from your mempool server".
- **PRC-2** Action **Price Source & Privacy**: choose **Public price
  sites**, with Tor off. Expect: "Price Source Saved" and a service restart.
  Then:
  - Settings > Privacy & Network reads "Set by your server: on StartOS,
    change them with the Price Source & Privacy action on BitcoinTX's
    service page." with the inputs disabled and no Save button.
  - Dashboard: a price above $0 and "Block Height: N" with N > 900,000.
    Unrealized Gains/Losses and Total Fees (approx) match the formulas in
    the expected-figures table.
  - The service log has a line "BTC price history from public site …: N
    days".
  - Repeat the first GLD-4 deposit (Income, blank basis). Expect: saved
    with Cost Basis = 0.001 × that day's price, where the Sats Converter's
    **Date** mode shows the price for 2025-07-01. Delete it.
  - The Complete Tax Report now values the holdings (RPT-6).
  - Ledger Review > **Check again**. Expect exactly one item: "Income
    deposits valued far from that day's price: 1", which is #9. Its
    $1,000.00 is made up, so this is correct. Any other item is a FAIL.
- **RPT-6** Complete Tax Report 2023 and 2024. Expect the values in the
  expected-figures table.
- **WID-1** The sidebar widgets. Sats Converter **Auto** shows the
  dashboard's price. **Manual** with `50000`: USD `100` gives BTC `0.002` and
  Sats `200000`. Calculator: `7 * 6 =` shows `42`, and **C** clears it.
- **PRC-3** (needs Tor on the VM) Action: **Public price sites** plus
  **Reach public price sites over Tor**. Expect: a price on the Dashboard.
  Stop Tor, wait a minute (the live price is cached for 60 seconds) and
  reload. Expect the Dashboard price to read "Error": requests must fail
  rather than go out directly. Start Tor: the price is back.
- **PRC-4** (needs Mempool) Action: **My Mempool on this server**.
  Expect: a price and block height, and the log line "Price history from
  your mempool server: N days". Without Mempool installed, StartOS shows
  the dependency as missing and the price error says to install and start
  Mempool.
- **PRC-5** Action: **Choose in BitcoinTX**. Expect: Settings > Privacy &
  Network is editable again and shows the app's own choice (**Off**, from
  AUTH-4). Choose **My mempool server** with the address blank and save.
  Expect it refused: "Enter your mempool server's address to use it."
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
  Setup prompt contains the same version and `$API`.
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
  `matched_transaction_id` = #2's id. Then `add_transactions` with the first
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
  `date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency,source,purpose,notes,fee_usd,fmv_usd,broker_reporting`
  and 14 rows. #4's `fee_usd` is `10.00` and #14's is `5.00`. The toast "CSV
  export downloaded." appears.
- **BAK-2** **Download** (Download Encrypted Backup) with the password
  `backup-pass-123`. Expect: the file `bitcoin_backup.btx` and "Backup
  downloaded."
- **IMP-1** Data Management > **Template** and **Instructions**. Expect:
  `btctx_import_template.csv`, whose header is the same as BAK-1's, and
  `BitcoinTX_CSV_Import_Guide.pdf`, which opens.
- **IMP-2** Choose BAK-1's CSV, then **Preview**. Expect it refused on a
  non-empty ledger: "Database has 14 existing transaction(s). Please delete
  all transactions before importing, or start with a fresh database."
- **IMP-3** Round trip. **Delete** (Delete All Transactions), accepting
  "Delete ALL transactions? This cannot be undone.". Expect "All
  transactions deleted." and an empty Dashboard. Then Preview BAK-1's CSV.
  Expect "14 valid / 14 total rows". Click **Import 14 Transactions** and
  confirm. Expect "Successfully imported 14 transaction(s)." and **every
  golden figure**: the file carries the fees' USD values, so nothing is
  priced again.
- **BAK-3** Before restoring, click **New key** and keep the new key (the
  backup holds an older one). **Restore from Backup** with BAK-2's file and
  the password `wrong-pass`. Expect "Failed to restore backup." with the
  ledger unchanged. Then restore with `backup-pass-123`. Expect "✅ Database
  successfully restored. Please log in again.", then the login page. Log in.
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
  "0 new".
- **IMP-5** Preview a CSV that isn't a River export, for example
  `date,type,amount` plus one row. Expect "This does not look like a River
  bitcoin-activity CSV. Missing columns: …".
- **BAK-4** Restore BAK-2's backup again, which removes the River rows.
  Expect every golden figure.

### SEC: the live install from outside

- **SEC-1** Without a session, `curl --cacert ca.crt -o /dev/null -w "%{http_code}"`
  on `$API/transactions`, `$API/settings/network` and `$API/reports/years`.
  Expect: 401 for each.
- **SEC-2** `$URL/docs` and `$URL/openapi.json`. Expect: 404.
- **SEC-3** `curl --cacert ca.crt -sI $URL/`. Expect these headers:
  `content-security-policy` (including `frame-ancestors 'none'`),
  `referrer-policy: no-referrer`, `x-content-type-options: nosniff`,
  `x-frame-options: DENY`.
- **SEC-4** Log in with curl:
  `curl --cacert ca.crt -si -c jar -X POST $API/login -H 'Content-Type: application/json' -d '{"username":"…","password":"…"}'`.
  Expect: `set-cookie: btc_session_id=…` with the attributes `HttpOnly`,
  `SameSite=lax` and `Secure`, in any letter case (StartOS serves over
  HTTPS).
- **SEC-5** With that cookie (`-b jar`), `POST $API/transactions/recalculate`:
  - with `-H 'Sec-Fetch-Site: cross-site'`: expect 403;
  - with `-H 'Origin: https://evil.example'`: expect 403;
  - with neither header: expect 200.
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
  `tester`. **Show Credentials** still shows `admin` and the generated
  password: stale, as documented.
- **SEC-9** Last in Track A's security checks, because it makes you wait:
  send wrong passwords to `$API/login` in quick succession, at most eight.
  Expect: from the sixth or seventh on, HTTP 429 with a `Retry-After`
  header and "Too many failed attempts. Try again in N second(s).". After
  waiting that long, the correct login works.

### LCK: locked out

- **LCK-1** With the service running, expect **Reset Login Credentials**
  unavailable: it runs only while stopped.
- **LCK-2** Stop the service, run **Reset Login Credentials** (read its
  warning), and expect "Credentials Reset". Start the service. Expect:
  Show Credentials gives `admin` and a new password; `tester` no longer
  logs in; `admin` with the new password does; every golden figure is
  intact.

### BAK (StartOS backup)

- **BAK-5** (needs the second virtual disk) Create a StartOS backup of
  BitcoinTX, then uninstall BitcoinTX (its data goes with it). Restore it
  from the backup. Expect: the service starts; Show Credentials gives the
  LCK-2 password, which logs in; every golden figure; Tax Timezone
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
- **END-2** Log out, then on the login page click **Create account**.
  Expect: a **Current Password** field and no Setup Code. Enter a new
  username `fresh`, a 12+ character password and the current password.
  Expect the confirm "Warning: The account is already registered.
  Re-registering will delete all transactions and update your credentials.
  Proceed?", then "Registration successful! Your credentials have been
  updated.". Logging in as `fresh` shows an empty ledger.
- **END-3** Uninstall BitcoinTX and revert the VM to `clean`.

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
  schema. The same login works. Every UPG-1 figure is identical. The AI key
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

## Track C: the Mac app (only on a Mac)

- **MAC-1** Open `BitcoinTX-macOS.dmg`, drag the app to Applications and
  open it: Control-click > Open, or on macOS 15+ System Settings > Privacy
  & Security > **Open Anyway**. Expect: the app window with BitcoinTX, and
  no port banner.
- **MAC-2** `curl http://127.0.0.1:8765/api/health`. Expect: version
  `X.Y.Z`. `ls -l ~/Library/Application\ Support/BitcoinTX/` shows
  `btctx.db` and `mcp.json`, and `mcp.json` is `-rw-------`.
- **MAC-3** On the Sign in page, click **Create account**. Expect "Register
  account" with New Username and New Password, and no Setup Code or Current
  Password field. Set username `mac-tester` and password
  `mac-tester-pass-1`, confirm, log in, and run `golden_loader.py` with
  `BTCTX_URL=http://127.0.0.1:8765` and those credentials. Expect: the
  golden Dashboard figures. IRS Reports 2025 **Export** opens a save
  dialog, then "Saved to: <path>", and the PDF matches the 2025 figures.
- **MAC-4** Settings > Connect an AI Assistant. Expect: **Reset key**
  instead of Create; the Setup prompt says no key or address is needed; and
  a "Grok Build command" box. Tick **Let AI assistants use BitcoinTX**,
  then run the connector with no settings at all (as in AI-8, but with
  nothing after `--` except the method options). Expect: 11 tools, and
  `get_portfolio` matches the Dashboard. **Reset key**: the connector keeps
  working (it re-reads `mcp.json`).
- **MAC-5** Quit and reopen within 5 seconds. Expect: the same port and no
  banner. Opening it again while it's open brings the window forward, with
  no second copy.
- **MAC-6** Quit, reopen and log in. Expect: the data is still there.

---

## Report

One file per run, `agent-test-report-X.Y.Z.md`:

```markdown
# BitcoinTX X.Y.Z agent test report
Commit: <SHA> · Date: <date> · Agent: <name/model> · StartOS: <version> · VM arch: x86_64
Tracks run: A, B, C (say which were skipped and why)

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
old code (CLAUDE.md), so the next run of this walk has less to catch.

## Known issues

Found while this document was written (v1.2.0). Report these as KNOWN.
Delete a line when its fix is merged into `develop`, since release
candidates are built from it.

- **GLD-6**: Delete shows its confirm twice (`TransactionPanel.tsx` and
  `TransactionForm.tsx`).
- **PRC, 1.2.0 and earlier only (Track B's previous release)**: an install
  with entries but no price choice switches itself to Public price sites at
  its next restart, e.g. the update. Fixed on `develop` (`afd23ea`): a
  release candidate must not do it.
