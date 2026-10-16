"""
The Mac app's AI key file (backend/services/ai_key.py, mode "mac") and the
MCP client's use of it (btctx_mcp/client.py): no password in any MCP config.
The Docker/StartOS key is tested in backend/tests/test_ai_key.py.
"""

import json
import os
import stat
import sys

import httpx
import pytest
from mcp import Client
from sqlalchemy.orm import sessionmaker

from backend import main as backend_main
from backend.database import get_db
from backend.main import app
from backend.services import ai_key, first_run
from btctx_mcp import server
from btctx_mcp.client import BtctxClient, BtctxError, _pid_alive
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
    monkeypatch.setenv("BTCTX_DESKTOP_URL", "http://127.0.0.1:8765")
    monkeypatch.setenv("BTCTX_MCP_FILE", str(key_file))
    with _db() as db:
        ai_key.sync(db)
        ai_key.set_access(db, True)  # the owner turned it on in Settings
    return key_file


@pytest.fixture
def restart(monkeypatch, backend_db):  # noqa: F811
    """BitcoinTX quits and starts again: its startup step for the key file."""
    monkeypatch.setattr(backend_main, "SessionLocal", sessionmaker(bind=backend_db))
    return backend_main._sync_ai_key_file


class _Recorder(httpx.AsyncBaseTransport):
    """The app on this computer, keeping each request's path and key and the answer's status."""

    def __init__(self):
        self._app = httpx.ASGITransport(app=app, client=("127.0.0.1", 50000))
        self.calls = []

    async def handle_async_request(self, request):
        response = await self._app.handle_async_request(request)
        self.calls.append((request.url.path, request.headers.get("authorization"), response.status_code))
        return response


def _pid_1_is_another_users():
    """pid 1 (launchd on a Mac, init on Linux) belongs to root, unless the
    tests run as root or in a container whose first process is theirs."""
    if sys.platform == "win32" or os.geteuid() == 0:
        return False
    return not os.path.exists("/proc/1") or os.stat("/proc/1").st_uid != os.geteuid()


class _db:
    def __enter__(self):
        self.gen = app.dependency_overrides[get_db]()
        return next(self.gen)

    def __exit__(self, *exc):
        self.gen.close()


def _token(key_file):
    return json.loads(key_file.read_text())["token"]


def _default_login() -> dict:
    """admin/password with the setup code, which the Mac app asks for too
    (backend/services/first_run.py)."""
    return {"username": "admin", "password": "password", "setup_code": first_run.ensure_code()}


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
        assert ai_key._get(db, ai_key.HASH_KEY) == ai_key._hash(data["token"])
        assert data["token"] not in json.dumps([ai_key._get(db, k) for k in (ai_key.HASH_KEY,)])


async def test_access_is_off_until_the_owner_turns_it_on(monkeypatch, tmp_path, backend_db):  # noqa: F811
    key_file = tmp_path / "BitcoinTX" / "mcp.json"
    monkeypatch.setenv("BTCTX_DESKTOP", "1")
    monkeypatch.setenv("BTCTX_DESKTOP_URL", "http://127.0.0.1:8765")
    monkeypatch.setenv("BTCTX_MCP_FILE", str(key_file))
    with _db() as db:
        ai_key.sync(db)
    token = {"Authorization": f"Bearer {_token(key_file)}"}
    async with _http() as h:
        r = await h.get("/api/transactions", headers=token)
        assert r.status_code == 401 and "turned off" in r.json()["detail"]
        assert (await h.post("/api/login", json=_default_login())).status_code == 200
        assert (await h.get("/api/settings/ai-access")).json()["on"] is False
        assert (await h.put("/api/settings/ai-access", json={"on": True})).json()["on"] is True
        h.cookies.clear()
        assert (await h.get("/api/transactions", headers=token)).status_code == 200


async def test_two_starts_give_different_keys(desktop, restart):
    first = _token(desktop)
    restart()
    second = _token(desktop)
    assert second != first and len(second) >= 43
    assert stat.S_IMODE(os.stat(desktop).st_mode) == 0o600
    with _db() as db:  # only the new key's hash is stored; the switch stays on
        assert ai_key._get(db, ai_key.HASH_KEY) == ai_key._hash(second)
        assert ai_key.access_on(db)


