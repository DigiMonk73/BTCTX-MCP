"""
scripts/equivalence_check.py reuses a release's snapshot only within the day
it holds. The reports print the UTC date, so the day is UTC's: keyed by the
computer's own date, an evening west of UTC reused the snapshot of the UTC
day before, and every report's date showed as a difference (#630).
"""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "equivalence_check.py"
_spec = importlib.util.spec_from_file_location("equivalence_check", SCRIPT)
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

# 21:00 in Chicago (CDT) on 2026-10-23 is already 2026-10-24 in UTC
EVENING_WEST = datetime(2026, 10, 24, 2, 0, tzinfo=timezone.utc)


class _Clock(datetime):
    """The script's clock at EVENING_WEST, as a computer in Chicago reads it."""

    @classmethod
    def now(cls, tz=None):
        return EVENING_WEST if tz is not None else datetime(2026, 10, 23, 21, 0)


def test_the_baseline_is_kept_by_the_reports_utc_day(monkeypatch):
    monkeypatch.setattr(check, "datetime", _Clock, raising=False)
    assert check._report_day() == "2026-10-24"


def test_the_baseline_folder_names_that_day(monkeypatch, tmp_path):
    def take(root, out, bench):
        out.mkdir(parents=True)
        (out / "done").touch()

    monkeypatch.setattr(check, "datetime", _Clock, raising=False)
    monkeypatch.setattr(check, "STORE", tmp_path)
    monkeypatch.setattr(check, "_git", lambda *args: "0123456789abcdef\n")
    monkeypatch.setattr(check, "_take", take)
    out = check._baseline_snapshot("origin/2.0", bench=False, fresh=False)
    assert out.name.endswith("-2026-10-24"), out.name
