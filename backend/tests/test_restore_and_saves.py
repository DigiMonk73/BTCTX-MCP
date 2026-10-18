"""
An in-app restore keeps this install's login, AI key and switch, the open
sessions of other browsers and the price settings as the live database holds
them just before the restored one replaces it: read then, under the live
database's write lock, held until the swap. So a change saved while a
restore runs (a new password, a logout, a key revoked, a price setting) is
kept, and a save that reaches the swap itself waits for it, then is refused
in plain words: nothing is undone.

Real restores over a database of their own (test_restore_checks.py's
`live`).
"""

import sys
import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

import backend.database
import backend.migrate
from backend.main import app
from backend.services import ai_key, backup, outbound
from backend.tests.test_restore_checks import (  # noqa: F401  (live: fixture)
    OWNER, _assert_nothing_changed, _backup, _key_works, _logs_in, _restore, _stored, live,
)
from backend.unexpected_errors import REPLACED, UNEXPECTED

NEW_LOGIN = {**OWNER, "password": "owner-password-456"}
NOBODY = {"price_source": "off", "mempool_url": None, "mempool_fallback": False, "proxy_url": None}


def _browser() -> TestClient:
    """Another browser, logged in as the owner."""
    client = TestClient(app)
    assert client.post("/api/login", json=OWNER).status_code == 200
    return client


def _copy_of(client: TestClient) -> TestClient:
    return TestClient(app, cookies=dict(client.cookies))


def _logged_in(client: TestClient) -> bool:
    return client.get("/api/transactions").status_code == 200


def _new_password(client: TestClient):
    user_id = client.get("/api/users/").json()[0]["id"]
    return client.patch(f"/api/users/{user_id}",
                        json={"password": NEW_LOGIN["password"], "current_password": OWNER["password"]})


def _once_rebuilt(monkeypatch, changes) -> None:
    """Make `changes` while the restore runs: its new database is built,
    the swap hasn't started."""
    rebuild = backup._rebuild

    def rebuild_then_change(*args):
        result = rebuild(*args)
        changes()
        return result

    monkeypatch.setattr(backup, "_rebuild", rebuild_then_change)


def test_a_restore_alone_keeps_this_installs_login_key_sessions_and_prices(live, tmp_path):  # noqa: F811
    other = _browser()
    blob, other_installs_key = _backup(tmp_path)

    r = _restore(live.client, blob)

    assert r.status_code == 200, r.text
    assert _logged_in(other) and not _logged_in(live.client)  # the restoring browser logs in again
    assert _logs_in(TestClient(app), OWNER)
    assert _key_works(live.token) and not _key_works(other_installs_key)
    assert outbound.current().price_source == "public" and outbound.current().proxy_url is not None


def test_changes_saved_while_a_restore_runs_are_kept(live, tmp_path, monkeypatch):  # noqa: F811
    changer, leaving = _browser(), _browser()
    left_behind = _copy_of(leaving)  # a copy of a cookie that logs out
    blob, _ = _backup(tmp_path)
    answers = {}

    def changes():
        answers["key revoked"] = changer.delete("/api/settings/ai-key").status_code
        answers["access off"] = changer.put("/api/settings/ai-access", json={"on": False}).status_code
        answers["prices"] = changer.put("/api/settings/network", json=NOBODY).status_code
        answers["logout"] = leaving.post("/api/logout").status_code
        answers["password"] = _new_password(changer).status_code
        answers["meanwhile"] = (_key_works(live.token), _logged_in(left_behind), _logs_in(TestClient(app), OWNER))

    _once_rebuilt(monkeypatch, changes)
    r = _restore(live.client, blob)

    assert r.status_code == 200, r.text
    assert answers.pop("meanwhile") == (False, False, False)
    assert set(answers.values()) == {200}, answers
    assert not _key_works(live.token)
    settings = _stored(live.engine)["settings"]
    assert ai_key.HASH_KEY not in settings and settings[ai_key.ACCESS_KEY] == "off"
    assert settings[outbound.SOURCE_KEY] == "off" and outbound.current().price_source == "off"
    assert not _logged_in(left_behind)
    assert _logged_in(changer)  # the password's change kept its own browser logged in
    assert not _logs_in(TestClient(app), OWNER)
    assert _logs_in(TestClient(app), NEW_LOGIN)


def test_a_change_at_the_swap_waits_then_is_refused_in_plain_words(live, tmp_path, monkeypatch, request):  # noqa: F811
    """The swap holds the live database's write lock: a save then waits for
    it, and once the database is replaced SQLite refuses the write. Its
    answer says so, and nothing of it is kept."""
    if sys.version_info < (3, 11):  # SQLite's code isn't named there: the answer is the plain 500
        request.applymarker(pytest.mark.unexpected_error)
    changer = _browser()
    blob, _ = _backup(tmp_path)
    writing, answer = threading.Event(), {}

    def note_the_write(conn, cursor, statement, *args):
        if statement.startswith("UPDATE users"):
            writing.set()

    copy_live_database = backend.migrate.backup_sqlite

    def copy_while_a_change_waits(db_path, label, **kwargs):  # under the lock, before the swap
        answer["thread"] = threading.Thread(target=lambda: answer.update(r=_new_password(changer)))
        answer["thread"].start()
        assert writing.wait(10)
        assert answer["thread"].is_alive()  # waiting for the lock
        return copy_live_database(db_path, label, **kwargs)

    event.listen(live.engine, "before_cursor_execute", note_the_write)
    monkeypatch.setattr(backend.migrate, "backup_sqlite", copy_while_a_change_waits)
    try:
        r = _restore(live.client, blob)
        answer["thread"].join(30)
    finally:
        event.remove(live.engine, "before_cursor_execute", note_the_write)

    assert r.status_code == 200, r.text
    refused = answer["r"]
    if sys.version_info >= (3, 11):
        assert (refused.status_code, refused.json()) == (503, {"detail": REPLACED})
    else:
        assert (refused.status_code, refused.json()) == (500, {"detail": UNEXPECTED})
    assert _logs_in(TestClient(app), OWNER)
    assert not _logs_in(TestClient(app), NEW_LOGIN)


def test_a_restore_that_cant_have_the_lock_stops_and_changes_nothing(live, tmp_path, monkeypatch):  # noqa: F811
    """Another save held the live database's lock past SQLite's 5 s wait."""
    before, in_memory = _stored(live.engine), outbound.as_dict()
    blob, _ = _backup(tmp_path)
    with monkeypatch.context() as m:
        m.setattr(backend.database, "take_write_lock", lambda db: False)
        r = _restore(live.client, blob)
    assert r.status_code == 400 and r.json()["detail"] == "Restore failed: " + backup.SAVING
    _assert_nothing_changed(live, before, in_memory)
