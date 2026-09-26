"""
The Mac app's AI assistant key (backend/services/mcp_key.py) and the MCP
client's use of it (btctx_mcp/client.py): no password in any MCP config.
"""

import json
import os
import stat

import httpx
import pytest
from mcp import Client

from backend.database import get_db
from backend.main import app
from backend.services import mcp_key
from btctx_mcp import server
from btctx_mcp.client import BtctxClient, BtctxError
from test_server import backend_db, call  # noqa: F401  (fixture)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def desktop(monkeypatch, tmp_path, backend_db):  # noqa: F811
    """The backend as the Mac app runs it, with its key file written."""
    key_file = tmp_path / "BitcoinTX" / "mcp.json"
    monkeypatch.setenv("BTCTX_DESKTOP", "1")
    monkeypatch.setenv("BTCTX_DESKTOP_PREFERRED_PORT", "8765")
    monkeypatch.setenv("BTCTX_DESKTOP_ACTUAL_PORT", "8765")
    monkeypatch.setenv("BTCTX_MCP_FILE", str(key_file))
    with _db() as db:
        mcp_key.sync(db)
    return key_file


class _db:
    def __enter__(self):
        self.gen = app.dependency_overrides[get_db]()
        return next(self.gen)

    def __exit__(self, *exc):
        self.gen.close()


def _token(key_file):
    return json.loads(key_file.read_text())["token"]


def _http(client_host="127.0.0.1"):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(client_host, 50000)),
        base_url="http://127.0.0.1:8765",
    )


def _key_client(key_file, client_host="127.0.0.1"):
    return BtctxClient(
        key_file=key_file, transport=httpx.ASGITransport(app=app, client=(client_host, 50000))
    )


async def test_key_file_is_private_and_complete(desktop):
    assert stat.S_IMODE(os.stat(desktop).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(desktop.parent).st_mode) == 0o700
    data = json.loads(desktop.read_text())
    assert data["url"] == "http://127.0.0.1:8765" and data["port"] == 8765
    assert data["pid"] == os.getpid() and data["version"]
    assert len(data["token"]) >= 43  # 32 random bytes
    with _db() as db:  # only a hash is stored
        assert mcp_key._get(db, mcp_key.HASH_KEY) == mcp_key._hash(data["token"])
        assert data["token"] not in json.dumps([mcp_key._get(db, k) for k in (mcp_key.HASH_KEY,)])


async def test_key_stays_the_same_across_restarts(desktop):
    before = _token(desktop)
    with _db() as db:
        mcp_key.sync(db)
    assert _token(desktop) == before


async def test_mcp_tools_work_with_no_password(desktop):
    btctx = _key_client(desktop)
    server.set_client(btctx)
    try:
        async with Client(server.mcp) as client:
            assert (await call(client, "list_transactions"))["transactions"] == []
            preview = await call(client, "preview_transactions", {"transactions": [{
                "date": "2024-03-01", "type": "Deposit", "amount": "0.01",
                "from_account": "External", "to_account": "Wallet", "source": "Income",
            }]})
            assert preview["ready_count"] == 1
    finally:
        server.set_client(None)
        await btctx.aclose()


async def test_reset_key_locks_out_old_copies_but_not_the_mcp(desktop):
    old = _token(desktop)
    btctx = _key_client(desktop)
    try:
        assert await btctx.get("/api/transactions") == []
        with _db() as db:
            mcp_key.rotate(db)
        assert _token(desktop) != old
        # The MCP server re-reads the file and carries on...
        assert await btctx.get("/api/transactions") == []
        # ...a copy of the old key doesn't.
        async with _http() as h:
            r = await h.get("/api/transactions", headers={"Authorization": f"Bearer {old}"})
            assert r.status_code == 401 and "reset" in r.json()["detail"]
    finally:
        await btctx.aclose()


async def test_key_refused_from_another_computer(desktop):
    async with _http("192.168.1.50") as h:
        r = await h.get("/api/transactions", headers={"Authorization": f"Bearer {_token(desktop)}"})
    assert r.status_code == 401 and "this computer" in r.json()["detail"]


async def test_no_key_outside_the_mac_app(desktop, monkeypatch):
    token = _token(desktop)
    monkeypatch.delenv("BTCTX_DESKTOP")
    async with _http() as h:
        r = await h.get("/api/transactions", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


async def test_access_switch_and_login_only_actions(desktop):
    token = {"Authorization": f"Bearer {_token(desktop)}"}
    async with _http() as h:
        # The key can't change its own access, reset itself or delete everything.
        assert (await h.put("/api/settings/ai-access", json={"on": True}, headers=token)).status_code == 403
        assert (await h.post("/api/settings/ai-access/reset-key", headers=token)).status_code == 403
        assert (await h.delete("/api/transactions/delete_all", headers=token)).status_code == 403
        # Backup, restore and CSV import stay login-only.
        assert (await h.get("/api/backup/csv", headers=token)).status_code == 401
        assert (await h.post("/api/backup/download", data={"password": "x"}, headers=token)).status_code == 401
        restore = await h.post("/api/backup/restore", data={"password": "x"},
                               files={"file": ("b.btx", b"x")}, headers=token)
        assert restore.status_code == 401

        # The user turns access off (logged in): the key stops working.
        login = await h.post("/api/login", json={"username": "admin", "password": "password"})
        assert login.status_code == 200
        r = await h.put("/api/settings/ai-access", json={"on": False})
        assert r.json() == {"available": True, "on": False, "key_file": str(desktop)}
        h.cookies.clear()
        r = await h.get("/api/transactions", headers=token)
        assert r.status_code == 401 and "turned off" in r.json()["detail"]


async def test_restored_database_keeps_the_key_the_mcp_has(desktop):
    token = _token(desktop)
    with _db() as db:  # a restored backup carries another install's hash
        mcp_key._set(db, mcp_key.HASH_KEY, "0" * 64)
        db.commit()
        mcp_key.sync(db)
    assert _token(desktop) == token
    async with _http() as h:
        r = await h.get("/api/transactions", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


async def test_clear_errors_when_the_app_isnt_found(tmp_path):
    missing = tmp_path / "mcp.json"
    btctx = BtctxClient(key_file=missing, transport=httpx.ASGITransport(app=app))
    with pytest.raises(BtctxError, match="not found") as e:
        await btctx.get("/api/transactions")
    assert str(missing) in str(e.value)

    missing.write_text(json.dumps({"url": "http://127.0.0.1:8765", "pid": 999_999_999, "token": "x" * 43}))
    with pytest.raises(BtctxError, match="no longer running"):
        await btctx.get("/api/transactions")
    await btctx.aclose()


def test_from_env_prefers_a_login_then_the_key_file(monkeypatch, tmp_path):
    monkeypatch.setenv("BTCTX_USERNAME", "u")
    monkeypatch.setenv("BTCTX_PASSWORD", "p")
    assert not BtctxClient.from_env().uses_key_file
    monkeypatch.delenv("BTCTX_PASSWORD")
    monkeypatch.setenv("BTCTX_MCP_FILE", str(tmp_path / "mcp.json"))
    client = BtctxClient.from_env()
    assert client.uses_key_file and client._key_file == tmp_path / "mcp.json"


def test_setup_guide_puts_no_password_in_a_mac_config():
    from pathlib import Path

    guide = (Path(__file__).parents[1] / "AI_SETUP.md").read_text()
    mac = guide[guide.index("## 2A."):guide.index("## 2B.")]
    assert "YOUR_BITCOINTX_PASSWORD" not in mac
    assert "-e " not in mac and '"env"' not in mac
    assert "Never put a password in the configuration" in guide
