# IRS Form Generation

How BitcoinTX fills the official IRS Form 8949 and Schedule D. The yearly
template update is covered in
[IRS_ANNUAL_FORM_UPDATE.md](IRS_ANNUAL_FORM_UPDATE.md).

Filling is pure Python ([pypdf](https://pypi.org/project/pypdf/)). Nothing
needs to be installed on the system, whether on the Mac app, Docker or
StartOS.

## Reports

All three endpoints need a logged-in session (`/api/reports/*`).

| Endpoint | Output | How |
|---|---|---|
| `GET /api/reports/irs_reports?year=YYYY` | Form 8949 sheets + Schedule D, one flattened PDF | Official IRS templates filled with pypdf |
| `GET /api/reports/complete_tax_report?year=YYYY` | BitcoinTX's own summary PDF (gains, income, fees, balances) | ReportLab |
| `GET /api/reports/simple_transaction_history?year=YYYY&format=csv\|pdf` | Raw transaction list | CSV / ReportLab |

The rest of this document covers `irs_reports`.

## File layout

```
backend/
├── assets/irs_templates/
│   ├── 2024/  f8949.pdf  f1040sd.pdf
│   ├── 2025/  f8949.pdf  f1040sd.pdf     # one folder per tax year, exact filenames
│   └── drafts/<year>/  f8949.pdf  f1040sd.pdf   # the IRS's drafts for the year after the newest final forms (one at a time): a preview until January 1 after that year
├── routers/reports.py                    # endpoints, template lookup, per-box sheets, merge
├── services/
│   ├── account.py                        # the account book: each account's kind, name, exchange and 1099-DA switch
│   ├── tax_time.py                       # tax timezone, tax-year bounds, date formatting
│   ├── transaction.py                    # lots per account, FIFO or the coins chosen, holding_period()
│   ├── review.py                         # Ledger Review, its reminder sale_may_differ_from_1099da
│   └── reports/
│       ├── form_8949.py                  # rows, 1099-DA box rules per exchange, Schedule D totals, per-year field config
│       ├── pdf_form_filler.py            # fill_pdf_form(): pypdf fill + flatten
│       ├── draft_forms.py                # the IRS's draft forms of the next year: shipped preview, test installs
│       ├── complete_tax_report.py        # its sections, "Sales by exchange", "Coins you chose"
│       ├── pdf_layout.py                 # the report PDFs' shared layout
│       ├── transaction_history.py
│       └── reporting_core.py
└── tests/
    ├── test_irs_templates.py             # every year folder: fields exist, values land, boxes, line 2, flatten
    ├── test_1099da_boxes.py              # box selection from real ledger data
    ├── test_1099da_boxes_349.py          # boxes per exchange: its switch, covered only for coins bought there
    ├── test_add_exchange_1099da_708.py   # the switch asked when an exchange is added
    ├── test_review_1099da_349.py         # Ledger Review's reminder where an exchange's own lot order may differ
    ├── test_fee_broker_override_549.py   # a spend's override places its fee's rows too
    ├── test_independent_figures_1099da.py  # the second calculation's boxes agree
    ├── test_2025_forms.py                # 11-row pages, overflow sheets, Part I/II, Schedule D totals
    ├── test_golden_years.py              # three hand-worked tax years: exact 8949 rows, Schedule D lines
    ├── test_draft_forms.py               # draft forms: off by default, checked, marked on every page
    ├── printed_forms.py                  # reads a flattened 8949 / Schedule D back, field by field where it's drawn
    ├── test_printed_forms.py             # the printed forms: every row once in its box, totals, Schedule D lines
    ├── test_using_these_forms.py         # the Complete Tax Report's "Using these forms" page
    └── test_invariants_property.py       # random valid ledgers keep the tax invariants (Hypothesis)
scripts/irs_new_year.py                   # download/verify/install a new year's templates
.github/workflows/irs-forms-watch.yml     # weekly: an issue when new IRS drafts or final forms are out
```

`get_supported_years()` in `reports.py` lists every year folder that holds
both PDFs (not `drafts/`). The endpoint checks the requested year against
that list (plus a draft year, below) and returns HTTP 400 for any other year.
The Reports page lists the years `GET /api/reports/years` gives, so no
frontend change is needed for a new year.

## Draft forms: the preview, and test installs

Each year's final forms come in an update once the IRS publishes them
(usually December or January). Until then the app offers the IRS's
**draft** Form 8949 and Schedule D of that year as a preview (the owner's
decision, #53), from two places:

- **Shipped with the app**: `backend/assets/irs_templates/drafts/<year>/`,
  one year at a time, put there by
  `python scripts/irs_new_year.py --draft --ship` once the IRS publishes the
  drafts (docs/IRS_ANNUAL_FORM_UPDATE.md). It is offered **only until
  January 1 after its year** (by the server's clock, in UTC): the final forms
  can be out then, and nobody should file a draft from a version they never
  updated. Reports then says the final forms come in an update.
- **On a test install**, the server's data folder, the directory of
  `DATABASE_FILE` (`/data` in Docker and on StartOS):
  `irs-draft-forms/<year>/f8949.pdf` and `f1040sd.pdf`. These win over the
  shipped ones and have no cut-off (a test may need them in January). One
  command puts them there:

```bash
python -m backend.cli install-draft-forms                    # from irs.gov/pub/irs-dft/ (the only site it contacts)
python -m backend.cli install-draft-forms --from-dir DIR     # f8949.pdf and f1040sd.pdf you downloaded
python -m backend.cli install-draft-forms --remove           # take them out again
```

In Docker: `docker exec -u btctx <container> python -m backend.cli install-draft-forms`.
On the StartOS test VM, `tools/vmtest seed` in the lab does it. No restart
is needed.

With a draft, `GET /api/reports/years` lists the year in `form_years` and
`draft_years`, the Reports page shows it as "2026 – IRS draft (preview, not
for filing)" with a warning not to file it, and `irs_reports` fills the
drafts as it fills a final form, leaving out the IRS's cover page ("the draft you are looking for
begins on the next page"). Every page printed says **DRAFT — DO NOT FILE**:
the IRS prints it on each page of a draft, and `draft_forms.py` uses a
draft only when it does. It also checks the year printed on both forms and
that every field the app writes exists and the boxes are in the config's
order (what `scripts/irs_new_year.py` checks for a final form); anything
else is left out with a warning in the log, and `install-draft-forms`
refuses it. A year with final forms ignores its drafts, so the yearly
update replaces them: `irs_new_year.py YYYY` removes `drafts/YYYY`, and a
test fails while a shipped draft's year has final forms.

## Data flow

```
LotDisposal rows for the tax year
  │  build_form_8949_and_schedule_d(year, db)                 form_8949.py
  │    - tax-year window in the tax timezone
  │    - taxable_disposals(): skip Gift / Donation / Lost, except their network-fee disposals
  │    - disposal_box(): _broker_reporting() (the exchange's switch, _on_a_1099da();
  │      covered_lot()) + _determine_box()  -> box letter per disposal
  │    - Form8949Row per disposal, split SHORT / LONG
  │    - Schedule D totals per line (SCHEDULE_D_LINE_FOR_BOX)
  ▼
get_irs_reports()                                             reports.py
  │  _chunks_by_box(): group each term by box, cut into rows_per_page chunks
  │  pair short chunk i with long chunk i on sheet i (zip_longest)
  │  map_8949_rows_to_field_data(chunk, page=1|2, year) -> {field: value}
  │    (the chunk's rows, plus line 2 "Totals" of that chunk)
  │  fill_pdf_form(f8949.pdf, fields)           -> one flattened sheet each
  │  map_schedule_d_fields(...) + fill_pdf_form(f1040sd.pdf, ...)
  ▼
_merge_all_pdfs(): each sheet's used Parts in order, then all of Schedule D's pages -> IRSReports_YYYY.pdf
```

Each LotDisposal is the part of a disposal that came from one lot, so a
disposal that used three lots (first in, first out within its account, or
the coins chosen for a wallet's withdrawal, #711) gives three 8949 rows. Sells, spends and
network-fee disposals are included.

## Tax timezone

Timestamps are stored in UTC. The tax timezone decides:
- **which tax year** a disposal falls in. `tax_year_bounds()` runs from local
  Jan 1 00:00 to the next local Jan 1. A 9 pm Dec 31 sale in New York belongs
  to that year, even though it is already Jan 1 in UTC.
- **the dates printed** in columns (b) and (c): `format_tax_date()` gives
  MM/DD/YYYY in the tax timezone.
- **the holding period** (next section).

Where the timezone comes from: **Settings → Account → Tax Timezone** (the
`tax_timezone` row in `app_settings`), then the `BTCTX_TIMEZONE` env var,
then UTC. Only the names of the `tzdata` package BitcoinTX ships with are
saved (#407), the same list on every machine: a restore elsewhere reads the
same zone, and a backup holding another name keeps this install's own.
API: `GET/PUT /api/settings/tax-timezone`. Changing it recalculates
the whole ledger, because stored holding periods can change; a change that
moves an earlier tax year's figures first asks the past-year question (409,
saved when sent again with `?confirm=`, after a copy; AGENTS.md, "The
past-year warning"). A login fills
it from the browser (`POST /api/settings/tax-timezone/fill`) only while
none was chosen and the ledger has no transactions (#334): with
transactions, only the owner's change in Settings moves it (its PUT sends
`"chosen": true`; one without it is refused with 409 then, as a page from
before the update would send), and Settings suggests the computer's
timezone in one line.

## Holding period

`holding_period()` in `services/transaction.py` implements the IRS "more than
one year" rule on calendar dates in the tax timezone. A disposal is **LONG
only if it is disposed after the one-year anniversary** of acquisition.
Selling on the anniversary itself is short-term. A Feb 29 acquisition's
anniversary is Feb 28. The value is stored on each LotDisposal when the ledger
is recalculated, and the form reads the stored value. SHORT rows go to Part I,
LONG rows to Part II. Inherited coins (`bitcoin_lots.inherited`, an Inherited
deposit's lot and the lots a transfer moves from it, #154) are LONG whatever
their dates (IRC §1223(9); `lot_holding_period()`).

## Form 1099-DA boxes

Each disposal gets one checkbox letter, from `_broker_reporting()` (is it on a
1099-DA, and is basis reported?) and `_determine_box()`:

| Disposal | 2024 and earlier | 2025 | 2026+ |
|---|---|---|---|
| Exchange **Sell** of a lot bought on that exchange on/after 2026-01-01 and never transferred out ("covered") | — | — | **G** / **J** (1099-DA, basis reported) |
| Any other exchange Sell: lot bought before 2026, or BTC transferred in from elsewhere (another exchange included) | C / F | **H** / **K** (1099-DA, proceeds only) | **H** / **K** |
| Spends (from a wallet or an exchange), network-fee disposals, and Sells on an exchange whose 1099-DA switch is off (no 1099; a spend's override can place its fee, below) | C / F | **I** / **L** | **I** / **L** |

(short / long). Details:
- "Exchange Sell" means `type == "Sell"` from an exchange's BTC account whose
  exchange has "This exchange sends me a Form 1099-DA" on
  (`exchanges.sends_1099da`, #349; asked when an exchange is added, on
  unless answered No, #708; changed in Settings › Wallets, exchanges and
  banks, `PUT /api/accounts/{id}` `{sends_1099da}`, which asks the
  past-year question by comparing boxes, with no replay): what each US
  exchange (River, say) reports on its Form 1099-DA, starting with 2025.
  With the switch off (an exchange outside the US usually sends none), that
  exchange's Sells are I/L, as a self-custody spend's are; the gain is the
  same either way. In a 1.x ledger the only such account is Exchange BTC.
- Covered means the lot was created by a Buy into the same account the Sell
  is from, with an acquisition date on or after
  `COVERED_DIGITAL_ASSET_START` (2026-01-01, as a date in the tax timezone,
  the same date printed in column (b)). A lot created by a Transfer is never
  covered, because a transfer breaks the broker's basis chain: coins moved
  from one exchange to another arrive noncovered (no transfer statement is
  required between brokers).
- From 2025, Boxes C/F exclude digital assets, so self-custody BTC moves to I/L.

**Per exchange in the complete tax report** (#635). Section 2 shows
each disposal's account under its kind ("Sale", then "Kraken BTC"), and
"Sales by exchange" follows it: for each exchange with Sells in the year,
whether it sends a 1099-DA, its Sells' boxes and rows, and their proceeds,
cost and gain, network fees left out, to set beside each exchange's
1099-DA. It moves no figure: its totals are its Sells' rows. Each lot held
when the year began names its account too, as the year-end lots do. In a
year with coins chosen in a wallet (#711), "Coins you chose" follows: each
such transaction's purchases or deposits the coins came from, with the day
the choice was saved (marked when that was after the coins left), the
record of the specific identification for whoever files the return.
Ledger Review's reminder `sale_may_differ_from_1099da` lists a Sell from
2026, on an exchange that sends a 1099-DA (and whose Broker form doesn't
say "none" or "proceeds"), for which the exchange's own lot order and
BitcoinTX's take different coins bought there (whose basis it reports): an
exchange without the purchase
dates of coins moved in counts them from their arrival (Instructions for
Form 1099-DA, lot selection). Once the two orders part, a later Sell can
differ too. Where the form differs, the Form 8949 the owner files shows the
exchange's figures with an adjustment (code B); BitcoinTX's forms leave
columns (f) and (g) blank, so that is for whoever files the return.

**Per-transaction override.** When a real 1099-DA (or, for 2024 and earlier,
1099-B) disagrees with these rules, the user sets `broker_reporting` on that
Sell or Spent withdrawal: in the transaction form ("Broker form"), with the
MCP `update_transaction` tool, or via the API. It replaces
`_broker_reporting()`'s answer for every disposal of that transaction:

| `broker_reporting` | 2024 and earlier | 2025+ |
|---|---|---|
| `none` (not on a broker form) | C / F | I / L |
| `proceeds` (basis not reported) | B / E | H / K |
| `basis` (proceeds and basis) | A / D | G / J |
| NULL (default) | rules above | rules above |

A spend's override places its network-fee disposals (`is_fee`) too, by the
same table (`_fee_follows_override()`, #549, the owner's rule, 2026-10-18),
so a 1099-DA that lists a spend and the coins its fee used can be matched.
Without an override a fee is on no broker form. A Gift, Donation or Lost
withdrawal has no rows of its own and the form offers it no override, so
its fee stays C / F or I / L even with one left from an edit; so does a
transfer's fee (only a Sell or Withdrawal can carry an override). Only the
box moves: the fee's value and gain are the same either way. A 1099-DA
that lists a fee but not its withdrawal, or a transfer's fee, can't be
matched yet (#551).

**One box per sheet.** Each Part of a Form 8949 page can have only one box
checked. `_chunks_by_box()` groups rows by box before cutting pages, so (for
example) H sales and I spends go on separate sheets.
`map_8949_rows_to_field_data()` raises `ValueError` if the rows of one page
have different boxes.

**Schedule D lines** (`SCHEDULE_D_LINE_FOR_BOX`): each box's totals go on the
line printed for it.

| Line | Boxes | Line | Boxes |
|---|---|---|---|
| 1b | A, G | 8b | D, J |
| 2 | B, H | 9 | E, K |
| 3 | C, I | 10 | F, L |

The app fills columns (d) proceeds, (e) cost and (h) gain/loss, a loss in
parentheses as the instructions ask. Column (g) is blank. Only lines that
have rows get filled. Each line is the sum of the line 2 totals of all that
box's Form 8949 sheets.

## Form 8949 fields

The template has two pages. Page 1 is Part I (short-term), page 2 is Part II
(long-term). Extra rows go on extra copies of the template, never on "page 3"
fields (those don't exist). Only the pages with rows are printed: the
instructions say to "complete and file either Part I or II" (and a separate
one for each box), so a sheet with only short-term rows has no empty Part
II printed, and the other way round. Schedule D always prints all its
pages: Part III is the filer's to complete. `rows_per_page` comes from the
year config: **14 for 2024, 11 for 2025**.

Row field names:

```
topmostSubform[0].Page{p}[0].{table}[0].Row{r}[0].f{p}_{n}[0]
  n = 3 + (r-1)*8 + offset
```

| Col | Offset | Value |
|---|---|---|
| (a) | 0 | the BTC amount with all eight decimals, `"0.00000005 BTC"` (`calculation.btc_text()`; never exponent form) |
| (b) | 1 | date acquired, MM/DD/YYYY (tax timezone): the lot's, which for a My BTC or Gift deposit is its date originally acquired when given; `INHERITED` for inherited coins, as the instructions ask (`form_8949.acquired_text()`) |
| (c) | 2 | date sold, MM/DD/YYYY (tax timezone) |
| (d) | 3 | proceeds, 2 decimals |
| (e) | 4 | cost basis, 2 decimals |
| (f) | 5 | **blank.** The app records no adjustment codes. The box letter is a checkbox, never a column (f) code. |
| (g) | 6 | blank |
| (h) | 7 | gain or loss, 2 decimals; a loss in parentheses, `(9.74)` (`_form_amount()`) |

**Line 2 "Totals"**, below the last row of each Part, gets the totals of the
rows on that page (one sheet's chunk of one box): (d), (e) and (h) added up to
the cent (losses subtracted), 2 decimals, a negative total in parentheses;
(f) and (g) blank like the rows. A Part with no rows leaves line 2 blank. The fields sit directly under the page,
not in the table: `topmostSubform[0].Page{p}[0].f{p}_{n}[0]`, with `n` per
column in `line2_fields` (`line2_field_names()`).

Year differences, kept in `get_8949_field_config(year)`:

| Year | `table` (p1 / p2) | Row 1 numbering | Line 2 (d) (e) (f) (g) (h) | Boxes Part I / Part II |
|---|---|---|---|---|
| 2024 | `Table_Line1` / `Table_Line1` | `f1_3`…`f1_10` | `f{p}_115`…`f{p}_119` | A B C / D E F |
| 2025 | `Table_Line1_Part1` / `Table_Line1_Part2` | `f1_03`…`f1_09`, `f1_10` | `f{p}_91`…`f{p}_95` | A B C G H I / D E F J K L |

Checkbox: `topmostSubform[0].Page{p}[0].c{p}_1[i]` with on-state `/{i+1}`,
where `i` is the letter's position in `boxes_part1` / `boxes_part2`
(`checkbox_field_for_box()`).

Schedule D field names are in `get_schedule_d_field_config(year)`. The only
2024/2025 difference is line 1b: 2024 uses `f1_07`–`f1_10` and 2025 uses
`f1_7`–`f1_10`.

## Filling: `fill_pdf_form(template, fields, flatten=True)`

`pdf_form_filler.py`:
1. Clones the template with pypdf and deletes the `/XFA` entry. IRS PDFs also
   contain an XFA form, and viewers that use XFA would ignore the AcroForm
   values.
2. **Rejects unknown field names.** If any key in `fields` isn't in the
   template, it raises `ValueError("N field(s) not in <template> ...")`. This
   is how an IRS field rename shows up: a loud failure, never a blank form.
3. Sets every field in the template: given values, `""` for other text
   fields, and `/Off` for other checkboxes. Checkbox values are on-state names
   such as `"/5"`.
4. With `flatten=True` (what the endpoint uses), draws each value into the
   page, removes the widget annotations and deletes the `/AcroForm`. The output
   can't be edited. `flatten=False` keeps the fillable form, and the tests use
   it to read values back.

The endpoint then concatenates the flattened PDFs with pypdf.

## Errors

| Symptom | Cause |
|---|---|
| HTTP 400 `Tax year YYYY not supported. Available years: [...]` | No `backend/assets/irs_templates/YYYY/` folder with both PDFs (nor a draft of it: the shipped preview until January 1 after its year, or a test install's). |
| A draft year isn't offered | The shipped preview stops on January 1 after its year (update for the final forms). Otherwise the log says why (`IRS draft forms in ... left out: ...`): not the IRS's draft of that year, or a field the app writes is missing. |
| HTTP 500 `The IRS forms couldn't be made: …`, and the log `IRS forms for YYYY failed: ValueError` | The error's own text is only in the trace, at `LOG_LEVEL=DEBUG` (#422). `N field(s) not in .../f8949.pdf ...`: a field name in the config doesn't exist in that year's template (template swapped, or config wrong); see [IRS_ANNUAL_FORM_UPDATE.md, Step 4](IRS_ANNUAL_FORM_UPDATE.md#step-4--if-field-names-changed). `Box X is not in Part I of the YYYY Form 8949`: `_determine_box()` returned a letter that the year's `boxes_part1` / `boxes_part2` doesn't have. |
| Tests fail with `templates are present but get_8949_field_config has not been verified for YYYY` | A new year folder was added without signing it off in `verified_years`. See the runbook. |

## Tests

```bash
python -m pytest -q backend/tests/test_irs_templates.py backend/tests/test_1099da_boxes.py backend/tests/test_2025_forms.py \
    backend/tests/test_draft_forms.py backend/tests/test_printed_forms.py
make test    # full suite
```

The printed (flattened) forms are read back: `backend/tests/printed_forms.py`
finds each value where it is drawn on the page. The layout comes from the
template itself (rows by field name, columns by position, checkboxes top to
bottom); only the boxes' printed letters and each box's Schedule D line are
written in. `test_printed_forms.py` checks the PDFs of the test ledgers (the full
one, the golden one, and a tiny one with a 5-satoshi sale and a long-term
loss): every row once in its box, (d) - (e) = (h), one box and line 2 per
page, Schedule D lines = their boxes' sheets, the Complete Tax Report's box
table, column (a)'s eight decimals, losses in parentheses, and no page
without rows. Every text field must be found where it is drawn, so a page
that can't be read fails instead of reading as blank.
