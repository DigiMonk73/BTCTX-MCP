"""
backend/tests/test_irs_templates.py

Guards the yearly IRS template update. For EVERY year folder in
backend/assets/irs_templates/ (auto-discovered, so a new year is tested the
moment its PDFs are dropped in), fill the real template with a full page of
rows and read the fields back:

  - every field name the app writes must exist in the template
    (a renamed field must fail loudly, not print a blank form)
  - every value must land where it was written
  - exactly one box is checked per Part, and it is the right one
  - line 2 "Totals" fields sit under their columns and get the page's sums
  - Schedule D totals land on lines 1b, 2, 3, 8b, 9 and 10

Pure Python (pypdf) — no external tools needed.
"""

import io
import os
from decimal import Decimal

import pytest
from pypdf import PdfReader

from backend.routers.reports import get_supported_years, get_template_path
from backend.services.reports.form_8949 import (
    Form8949Row,
    _determine_box,
    get_8949_field_config,
    line2_field_names,
    map_8949_rows_to_field_data,
    map_schedule_d_fields,
)
from backend.services.reports.pdf_form_filler import fill_pdf_form

YEARS = get_supported_years()


def _fill_without_flatten(template: str, field_data: dict) -> dict:
    """Fill (keeping the form fields) and return the resulting PDF's fields."""
    return PdfReader(io.BytesIO(fill_pdf_form(template, field_data, flatten=False))).get_fields()


def _rows(year: int, hp: str, n: int, box: str = None):
    box = box or _determine_box(hp, False, year)
    return [
        Form8949Row(
            description=f"0.00{i:02d} BTC", date_acquired="01/15/2020",
            date_sold=f"06/{i + 1:02d}/{year}", proceeds=Decimal(f"{1000 + i}.00"),
            cost=Decimal(f"{400 + i}.00"), gain_loss=Decimal("600.00"),
            holding_period=hp, box=box,
        )
        for i in range(n)
    ]


def test_years_discovered():
    assert 2024 in YEARS and 2025 in YEARS


@pytest.mark.parametrize("year", YEARS)
def test_year_has_explicit_config(year):
    """A new year folder must come with a reviewed config, not silently inherit
    the previous year's (see docs/IRS_ANNUAL_FORM_UPDATE.md)."""
    config = get_8949_field_config(year)
    assert year in config["verified_years"], (
        f"{year} templates are present but get_8949_field_config has not been "
        f"verified for {year}. Run: python scripts/irs_new_year.py {year} --check"
    )


@pytest.mark.parametrize("year", YEARS)
def test_form_8949_full_page_lands_exactly(year):
    per_page = get_8949_field_config(year)["rows_per_page"]
    field_data = {}
    field_data.update(map_8949_rows_to_field_data(_rows(year, "SHORT", per_page), page=1, year=year))
    field_data.update(map_8949_rows_to_field_data(_rows(year, "LONG", per_page), page=2, year=year))

    filled = _fill_without_flatten(get_template_path(year, "f8949.pdf"), field_data)

    missing = sorted(k for k in field_data if k not in filled)
    assert not missing, f"{year}: {len(missing)} field names not in template, e.g. {missing[:3]}"

    not_landed = [
        (k, v, filled[k].get("/V"))
        for k, v in field_data.items()
        if (filled[k].get("/V") or "") != v
    ]
    assert not not_landed, f"{year}: values did not land: {not_landed[:3]}"


@pytest.mark.parametrize("year", YEARS)
def test_form_8949_checks_exactly_the_right_box(year):
    config = get_8949_field_config(year)
    field_data = {}
    field_data.update(map_8949_rows_to_field_data(_rows(year, "SHORT", 1), page=1, year=year))
    field_data.update(map_8949_rows_to_field_data(_rows(year, "LONG", 1), page=2, year=year))
    filled = _fill_without_flatten(get_template_path(year, "f8949.pdf"), field_data)

    for page, part_boxes, hp in ((1, config["boxes_part1"], "SHORT"), (2, config["boxes_part2"], "LONG")):
        checked = [k for k, v in filled.items()
                   if f"Page{page}[0].c{page}_1" in k and v.get("/V") not in (None, "/Off")]
        assert len(checked) == 1, f"{year} Part {page}: checked boxes = {checked}"
        expected = part_boxes.index(_determine_box(hp, False, year))
        assert checked[0].endswith(f"c{page}_1[{expected}]"), checked


