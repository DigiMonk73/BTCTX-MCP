# Annual IRS Form Update Runbook

> **Purpose:** Step-by-step procedure for adding a new tax year's Form 8949 and
> Schedule D templates without breaking existing years. Written so an AI
> assistant (or a human) can execute it start-to-finish in one session.
>
> **When to run:** Once a year, after the IRS publishes the **final** (not
> draft) revision of both forms — typically **December–January**. The app keeps
> every prior year's templates, so this is purely additive.
>
> **Companion doc:** [IRS_FORM_GENERATION.md](IRS_FORM_GENERATION.md) explains
> *how* the form-filling pipeline works (XFA workaround, FDF, field naming).
> This runbook is the *what to do each year*.

Throughout this document, `YYYY` means the new tax year (e.g., `2026`).

---

## Quick path (usually all you need)

```bash
python scripts/irs_new_year.py YYYY          # download final forms, verify, install, test
```

The script refuses drafts and wrong-year PDFs, checks that every field name
the app writes exists in the new template, checks the checkbox order against
the boxes printed on the form, diffs field names against the previous year,
and runs `backend/tests/test_irs_templates.py`. If it all matches, add `YYYY`
to `verified_years` in `get_8949_field_config()` (the tests fail until you do —
a person signs off once a year), rerun, then do **Step 6** (look at the PDF)
and **Step 7**. If anything fails, the steps below explain what to change.

The **IRS forms watch** workflow (`.github/workflows/irs-forms-watch.yml`)
checks irs.gov weekly Nov–Mar and fails — emailing you — when final forms for
the next year are published.

## How the multi-year system works (30-second refresher)

- Templates live at `backend/assets/irs_templates/YYYY/f8949.pdf` and
  `backend/assets/irs_templates/YYYY/f1040sd.pdf`. **Exact filenames required.**
- `get_supported_years()` in `backend/routers/reports.py` **auto-detects** year
  folders that contain both PDFs — no code change needed for discovery.
- Per-year field-naming quirks are isolated in two functions in
  `backend/services/reports/form_8949.py`:
  - `get_8949_field_config(year)` — table names, zero-padding, **rows per page**
  - `get_schedule_d_field_config(year)` — Schedule D Line 3 / Line 10 field names
- Everything else (chunking, FDF generation, pdftk filling, merging) is
  year-agnostic and reads from those configs.

So a new year is: **download → verify → drop in folder → diff field names →
add a config branch if anything changed → test → release.**

---

## Step 1 — Download the official PDFs from the IRS

The IRS hosts machine-fillable (AcroForm/XFA) PDFs at stable URL patterns
(all verified working as of June 2026):

| What | URL pattern |
|------|-------------|
| **Current-season form** | `https://www.irs.gov/pub/irs-pdf/f8949.pdf` and `https://www.irs.gov/pub/irs-pdf/f1040sd.pdf` |
| **Prior-year archive** | `https://www.irs.gov/pub/irs-prior/f8949--YYYY.pdf` and `https://www.irs.gov/pub/irs-prior/f1040sd--YYYY.pdf` |
| **Drafts (NEVER bundle)** | `https://www.irs.gov/pub/irs-dft/f8949--dft.pdf` |
| Landing pages (humans) | `https://www.irs.gov/form8949` · `https://www.irs.gov/scheduled` |

```bash
# During the filing season for year YYYY, the current-season URL serves the
# YYYY revision. Once the IRS posts the next year's form, YYYY moves to the
# irs-prior archive URL. Prefer the archive URL when it exists — it is
# unambiguous about the year.
curl -sL -o /tmp/f8949.pdf  "https://www.irs.gov/pub/irs-prior/f8949--YYYY.pdf"  || \
curl -sL -o /tmp/f8949.pdf  "https://www.irs.gov/pub/irs-pdf/f8949.pdf"
curl -sL -o /tmp/f1040sd.pdf "https://www.irs.gov/pub/irs-prior/f1040sd--YYYY.pdf" || \
curl -sL -o /tmp/f1040sd.pdf "https://www.irs.gov/pub/irs-pdf/f1040sd.pdf"
```

### Verify you have the right, final revision

1. **Year check:** Open each PDF (or `pdftk /tmp/f8949.pdf dump_data | head`)
   and confirm the form shows the new tax year and **no "DRAFT" watermark**.
   Draft forms (`irs-dft`) change field layouts before finalization — never
   bundle them.
2. **Record checksums** (goes in the commit message and CHANGELOG):
   ```bash
   md5 /tmp/f8949.pdf /tmp/f1040sd.pdf
   ```
3. **Sanity:** file sizes should be roughly 90–140 KB each. A multi-hundred-KB
   file is probably the instructions or a draft.

