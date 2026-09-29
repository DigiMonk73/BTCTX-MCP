#!/usr/bin/env python3
"""
Add (or check) a tax year's IRS Form 8949 + Schedule D templates.

    python scripts/irs_new_year.py 2026            # download from irs.gov, verify, install
    python scripts/irs_new_year.py 2026 --check    # verify an already-installed year
    python scripts/irs_new_year.py 2026 --from-dir ~/Downloads   # use PDFs you downloaded
    python scripts/irs_new_year.py --watch         # CI: is a new final form out yet?
    python scripts/irs_new_year.py --draft         # preview: check the IRS DRAFT forms now

What it verifies (the things that silently break printed forms):
  1. It's the FINAL form for that year, not a draft or another year.
  2. Every field name the app writes (rows and line 2 totals) exists in the
     new template, the line 2 totals sit under their columns below the last
     row, and the checkbox order matches the boxes printed on the form.
  3. Field-name differences vs the previous year, so you know whether
     get_8949_field_config needs a new branch.
Then it runs backend/tests/test_irs_templates.py.

If everything matches, the last manual step is adding the year to
"verified_years" in backend/services/reports/form_8949.py (the tests
refuse to pass until you do — that's deliberate: a human looks once a year).
Full procedure: docs/IRS_ANNUAL_FORM_UPDATE.md
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from collections import Counter
from pathlib import Path

logging.disable(logging.CRITICAL)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TEMPLATES = ROOT / "backend" / "assets" / "irs_templates"
FORMS = {"f8949.pdf": "8949", "f1040sd.pdf": "Schedule D"}
DRAFT_URL = "https://www.irs.gov/pub/irs-dft/{stem}--dft.pdf"
URLS = [
    "https://www.irs.gov/pub/irs-prior/{stem}--{year}.pdf",  # archive: unambiguous year
    "https://www.irs.gov/pub/irs-pdf/{stem}.pdf",            # current filing season
]

from pypdf import PdfReader  # noqa: E402


def say(ok: bool, msg: str) -> bool:
    print(f"  {'✓' if ok else '✗'} {msg}")
    return ok


def form_year(path: Path) -> int | None:
    """Tax year printed on the form, e.g. 'Form 8949 (2025)' / 'Schedule D (Form 1040) 2025'."""
    text = " ".join((p.extract_text() or "") for p in PdfReader(str(path)).pages[:2])
    m = re.search(r"Form\s*8949\s*\((20\d\d)\)", text) or re.search(r"Schedule D \(Form 1040\)\s*(20\d\d)", text)
    if m:
        return int(m.group(1))
    years = Counter(re.findall(r"\b(20\d\d)\b", text))
    return int(years.most_common(1)[0][0]) if years else None


def is_draft(path: Path) -> bool:
    text = " ".join((p.extract_text() or "") for p in PdfReader(str(path)).pages[:2])
    return bool(re.search(r"\bDRAFT\b", text)) or "irs-dft" in str(path)


def download(year: int, dest: Path) -> bool:
    ok = True
    for name in FORMS:
        stem = name[:-4]
        for url in URLS:
            url = url.format(stem=stem, year=year)
            try:
                with urllib.request.urlopen(url, timeout=60) as r, open(dest / name, "wb") as f:
                    f.write(r.read())
            except Exception:
                continue
            if form_year(dest / name) == year:
                print(f"  ✓ {name} from {url}")
                break
        else:
            ok = say(False, f"no final {year} {name} on irs.gov yet")
    return ok


def field_names(path: Path) -> set[str]:
    return set((PdfReader(str(path)).get_fields() or {}).keys())


def widget_rects(path: Path) -> dict[str, list[float]]:
    """Full field name -> widget rectangle [x1, y1, x2, y2]."""
    rects = {}
    for page in PdfReader(str(path)).pages:
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


def verify(year: int, folder: Path, draft: bool = False) -> bool:
    forms_ok = _check_forms(year, folder, draft)
    if forms_ok is None:
        return False
    rows = _sample_rows(year)
    ok = forms_ok
    ok &= _check_8949_fields(year, folder, rows)
    ok &= _check_line2_positions(year, folder, rows)
    ok &= _check_printed_boxes(year, folder)
    ok &= _check_schedule_d(year, folder)
    _report_field_changes(year, folder, draft)
    return ok


def _check_forms(year: int, folder: Path, draft: bool) -> bool | None:
    """Each form is there, the year's revision, and final unless `draft`;
    None when one is missing (nothing else can be checked)."""
    ok = True
    for name, label in FORMS.items():
        path = folder / name
        if not say(path.exists(), f"{label} template present ({name})"):
            return None
        ok &= say(form_year(path) == year, f"{label} is the {year} revision (form says {form_year(path)})")
        if not draft:
            ok &= say(not is_draft(path), f"{label} is final, not a draft")
    return ok


def _sample_rows(year: int) -> dict:
    """A full page of short-term rows for Part I (page 1) and of long-term
    rows for Part II (page 2)."""
    # Imported here: the backend opens its database on import, which
    # --watch and --draft don't need.
    from decimal import Decimal

    from backend.services.reports.form_8949 import Form8949Row, _determine_box, get_8949_field_config

    per_page = get_8949_field_config(year)["rows_per_page"]
    return {
        page: [Form8949Row("0.01 BTC", "01/01/2020", f"06/01/{year}", Decimal(1), Decimal(1), Decimal(0), term,
                           _determine_box(term, False, year))] * per_page
        for page, term in ((1, "SHORT"), (2, "LONG"))
    }


def _check_8949_fields(year: int, folder: Path, rows: dict) -> bool:
    from backend.services.reports.form_8949 import map_8949_rows_to_field_data

    wanted = set(map_8949_rows_to_field_data(rows[1], 1, year)) | set(map_8949_rows_to_field_data(rows[2], 2, year))
    missing = sorted(wanted - field_names(folder / "f8949.pdf"))
    return say(not missing, f"8949: all {len(wanted)} field names the app writes exist"
               + (f" — MISSING {len(missing)}, e.g. {missing[:2]}" if missing else ""))


def _check_line2_positions(year: int, folder: Path, rows: dict) -> bool:
    """Line 2 "Totals": each field under its column (x of the last row's
    cell), below that row."""
    from backend.services.reports.form_8949 import (
        get_8949_field_config, line2_field_names, map_8949_rows_to_field_data,
    )

    rects, n = widget_rects(folder / "f8949.pdf"), get_8949_field_config(year)["rows_per_page"]
    ok = True
    for page in (1, 2):
        last = dict(zip("abcdefgh", [k for k in map_8949_rows_to_field_data(rows[page], page, year)
                                      if f".Row{n}[0]." in k]))
        wrong = [col for col, name in line2_field_names(page, year).items()
                 if name not in rects or last.get(col) not in rects
                 or abs(rects[name][0] - rects[last[col]][0]) >= 1 or rects[name][3] > rects[last[col]][1]]
        ok &= say(not wrong, f"Part {'I' if page == 1 else 'II'} line 2 totals fields sit under columns (d)-(h)"
                  + (f" — WRONG for {wrong}" if wrong else ""))
    return ok


def _check_printed_boxes(year: int, folder: Path) -> bool:
    """The boxes printed on each Part, in order, are the config's."""
    from backend.services.reports.form_8949 import get_8949_field_config

    config = get_8949_field_config(year)
    reader = PdfReader(str(folder / "f8949.pdf"))
    # IRS drafts open with a "the draft begins on the next page" cover sheet
    first = 1 if "begins on the next page" in (reader.pages[0].extract_text() or "") else 0
    ok = True
    for page, key in ((first, "boxes_part1"), (first + 1, "boxes_part2")):
        printed = re.findall(r"\(([A-L])\)\s+(?:Short|Long)-term", reader.pages[page].extract_text())
        ok &= say(printed == config[key], f"Part {'I' if key == 'boxes_part1' else 'II'} boxes on form {printed} match config")
    return ok


