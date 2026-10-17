"""
An unexpected failure of the CSV or River import (not a row the ledger
refused) answers one fixed sentence, as the restore answers in plain words:
the error's own text can carry SQL, a server path or a transaction's date.
A database locked past its wait answers busy, as other saves do. The log
names the error's type, its trace only at DEBUG. The AI preview's dry run
does the same for a row it stops at (#204); so do the IRS forms and a
restore stopped by something other than the backup itself (#422).
"""

import sqlite3

import pytest
from sqlalchemy.exc import OperationalError

from fastapi import HTTPException

from backend.routers.backup import RESTORE_FAILED
from backend.routers.csv_import import IMPORT_BUSY, IMPORT_FAILED
from backend.routers.reports import IRS_FORMS_FAILED
from backend.services.entry_import import SIMULATION_BUSY, SIMULATION_FAILED
from backend.tests.conftest import stub_daily_prices
from backend.tests.test_imports_do_not_block import CSV, ENTRY, RIVER_ROW

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


def test_the_irs_forms_keep_the_ledgers_own_words(clean, monkeypatch):
    """#422: a value to enter in a transaction came back as a 500 reading
    "IRS report generation failed: 422: …"; it keeps its status and words."""
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
