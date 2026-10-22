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
import io
import json
import logging
import time
from base64 import b64encode

import itsdangerous
import pytest
from fastapi import HTTPException, UploadFile

from backend.body_limit import FORM_ROOM, MAX_BODY_BYTES, too_large
from backend.main import SECRET_KEY, SESSION_COOKIE, SESSION_MAX_AGE, app
from backend.routers import backup
from backend.routers.backup import RESTORE_TOO_LARGE
from backend.routers.csv_import import MAX_FILE_SIZE, _read_validated_csv
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
    monkeypatch.setattr(backup, "restore_backup",
                        lambda password, path, **kept: restored.append(path.stat().st_size))
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


@pytest.mark.parametrize("cookie", [
    None,
    session_cookie({"user_id": 1}, key="not-this-app's-key"),
    session_cookie({"user_id": 1}, age=SESSION_MAX_AGE + 60),
    session_cookie({}),
    session_cookie({"user_id": 1}),
    "garbage",
], ids=["no cookie", "another key", "expired", "no user_id", "no open session", "not a cookie"])
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


def test_an_upload_is_read_only_up_to_its_limit():
    """#204: the CSV and River imports read the whole upload (spooled by
    Starlette) before the 5 MB check; now at most the limit and one byte."""
    class Spool(io.BytesIO):
        def read(self, size=-1):
            reads.append(size)
            return super().read(size)

    reads = []
    upload = UploadFile(Spool(b"x" * (MAX_FILE_SIZE + 4096)), filename="big.csv")
    with pytest.raises(HTTPException) as refused:
        _read_validated_csv(upload)
    assert refused.value.status_code == 400 and reads == [MAX_FILE_SIZE + 1]


def test_a_busy_database_answers_busy_not_too_large(auth_client, monkeypatch):
    """Whether a login's session is still open can't be read: the owner is
    told BitcoinTX is busy (503), not that the file is too large."""
    from sqlalchemy.exc import OperationalError

    from backend import session_auth

    def busy(*args):
        raise OperationalError("SELECT", {}, Exception("database is locked"))

    monkeypatch.setattr(session_auth, "session_is_live", busy)
    login = auth_client.cookies.get(SESSION_COOKIE)
    status, read, answer = send("/api/backup/restore", [b" " * MB] * 6, length=6 * MB, cookie=login)
    assert (status, read) == (503, 0) and answer["json"]["detail"] == "BitcoinTX is busy: try again in a moment."


# A body sent with a GET for one of the web app's files (#589's review).
# Starlette 1.8's FileResponse reads receive() while it sends a file, to see
# the client leave (under uvicorn, ASGI spec 2.3), so it reads a body no
# route asked for; past 5 MB that refusal came in the middle of the file.
PAGE_SIZE, SCRIPT_SIZE = 200 * 1024, 300 * 1024  # several of FileResponse's 64 KB chunks


@pytest.fixture
def web_files(tmp_path, monkeypatch):
    """The web app's page and a script of its bundle, served from tmp_path;
    their contents by path."""
    import backend.main as main

    page = b"<!doctype html><title>BitcoinTX</title>".ljust(PAGE_SIZE, b" ")
    script = b"console.log(1);".ljust(SCRIPT_SIZE, b" ")
    (tmp_path / "index.html").write_bytes(page)
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_bytes(script)
    files = next(route.app for route in main.app.routes if getattr(route, "name", None) == "frontend")
    monkeypatch.setattr(files, "directory", str(tmp_path))
    monkeypatch.setattr(files, "all_directories", [str(tmp_path)])
    monkeypatch.setattr(main, "frontend_dist", str(tmp_path))  # the page for the app's own routes
    return {"/": page, "/dashboard": page, "/assets/index-abc123.js": script}


def get_with_a_body(path: str, chunks: list[bytes], arriving: bool) -> tuple[int, bytes, bool]:
    """
    GET `path` straight to the app as uvicorn calls it (ASGI spec 2.3), with
    `chunks` as its body and no Content-Length. `arriving`: each chunk takes
    a turn of the event loop, so the answer gets under way meanwhile; else
    they are all there at once. Once the body is read, receive() waits for
    the answer's end and then says the client left, as uvicorn's does.
    Returns the status, the body sent and whether the answer was finished.
    """
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}, "http_version": "1.1",
        "method": "GET", "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
        "root_path": "", "headers": [(b"host", b"testserver")], "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    sent = []

    async def run():
        finished = asyncio.Event()
        read = 0

        async def receive():
            nonlocal read
            if read == len(chunks):
                await finished.wait()
                return {"type": "http.disconnect"}
            if arriving:
                await asyncio.sleep(0)
            read += 1
            return {"type": "http.request", "body": chunks[read - 1], "more_body": read < len(chunks)}

        async def collect(message):
            sent.append(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                finished.set()

        await asyncio.wait_for(app(scope, receive, collect), timeout=30)

    asyncio.run(run())
    start = next(m for m in sent if m["type"] == "http.response.start")
    bodies = [m for m in sent if m["type"] == "http.response.body"]
    return start["status"], b"".join(m.get("body", b"") for m in bodies), bool(bodies) and not bodies[-1].get(
        "more_body", False)


def no_error_logged(caplog) -> bool:
    return not [r for r in caplog.records if r.levelno >= logging.ERROR]


@pytest.mark.parametrize("path", ["/", "/dashboard", "/assets/index-abc123.js"])
def test_a_body_arriving_while_a_file_is_sent_is_dropped_never_refused_mid_file(web_files, caplog, path):
    """The answer is under way when the body passes 5 MB: nothing can be
    refused any more, so the rest of the body is thrown away and the
    whole file is sent. It was a 200 cut off with no file and an error in
    the log (RuntimeError, or _TooLarge for an app page)."""
    status, body, finished = get_with_a_body(path, [b" " * MB] * 6, arriving=True)
    assert (status, finished, len(body)) == (200, True, len(web_files[path])), (path, status, finished, len(body))
    assert body == web_files[path]
    assert no_error_logged(caplog), [r.getMessage() for r in caplog.records]


@pytest.mark.parametrize("path", ["/", "/dashboard", "/assets/index-abc123.js"])
def test_a_body_past_the_limit_before_a_file_is_sent_is_a_413(web_files, caplog, path):
    """The body passes 5 MB before the answer starts: 413, as for any
    route, never a 500 and an error in the log (the app page's was)."""
    status, body, finished = get_with_a_body(path, [b" " * MB] * 6, arriving=False)
    assert (status, finished) == (413, True), (path, status, body[:200])
    assert json.loads(body)["detail"] == too_large(MAX_BODY_BYTES)
    assert no_error_logged(caplog), [r.getMessage() for r in caplog.records]


def test_a_body_under_the_limit_sent_with_a_file_changes_nothing(web_files, caplog):
    status, body, finished = get_with_a_body("/assets/index-abc123.js", [b" " * MB] * 4, arriving=True)
    assert (status, finished, body) == (200, True, web_files["/assets/index-abc123.js"])
    assert no_error_logged(caplog)