def _check_schedule_d(year: int, folder: Path) -> bool:
    from decimal import Decimal

    from backend.services.reports.form_8949 import map_schedule_d_fields

    one = {"proceeds": Decimal(1), "cost": Decimal(1), "gain_loss": Decimal(0)}
    sd = map_schedule_d_fields({"lines": {ln: one for ln in ("1b", "2", "3", "8b", "9", "10")}}, year=year)
    sd_missing = sorted(set(sd) - field_names(folder / "f1040sd.pdf"))
    return say(not sd_missing, "Schedule D lines 1b, 2, 3, 8b, 9, 10 fields exist"
               + (f" — MISSING {sd_missing[:2]}" if sd_missing else ""))


def _report_field_changes(year: int, folder: Path, draft: bool) -> None:
    """How each form's field names differ from the latest installed year's
    (listed, for a draft)."""
    prev = [y for y in sorted(int(p.name) for p in TEMPLATES.iterdir() if p.name.isdigit()) if y < year]
    if not prev:
        return
    for name, label in FORMS.items():
        new = field_names(folder / name)
        before = field_names(TEMPLATES / str(prev[-1]) / name)
        added, removed = sorted(new - before), sorted(before - new)
        print(f"  • {label} field names vs {prev[-1]}: {len(added)} added, {len(removed)} removed"
              + (" (identical layout)" if not added and not removed else " — review the diff"))
        if draft:
            for tag, names in (("+", added), ("-", removed)):
                for n in names[:25]:
                    print(f"      {tag} {n}")


