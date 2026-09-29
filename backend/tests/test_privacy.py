"""
Privacy and browser-security headers (backend/security_headers.py) and the
fonts bundled with the frontend (no font CDN).
"""

from backend.tests.conftest import default_login
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
    r = client.post("/api/login", json=default_login(), headers=headers)
    assert r.status_code == 200, r.text
    return r.headers["set-cookie"]


def test_session_cookie_is_secure_over_https_only(auth_client):
    over_https = _login_cookie({"X-Forwarded-Proto": "https"})
    assert "btc_session_id=" in over_https and "; Secure" in over_https
    assert "samesite=lax" in over_https.lower()
    over_http = _login_cookie({})
    assert "secure" not in over_http.lower()


def test_no_access_log_on_any_edition():
    """uvicorn's access log records client addresses and request paths,
    which carry transaction dates (?date=...). The Mac app had it off."""
    assert '"--no-access-log"' in (REPO / "Dockerfile").read_text()
    assert "'--no-access-log'" in (REPO / "startos" / "startos" / "main.ts").read_text()
    assert "access_log=False" in (REPO / "desktop" / "entrypoint.py").read_text()


def test_transaction_dates_stay_out_of_the_info_log(auth_client, caplog):
    """Creating a backdated entry and editing one logged their timestamps at INFO."""
    auth_client.delete("/api/transactions/delete_all")
    tx = lambda ts, amount: auth_client.post("/api/transactions", json={  # noqa: E731
        "type": "Deposit", "timestamp": ts, "from_account_id": 99, "to_account_id": 1,
        "amount": amount, "fee_amount": "0", "fee_currency": "USD", "source": "N/A"})
    with caplog.at_level("INFO", logger="backend"):
        later = tx("2023-05-17T10:11:12Z", "1000").json()
        tx("2021-02-03T04:05:06Z", "2000")  # backdated: recalculates everything
        r = auth_client.put(f"/api/transactions/{later['id']}", json={"timestamp": "2022-08-09T01:02:03Z"})
        assert r.status_code == 200, r.text
    auth_client.delete("/api/transactions/delete_all")
    info = "\n".join(rec.getMessage() for rec in caplog.records if rec.levelname != "DEBUG")
    for day in ("2023-05-17", "2021-02-03", "2022-08-09"):
        assert day not in info


def test_reports_log_no_counts_of_the_ledger_at_info(auth_client, caplog):
    """Privacy audit 2026-09-29 (3a): making reports logged how many
    transactions, disposals and lots each year had, at INFO."""
    auth_client.delete("/api/transactions/delete_all")
    for body in (
        dict(type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=99, to_account_id=1,
             amount="50000", fee_amount="0", fee_currency="USD", source="N/A"),
        dict(type="Buy", timestamp="2024-01-03T12:00:00Z", from_account_id=1, to_account_id=4,
             amount="1", cost_basis_usd="40000", fee_amount="0", fee_currency="USD"),
        dict(type="Sell", timestamp="2024-06-03T12:00:00Z", from_account_id=4, to_account_id=3,
             amount="0.5", gross_proceeds_usd="30000", fee_amount="0", fee_currency="USD"),
    ):
        assert auth_client.post("/api/transactions", json=body).status_code == 200
    with caplog.at_level("INFO", logger="backend"):
        for path, params in (("irs_reports", {}), ("complete_tax_report", {}),
                             ("simple_transaction_history", {"format": "csv"}),
                             ("simple_transaction_history", {"format": "pdf"})):
            r = auth_client.get(f"/api/reports/{path}", params={"year": 2024, **params})
            assert r.status_code == 200, (path, r.text)
    auth_client.delete("/api/transactions/delete_all")
    info = [rec.getMessage() for rec in caplog.records if rec.levelno >= 20]
    counted = [m for m in info if any(w in m for w in ("transactions for", "rows", "disposals", "lots"))]
    assert counted == []


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


def test_a_v1_wrong_password_that_happens_to_unpad_is_still_caught():
    """v1 has no MAC: a wrong key unpads cleanly about 1 time in 256 and
    used to come back as garbage (the test above failed at random). Here the
    unpadding succeeds for sure: the file holds no database."""
    salt, iv = b"s" * backup.SALT_LENGTH, b"i" * backup.IV_LENGTH
    key = backup._derive_key("pw", salt, backup.LEGACY_ITERATIONS)
    v1 = salt + iv + backup._encrypt_data(b"not a database" * 8, key, iv)
    with pytest.raises(ValueError, match="Wrong password"):
        backup.decrypt_backup(v1, "pw")


