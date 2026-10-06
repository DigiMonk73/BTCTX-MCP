"""
Test-only IRS DRAFT forms: Form 8949 and Schedule D for a year this version
has no final forms for, so a test install can print that year's forms before
the IRS publishes them.

Off unless the drafts are in the data folder (DATABASE_FILE's), as
irs-draft-forms/<year>/f8949.pdf and f1040sd.pdf; `python -m backend.cli
install-draft-forms` puts them there. Never bundled
(docs/IRS_ANNUAL_FORM_UPDATE.md), and a year with bundled forms ignores its
drafts, so the yearly update replaces them.

A year counts only when both files are the IRS's drafts for it that the app
can fill: that year printed on them, "DRAFT — DO NOT FILE" on every form
page (so on every page the app prints), and every field the app writes and
the boxes in the config's order (form_8949.py). Anything else, a file that
can't be read included, is left out with a warning in the log: it never
stops the bundled years' forms.

install() downloads from irs.gov itself, not through services/outbound.py:
it runs only when an admin runs `install-draft-forms` on a test install,
never in the app, so the owner's price settings don't apply to it.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import urllib.request
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader

logger = logging.getLogger(__name__)

FOLDER_NAME = "irs-draft-forms"
FORMS = ("f8949.pdf", "f1040sd.pdf")
DRAFT_MARK = "DRAFT — DO NOT FILE"
DRAFT_URL = "https://www.irs.gov/pub/irs-dft/{stem}--dft.pdf"
# IRS drafts open with a "the draft ... begins on the next page" cover sheet
COVER_NOTE = "begins on the next page"

DATA_DIR: str | None = None  # None: DATABASE_FILE's folder; tests point this elsewhere


def folder() -> Path:
    if DATA_DIR is not None:
        return Path(DATA_DIR) / FOLDER_NAME
    from backend.database import DATABASE_FILE

    return Path(DATABASE_FILE).parent / FOLDER_NAME


def printed_year(path: Path) -> int | None:
    """Tax year printed on the form, e.g. 'Form 8949 (2025)' / 'Schedule D (Form 1040) 2025'."""
    from collections import Counter

    text = " ".join((p.extract_text() or "") for p in PdfReader(str(path)).pages[:2])
    m = re.search(r"Form\s*8949\s*\((20\d\d)\)", text) or re.search(r"Schedule D \(Form 1040\)\s*(20\d\d)", text)
    if m:
        return int(m.group(1))
    years = Counter(re.findall(r"\b(20\d\d)\b", text))
    return int(years.most_common(1)[0][0]) if years else None


def first_form_page(path: Path) -> int:
    """Index of the first page of the form itself: 1 after the IRS cover sheet."""
    return 1 if COVER_NOTE in (PdfReader(str(path)).pages[0].extract_text() or "") else 0


def draft_years(bundled: list[int]) -> list[int]:
    """The years with checked drafts, each newer than every bundled year."""
    newest = max(bundled, default=0)
    try:
        years = [(int(d.name), d) for d in folder().iterdir() if re.fullmatch(r"[0-9]{4}", d.name)]
    except FileNotFoundError:
        return []
    except OSError as e:
        logger.warning("IRS draft forms in %s left out: %s", folder(), e)
        return []
    return sorted(year for year, d in years if year > newest and _usable(year, d))


def template_path(year: int, form_name: str) -> str:
    return str(folder() / str(year) / form_name)


def _usable(year: int, path: Path) -> bool:
    try:
        stats = [(path / name).stat() for name in FORMS]
    except OSError as e:
        logger.warning("IRS draft forms in %s left out: %s", path, e)
        return False
    signature = tuple((s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns) for s in stats)
    return not _checked(year, str(path), signature)


@lru_cache(maxsize=16)
def _checked(year: int, path: str, signature: tuple) -> tuple[str, ...]:
    """problems() once per version of the files (`signature`), logged."""
    try:
        found = tuple(problems(year, Path(path)))
    except Exception as e:  # a damaged or half-copied PDF: leave it out, never fail the request
        found = (f"unreadable: {type(e).__name__}: {e}",)
    if found:
        logger.warning("IRS draft forms in %s left out: %s", path, "; ".join(found))
    return found


def problems(year: int, path: Path) -> list[str]:
    """Why the PDFs in `path` aren't usable as `year`'s draft forms; [] when they are."""
    found = []
    for name in FORMS:
        f = path / name
        if not f.is_file():
            return [f"{name} is missing"]
        printed = printed_year(f)
        if printed != year:
            found.append(f"{name} is for {printed}, not {year}")
        reader = PdfReader(str(f))
        unmarked = [i + 1 for i, page in enumerate(reader.pages[first_form_page(f):])
                    if DRAFT_MARK not in (page.extract_text() or "")]
        if unmarked:
            found.append(f"{name} page(s) {unmarked} don't say {DRAFT_MARK} (not an IRS draft)")
    return found + _fields_problems(year, path)


def _fields_problems(year: int, path: Path) -> list[str]:
    """The field names the app writes and the boxes' order, as for a final form
    (scripts/irs_new_year.py checks the same with the year's templates)."""
    from decimal import Decimal

    from backend.services.reports.form_8949 import (
        Form8949Row, checkbox_field_for_box, get_8949_field_config,
        map_8949_rows_to_field_data, map_schedule_d_fields,
    )

    config = get_8949_field_config(year)
    wanted: set[str] = set()
    for page, term, boxes in ((1, "SHORT", config["boxes_part1"]), (2, "LONG", config["boxes_part2"])):
        rows = [Form8949Row("0.01 BTC", "01/01/2020", f"06/01/{year}", Decimal(1), Decimal(1), Decimal(0),
                            term, boxes[0])] * config["rows_per_page"]
        wanted |= set(map_8949_rows_to_field_data(rows, page, year))
        wanted |= {checkbox_field_for_box(box, page, year)[0] for box in boxes}
    one = {"proceeds": Decimal(1), "cost": Decimal(1), "gain_loss": Decimal(0)}
    sd_wanted = set(map_schedule_d_fields({"lines": {ln: one for ln in ("1b", "2", "3", "8b", "9", "10")}}, year))

    found = []
    for name, names in (("f8949.pdf", wanted), ("f1040sd.pdf", sd_wanted)):
        missing = sorted(names - set(PdfReader(str(path / name)).get_fields() or {}))
        if missing:
            found.append(f"{name} lacks {len(missing)} field(s) the app writes, e.g. {missing[:2]}")

    reader = PdfReader(str(path / "f8949.pdf"))
    first = first_form_page(path / "f8949.pdf")
    for offset, key in ((0, "boxes_part1"), (1, "boxes_part2")):
        text = reader.pages[first + offset].extract_text() if first + offset < len(reader.pages) else ""
        printed = re.findall(r"\(([A-L])\)\s+(?:Short|Long)-term", text or "")
        if printed != config[key]:
            found.append(f"f8949.pdf Part {'I' if offset == 0 else 'II'} boxes are {printed}, not {config[key]}")
    return found


def install(bundled: list[int], from_dir: Path | None = None) -> tuple[int, Path]:
    """
    Put the IRS's current draft forms in the data folder, from irs.gov (the
    only site this contacts, and only when run) or from `from_dir`. Checked
    first; refused for a year with bundled forms. Returns (year, folder).
    """
    base = folder()
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as tmp:
        staging = Path(tmp)
        for name in FORMS:
            if from_dir is not None:
                shutil.copyfile(Path(from_dir).expanduser() / name, staging / name)
            else:
                with urllib.request.urlopen(DRAFT_URL.format(stem=name[:-4]), timeout=60) as r:
                    (staging / name).write_bytes(r.read())
        year = printed_year(staging / "f8949.pdf")
        newest = max(bundled, default=0)
        if year is None or year <= newest:
            raise ValueError(f"These are {year} forms; this version has the final forms up to {newest}: "
                             "nothing to install.")
        found = problems(year, staging)
        if found:
            raise ValueError(f"Not the IRS's {year} draft forms the app can fill: " + "; ".join(found))
        dest = base / str(year)
        shutil.rmtree(dest, ignore_errors=True)
        os.replace(staging, dest)
        staging.mkdir()  # for TemporaryDirectory's cleanup
    return year, dest


def remove() -> bool:
    """Delete every installed draft; whether there were any."""
    base = folder()
    if not base.exists():
        return False
    shutil.rmtree(base)
    return True
