"""
scripts/equivalence_snapshot.py hides what changes on every run, so two
snapshots of the same code compare equal: here, the moment the Complete Tax
Report prints. From 1.2.5 it is a "GENERATED" line the old "Date:" mask
missed, so every comparison reported a difference on that line.
"""

import importlib.util
import re
import sys
from io import BytesIO
from pathlib import Path

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
