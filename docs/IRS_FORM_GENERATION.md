# IRS Form Generation - Technical Documentation

> **CRITICAL:** This document explains how BitcoinTX generates IRS tax forms. This is complex code that uses workarounds for PDF form filling. Keep this document updated whenever changes are made.

**Last Updated:** 2026-01-10

---

## Year-Specific Field Differences (CRITICAL)

> **READ THIS FIRST:** IRS changes PDF field names between years. The field mappings that work for 2024 forms will NOT work for 2025 forms. This section documents known differences.

### Known Differences by Year

| Year | Form 8949 Table Name | Field Format | Checkboxes (Short) | Checkboxes (Long) |
|------|---------------------|--------------|--------------------|--------------------|
| 2024 | `Table_Line1[0]` | `f1_3`, `f1_4` | A, B, C | D, E, F |
| 2025 | `Table_Line1_Part1[0]` (Page 1), `Table_Line1_Part2[0]` (Page 2) | `f1_03`, `f1_04` (zero-padded) | A, B, C, G, H, I | D, E, F, J, K, L |

### 2024 → 2025 Breaking Changes

The IRS made significant field name changes for 2025:

**1. Table Name Changed:**
```
# 2024
topmostSubform[0].Page1[0].Table_Line1[0].Row1[0].f1_3[0]

# 2025
topmostSubform[0].Page1[0].Table_Line1_Part1[0].Row1[0].f1_03[0]
```

**2. Field Numbers Are Zero-Padded:**
```
# 2024: f1_3, f1_4, f1_5 ...
# 2025: f1_03, f1_04, f1_05 ...
```

**3. New Checkboxes for Form 1099-DA:**

| Box | Holding Period | Form 1099-DA | Basis Reported |
|-----|----------------|--------------|----------------|
| G | Short-term | Yes | Yes |
| H | Short-term | Yes | No |
| I | Short-term | Yes | Unknown |
| J | Long-term | Yes | Yes |
| K | Long-term | Yes | No |
| L | Long-term | Yes | Unknown |

**4. Schedule D Field Changes:**
```
# 2024: f1_07, f1_08, f1_01, f1_02
# 2025: f1_7, f1_8, f1_1, f1_2 (NOT zero-padded, opposite of Form 8949!)
```

### How to Discover Field Names for New Years

```bash
# Extract all field names from a PDF
pdftk backend/assets/irs_templates/2025/f8949.pdf dump_data_fields | grep FieldName

# Compare two years
pdftk backend/assets/irs_templates/2024/f8949.pdf dump_data_fields | grep FieldName > /tmp/2024.txt
pdftk backend/assets/irs_templates/2025/f8949.pdf dump_data_fields | grep FieldName > /tmp/2025.txt
diff /tmp/2024.txt /tmp/2025.txt
```

---

## Dynamic Template and Field Selection (REQUIRED)

### Template Path Selection

The code MUST select the correct template folder based on the `year` parameter:

```python
# In reports.py - REQUIRED PATTERN
def get_template_path(year: int, form_name: str) -> str:
    """Get the template path for a specific tax year."""
    template_path = os.path.join(_ASSETS_DIR, str(year), form_name)
    if not os.path.exists(template_path):
        raise HTTPException(
            status_code=400,
            detail=f"No template available for tax year {year}"
        )
    return template_path

# Usage
form_8949_path = get_template_path(year, "f8949.pdf")
schedule_d_path = get_template_path(year, "f1040sd.pdf")
```

### Field Mapping Selection

Field mappings vary by year. The code MUST use year-specific mappings:

**Option A: In-Code Mappings (Current Approach)**
```python
# In form_8949.py
def get_8949_field_config(year: int) -> dict:
    """Return year-specific field configuration."""
    if year >= 2025:
        return {
            "table_name_page1": "Table_Line1_Part1",
            "table_name_page2": "Table_Line1_Part2",
            "field_format": "{:02d}",  # Zero-padded
            "boxes_part1": ["A", "B", "C", "G", "H", "I"],
            "boxes_part2": ["D", "E", "F", "J", "K", "L"],
        }
    else:  # 2024 and earlier
        return {
            "table_name_page1": "Table_Line1",
            "table_name_page2": "Table_Line1",
            "field_format": "{}",  # Not zero-padded
            "boxes_part1": ["A", "B", "C"],
            "boxes_part2": ["D", "E", "F"],
        }
```

**Option B: Config Files Per Year (Alternative)**
```
backend/assets/irs_templates/
├── 2024/
│   ├── f8949.pdf
│   ├── f1040sd.pdf
│   └── field_config.json    # Year-specific field mappings
├── 2025/
│   ├── f8949.pdf
│   ├── f1040sd.pdf
│   └── field_config.json
```

