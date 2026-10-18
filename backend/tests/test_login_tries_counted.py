"""
Login tries are counted as they arrive (backend/services/login_throttle.py):
a try counts as a failure from when check() lets it through, before its
password or code is checked, until succeeded() says it was right. The
limits (5 free failures per client, 30 a minute across clients) hold for
tries in flight together too. A right password still gets in, and a known
browser (device cookie) still isn't stopped by others' failures.

Each test holds every try the throttle let through, until each try it sent
has been held or answered, so all of them are in flight together.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import bcrypt
import pytest
from fastapi.testclient import TestClient

import backend.main as main_module
from backend.main import app
from backend.models.user import User
from backend.services import first_run, login_throttle

OWNER = {"username": "me", "password": "owners-password-1"}
WRONG = {"username": "me", "password": "a-wrong-guess-1"}
PROXY = "10.8.0.1"
AT_ONCE = 40


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    """The throttle's clock, held still: every try arrives at the same moment."""
    monkeypatch.setattr(login_throttle, "_now", lambda: 1000.0)


@pytest.fixture
def owner_login(fresh_app):
    """The account as the owner set it, with a quick hash."""
    db = fresh_app()
    user = db.query(User).first()
    user.username = OWNER["username"]
    user.password_hash = bcrypt.hashpw(OWNER["password"].encode(), bcrypt.gensalt(rounds=4)).decode()
    db.commit()
    db.close()


class HeldChecks:
    """Stands in for a step a try takes once the throttle let it through,
    holding each one until the test releases them all; counts how many were
    reached."""

    def __init__(self, real):
        self.real = real
        self.reached = 0
        self._lock = threading.Lock()
        self.release = threading.Event()

    def __call__(self, *args):
        with self._lock:
            self.reached += 1
        self.release.wait(timeout=20)
        return self.real(*args)


def at_once(held: HeldChecks, tries: list) -> list[int]:
    """Send every try at the same moment (each a callable returning a
    response); release the held checks once each try has reached one or
    been answered. The status codes, in order."""
    with ThreadPoolExecutor(max_workers=len(tries)) as pool:
        futures = [pool.submit(send) for send in tries]
        deadline = time.monotonic() + 10
        while held.reached + sum(f.done() for f in futures) < len(tries) and time.monotonic() < deadline:
            time.sleep(0.01)
        held.release.set()
        return [f.result().status_code for f in futures]


def anon(host: str) -> TestClient:
    return TestClient(app, client=(host, 50000))


def login_from(host: str, body: dict = WRONG, cookies: dict | None = None):
    return lambda: TestClient(app, client=(host, 50000), cookies=cookies).post("/api/login", json=body)


def hold_logins(monkeypatch) -> HeldChecks:
    """Before a login's user is looked up: a held try then keeps no
    connection to the database, which has fewer than there are tries (one
    with a device cookie keeps the one its check took; at most 5 are held)."""
    held = HeldChecks(main_module.get_user_by_username)
    monkeypatch.setattr(main_module, "get_user_by_username", held)
    return held


def hold_current_password_checks(monkeypatch) -> HeldChecks:
    held = HeldChecks(User.verify_password)
    monkeypatch.setattr(User, "verify_password", lambda user, password: held(user, password))
    return held


def test_wrong_passwords_sent_at_once_from_one_address_are_held_to_five(owner_login, monkeypatch):
    held = hold_logins(monkeypatch)
    codes = at_once(held, [login_from(PROXY) for _ in range(AT_ONCE)])
    assert held.reached == login_throttle.FREE_FAILURES
    assert sorted(codes) == [401] * 5 + [429] * (AT_ONCE - 5)
    r = anon(PROXY).post("/api/login", json=OWNER)  # the address waits, as after five one by one
    assert r.status_code == 429 and r.headers["Retry-After"] == "1"


def test_wrong_passwords_sent_at_once_from_many_addresses_are_held_to_the_cap(owner_login, monkeypatch):
    held = hold_logins(monkeypatch)
    codes = at_once(held, [login_from(f"10.8.1.{i}") for i in range(AT_ONCE)])
    assert held.reached == login_throttle.GLOBAL_MAX
    assert sorted(codes) == [401] * 30 + [429] * (AT_ONCE - 30)
    assert anon("10.8.2.1").post("/api/login", json=OWNER).status_code == 429  # everyone waits


