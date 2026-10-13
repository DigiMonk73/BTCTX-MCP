"""
backend/tests/test_login_protection.py

The routes anyone can reach that check a password or code:
- Login throttling (backend/services/login_throttle.py): after 5 failures
  a client waits 1 s, 2 s, 4 s... (429 + Retry-After), at most 5 minutes;
  30 failures a minute across all clients make everyone wait. Login,
  reset-account and a password change share it.
- New passwords are at least 12 characters (older, shorter ones still log
  in); a password change needs the current password.
- setup-status runs bcrypt once per set of credentials, not on every call.
- The first-run setup code (backend/services/first_run.py): logging in with
  the default admin/password login and claiming it need a code from the
  server's data folder (and its log, outside the Mac app, whose window
  reads the file itself).
"""

import ast
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import bcrypt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.user import User
from backend.services import first_run, login_throttle

from backend.tests.conftest import MAC_APP_HOST, default_login


def good() -> dict:
    return default_login()
BAD = {"username": "admin", "password": "not-the-password"}
NOBODY = {"username": "nobody", "password": "x"}  # a failure without bcrypt's wait


def anon(host: str = "testclient") -> TestClient:
    return TestClient(app, client=(host, 50000))


@pytest.fixture
def clock(monkeypatch):
    """The throttle's clock, moved by hand."""
    now = [1000.0]
    monkeypatch.setattr(login_throttle, "_now", lambda: now[0])
    return now


def fail_login(client: TestClient, times: int, body=NOBODY) -> list:
    return [client.post("/api/login", json=body).status_code for _ in range(times)]


# ---------------------------------------------------------------------------
# Throttling
# ---------------------------------------------------------------------------
def test_repeated_bad_passwords_get_429_with_retry_after(fresh_app, clock):
    me = anon()
    assert fail_login(me, 5, BAD) == [401] * 5
    r = me.post("/api/login", json=good())  # even the right password waits
    assert r.status_code == 429 and r.headers["Retry-After"] == "1"
    assert "Try again in 1 second" in r.json()["detail"]
    clock[0] += 1.01
    assert me.post("/api/login", json=good()).status_code == 200
    # a success clears the count
    assert fail_login(me, 5) == [401] * 5


def test_the_wait_doubles_up_to_five_minutes(fresh_app, clock):
    me = anon()
    fail_login(me, 5)
    waits = []
    for _ in range(12):
        r = me.post("/api/login", json=NOBODY)
        assert r.status_code == 429
        waits.append(int(r.headers["Retry-After"]))
        clock[0] += waits[-1]
        assert me.post("/api/login", json=NOBODY).status_code == 401
    assert waits == [1, 2, 4, 8, 16, 32, 64, 128, 256, 300, 300, 300]


def test_other_clients_are_not_slowed_by_one(fresh_app, clock):
    fail_login(anon("10.0.0.1"), 5)
    assert anon("10.0.0.1").post("/api/login", json=good()).status_code == 429
    assert anon("10.0.0.2").post("/api/login", json=good()).status_code == 200


def test_many_failures_from_many_addresses_make_everyone_wait(fresh_app, clock):
    """Behind StartOS's proxy all requests share one address; an attacker
    may have many. 30 failures within a minute stop every try."""
    for i in range(login_throttle.GLOBAL_MAX):
        assert fail_login(anon(f"10.1.0.{i}"), 1) == [401]
        clock[0] += 1
    r = anon("10.2.0.1").post("/api/login", json=good())
    assert r.status_code == 429 and 1 <= int(r.headers["Retry-After"]) <= 60
    clock[0] += int(r.headers["Retry-After"])
    assert anon("10.2.0.1").post("/api/login", json=good()).status_code == 200


def test_a_client_is_forgotten_after_an_hour(clock):
    req = SimpleNamespace(client=SimpleNamespace(host="10.3.0.1"))
    for _ in range(7):
        login_throttle.failed(req)
    with pytest.raises(HTTPException):
        login_throttle.check(req)
    clock[0] += login_throttle.FORGET_AFTER + 1
    login_throttle.check(req)  # no wait, and a fresh count
    login_throttle.failed(req)
    login_throttle.check(req)