### Supported Years Validation

The API should validate that templates exist for the requested year:

```python
def get_supported_years() -> list[int]:
    """Return list of years with available templates."""
    years = []
    for item in os.listdir(_ASSETS_DIR):
        item_path = os.path.join(_ASSETS_DIR, item)
        if os.path.isdir(item_path) and item.isdigit():
            # Check that required templates exist
            if (os.path.exists(os.path.join(item_path, "f8949.pdf")) and
                os.path.exists(os.path.join(item_path, "f1040sd.pdf"))):
                years.append(int(item))
    return sorted(years)

# In endpoint
@router.get("/irs_reports")
def get_irs_reports(year: int, db: Session = Depends(get_db)):
    supported = get_supported_years()
    if year not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Tax year {year} not supported. Available years: {supported}"
        )
    # ... continue with generation
```

---

## Overview

BitcoinTX generates three types of tax reports:

| Report | Endpoint | Method | Output |
|--------|----------|--------|--------|
| **IRS Reports** | `/api/reports/irs_reports` | pdftk form filling | Form 8949 + Schedule D (official IRS forms) |
| **Complete Tax Report** | `/api/reports/complete_tax_report` | ReportLab from scratch | Custom PDF with all tax data |
| **Transaction History** | `/api/reports/simple_transaction_history` | CSV or ReportLab | Raw transaction list |

The IRS Reports endpoint is the most complex because it fills official IRS PDF forms.

---

## The XFA Problem and Our Workaround

### Why This Is Hard

IRS fillable PDFs use **XFA (XML Forms Architecture)**, a complex Adobe format that most PDF libraries cannot handle. Standard Python PDF libraries (PyPDF, reportlab) cannot fill XFA forms.

### Our Solution: pdftk

We use `pdftk` (PDF Toolkit) with a multi-step workaround:

```
1. pdftk template.pdf output no_xfa.pdf drop_xfa
   → Removes XFA, exposing the underlying AcroForm fields

2. Generate FDF (Forms Data Format) file with field values
   → Simple text format that maps field names to values

3. pdftk no_xfa.pdf fill_form data.fdf output filled.pdf flatten
   → Fills the form and flattens (locks) it
```

**This is a hack**, but it works reliably for IRS forms.

---

## Multi-Year Form Strategy

**Design Decision:** The app maintains all historical IRS form templates, allowing users to generate reports for any supported tax year.

### Directory Structure

```
backend/assets/irs_templates/
├── 2024/
│   ├── f8949.pdf
│   └── f1040sd.pdf
├── 2025/
│   ├── f8949.pdf
│   └── f1040sd.pdf
└── 2026/
    └── (added January 2027)
```

### Why This Approach

1. **Single codebase** - No maintaining multiple app versions
2. **Amended returns** - Users can file late/amended returns for prior years
3. **Simple updates** - New tax year = new folder + any field mapping changes
4. **No version rollback** - Users always have latest app with all form years

### Adding New Tax Year Forms

When IRS releases new forms (typically late December):
1. Create new year folder in `backend/assets/irs_templates/`
2. Download fillable PDFs from IRS.gov
3. Extract and compare field names (see "Updating for New Tax Years" section)
4. Update field mappings if changed
5. Bump minor version (e.g., v0.3.0 for 2025 forms)

---

## File Structure

```
backend/
├── assets/irs_templates/
│   └── [year]/                        # One folder per tax year
│       ├── f8949.pdf                  # IRS Form 8949 template
│       └── f1040sd.pdf                # IRS Schedule D template
├── services/reports/
│   ├── pdftk_filler.py                # Core pdftk operations
│   ├── pdf_utils.py                   # PDF flattening utility
│   ├── form_8949.py                   # Data model & field mapping
│   ├── complete_tax_report.py         # ReportLab-based report
│   ├── transaction_history.py         # CSV/PDF export
│   └── reporting_core.py              # Data aggregation
├── routers/
│   └── reports.py                     # API endpoints
└── scripts/
    ├── extract_fields_8949.py         # Utility to discover field names
    └── inspect_8949_fields.py         # Field inspection tool
```

---

## How Form 8949 Generation Works

### Step-by-Step Process

