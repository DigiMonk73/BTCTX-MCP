"""
An error nobody expected is said and logged without its own text, which
can carry SQL with its parameters (a transaction's date) or a server path:
the answer is a fixed sentence, the log names the error's type at ERROR,
its trace only at DEBUG (backend/unexpected_errors.py). The CSV and River
imports (a locked database answers busy, as other saves do) and the AI
preview's dry run (#204); the IRS forms and a restore stopped by something
other than the backup itself (#422); an error no route handled, Ledger
Review's dry run of Recalculate Ledger, the tax timezone change's
recalculation, the startup steps, the restore's refresh, the price
source's note and a report's year-end price (#430).
"""

import sqlite3

import pytest
from sqlalchemy.exc import OperationalError

from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend.routers.backup import RESTORE_FAILED
from backend.routers.csv_import import IMPORT_BUSY, IMPORT_FAILED
from backend.routers.reports import IRS_FORMS_FAILED
from backend.services.entry_import import SIMULATION_BUSY, SIMULATION_FAILED
from backend.tests.conftest import stub_daily_prices
from backend.tests.test_imports_do_not_block import CSV, ENTRY, RIVER_ROW
from backend.unexpected_errors import UNEXPECTED

LEAKY = ("(sqlite3.OperationalError) disk I/O error [SQL: INSERT INTO transactions (timestamp) "
         "VALUES (?)] [parameters: ('2019-07-04 09:00:00',)] /data/btctx.db")
CASES = {
    "CSV import": ("backend.routers.csv_import.execute_import",
                   "/api/import/execute", {"files": {"file": ("x.csv", CSV, "text/csv")}}),
    "River import": ("backend.routers.river_import.execute_import",
                     "/api/import/river/execute", {"json": {"rows": [RIVER_ROW]}}),
}


@pytest.fixture
def clean(auth_client, monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 50000)
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    yield auth_client
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def _raises(error):
    def fails(*args, **kwargs):
        raise error
    return fails


def _leaked(text: str) -> bool:
    return "2019-07-04" in text or "/data/" in text


@pytest.mark.parametrize("case", list(CASES))
def test_an_unexpected_failure_answers_a_fixed_sentence(clean, monkeypatch, caplog, case):
    step, url, request = CASES[case]
    monkeypatch.setattr(step, _raises(RuntimeError(LEAKY)))
    with caplog.at_level("INFO"):
        r = clean.post(url, **request)
    assert (r.status_code, r.json()) == (500, {"detail": IMPORT_FAILED})
    assert f"{case} failed: RuntimeError" in caplog.text and not _leaked(caplog.text)


LOCKED = OperationalError("INSERT INTO transactions", {}, sqlite3.OperationalError("database is locked"))
# "locked" in a query's parameters, not SQLite's message: not busy
NOT_LOCKED = OperationalError("INSERT INTO transactions", ("locked",), sqlite3.OperationalError("disk I/O error"))


@pytest.mark.parametrize("case", list(CASES))
def test_a_locked_database_answers_busy(clean, monkeypatch, case):
    """#419's review: SQLite's write lock held past the 5 s wait is the
    likeliest unexpected failure; other saves answer it busy (503). Only
    SQLite's own message says so."""
    step, url, request = CASES[case]
    monkeypatch.setattr(step, _raises(LOCKED))
    assert clean.post(url, **request).json() == {"detail": IMPORT_BUSY}
    monkeypatch.setattr(step, _raises(NOT_LOCKED))
    r = clean.post(url, **request)
    assert (r.status_code, r.json()) == (500, {"detail": IMPORT_FAILED})


def test_the_ai_previews_dry_run_names_no_error_text(clean, monkeypatch, caplog):
    """#419's review: a row the AI preview's dry run stopped at carried the
    error's own text to the AI connector (and its provider), and the log had
    its trace at ERROR."""
    monkeypatch.setattr("backend.services.entry_import.create_transaction_record", _raises(RuntimeError(LEAKY)))
    with caplog.at_level("INFO"):
        r = clean.post("/api/import/entries/preview", json={"rows": [ENTRY]})
    [row] = r.json()["results"]
    assert (row["status"], row["errors"]) == ("rejected", [SIMULATION_FAILED])
    assert not _leaked(r.text)
    assert "Entry simulation of row 1 failed: RuntimeError" in caplog.text and not _leaked(caplog.text)