def test_a_known_browser_gets_in_while_others_send_wrong_passwords_at_once(owner_login, monkeypatch):
    """Behind a proxy every request has its address: the owner's browser,
    which logged in before, logs in at the same moment as the others' tries,
    and after them."""
    owner = anon(PROXY)
    assert owner.post("/api/login", json=OWNER).status_code == 200
    cookies = {login_throttle.DEVICE_COOKIE: owner.cookies.get(login_throttle.DEVICE_COOKIE)}
    held = hold_logins(monkeypatch)
    tries = [login_from(PROXY) for _ in range(AT_ONCE)] + [login_from(PROXY, OWNER, cookies)]
    codes = at_once(held, tries)
    assert codes[-1] == 200
    assert sorted(codes[:-1]) == [401] * 5 + [429] * (AT_ONCE - 5)
    assert login_from(PROXY, OWNER, cookies)().status_code == 200
    assert anon(PROXY).post("/api/login", json=OWNER).status_code == 429  # a browser without it waits


def test_a_known_browsers_own_wrong_passwords_sent_at_once_are_held_to_five(owner_login, monkeypatch):
    """A copied device cookie gets no more tries than an address."""
    owner = anon(PROXY)
    assert owner.post("/api/login", json=OWNER).status_code == 200
    cookies = {login_throttle.DEVICE_COOKIE: owner.cookies.get(login_throttle.DEVICE_COOKIE)}
    held = hold_logins(monkeypatch)
    codes = at_once(held, [login_from(PROXY, WRONG, cookies) for _ in range(AT_ONCE)])
    assert held.reached == 5 and sorted(codes) == [401] * 5 + [429] * (AT_ONCE - 5)
    assert anon("10.8.3.1").post("/api/login", json=OWNER).status_code == 200  # counted for it alone


def test_right_passwords_give_their_try_back(owner_login):
    """A success leaves no failure behind: neither its client's count nor
    the count across clients."""
    for _ in range(3):
        assert anon(PROXY).post("/api/login", json=WRONG).status_code == 401
        assert anon(PROXY).post("/api/login", json=OWNER).status_code == 200
    assert login_throttle._clients == {}
    for i in range(login_throttle.GLOBAL_MAX + 5):  # more right logins than the cap, within a minute
        assert anon(f"10.8.4.{i}").post("/api/login", json=OWNER).status_code == 200
    assert len(login_throttle._recent) == 3  # only the three wrong ones
    assert anon("10.8.5.1").post("/api/login", json=OWNER).status_code == 200


@pytest.mark.unexpected_error
def test_an_error_while_checking_leaves_the_try_counted(owner_login, monkeypatch):
    def broken(*_args):
        raise RuntimeError("the lookup broke")

    monkeypatch.setattr(main_module, "get_user_by_username", broken)
    client = TestClient(app, client=(PROXY, 50000), raise_server_exceptions=False)
    assert client.post("/api/login", json=OWNER).status_code == 500
    assert login_throttle._clients[PROXY][0] == 1


def test_reset_account_tries_sent_at_once_are_held_to_five(owner_login, monkeypatch):
    held = hold_current_password_checks(monkeypatch)
    guess = {"username": "someone", "password": "a-new-password-1", "current_password": "a-wrong-guess-1"}
    send = lambda: anon(PROXY).post("/api/users/reset-account", json=guess)  # noqa: E731
    codes = at_once(held, [send for _ in range(AT_ONCE)])
    assert held.reached == 5 and sorted(codes) == [403] * 5 + [429] * (AT_ONCE - 5)


def test_setup_codes_sent_at_once_are_held_to_five(fresh_app, monkeypatch):
    """While the account has the default login, reset-account checks the
    setup code."""
    first_run.ensure_code()
    held = HeldChecks(first_run.check_code)
    monkeypatch.setattr(first_run, "check_code", held)
    claim = {"username": "someone", "password": "a-new-password-1", "setup_code": "AAAA-AAAA-AAAA"}
    send = lambda: anon(PROXY).post("/api/users/reset-account", json=claim)  # noqa: E731
    codes = at_once(held, [send for _ in range(AT_ONCE)])
    assert held.reached == 5 and sorted(codes) == [403] * 5 + [429] * (AT_ONCE - 5)


def test_current_passwords_sent_at_once_to_change_the_login_are_held_to_five(owner_login, monkeypatch):
    owner = anon(PROXY)
    assert owner.post("/api/login", json=OWNER).status_code == 200
    cookies = dict(owner.cookies)
    held = hold_current_password_checks(monkeypatch)
    change = {"password": "a-new-password-2", "current_password": "a-wrong-guess-1"}
    send = lambda: TestClient(app, client=(PROXY, 50000), cookies=cookies).patch("/api/users/1", json=change)  # noqa: E731
    codes = at_once(held, [send for _ in range(AT_ONCE)])
    assert held.reached == 5 and sorted(codes) == [403] * 5 + [429] * (AT_ONCE - 5)
