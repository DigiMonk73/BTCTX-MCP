"""
The connector with an AI key (Docker/StartOS), and with a config from before
v1.0.3 that still holds the BitcoinTX password (btctx_mcp/client.py).
The Mac app's key file: test_key_file.py.
"""

import logging
from pathlib import Path

import httpx
import pytest
from mcp import Client

from btctx_mcp import server
from btctx_mcp.client import KEY_REFUSED, PASSWORD_REFUSED, BtctxClient, BtctxError
from test_server import backend_db, call, mcp_client  # noqa: F401  (fixtures)

pytestmark = pytest.mark.anyio

KEY = "btctx_ak_" + "k" * 43


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def env(monkeypatch):
    for name in ("BTCTX_URL", "BTCTX_AI_KEY", "BTCTX_USERNAME", "BTCTX_PASSWORD", "BTCTX_MCP_FILE"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def mock(status=200, body=None):
    """A fake BitcoinTX that records what it was sent."""
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, json=[] if body is None else body)

    return httpx.MockTransport(handler), seen


# Every tool that talks to BitcoinTX, with arguments it accepts.
ROW = {"date": "2024-03-01", "type": "Deposit", "amount": "0.01",
       "from_account": "External", "to_account": "Wallet", "source": "Income"}
TOOL_ARGS = {
    "get_portfolio": {}, "list_transactions": {}, "get_btc_price": {}, "review_ledger": {},
    "preview_transactions": {"transactions": [ROW]}, "add_transactions": {"transactions": [ROW]},
    "update_transaction": {"transaction_id": 1, "amount": "0.1"},
    "delete_transaction": {"transaction_id": 1}, "recalculate_ledger": {}, "backup_ledger": {},
}


@pytest.mark.parametrize("with_key", [False, True], ids=["password only", "key and password"])
async def test_a_password_in_the_config_is_refused_and_never_sent(env, with_key):
    env.setenv("BTCTX_URL", "http://btctx.test")
    env.setenv("BTCTX_USERNAME", "admin")
    env.setenv("BTCTX_PASSWORD", "hunter2-secret")
    if with_key:
        env.setenv("BTCTX_AI_KEY", KEY)
    sent = []

    async def no_network(self, request, **kwargs):
        sent.append(request)
        raise AssertionError("no request may be made")

    env.setattr(httpx.AsyncClient, "send", no_network)
    btctx = BtctxClient.from_env()
    server.set_client(btctx)
    try:
        async with Client(server.mcp) as client:
            tools = {t.name for t in (await client.list_tools()).tools}
            assert tools == set(TOOL_ARGS) | {"get_ledger_guide"}  # a new tool goes in TOOL_ARGS
            for name, args in TOOL_ARGS.items():
                text = await call(client, name, args, expect_error=True)
                assert PASSWORD_REFUSED in text, name
                assert "hunter2" not in text
    finally:
        server.set_client(None)
        await btctx.aclose()
    assert sent == []


def test_from_env_uses_the_key_or_else_the_mac_key_file(env, tmp_path):
    env.setenv("BTCTX_AI_KEY", f"  {KEY}\n")
    client = BtctxClient.from_env()
    assert not client.uses_key_file and client._ai_key == KEY
    env.delenv("BTCTX_AI_KEY")
    env.setenv("BTCTX_MCP_FILE", str(tmp_path / "mcp.json"))
    client = BtctxClient.from_env()
    assert client.uses_key_file and client._key_file == tmp_path / "mcp.json"


async def test_the_key_is_sent_as_a_bearer_token_and_nothing_logs_in():
    transport, seen = mock()
    btctx = BtctxClient(base_url="http://btctx.test", ai_key=KEY, transport=transport)
    assert await btctx.get("/api/transactions") == []
    assert [r.url.path for r in seen] == ["/api/transactions"]
    assert seen[0].headers["authorization"] == f"Bearer {KEY}"
    assert "cookie" not in seen[0].headers
    await btctx.aclose()


async def test_the_key_never_shows_in_errors_or_logs(caplog):
    caplog.set_level(logging.DEBUG)
    transport, seen = mock(401, {"detail": "AI key not accepted: it was replaced or revoked, or was copied wrong."})
    btctx = BtctxClient(base_url="http://btctx.test", ai_key=KEY, transport=transport)
    with pytest.raises(BtctxError) as e:
        await btctx.get("/api/transactions")
    assert "replaced or revoked" in str(e.value)
    assert len(seen) == 1  # a wrong key isn't retried
    assert KEY not in str(e.value) and KEY not in caplog.text
    await btctx.aclose()


async def test_a_refused_action_says_to_do_it_in_bitcointx():
    transport, _ = mock(403, {"detail": "The AI key can't do this. Log in to BitcoinTX to do it."})
    btctx = BtctxClient(base_url="http://btctx.test", ai_key=KEY, transport=transport)
    with pytest.raises(BtctxError, match="Ask the user to do it in BitcoinTX") as e:
        await btctx.post("/api/settings/ai-key", json={})
    assert str(e.value) == KEY_REFUSED
    await btctx.aclose()


async def test_backup_ledger_returns_the_file_name(mcp_client, backend_db):  # noqa: F811
    result = await call(mcp_client, "backup_ledger")
    copy = Path(backend_db.url.database).parent / "backups" / result["file"]
    try:
        assert copy.exists() and result["kept"] == 3
        again = await call(mcp_client, "backup_ledger", expect_error=True)
        assert "less than a minute" in again
    finally:
        copy.unlink(missing_ok=True)
