"""
The encrypted backup download writes the backup to a temp file and streams
it; the file is removed once the answer is sent (#462). When the backup
itself failed (no database file, a SQLite error, a full disk), the answer
was the right 500 with its fixed sentence, but the file, empty or holding
part of the backup, stayed in the system's temp folder for good: one more
for each failed download. It now goes in every case: a backup that fails
before writing or partway, a download that succeeds, one the client cuts off.

Each test points the system's temp folder at a folder of its own and checks
that the router's file was made there and is gone.
"""

import asyncio
import sqlite3
import tempfile
from pathlib import Path

import pytest

from backend.main import app
from backend.routers import backup as backup_router
from backend.services import backup
from backend.unexpected_errors import UNEXPECTED

PASSWORD = "twelve-chars"
URL = "/api/backup/download"


@pytest.fixture
def temp_folder(tmp_path, monkeypatch, test_engine):
    """The system's temp folder, empty, and the test database as the one
    backed up (never the project's own)."""
    folder = tmp_path / "tmp"
    folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    monkeypatch.setattr(backup, "DB_PATH", Path(test_engine.url.database))
    return folder


@pytest.fixture
def made(monkeypatch):
    """The files the route handed to make_backup, which still runs."""
    files = []
    real = backup_router.make_backup

    def recording(password, output_file):
        files.append(Path(output_file))
        return real(password, output_file)

    monkeypatch.setattr(backup_router, "make_backup", recording)
    return files


def _left(folder: Path) -> list:
    return sorted(p.name for p in folder.iterdir())


@pytest.mark.unexpected_error
def test_a_backup_that_fails_before_writing_leaves_no_temp_file(auth_client, temp_folder, made, tmp_path,
                                                                 monkeypatch):
    monkeypatch.setattr(backup, "DB_PATH", tmp_path / "missing.db")

    r = auth_client.post(URL, data={"password": PASSWORD})

    assert (r.status_code, r.json()) == (500, {"detail": UNEXPECTED})
    assert [p.parent for p in made] == [temp_folder]
    assert _left(temp_folder) == []


@pytest.mark.unexpected_error
def test_a_backup_that_fails_partway_leaves_no_temp_file(auth_client, temp_folder, monkeypatch):
    written = []

    def fails_partway(password, output_file):
        Path(output_file).write_bytes(b"part of a backup")
        written.append(Path(output_file))
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(backup_router, "make_backup", fails_partway)

    r = auth_client.post(URL, data={"password": PASSWORD})

    assert (r.status_code, r.json()) == (500, {"detail": UNEXPECTED})
    assert [p.parent for p in written] == [temp_folder]
    assert _left(temp_folder) == []


def test_a_download_that_succeeds_leaves_no_temp_file(auth_client, temp_folder, made):
    r = auth_client.post(URL, data={"password": PASSWORD})

    assert r.status_code == 200
    assert backup.decrypt_backup(r.content, PASSWORD).startswith(backup.SQLITE_HEADER)
    assert [p.parent for p in made] == [temp_folder]
    assert _left(temp_folder) == []


def _cut_off_after_the_first_piece(cookies: dict) -> list:
    """POST the download straight to the app over ASGI as uvicorn serves it
    (ASGI spec 2.3), the client going away once the first piece of the file
    has come: from then on uvicorn drops what is sent and says the client
    disconnected. Returns the messages the app sent before that."""
    body = f"password={PASSWORD}".encode()
    headers = [(b"host", b"testserver"), (b"content-type", b"application/x-www-form-urlencoded"),
               (b"content-length", str(len(body)).encode()),
               (b"cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()).encode())]
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}, "http_version": "1.1",
        "method": "POST", "scheme": "http", "path": URL, "raw_path": URL.encode(), "query_string": b"",
        "root_path": "", "headers": headers, "client": ("127.0.0.1", 50000), "server": ("testserver", 80),
    }
    sent = []

    async def run():
        gone = asyncio.Event()
        asked = False

        async def receive():
            nonlocal asked
            if not asked:
                asked = True
                return {"type": "http.request", "body": body, "more_body": False}
            await gone.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if gone.is_set():
                return
            sent.append(message)
            if message["type"] == "http.response.body" and message.get("body"):
                gone.set()

        await app(scope, receive, send)

    asyncio.run(run())
    return sent


def test_a_download_the_client_cuts_off_leaves_no_temp_file(auth_client, temp_folder, made):
    sent = _cut_off_after_the_first_piece(dict(auth_client.cookies))

    assert sent[0]["type"] == "http.response.start" and sent[0]["status"] == 200
    assert [m["more_body"] for m in sent[1:]] == [True]  # one piece, then the client was gone
    assert [p.parent for p in made] == [temp_folder]
    assert _left(temp_folder) == []