@pytest.mark.parametrize("year", YEARS)
def test_every_box_letter_checks_its_own_widget(year):
    """All boxes the form defines, not just the defaults: a 1099-DA override
    (transactions.broker_reporting) can select any of them."""
    config = get_8949_field_config(year)
    for page, part_boxes, hp in ((1, config["boxes_part1"], "SHORT"), (2, config["boxes_part2"], "LONG")):
        for index, box in enumerate(part_boxes):
            field_data = map_8949_rows_to_field_data(_rows(year, hp, 1, box=box), page=page, year=year)
            filled = _fill_without_flatten(get_template_path(year, "f8949.pdf"), field_data)
            checked = [k for k, v in filled.items()
                       if f"Page{page}[0].c{page}_1" in k and v.get("/V") not in (None, "/Off")]
            assert len(checked) == 1 and checked[0].endswith(f"c{page}_1[{index}]"), (year, box, checked)


@pytest.mark.parametrize("year", YEARS)
def test_box_labels_match_template_text(year):
    """The box order in the config must match the order printed on the form."""
    import re
    reader = PdfReader(get_template_path(year, "f8949.pdf"))
    config = get_8949_field_config(year)
    for page, boxes in ((0, config["boxes_part1"]), (1, config["boxes_part2"])):
        printed = re.findall(r"\(([A-L])\)\s+(?:Short|Long)-term", reader.pages[page].extract_text())
        assert printed == boxes, f"{year} page {page + 1}: form shows {printed}, config has {boxes}"


def _widget_rects(template: str) -> dict:
    """Full field name -> widget rectangle [x1, y1, x2, y2] (points)."""
    rects = {}
    for page in PdfReader(template).pages:
        for annot in page.get("/Annots", []):
            widget = annot.get_object()
            if widget.get("/Subtype") != "/Widget":
                continue
            names, node = [], widget
            while node is not None:
                if "/T" in node:
                    names.append(str(node["/T"]))
                parent = node.get("/Parent")
                node = parent.get_object() if parent is not None else None
            rects[".".join(reversed(names))] = [float(v) for v in widget["/Rect"]]
    return rects


@pytest.mark.parametrize("year", YEARS)
def test_line_2_totals_fields_sit_under_their_columns(year):
    """Bug hunt 2026-09-29: Form 8949 line 2. The configured line-2 fields
    must be the Totals line: each one under its column (same x as the last
    row's (d)..(h)) and below the last row, on both pages. Field names alone
    would still match a renumbered form that means something else."""
    n = get_8949_field_config(year)["rows_per_page"]
    rects = _widget_rects(get_template_path(year, "f8949.pdf"))
    for page, hp in ((1, "SHORT"), (2, "LONG")):
        row_fields = map_8949_rows_to_field_data(_rows(year, hp, n), page=page, year=year)
        last_row = dict(zip("abcdefgh", [k for k in row_fields if f".Row{n}[0]." in k]))
        for col, name in line2_field_names(page, year).items():
            total, cell = rects[name], rects[last_row[col]]
            assert abs(total[0] - cell[0]) < 1 and abs(total[2] - cell[2]) < 1, (year, page, col, total, cell)
            assert total[3] <= cell[1], f"{year} page {page} ({col}): {name} is not below row {n}"


