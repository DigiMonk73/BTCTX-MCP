"""
The whole reference test ledger through Settings' CSV (#844): exported by the
app, imported by the app into an empty install holding the same accounts,
it gives every figure of testdata/reference_figures.json and the same IRS
form fields for every forms year. test_csv_roundtrip.py does this for the
small golden ledger; this ledger has what it lacks: 16 accounts, one hidden
and one renamed, every 1099-DA switch, chosen coins and values from a price.

testdata/reference_ledger.csv is that export, committed for testing by hand
(docs/HAND-TEST.md). Its one change: `coins_chosen_at` is the day a choice was
saved, the day the ledger was seeded, so the file gives every choice a fixed
day instead, or it would be stale every day. `make test-pack` makes it again.

A figure that doesn't survive is an app bug (AGENTS.md, "Bugs and security"):
never a reason to change the ledger, or to mark a test as expected to fail.
"""

import csv
import importlib.util
import io
import json
import os
from contextlib import contextmanager
from itertools import zip_longest
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import get_db
from backend.main import app
from backend.routers.reports import _chunks_by_box
from backend.services import first_run, outbound
from backend.services.csv_import import CSV_COLUMNS
from backend.services.reports.form_8949 import (
    Form8949Row,
    build_form_8949_and_schedule_d,
    get_8949_field_config,
    map_8949_rows_to_field_data,
    map_schedule_d_fields,
)
from backend.services.review import build_review
from backend.tests.conftest import init_test_db, remove_temp_db, stub_daily_prices, temp_db_file
from backend.tests.hand_test_tables import figures_tables

ROOT = Path(__file__).resolve().parents[2]
COMMITTED = ROOT / "testdata" / "reference_ledger.csv"
UPDATE = "BTCTX_UPDATE_TEST_PACK"


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed_ledger = _script("seed_ledger")
reference_figures = _script("reference_figures")

# One worker seeds the ledger once a run (--dist loadgroup, as test_printed_forms.py's)
pytestmark = pytest.mark.xdist_group("reference_csv")

USER, PASSWORD = "csv-user", "csv-password-123"
FORMS_YEARS = (2024, 2025, 2026)
# After the ledger's last choice and before any run of this test: the committed file's coins_chosen_at
CHOSEN_AT = "2026-10-01T12:00:00Z"
ROWS = len(seed_ledger.ledger_rows(with_prices=True))


async def no_prices(day, full):
    return {}, False


