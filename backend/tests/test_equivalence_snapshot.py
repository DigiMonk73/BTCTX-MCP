"""
scripts/equivalence_snapshot.py hides what changes on every run, so two
snapshots of the same code compare equal: here, the moment the Complete Tax
Report prints. From 1.2.5 it is a "GENERATED" line the old "Date:" mask
missed, so every comparison reported a difference on that line.
"""

import ast
import importlib.util
import inspect
import re
import sys
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from pypdf import PdfReader

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
_spec = importlib.util.spec_from_file_location("equivalence_snapshot", SCRIPTS / "equivalence_snapshot.py")
snapshot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(snapshot)

MOMENT = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")


def test_the_report_moment_is_masked(auth_client):
    r = auth_client.get("/api/reports/complete_tax_report", params={"year": 2024})
    assert r.status_code == 200, r.text
    pages = [p.extract_text() or "" for p in PdfReader(BytesIO(r.content)).pages]
    assert any(MOMENT.search(p) for p in pages)
    masked = snapshot.masked_report_pages(pages)
    assert not any(MOMENT.search(p) for p in masked)
    assert any("<now> UTC" in p for p in masked)
    # Only the moment: a line it also hid would hide a real difference
    assert sum(snapshot.REPORT_MOMENT.subn("", p)[1] for p in pages) == 1


def test_the_old_date_line_is_masked_too():
    """Releases up to 1.2.4 print "Date: <time>": the baseline's snapshot."""
    assert snapshot.masked_report_pages(["Date: 2025-01-02 03:04:05"]) == ["Date: <now>"]


def test_the_reference_ledger_loads_from_any_folder(tmp_path, monkeypatch):
    """Review of #140: a release's snapshot runs in its own worktree, which
    may have no testdata/; both sides read this checkout's ledger."""
    monkeypatch.chdir(tmp_path)
    ledgers = {name: txs for name, _, txs in snapshot._ledgers()}
    assert len(ledgers["reference"]) >= 108
    assert not any("why" in tx for tx in ledgers["reference"])


def test_this_tax_year_is_the_tests_on_a_side_that_has_the_clock(monkeypatch):
    """2.0's past-year warning (plan 5.8) never asks in-process: the snapshot
    pins "this tax year" as the backend tests do (5.15), so each side's
    writes save as before the warning."""
    from backend.services import tax_time

    monkeypatch.setattr(tax_time, "current_tax_year", lambda tz: 2026)
    snapshot.pin_tax_year()
    assert tax_time.current_tax_year(ZoneInfo("America/Chicago")) == 2009


def test_each_snapshot_pins_it():
    """Called as each side's snapshot sets up (its globals are the side's
    own, so a test can't run that setup without changing this session's)."""
    calls = [node.func.id for node in ast.walk(ast.parse(inspect.getsource(snapshot._shut_out_the_world)))
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
    assert "pin_tax_year" in calls


def test_a_side_without_the_clock_gets_none(monkeypatch):
    """A release before 2.0 has no current_tax_year and no warning: nothing
    is added that its code would never read."""
    from backend.services import tax_time

    monkeypatch.delattr(tax_time, "current_tax_year")
    snapshot.pin_tax_year()
    assert not hasattr(tax_time, "current_tax_year")


def test_settings_1x_never_writes_are_left_out_of_the_database_rows(tmp_path):
    """2.0's recalculated_by (#352) and accounts_old_rows (#348): the pin's
    1.x side never writes them, so the comparison would count every ledger."""
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    with engine.begin() as con:
        con.execute(text("CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT)"))
        for key in ("tax_timezone", "recalculated_by", "accounts_old_rows"):
            con.execute(text("INSERT INTO app_settings VALUES (:k, 'x')"), {"k": key})
    assert [row["key"] for row in snapshot.database_rows(engine)["app_settings"]] == ["tax_timezone"]
    engine.dispose()