def test_reset_account_current_password_is_throttled(fresh_app, clock):
    db = fresh_app()
    user = db.query(User).first()
    user.username, user.password_hash = "me", bcrypt.hashpw(b"real-password-1", bcrypt.gensalt()).decode()
    db.commit()
    db.close()
    guess = {"username": "attacker", "password": "attacker-pass-1", "current_password": "guess"}
    codes = [anon().post("/api/users/reset-account", json=guess).status_code for _ in range(6)]
    assert codes == [403] * 5 + [429]
    right = dict(guess, current_password="real-password-1")
    assert anon().post("/api/users/reset-account", json=right).status_code == 429
    clock[0] += 1.01
    assert anon().post("/api/users/reset-account", json=right).status_code == 200


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def test_new_passwords_need_12_characters(fresh_app):
    code = first_run.ensure_code()
    short = {"username": "me", "password": "elevenchars", "setup_code": code}
    r = anon().post("/api/users/reset-account", json=short)
    assert r.status_code == 422 and "at least 12 characters" in r.text
    assert anon().post("/api/users/register", json={"username": "x", "password": "elevenchars"}).status_code == 422
    me = anon()
    assert me.post("/api/login", json=good()).status_code == 200
    r = me.patch("/api/users/1", json={"password": "elevenchars", "current_password": "password",
                                         "setup_code": code})
    assert r.status_code == 422
    ok = dict(short, password="twelve-chars")
    assert anon().post("/api/users/reset-account", json=ok).status_code == 200


def test_an_older_short_password_still_logs_in(fresh_app):
    db = fresh_app()
    user = db.query(User).first()
    user.username, user.password_hash = "me", bcrypt.hashpw(b"short1", bcrypt.gensalt()).decode()
    db.commit()
    db.close()
    assert anon().post("/api/login", json={"username": "me", "password": "short1"}).status_code == 200


def test_a_password_change_needs_the_current_password(fresh_app):
    db = fresh_app()
    user = db.query(User).first()
    user.username, user.password_hash = "me", bcrypt.hashpw(b"real-password-1", bcrypt.gensalt()).decode()
    db.commit()
    db.close()
    me = anon()
    assert me.post("/api/login", json={"username": "me", "password": "real-password-1"}).status_code == 200
    change = {"password": "a-new-password-2"}
    for extra in ({}, {"current_password": "guess"}):
        r = me.patch("/api/users/1", json={**change, **extra})
        assert r.status_code == 403 and r.json()["detail"] == "Current password is incorrect."
    r = me.patch("/api/users/1", json={"username": "renamed"})
    assert r.status_code == 403  # the username too
    r = me.patch("/api/users/1", json={**change, "current_password": "real-password-1"})
    assert r.status_code == 200, r.text
    assert anon().post("/api/login", json={"username": "me", "password": "a-new-password-2"}).status_code == 200


# ---------------------------------------------------------------------------
# setup-status
# ---------------------------------------------------------------------------
def test_setup_status_runs_bcrypt_once_per_credentials(fresh_app, monkeypatch):
    calls = []
    real = User.verify_password

    def counting(self, password):
        calls.append(password)
        return real(self, password)

    monkeypatch.setattr(User, "verify_password", counting)
    for _ in range(5):
        assert anon().get("/api/users/setup-status").json()["is_default"] is True
    assert len(calls) == 1

    # A change made elsewhere (the CLI, a restore) is a new hash: checked again
    db = fresh_app()
    db.query(User).first().password_hash = bcrypt.hashpw(b"cli-password-1", bcrypt.gensalt()).decode()
    db.commit()
    db.close()
    assert anon().get("/api/users/setup-status").json()["is_default"] is False
    assert len(calls) == 2


def test_setup_status_flips_after_the_account_is_claimed(fresh_app):
    assert anon().get("/api/users/setup-status").json()["is_default"] is True
    r = anon().post("/api/users/reset-account", json={
        "username": "me", "password": "n3w-passw0rd", "setup_code": first_run.ensure_code()})
    assert r.status_code == 200
    assert anon().get("/api/users/setup-status").json() == {
        "has_user": True, "is_default": False, "setup_code_required": False}


# ---------------------------------------------------------------------------
# First-run setup code
# ---------------------------------------------------------------------------
CLAIM = {"username": "me", "password": "n3w-passw0rd"}


def test_startup_makes_a_code_file_and_logs_it(fresh_app, caplog):
    db = fresh_app()
    with caplog.at_level("WARNING", logger="backend.services.first_run"):
        first_run.prepare(db)
    code = open(first_run.code_path()).read().strip()
    assert len(code) == 14 and code.count("-") == 2
    assert set(code.replace("-", "")) <= set(first_run.CODE_ALPHABET)
    assert stat.S_IMODE(os.stat(first_run.code_path()).st_mode) == 0o600
    assert f"First-run setup code: {code}" in caplog.text and first_run.code_path() in caplog.text
    first_run.prepare(db)  # a restart keeps the same code
    assert open(first_run.code_path()).read().strip() == code
    db.close()


def test_claiming_without_the_code_is_refused(fresh_app):
    first_run.ensure_code()
    r = anon().post("/api/users/reset-account", json=CLAIM)
    assert r.status_code == 403 and "setup code" in r.json()["detail"]
    assert "docker logs" in r.json()["detail"]
    assert anon().get("/api/users/setup-status").json()["is_default"] is True