> Precedent: the bundled 2025 templates are MD5-identical to
> `irs-prior/f8949--2025.pdf` (`7a32df8f9880449d25aabc100cad8993`) and
> `irs-prior/f1040sd--2025.pdf` (`8a97b160b55866cb547932adf7795590`),
> re-verified 2026-06-10.

---

## Step 2 — Place the templates

```bash
mkdir -p backend/assets/irs_templates/YYYY
cp /tmp/f8949.pdf   backend/assets/irs_templates/YYYY/f8949.pdf
cp /tmp/f1040sd.pdf backend/assets/irs_templates/YYYY/f1040sd.pdf
```

That alone makes the year appear in `get_supported_years()`. Do **not** touch
prior-year folders.

---

## Step 3 — Diff the form field names against the previous year

This is the step that determines whether any code change is needed at all.

```bash
P=YYYY; Q=$((YYYY-1))   # new year and previous year
for f in f8949 f1040sd; do
  pdftk backend/assets/irs_templates/$Q/$f.pdf dump_data_fields | grep FieldName: | sort > /tmp/$f-$Q.txt
  pdftk backend/assets/irs_templates/$P/$f.pdf dump_data_fields | grep FieldName: | sort > /tmp/$f-$P.txt
  echo "=== $f ==="; diff /tmp/$f-$Q.txt /tmp/$f-$P.txt && echo "(identical)"
done
```

(`backend/scripts/extract_fields_8949.py` and `extract_fields_scheduleD.py` do
the same dump via Python if pdftk is awkward.)

### What to look for in `f8949.pdf`

Check each of these against `get_8949_field_config()` in
`backend/services/reports/form_8949.py`:

| Config key | How to read it from the dump |
|------------|------------------------------|
| `table_name_page1` / `table_name_page2` | The container in row fields, e.g. `topmostSubform[0].Page1[0].Table_Line1_Part1[0].Row1[0].f1_03[0]`. 2024 used `Table_Line1` on both pages; 2025 split into `Table_Line1_Part1` (p1) / `Table_Line1_Part2` (p2). |
| `rows_per_page` | Count distinct `RowN[0]` entries inside the page-1 table: `grep -c 'Page1\[0\].*Row[0-9]*\[0\].f1_' /tmp/f8949-$P.txt` then divide by 8 (8 columns per row). **2024 = 14, 2025 = 11.** Getting this wrong silently drops rows — this was a real bug. |
| `row1_base_index` | The first data field number in Row1 (historically `3`, i.e. `f1_3`/`f1_03`). |
| `row1_zero_pad` / `row2_plus_zero_pad` | Are field numbers zero-padded? 2025 pads row 1 only (`f1_03`…`f1_10`) but not rows 2+ (`f1_11`…). Check both row 1 and row 2 explicitly. |
| Page-2 prefix | Part II fields should use `f2_`. Confirm the same row/pad structure holds. |

Each row has 8 data fields = columns (a)–(h); the mapper computes
`base = row1_base_index + (row-1)*8`. If the IRS ever changes the column count
or numbering scheme itself, `map_8949_rows_to_field_data()` needs work — that
has not happened through 2025.

Also check the **checkbox fields** (`c1_1`, `c2_1`, …) and the box letters
printed next to them. The config's `boxes_part1` / `boxes_part2` must list the
letters in the order printed on the form (a test enforces this). If the IRS
changes which box applies to self-custody digital assets, update
`_determine_box()` — 2025 moved crypto from C/F to **I/L**.

### What to look for in `f1040sd.pdf`

The app fills only 8 fields, via `get_schedule_d_field_config()`:
Line 3 (`...Row3[0].f1_15[0]`–`f1_18[0]`) and Line 10
(`...Row10[0].f1_35[0]`–`f1_38[0]`). These were identical for 2024 and 2025.
Confirm those exact field names still exist in the dump; if the IRS renumbers
Schedule D lines, update the config **and** re-check that Line 3 / Line 10 are
still the correct "transactions not reported on a 1099-B" rows (read the form
text, not just field names).

---

## Step 4 — Update the per-year configs (only if the diff showed changes)

In `backend/services/reports/form_8949.py`:

1. `get_8949_field_config(year)` — add a branch for `YYYY`. **Pattern to
   follow:** make the newest year the explicit branch and let the structure
   mirror the existing 2025 branch. If the new year's fields are identical to
   the previous year's, extend the existing branch's condition (e.g.
   `if year >= 2025:`) rather than duplicating the dict — but only after the
   diff in Step 3 proved them identical.
2. `get_schedule_d_field_config(year)` — same approach.
3. `_determine_box()` — only if box letters changed (rare).

