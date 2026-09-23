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
│   └── 2025/  f8949.pdf  f1040sd.pdf     # one folder per tax year, exact filenames
├── routers/reports.py                    # endpoints, template lookup, per-box sheets, merge
├── services/
│   ├── tax_time.py                       # tax timezone, tax-year bounds, date formatting
│   ├── transaction.py                    # FIFO lots, holding_period()
│   └── reports/
│       ├── form_8949.py                  # rows, 1099-DA box rules, Schedule D totals, per-year field config
│       ├── pdf_form_filler.py            # fill_pdf_form(): pypdf fill + flatten
│       ├── complete_tax_report.py
│       ├── transaction_history.py
│       └── reporting_core.py
└── tests/
    ├── test_irs_templates.py             # every year folder: fields exist, values land, boxes, flatten
    ├── test_1099da_boxes.py              # box selection from real ledger data
    └── test_2025_forms.py                # 11-row pages, overflow sheets, Part I/II, Schedule D totals
scripts/irs_new_year.py                   # download/verify/install a new year's templates
.github/workflows/irs-forms-watch.yml     # weekly check for new final IRS forms (Nov–Mar)
```

`get_supported_years()` in `reports.py` lists every year folder that holds
both PDFs. The endpoint checks the requested year against that list and
returns HTTP 400 for any other year. The Reports page takes the year as free
text, so no frontend change is needed for a new year.

## Data flow

```
LotDisposal rows for the tax year
  │  build_form_8949_and_schedule_d(year, db)                 form_8949.py
  │    - tax-year window in the tax timezone
  │    - skip purposes Gift / Donation / Lost
  │    - _broker_reporting() + _determine_box()  -> box letter per disposal
  │    - Form8949Row per disposal, split SHORT / LONG
  │    - Schedule D totals per line (SCHEDULE_D_LINE_FOR_BOX)
  ▼
get_irs_reports()                                             reports.py
  │  _chunks_by_box(): group each term by box, cut into rows_per_page chunks
  │  pair short chunk i with long chunk i on sheet i (zip_longest)
  │  map_8949_rows_to_field_data(chunk, page=1|2, year) -> {field: value}
  │  fill_pdf_form(f8949.pdf, fields)           -> one flattened sheet each
  │  map_schedule_d_fields(...) + fill_pdf_form(f1040sd.pdf, ...)
  ▼