1. **Query Database**: Get all `LotDisposal` records for the tax year
2. **Build Rows**: Convert each disposal to a `Form8949Row` object
3. **Separate by Holding Period**: Split into short-term and long-term lists
4. **Chunk into Pages**: Each Form 8949 page holds 14 rows max
5. **Map to Field Names**: Convert row data to PDF field names
6. **Fill Each Page**: Use pdftk to fill the template for each chunk
7. **Fill Schedule D**: Fill summary totals
8. **Merge Pages**: Combine all pages with pypdf
9. **Flatten**: Final pdftk flatten to lock the form

### Code Flow

```
GET /api/reports/irs_reports?year=2024
    ↓
reports.py: get_irs_reports()
    ↓
form_8949.py: build_form_8949_and_schedule_d()
    → Queries LotDisposal records
    → Creates Form8949Row objects
    → Separates short/long term
    → Calculates Schedule D totals
    ↓
reports.py: Loop through chunks of 14 rows
    ↓
form_8949.py: map_8949_rows_to_field_data()
    → Converts rows to {field_name: value} dict
    ↓
pdftk_filler.py: fill_pdf_with_pdftk()
    → Generates FDF
    → Calls pdftk drop_xfa
    → Calls pdftk fill_form + flatten
    ↓
reports.py: _merge_all_pdfs()
    → Combines pages with pypdf
    ↓
pdf_utils.py: flatten_pdf_with_pdftk()
    → Final flatten pass
    ↓
Return PDF bytes
```

---

## Form 8949 Field Mapping

> **Note:** This section shows the 2024 field patterns. See "Year-Specific Field Differences" above for 2025+ changes.

### Field Naming Convention (2024)

IRS PDF forms use deeply nested XPath-style field names:

```
topmostSubform[0].Page1[0].Table_Line1[0].Row1[0].f1_3[0]
                 ↑         ↑              ↑       ↑
                 Page      Table name     Row     Field index
```

**For 2025+**, the pattern changes to:
```
topmostSubform[0].Page1[0].Table_Line1_Part1[0].Row1[0].f1_03[0]
                          ↑                            ↑
                          Part1 or Part2               Zero-padded
```

### Row Field Indices

Each row has 8 columns (a-h) with consecutive field indices:

| Column | Content | Offset from Base |
|--------|---------|------------------|
| (a) | Description of property | +0 |
| (b) | Date acquired | +1 |
| (c) | Date sold | +2 |
| (d) | Proceeds | +3 |
| (e) | Cost or other basis | +4 |
| (f) | Code (if any) | +5 |
| (g) | Adjustment | +6 |
| (h) | Gain or (loss) | +7 |

### Base Index Calculation

```python
# Row 1 starts at index 3
# Each row adds 8 to the base
base_index = 3 + (row_number - 1) * 8

# Examples:
# Row 1: base = 3  → fields f1_3 through f1_10
# Row 2: base = 11 → fields f1_11 through f1_18
# Row 3: base = 19 → fields f1_19 through f1_26
# ...
# Row 14: base = 107 → fields f1_107 through f1_114
```

### Full Field Name Construction

**2024 Version:**
```python
def field_name_2024(page: int, row: int, field_offset: int) -> str:
    base_index = 3 + (row - 1) * 8
    field_no = base_index + field_offset
    return f"topmostSubform[0].Page{page}[0].Table_Line1[0].Row{row}[0].f{page}_{field_no}[0]"
```

**2025+ Version:**
```python
def field_name_2025(page: int, row: int, field_offset: int) -> str:
    base_index = 3 + (row - 1) * 8
    field_no = base_index + field_offset
    # Part1 for short-term (Page 1), Part2 for long-term (Page 2)
    part = "Part1" if page == 1 else "Part2"
    # Zero-pad field numbers
    return f"topmostSubform[0].Page{page}[0].Table_Line1_{part}[0].Row{row}[0].f{page}_{field_no:02d}[0]"
```

### Multi-Page Handling

When there are more than 14 rows:
- Rows 1-14 → Page 1 (field prefix `f1_`)
- Rows 15-28 → Page 2 (field prefix `f2_`)
- etc.

**Important**: The page number in the field name changes (`f1_`, `f2_`, `f3_`...).

---

## Schedule D Field Mapping

Schedule D summarizes the Form 8949 totals.

> **Note:** Schedule D field naming is inconsistent with Form 8949. In 2025, Schedule D uses NON-zero-padded field numbers while Form 8949 uses zero-padded.

### Short-Term (Part I, Line 1b)

**2024:**
```python
"topmostSubform[0].Page1[0].Table_PartI[0].Row1b[0].f1_07[0]"  # Proceeds
"topmostSubform[0].Page1[0].Table_PartI[0].Row1b[0].f1_08[0]"  # Cost
"topmostSubform[0].Page1[0].Table_PartI[0].Row1b[0].f1_09[0]"  # Adjustment (empty)
"topmostSubform[0].Page1[0].Table_PartI[0].Row1b[0].f1_10[0]"  # Gain/Loss
```

