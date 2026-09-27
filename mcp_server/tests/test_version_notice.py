"""
The connector is pinned to a BitcoinTX release in the AI app's settings;
BitcoinTX updates on its own schedule. When the two versions differ, every
tool reply (and error) starts with a line saying so and what to do. A warning
only: the tool still runs.
"""

import pytest
from mcp import Client

from backend.version import app_version
from btctx_mcp import server
from test_server import backend_db, call, mcp_client  # noqa: F401  (fixtures)

pytestmark = pytest.mark.anyio

APP = app_version()


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_notice_wording():
    assert server.mismatch_notice(APP, APP) is None
    assert server.mismatch_notice(None, APP) is None  # run from a source tree
    older = server.mismatch_notice("0.9.0", "1.0.3")
    assert older.startswith("Your BitcoinTX connector is v0.9.0 but BitcoinTX is v1.0.3.")
    assert "change the connector's version (the @v0.9.0 in its uvx command) to @v1.0.3" in older
    newer = server.mismatch_notice("1.1.0", "1.0.3")
    assert "Update BitcoinTX, or set the connector back to v1.0.3" in newer


async def test_same_version_no_notice(mcp_client):  # noqa: F811
    assert "notice" not in await call(mcp_client, "list_transactions")
    guide = await mcp_client.call_tool("get_ledger_guide", {})
    assert not guide.content[0].text.startswith("Your BitcoinTX connector")


async def test_different_version_notice_first_on_every_reply(mcp_client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(server, "connector_version", lambda: "0.9.0")
    result = await call(mcp_client, "list_transactions")
    assert list(result)[0] == "notice"
    assert result["notice"].startswith(f"Your BitcoinTX connector is v0.9.0 but BitcoinTX is v{APP}.")
    assert result["transactions"] == []  # the tool still ran
    guide = await mcp_client.call_tool("get_ledger_guide", {})
    assert guide.content[0].text.startswith("Your BitcoinTX connector is v0.9.0")
    error = await call(mcp_client, "delete_transaction", {"transaction_id": 999}, expect_error=True)
    # (the MCP library puts "Error executing tool …:" in front of every error)
    assert 0 <= error.find("Your BitcoinTX connector is v0.9.0") < error.find("404")


async def test_bitcointx_down_at_first_is_checked_on_a_later_call(backend_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(server, "connector_version", lambda: "0.9.0")
    answers = iter([None, APP])

    class Client_:
        async def app_version(self):
            return next(answers)

        async def request(self, method, path, **kwargs):
            return []

    server.set_client(Client_())
    try:
        async with Client(server.mcp) as client:
            assert "notice" not in await call(client, "list_transactions")  # BitcoinTX didn't say
            assert "notice" in await call(client, "list_transactions")      # now it did
    finally:
        server.set_client(None)