async def test_a_key_from_a_previous_start_is_refused(desktop, restart):
    old = _token(desktop)
    restart()
    async with _http() as h:
        r = await h.get("/api/transactions", headers={"Authorization": f"Bearer {old}"})
        assert r.status_code == 401 and "replaced or revoked" in r.json()["detail"]
        new = {"Authorization": f"Bearer {_token(desktop)}"}
        assert (await h.get("/api/transactions", headers=new)).status_code == 200


async def test_an_ai_session_carries_on_across_a_restart(desktop, restart):
    """The AI app stays open while BitcoinTX quits and starts again. Its next
    call is refused with the old key; the connector rereads the key file and
    sends the call again with the new key. The owner does nothing."""
    old = _token(desktop)
    seen = _Recorder()
    btctx = BtctxClient(key_file=desktop, transport=seen)
    try:
        assert await btctx.get("/api/transactions") == []
        restart()
        seen.calls.clear()
        assert await btctx.get("/api/transactions") == []
        keys = [(key, status) for path, key, status in seen.calls if path == "/api/transactions"]
        assert keys == [(f"Bearer {old}", 401), (f"Bearer {_token(desktop)}", 200)]
        # Finding the app again sends no key, not even the one just refused
        assert [key for path, key, _ in seen.calls if path == "/api/health"] == [None]
    finally:
        await btctx.aclose()


async def test_a_restore_leaves_the_key_file_alone(desktop):
    """After a restore the key the connector holds is still this install's:
    refreshing after it must not write a new one (ai_key.sync does)."""
    from backend.routers import backup as backup_router

    before = desktop.read_text()
    with _db() as db:
        backup_router._refresh_after_restore(db)
    assert desktop.read_text() == before


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
            ai_key.rotate(db)
        assert _token(desktop) != old
        # The MCP server re-reads the file and carries on...
        assert await btctx.get("/api/transactions") == []
        # ...a copy of the old key doesn't.
        async with _http() as h:
            r = await h.get("/api/transactions", headers={"Authorization": f"Bearer {old}"})
            assert r.status_code == 401 and "replaced or revoked" in r.json()["detail"]
    finally:
        await btctx.aclose()


def _boom(*args, **kwargs):
    raise OSError("disk full")


def _failing(m, step):
    """The key file's write fails at `step`: before the hash is committed, or after."""
    m.setattr(ai_key.tempfile if step == "mkstemp" else ai_key.os, step, _boom)


@pytest.mark.parametrize("step", ["mkstemp", "replace"])
async def test_a_start_whose_key_file_cant_be_written_has_no_key(desktop, restart, monkeypatch, step):
    """The file left is the earlier run's (its pid gone, so the connector
    refuses it): this run has no key, and the earlier run's key doesn't
    work again. A reset in Settings makes one."""
    old = _token(desktop)
    with monkeypatch.context() as m:
        _failing(m, step)
        restart()  # logged; the app starts anyway
    assert _token(desktop) == old and not list(desktop.parent.glob(".mcp-*"))
    with _db() as db:
        assert ai_key._get(db, ai_key.HASH_KEY) is None
    async with _http() as h:
        assert (await h.get("/api/transactions", headers={"Authorization": f"Bearer {old}"})).status_code == 401
    with _db() as db:
        ai_key.rotate(db)
    assert _token(desktop) != old


@pytest.mark.parametrize("step", ["mkstemp", "replace", "commit"])
async def test_a_reset_whose_key_file_cant_be_written_keeps_the_key(desktop, monkeypatch, step):
    """The file and the hash stay the same pair, so the connector carries on."""
    old = _token(desktop)
    with _db() as db, monkeypatch.context() as m:
        if step == "commit":
            m.setattr(db, "commit", _boom)
        else:
            _failing(m, step)
        with pytest.raises(OSError):
            ai_key.rotate(db)
    assert _token(desktop) == old and not list(desktop.parent.glob(".mcp-*"))
    with _db() as db:
        assert ai_key._get(db, ai_key.HASH_KEY) == ai_key._hash(old)
    async with _http() as h:
        assert (await h.get("/api/transactions", headers={"Authorization": f"Bearer {old}"})).status_code == 200