_merge_all_pdfs(): 8949 sheets in order, then Schedule D  -> IRSReports_YYYY.pdf
```

Each LotDisposal is the part of a disposal that came from one lot, so a Sell
that used three FIFO lots gives three 8949 rows. Sells, spends and
network-fee disposals are included.

## Tax timezone

Timestamps are stored in UTC. The tax timezone decides:
- **which tax year** a disposal falls in. `tax_year_bounds()` runs from local
  Jan 1 00:00 to the next local Jan 1. A 9 pm Dec 31 sale in New York belongs
  to that year, even though it is already Jan 1 in UTC.
- **the dates printed** in columns (b) and (c): `format_tax_date()` gives
  MM/DD/YYYY in the tax timezone.
- **the holding period** (next section).

Where the timezone comes from: **Settings → Tax Timezone** (the
`tax_timezone` row in `app_settings`, filled from the browser on first login),
then the `BTCTX_TIMEZONE` env var, then UTC. API:
`GET/PUT /api/settings/tax-timezone`. Changing it recalculates the whole
ledger, because stored holding periods can change.

## Holding period

`holding_period()` in `services/transaction.py` implements the IRS "more than
one year" rule on calendar dates in the tax timezone. A disposal is **LONG
only if it is disposed after the one-year anniversary** of acquisition.
Selling on the anniversary itself is short-term. A Feb 29 acquisition's
anniversary is Feb 28. The value is stored on each LotDisposal when the ledger
is recalculated, and the form reads the stored value. SHORT rows go to Part I,
LONG rows to Part II.

## Form 1099-DA boxes

Each disposal gets one checkbox letter, from `_broker_reporting()` (is it on a
1099-DA, and is basis reported?) and `_determine_box()`:

| Disposal | 2024 and earlier | 2025 | 2026+ |
|---|---|---|---|
| Exchange **Sell** of a lot bought on the exchange on/after 2026-01-01 and never transferred out ("covered") | — | — | **G** / **J** (1099-DA, basis reported) |
| Any other exchange Sell: lot bought before 2026, or BTC transferred in from elsewhere | C / F | **H** / **K** (1099-DA, proceeds only) | **H** / **K** |
| Self-custody spends, network-fee disposals (no 1099) | C / F | **I** / **L** | **I** / **L** |

(short / long). Details:
- "Exchange Sell" means `type == "Sell"` from the Exchange BTC account. That is
  what the broker (River) reports on Form 1099-DA, starting with 2025.
- Covered means the lot was created by a Buy into Exchange BTC with
  an acquisition date on or after `COVERED_DIGITAL_ASSET_START` (2026-01-01,
  as a date in the tax timezone, the same date printed in column (b)). A lot created by a Transfer is never covered, because a transfer
  breaks the broker's basis chain.
- From 2025, Boxes C/F exclude digital assets, so self-custody BTC moves to I/L.

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

The app fills columns (d) proceeds, (e) cost and (h) gain/loss. Column (g) is
blank. Only lines that have rows get filled.

## Form 8949 fields

The template has two pages. Page 1 is Part I (short-term), page 2 is Part II
(long-term). Extra rows go on extra copies of the template, never on "page 3"
fields (those don't exist). `rows_per_page` comes from the year config:
**14 for 2024, 11 for 2025**.

Row field names:

```
topmostSubform[0].Page{p}[0].{table}[0].Row{r}[0].f{p}_{n}[0]
  n = 3 + (r-1)*8 + offset
```

| Col | Offset | Value |
|---|---|---|
| (a) | 0 | `"<disposed_btc> BTC"` |
| (b) | 1 | date acquired, MM/DD/YYYY (tax timezone) |
| (c) | 2 | date sold, MM/DD/YYYY (tax timezone) |
| (d) | 3 | proceeds, 2 decimals |
| (e) | 4 | cost basis, 2 decimals |
| (f) | 5 | **blank.** The app records no adjustment codes. The box letter is a checkbox, never a column (f) code. |
| (g) | 6 | blank |
| (h) | 7 | gain or loss, 2 decimals |

Year differences, kept in `get_8949_field_config(year)`:

| Year | `table` (p1 / p2) | Row 1 numbering | Boxes Part I / Part II |
|---|---|---|---|
| 2024 | `Table_Line1` / `Table_Line1` | `f1_3`…`f1_10` | A B C / D E F |
| 2025 | `Table_Line1_Part1` / `Table_Line1_Part2` | `f1_03`…`f1_09`, `f1_10` | A B C G H I / D E F J K L |

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
| HTTP 400 `Tax year YYYY not supported. Available years: [...]` | No `backend/assets/irs_templates/YYYY/` folder with both PDFs. |
| HTTP 500 `IRS report generation failed: N field(s) not in .../f8949.pdf ...` | A field name in the config doesn't exist in that year's template (template swapped, or config wrong). See [IRS_ANNUAL_FORM_UPDATE.md, Step 4](IRS_ANNUAL_FORM_UPDATE.md#step-4--if-field-names-changed). |
| HTTP 500 `... Box X is not in Part I of the YYYY Form 8949` | `_determine_box()` returned a letter that the year's `boxes_part1` / `boxes_part2` doesn't have. |
| Tests fail with `templates are present but get_8949_field_config has not been verified for YYYY` | A new year folder was added without signing it off in `verified_years`. See the runbook. |

## Tests

```bash
python -m pytest -q backend/tests/test_irs_templates.py backend/tests/test_1099da_boxes.py backend/tests/test_2025_forms.py
make test    # full suite
```
