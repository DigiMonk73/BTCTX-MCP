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
2025 and 2026, multi-page boxes), the golden ledger (test_golden_years.py:
hand-checked figures, a loss in box H) and a tiny one with a 5-satoshi sale.

And the formats the IRS forms need:
- BTC amounts with all eight decimals, never "5E-8 BTC" (#74).
"""

import importlib.util
import re
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import create_engine
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

BANK, EXCH_USD, EXCH_BTC, EXTERNAL = 1, 3, 4, 99
# A 5-satoshi sale: str() of a Decimal under 0.000001 is "5E-8" (#74)
TINY_LEDGER = [
    dict(type="Deposit", timestamp="2025-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
         amount="1000", fee_amount="0", fee_currency="USD", source="N/A"),
    dict(type="Buy", timestamp="2025-01-10T12:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
         amount="0.001", cost_basis_usd="100", fee_amount="0", fee_currency="USD"),
    dict(type="Sell", timestamp="2025-02-01T12:00:00Z", from_account_id=EXCH_BTC, to_account_id=EXCH_USD,
         amount="0.00000005", gross_proceeds_usd="0.01", fee_amount="0", fee_currency="USD"),
]

LEDGERS = {
    "seed": (seed_ledger.ledger_rows, "UTC"),
    "golden": (lambda: [dict(r) for r in GOLDEN_LEDGER], "America/New_York"),
    "tiny": (lambda: [dict(r) for r in TINY_LEDGER], "UTC"),
}
# Every (ledger, year) with Form 8949 rows (test_cases_cover_every_year_with_rows)
CASES = [("seed", 2024), ("seed", 2025), ("seed", 2026), ("golden", 2024), ("golden", 2025), ("tiny", 2025)]


@pytest.fixture(scope="module")
def printed(auth_client, tmp_path_factory):
    """Each ledger on its own database, and what it prints: ledger ->
    {"pages": {year: the IRS PDF's pages read back}, "reports": {year:
    report text}, "rows": {year: build_form_8949_and_schedule_d()}}.
    auth_client has set the session's database override, which this swaps
    for each ledger's and always puts back: the modules after this one run
    on the session's database."""
    previous = app.dependency_overrides[get_db]
    out = {}
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(draft_forms, "SHIPPED_DIR", ROOT / "backend" / "assets" / "irs_templates" / "drafts")
            mp.setattr(draft_forms, "today", lambda: FORMS_DAY)
            mp.setattr(outbound, "_current", outbound.NetworkSettings(price_source="public"))
            for name, (rows, timezone) in LEDGERS.items():
                out[name] = _print_on_own_database(name, rows(), timezone, tmp_path_factory)
    finally:
        app.dependency_overrides[get_db] = previous
    return out


def _print_on_own_database(name: str, rows: list[dict], timezone: str, tmp_path_factory) -> dict:
    path = tmp_path_factory.mktemp(f"forms-{name}") / "btctx.db"
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    init_test_db(engine)
    Session = sessionmaker(bind=engine)
    app.dependency_overrides[get_db] = _sessions_of(Session)
    first_run.clear_code()
    try:
        return _print_ledger(rows, timezone, Session)
    finally:
        first_run.clear_code()
        engine.dispose()


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


def _read_back(pdf: bytes, year: int) -> list[pf.PrintedPage]:
    templates = pf.template_pages(Path(get_template_path(year, "f8949.pdf")), "f8949") + _schedule_d_templates(year)
    return pf.read_printed(pdf, templates)


def _schedule_d_templates(year: int) -> list[pf.TemplatePage]:
    with pytest.MonkeyPatch.context() as mp:  # the 2026 drafts, as when the forms were made
        mp.setattr(draft_forms, "SHIPPED_DIR", ROOT / "backend" / "assets" / "irs_templates" / "drafts")
        mp.setattr(draft_forms, "today", lambda: FORMS_DAY)
        return pf.template_pages(Path(get_template_path(year, "f1040sd.pdf")), "f1040sd")


def _pages(printed, ledger: str, year: int) -> list[pf.PrintedPage]:
    return printed[ledger]["pages"][year]


def _parts(pages: list[pf.PrintedPage], year: int) -> list[pf.Form8949Part]:
    return [pf.form_8949_part(p, year) for p in pages if p.template.form == "f8949"]


def test_cases_cover_every_year_with_rows(printed):
    with_rows = {(ledger, year) for ledger, result in printed.items() for year, rows in result["rows"].items()
                 if rows["short_term"] or rows["long_term"]}
    assert set(CASES) == with_rows


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
    # Both pages, in order: Part III is the filer's to complete
    assert [p.template.signature for p in schedule_d] == [t.signature for t in _schedule_d_templates(year)]
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


@pytest.mark.parametrize("ledger, year", CASES)
def test_btc_amounts_have_eight_decimals(printed, ledger, year):
    """Column (a) reads "0.00000005 BTC", never exponent form, which str()
    gives a Decimal under 0.000001 BTC (#74)."""
    for part in _parts(_pages(printed, ledger, year), year):
        for row in part.rows:
            assert re.fullmatch(r"\d+\.\d{8} BTC", row["a"]), row["a"]


def test_the_tiny_sale_is_printed(printed):
    rows = [row["a"] for part in _parts(_pages(printed, "tiny", 2025), 2025) for row in part.rows]
    assert rows == ["0.00000005 BTC"]
