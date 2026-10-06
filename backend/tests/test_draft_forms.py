"""
IRS draft forms (services/reports/draft_forms.py): a year's drafts from the
data folder's irs-draft-forms/<year>/ (a test install) or shipped as the
app's preview (backend/assets/irs_templates/drafts/<year>/, offered until
the year is over). Reports then offers that year and prints its Form 8949
and Schedule D from them, every page marked DRAFT — DO NOT FILE. Only drafts
of a year newer than the bundled ones, that say so on every page and have
every field the app writes.

The stand-in draft is the newest bundled form with the draft's cover sheet
and markings added, which is how the IRS's drafts look (2026's did, May
2026), so these tests don't depend on which draft ships.
"""

import io
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

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


def _sale(year: int) -> list[dict]:
    """A 2026-style covered exchange sale (Box G): $4,400 for $3,600 of basis."""
    return [
        dict(type="Deposit", timestamp=f"{year}-01-02T12:00:00Z", from_account_id=99, to_account_id=3,
             amount="10000", fee_amount="0", fee_currency="USD", source="N/A"),
        dict(type="Buy", timestamp=f"{year}-01-05T12:00:00Z", from_account_id=3, to_account_id=4,
             amount="0.1", cost_basis_usd="9000.00", fee_amount="0", fee_currency="USD"),
        dict(type="Sell", timestamp=f"{year}-03-05T12:00:00Z", from_account_id=4, to_account_id=3,
             amount="0.04", gross_proceeds_usd="4400.00", fee_amount="0", fee_currency="USD"),
    ]


class _EndOfDraftYear(datetime):
    """"Now" late in the draft year, so its sales aren't in the future
    (review of #52: right after a yearly update, YEAR's spring still is)."""

    @classmethod
    def now(cls, tz=None):
        return datetime(YEAR, 12, 31, tzinfo=timezone.utc).astimezone(tz)


@pytest.mark.parametrize("cover", [True, False])
def test_forms_print_from_the_drafts_marked_on_every_page(auth_client, data_dir, monkeypatch, cover):
    make_draft(data_dir / draft_forms.FOLDER_NAME / str(YEAR), cover=cover)
    monkeypatch.setattr("backend.services.transaction.datetime", _EndOfDraftYear)
    auth_client.delete("/api/transactions/delete_all")
    for tx in _sale(YEAR):
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


def test_a_damaged_draft_never_stops_the_bundled_forms(auth_client, data_dir, caplog):
    """Review of #52: an unreadable PDF in the draft folder made every
    year's IRS forms, and the year list, fail with a 500."""
    folder = data_dir / draft_forms.FOLDER_NAME / str(YEAR)
    folder.mkdir(parents=True)
    for name in draft_forms.FORMS:
        (folder / name).write_bytes(b"%PDF-1.7 half copied")
    (data_dir / draft_forms.FOLDER_NAME / "²").mkdir()  # isdigit(), but not a year
    years = auth_client.get("/api/reports/years")
    assert years.status_code == 200 and years.json()["draft_years"] == []
    r = auth_client.get("/api/reports/irs_reports", params={"year": max(BUNDLED)})
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    assert "left out: unreadable" in caplog.text


@pytest.fixture
def shipped(tmp_path, monkeypatch):
    """A shipped preview of YEAR (a stand-in), and `set_today(day)`."""
    make_draft(tmp_path / "shipped" / str(YEAR))
    monkeypatch.setattr(draft_forms, "SHIPPED_DIR", tmp_path / "shipped")
    return lambda day: monkeypatch.setattr(draft_forms, "today", lambda: day)


def test_the_shipped_preview_is_offered_during_its_year(auth_client, shipped):
    shipped(date(YEAR, 10, 6))
    years = auth_client.get("/api/reports/years").json()
    assert (years["form_years"], years["draft_years"]) == (BUNDLED + [YEAR], [YEAR])
    assert draft_forms.FOLDER_NAME not in get_template_path(YEAR, "f8949.pdf")


def test_the_shipped_preview_ends_with_its_year(auth_client, shipped):
    """From January 1 after its year the final forms can be out: nobody may
    file the draft from an old version, so it's no longer offered."""
    shipped(date(YEAR, 12, 31))
    assert auth_client.get("/api/reports/years").json()["draft_years"] == [YEAR]
    shipped(date(YEAR + 1, 1, 1))
    years = auth_client.get("/api/reports/years").json()
    assert (years["form_years"], years["draft_years"]) == (BUNDLED, [])
    assert auth_client.get("/api/reports/irs_reports", params={"year": YEAR}).status_code == 400


def test_a_test_install_s_drafts_come_before_the_shipped_ones(auth_client, with_drafts, shipped):
    """Review of #54: during the year both are offered; the test install's win."""
    shipped(date(YEAR, 10, 6))
    assert auth_client.get("/api/reports/years").json()["draft_years"] == [YEAR]
    assert draft_forms.FOLDER_NAME in get_template_path(YEAR, "f8949.pdf")