**No changes are needed** in `backend/routers/reports.py` (template discovery
and chunking are dynamic), `map_8949_rows_to_field_data()`,
`pdftk_filler.py`, or the frontend (the year dropdown reads
`get_supported_years()`).

---

## Step 5 — Tests

1. **Create `backend/tests/test_YYYY_forms.py`** by copying
   `backend/tests/test_2025_forms.py` and updating:
   - the year constant(s) and acquisition/disposal dates so holding periods
     still split short/long across the new year,
   - the `rows_per_page` expectation (drives the multi-sheet test: seed
     `rows_per_page + 2` short-term disposals and assert none are lost and a
     second sheet is produced),
   - expected page counts.
   The 2025 file's six tests are the template: basic generation, row capacity
   (overflow row survives), multi-sheet page count, Part I/Part II separation,
   Schedule D totals, and prior-year backward compatibility.
2. **Run the suite** (from repo root; venv is `desktop/.venv`):
   ```bash
   PYTHONPATH=$(pwd) desktop/.venv/bin/pytest backend/tests/ \
     --ignore=backend/tests/test_requests.py \
     --ignore=backend/tests/test_transactions.py \
     -v --tb=short
   ```
   All prior-year form tests (e.g. `test_2025_forms.py`) must still pass —
   that's the "without breaking the app" guarantee.
3. **Baseline PDF regression:** `baseline-pdfs/regen_and_diff.sh` must PASS
   (it regenerates the three reports from a frozen seed and text-diffs against
   committed baselines; it exercises prior years, so it proves you didn't
   disturb them).

---

## Step 6 — Manual visual check (do not skip)

Generate a real IRS report for the new year and open it:

```bash
curl -s "http://localhost:8000/api/reports/irs_reports?year=YYYY" -o /tmp/irs-YYYY.pdf && open /tmp/irs-YYYY.pdf
```

(Needs a running backend with test data and pdftk installed; see
"Pytest Suite" notes in CLAUDE.md for starting one against a temp DB.)

Verify with your eyes:
- [ ] Rows land in the visible table cells (not shifted by one column/row)
- [ ] Dates are MM/DD/YYYY, amounts have two decimals
- [ ] Short-term rows are on Part I (page 1), long-term on Part II (page 2)
- [ ] Exactly one box checked per Part: C/F for 2024, **I/L** for 2025+ (self-custody BTC)
- [ ] Column (f) "Code(s)" is empty
- [ ] Schedule D Line 3 and Line 10 totals match the 8949 column (d)/(e)/(h) sums
- [ ] With more rows than `rows_per_page`, a second sheet appears and no rows vanish

---

## Step 7 — Docs, version, release

1. Update the **year-quirks table below** in this file.
2. Add a CHANGELOG entry including the template MD5s and IRS source URLs.
3. Update CLAUDE.md "Recent Changes" / current version.
4. **Bump the minor version** (project convention: new tax-year forms = minor
   bump, e.g. v0.6.x → v0.7.0).
5. Follow the standard release checklist in CLAUDE.md (both remotes, both
   GitHub releases, `./scripts/release-docker.sh vX.Y.Z`).

---

## Year quirks reference (keep current)

| Year | 8949 table names | Rows/page | Zero-padding | Schedule D fields | Notes |
|------|------------------|-----------|--------------|-------------------|-------|
| 2024 | `Table_Line1` (both pages) | **14** | none | Row3 `f1_15–18`, Row10 `f1_35–38` | baseline |
| 2025 | `Table_Line1_Part1` / `Table_Line1_Part2` | **11** | row 1 only (`f1_03`…`f1_10`) | identical to 2024 | Boxes G–L added; C/F now exclude digital assets → app uses **I/L** |

---

## Failure modes seen before (why the steps above exist)

- **Wrong `rows_per_page`** → rows silently dropped past row N. (2025 bug:
  chunked by 14 on an 11-row form.) Step 3's row count + Step 5's overflow
  test catch this.
- **Field name written to a nonexistent field** → pdftk fills nothing for that
  key, silently. (2025 bug: continuous `f3_+` page numbering wrote to fields
  that don't exist.) The Step 6 visual check is the backstop.
- **No box checked / box letter in column (f)** → through v0.7.0 the app never
  set the Part checkboxes and wrote "C"/"F" into the adjustment-code column,
  and kept using C/F in 2025 after the form reserved them for non-digital
  assets. `test_irs_templates.py` now checks the right box per year.
- **XFA forms** → IRS PDFs ship with XFA; `fill_pdf_with_pdftk()` already
  strips it (`drop_xfa`). If a future form won't fill at all, see the XFA
  section of [IRS_FORM_GENERATION.md](IRS_FORM_GENERATION.md).
