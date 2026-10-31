"""
Every connector test starts with a fresh version check and the accounts not
read yet, the connector at
BitcoinTX's own version (the installed package's metadata may be older in a
dev environment; test_version_notice.py sets other versions itself), and with
public price sites chosen. "This tax year" is the backend tests' (2009),
unless a test sets it (tax_year).
"""

import pytest

from backend.tests.conftest import PINNED_TAX_YEAR
from backend.version import app_version
from btctx_mcp import server


@pytest.fixture(autouse=True, scope="session")
def pinned_tax_year():
    """These tests drive the backend in-process, in the same run as the
    backend's own: "this tax year" is pinned for them too (2.0 plan 5.15),
    whichever tests ran first on the worker, so no write meets the
    past-year warning (5.8)."""
    from backend.services import tax_time

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(tax_time, "current_tax_year", lambda tz: PINNED_TAX_YEAR)
        yield


@pytest.fixture
def tax_year(monkeypatch):
    """Sets "this tax year" for one test of the past-year warning: tax_year(2026)."""
    from backend.services import tax_time

    def set_year(year: int) -> None:
        monkeypatch.setattr(tax_time, "current_tax_year", lambda tz: year)

    return set_year


@pytest.fixture(autouse=True)
def same_version_as_the_app(monkeypatch):
    monkeypatch.setattr(server, "connector_version", app_version)
    monkeypatch.setattr(server, "_version", {"checked": False, "notice": None})


@pytest.fixture(autouse=True)
def accounts_not_read_yet(monkeypatch):
    """Each test's connector reads the user's accounts afresh, as a new run does."""
    monkeypatch.setattr(server, "_accounts", {"names": None})


@pytest.fixture(autouse=True)
def public_price_source(monkeypatch):
    """The owner chose public price sites (a fresh install has no source yet)."""
    from backend.services import hourly_prices, outbound, price_history

    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings(price_source="public"))
    price_history.reset_state()
    hourly_prices.reset_state()


@pytest.fixture(autouse=True)
def no_hourly_prices(monkeypatch, tmp_path):
    """No hourly price from a source and no download of the year files: a
    value is priced at the stubbed day's price (services/hourly_prices.py)."""
    from backend.services import hourly_prices

    async def no_hours(hour, files_end, stored):
        return {}

    monkeypatch.setattr(hourly_prices, "find_hours", no_hours)
    monkeypatch.setattr(hourly_prices, "start_download", lambda: False)
    monkeypatch.setattr(hourly_prices, "DATA_DIR", str(tmp_path))


@pytest.fixture(autouse=True)
def first_run_files(monkeypatch, tmp_path):
    """The first-run setup code's file in a temp folder, not next to the
    database DATABASE_FILE names (backend/services/first_run.py)."""
    from backend.services import first_run

    monkeypatch.setattr(first_run, "DATA_DIR", str(tmp_path))
