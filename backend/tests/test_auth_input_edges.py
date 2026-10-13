"""Edge inputs to the first-run setup code and to password checks must be refused, not crash.

- A setup code with non-ASCII letters or digits is compared with hmac, which raises TypeError
  for non-ASCII text. Such a code can never match, so it is treated as wrong.
- bcrypt reads at most 72 bytes and raises ValueError for more. A longer password never
  matches, so verify_password returns False, and a longer new password is refused (422).

Through the routes these are a wrong code or password like any other: refused, and counted
by the login throttle (#205's review).
"""

import bcrypt
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.user import User
from backend.services import first_run, login_throttle

CODE = "ABCD-EFGH-JKMN"


def test_a_setup_code_with_non_ascii_letters_is_just_wrong(monkeypatch):
    monkeypatch.setattr(first_run, "read_code", lambda: "ABCD-EFGH-JKMN")
    assert first_run.check_code("ÀÀÀÀ-ÀÀÀÀ-ÀÀÀÀ") is False


def test_the_matching_setup_code_still_passes(monkeypatch):
    monkeypatch.setattr(first_run, "read_code", lambda: "ABCD-EFGH-JKMN")
    assert first_run.check_code("abcd-efgh-jkmn") is True


def test_a_password_longer_than_72_bytes_does_not_match_or_raise():
    user = User(username="u", password_hash=bcrypt.hashpw(b"correct horse", bcrypt.gensalt()).decode())
    assert user.verify_password("x" * 73) is False


def test_a_correct_password_still_verifies():
    user = User(username="u", password_hash=bcrypt.hashpw(b"correct horse", bcrypt.gensalt()).decode())
    assert user.verify_password("correct horse") is True


def test_through_the_routes_they_are_refused_and_counted(fresh_app, monkeypatch):
    monkeypatch.setattr(first_run, "read_code", lambda: CODE)
    client, failures = TestClient(app, client=("testclient", 50000)), []
    tries = [
        ("/api/users/reset-account", {"username": "owner", "password": "y" * 14, "setup_code": "ÀÀÀÀ-ÀÀÀÀ-ÀÀÀÀ"}, 403),
        ("/api/login", {"username": "admin", "password": "password", "setup_code": "ÀÀÀÀ-ÀÀÀÀ-ÀÀÀÀ"}, 403),
        ("/api/login", {"username": "admin", "password": "x" * 73}, 401),
        ("/api/login", {"username": "admin", "password": "x" * 71 + "é"}, 401),  # 73 bytes, 72 characters
    ]
    for url, body, status in tries:
        assert client.post(url, json=body).status_code == status
        failures.append(login_throttle._clients["testclient"][0])
    assert failures == [1, 2, 3, 4]


def test_a_new_password_over_72_bytes_is_refused_not_a_server_error(fresh_app, monkeypatch):
    monkeypatch.setattr(first_run, "read_code", lambda: CODE)
    client = TestClient(app)
    for password in ("y" * 73, "é" * 37):  # 73 and 74 bytes
        r = client.post("/api/users/reset-account", json={"username": "owner", "password": password, "setup_code": CODE})
        assert r.status_code == 422 and "at most 72 characters" in r.text
    assert client.post("/api/login", json={"username": "admin", "password": "password", "setup_code": CODE}).status_code == 200
    r = client.patch("/api/users/1", json={"password": "é" * 37, "current_password": "password", "setup_code": CODE})
    assert r.status_code == 422 and "at most 72 characters" in r.text
