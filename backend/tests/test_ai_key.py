"""
backend/tests/test_ai_key.py

The AI key on Docker/StartOS (backend/services/ai_key.py): created, replaced
and revoked in Settings, only a hash stored, off until the owner turns AI
access on, and usable only on the routes the MCP tools need (AI_KEY_ROUTES).
Everything else answers 403 (or 401 where a route is login-only by itself).
The Mac app's key file is tested in mcp_server/tests/test_key_file.py.
"""

import hashlib
import json
import os
import re
import sqlite3
import stat
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.tests.conftest import default_login
from backend.main import app
from backend.migrate import backup_copies, backup_sqlite
from backend.services import ai_key

REPO = Path(__file__).resolve().parents[2]


def key_only():
    """A client with no session: only what the key allows."""
    return TestClient(app)


def stored_settings(test_engine) -> dict:
    with test_engine.connect() as conn:
        return dict(conn.execute(text("SELECT key, value FROM app_settings")).fetchall())


# ---------------------------------------------------------------------------
# Creating, replacing, revoking, the switch
# ---------------------------------------------------------------------------
def test_off_and_no_key_until_the_owner_acts(auth_client):
    state = auth_client.get("/api/settings/ai-access").json()
    assert state == {"mode": "server", "on": False, "has_key": False, "key_file": None}


def test_created_key_works_and_only_its_hash_is_kept(auth_client, ai_key_headers, test_engine):
    key = ai_key_headers["Authorization"].split(" ", 1)[1]
    assert key.startswith("btctx_ak_") and len(key) >= 50
    assert key_only().get("/api/transactions", headers=ai_key_headers).status_code == 200
    settings = stored_settings(test_engine)
    assert settings[ai_key.HASH_KEY] == hashlib.sha256(key.encode()).hexdigest()
    assert not any(key in (v or "") for v in settings.values())
    state = auth_client.get("/api/settings/ai-access").json()
    assert state["has_key"] is True and "key" not in state  # shown once, at creation only


def test_new_key_replaces_the_old_one(auth_client, ai_key_headers):
    new = auth_client.post("/api/settings/ai-key").json()["key"]
    r = key_only().get("/api/transactions", headers=ai_key_headers)
    assert r.status_code == 401 and "replaced or revoked" in r.json()["detail"]
    assert key_only().get("/api/transactions", headers={"Authorization": f"Bearer {new}"}).status_code == 200


def test_revoke_and_the_switch(auth_client, ai_key_headers):
    auth_client.put("/api/settings/ai-access", json={"on": False})
    r = key_only().get("/api/transactions", headers=ai_key_headers)
    assert r.status_code == 401 and r.json()["detail"] == "AI access is turned off in BitcoinTX Settings."
    auth_client.put("/api/settings/ai-access", json={"on": True})
    assert key_only().get("/api/transactions", headers=ai_key_headers).status_code == 200

    assert auth_client.delete("/api/settings/ai-key").json()["has_key"] is False
    assert key_only().get("/api/transactions", headers=ai_key_headers).status_code == 401


def test_the_key_file_routes_are_mac_only(auth_client):
    r = auth_client.post("/api/settings/ai-access/reset-key")
    assert r.status_code == 400


def test_a_key_is_no_login(auth_client, ai_key_headers):
    """Sending the key to /api/login gets no session: login takes the password only."""
    client = key_only()
    assert client.post("/api/login", headers=ai_key_headers).status_code == 422
    r = client.post("/api/login", json={"username": "admin", "password": "wrong"}, headers=ai_key_headers)
    assert r.status_code == 401
    assert client.get("/api/users/").status_code == 401


