"""
Every request body has a size limit, checked before anything reads it
(backend/body_limit.py): FastAPI reads a body before the login check, so
the routes anyone can reach (login, Create account, the account reset) took
a body of any size. Over MAX_BODY_BYTES the answer is 413, before a byte is
read when Content-Length says so, and as soon as the bytes passed it when
the body comes in chunks. The routes taking a file keep their own limits,
for a logged-in owner's request only.
"""

import asyncio
import json
import time
from base64 import b64encode

import itsdangerous
import pytest

from backend.body_limit import FORM_ROOM, MAX_BODY_BYTES, too_large
from backend.main import SECRET_KEY, SESSION_COOKIE, SESSION_MAX_AGE, app
from backend.routers import backup
from backend.routers.backup import RESTORE_TOO_LARGE
from backend.routers.csv_import import MAX_FILE_SIZE
from backend.services.csv_import import CSV_COLUMNS
from backend.tests.conftest import default_login

MB = 1024 * 1024
ANYONE = ["/api/login", "/api/users/register", "/api/users/reset-account"]


def send(path: str, chunks: list[bytes], length: int | None, cookie: str | None = None) -> tuple[int, int, dict]:
    """
    POST `chunks` straight to the app over ASGI, with a Content-Length of
    `length` (none: the body comes in chunks) and this session cookie.
    Returns the status, how many chunks the app read, and the answer: its
    headers and its JSON ("json").
    """
    headers = [(b"host", b"testserver"), (b"content-type", b"application/json")]
    if length is not None:
        headers.append((b"content-length", str(length).encode()))
    if cookie is not None:
        headers.append((b"cookie", f"{SESSION_COOKIE}={cookie}".encode()))
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
        "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
        "headers": headers, "client": ("127.0.0.1", 50000), "server": ("testserver", 80),
    }
    read = 0
    sent = []

    async def receive():
        nonlocal read
        if read == len(chunks):
            return {"type": "http.disconnect"}
        read += 1
        return {"type": "http.request", "body": chunks[read - 1], "more_body": read < len(chunks)}

    async def collect(message):
        sent.append(message)

    asyncio.run(app(scope, receive, collect))
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    answer = {name.decode(): value.decode() for name, value in start["headers"]}
    return start["status"], read, {**answer, "json": json.loads(body or b"{}")}


@pytest.mark.parametrize("path", [*ANYONE, "/api/import/entries/preview", "/api/transactions"])
def test_a_body_over_the_limit_is_refused_before_a_byte_is_read(auth_client, path):
    megabyte = b" " * MB
    status, read, answer = send(path, [megabyte] * 6, length=6 * MB)
    assert (status, read) == (413, 0), (path, status, read, answer)
    assert answer["json"]["detail"] == too_large(MAX_BODY_BYTES) == "Request too large. Maximum size is 5MB."


@pytest.mark.parametrize("path", ANYONE)
def test_a_body_in_chunks_is_refused_once_it_passes_the_limit(auth_client, path):
    """No Content-Length: the app reads the 6 chunks that pass 5 MB, not the
    other 6."""
    megabyte = b" " * MB
    status, read, answer = send(path, [megabyte] * 12, length=None)
    assert (status, read) == (413, 6), (path, status, read, answer)
    assert answer["json"]["detail"] == too_large(MAX_BODY_BYTES)


def test_a_body_up_to_the_limit_is_unaffected(auth_client):
    login = default_login()
    prefix = b'{"username": "%s", "password": "%s", "setup_code": "%s", "pad": "' % (
        login["username"].encode(), login["password"].encode(), login["setup_code"].encode())
    body = prefix + b"x" * (MAX_BODY_BYTES - len(prefix) - 2) + b'"}'
    assert len(body) == MAX_BODY_BYTES
    r = auth_client.post("/api/login", content=body, headers={"Content-Type": "application/json"})
    assert r.status_code == 200, r.text