@pytest.mark.parametrize("year", YEARS)
def test_line_2_totals_are_the_sum_of_the_page_rows(year):
    """Bug hunt 2026-09-29: Form 8949 line 2 ("Totals" of (d), (e), (g), (h))
    was never filled. It totals this page's rows to the cent, losses
    subtracted; (f) and (g) stay blank like the rows'."""
    amounts = [("1000.10", "400.05", "600.05"), ("150.10", "200.00", "-49.90"), ("0.01", "0.02", "-0.01")]
    for page, hp in ((1, "SHORT"), (2, "LONG")):
        rows = [
            Form8949Row(f"0.00{i} BTC", "01/15/2020", f"06/0{i + 1}/{year}", Decimal(d), Decimal(e),
                        Decimal(h), hp, _determine_box(hp, False, year))
            for i, (d, e, h) in enumerate(amounts)
        ]
        field_data = map_8949_rows_to_field_data(rows, page=page, year=year)
        line2 = line2_field_names(page, year)
        assert {col: field_data[line2[col]] for col in "defgh"} == {
            "d": "1150.21", "e": "600.07", "f": "", "g": "", "h": "550.14"}
        filled = _fill_without_flatten(get_template_path(year, "f8949.pdf"), field_data)
        assert (filled[line2["h"]].get("/V"), filled[line2["d"]].get("/V")) == ("550.14", "1150.21")
    # A Part with no rows (e.g. no long-term sales) leaves line 2 blank
    assert not set(line2_field_names(1, year).values()) & set(map_8949_rows_to_field_data([], page=1, year=year))


def test_self_custody_btc_boxes():
    assert (_determine_box("SHORT", False, 2024), _determine_box("LONG", False, 2024)) == ("C", "F")
    # 2025+: Box C/F exclude digital assets; I/L = digital assets not on a 1099
    assert (_determine_box("SHORT", False, 2025), _determine_box("LONG", False, 2025)) == ("I", "L")


@pytest.mark.parametrize("year", YEARS)
def test_schedule_d_all_8949_lines_land(year):
    """Lines 1b, 2, 3 (Part I) and 8b, 9, 10 (Part II) — one per 8949 box pair."""
    lines = {
        line: {"proceeds": Decimal(f"{100 * i + 1}.00"), "cost": Decimal(f"{10 * i}.00"),
               "gain_loss": Decimal(f"{90 * i + 1}.00")}
        for i, line in enumerate(("1b", "2", "3", "8b", "9", "10"), start=1)
    }
    field_data = map_schedule_d_fields({"lines": lines}, year=year)
    assert len(field_data) == 24
    filled = _fill_without_flatten(get_template_path(year, "f1040sd.pdf"), field_data)
    for k, v in field_data.items():
        assert k in filled, f"{year} Schedule D field missing: {k}"
        assert (filled[k].get("/V") or "") == v, (k, v, filled[k].get("/V"))


@pytest.mark.parametrize("year", YEARS)
def test_unknown_field_name_fails_loudly(year):
    """A renamed IRS field must raise, never silently print a blank form."""
    with pytest.raises(ValueError, match="not in"):
        fill_pdf_form(get_template_path(year, "f8949.pdf"), {"topmostSubform[0].Page1[0].nope[0]": "x"})


@pytest.mark.parametrize("year", YEARS)
def test_flattened_output_has_no_form_fields_and_keeps_values(year):
    config = get_8949_field_config(year)
    field_data = map_8949_rows_to_field_data(_rows(year, "SHORT", config["rows_per_page"]), page=1, year=year)
    reader = PdfReader(io.BytesIO(fill_pdf_form(get_template_path(year, "f8949.pdf"), field_data)))
    assert not reader.get_fields()
    text = reader.pages[0].extract_text()
    assert "1000.00" in text and "600.00" in text and f"06/01/{year}" in text


@pytest.mark.parametrize("year", YEARS)
def test_flattened_sheet_stays_small(year):
    # Flattening orphans the widgets' appearance streams; unless they are
    # dropped a full 8949 sheet is ~5 MB (a 20-sheet report ~100 MB).
    config = get_8949_field_config(year)
    field_data = map_8949_rows_to_field_data(_rows(year, "SHORT", config["rows_per_page"]), page=1, year=year)
    template = get_template_path(year, "f8949.pdf")
    size = len(fill_pdf_form(template, field_data))
    assert size < 3 * os.path.getsize(template), f"{size // 1024} KB"
