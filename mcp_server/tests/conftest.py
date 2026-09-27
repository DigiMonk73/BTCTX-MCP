"""
Every connector test starts with a fresh version check, the connector at
BitcoinTX's own version (the installed package's metadata may be older in a
dev environment). test_version_notice.py sets other versions itself.
"""

import pytest

from backend.version import app_version
from btctx_mcp import server


@pytest.fixture(autouse=True)
def same_version_as_the_app(monkeypatch):
    monkeypatch.setattr(server, "connector_version", app_version)
    monkeypatch.setattr(server, "_version", {"checked": False, "notice": None})
