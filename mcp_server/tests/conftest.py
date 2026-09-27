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
    from backend.services import outbound, price_history

    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings(price_source="public"))
    price_history.reset_state()
