"""
Every connector test starts with a fresh version check, the connector at
BitcoinTX's own version (the installed package's metadata may be older in a
dev environment; test_version_notice.py sets other versions itself), and with
public price sites chosen.
"""

import pytest

from backend.version import app_version
from btctx_mcp import server


@pytest.fixture(autouse=True)
def same_version_as_the_app(monkeypatch):
    monkeypatch.setattr(server, "connector_version", app_version)
    monkeypatch.setattr(server, "_version", {"checked": False, "notice": None})


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
