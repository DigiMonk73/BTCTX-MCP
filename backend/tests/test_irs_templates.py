"""
backend/tests/test_irs_templates.py

Guards the yearly IRS template update. For EVERY year folder in
backend/assets/irs_templates/ (auto-discovered, so a new year is tested the
moment its PDFs are dropped in), fill the real template with a full page of
rows and read the fields back:

  - every field name the app writes must exist in the template
    (pdftk silently drops unknown names -> blank forms with no error)
  - every value must land where it was written
  - exactly one box is checked per Part, and it is the right one
  - Schedule D totals land on lines 1b, 2, 3, 8b, 9 and 10

Requires pdftk (skipped otherwise); CI installs it.
"""

import os
import shutil
import subprocess
import tempfile
from decimal import Decimal

import pytest
from pypdf import PdfReader

from backend.routers.reports import get_supported_years, get_template_path
from backend.services.reports.form_8949 import (
    Form8949Row,
    _determine_box,
    get_8949_field_config,
    map_8949_rows_to_field_data,
    map_schedule_d_fields,
)
from backend.services.reports.pdftk_filler import generate_fdf
from backend.services.reports.pdftk_path import find_pdftk

YEARS = get_supported_years()
PDFTK = find_pdftk() or shutil.which("pdftk")
needs_pdftk = pytest.mark.skipif(not PDFTK, reason="pdftk not installed")


def _fill_without_flatten(template: str, field_data: dict) -> dict:
    """Fill with pdftk (no flatten) and return the resulting PDF's fields."""
    with tempfile.TemporaryDirectory() as d:
        fdf, out = os.path.join(d, "data.fdf"), os.path.join(d, "out.pdf")
        with open(fdf, "w", encoding="utf-8") as fh:
            fh.write(generate_fdf(field_data))
        subprocess.run([PDFTK, template, "fill_form", fdf, "output", out],
                       check=True, capture_output=True)
        return PdfReader(out).get_fields()


def _rows(year: int, hp: str, n: int):
    box = _determine_box(hp, False, year)
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


@needs_pdftk
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
        if not v.startswith("/") and (filled[k].get("/V") or "") != v
    ]
    assert not not_landed, f"{year}: values did not land: {not_landed[:3]}"


@needs_pdftk
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
def test_box_labels_match_template_text(year):
    """The box order in the config must match the order printed on the form."""
    import re
    reader = PdfReader(get_template_path(year, "f8949.pdf"))
    config = get_8949_field_config(year)
    for page, boxes in ((0, config["boxes_part1"]), (1, config["boxes_part2"])):
        printed = re.findall(r"\(([A-L])\)\s+(?:Short|Long)-term", reader.pages[page].extract_text())
        assert printed == boxes, f"{year} page {page + 1}: form shows {printed}, config has {boxes}"


def test_self_custody_btc_boxes():
    assert (_determine_box("SHORT", False, 2024), _determine_box("LONG", False, 2024)) == ("C", "F")
    # 2025+: Box C/F exclude digital assets; I/L = digital assets not on a 1099
    assert (_determine_box("SHORT", False, 2025), _determine_box("LONG", False, 2025)) == ("I", "L")


@needs_pdftk
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
