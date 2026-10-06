"""
Test-only IRS draft forms (services/reports/draft_forms.py): off unless a
year's drafts are in the data folder's irs-draft-forms/<year>/; then Reports
offers that year and prints its Form 8949 and Schedule D from them, every
page marked DRAFT — DO NOT FILE. Only drafts of a year newer than the bundled
ones, that say so on every page and have every field the app writes.

No IRS draft is kept in the repository (never bundled): the stand-in is the
newest bundled form with the draft's cover sheet and markings added, which
is how the IRS's drafts look (2026's did, May 2026).
"""

import io
import shutil

import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from backend import cli
from backend.routers.reports import get_supported_years, get_template_path
from backend.services.reports import draft_forms

BUNDLED = get_supported_years()
YEAR = max(BUNDLED) + 1  # the year after the newest bundled forms
TITLE = {"f8949.pdf": "Form 8949 ({year})", "f1040sd.pdf": "Schedule D (Form 1040) {year}"}


def _one_page(*lines: str) -> PdfReader:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    for i, line in enumerate(lines):
        c.drawString(20, 780 - 12 * i, line)
    c.save()
    return PdfReader(io.BytesIO(buf.getvalue()))


def make_draft(dest, year: int = YEAR, source_year: int | None = None, marked: bool = True, cover: bool = True):
    """f8949.pdf and f1040sd.pdf in `dest` as an IRS draft of `year`, from the
    bundled forms of `source_year` (the newest)."""
    dest.mkdir(parents=True, exist_ok=True)
    for name, title in TITLE.items():
        writer = PdfWriter(clone_from=get_template_path(source_year or max(BUNDLED), name))
        lines = [title.format(year=year)] + (["DRAFT — DO NOT FILE"] if marked else [])
        for page in writer.pages:
            page.merge_page(_one_page(*lines).pages[0], over=False)  # read before the form's own text
        if cover:
            writer.insert_page(_one_page("Note: The draft you are looking for begins on the next page.").pages[0], 0)
        with open(dest / name, "wb") as f:
            writer.write(f)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(draft_forms, "DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def with_drafts(data_dir):
    make_draft(data_dir / draft_forms.FOLDER_NAME / str(YEAR))
    return data_dir


def test_off_by_default(auth_client):
    years = auth_client.get("/api/reports/years").json()
    assert (years["form_years"], years["draft_years"]) == (BUNDLED, [])
    assert auth_client.get("/api/reports/irs_reports", params={"year": YEAR}).status_code == 400


def test_the_draft_year_is_offered(auth_client, with_drafts):
    years = auth_client.get("/api/reports/years").json()
    assert years["form_years"] == BUNDLED + [YEAR]
    assert years["draft_years"] == [YEAR]


def test_forms_print_from_the_drafts_marked_on_every_page(auth_client, with_drafts):
    auth_client.delete("/api/transactions/delete_all")
    for tx in (
        dict(type="Deposit", timestamp=f"{YEAR}-01-02T12:00:00Z", from_account_id=99, to_account_id=3,
             amount="10000", fee_amount="0", fee_currency="USD", source="N/A"),
        dict(type="Buy", timestamp=f"{YEAR}-01-05T12:00:00Z", from_account_id=3, to_account_id=4,
             amount="0.1", cost_basis_usd="9000.00", fee_amount="0", fee_currency="USD"),
        dict(type="Sell", timestamp=f"{YEAR}-03-05T12:00:00Z", from_account_id=4, to_account_id=3,
             amount="0.04", gross_proceeds_usd="4400.00", fee_amount="0", fee_currency="USD"),
    ):
        assert auth_client.post("/api/transactions", json=tx).status_code == 200
    try:
        r = auth_client.get("/api/reports/irs_reports", params={"year": YEAR})
    finally:
        auth_client.delete("/api/transactions/delete_all")
    assert r.status_code == 200, r.text
    pages = PdfReader(io.BytesIO(r.content)).pages
    texts = [p.extract_text() or "" for p in pages]
    assert len(pages) == 4  # one 8949 sheet and Schedule D, without the drafts' cover pages
    assert all(draft_forms.DRAFT_MARK in t for t in texts)
    assert not any(draft_forms.COVER_NOTE in t for t in texts)
    assert "4400.00" in texts[0] and "3600.00" in texts[0]  # the sale, Box G (covered)
    assert "800.00" in texts[2]  # Schedule D line 1b


def test_a_bundled_year_ignores_its_drafts(auth_client, data_dir):
    newest = max(BUNDLED)
    make_draft(data_dir / draft_forms.FOLDER_NAME / str(newest), year=newest)
    years = auth_client.get("/api/reports/years").json()
    assert years["draft_years"] == [] and years["form_years"] == BUNDLED
    assert draft_forms.FOLDER_NAME not in get_template_path(newest, "f8949.pdf")


@pytest.mark.parametrize("why, make", [
    ("not marked as a draft", lambda d: make_draft(d, marked=False)),
    ("another year's forms", lambda d: make_draft(d, year=YEAR + 1)),
    ("a final form copied in", lambda d: [shutil.copy(get_template_path(max(BUNDLED), n), d / n)
                                          for n in draft_forms.FORMS]),
    ("Schedule D missing", lambda d: (make_draft(d), (d / "f1040sd.pdf").unlink())),
    ("8949 fields missing", lambda d: (make_draft(d), shutil.copy(d / "f1040sd.pdf", d / "f8949.pdf"))),
])
def test_anything_but_that_years_drafts_is_left_out(auth_client, data_dir, why, make):
    folder = data_dir / draft_forms.FOLDER_NAME / str(YEAR)
    folder.mkdir(parents=True)
    make(folder)
    assert auth_client.get("/api/reports/years").json()["draft_years"] == [], why
    assert auth_client.get("/api/reports/irs_reports", params={"year": YEAR}).status_code == 400


def test_the_drafts_are_checked_like_a_final_form(tmp_path):
    make_draft(tmp_path)
    assert draft_forms.problems(YEAR, tmp_path) == []
    make_draft(tmp_path, cover=False)  # a draft without the cover sheet is fine too
    assert draft_forms.problems(YEAR, tmp_path) == []


def test_cli_installs_checks_and_removes_the_drafts(data_dir, tmp_path, capsys):
    source = tmp_path / "downloaded"
    make_draft(source)
    assert cli.main(["install-draft-forms", "--from-dir", str(source)]) == 0
    assert f"for {YEAR} installed" in capsys.readouterr().out
    assert draft_forms.draft_years(BUNDLED) == [YEAR]

    assert cli.main(["install-draft-forms", "--remove"]) == 0
    assert draft_forms.draft_years(BUNDLED) == []
    assert not (data_dir / draft_forms.FOLDER_NAME).exists()


def test_cli_refuses_a_final_form_or_a_bundled_year(data_dir, tmp_path, capsys):
    final = tmp_path / "final"
    final.mkdir()
    for name in draft_forms.FORMS:
        shutil.copy(get_template_path(max(BUNDLED), name), final / name)
    assert cli.main(["install-draft-forms", "--from-dir", str(final)]) == 1
    assert "nothing to install" in capsys.readouterr().err

    unmarked = tmp_path / "unmarked"
    make_draft(unmarked, marked=False)
    assert cli.main(["install-draft-forms", "--from-dir", str(unmarked)]) == 1
    assert "DRAFT — DO NOT FILE" in capsys.readouterr().err
    assert draft_forms.draft_years(BUNDLED) == []