def test_a_test_install_keeps_its_drafts_after_the_year(auth_client, with_drafts, shipped):
    shipped(date(YEAR + 1, 2, 1))
    assert auth_client.get("/api/reports/years").json()["draft_years"] == [YEAR]
    assert draft_forms.FOLDER_NAME in get_template_path(YEAR, "f8949.pdf")  # the test install's first


REAL_SHIPPED = Path(draft_forms.__file__).resolve().parents[2] / "assets" / "irs_templates" / "drafts"


SHIPPED_YEARS = sorted(REAL_SHIPPED.glob("[0-9][0-9][0-9][0-9]"))


def _irs_new_year():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "irs_new_year", Path(__file__).resolve().parents[2] / "scripts" / "irs_new_year.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("folder", SHIPPED_YEARS, ids=lambda p: p.name)
def test_the_shipped_draft_is_the_irs_draft_of_a_year_without_final_forms(folder):
    """At the yearly update the final forms replace the draft:
    scripts/irs_new_year.py removes it, and this fails if it's still there.
    Checked as a final form is (review of #54): fields, line 2 positions,
    box order, Schedule D lines."""
    year = int(folder.name)
    assert year > max(BUNDLED), f"{year}'s final forms are bundled: delete {folder}"
    assert draft_forms.problems(year, folder) == []
    assert _irs_new_year().verify(year, folder, draft=True)
    assert len(SHIPPED_YEARS) == 1  # one preview at a time


@pytest.mark.parametrize("folder", SHIPPED_YEARS, ids=lambda p: p.name)
def test_the_shipped_draft_prints_marked_on_every_page(auth_client, monkeypatch, folder):
    """The real files, through the route: a sale lands, every page says
    DRAFT — DO NOT FILE, no IRS cover page."""
    year = int(folder.name)
    monkeypatch.setattr(draft_forms, "SHIPPED_DIR", REAL_SHIPPED)
    monkeypatch.setattr(draft_forms, "today", lambda: date(year, 12, 31))
    monkeypatch.setattr("backend.services.transaction.datetime", _EndOfDraftYear)
    auth_client.delete("/api/transactions/delete_all")
    try:
        for tx in _sale(year):
            assert auth_client.post("/api/transactions", json=tx).status_code == 200
        r = auth_client.get("/api/reports/irs_reports", params={"year": year})
    finally:
        auth_client.delete("/api/transactions/delete_all")
    assert r.status_code == 200, r.text
    texts = [p.extract_text() or "" for p in PdfReader(io.BytesIO(r.content)).pages]
    assert len(texts) == 4 and all(draft_forms.DRAFT_MARK in t for t in texts)
    assert not any(draft_forms.COVER_NOTE in t for t in texts)
    assert "4400.00" in texts[0] and "800.00" in texts[2]


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


@pytest.fixture
def watch(tmp_path, monkeypatch):
    """irs_new_year.py's --due with irs.gov stubbed: `irs["draft"]` is the
    folder the draft comes from, `irs["final"]` the final forms' (or None)."""
    script = _irs_new_year()
    irs = {"draft": tmp_path / "irs-draft", "final": None}
    make_draft(irs["draft"])
    monkeypatch.setattr(draft_forms, "SHIPPED_DIR", tmp_path / "shipped")

    def copy_from(source):
        def fetch(dest: Path) -> bool:
            if source() is None:
                return False
            for name in draft_forms.FORMS:
                shutil.copy(source() / name, dest / name)
            return True
        return fetch

    monkeypatch.setattr(script, "fetch_draft", copy_from(lambda: irs["draft"]))
    monkeypatch.setattr(script, "download", lambda year, dest: copy_from(lambda: irs["final"])(dest))
    return script, irs


def test_the_watch_asks_once_to_ship_a_new_draft(watch):
    script, irs = watch
    assert [s["title"] for s in script.due()] == [f"IRS forms: ship the {YEAR} draft as the preview"]
    shutil.copytree(irs["draft"], draft_forms.SHIPPED_DIR / str(YEAR))
    assert script.due() == []  # shipped: nothing to do


def test_the_watch_notices_a_revised_draft(watch):
    script, irs = watch
    shutil.copytree(irs["draft"], draft_forms.SHIPPED_DIR / str(YEAR))
    with open(irs["draft"] / "f8949.pdf", "ab") as f:
        f.write(b"\n% the IRS's revision\n")
    assert [s["title"] for s in script.due()] == [f"IRS forms: ship the {YEAR} draft as the preview (the IRS revised it)"]


def test_the_watch_asks_for_the_final_forms(watch, tmp_path):
    script, irs = watch
    shutil.copytree(irs["draft"], draft_forms.SHIPPED_DIR / str(YEAR))
    irs["final"] = Path(get_template_path(max(BUNDLED), "f8949.pdf")).parent  # final forms, not drafts
    steps = script.due()
    assert [s["title"] for s in steps] == [f"IRS forms: add the final {YEAR} Form 8949 and Schedule D"]
    assert f"irs_new_year.py {YEAR}" in steps[0]["body"] and "owner's \"merge\"" in steps[0]["body"]