@pytest.mark.parametrize("iterations", [0, 1_000, 99_999, 5_000_001, 2**32 - 1])
def test_a_backup_asking_for_an_absurd_key_strength_is_refused_at_once(iterations, monkeypatch):
    """The PBKDF2 count comes from the file: 4 billion rounds would tie up
    the server for hours before the password could even be checked."""
    def no_derivation(*a, **k):
        raise AssertionError("key derivation must not start")

    monkeypatch.setattr(backup, "_derive_key", no_derivation)
    blob = b"BTCTX-BACKUP" + bytes([2]) + struct.pack(">I", iterations) + os.urandom(16 + 16 + 64 + 32)
    with pytest.raises(ValueError, match="damaged or wasn't made by BitcoinTX"):
        backup.decrypt_backup(blob, "pw")


def test_a_backup_in_the_allowed_range_still_restores(tmp_path):
    live = _db(tmp_path / "live.db").read_bytes()
    for iterations in (backup.MIN_ITERATIONS, 600_000):
        assert backup.decrypt_backup(backup.encrypt_backup(live, "pw", iterations), "pw") == live


def test_restore_refuses_a_file_over_the_size_limit(auth_client, monkeypatch):
    from backend.routers import backup as backup_router

    monkeypatch.setattr(backup_router, "MAX_RESTORE_BYTES", 4096)
    big = b"BTCTX-BACKUP" + os.urandom(5000)
    r = auth_client.post("/api/backup/restore", data={"password": "pw"}, files={"file": ("b.btx", big)})
    assert r.status_code == 413 and "too large" in r.json()["detail"]


def test_restore_copies_the_upload_in_chunks_up_to_the_limit(monkeypatch):
    """Never one read of the whole upload; stops as soon as the limit is passed."""
    import io

    from fastapi import HTTPException

    from backend.routers.backup import _copy_at_most

    reads = []

    class Src(io.BytesIO):
        def read(self, n=-1):
            assert 0 < n <= 1024 * 1024
            reads.append(n)
            return super().read(n)

    out = io.BytesIO()
    _copy_at_most(Src(b"x" * 3_000_000), out, 3_000_000)
    assert out.getvalue() == b"x" * 3_000_000
    reads.clear()
    with pytest.raises(HTTPException) as exc:
        _copy_at_most(Src(b"x" * (5 * 1024 * 1024)), io.BytesIO(), 2 * 1024 * 1024)
    assert exc.value.status_code == 413 and len(reads) == 3


def test_the_database_file_is_owner_only(tmp_path):
    path = tmp_path / "btctx.db"
    engine = create_engine(f"sqlite:///{path}")
    init_db(engine)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    engine.dispose()


def test_a_backup_leaves_no_plain_copy_outside_the_data_folder(tmp_path, monkeypatch):
    """Privacy audit 2026-09-29 (3c): the consistent snapshot was written in
    plain to the system's temp folder (another filesystem on Docker or
    StartOS) before being encrypted."""
    data = tmp_path / "data"
    data.mkdir()
    live = _db(data / "btctx.db")
    opened = []
    real_connect = sqlite3.connect
    monkeypatch.setattr(backup.sqlite3, "connect", lambda p, *a, **k: opened.append(str(p)) or real_connect(p, *a, **k))
    backup.make_backup("pw", tmp_path / "out.btx", db_path=live)
    assert opened and all(p == ":memory:" or p.startswith(str(data)) for p in opened), opened
    assert sorted(f.name for f in data.iterdir()) == ["btctx.db"]


def test_a_restore_never_writes_the_decrypted_ledger_readable_by_others(tmp_path, monkeypatch):
    """Privacy audit 2026-09-29 (3c): the staging file was written with the
    default permissions, then made owner-only."""
    live = _db(tmp_path / "btctx.db")
    blob = tmp_path / "b.btx"
    backup.make_backup("pw", blob, db_path=live)
    modes = []
    real_write = Path.write_bytes

    def spy(self, data):
        n = real_write(self, data)
        if self.name.endswith(".restoring"):
            modes.append(stat.S_IMODE(os.stat(self).st_mode))
        return n

    monkeypatch.setattr(Path, "write_bytes", spy)
    old = os.umask(0o022)
    try:
        engine = create_engine(f"sqlite:///{live}")
        with pytest.raises(Exception):  # the toy database isn't a BitcoinTX schema; staging is what matters
            backup.restore_backup("pw", blob, db_path=live, engine=engine)
    finally:
        os.umask(old)
    assert all(m == 0o600 for m in modes), [oct(m) for m in modes]