async def test_key_refused_from_another_computer(desktop):
    async with _http("192.168.1.50") as h:
        r = await h.get("/api/transactions", headers={"Authorization": f"Bearer {_token(desktop)}"})
    assert r.status_code == 401 and "this computer" in r.json()["detail"]


async def test_access_switch_and_login_only_actions(desktop):
    token = {"Authorization": f"Bearer {_token(desktop)}"}
    async with _http() as h:
        # The key can't change its own access, reset itself or delete everything.
        assert (await h.put("/api/settings/ai-access", json={"on": True}, headers=token)).status_code == 403
        assert (await h.post("/api/settings/ai-access/reset-key", headers=token)).status_code == 403
        assert (await h.delete("/api/transactions/delete_all", headers=token)).status_code == 403
        # Backup download, restore and CSV export stay login-only.
        assert (await h.get("/api/backup/csv", headers=token)).status_code == 403
        assert (await h.post("/api/backup/download", data={"password": "x"}, headers=token)).status_code == 403
        restore = await h.post("/api/backup/restore", data={"password": "x"},
                               files={"file": ("b.btx", b"x")}, headers=token)
        assert restore.status_code == 403

        # The user turns access off (logged in): the key stops working.
        login = await h.post("/api/login", json=_default_login())
        assert login.status_code == 200
        r = await h.put("/api/settings/ai-access", json={"on": False})
        assert r.json() == {"mode": "mac", "on": False, "has_key": True, "key_file": str(desktop)}
        # New/Revoke are for Docker and StartOS; the Mac app resets its file.
        assert (await h.post("/api/settings/ai-key")).status_code == 400
        h.cookies.clear()
        r = await h.get("/api/transactions", headers=token)
        assert r.status_code == 401 and "turned off" in r.json()["detail"]


async def test_restored_database_keeps_the_key_the_mcp_has(desktop):
    token = _token(desktop)
    with _db() as db:
        before = ai_key.snapshot(db)
        ai_key._set(db, ai_key.HASH_KEY, "0" * 64)  # a restored backup carries another install's hash
        db.commit()
        ai_key.carry_over(db, before)
        db.commit()  # the restore commits what carry_over wrote, then checks it
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
    # The app may be open with no file at all, if its first start couldn't write it (#238)
    assert "or, if it's open, press Reset key in its Settings (Connect an AI Assistant)" in str(e.value)

    missing.write_text(json.dumps({"url": "http://127.0.0.1:8765", "pid": 999_999_999, "token": "x" * 43}))
    with pytest.raises(BtctxError, match="no longer running") as e:
        await btctx.get("/api/transactions")
    # The app may be open with no key of this run (its file couldn't be written): Reset key (#238)
    assert str(e.value).startswith("Cannot reach BitcoinTX. Open the BitcoinTX app and try again, or, if it's "
                                   "open, press Reset key in its Settings (Connect an AI Assistant). Looked at:")
    await btctx.aclose()


@pytest.mark.skipif(not _pid_1_is_another_users(), reason="needs pid 1 to be another user's process")
async def test_a_key_file_whose_pid_is_another_users_process_is_not_used(tmp_path):
    """Only this user's BitcoinTX counts: a pid that now belongs to another
    user's process (pid 1, owned by root) means the app isn't running, and the
    connector sends nothing."""
    assert _pid_alive(1) is False
    key_file = tmp_path / "mcp.json"
    key_file.write_text(json.dumps({"url": "http://127.0.0.1:8765", "pid": 1, "token": "x" * 43}))
    sent = []
    btctx = BtctxClient(
        key_file=key_file,
        transport=httpx.MockTransport(lambda request: sent.append(request) or httpx.Response(200, json=[])),
    )
    with pytest.raises(BtctxError, match="no longer running"):
        await btctx.get("/api/transactions")
    await btctx.aclose()
    assert sent == []


def test_setup_guide_puts_no_password_in_a_mac_config():
    from pathlib import Path

    guide = (Path(__file__).parents[1] / "AI_SETUP.md").read_text()
    mac = guide[guide.index("## 2A."):guide.index("## 2B.")]
    assert "YOUR_BITCOINTX_PASSWORD" not in mac
    assert "-e " not in mac and '"env"' not in mac
    assert "Never put a password in the configuration" in guide
