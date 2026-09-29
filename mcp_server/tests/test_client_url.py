"""BTCTX_URL may be the server root or the StartOS "MCP API" address (…/api)."""

import logging

import pytest

from btctx_mcp.client import BtctxClient, normalize_base_url


@pytest.mark.parametrize(
    "given, expected",
    [
        ("http://127.0.0.1:8765", "http://127.0.0.1:8765"),
        ("http://127.0.0.1:8765/", "http://127.0.0.1:8765"),
        ("https://btctx.local/api", "https://btctx.local"),
        ("https://btctx.local/api/", "https://btctx.local"),
        (" https://example.com/btc/api ", "https://example.com/btc"),
        ("https://apiary.example", "https://apiary.example"),
    ],
)
def test_normalize_base_url(given, expected):
    assert normalize_base_url(given) == expected


def test_client_requests_go_to_the_root():
    client = BtctxClient("https://btctx.local/api", ai_key="btctx_ak_test")
    assert str(client._http.base_url) == "https://btctx.local"


@pytest.mark.parametrize("url, warns", [
    ("http://192.168.1.50:8080", True),
    ("http://btctx.lan", True),
    ("http://localhost:8080", False),
    ("http://127.0.0.1:8765", False),
    ("http://[::1]:8000", False),
    ("https://adjective-noun.local/api", False),
])
def test_plain_http_to_another_machine_warns_once(url, warns, caplog, monkeypatch):
    """Privacy audit 2026-09-29 (4c), owner decision: over plain http:// to
    another machine the AI key and the ledger cross the network unencrypted.
    The connector still works, and says so once in the AI app's log."""
    import btctx_mcp.client as client_module

    monkeypatch.setattr(client_module, "_warned_plain_http", False)
    caplog.set_level(logging.WARNING, logger="btctx_mcp")
    BtctxClient(base_url=url, ai_key="btctx_ak_x")
    BtctxClient(base_url=url, ai_key="btctx_ak_x")
    warnings = [r for r in caplog.records if "unencrypted" in r.getMessage()]
    assert len(warnings) == (1 if warns else 0), [r.getMessage() for r in caplog.records]
