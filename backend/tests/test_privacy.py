"""
Privacy and browser-security headers (backend/security_headers.py) and the
fonts bundled with the frontend (no font CDN).
"""

from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app
from backend.security_headers import CSP

REPO = Path(__file__).resolve().parents[2]


def test_every_response_says_no_referrer_nosniff_no_framing(auth_client):
    for path in ("/api/health", "/api/transactions"):
        r = auth_client.get(path)
        assert r.headers["referrer-policy"] == "no-referrer"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["content-security-policy"] == CSP
    assert "default-src 'self'" in CSP and "frame-ancestors 'none'" in CSP


def test_no_csp_in_the_mac_app(auth_client, monkeypatch):
    monkeypatch.setenv("BTCTX_DESKTOP", "1")
    r = auth_client.get("/api/health")
    assert "content-security-policy" not in r.headers
    assert r.headers["referrer-policy"] == "no-referrer"


def _login_cookie(headers: dict) -> str:
    client = TestClient(app)
    r = client.post("/api/login", json={"username": "admin", "password": "password"}, headers=headers)
    assert r.status_code == 200, r.text
    return r.headers["set-cookie"]


def test_session_cookie_is_secure_over_https_only(auth_client):
    over_https = _login_cookie({"X-Forwarded-Proto": "https"})
    assert "btc_session_id=" in over_https and "; Secure" in over_https
    assert "samesite=lax" in over_https.lower()
    over_http = _login_cookie({})
    assert "secure" not in over_http.lower()


def test_fonts_are_bundled_not_fetched_from_google():
    index = (REPO / "frontend" / "index.html").read_text()
    assert "fonts.googleapis.com" not in index and "fonts.gstatic.com" not in index
    main = (REPO / "frontend" / "src" / "main.tsx").read_text()
    assert '@fontsource/inter/latin-400.css' in main and '@fontsource/outfit/latin-600.css' in main


# ---------------------------------------------------------------------------
# At rest: backups and the database file
# ---------------------------------------------------------------------------
import os  # noqa: E402
import sqlite3  # noqa: E402
import stat  # noqa: E402
import struct  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

from backend.database import init_db  # noqa: E402
from backend.services import backup  # noqa: E402


def _db(path):
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE t (x)")
    con.execute("INSERT INTO t VALUES ('ledger')")
    con.commit()
    con.close()
    return path


def _legacy_v1_backup(db_bytes: bytes, password: str) -> bytes:
    """How BitcoinTX up to 0.9.1 wrote a backup."""
    salt, iv = os.urandom(16), os.urandom(16)
    key = backup._derive_key(password, salt, 100_000)
    return salt + iv + backup._encrypt_data(db_bytes, key, iv)


def test_new_backups_use_600k_iterations_and_are_owner_only(tmp_path):
    out = tmp_path / "b.btx"
    backup.make_backup("pw", out, db_path=_db(tmp_path / "live.db"))
    blob = out.read_bytes()
    assert blob.startswith(b"BTCTX-BACKUP") and blob[len(b"BTCTX-BACKUP")] == 2
    assert struct.unpack(">I", blob[13:17])[0] == 600_000
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o600
    assert backup.decrypt_backup(blob, "pw").startswith(backup.SQLITE_HEADER)


def test_wrong_password_and_tampering_are_caught(tmp_path):
    out = tmp_path / "b.btx"
    backup.make_backup("pw", out, db_path=_db(tmp_path / "live.db"))
    blob = out.read_bytes()
    with pytest.raises(ValueError, match="Wrong password"):
        backup.decrypt_backup(blob, "not-it")
    tampered = blob[:40] + bytes([blob[40] ^ 1]) + blob[41:]
    with pytest.raises(ValueError, match="Wrong password"):
        backup.decrypt_backup(tampered, "pw")


def test_backups_made_before_0_9_2_still_restore(tmp_path):
    live = _db(tmp_path / "live.db")
    v1 = _legacy_v1_backup(live.read_bytes(), "old-pw")
    assert backup.decrypt_backup(v1, "old-pw") == live.read_bytes()
    with pytest.raises(ValueError, match="Wrong password"):
        backup.decrypt_backup(v1, "nope")


def test_the_database_file_is_owner_only(tmp_path):
    path = tmp_path / "btctx.db"
    engine = create_engine(f"sqlite:///{path}")
    init_db(engine)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    engine.dispose()
