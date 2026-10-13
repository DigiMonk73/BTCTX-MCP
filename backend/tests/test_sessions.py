"""
backend/tests/test_sessions.py

Each login opens a session of its own (backend/session_auth.py): the cookie
carries a random id, and the server keeps the newest MAX_OPEN_SESSIONS of
them open. Logging out ends that session, so the cookie and any copy of it
stop working, while other browsers stay logged in. A password change, an
account reset or `cli set-password` (test_maintenance.py) ends every
session; a cookie made before sessions had an id counts as logged out.
"""

import base64
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import bcrypt
import pytest
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner
from sqlalchemy import text

from backend import session_auth
from backend.main import SECRET_KEY, app
from backend.models.user import User
from backend.tests.conftest import keep_in_use, default_login

LOGIN = {"username": "me", "password": "my-own-password-1"}
COOKIE = "btc_session_id"


@pytest.fixture
def own_login(fresh_app):
    """A fresh install whose login is LOGIN (no setup code; bcrypt's lowest
    cost keeps the many logins quick). Yields its sessionmaker."""
    db = fresh_app()
    user = db.query(User).first()
    user.username = LOGIN["username"]
    user.password_hash = bcrypt.hashpw(LOGIN["password"].encode(), bcrypt.gensalt(rounds=4)).decode()
    db.commit()
    db.close()
    return fresh_app


def logged_in(login: dict = LOGIN) -> TestClient:
    client = TestClient(app)
    r = client.post("/api/login", json=login)
    assert r.status_code == 200, r.text
    return client


def copy_of(client: TestClient) -> TestClient:
    """Another client sending the same session cookie."""
    return TestClient(app, cookies={COOKIE: client.cookies[COOKIE]})


def status(client: TestClient) -> int:
    return client.get("/api/transactions").status_code


def stored_sessions(sessionmaker) -> list:
    with sessionmaker() as db:
        raw = db.execute(text("SELECT value FROM app_settings WHERE key = :k"),
                         {"k": session_auth.OPEN_SESSIONS}).scalar()
    return json.loads(raw) if raw else []


def test_a_copy_of_the_cookie_stops_working_at_logout(own_login):
    me = logged_in()
    copy = copy_of(me)
    assert status(copy) == 200
    assert me.post("/api/logout").status_code == 200
    assert status(me) == 401
    assert status(copy) == 401
    assert copy.get("/api/protected").status_code == 401


def test_other_browsers_stay_logged_in_when_one_logs_out(own_login):
    laptop, phone = logged_in(), logged_in()
    copy = copy_of(laptop)
    assert laptop.post("/api/logout").status_code == 200
    assert status(copy) == 401
    assert status(phone) == 200
    assert len(stored_sessions(own_login)) == 1


def test_logging_in_again_replaces_this_browsers_session(own_login):
    me = logged_in()
    before = copy_of(me)
    assert me.post("/api/login", json=LOGIN).status_code == 200
    assert status(me) == 200
    assert status(before) == 401
    assert len(stored_sessions(own_login)) == 1


def test_a_password_change_ends_every_session(own_login):
    laptop, phone = logged_in(), logged_in()
    before = copy_of(laptop)
    r = laptop.patch("/api/users/1", json={"password": "a-new-password-2", "current_password": LOGIN["password"]})
    assert r.status_code == 200, r.text
    assert status(laptop) == 200  # the browser that changed it carries on, in a new session
    assert status(phone) == 401
    assert status(before) == 401
    assert len(stored_sessions(own_login)) == 1


def test_an_account_reset_ends_every_session(own_login):
    laptop = logged_in()
    r = TestClient(app).post("/api/users/reset-account", json={
        "username": "someone", "password": "a-new-password-2", "current_password": LOGIN["password"]})
    assert r.status_code == 200, r.text
    assert status(laptop) == 401
    assert stored_sessions(own_login) == []


def test_a_cookie_from_before_session_ids_is_logged_out(own_login):
    """Everyone logs in once after the update that brought session ids."""
    with own_login() as db:
        user = db.query(User).first()
        old_shape = {"user_id": user.id, session_auth.STAMP_KEY: session_auth.credential_stamp(user)}
    cookie = TimestampSigner(SECRET_KEY).sign(base64.b64encode(json.dumps(old_shape).encode())).decode()
    old = TestClient(app, cookies={COOKIE: cookie})
    assert status(old) == 401
    assert status(logged_in()) == 200