# Routes taking a file keep their own limits
def test_a_restore_near_its_own_limit_is_still_taken(auth_client, monkeypatch):
    """The restore's own limit (1 GiB, here 8 MB) is checked by the restore;
    the 5 MB limit doesn't apply to it."""
    restored = []
    monkeypatch.setattr(backup, "MAX_RESTORE_BYTES", 8 * MB)
    monkeypatch.setattr(backup, "restore_backup", lambda password, path: restored.append(path.stat().st_size))
    file = b"b" * (8 * MB - 1)
    r = auth_client.post("/api/backup/restore", data={"password": "pw"}, files={"file": ("b.btx", file)})
    assert r.status_code == 200, r.text
    assert restored == [len(file)]
    assert auth_client.post("/api/login", json=default_login()).status_code == 200  # the restore logged out

    r = auth_client.post("/api/backup/restore", data={"password": "pw"}, files={"file": ("b.btx", file + b"bb")})
    assert r.status_code == 413 and r.json()["detail"] == RESTORE_TOO_LARGE  # its own check, its own words
    assert restored == [len(file)]


def test_a_413_carries_the_security_headers(auth_client):
    status, read, answer = send("/api/login", [], length=MAX_BODY_BYTES + 1)
    assert (status, read) == (413, 0)
    assert answer["x-content-type-options"] == "nosniff" and answer["x-frame-options"] == "DENY"
    assert answer["referrer-policy"] == "no-referrer" and "frame-ancestors 'none'" in answer["content-security-policy"]


def session_cookie(session: dict, key: str = SECRET_KEY, age: int = 0) -> str:
    """A session cookie as SessionMiddleware writes it, signed with `key`,
    `age` seconds ago."""
    class Signer(itsdangerous.TimestampSigner):
        def get_timestamp(self):
            return int(time.time()) - age

    return Signer(str(key)).sign(b64encode(json.dumps(session).encode())).decode()


def test_the_restores_own_limit_and_the_form_around_it_pass_with_a_login(auth_client):
    """Only Content-Length is sent (nothing is read): at the restore's limit
    with room for the form the body is taken, past it refused."""
    login = auth_client.cookies.get(SESSION_COOKIE)
    limit = backup.MAX_RESTORE_BYTES + FORM_ROOM
    status, read, _ = send("/api/backup/restore", [], length=limit + 1, cookie=login)
    assert (status, read) == (413, 0)
    status, _, _ = send("/api/backup/restore", [b"--"], length=limit, cookie=login)
    assert status != 413
    status, _, _ = send("/api/backup/restore", [b"--"], length=6 * MB, cookie=session_cookie({"user_id": 1}))
    assert status != 413


@pytest.mark.parametrize("cookie", [
    None,
    session_cookie({"user_id": 1}, key="not-this-app's-key"),
    session_cookie({"user_id": 1}, age=SESSION_MAX_AGE + 60),
    session_cookie({}),
    "garbage",
], ids=["no cookie", "another key", "expired", "no user_id", "not a cookie"])
def test_a_file_over_5_mb_needs_a_login(auth_client, cookie):
    """The larger allowance is for a logged-in owner's file: anyone else
    gets 5 MB, refused before a byte is read."""
    for path in ("/api/backup/restore", "/api/import/preview"):
        status, read, answer = send(path, [b" " * MB] * 6, length=6 * MB, cookie=cookie)
        assert (status, read) == (413, 0), (path, status, read, answer["json"])


def test_a_csv_import_keeps_its_own_limit_and_words(auth_client):
    header = (",".join(CSV_COLUMNS) + "\n").encode()
    row = b"2024-01-05T12:00:00Z,Deposit,1000,External,Bank,,,,,,,\n"
    at_limit = header + row + b"\n" * (MAX_FILE_SIZE - len(header) - len(row))  # blank lines: skipped
    assert len(at_limit) == MAX_FILE_SIZE
    r = auth_client.post("/api/import/preview", files={"file": ("big.csv", at_limit, "text/csv")})
    assert r.status_code == 200, r.text[:300]

    r = auth_client.post("/api/import/preview", files={"file": ("big.csv", at_limit + b"x", "text/csv")})
    assert r.status_code == 400 and r.json()["detail"] == "File too large. Maximum size is 5MB."