**2025:**
```python
"topmostSubform[0].Page1[0].Table_PartI[0].Row1b[0].f1_7[0]"   # Proceeds (NOT zero-padded!)
"topmostSubform[0].Page1[0].Table_PartI[0].Row1b[0].f1_8[0]"   # Cost
"topmostSubform[0].Page1[0].Table_PartI[0].Row1b[0].f1_9[0]"   # Adjustment (empty)
"topmostSubform[0].Page1[0].Table_PartI[0].Row1b[0].f1_10[0]"  # Gain/Loss
```

### Long-Term (Part II, Line 8b)

**2024:**
```python
"topmostSubform[0].Page1[0].Table_PartII[0].Row8b[0].f1_27[0]"  # Proceeds
"topmostSubform[0].Page1[0].Table_PartII[0].Row8b[0].f1_28[0]"  # Cost
"topmostSubform[0].Page1[0].Table_PartII[0].Row8b[0].f1_29[0]"  # Adjustment (empty)
"topmostSubform[0].Page1[0].Table_PartII[0].Row8b[0].f1_30[0]"  # Gain/Loss
```

**2025:** (Same field names - no changes detected)

---

## Checkbox Logic (Box Selection)

Form 8949 has checkboxes to indicate the type of transaction. **These changed significantly in 2025.**

### 2024 Checkboxes

| Box | Holding Period | Form Type | Basis Reported |
|-----|----------------|-----------|----------------|
| A | Short-term | 1099-B | Yes |
| B | Short-term | 1099-B | No |
| C | Short-term | No 1099-B | N/A |
| D | Long-term | 1099-B | Yes |
| E | Long-term | 1099-B | No |
| F | Long-term | No 1099-B | N/A |

```python
# 2024 Implementation
def _determine_box_2024(holding_period: str, basis_reported: bool):
    if holding_period == "LONG":
        return "D" if basis_reported else "F"
    return "A" if basis_reported else "C"
```

### 2025 Checkboxes (NEW - Includes Form 1099-DA)

Wording from the 2025 form itself. Note that Box C/F now **exclude digital
assets** — crypto can no longer go in C/F.

| Box | Holding Period | Meaning |
|-----|----------------|---------|
| A / D | Short / Long | Reported on 1099-B, basis reported |
| B / E | Short / Long | Reported on 1099-B, basis not reported |
| C / F | Short / Long | **Other than digital assets**, not on 1099-B or 1099-DA |
| **G / J** | Short / Long | Reported on **1099-DA**, basis reported |
| **H / K** | Short / Long | Reported on **1099-DA**, basis not reported |
| **I / L** | Short / Long | **Digital assets not reported** on 1099-DA or 1099-B |

```python
# form_8949._determine_box(holding_period, basis_reported, year)
# self-custody BTC with no broker form: 2024 -> C/F, 2025+ -> I/L
```

### Checkbox Field Names

**2024:** 3 checkboxes per part
```
topmostSubform[0].Page1[0].c1_1[0]  # Box A
topmostSubform[0].Page1[0].c1_1[1]  # Box B
topmostSubform[0].Page1[0].c1_1[2]  # Box C
```

**2025:** 6 checkboxes per part
```
topmostSubform[0].Page1[0].c1_1[0]  # Box A
topmostSubform[0].Page1[0].c1_1[1]  # Box B
topmostSubform[0].Page1[0].c1_1[2]  # Box C
topmostSubform[0].Page1[0].c1_1[3]  # Box G (NEW)
topmostSubform[0].Page1[0].c1_1[4]  # Box H (NEW)
topmostSubform[0].Page1[0].c1_1[5]  # Box I (NEW)
```

### How the box is written

`map_8949_rows_to_field_data()` checks exactly one box per Part: the widget
`c{page}_1[i]` whose on-state is `/(i+1)`, where `i` is the box's position in
the year config's `boxes_part1` / `boxes_part2` (top-to-bottom order printed on
the form, verified by `test_box_labels_match_template_text`). `generate_fdf()`
writes values starting with `/` as PDF names (`/V /6`), which checkboxes need.
Column (f) "Code(s)" is left blank — the box letter never goes there.

### Note on 1099-DA

Starting with 2025 sales, US brokers (including River) issue Form 1099-DA.
Disposals a broker reported belong in Box H/K (or G/J once basis reporting
starts). The app currently puts every disposal in I/L; `basis_reported_flags`
and `_determine_box()` are the hooks for broker-reported rows.

