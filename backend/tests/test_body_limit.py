"""
Every request body has a size limit, checked before anything reads it
(backend/body_limit.py): FastAPI reads a body before the login check, so
the routes anyone can reach (login, Create account, the account reset) took
a body of any size. Over MAX_BODY_BYTES the answer is 413, before a byte is
read when Content-Length says so, and as soon as the bytes passed it when
the body comes in chunks. The routes taking a file keep their own limits.
"""

import asyncio
import json

import pytest

from backend.body_limit import FORM_ROOM, MAX_BODY_BYTES, too_large
from backend.main import app
from backend.routers import backup
from backend.routers.backup import RESTORE_TOO_LARGE
from backend.routers.csv_import import MAX_FILE_SIZE
from backend.services.csv_import import CSV_COLUMNS
from backend.tests.conftest import default_login

MB = 1024 * 1024
ANYONE = ["/api/login", "/api/users/register", "/api/users/reset-account"]


def send(path: str, chunks: list[bytes], length: int | None) -> tuple[int, int, dict]:
    """
    POST `chunks` straight to the app over ASGI, with a Content-Length of
    `length` (none: the body comes in chunks). Returns the status, how many
    chunks the app read, and the JSON answer.
    """
    headers = [(b"host", b"testserver"), (b"content-type", b"application/json")]
    if length is not None:
        headers.append((b"content-length", str(length).encode()))
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
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, read, json.loads(body or b"{}")


@pytest.mark.parametrize("path", [*ANYONE, "/api/import/entries/preview", "/api/transactions"])
def test_a_body_over_the_limit_is_refused_before_a_byte_is_read(auth_client, path):
    megabyte = b" " * MB
    status, read, answer = send(path, [megabyte] * 6, length=6 * MB)
    assert (status, read) == (413, 0), (path, status, read, answer)
    assert answer["detail"] == too_large(MAX_BODY_BYTES) == "Request too large. Maximum size is 5MB."


@pytest.mark.parametrize("path", ANYONE)
def test_a_body_in_chunks_is_refused_once_it_passes_the_limit(auth_client, path):
    """No Content-Length: the app reads the 6 chunks that pass 5 MB, not the
    other 6."""
    megabyte = b" " * MB
    status, read, answer = send(path, [megabyte] * 12, length=None)
    assert (status, read) == (413, 6), (path, status, read, answer)
    assert answer["detail"] == too_large(MAX_BODY_BYTES)


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


def test_the_restores_own_limit_and_the_form_around_it_pass_the_body_limit(auth_client):
    """Only Content-Length is sent (nothing is read): at the restore's limit
    with room for the form the body is taken, past it refused."""
    status, read, _ = send("/api/backup/restore", [], length=backup.MAX_RESTORE_BYTES + FORM_ROOM + 1)
    assert (status, read) == (413, 0)
    status, _, _ = send("/api/backup/restore", [b"--"], length=backup.MAX_RESTORE_BYTES + FORM_ROOM)
    assert status != 413


def test_a_csv_import_keeps_its_own_limit_and_words(auth_client):
    header = (",".join(CSV_COLUMNS) + "\n").encode()
    row = b"2024-01-05T12:00:00Z,Deposit,1000,External,Bank,,,,,,,\n"
    at_limit = header + row + b"\n" * (MAX_FILE_SIZE - len(header) - len(row))  # blank lines: skipped
    assert len(at_limit) == MAX_FILE_SIZE
    r = auth_client.post("/api/import/preview", files={"file": ("big.csv", at_limit, "text/csv")})
    assert r.status_code == 200, r.text[:300]

    r = auth_client.post("/api/import/preview", files={"file": ("big.csv", at_limit + b"x", "text/csv")})
    assert r.status_code == 400 and r.json()["detail"] == "File too large. Maximum size is 5MB."