def test_the_ai_previews_dry_run_answers_busy(clean, monkeypatch):
    monkeypatch.setattr("backend.services.entry_import.create_transaction_record", _raises(LOCKED))
    [row] = clean.post("/api/import/entries/preview", json={"rows": [ENTRY]}).json()["results"]
    assert (row["status"], row["errors"]) == ("rejected", [SIMULATION_BUSY])


def test_the_irs_forms_name_no_error_text(clean, monkeypatch, caplog):
    """#422: the IRS forms answered "IRS report generation failed: {e}"
    and logged the text with its trace at ERROR."""
    monkeypatch.setattr("backend.routers.reports.build_form_8949_and_schedule_d", _raises(RuntimeError(LEAKY)))
    with caplog.at_level("INFO"):
        r = clean.get("/api/reports/irs_reports", params={"year": 2024})
    assert (r.status_code, r.json()) == (500, {"detail": IRS_FORMS_FAILED})
    assert "IRS forms for 2024 failed: RuntimeError" in caplog.text and not _leaked(caplog.text)


def test_the_irs_forms_keep_a_refusals_own_words(clean, monkeypatch):
    """#422: an HTTPException raised while the forms are made keeps its
    status and words (none is raised there today: a guard)."""
    why = "Withdrawal of 0.05 BTC on 2024-06-01: it has no Proceeds (USD) value (enter it in that transaction)."
    monkeypatch.setattr("backend.routers.reports.build_form_8949_and_schedule_d",
                        _raises(HTTPException(status_code=422, detail=why)))
    r = clean.get("/api/reports/irs_reports", params={"year": 2024})
    assert (r.status_code, r.json()) == (422, {"detail": why})


def test_a_restore_stopped_unexpectedly_names_no_error_text(clean, monkeypatch, caplog):
    """#422: anything but the backup's own plain words (restore_backup's
    ValueErrors) came back as "Restore failed: {e}"."""
    monkeypatch.setattr("backend.routers.backup.restore_backup", _raises(OSError(LEAKY)))
    with caplog.at_level("INFO"):
        r = clean.post("/api/backup/restore", data={"password": "pw"}, files={"file": ("b.btx", b"x")})
    assert (r.status_code, r.json()) == (500, {"detail": RESTORE_FAILED})
    assert "Restore failed: OSError" in caplog.text and not _leaked(caplog.text)
    monkeypatch.setattr("backend.routers.backup.restore_backup", _raises(ValueError("This file is damaged.")))
    r = clean.post("/api/backup/restore", data={"password": "pw"}, files={"file": ("b.btx", b"x")})
    assert (r.status_code, r.json()) == (400, {"detail": "Restore failed: This file is damaged."})


# #430
def _fails() -> dict:
    raise RuntimeError(LEAKY)


def test_an_error_no_route_handled_answers_a_fixed_sentence(clean, caplog):
    """Starlette's own handler answered "Internal Server Error" but raised
    the error again for the server, which logged its whole trace at ERROR
    (here: the test client raised it)."""
    from backend.main import app

    route = APIRoute("/api/test-430", _fails, methods=["GET"])
    app.router.routes.insert(0, route)
    try:
        with caplog.at_level("INFO"):
            r = TestClient(app).get("/api/test-430?q=1")
    finally:
        app.router.routes.remove(route)
    assert (r.status_code, r.json()) == (500, {"detail": UNEXPECTED})
    assert r.headers["cache-control"] == "no-store" and r.headers["x-frame-options"] == "DENY"
    assert "GET /api/test-430 failed: RuntimeError" in caplog.text and not _leaked(caplog.text)  # no query either