---

## FDF Generation

FDF (Forms Data Format) is a simple text format for PDF form data:

```fdf
%FDF-1.2
1 0 obj <<
/FDF << /Fields [
<< /T (field_name_1) /V (value_1) >>
<< /T (field_name_2) /V (value_2) >>
] >>
>>
endobj
trailer
<< /Root 1 0 R >>
%%EOF
```

The `generate_fdf()` function in `pdftk_filler.py` creates this format.

**Important**: Parentheses in field names or values must be escaped with backslashes.

---

## Dependencies

### Required for IRS Forms

- **pdftk** (or pdftk-java): Form filling and flattening
  - macOS: `brew install pdftk-java`
  - Linux: `apt-get install pdftk`
  - Docker: Installed via Dockerfile

- **pypdf**: PDF reading and merging (pure Python)

### Required for Other Reports

- **ReportLab**: PDF generation from scratch (Complete Tax Report, Transaction History PDF)

---

## Docker Considerations

The Dockerfile must include pdftk:

```dockerfile
# Install pdftk for PDF form filling
RUN apt-get update && apt-get install -y pdftk
```

Template paths use absolute paths based on `__file__`:

```python
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
_ASSETS_DIR = os.path.join(_BACKEND_DIR, "assets", "irs_templates")
```

---

## Updating for New Tax Years

**Follow the dedicated runbook: [IRS_ANNUAL_FORM_UPDATE.md](IRS_ANNUAL_FORM_UPDATE.md).**

Summary of the current (post-v0.6.0) process — the runbook has the details:

1. Download the final-revision PDFs from the IRS (`irs.gov/pub/irs-prior/f8949--YYYY.pdf` once archived, or `irs.gov/pub/irs-pdf/` during the season; never `irs-dft` drafts) and record MD5s.
2. Save as `backend/assets/irs_templates/YYYY/f8949.pdf` and `f1040sd.pdf` — `get_supported_years()` auto-detects the folder; there are no path constants to update.
3. Diff field names against the prior year (`pdftk ... dump_data_fields`) and, only if they changed, add a year branch to `get_8949_field_config()` / `get_schedule_d_field_config()` in `form_8949.py` (and `_determine_box()` if box letters changed).
4. Copy `test_2025_forms.py` to `test_YYYY_forms.py`, adjust year/rows-per-page expectations, run the full suite plus `baseline-pdfs/regen_and_diff.sh`, and do the manual visual check.
5. Bump the minor version and release per CLAUDE.md.

---

## Troubleshooting

### "pdftk not found"

```
HTTPException: pdftk is not installed or not in PATH
```

**Solution**: Install pdftk (`brew install pdftk-java` on macOS)

### "Template PDF not found"

```
HTTPException: Missing IRS template PDFs
```

**Solution**: Verify templates exist in `backend/assets/irs_templates/`

### Fields Not Filling

Possible causes:
1. Field names changed in new IRS form version
2. XFA not properly removed
3. FDF escaping issue with special characters

**Debug**:
```bash
# List fields in a PDF
pdftk Form_8949_Fillable_2024.pdf dump_data_fields
```

### Multi-Page Issues

If pages aren't merging correctly:
1. Check that page prefix (`f1_`, `f2_`) matches the page number
2. Verify pypdf merge is including all pages
3. Check for exceptions in the chunk loop

---

## Alternative Approaches (Not Currently Used)

### ReportLab-Only Approach

Instead of filling IRS forms, generate custom PDFs that replicate the form layout. This would:
- Remove pdftk dependency
- Be more maintainable
- But NOT produce official IRS forms

The Complete Tax Report already uses this approach for non-IRS documentation.

### Browser-Based PDF Filling

Use JavaScript PDF libraries in the frontend to fill forms client-side. This would:
- Remove server-side PDF processing
- But require sending templates to client
- And may have browser compatibility issues

### Commercial PDF APIs

Services like Adobe PDF Services or DocuSign can fill forms. This would:
- Be more reliable
- But add cost and external dependency
- And require API keys / internet access

---

## Related Documentation

- [STARTOS_COMPATIBILITY.md](STARTOS_COMPATIBILITY.md) - Docker requirements
- [CHANGELOG.md](CHANGELOG.md) - Version history
- [ROADMAP.md](ROADMAP.md) - Future plans including 2025 form updates

---

## Contact / Questions

If you're working on this code and have questions:
1. Read this document thoroughly first
2. Check the scripts in `backend/scripts/` for field inspection
3. Test with `pdftk dump_data_fields` to see actual field names
4. Update this document with any new findings