def test_only_the_newest_sessions_stay_open(own_login, monkeypatch):
    monkeypatch.setattr(session_auth, "MAX_OPEN_SESSIONS", 3)
    browsers = [logged_in() for _ in range(4)]
    assert [status(b) for b in browsers] == [401, 200, 200, 200]
    assert len(stored_sessions(own_login)) == 3


def test_users_protected_tells_a_logged_out_cookie_nothing(own_login):
    """The route read the session without checking it and nothing called
    it: it's gone."""
    me = logged_in()
    copy = copy_of(me)
    me.post("/api/logout")
    for client in (copy, me, TestClient(app)):
        r = client.get("/api/users/protected")
        assert r.status_code == 404, r.text
        assert LOGIN["username"] not in r.text


def test_the_ai_key_is_unaffected(auth_client, ai_key_headers):
    """The AI key has no session. A logged-out cookie sent along with it
    opens no login-only route; another browser's logout ends nothing else."""
    browser = logged_in(default_login())
    copy = copy_of(browser)
    assert browser.post("/api/logout").status_code == 200
    assert TestClient(app).get("/api/transactions", headers=ai_key_headers).status_code == 200
    assert copy.get("/api/transactions", headers=ai_key_headers).status_code == 200
    assert copy.get("/api/debug/lots", headers=ai_key_headers).status_code == 401
    assert status(auth_client) == 200


def test_many_logins_and_logouts_at_once_keep_the_list_whole(own_login):
    count = 16
    start = Barrier(count)

    def browser(i: int) -> TestClient:
        client = TestClient(app)
        start.wait()
        assert client.post("/api/login", json=LOGIN).status_code == 200
        copy = copy_of(client)
        if i % 2:
            assert client.post("/api/logout").status_code == 200
        return copy

    with ThreadPoolExecutor(max_workers=count) as pool:
        copies = [f.result() for f in [pool.submit(browser, i) for i in range(count)]]
    assert [status(c) for c in copies] == [401 if i % 2 else 200 for i in range(count)]
    assert len(stored_sessions(own_login)) == count // 2


def test_a_restore_keeps_the_sessions_open_before_it(auth_client, test_engine, monkeypatch):
    """The backup's list never comes back: a session logged out since it was
    made stays logged out; other browsers stay logged in; the browser that
    restored logs in again, as the message says."""
    from backend.routers import backup

    other, gone = logged_in(default_login()), logged_in(default_login())
    copy, own_copy = copy_of(gone), copy_of(auth_client)
    with test_engine.connect() as conn:
        in_backup = conn.execute(text("SELECT value FROM app_settings WHERE key = :k"),
                                 {"k": session_auth.OPEN_SESSIONS}).scalar()
    assert gone.post("/api/logout").status_code == 200

    def restore_old_backup(password, path, carry_over=None):  # the backup's database: gone was open then
        with test_engine.begin() as conn:
            conn.execute(text("INSERT OR REPLACE INTO app_settings (key, value) VALUES (:k, :v)"),
                         {"k": session_auth.OPEN_SESSIONS, "v": in_backup})
        keep_in_use(test_engine, carry_over)

    monkeypatch.setattr(backup, "restore_backup", restore_old_backup)
    r = auth_client.post("/api/backup/restore", data={"password": "pw"}, files={"file": ("b.btx", b"x")})
    assert r.status_code == 200, r.text
    assert status(copy) == 401
    assert status(other) == 200
    assert status(auth_client) == 401
    assert status(own_copy) == 401  # the restoring browser's session ended, every copy too
    assert auth_client.post("/api/login", json=default_login()).status_code == 200
    other.post("/api/logout")


def test_logout_works_in_the_browser_even_when_the_database_is_busy(monkeypatch):
    """#221's review: logout answered 500 and the button did nothing."""
    from sqlalchemy.exc import OperationalError

    browser = logged_in(default_login())

    def busy(db, change):
        raise OperationalError("UPDATE app_settings", {}, Exception("database is locked"))

    monkeypatch.setattr(session_auth, "_change_open_sessions", busy)
    assert browser.post("/api/logout").status_code == 200
    assert status(browser) == 401  # this browser is logged out


def test_a_login_during_a_long_write_answers_busy_not_a_server_error(monkeypatch):
    """#221's re-check: login writes the open sessions, so a write held
    elsewhere past the busy timeout gave a 500."""
    from sqlalchemy.exc import OperationalError

    def busy(db, change):
        raise OperationalError("UPDATE app_settings", {}, Exception("database is locked"))

    monkeypatch.setattr(session_auth, "_change_open_sessions", busy)
    r = TestClient(app).post("/api/login", json=default_login())
    assert r.status_code == 503 and "busy" in r.json()["detail"]
