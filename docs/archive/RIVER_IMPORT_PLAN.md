# River CSV Import — Implementation Plan

> **Status:** Phases 1–2 SHIPPED on `feature/river-import` (2026-06-10);
> verified on real data — post-import balances reconciled to River to the
> exact satoshi/cent. Phase 3 (account-activity CSV) **dropped by owner
> decision (2026-06-10)**: USD cash deposits are ~3 simple manual entries a
> month — not worth a second adapter. Do not revive without being asked.
> **Design decision (owner):** buy funding source is inherently a per-purchase
> human choice — no predictor can be reliable, so the preview toggle IS the
> mechanism, and heuristic defaults are best-effort only. Note the recurrence
> heuristic learns from the uploaded file, so on small incremental files most
> buys default to Exchange USD; expect to flip the Bank-funded ones each import.
> **Branch:** `feature/river-import`
> **Goal:** Stop entering River transactions by hand. Periodically download
> River's CSV export, upload it to BitcoinTX, review a preview of *new* rows,
> click import.

## Background

River (river.com → **Taxes & Documents**, web only) exports two CSVs:

- **Bitcoin activity** — all BTC transactions. Columns:
  `Date, Sent Amount, Sent Currency, Received Amount, Received Currency, Fee Amount, Fee Currency, Tag`
  Dates are `YYYY-MM-DD HH:MM:SS` (UTC). `Tag` is one of
  `Buy`, `Sell`, `Income`, `Interest`, `Withdrawal`, or empty (on-chain
  sends/receives).
- **Account activity** — BTC *and* cash movements (USD deposits/withdrawals).
  Format TBD — needed for Phase 3.

A row-matching analysis of the owner's real River export against the manually
maintained BitcoinTX ledger (June 2026) validated the design:

