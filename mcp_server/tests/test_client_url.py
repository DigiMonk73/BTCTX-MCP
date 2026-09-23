"""BTCTX_URL may be the server root or the StartOS "MCP API" address (…/api)."""

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
    client = BtctxClient("https://btctx.local/api", "admin", "pw")
    assert str(client._http.base_url) == "https://btctx.local"
