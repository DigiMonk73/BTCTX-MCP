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

import json
import sqlite3
import sys
import threading
from contextlib import closing, contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.routing import Route

import backend.database
import backend.migrate
from backend.database import init_db
from backend.main import app
from backend.services import ai_key, backup, outbound
from backend.tests.conftest import init_test_db
from backend.tests.test_restore_checks import (  # noqa: F401  (live: fixture)
    OWNER, STOPPED, _assert_nothing_changed, _backup, _key_works, _logs_in, _restore, _stored, live,
)
from backend.unexpected_errors import REPLACED, UNEXPECTED, UnexpectedErrorMiddleware

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


@contextmanager
def _a_new_password_at_the_swap(install, changer, monkeypatch):
    """`changer` changes the password once the restore holds the live
    database's lock (as it copies it, just before the swap): the save waits
    for the lock. Gives the answer ("r"), once the restore has answered."""
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

    event.listen(install.engine, "before_cursor_execute", note_the_write)
    try:
        with monkeypatch.context() as m:
            m.setattr(backend.migrate, "backup_sqlite", copy_while_a_change_waits)
            yield answer
        if "thread" in answer:
            answer["thread"].join(30)
    finally:
        event.remove(install.engine, "before_cursor_execute", note_the_write)


def _refused_in_plain_words(answer, request) -> None:
    """The save the swap refused said so, and nothing of it is kept."""
    if sys.version_info >= (3, 11):
        assert (answer.status_code, answer.json()) == (503, {"detail": REPLACED})
    else:  # SQLite's code isn't named there: the plain 500
        request.applymarker(pytest.mark.unexpected_error)
        assert (answer.status_code, answer.json()) == (500, {"detail": UNEXPECTED})
    assert _logs_in(TestClient(app), OWNER)
    assert not _logs_in(TestClient(app), NEW_LOGIN)


def test_a_change_at_the_swap_waits_then_is_refused_in_plain_words(live, tmp_path, monkeypatch, request):  # noqa: F811
    """The swap holds the live database's write lock: a save then waits for
    it, and once the database is replaced SQLite refuses the write. Its
    answer says so, and nothing of it is kept."""
    changer = _browser()
    blob, _ = _backup(tmp_path)
    with _a_new_password_at_the_swap(live, changer, monkeypatch) as answer:
        r = _restore(live.client, blob)

    assert r.status_code == 200, r.text
    _refused_in_plain_words(answer["r"], request)


# A live database an older version's restore left in write-ahead-log mode
def test_the_restore_switches_a_live_database_out_of_write_ahead_log_mode(live, tmp_path, monkeypatch,  # noqa: F811
                                                                          request):
    """With nothing else holding it, the restore switches it to the
    rollback journal before its lock, so a save at the swap is refused in
    plain words there too (in the log, it was answered as saved, and lost)."""
    with live.engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode = WAL")
    changer = _browser()
    blob, _ = _backup(tmp_path)
    with _a_new_password_at_the_swap(live, changer, monkeypatch) as answer:
        r = _restore(live.client, blob)

    assert r.status_code == 200, r.text
    _refused_in_plain_words(answer["r"], request)
    assert _journal_mode(live.path) == "delete"


def test_a_live_database_kept_in_write_ahead_log_mode_stops_the_restore(live, tmp_path, monkeypatch):  # noqa: F811
    """Something else has it open, so it can't be switched: the restore
    stops before it copies or replaces anything, the database as it was.
    Once nothing else has it open, the restore goes through."""
    with live.engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode = WAL")
    changer = _browser()
    blob, _ = _backup(tmp_path)
    with closing(sqlite3.connect(live.path)) as held:
        held.execute("SELECT count(*) FROM users").fetchone()
        before, in_memory = _stored(live.engine), outbound.as_dict()
        with _a_new_password_at_the_swap(live, changer, monkeypatch) as answer:
            r = _restore(live.client, blob)

        assert r.status_code == 400 and r.json()["detail"] == "Restore failed: " + backup.OLD_JOURNAL
        assert "thread" not in answer  # stopped before its copy and swap: no save waited at them
        _assert_nothing_changed(live, before, in_memory)
        assert _journal_mode(live.path) == "wal"
    assert _restore(live.client, blob).status_code == 200
    assert _journal_mode(live.path) == "delete"


def test_a_restore_that_cant_have_the_lock_stops_and_changes_nothing(live, tmp_path, monkeypatch):  # noqa: F811
    """Another save held the live database's lock past SQLite's 5 s wait."""
    before, in_memory = _stored(live.engine), outbound.as_dict()
    blob, _ = _backup(tmp_path)
    with monkeypatch.context() as m:
        m.setattr(backend.database, "take_write_lock", lambda db: False)
        r = _restore(live.client, blob)
    assert r.status_code == 400 and r.json()["detail"] == "Restore failed: " + backup.SAVING
    _assert_nothing_changed(live, before, in_memory)