def test_a_wrong_code_is_refused_and_throttled(fresh_app, clock):
    code = first_run.ensure_code()
    wrong = dict(CLAIM, setup_code="AAAA-AAAA-AAAA")
    codes = [anon().post("/api/users/reset-account", json=wrong).status_code for _ in range(6)]
    assert codes == [403] * 5 + [429]
    clock[0] += 1.01
    right = dict(CLAIM, setup_code=code.lower().replace("-", " "))  # as typed
    assert anon().post("/api/users/reset-account", json=right).status_code == 200


def test_the_right_code_claims_the_account_and_is_deleted(fresh_app):
    code = first_run.ensure_code()
    assert anon().get("/api/users/setup-status").json()["setup_code_required"] is True
    r = anon().post("/api/users/reset-account", json=dict(CLAIM, setup_code=code))
    assert r.status_code == 200, r.text
    assert not os.path.exists(first_run.code_path())
    assert anon().post("/api/login", json={"username": "me", "password": "n3w-passw0rd"}).status_code == 200


def test_a_missing_code_file_is_made_again(fresh_app):
    """Deleted by hand, or a restore brought the default login back."""
    r = anon().post("/api/users/reset-account", json=dict(CLAIM, setup_code="ABCD-EFGH-JKMN"))
    assert r.status_code == 403
    assert os.path.exists(first_run.code_path())


def test_changing_the_default_login_in_settings_needs_the_code_too(fresh_app):
    """Otherwise anyone could log in with admin/password and change it."""
    me = anon()
    assert me.post("/api/login", json=good()).status_code == 200  # with the code
    change = {"username": "me", "password": "n3w-passw0rd", "current_password": "password"}
    assert me.patch("/api/users/1", json=change).status_code == 403
    r = me.patch("/api/users/1", json=dict(change, setup_code=first_run.ensure_code()))
    assert r.status_code == 200, r.text
    assert not os.path.exists(first_run.code_path())


def mac_app() -> TestClient:
    """A client at the Mac app's own address (in Mac mode it answers no other)."""
    return TestClient(app, client=("127.0.0.1", 50000), headers=MAC_APP_HOST)


DEFAULT = {"username": "admin", "password": "password"}


def test_the_mac_app_needs_the_code_too(fresh_app, monkeypatch, caplog):
    """The Mac app's default login needs the setup code too, as a server's
    does (#151). Its window reads the code from the file
    (desktop/desktop_api.py), so its log never shows it."""
    monkeypatch.setenv("BTCTX_DESKTOP", "1")
    db = fresh_app()
    with caplog.at_level("INFO", logger="backend.services.first_run"):
        first_run.prepare(db)
    db.close()
    code = open(first_run.code_path()).read().strip()
    assert stat.S_IMODE(os.stat(first_run.code_path()).st_mode) == 0o600
    assert code not in caplog.text
    assert mac_app().get("/api/users/setup-status").json() == {
        "has_user": True, "is_default": True, "setup_code_required": True}

    r = mac_app().post("/api/login", json=DEFAULT)
    assert r.status_code == 403 and "enter the setup code" in r.json()["detail"]
    assert "docker logs" not in r.json()["detail"]  # where the Mac app keeps it instead
    assert "Application Support/BitcoinTX" in r.json()["detail"]
    assert mac_app().post("/api/login", json=dict(DEFAULT, setup_code="WRNG-WRNG-WRNG")).status_code == 403
    r = mac_app().post("/api/users/reset-account", json=CLAIM)
    assert r.status_code == 403 and "setup code" in r.json()["detail"]
    assert mac_app().get("/api/users/setup-status").json()["is_default"] is True
    assert mac_app().post("/api/login", json=dict(DEFAULT, setup_code=code)).status_code == 200


def test_the_mac_window_sets_the_owners_login_and_keeps_the_ledger(fresh_app, monkeypatch):
    """What the window's first-run step sends (frontend/src/utils/ownLogin.ts):
    the default login with the code, then the new username and password by
    PATCH, never reset-account, which deletes every transaction."""
    monkeypatch.setenv("BTCTX_DESKTOP", "1")
    code = first_run.ensure_code()
    me = mac_app()
    assert me.post("/api/login", json=dict(DEFAULT, setup_code=code)).status_code == 200
    deposit = {"type": "Deposit", "timestamp": "2024-01-02T12:00:00Z", "from_account_id": 99,
               "to_account_id": 1, "amount": "1000", "fee_amount": "0", "fee_currency": "USD"}
    assert me.post("/api/transactions", json=deposit).status_code in (200, 201)

    change = {"username": "owner", "password": "own-passw0rd-1", "current_password": "password"}
    r = me.patch("/api/users/1", json=change)
    assert r.status_code == 403 and "setup code" in r.json()["detail"]
    r = me.patch("/api/users/1", json=dict(change, setup_code=code))
    assert r.status_code == 200, r.text
    assert len(me.get("/api/transactions").json()) == 1  # the session carries on, the ledger stays
    assert not os.path.exists(first_run.code_path())

    assert mac_app().post("/api/login", json=dict(DEFAULT, setup_code=code)).status_code == 401
    own = {"username": "owner", "password": "own-passw0rd-1"}
    assert mac_app().post("/api/login", json=own).status_code == 200
    # The code no longer matters, given or not
    assert mac_app().post("/api/login", json=dict(own, setup_code="WRNG-WRNG-WRNG")).status_code == 200
    assert mac_app().get("/api/users/setup-status").json() == {
        "has_user": True, "is_default": False, "setup_code_required": False}


