"""
backend/tests/test_security.py

Regression tests for two account-takeover holes fixed after v0.7.0:
  1. /api/users routes had no auth: anyone could change the password.
  2. The session cookie was signed with a key published in the repo
     ("default_secret_key") whenever SECRET_KEY wasn't set (Docker/StartOS),
     so anyone could forge a login cookie.
"""

import base64
import json
import os
import stat
import tempfile

import bcrypt
import pytest
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base, get_db
from backend.main import SECRET_KEY, app
from backend.models.user import User
from backend.secret_key import KEY_FILENAME, PUBLIC_DEFAULTS, load_secret_key
from backend.tests.conftest import LOGIN_CREDS, _seed_test_db


def anon() -> TestClient:
    return TestClient(app)


def can_login(password: str) -> bool:
    return anon().post("/api/login", json={"username": "admin", "password": password}).status_code == 200


class TestUserRoutesRequireAuth:
    def test_anonymous_cannot_list_users(self, auth_client):
        assert anon().get("/api/users/").status_code == 401

    def test_anonymous_cannot_change_password(self, auth_client):
        r = anon().patch("/api/users/1", json={"password": "hacked123"})
        assert r.status_code == 401
        assert not can_login("hacked123")
        assert can_login(LOGIN_CREDS["password"])

    def test_anonymous_cannot_delete_user(self, auth_client):
        assert anon().delete("/api/users/1").status_code == 401

    def test_cannot_change_another_user(self, auth_client):
        assert auth_client.patch("/api/users/999", json={"password": "x" * 12}).status_code == 403

    def test_logged_in_user_lists_users(self, auth_client):
        assert auth_client.get("/api/users/").status_code == 200

    def test_setup_status_is_public_and_minimal(self, auth_client):
        r = anon().get("/api/users/setup-status")
        assert r.status_code == 200
        assert set(r.json()) == {"has_user", "is_default"}


class TestResetAccount:
    """Runs on its own database: resetting changes the login."""

    @pytest.fixture
    def fresh_app(self, auth_client):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        engine = create_engine(f"sqlite:///{tmp.name}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        _seed_test_db(engine)  # admin / password, like a fresh install
        Session = sessionmaker(bind=engine)

        def override():
            db = Session()
            try:
                yield db
            finally:
                db.close()

        previous = app.dependency_overrides[get_db]
        app.dependency_overrides[get_db] = override
        yield Session
        app.dependency_overrides[get_db] = previous
        engine.dispose()
        os.unlink(tmp.name)

    def test_default_account_can_be_claimed(self, fresh_app):
        assert anon().get("/api/users/setup-status").json() == {"has_user": True, "is_default": True}
        r = anon().post("/api/users/reset-account", json={"username": "me", "password": "n3w-passw0rd"})
        assert r.status_code == 200, r.text
        assert anon().post("/api/login", json={"username": "me", "password": "n3w-passw0rd"}).status_code == 200
        assert anon().get("/api/users/setup-status").json()["is_default"] is False

    def test_non_default_account_needs_current_password(self, fresh_app):
        db = fresh_app()
        user = db.query(User).first()
        user.username = "me"
        user.password_hash = bcrypt.hashpw(b"real-password", bcrypt.gensalt()).decode()
        db.commit()
        db.close()

        payload = {"username": "attacker", "password": "whatever1"}
        assert anon().post("/api/users/reset-account", json=payload).status_code == 403
        wrong = dict(payload, current_password="guess")
        assert anon().post("/api/users/reset-account", json=wrong).status_code == 403
        right = dict(payload, current_password="real-password")
        assert anon().post("/api/users/reset-account", json=right).status_code == 200

    def test_admin_username_rejected(self, fresh_app):
        r = anon().post("/api/users/reset-account", json={"username": "admin", "password": "n3w-passw0rd"})
        assert r.status_code == 400


class TestSessionSecret:
    def test_app_key_is_not_a_published_default(self):
        assert SECRET_KEY not in PUBLIC_DEFAULTS
        assert len(SECRET_KEY) >= 32

    @pytest.mark.parametrize("published", sorted(PUBLIC_DEFAULTS - {""}))
    def test_cookie_forged_with_published_key_is_rejected(self, auth_client, published):
        data = base64.b64encode(json.dumps({"user_id": 1}).encode())
        cookie = TimestampSigner(published).sign(data).decode()
        forged = TestClient(app, cookies={"btc_session_id": cookie})
        assert forged.get("/api/transactions").status_code == 401

    def test_generated_key_is_persistent_and_private(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SECRET_KEY", "default_secret_key")  # public value => ignored
        first = load_secret_key(str(tmp_path))
        assert first not in PUBLIC_DEFAULTS and len(first) >= 32
        assert load_secret_key(str(tmp_path)) == first  # survives restarts
        mode = stat.S_IMODE(os.stat(tmp_path / KEY_FILENAME).st_mode)
        assert mode == 0o600

    def test_explicit_env_key_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SECRET_KEY", "an-operator-supplied-secret-value-1234567890")
        assert load_secret_key(str(tmp_path)) == "an-operator-supplied-secret-value-1234567890"
        assert not (tmp_path / KEY_FILENAME).exists()