def draft_check() -> int:
    """Informational: run every check against the IRS's current DRAFT forms."""
    have = max(int(p.name) for p in TEMPLATES.iterdir() if p.name.isdigit())
    with tempfile.TemporaryDirectory() as d:
        folder = Path(d)
        for name in FORMS:
            url = DRAFT_URL.format(stem=name[:-4])
            try:
                with urllib.request.urlopen(url, timeout=60) as r, open(folder / name, "wb") as f:
                    f.write(r.read())
            except Exception as e:
                print(f"  ✗ couldn't download {url}: {e}")
                return 0
        year = form_year(folder / "f8949.pdf")
        sd_year = form_year(folder / "f1040sd.pdf")
        print(f"IRS drafts on irs.gov: Form 8949 for {year}, Schedule D for {sd_year} (latest bundled: {have})")
        if not year or year <= have:
            print("No draft newer than the bundled forms; nothing to preview.")
            return 0
        print(f"\nChecking the {year} DRAFT against the app (drafts can still change)")
        ok = verify(year, folder, draft=True)
        print(f"\n{'✓ The app already fits the draft.' if ok else '✗ Differences above need a config change when the final form ships.'}")
    return 0


def watch() -> int:
    """For CI: exit 1 when irs.gov has a final form for a year we don't have."""
    have = max(int(p.name) for p in TEMPLATES.iterdir() if p.name.isdigit())
    target = have + 1
    with tempfile.TemporaryDirectory() as d:
        if download(target, Path(d)) and all(not is_draft(Path(d) / n) for n in FORMS):
            print(f"\nFinal {target} IRS forms are out. Run: python scripts/irs_new_year.py {target}")
            return 1
    print(f"No final {target} forms yet (latest bundled: {have}).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("year", type=int, nargs="?")
    ap.add_argument("--check", action="store_true", help="verify the installed templates only")
    ap.add_argument("--from-dir", type=Path, help="use f8949.pdf / f1040sd.pdf from this folder")
    ap.add_argument("--watch", action="store_true", help="CI: fail if a new final year is available")
    ap.add_argument("--draft", action="store_true", help="preview: check the IRS draft forms (installs nothing)")
    a = ap.parse_args()
    if a.watch:
        return watch()
    if a.draft:
        return draft_check()
    if not a.year:
        ap.error("year is required")

    if a.check:
        print(f"Verifying installed {a.year} templates")
        if not verify(a.year, TEMPLATES / str(a.year)):
            return 1
    elif not install(a.year, a.from_dir):
        return 1
    return run_template_tests(a.year)


def install(year: int, from_dir: Path | None) -> bool:
    """Download (or copy) the year's templates, verify them and install them."""
    print(f"Getting {year} templates")
    with tempfile.TemporaryDirectory() as d:
        staging = Path(d)
        if from_dir:
            for name in FORMS:
                shutil.copy(from_dir.expanduser() / name, staging / name)
        elif not download(year, staging):
            return False
        print(f"\nVerifying {year}")
        if not verify(year, staging):
            print("\n✗ Not installed — see the ✗ lines above. If field names changed, follow docs/IRS_ANNUAL_FORM_UPDATE.md Step 4.")
            return False
        dest = TEMPLATES / str(year)
        dest.mkdir(parents=True, exist_ok=True)
        for name in FORMS:
            shutil.copy(staging / name, dest / name)
        print(f"  ✓ installed to {dest.relative_to(ROOT)}")
    return True


def run_template_tests(year: int) -> int:
    print("\nRunning template tests")
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "backend/tests/test_irs_templates.py",
                        "-k", str(year), "-p", "no:cacheprovider"], cwd=ROOT)
    if r.returncode != 0:
        print(f"\nIf the only failure is 'not verified for {year}': the layout matches. Add {year} to\n"
              f"\"verified_years\" in backend/services/reports/form_8949.py, rerun, commit.")
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