def test_with_no_live_database_the_restore_stops_in_plain_words(live, tmp_path, monkeypatch):  # noqa: F811
    """DATABASE_URL naming another database than DATABASE_FILE: there's
    nothing to keep this install's login from, so the backup's would come
    back."""
    before, in_memory = _stored(live.engine), outbound.as_dict()
    elsewhere = live.path.with_name("elsewhere.db")
    blob, _ = _backup(tmp_path)
    with monkeypatch.context() as m:
        m.setattr(backup, "DB_PATH", elsewhere)
        r = _restore(live.client, blob)
    assert r.status_code == 400 and r.json()["detail"] == STOPPED
    assert not list(live.path.parent.glob("elsewhere.db*"))
    _assert_nothing_changed(live, before, in_memory)


# The journal mode a restore's swap relies on
def _journal_mode(path) -> str:
    with closing(sqlite3.connect(path)) as con:
        return con.execute("PRAGMA journal_mode").fetchone()[0]


def _left_in_write_ahead_log_mode(path):
    engine = create_engine(f"sqlite:///{path}")
    init_test_db(engine)
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode = WAL")
    assert _journal_mode(path) == "wal"
    return engine


def test_a_database_left_in_write_ahead_log_mode_starts_in_the_rollback_journal(tmp_path):
    path = tmp_path / "btctx.db"
    engine = _left_in_write_ahead_log_mode(path)
    try:
        init_db(engine)
    finally:
        engine.dispose()
    assert _journal_mode(path) == "delete"
    assert path.read_bytes()[18:20] == b"\x01\x01"


def test_a_log_beside_a_rollback_journal_file_is_switched_at_start(tmp_path):
    """A log with writes in it beside a file whose header says rollback
    journal (an earlier version's restore could leave one): SQLite opens it
    in write-ahead-log mode all the same, so it's switched too, the log's
    writes kept."""
    logged = tmp_path / "logged.db"
    engine = _left_in_write_ahead_log_mode(logged)
    engine.dispose()
    with closing(sqlite3.connect(logged)) as con:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.execute("INSERT INTO app_settings (key, value) VALUES ('in_the_log', 'x')")
        con.commit()
        path = tmp_path / "btctx.db"
        path.write_bytes(logged.read_bytes()[:18] + b"\x01\x01" + logged.read_bytes()[20:])
        path.with_name("btctx.db-wal").write_bytes(logged.with_name("logged.db-wal").read_bytes())
    assert _journal_mode(path) == "wal"
    engine = create_engine(f"sqlite:///{path}")
    try:
        init_db(engine)
    finally:
        engine.dispose()
    assert _journal_mode(path) == "delete" and not path.with_name("btctx.db-wal").exists()
    with closing(sqlite3.connect(path)) as con:
        assert con.execute("SELECT value FROM app_settings WHERE key = 'in_the_log'").fetchone() == ("x",)


def test_a_database_another_connection_holds_open_starts_all_the_same(tmp_path, caplog):
    path = tmp_path / "btctx.db"
    engine = _left_in_write_ahead_log_mode(path)
    with closing(sqlite3.connect(path)) as held:
        held.execute("SELECT count(*) FROM users").fetchone()
        try:
            init_db(engine)
        finally:
            engine.dispose()
    assert "stays in write-ahead-log mode for now: something else has it open" in caplog.text
    assert _journal_mode(path) == "wal"


# The answer to a save a restore's swap refused, on every Python version
class _SQLiteError(Exception):
    """sqlite3's error as Python 3.11+ gives it, its code named (3.10: none)."""

    def __init__(self, name):
        super().__init__("attempt to write a readonly database")  # the same words for each
        self.sqlite_errorname = name


@pytest.mark.parametrize("name, answer", [
    ("SQLITE_READONLY_DBMOVED", (503, REPLACED)),
    ("SQLITE_READONLY", (500, UNEXPECTED)),
    (None, (500, UNEXPECTED)),
], ids=["the file replaced by a restore", "a read-only database", "no name (Python 3.10)"])
def test_only_a_save_the_swap_refused_says_so(name, answer, request, caplog):
    if answer[0] == 500:
        request.applymarker(pytest.mark.unexpected_error)

    def save(_request):
        raise OperationalError("UPDATE users SET password_hash=?", ("x",), _SQLiteError(name))

    client = TestClient(Starlette(routes=[Route("/save", save, methods=["POST"])],
                                  middleware=[Middleware(UnexpectedErrorMiddleware)]))
    r = client.post("/save")

    assert (r.status_code, r.json()["detail"]) == answer
    assert ("not saved: a restore replaced the database" in caplog.text) == (answer[0] == 503)


# The last account id given (accounts_last_id, 2.0 spec 5.1, 5.11): a
# restore keeps the higher of this install's and the backup's, so an id
# handed out here, even while the restore ran, is never handed out again
LAST_ID = "SELECT value FROM app_settings WHERE key = 'accounts_last_id'"


def _last_id(live):  # noqa: F811
    with closing(sqlite3.connect(live.path)) as con:
        return con.execute(LAST_ID).fetchall()


def _add_wallet(client, name):
    r = client.post("/api/accounts/", json={"kind": "wallet", "name": name})
    assert r.status_code == 201, r.text
    return r.json()[0]["id"]