REBINDING_PAGE = {"Host": "attacker.example:8765", "Origin": "http://attacker.example:8765",
                  "Sec-Fetch-Site": "same-origin"}


def test_the_mac_app_answers_only_at_its_own_address(fresh_app, monkeypatch):
    """In Mac mode the backend answers only requests addressed to 127.0.0.1,
    localhost or [::1] (#151), the page and every route alike."""
    monkeypatch.setenv("BTCTX_DESKTOP", "1")
    default = {"username": "admin", "password": "password"}
    assert anon().post("/api/login", json=default, headers=REBINDING_PAGE).status_code == 421
    assert anon().post("/api/users/reset-account", json=CLAIM, headers=REBINDING_PAGE).status_code == 421
    assert anon().get("/api/users/setup-status", headers=REBINDING_PAGE).status_code == 421
    refused = anon().get("/", headers=REBINDING_PAGE)
    assert refused.status_code == 421 and refused.headers["x-content-type-options"] == "nosniff"
    for name in ("attacker.example", "127.0.0.1.attacker.example", "localhost.attacker.example:8765",
                 "localhost.:8765", "127.0.0.2:8765", "[::2]:8765", "", "127.0.0.1:8765.attacker.example",
                 "[::1].attacker.example", "localhost:abc"):
        assert anon().get("/api/health", headers={"Host": name}).status_code == 421, name
    for name in ("127.0.0.1:8765", "localhost:8765", "[::1]:8765", "LOCALHOST:8765", "127.0.0.1"):
        assert anon().get("/api/health", headers={"Host": name}).status_code == 200, name


def test_a_server_answers_at_any_name(fresh_app, monkeypatch):
    """Docker and StartOS are reached at names of the owner's choosing."""
    monkeypatch.delenv("BTCTX_DESKTOP", raising=False)
    assert anon().get("/api/health", headers={"Host": "bitcointx.home.example:8443"}).status_code == 200


def test_the_mac_app_never_takes_a_client_address_from_x_forwarded_for():
    """The Mac app's server takes a client's address from the connection,
    never from X-Forwarded-For (#151): its uvicorn.Config says so."""
    launcher = ast.parse((Path(__file__).resolve().parents[2] / "desktop" / "entrypoint.py").read_text())
    config = next(node for node in ast.walk(launcher) if isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Attribute) and node.func.attr == "Config")
    settings = {k.arg: k.value.value for k in config.keywords if isinstance(k.value, ast.Constant)}
    assert settings.get("proxy_headers") is False


def test_an_account_without_the_default_login_involves_no_code(fresh_app):
    """StartOS sets a generated password at install."""
    db = fresh_app()
    user = db.query(User).first()
    user.password_hash = bcrypt.hashpw(b"generated-by-startos-24ch", bcrypt.gensalt()).decode()
    db.commit()
    first_run.ensure_code()  # a stale file from before
    first_run.prepare(db)
    db.close()
    assert not os.path.exists(first_run.code_path())
    assert anon().get("/api/users/setup-status").json()["setup_code_required"] is False
    r = anon().post("/api/users/reset-account",
                    json=dict(CLAIM, current_password="generated-by-startos-24ch"))
    assert r.status_code == 200, r.text


def test_the_default_login_needs_the_code(fresh_app):
    """Otherwise anyone who can reach a fresh install logs in with admin/password
    before the owner claims it: restore their own backup, create an AI key."""
    r = anon().post("/api/login", json={"username": "admin", "password": "password"})
    assert r.status_code == 403 and "enter the setup code" in r.json()["detail"]
    assert "Create account" not in r.json()["detail"]  # that page would start the ledger over
    r = anon().post("/api/login", json={"username": "admin", "password": "password", "setup_code": "WRNG-WRNG-WRNG"})
    assert r.status_code == 403
    assert anon().post("/api/login", json=good()).status_code == 200