def test_ledger_reviews_dry_run_logs_no_error_text(clean, monkeypatch, caplog):
    from backend.services import review

    monkeypatch.setattr("backend.services.transaction.recalculate_all_transactions", _raises(RuntimeError(LEAKY)))
    from backend.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    with caplog.at_level("INFO"):
        assert review.simulate_recalculation(db) == (None, review.DRY_RUN_FAILED)
    assert "Recalculate Ledger failed: RuntimeError" in caplog.text and not _leaked(caplog.text)


def test_the_tax_timezone_change_shows_only_its_own_words(clean, monkeypatch, caplog):
    """Its recalculation's ValueError was answered as it was (400 with its text)."""
    r = clean.put("/api/settings/tax-timezone", json={"timezone": "Not/AZone", "chosen": True})
    assert r.status_code == 400 and "Unknown timezone" in r.json()["detail"]
    monkeypatch.setattr("backend.routers.settings.recalculate_all_transactions", _raises(ValueError(LEAKY)))
    with caplog.at_level("INFO"):
        r = clean.put("/api/settings/tax-timezone", json={"timezone": "UTC", "chosen": True})
    assert (r.status_code, r.json()) == (500, {"detail": UNEXPECTED})
    assert "PUT /api/settings/tax-timezone failed: ValueError" in caplog.text and not _leaked(caplog.text)


def _ai_key_file(monkeypatch):
    from backend.services import ai_key
    monkeypatch.setattr(ai_key, "mode", lambda: "mac")
    return "backend.services.ai_key.sync"


@pytest.mark.parametrize("helper, inner, logged", [
    ("_load_network_settings", "backend.services.outbound.load", "Reading the network settings failed"),
    ("_download_hourly_prices", "backend.services.hourly_prices.download_if_public",
     "Starting the hourly price download failed"),
    ("_prepare_first_run", "backend.services.first_run.prepare", "Preparing the first-run setup code failed"),
    ("_sync_ai_key_file", None, "Writing the AI key file failed"),
])
def test_the_startup_steps_log_no_error_text(clean, monkeypatch, caplog, helper, inner, logged):
    import backend.main as main

    monkeypatch.setattr(inner or _ai_key_file(monkeypatch), _raises(RuntimeError(LEAKY)))
    with caplog.at_level("INFO"):
        getattr(main, helper)()
    assert f"{logged}: RuntimeError" in caplog.text and not _leaked(caplog.text)


def test_the_restores_refresh_logs_no_error_text(clean, monkeypatch, caplog):
    from backend.routers import backup as backup_router

    monkeypatch.setattr("backend.services.outbound.load", _raises(RuntimeError(LEAKY)))
    monkeypatch.setattr("backend.services.first_run.prepare", lambda db: None)
    from backend.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    with caplog.at_level("INFO"):
        backup_router._refresh_after_restore(db)
    assert "Refreshing the price settings after the restore failed: RuntimeError" in caplog.text
    assert not _leaked(caplog.text)


def test_the_price_sources_note_logs_no_error_text(clean, monkeypatch, caplog):
    """The server's own price choice applies even when the note that none
    was chosen in the app can't be written."""
    from backend.services import outbound

    monkeypatch.setattr(outbound, "from_env", lambda: outbound.NetworkSettings(price_source="off", managed=True))
    monkeypatch.setattr(outbound, "_mark_unchosen", _raises(RuntimeError(LEAKY)))
    from backend.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    try:
        with caplog.at_level("INFO"):
            assert outbound.load(db).price_source == "off"
    finally:
        monkeypatch.undo()
        outbound.load(db)
    assert "Recording that no price source was chosen in the app failed: RuntimeError" in caplog.text
    assert not _leaked(caplog.text)


def test_a_reports_year_end_price_logs_no_error_text(clean, monkeypatch, caplog):
    from datetime import datetime, timezone

    from backend.services.reports import reporting_core

    monkeypatch.setattr("backend.services.hourly_prices.price_at", _raises(RuntimeError(LEAKY)))
    from backend.database import get_db
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    with caplog.at_level("INFO"):
        assert reporting_core._held_value_price(db, datetime(2020, 1, 1, tzinfo=timezone.utc)) is None
    assert "The BTC price for 2020-01-01T00:00:00+00:00 failed: RuntimeError" in caplog.text
    assert not _leaked(caplog.text)
