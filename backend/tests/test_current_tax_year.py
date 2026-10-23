"""
"This tax year", the one clock (2.0 plan 5.15): services/tax_time's
current_tax_year, which the past-year warning (5.8) reads. The tests pin it
to 2009, before any year they enter (conftest.py), so no save meets the
warning and the suite doesn't change on its own every 1 January; a test of
the warning sets it with `tax_year`. Outside the tests it is the year it is
now in the tax timezone, and nothing binds it by name, so the pin reaches
every caller.
"""

import ast
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from backend.services import tax_time
from backend.tests.conftest import PINNED_TAX_YEAR

# Taken as this module is collected, before conftest pins it for the session
REAL_CLOCK = tax_time.current_tax_year

ROOT = Path(__file__).resolve().parents[2]
ZONES = ("UTC", "America/Chicago", "Asia/Tokyo")
# Folders of other code a checkout may hold: virtual environments, a build's copies
NOT_OURS = {".venv", "build", "node_modules"}


@pytest.mark.parametrize("zone", ZONES)
def test_this_tax_year_is_2009_in_the_tests(zone):
    assert PINNED_TAX_YEAR == 2009
    assert tax_time.current_tax_year(ZoneInfo(zone)) == 2009


def test_a_test_of_the_warning_sets_it(tax_year):
    tax_year(2026)
    assert all(tax_time.current_tax_year(ZoneInfo(zone)) == 2026 for zone in ZONES)


def test_the_clock_held_here_is_the_real_one():
    assert REAL_CLOCK is not tax_time.current_tax_year  # the tests' pin is in place
    assert (REAL_CLOCK.__module__, REAL_CLOCK.__name__) == ("backend.services.tax_time", "current_tax_year")


class _NewYearsNight(datetime):
    """2026-01-01 03:00 UTC: still 2025 in Chicago, already 2026 in Tokyo."""

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 1, 1, 3, tzinfo=timezone.utc).astimezone(tz)


@pytest.mark.parametrize(("zone", "year"), [("UTC", 2026), ("America/Chicago", 2025), ("Asia/Tokyo", 2026)])
def test_outside_the_tests_it_is_the_year_now_in_the_tax_timezone(monkeypatch, zone, year):
    monkeypatch.setattr(tax_time, "datetime", _NewYearsNight)
    assert REAL_CLOCK(ZoneInfo(zone)) == year


def test_outside_the_tests_it_follows_the_computers_clock():
    tz = ZoneInfo("Asia/Tokyo")
    before = datetime.now(tz).year
    assert REAL_CLOCK(tz) in {before, datetime.now(tz).year}


def _binds_the_clock_by_name(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(isinstance(node, ast.ImportFrom) and node.module == "backend.services.tax_time"
               and any(alias.name in ("current_tax_year", "*") for alias in node.names)
               for node in ast.walk(tree))


def test_nothing_binds_the_clock_by_name():
    """`from backend.services.tax_time import current_tax_year` would keep the
    real clock past the tests' pin: every caller reads tax_time.current_tax_year."""
    sources = [path for folder in ("backend", "mcp_server", "scripts", "desktop") for path in (ROOT / folder).rglob("*.py")
               if not NOT_OURS & set(path.relative_to(ROOT).parts)]
    assert len(sources) > 100
    assert [str(path.relative_to(ROOT)) for path in sources if _binds_the_clock_by_name(path)] == []
