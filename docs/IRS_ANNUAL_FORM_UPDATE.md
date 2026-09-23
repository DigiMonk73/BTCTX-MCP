# Annual IRS Form Update Runbook

Once a year the IRS publishes the final Form 8949 and Schedule D for the tax
year just ended, usually December–January. This runbook adds that year's
templates without changing any earlier year. Every earlier year's templates
stay in the app, so the change only adds files.

How the pipeline works: [IRS_FORM_GENERATION.md](IRS_FORM_GENERATION.md).
`YYYY` below means the new tax year (e.g. `2026`).

---

## Quick path (usually all you need)

1. **Alert.** The *IRS forms watch* workflow
   (`.github/workflows/irs-forms-watch.yml`) runs
   `python scripts/irs_new_year.py --watch` every Monday, November through
   March. It fails, and GitHub emails you, once irs.gov has final forms for the
   year after the newest bundled one. You can also run it by hand from the
   Actions tab (`workflow_dispatch`).

2. **Download, verify, install:**
   ```bash
   python scripts/irs_new_year.py YYYY
   ```
   The script:
   - downloads `f8949.pdf` and `f1040sd.pdf`. It tries
     `irs.gov/pub/irs-prior/<form>--YYYY.pdf` first, then
     `irs.gov/pub/irs-pdf/<form>.pdf`.
   - rejects drafts and PDFs for the wrong year. It reads the year printed on
     the form.
   - checks that every Form 8949 and Schedule D field name the app writes
     exists in the new PDFs. It checks a full page of rows in both Parts, plus
     Schedule D lines 1b, 2, 3, 8b, 9 and 10.
   - checks that the checkbox letters printed on each Part, in order, match
     `boxes_part1` / `boxes_part2`.
   - prints how many 8949 field names were added or removed compared with the
     previous bundled year.
   - if every check passes, installs the PDFs to
     `backend/assets/irs_templates/YYYY/` and runs
     `backend/tests/test_irs_templates.py -k YYYY`.

   If any check fails (a line marked ✗), nothing is installed. Go to
   [Step 4](#step-4--if-field-names-changed).

3. **Sign off.** The template tests stay red until you add `YYYY` to
   `verified_years` in `get_8949_field_config()`
   (`backend/services/reports/form_8949.py`). This is deliberate: a person has
   to look at each year once. If the new year uses the same layout, add it to
   the existing `year >= 2025` branch:
   ```python
   "verified_years": [2025, YYYY],
   ```

4. **Run the tests:**
   ```bash
   python scripts/irs_new_year.py YYYY --check   # re-verify installed PDFs + template tests
   make test                                     # full suite
   ```
   `test_irs_templates.py` finds every year folder on its own. For each year it
   checks that all fields land in a real fill, that exactly the right box is
   checked, that the box order matches the printed form, that Schedule D lines
   land, that an unknown field name raises an error, and that the output is
   flattened.

5. **Look at a generated PDF** ([checklist below](#visual-check-do-not-skip)).

6. **Commit and release.** Commit the new `backend/assets/irs_templates/YYYY/`
   folder and the `verified_years` change. Add a CHANGELOG entry that names the
   irs.gov source URLs. Then bump the **minor** version (project convention: a
   new tax year's forms is a minor release) and follow the release checklist in
   `CLAUDE.md`. Also update the [year quirks](#year-quirks-reference) table.

### Script options

| Command | Use |
|---|---|
| `python scripts/irs_new_year.py YYYY` | Download from irs.gov, verify, install, test |
| `python scripts/irs_new_year.py YYYY --from-dir ~/Downloads` | Use `f8949.pdf` / `f1040sd.pdf` you downloaded yourself (same checks) |
| `python scripts/irs_new_year.py YYYY --check` | Verify templates already in `backend/assets/irs_templates/YYYY/` and run the template tests |
| `python scripts/irs_new_year.py --watch` | For CI: exit 1 when final forms for the next year are on irs.gov |

Never bundle a draft (`irs.gov/pub/irs-dft/...`). The IRS changes field layouts
before a form is final.

### Visual check (do not skip)

The tests check field names and values, not how the page looks. Look at one
filled sheet yourself. The quickest way fills the templates directly and needs
no server or data. Run it from the repo root:

```bash
python - <<'EOF'
from decimal import Decimal as D
from backend.services.reports.form_8949 import (
    Form8949Row, get_8949_field_config, map_8949_rows_to_field_data, map_schedule_d_fields)
from backend.services.reports.pdf_form_filler import fill_pdf_form

Y = 2026                                   # the new year
n = get_8949_field_config(Y)["rows_per_page"]
row = lambda hp, box: Form8949Row("0.01 BTC", "01/15/2020", f"06/01/{Y}",
                                  D("1000"), D("400"), D("600"), hp, box)
fields = {**map_8949_rows_to_field_data([row("SHORT", "H")] * n, 1, Y),
          **map_8949_rows_to_field_data([row("LONG", "K")] * n, 2, Y)}
t = f"backend/assets/irs_templates/{Y}"
open("/tmp/f8949-check.pdf", "wb").write(fill_pdf_form(f"{t}/f8949.pdf", fields))
one = {"proceeds": D("1000"), "cost": D("400"), "gain_loss": D("600")}
sd = map_schedule_d_fields({"lines": {k: one for k in ("1b", "2", "3", "8b", "9", "10")}}, Y)
open("/tmp/f1040sd-check.pdf", "wb").write(fill_pdf_form(f"{t}/f1040sd.pdf", sd))
EOF
```

You can also generate the real report from **Reports → IRS Reports** in a
running app, using test data (never your real database). Add a few `YYYY`
disposals: an exchange Sell, a long-term Sell, and a self-custody spend.

Check:
- [ ] Every row sits inside its table cell, not shifted by a column or row. The last row on each page is filled.
- [ ] Dates are MM/DD/YYYY and amounts have two decimals.
- [ ] Short-term rows are in Part I (page 1) and long-term rows in Part II (page 2).
- [ ] Each Part has exactly one box checked, next to the right letter.
- [ ] Column (f) "Code(s)" and column (g) are empty.
- [ ] Schedule D amounts are on the lines that match the boxes (see the table in [IRS_FORM_GENERATION.md](IRS_FORM_GENERATION.md#form-1099-da-boxes)).
- [ ] The output is flattened: fields can't be edited in a PDF viewer.

---

## Step 4 — If field names changed

The script stops with ✗ lines when a field the app writes is missing, or when
the box order doesn't match the printed form. The app itself also fails
loudly: `fill_pdf_form` raises `ValueError` for any field name that isn't in
the template, so a renamed field can never print a blank form without an error.

### 1. See what changed (pypdf)

Put the new PDFs in a folder (download them from the irs.gov URLs above if the
script refused to install them), then:

```bash
python - <<'EOF'
from pypdf import PdfReader
OLD_DIR = "backend/assets/irs_templates/2025"
NEW_DIR = "/path/to/new/pdfs"          # holds f8949.pdf and f1040sd.pdf
fields = lambda d, form: PdfReader(f"{d}/{form}.pdf").get_fields()
for form in ("f8949", "f1040sd"):
    a, b = fields(OLD_DIR, form), fields(NEW_DIR, form)
    print(f"== {form}: {len(b.keys() - a.keys())} added, {len(a.keys() - b.keys())} removed")
    for k in sorted(a.keys() - b.keys())[:20]: print("  -", k)
    for k in sorted(b.keys() - a.keys())[:20]: print("  +", k)
for k, v in fields(NEW_DIR, "f8949").items():   # checkbox widgets and on-states
    if ".c1_1[" in k or ".c2_1[" in k: print(k, v.get("/_States_"))
EOF
```

### 2. Form 8949: `get_8949_field_config(year)`

Add a new branch for the year, e.g. `if year >= YYYY:` above the 2025 branch,
with its own `verified_years`. Leave the existing branches alone so earlier
years keep working. The row field names are built like this:

```
topmostSubform[0].Page{p}[0].{table}[0].Row{r}[0].f{p}_{n}[0]
    p = 1 (Part I, short-term) or 2 (Part II, long-term)
    n = 3 + (r-1)*8 + column offset   (a=0, b=1, c=2, d=3, e=4, f=5, g=6, h=7)
```

| Key | What to check in the field list |
|---|---|
| `table_name_page1` / `table_name_page2` | The table name in the row fields: `Table_Line1` (2024, both pages) or `Table_Line1_Part1` / `Table_Line1_Part2` (2025). |
| `rows_per_page` | Number of `Row{r}` groups in the page-1 table (fields ÷ 8). **2024 = 14, 2025 = 11.** Set too high, rows go to fields that don't exist and generation fails. Set too low, sheets are only partly used. |
| `row1_zero_pad` | Whether row 1 uses `f1_03`…`f1_09` (2025) or `f1_3`… (2024). Rows 2+ are never padded. |
| `boxes_part1` / `boxes_part2` | Box letters in the order they are **printed** on each Part, top to bottom. |
| `verified_years` | The years this branch was checked against. |

`map_8949_rows_to_field_data()` always starts row 1 at field index 3 and pads
only row 1. If the IRS changes the numbering scheme itself (a different start
index, a different number of columns, or padding on other rows), change the
mapper, not just the config.

**Checkboxes.** Each Part's boxes are one field with several widgets:
`topmostSubform[0].Page{p}[0].c{p}_1[i]`. The on-state of widget `i` is
`/{i+1}`, and `i` is the letter's position in `boxes_part1` / `boxes_part2`
(`checkbox_field_for_box()`). For 2025 the Part I list is
`["A","B","C","G","H","I"]`, so Box H is `c1_1[4]` with on-state `/5`. Check
`/_States_` in the snippet output. If the widgets are no longer numbered in
printed order, or the on-states aren't `/1`…`/n`, change
`checkbox_field_for_box()`.

### 3. Schedule D: `get_schedule_d_field_config(year)`

The app fills four fields, (d) (e) (g) (h), on each of lines 1b, 2, 3 (Part I,
`Table_PartI`) and 8b, 9, 10 (Part II, `Table_PartII`):

```
topmostSubform[0].Page1[0].{Table_PartI|Table_PartII}[0].Row{line}[0].f1_{n}[0]
    1b: 7-10 (2024 pads: 07, 08, 09, 10)   2: 11-14   3: 15-18
    8b: 27-30   9: 31-34   10: 35-38
```

If the numbers or padding change, add a year condition in that function. If
the IRS renumbers lines, also read the form text to confirm which line each
8949 box feeds, and update `SCHEDULE_D_LINE_FOR_BOX`.

### 4. Re-run

```bash
python scripts/irs_new_year.py YYYY --from-dir /path/to/new/pdfs   # or: YYYY --check once installed
make test
```

If the layout changed in a way the per-year tests don't cover, e.g. a new
`rows_per_page`, copy `backend/tests/test_2025_forms.py` to
`test_YYYY_forms.py` and update the year, dates and page-count expectations.
The row-overflow test (seed `rows_per_page + 2` rows and assert that none are
lost) is the one that matters.

---

## When the 1099-DA box rules need updating

Box selection lives in `_broker_reporting()` and `_determine_box()` in
`form_8949.py`, and `backend/tests/test_1099da_boxes.py` tests it. Current
rules:

- Through 2024: C / F.
- 2025+: exchange Sells (proceeds reported on Form 1099-DA, no basis) → H / K.
- 2026+: Sells of lots bought on the exchange on or after 2026-01-01 and never
  transferred out ("covered", `COVERED_DIGITAL_ASSET_START`) → G / J. Lots
  transferred in from elsewhere stay H / K.
- Self-custody spends and network-fee disposals (no 1099) → I / L.

These rules only change when the form or the rules change, not every year.
Revisit them if any of these happens:
- the new Form 8949 adds, removes or re-letters boxes, or changes what a box
  means (read the box captions);
- the broker regulations change the covered-asset start date or what counts as
  covered;
- the 1099-DA you receive doesn't match what the app produced. For one or a
  few sales, set the transaction's "Broker form" (`broker_reporting`); for a
  systematic difference, change `_broker_reporting()`.

---

## Year quirks reference

| Year | 8949 table names | Rows/page | Zero-padding (8949) | Boxes (Part I / Part II) | Schedule D |
|---|---|---|---|---|---|
| 2024 | `Table_Line1` (both pages) | 14 | none | A B C / D E F | line 1b fields `f1_07`–`f1_10` |
| 2025 | `Table_Line1_Part1` / `Table_Line1_Part2` | 11 | row 1 only (`f1_03`…`f1_09`) | A B C G H I / D E F J K L | line 1b fields `f1_7`–`f1_10`; other lines same as 2024 |
