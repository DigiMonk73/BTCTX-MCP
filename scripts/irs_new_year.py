#!/usr/bin/env python3
"""
Add (or check) a tax year's IRS Form 8949 + Schedule D templates.

    python scripts/irs_new_year.py 2026            # download from irs.gov, verify, install
    python scripts/irs_new_year.py 2026 --check    # verify an already-installed year
    python scripts/irs_new_year.py 2026 --from-dir ~/Downloads   # use PDFs you downloaded
    python scripts/irs_new_year.py --watch         # CI: is a new final form out yet?

What it verifies (the things that silently break printed forms):
  1. It's the FINAL form for that year, not a draft or another year.
  2. Every field name the app writes exists in the new template, and the
     checkbox order matches the boxes printed on the form.
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


def verify(year: int, folder: Path) -> bool:
    from backend.services.reports.form_8949 import (
        Form8949Row, _determine_box, get_8949_field_config,
        map_8949_rows_to_field_data, map_schedule_d_fields,
    )
    from decimal import Decimal

    ok = True
    for name, label in FORMS.items():
        path = folder / name
        if not say(path.exists(), f"{label} template present ({name})"):
            return False
        ok &= say(form_year(path) == year, f"{label} is the {year} revision (form says {form_year(path)})")
        ok &= say(not is_draft(path), f"{label} is final, not a draft")

    config = get_8949_field_config(year)
    tpl = field_names(folder / "f8949.pdf")
    rows = [Form8949Row("0.01 BTC", "01/01/2020", f"06/01/{year}", Decimal(1), Decimal(1), Decimal(0), hp,
                        _determine_box(hp, False, year)) for hp in ("SHORT",)] * config["rows_per_page"]
    long_rows = [Form8949Row("0.01 BTC", "01/01/2020", f"06/01/{year}", Decimal(1), Decimal(1), Decimal(0), "LONG",
                             _determine_box("LONG", False, year))] * config["rows_per_page"]
    wanted = set(map_8949_rows_to_field_data(rows, 1, year)) | set(map_8949_rows_to_field_data(long_rows, 2, year))
    missing = sorted(wanted - tpl)
    ok &= say(not missing, f"8949: all {len(wanted)} field names the app writes exist"
              + (f" — MISSING {len(missing)}, e.g. {missing[:2]}" if missing else ""))

    reader = PdfReader(str(folder / "f8949.pdf"))
    for page, key in ((0, "boxes_part1"), (1, "boxes_part2")):
        printed = re.findall(r"\(([A-L])\)\s+(?:Short|Long)-term", reader.pages[page].extract_text())
        ok &= say(printed == config[key], f"Part {'I' if page == 0 else 'II'} boxes on form {printed} match config")

    one = {"proceeds": Decimal(1), "cost": Decimal(1), "gain_loss": Decimal(0)}
    sd = map_schedule_d_fields({"lines": {ln: one for ln in ("1b", "2", "3", "8b", "9", "10")}}, year=year)
    sd_missing = sorted(set(sd) - field_names(folder / "f1040sd.pdf"))
    ok &= say(not sd_missing, "Schedule D lines 1b, 2, 3, 8b, 9, 10 fields exist"
              + (f" — MISSING {sd_missing[:2]}" if sd_missing else ""))

    prev = [y for y in sorted(int(p.name) for p in TEMPLATES.iterdir() if p.name.isdigit()) if y < year]
    if prev:
        before = field_names(TEMPLATES / str(prev[-1]) / "f8949.pdf")
        added, removed = len(tpl - before), len(before - tpl)
        print(f"  • 8949 field names vs {prev[-1]}: {added} added, {removed} removed"
              + (" (identical layout)" if not added and not removed else " — review the diff"))
    return ok


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
    a = ap.parse_args()
    if a.watch:
        return watch()
    if not a.year:
        ap.error("year is required")

    dest = TEMPLATES / str(a.year)
    if not a.check:
        print(f"Getting {a.year} templates")
        with tempfile.TemporaryDirectory() as d:
            staging = Path(d)
            if a.from_dir:
                for name in FORMS:
                    shutil.copy(a.from_dir.expanduser() / name, staging / name)
            elif not download(a.year, staging):
                return 1
            print(f"\nVerifying {a.year}")
            if not verify(a.year, staging):
                print("\n✗ Not installed — see the ✗ lines above. If field names changed, follow docs/IRS_ANNUAL_FORM_UPDATE.md Step 4.")
                return 1
            dest.mkdir(parents=True, exist_ok=True)
            for name in FORMS:
                shutil.copy(staging / name, dest / name)
            print(f"  ✓ installed to {dest.relative_to(ROOT)}")
    else:
        print(f"Verifying installed {a.year} templates")
        if not verify(a.year, dest):
            return 1

    print("\nRunning template tests")
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "backend/tests/test_irs_templates.py",
                        "-k", str(a.year), "-p", "no:cacheprovider"], cwd=ROOT)
    if r.returncode != 0:
        print(f"\nIf the only failure is 'not verified for {a.year}': the layout matches. Add {a.year} to\n"
              f"\"verified_years\" in backend/services/reports/form_8949.py, rerun, commit.")
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