def test_a_restore_keeps_an_id_given_here_before_it(live, tmp_path):  # noqa: F811
    blob, _ = _backup(tmp_path)
    assert _add_wallet(live.client, "Jade") == 100  # not in the backup
    assert _restore(live.client, blob).status_code == 200
    assert _last_id(live) == [("100",)]
    assert _add_wallet(_browser(), "Coldcard") == 101


def test_a_restore_keeps_a_backups_higher_last_id(live, tmp_path):  # noqa: F811
    _add_wallet(live.client, "Jade")
    blob, _ = _backup(tmp_path, "INSERT INTO app_settings (key, value) VALUES ('accounts_last_id', '150')")
    assert _restore(live.client, blob).status_code == 200
    assert _last_id(live) == [("150",)]


@pytest.mark.parametrize("stored", ["'\u00b2'", "'9223372036854775807'", "X'313530'", "X'FF'"])
def test_a_backups_last_id_that_isnt_one_is_ignored(live, tmp_path, stored):  # noqa: F811
    _add_wallet(live.client, "Jade")
    blob, _ = _backup(tmp_path, f"INSERT INTO app_settings (key, value) VALUES ('accounts_last_id', {stored})")
    assert _restore(live.client, blob).status_code == 200
    assert _last_id(live) == [("100",)]
    assert _add_wallet(_browser(), "Coldcard") == 101


def test_an_id_given_while_a_restore_runs_isnt_given_again(live, tmp_path, monkeypatch):  # noqa: F811
    other, given = _browser(), []
    blob, _ = _backup(tmp_path)
    _once_rebuilt(monkeypatch, lambda: given.append(_add_wallet(other, "Jade")))
    assert _restore(live.client, blob).status_code == 200
    assert given == [100] and _last_id(live) == [("100",)]
    assert _add_wallet(_browser(), "Coldcard") == 101


# The rows from before 0.9.2 (accounts_old_rows, 2.0 spec 5.13, 5.11): a
# restore takes the backup's list, which names the backup's own rows; a 1.x
# backup has none, and the start after the restore writes it from its rows
OLD_ROWS = "SELECT value FROM app_settings WHERE key = 'accounts_old_rows'"


def _old_rows(live):  # noqa: F811
    with closing(sqlite3.connect(live.path)) as con:
        return con.execute(OLD_ROWS).fetchall()


def test_a_restore_takes_a_2_0_backups_list_of_old_rows(live, tmp_path):  # noqa: F811
    with closing(sqlite3.connect(live.path)) as con:
        con.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('accounts_old_rows', '[1, 2]')")
        con.commit()
    blob, _ = _backup(tmp_path, "INSERT OR REPLACE INTO app_settings (key, value) VALUES ('accounts_old_rows', '[42]')")
    assert _restore(live.client, blob).status_code == 200
    assert _old_rows(live) == [("[42]",)]


def test_a_restore_of_a_1x_backup_lists_its_own_old_rows(live, tmp_path):  # noqa: F811
    blob, _ = _backup(
        tmp_path,
        "DELETE FROM app_settings WHERE key = 'accounts_old_rows'",
        "INSERT INTO accounts (id, user_id, name, currency, kind, hidden) VALUES (7, 1, 'cold2', 'BTC', 'wallet', 0)",
        "UPDATE transactions SET to_account_id = 7 WHERE type = 'Buy'",  # rows naming 7, as only 1.x saved
    )
    assert _restore(live.client, blob).status_code == 200
    with closing(sqlite3.connect(live.path)) as con:
        naming_7 = [i for (i,) in con.execute("SELECT id FROM transactions WHERE to_account_id = 7 ORDER BY id")]
    assert naming_7 and _old_rows(live) == [(json.dumps(naming_7),)]


# Which BitcoinTX last recalculated the ledger (recalculated_by, 2.0 spec
# 5.8, 5.11): a restore takes the backup's, which describes the figures that
# come with it; a 1.x backup has none, so the next covered write takes both
# passes of the past-year warning's dry run
RECALCULATED_BY = "SELECT value FROM app_settings WHERE key = 'recalculated_by'"


def _recalculated_by(live):  # noqa: F811
    with closing(sqlite3.connect(live.path)) as con:
        return con.execute(RECALCULATED_BY).fetchall()


def test_a_restore_takes_a_2_0_backups_recalculated_by(live, tmp_path):  # noqa: F811
    assert live.client.post("/api/transactions/recalculate").status_code == 200
    assert _recalculated_by(live)  # this install's
    blob, _ = _backup(tmp_path, "INSERT INTO app_settings (key, value) VALUES ('recalculated_by', '2.0.0 0101 UTC')")
    assert _restore(live.client, blob).status_code == 200
    assert _recalculated_by(live) == [("2.0.0 0101 UTC",)]


def test_a_restore_of_a_1x_backup_leaves_none(live, tmp_path):  # noqa: F811
    assert live.client.post("/api/transactions/recalculate").status_code == 200
    blob, _ = _backup(tmp_path, "DELETE FROM app_settings WHERE key = 'recalculated_by'")
    assert _restore(live.client, blob).status_code == 200
    assert _recalculated_by(live) == []