@contextmanager
def install():
    """The app on a database of its own, as a fresh install has it, claimed
    and logged in, its price source Nobody, with nothing asked of the
    network; yields (client, its sessionmaker). Whatever was in use before
    is put back."""
    path = temp_db_file()
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    init_test_db(engine)
    Session = sessionmaker(bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    first_run.clear_code()
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(outbound, "_current", outbound.NetworkSettings(price_source="off"))
            mp.setattr("backend.services.price_history.find_prices", no_prices)  # the stored ones only
            c = TestClient(app)
            seed_ledger.log_in(c, USER, PASSWORD, first_run.ensure_code())
            yield c, Session
    finally:
        first_run.clear_code()
        app.dependency_overrides[get_db] = previous
        engine.dispose()
        remove_temp_db(path)


def database_file(Session) -> Path:
    return Path(Session.kw["bind"].url.database)


def csv_file(text: str) -> dict:
    return {"file": ("reference_ledger.csv", text.encode(), "text/csv")}


def form_fields(db) -> dict[int, list[dict[str, str]]]:
    """Each forms year's IRS fields, sheet by sheet, Schedule D's last, as
    the IRS forms route fills them."""
    fields = {}
    for year in FORMS_YEARS:
        data = build_form_8949_and_schedule_d(year, db)
        size = get_8949_field_config(year)["rows_per_page"]
        short = _chunks_by_box([Form8949Row(**r) for r in data["short_term"]], size)
        long = _chunks_by_box([Form8949Row(**r) for r in data["long_term"]], size)
        sheets = []
        for short_chunk, long_chunk in zip_longest(short, long):
            sheet = {}
            if short_chunk:
                sheet.update(map_8949_rows_to_field_data(short_chunk, page=1, year=year))
            if long_chunk:
                sheet.update(map_8949_rows_to_field_data(long_chunk, page=2, year=year))
            sheets.append(sheet)
        fields[year] = [*sheets, map_schedule_d_fields(data["schedule_d"], year=year)]
    return fields


def results(c, Session) -> dict:
    """What a ledger gives: every figure, every IRS form field, how many rows
    each Ledger Review item lists, and the app's own export of it."""
    with Session() as db:
        figures, fields = reference_figures.figures(db), form_fields(db)
        review = {check["key"]: check["count"] for check in build_review(db)["checks"]}
    export = c.get("/api/backup/csv")
    assert export.status_code == 200, export.text
    return {"figures": figures, "fields": fields, "review": review, "export": export.text}


def make_accounts_under_their_names(c) -> list[dict]:
    """The ledger's accounts under the names the CSV uses (its export has
    each account's name now), each exchange with its 1099-DA switch, as an
    owner adds them in Settings. Returns them, for hiding after the import."""
    accounts = [{**account, "made_as": account["name"]} for account in seed_ledger.ledger_accounts()]
    for account in accounts:
        seed_ledger.make_account(c, account)
    return accounts


def import_csv(c, text: str) -> dict:
    """The file through the import's preview and execute, as the screen
    sends it. Returns the preview."""
    preview = c.post("/api/import/preview", files=csv_file(text))
    assert preview.status_code == 200, preview.text
    assert preview.json()["errors"] == [] and preview.json()["can_import"], preview.json()["errors"]
    r = c.post("/api/import/execute", files=csv_file(text))
    assert r.status_code == 200, r.text
    assert r.json()["imported_count"] == ROWS
    return preview.json()


@pytest.fixture(scope="module")
def seeded(auth_client) -> dict:
    """The reference ledger's own results, every row with its prices, as
    test_seed_ledger.py seeds it."""
    with install() as (c, Session):
        seed_ledger.store_prices(database_file(Session))
        assert seed_ledger.seed(c, with_prices=True) == ROWS
        seed_ledger.store_prices(database_file(Session), later=True)
        return results(c, Session)


def round_trip(text: str, prices: bool = True) -> dict:
    """The CSV imported into an empty install with the same accounts, the
    one hidden afterwards, as the seed does (the stored prices too, unless
    prices=False): its results and the preview."""
    with install() as (c, Session):
        if prices:
            seed_ledger.store_prices(database_file(Session))
        accounts = make_accounts_under_their_names(c)
        preview = import_csv(c, text)
        for account in accounts:
            seed_ledger.finish_account(c, account)
        if prices:
            seed_ledger.store_prices(database_file(Session), later=True)
        return {**results(c, Session), "preview": preview}


def saved_figures() -> dict:
    return json.loads(reference_figures.FIGURES.read_text())


def moved(saved, now) -> list[str]:
    """Where two figure trees differ, both ways: nothing may go missing."""
    return list(reference_figures.differences(saved, now))


def with_a_fixed_day(export: str) -> str:
    """The export with every choice's coins_chosen_at the committed file's."""
    rows = list(csv.DictReader(io.StringIO(export)))
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    writer.writerows({**row, "coins_chosen_at": CHOSEN_AT if row["coins_chosen_at"] else ""} for row in rows)
    return output.getvalue()


def without_column(text: str, column: str) -> str:
    rows = list(csv.DictReader(io.StringIO(text)))
    kept = [name for name in CSV_COLUMNS if name != column]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=kept, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def test_the_seeded_ledger_gives_the_saved_figures(seeded):
    assert moved(saved_figures(), seeded["figures"]) == []


def test_the_whole_ledger_survives_an_export_and_an_import(seeded):
    now = round_trip(seeded["export"])
    assert now["preview"]["warnings"] == []
    assert (now["preview"]["total_rows"], now["preview"]["valid_rows"]) == (ROWS, ROWS)
    assert moved(seeded["figures"], now["figures"]) == []
    assert moved(saved_figures(), now["figures"]) == []
    assert now["fields"] == seeded["fields"]
    assert now["review"] == seeded["review"]
    # Exported again, the same file to the byte: nothing a figure can't show was lost either
    assert now["export"] == seeded["export"]


def test_the_committed_csv_is_todays_export(seeded):
    made = with_a_fixed_day(seeded["export"])
    if os.environ.get(UPDATE):
        COMMITTED.write_bytes(made.encode())
    assert COMMITTED.read_bytes().decode() == made, (
        "testdata/reference_ledger.csv is stale: `make test-pack` makes it again from the reference ledger")


def test_the_committed_csv_gives_the_same_figures(seeded):
    """The file a person downloads, not only a fresh export."""
    text = COMMITTED.read_bytes().decode()
    now = round_trip(text)
    assert moved(saved_figures(), now["figures"]) == []
    assert now["fields"] == seeded["fields"]
    assert now["review"] == seeded["review"]
    assert now["export"] == text


@pytest.mark.parametrize("column", ["broker_reporting", "fmv_usd", "chosen_coins", "price_moment"])
def test_a_column_left_out_is_seen(seeded, column):
    """So we know the round trip checks: without one of these the file still
    imports, and figures move."""
    assert moved(seeded["figures"], round_trip(without_column(seeded["export"], column))["figures"]) != []


@pytest.mark.parametrize("column", ["fee_usd", "cost_basis_usd", "acquired_at", "id"])
def test_a_column_the_ledger_cant_do_without_is_refused(seeded, column):
    with install() as (c, _):
        make_accounts_under_their_names(c)
        preview = c.post("/api/import/preview", files=csv_file(without_column(seeded["export"], column)))
    assert preview.status_code == 200, preview.text
    assert preview.json()["errors"] and not preview.json()["can_import"]


def test_coins_chosen_at_left_out_changes_only_the_export(seeded):
    """The day a choice was saved is on the report, but no figure: the second
    export is what sees it lost."""
    now = round_trip(without_column(seeded["export"], "coins_chosen_at"))
    assert moved(seeded["figures"], now["figures"]) == []
    assert now["export"] != seeded["export"]


def test_with_no_prices_stored_only_the_name_of_a_prices_source_goes(seeded):
    """A person's throwaway install has none of the fixture's prices: the
    report's "priced at" can't name where a price came from, and that's all
    that moves. Every value is in the file, so nothing is priced again."""
    now = round_trip(seeded["export"], prices=False)
    assert now["fields"] == seeded["fields"]
    assert now["export"] == seeded["export"]
    differences = moved(seeded["figures"], now["figures"])
    assert differences and all(".report.priced_values[" in d and ".priced_at: " in d for d in differences), differences
    assert figures_tables(now["figures"]) == figures_tables(saved_figures())


def test_a_price_source_moves_nothing_the_guide_compares(seeded):
    """With a price source chosen, the file's values stay as they are; only
    the holdings' market value, which the guide doesn't list, takes a price."""
    with install() as (c, Session), pytest.MonkeyPatch.context() as mp:
        mp.setattr(outbound, "_current", outbound.NetworkSettings(price_source="public"))
        stub_daily_prices(mp, lambda day: 77777)
        accounts = make_accounts_under_their_names(c)
        import_csv(c, seeded["export"])
        for account in accounts:
            seed_ledger.finish_account(c, account)
        now = results(c, Session)
    assert now["fields"] == seeded["fields"]
    assert now["export"] == seeded["export"]
    assert figures_tables(now["figures"]) == figures_tables(saved_figures())