# ---------------------------------------------------------------------------
# What the key can't do
# ---------------------------------------------------------------------------
CSV = {"file": ("t.csv", b"date,type,amount\n", "text/csv")}
REFUSED = [
    # (what, method, path, request kwargs, status)
    ("key: create", "POST", "/api/settings/ai-key", {}, 403),
    ("key: revoke", "DELETE", "/api/settings/ai-key", {}, 403),
    ("key: reset (Mac)", "POST", "/api/settings/ai-access/reset-key", {}, 403),
    ("AI switch: read", "GET", "/api/settings/ai-access", {}, 403),
    ("AI switch: change", "PUT", "/api/settings/ai-access", {"json": {"on": True}}, 403),
    ("restore", "POST", "/api/backup/restore", {"data": {"password": "x"}, "files": {"file": ("b.btx", b"x")}}, 403),
    ("backup download (.btx)", "POST", "/api/backup/download", {"data": {"password": "x"}}, 403),
    ("CSV export", "GET", "/api/backup/csv", {}, 403),
    ("CSV import preview", "POST", "/api/import/preview", {"files": CSV}, 403),
    ("CSV import", "POST", "/api/import/execute", {"files": CSV}, 403),
    ("River import preview", "POST", "/api/import/river/preview", {"files": CSV}, 403),
    ("River import", "POST", "/api/import/river/execute", {"files": CSV}, 403),
    ("delete everything", "DELETE", "/api/transactions/delete_all", {}, 403),
    ("new transaction outside the import", "POST", "/api/transactions", {"json": {}}, 403),
    ("account: create", "POST", "/api/accounts/", {"json": {"name": "x", "currency": "BTC"}}, 403),
    ("account: change", "PUT", "/api/accounts/2", {"json": {"name": "x"}}, 403),
    ("account: delete", "DELETE", "/api/accounts/2", {}, 403),
    ("Ledger review fix", "POST", "/api/review/fee-prices", {"json": {"ids": [1]}}, 403),
    ("tax timezone", "PUT", "/api/settings/tax-timezone", {"json": {"timezone": "Asia/Tokyo"}}, 403),
    ("privacy & network", "PUT", "/api/settings/network", {"json": {"price_source": "off"}}, 403),
    ("reports", "GET", "/api/reports/years", {}, 403),
    ("debug", "GET", "/api/debug/lots", {}, 401),
    ("users: list", "GET", "/api/users/", {}, 401),
    ("users: change username or password", "PATCH", "/api/users/1", {"json": {"password": "newpassword1"}}, 401),
    ("users: delete", "DELETE", "/api/users/1", {}, 401),
]


@pytest.mark.parametrize("what, method, path, kwargs, status", REFUSED, ids=[r[0] for r in REFUSED])
def test_refused_with_the_key(auth_client, ai_key_headers, what, method, path, kwargs, status):
    r = key_only().request(method, path, headers=ai_key_headers, **kwargs)
    assert r.status_code == status, (what, r.status_code, r.text)
    if status == 403:
        assert r.json()["detail"] == ai_key.NOT_ALLOWED


def test_refusals_changed_nothing(auth_client, ai_key_headers):
    for _, method, path, kwargs, _ in REFUSED:
        key_only().request(method, path, headers=ai_key_headers, **kwargs)
    assert auth_client.get("/api/settings/tax-timezone").json()["timezone"] != "Asia/Tokyo"
    assert auth_client.get("/api/settings/network").json()["price_source"] == "public"
    assert auth_client.post("/api/login", json=default_login()).status_code == 200


# ---------------------------------------------------------------------------
# The allow-list
# ---------------------------------------------------------------------------
def test_ids_are_digits_only():
    assert ai_key.key_may_use("DELETE", "/api/transactions/12")
    assert ai_key.key_may_use("GET", "/api/transactions/")
    assert not ai_key.key_may_use("DELETE", "/api/transactions/delete_all")
    assert not ai_key.key_may_use("POST", "/api/transactions/12")
    assert not ai_key.key_may_use("GET", "/api/transactions/12/extra")


def _shape(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path.rstrip("/"))


def test_every_listed_route_exists():
    """A renamed route must be renamed in AI_KEY_ROUTES too."""
    app_routes = {(m.upper(), _shape(p)) for p, ops in app.openapi()["paths"].items() for m in ops}
    for method, path, _ in ai_key.AI_KEY_ROUTES:
        assert (method, _shape(path)) in app_routes, (method, path)


def test_every_route_the_mcp_tools_call_is_allowed():
    """The connector's calls (mcp_server/btctx_mcp/server.py) and the list agree."""
    source = (REPO / "mcp_server" / "btctx_mcp" / "server.py").read_text()
    calls = re.findall(r'_call\(\s*"([A-Z]+)",\s*f?"(/api/[^"]+)"', source)
    assert len(calls) >= 12
    for method, path in calls:
        path = re.sub(r"\{[^}]+\}", "7", path)
        assert ai_key.key_may_use(method, path), (method, path)