- Buys match 1:1 on exact BTC amount within ±48 h (manual timestamps drift up
  to ~29 h from River's).
- BitcoinTX `cost_basis_usd` = River `Sent Amount`; fee is separate. Zero BTC
  amount mismatches.
- A simple funding-source heuristic (see below) classified ~96 % of buys
  correctly.
- The comparison also surfaced several manual bookkeeping errors (missed
  buys, a wrong basis) — supporting evidence that import > manual entry.

## User's account model (deliberately simple — do not generalize)

| BitcoinTX account | Real world |
|---|---|
| Bank | Outside bank (USD via ACH) |
| Exchange USD / Exchange BTC | **River** (cash balance / BTC balance) |
| Wallet | Cold storage |
| External | Everything else (Gemini rewards, gifts, spends…) |

Implications:
- River **Buy** funded by ACH → `Buy: Bank → Exchange BTC`; funded from River
  cash balance → `Buy: Exchange USD → Exchange BTC`. The bitcoin-activity CSV
  cannot distinguish these — hence heuristic + preview toggle.
- Untagged BTC **send** is almost always a cold-storage move
  (`Transfer: Exchange BTC → Wallet`); untagged **receive** is the trip back
  (`Transfer: Wallet → Exchange BTC`). Occasionally a send is a real
  `Withdrawal` (spent/gift) — user reclassifies in preview.
- **Gemini cashback rewards** never touch River; they remain manual entries
  (`Deposit` with source=Reward). Out of scope here.
- **Interest on the River cash balance is paid in BTC** (monthly, on the
  1st) and appears in the bitcoin-activity CSV tagged `Interest` — fully
  covered by the Deposit mapping below; nothing interest-related needs the
  account-activity CSV.

## Row mapping (bitcoin-activity CSV → internal tx)

| River pattern | BitcoinTX transaction | Notes |
|---|---|---|
| Tag=Buy (USD→BTC) | `Buy`, from=**heuristic** Bank/Exchange USD, to=Exchange BTC, `amount`=Received, `cost_basis_usd`=Sent, fee from Fee cols | funding toggle in preview |
| Tag=Sell (BTC→USD) | `Sell: Exchange BTC → Exchange USD`, `amount`=Sent, `proceeds_usd`=Received, fee USD | |
| Tag=Interest / Income | `Deposit: External → Exchange BTC`, source=Interest/Income, `cost_basis_usd`=**FMV autofill** (editable) | River gives no USD value |
| Untagged send (Sent=BTC, no Received) | `Transfer: Exchange BTC → Wallet`, fee from Fee cols (River often omits it) | toggle → Withdrawal + purpose |
| Untagged receive (Received=BTC, no Sent) | `Transfer: Wallet → Exchange BTC`, fee 0 (River can't see wallet-side fee; editable) | toggle → Deposit + source |
| Tag=Withdrawal | `Withdrawal: Exchange BTC → External`, purpose chosen in preview (default Spent) | rare |

**Funding heuristic (Buys):** compute total outlay = Sent + USD fee. Group by
outlay across the file; an outlay value that recurs (≥4 occurrences) with no
fee is a recurring auto-buy → default **Bank**; everything else defaults
**Exchange USD**. Every row's funding source is a one-click toggle in the
preview. (Measured ~96 % accurate on real data ≈ a handful of flips per
half-year.)

**FMV autofill:** new helper for historical daily BTC price (e.g. CoinGecko
`/coins/bitcoin/history`, Kraken OHLC fallback, same 3-source spirit as
`services/bitcoin.py`), used to prefill basis for Interest/Income deposits;
always editable in preview; degrade gracefully to blank if offline.

## Dedup / merge engine (the core new capability)

Unlike the existing onboarding CSV import (which **requires an empty DB**),
this flow merges into live data:

1. Parse + adapt all River rows.
2. For each candidate, search existing DB transactions with: compatible type
   mapping, **exact BTC amount** (8 dp), timestamp within **±48 h**.
   One-to-one greedy match (nearest timestamp first).
3. Matched rows → marked *already imported*, excluded from the import set
   (shown collapsed in preview for transparency).
4. Matched-but-different rows (same amount/type, different basis or fee) →
   flagged as **discrepancies** in the preview (informational; user fixes
   manually if desired).
5. Unmatched rows → the import set, shown in the editable preview grid.
6. Execute = existing pattern: sort by timestamp + type order
   (acquisitions before disposals), `create_transaction_record(...,
   auto_commit=False)` per row, single commit, rollback on any failure.
   Backdated inserts rely on the existing full-recalculation
   ("scorched earth") path — covered by tests.

## API

New router `backend/routers/river_import.py` (session-auth, like csv_import):

- `POST /api/import/river/preview` — multipart CSV upload → JSON: import set
  (with per-row defaults/toggles metadata), already-matched count,
  discrepancy list, validation errors/warnings.
- `POST /api/import/river/execute` — CSV + JSON of user's per-row overrides
  (funding source, transfer↔withdrawal reclassification, edited
  basis/fee values) → atomic import, returns count.

Re-uses `csv_import.py` validation primitives (`_parse_decimal`,
account-pair rules) — refactor those into a shared module rather than
duplicating. Does **not** touch the legacy empty-DB import flow.

## Frontend

Settings (or a new "Import" page): upload → preview table of NEW rows only:
date, type (with toggle where ambiguous), amounts, funding-source toggle on
Buys, editable basis/fee cells, per-row exclude checkbox; summary header
("182 rows: 14 new, 168 already in ledger, 2 discrepancies"); Import button →
confirmation showing the atomic result. Discrepancies render as a collapsible
warning list.

## Phases

1. **Backend** — adapter, heuristic, dedup, FMV helper, preview/execute
   endpoints, tests. (The useful core; can be exercised via curl before UI.)
   ✅ Shipped in v0.7.0.
2. **Frontend** — preview/override UI. ✅ Shipped in v0.7.0.
3. ~~**Account-activity CSV** — USD deposits/withdrawals~~ **DROPPED**
   (owner decision, 2026-06-10): cash deposits are a few trivial manual
   entries per month; a second adapter isn't worth building or maintaining.
   The funding-disambiguation benefit is moot — funding source is a
   per-import human choice by design (see status note above).
4. *(Future, optional)* generic adapter interface so other exchanges
   (Strike, Coinbase, Gemini…) are new adapters, not new pipelines.

## Testing requirements

- **Fixtures must be synthetic.** Model them on the real patterns (recurring
  no-fee buys, odd-amount fee buys, untagged sends with/without fee, Interest
  receives) but never commit real amounts/dates from the owner's exports.
- Unit: adapter mapping per row pattern; heuristic classification; date
  parsing (UTC, space-separated format).
- Dedup: exact-amount ±48 h matching, greedy one-to-one, discrepancy
  detection, idempotency (re-importing the same file imports nothing).
- Integration: import into a DB with existing transactions, including
  backdated rows → FIFO recalc correct; atomic rollback on a poisoned row.
- Run the full suite + `baseline-pdfs/regen_and_diff.sh` (imports must not
  perturb report generation).

## Privacy note

Real River/BitcoinTX exports used during development live temporarily in
`docs/`, are excluded via `.git/info/exclude` (local-only), and are deleted
when the feature ships. Never commit them, reference their contents in
committed code/tests/docs, or push them anywhere.
