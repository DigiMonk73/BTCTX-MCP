"""
Restoring a backup file inside the app keeps the login in use, as it keeps
the AI key (owner decision 2026-09-28, after Grok Bot's StartOS test): the
restored database brought back the backup's username and password, so on
StartOS the password Show Credentials displays stopped working.
"""

from sqlalchemy import text

from backend.models.user import User
from backend.tests.conftest import default_login


def test_restoring_an_old_backup_keeps_the_login_in_use(auth_client, test_engine, monkeypatch):
    from backend.routers import backup

    old = User(username="old-owner", password_hash="")
    old.set_password("old-password-123")

    def restore_old_backup(password, path):  # the backup's database: another login
        with test_engine.begin() as conn:
            conn.execute(text("UPDATE users SET username = :u, password_hash = :h"),
                         {"u": old.username, "h": old.password_hash})

    monkeypatch.setattr(backup, "restore_backup", restore_old_backup)
    r = auth_client.post("/api/backup/restore", data={"password": "pw"}, files={"file": ("b.btx", b"x")})
    assert r.status_code == 200, r.text

    with test_engine.connect() as conn:
        assert conn.execute(text("SELECT username FROM users")).scalar() == default_login()["username"]
    assert auth_client.post("/api/login", json={"username": "old-owner", "password": "old-password-123"}).status_code != 200
    assert auth_client.post("/api/login", json=default_login()).status_code == 200
    assert "current username and password" in r.json()["message"]
