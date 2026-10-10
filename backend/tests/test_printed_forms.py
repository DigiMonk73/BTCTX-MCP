"""
The printed forms, read back (#80): the IRS Form 8949 and Schedule D PDFs
and the Complete Tax Report as a preparer gets them, for the test ledgers.

The numbers behind the forms have their own tests (test_golden_years.py,
test_seed_ledger.py); a QA pass of a 2026 draft still found defects only
the printed PDF showed (#74, #75, #78). So these read each field where it
is drawn on the page (printed_forms.py) and check:
- every row of the year is printed once, in its box, with its figures;
- each row adds up, (d) - (e) = (h), with (f) and (g) blank;
- each page has one box checked and line 2 totals its own rows;
- Schedule D's lines are its boxes' sheets added up, and nothing else on
  Schedule D is filled;
- the Complete Tax Report's box table shows the forms' figures.

Ledgers: the full test ledger (scripts/seed_ledger.py: every box of 2024,
2025 and 2026, multi-page boxes) and the golden ledger
(test_golden_years.py: hand-checked figures, a loss in box H).
"""

import importlib.util
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy.orm import sessionmaker

from backend.database import get_db
from backend.main import app
from backend.routers.reports import get_template_path
from backend.services import first_run, outbound
from backend.services.reports import draft_forms
from backend.services.reports.form_8949 import build_form_8949_and_schedule_d
from backend.tests import printed_forms as pf
from backend.tests.conftest import init_test_db
from backend.tests.test_golden_years import LEDGER as GOLDEN_LEDGER

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("seed_ledger", ROOT / "scripts" / "seed_ledger.py")
seed_ledger = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_ledger)

USER, PASSWORD = "forms-user", "forms-password-123"
# The day the forms are made: inside 2026, so the shipped 2026 drafts are offered
FORMS_DAY = date(2026, 10, 10)

LEDGERS = {
    "seed": (seed_ledger.ledger_rows, "UTC"),
    "golden": (lambda: [dict(r) for r in GOLDEN_LEDGER], "America/New_York"),
}


@pytest.fixture(scope="module")
def printed(auth_client, tmp_path_factory):
    """Each ledger on its own database, and what it prints: ledger ->
    {"pages": {year: the IRS PDF's pages read back}, "reports": {year:
    report text}, "rows": {year: build_form_8949_and_schedule_d()}}."""
    from sqlalchemy import create_engine

    previous = app.dependency_overrides[get_db]
    out = {}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(draft_forms, "SHIPPED_DIR", ROOT / "backend" / "assets" / "irs_templates" / "drafts")
        mp.setattr(draft_forms, "today", lambda: FORMS_DAY)
        mp.setattr(outbound, "_current", outbound.NetworkSettings(price_source="public"))
        for name, (rows, timezone) in LEDGERS.items():
            path = tmp_path_factory.mktemp(f"forms-{name}") / "btctx.db"
            engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
            init_test_db(engine)
            Session = sessionmaker(bind=engine)
            app.dependency_overrides[get_db] = _sessions_of(Session)
            first_run.clear_code()
            out[name] = _print_ledger(rows(), timezone, Session)
            first_run.clear_code()
            engine.dispose()
    app.dependency_overrides[get_db] = previous
    return out


def _sessions_of(Session):
    """A get_db override on that database (FastAPI reads the override's own
    parameters as request parameters, so it takes none)."""
    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()
    return override


def _print_ledger(rows: list[dict], timezone: str, Session) -> dict:
    c = TestClient(app)
    seed_ledger.log_in(c, USER, PASSWORD, first_run.ensure_code())
    assert c.put("/api/settings/tax-timezone", json={"timezone": timezone}).status_code == 200
    assert seed_ledger.seed(c, rows) == len(rows)
    years = c.get("/api/reports/years").json()
    result = {"pages": {}, "reports": {}, "rows": {}}
    for year in years["ledger_years"]:
        r = c.get("/api/reports/complete_tax_report", params={"year": year})
        assert r.status_code == 200, r.text
        result["reports"][year] = "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(r.content)).pages)
        if year not in years["form_years"]:
            continue
        r = c.get("/api/reports/irs_reports", params={"year": year})
        assert r.status_code == 200, r.text
        result["pages"][year] = _read_back(r.content, year)
        with Session() as db:
            result["rows"][year] = build_form_8949_and_schedule_d(year, db)
    return result


CASES = [("seed", 2024), ("seed", 2025), ("seed", 2026), ("golden", 2024), ("golden", 2025)]