# ---------------------------------------------------------------------------
# Backups the key may ask for
# ---------------------------------------------------------------------------
def test_backup_copy_with_the_key(auth_client, ai_key_headers, test_engine):
    r = key_only().post("/api/backup/ai-copy", headers=ai_key_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    copy = Path(test_engine.url.database).parent / "backups" / body["file"]
    try:
        assert copy.exists() and set(body) == {"file", "created", "kept"}
        assert stat.S_IMODE(os.stat(copy).st_mode) == 0o600
        assert body["file"].startswith(Path(test_engine.url.database).stem + "-ai-")
        again = key_only().post("/api/backup/ai-copy", headers=ai_key_headers)
        assert again.status_code == 429 and "less than a minute" in again.json()["detail"]
    finally:
        copy.unlink(missing_ok=True)


@pytest.fixture
def db_file(tmp_path):
    path = tmp_path / "btctx.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (x)")
    conn.commit()
    conn.close()
    engine = create_engine(f"sqlite:///{path}")
    session = sessionmaker(bind=engine)()
    yield path, session
    session.close()
    engine.dispose()


def test_ai_copies_keep_three_and_never_evict_pre_upgrade_copies(db_file, monkeypatch):
    from backend.routers import backup

    path, session = db_file
    upgrade = [backup_sqlite(path, "upgrade") for _ in range(2)]
    monkeypatch.setattr(backup, "AI_COPY_EVERY", 0)
    made = [backup.ai_copy(db=session)["file"] for _ in range(4)]
    kept = [p.name for p in backup_copies(path, "ai")]
    assert len(kept) == 3 and made[0] not in kept and set(made[1:]) == set(kept)
    assert all(p.exists() for p in upgrade)
    assert json.dumps(made).count("-ai-backup-") == 4


def test_one_ai_copy_a_minute(db_file):
    from backend.routers import backup

    path, session = db_file
    backup.ai_copy(db=session)
    with pytest.raises(HTTPException) as e:
        backup.ai_copy(db=session)
    assert e.value.status_code == 429
    assert len(backup_copies(path, "ai")) == 1


# ---------------------------------------------------------------------------
# Restore keeps the key and switch in use
# ---------------------------------------------------------------------------
def test_restoring_an_old_backup_does_not_bring_back_a_revoked_key(
    auth_client, ai_key_headers, test_engine, monkeypatch
):
    from backend.routers import backup

    leaked_hash = stored_settings(test_engine)[ai_key.HASH_KEY]
    auth_client.delete("/api/settings/ai-key")  # the key leaked: revoked, access off
    auth_client.put("/api/settings/ai-access", json={"on": False})

    def restore_old_backup(password, path):  # a backup from before: old key, access on
        with test_engine.begin() as conn:
            conn.execute(
                text("INSERT OR REPLACE INTO app_settings (key, value) VALUES (:k, :v)"),
                [{"k": ai_key.HASH_KEY, "v": leaked_hash}, {"k": ai_key.ACCESS_KEY, "v": "on"}],
            )

    monkeypatch.setattr(backup, "restore_backup", restore_old_backup)
    r = auth_client.post("/api/backup/restore", data={"password": "pw"}, files={"file": ("b.btx", b"x")})
    assert r.status_code == 200, r.text
    settings = stored_settings(test_engine)
    assert ai_key.HASH_KEY not in settings and settings[ai_key.ACCESS_KEY] == "off"
    assert key_only().get("/api/transactions", headers=ai_key_headers).status_code == 401
    # The restore ended the session; log back in for the fixture's clean-up.
    assert auth_client.post("/api/login", json=default_login()).status_code == 200


# ---------------------------------------------------------------------------
# StartOS: the Connect an AI Assistant action hands out no password
# ---------------------------------------------------------------------------
def test_startos_action_reads_and_shows_no_login():
    """connectAi.ts once read the generated password from store.json and put it
    into the AI app's configuration. Its messages may name the old variables
    (to tell upgraders to remove them); its code and config may not."""
    action = (REPO / "startos" / "startos" / "actions" / "connectAi.ts").read_text()
    for name in ("storeJson", "adminPassword", "ADMIN_USERNAME", "BTCTX_PASSWORD:", "BTCTX_USERNAME:"):
        assert name not in action, name
    assert "BTCTX_AI_KEY: KEY_PLACEHOLDER" in action
