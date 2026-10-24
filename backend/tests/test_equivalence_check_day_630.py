"""
scripts/equivalence_check.py reuses a release's snapshot only while the
snapshot would hold the same dates. A report prints today's date in its
ledger's tax timezone, so the snapshot is kept by today's date in each of
those zones. Kept by the computer's own date, a baseline was reused across
a midnight in another of them: in Chicago (summer time), Tokyo's at 10:00,
UTC's at 19:00 and New York's at 23:00 (#630).
"""

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import equivalence_inputs as inputs  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = _load("equivalence_check")
snapshot = _load("equivalence_snapshot")
CHICAGO = ZoneInfo("America/Chicago")


def _utc(day, hour, minute=0):
    return datetime(2020, 3, day, hour, minute, tzinfo=timezone.utc)


class _Clock(datetime):
    """The script's clock at `instant`, as a computer in Chicago reads it."""

    instant = _utc(11, 6)

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls.instant.astimezone(CHICAGO).replace(tzinfo=None)
        return cls.instant.astimezone(tz)


def _folder(monkeypatch, tmp_path, instant):
    """The baseline folder equivalence_check names at `instant`."""

    def take(root, out, bench):
        out.mkdir(parents=True)
        (out / "done").touch()

    monkeypatch.setattr(_Clock, "instant", instant)
    monkeypatch.setattr(check, "datetime", _Clock)
    monkeypatch.setattr(check, "STORE", tmp_path)
    monkeypatch.setattr(check, "_git", lambda *args: "0123456789abcdef\n")
    monkeypatch.setattr(check, "_take", take)
    return check._baseline_snapshot("origin/2.0", bench=False, fresh=False).name


def test_a_baseline_is_retaken_after_a_midnight_in_any_ledgers_zone(monkeypatch, tmp_path):
    # Chicago (CDT, from 2020-03-08) 18:00 → 19:30: the UTC ledgers' date moves
    assert _folder(monkeypatch, tmp_path, _utc(10, 23)) != _folder(monkeypatch, tmp_path, _utc(11, 0, 30))
    # 22:30 → 23:30, the same UTC day: New York's date alone moves
    assert _folder(monkeypatch, tmp_path, _utc(11, 3, 30)) != _folder(monkeypatch, tmp_path, _utc(11, 4, 30))
    # 23:30 → 00:30: Chicago's date moves
    assert _folder(monkeypatch, tmp_path, _utc(11, 4, 30)) != _folder(monkeypatch, tmp_path, _utc(11, 5, 30))
    # 09:00 → 11:00: Tokyo's date moves
    assert _folder(monkeypatch, tmp_path, _utc(11, 14)) != _folder(monkeypatch, tmp_path, _utc(11, 16))


def test_a_baseline_is_reused_while_every_date_holds(monkeypatch, tmp_path):
    # 01:00 → 08:00 in Chicago: the same date in UTC, New York, Chicago and Tokyo
    assert _folder(monkeypatch, tmp_path, _utc(11, 6)) == _folder(monkeypatch, tmp_path, _utc(11, 13))


def test_the_baseline_is_kept_by_every_ledgers_zone():
    assert {zone for _, zone, _ in snapshot._ledgers()} == set(inputs.ZONES)