def _read_back(pdf: bytes, year: int) -> list[pf.PrintedPage]:
    templates = (pf.template_pages(Path(get_template_path(year, "f8949.pdf")), "f8949")
                 + pf.template_pages(Path(get_template_path(year, "f1040sd.pdf")), "f1040sd"))
    return pf.read_printed(pdf, templates)


def _pages(printed, ledger: str, year: int) -> list[pf.PrintedPage]:
    return printed[ledger]["pages"][year]


def _parts(pages: list[pf.PrintedPage], year: int) -> list[pf.Form8949Part]:
    return [pf.form_8949_part(p, year) for p in pages if p.template.form == "f8949"]


def test_every_case_has_forms(printed):
    for ledger, year in CASES:
        assert year in printed[ledger]["pages"], (ledger, year)


@pytest.mark.parametrize("ledger, year", CASES)
def test_every_row_is_printed_once_in_its_box(printed, ledger, year):
    printed_rows = Counter(
        (part.boxes, row["a"], row["b"], row["c"], pf.amount(row["d"]), pf.amount(row["e"]), pf.amount(row["h"]))
        for part in _parts(_pages(printed, ledger, year), year) for row in part.rows
    )
    computed = printed[ledger]["rows"][year]
    expected = Counter(
        (r["box"], r["description"], r["date_acquired"], r["date_sold"],
         Decimal(r["proceeds"]), Decimal(r["cost"]), Decimal(r["gain_loss"]))
        for r in computed["short_term"] + computed["long_term"]
    )
    assert expected, "the case has no rows to print"
    assert printed_rows == expected


@pytest.mark.parametrize("ledger, year", CASES)
def test_each_row_adds_up(printed, ledger, year):
    for part in _parts(_pages(printed, ledger, year), year):
        for row in part.rows:
            assert all(row[col] for col in "abcdeh"), row
            assert row["f"] == "" and row["g"] == "", row
            assert pf.amount(row["d"]) - pf.amount(row["e"]) == pf.amount(row["h"]), row


@pytest.mark.parametrize("ledger, year", CASES)
def test_each_page_has_one_box_and_totals_its_rows(printed, ledger, year):
    for part in _parts(_pages(printed, ledger, year), year):
        if not part.rows:
            assert part.boxes == "" and not any(part.line2.values()), part
            continue
        assert len(part.boxes) == 1, part.boxes
        assert part.boxes in (pf.BOXES_FROM_2025 if year >= 2025 else pf.BOXES_UNTIL_2024)[part.part]
        assert not part.empty_rows_between
        for col in "deh":
            assert pf.amount(part.line2[col]) == sum(pf.amount(r[col]) for r in part.rows), (col, part)
        assert part.line2["f"] == "" and part.line2["g"] == ""


@pytest.mark.parametrize("ledger, year", CASES)
def test_schedule_d_lines_are_their_boxes_sheets(printed, ledger, year):
    pages = _pages(printed, ledger, year)
    sheets: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for part in _parts(pages, year):
        if part.rows:
            for col in "deh":
                sheets[pf.SCHEDULE_D_LINE[part.boxes]][col] += pf.amount(part.line2[col])
    schedule_d = [p for p in pages if p.template.form == "f1040sd"]
    assert len(schedule_d) == 2  # both pages: Part III is the filer's to complete
    lines = pf.schedule_d_lines(schedule_d)
    for line, cells in lines.items():
        if line in sheets:
            assert {col: pf.amount(cells[col]) for col in "deh"} == sheets[line], line
            assert cells["g"] == ""
        else:
            assert not any(cells.values()), (line, cells)
    assert set(sheets) <= set(lines)
    assert pf.other_schedule_d_values(schedule_d) == {}


@pytest.mark.parametrize("ledger, year", CASES)
def test_the_report_shows_the_forms_figures(printed, ledger, year):
    by_box: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for part in _parts(_pages(printed, ledger, year), year):
        for row in part.rows:
            by_box[part.boxes]["rows"] += 1
            for col, key in (("d", "proceeds"), ("e", "cost"), ("h", "gain")):
                by_box[part.boxes][key] += pf.amount(row[col])
    report = pf.report_boxes(printed[ledger]["reports"][year])
    assert set(report) == set(by_box)
    for box, shown in report.items():
        assert shown["line"] == pf.SCHEDULE_D_LINE[box]
        assert int(shown["rows"]) == by_box[box]["rows"]
        for key in ("proceeds", "cost", "gain"):
            assert pf.amount(shown[key].replace("$", "")) == by_box[box][key], (box, key, shown)
