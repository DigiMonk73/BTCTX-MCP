"""
SQLite's write lock, taken with database.take_write_lock (#402) by Delete
All, the hourly prices' apply and a login's timezone fill. Each takes it at
its own step and holds it until it ends, and answers a database another
save keeps locked in its own words: Delete All's 503 and log line, the
apply's 503, the fill's False.
"""

import logging
import sqlite3
from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from backend.database import is_busy, take_write_lock
from backend.models.app_setting import AppSetting
from backend.services import hourly_review, tax_time, wipe
from backend.tests.conftest import init_test_db, remove_temp_db, temp_db_file

WAIT = 0.1  # seconds a session here waits for the lock (5 in the app)
NY = "America/New_York"


@pytest.fixture
def database(monkeypatch):
    """A database of its own, as a fresh install has it (no timezone
    chosen); its file."""
    monkeypatch.delenv("BTCTX_TIMEZONE", raising=False)
    path = temp_db_file()
    engine = create_engine(f"sqlite:///{path}")
    init_test_db(engine)
    engine.dispose()
    yield path
    remove_temp_db(path)


@pytest.fixture
def session(database):
    """A session on that database that waits WAIT for the write lock."""
    engine = create_engine(f"sqlite:///{database}", connect_args={"timeout": WAIT})
    db = sessionmaker(bind=engine)()
    yield db
    db.close()
    engine.dispose()


@contextmanager
def held(path):
    """The write lock held by another connection, as an import saving holds it."""
    other = sqlite3.connect(path, timeout=0)
    other.execute("BEGIN IMMEDIATE")
    try:
        yield
    finally:
        other.rollback()
        other.close()


def locked_elsewhere(path) -> bool:
    """Whether another connection's save would have to wait now."""
    other = sqlite3.connect(path, timeout=0)
    try:
        other.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError as e:
        assert "locked" in str(e)
        return True
    else:
        other.rollback()
        return False
    finally:
        other.close()


def in_transaction(db: Session) -> bool:
    return db.connection().connection.driver_connection.in_transaction


def delete_all(db):
    return wipe.delete_all(db, wipe.CONFIRMATION)


def apply_hourly(db):
    return hourly_review.apply_hourly_prices(db, ids=[1])


def fill(db):
    return tax_time.fill_tax_timezone(db, NY)


def answer(step, db):
    """What step(db) answered: its refusal's status and words, else what it returned."""
    try:
        return step(db)
    except HTTPException as e:
        return e.status_code, e.detail


@pytest.fixture
def one_to_apply(monkeypatch):
    """The hourly prices' check lists one transaction, so the apply goes on
    to its copy and the lock."""
    monkeypatch.setattr(hourly_review, "hourly_changes", lambda db, **_: [{"id": 1}])


def test_the_lock_is_held_until_the_session_ends(session, database):
    assert take_write_lock(session) is True
    assert locked_elsewhere(database)
    session.rollback()
    assert not locked_elsewhere(database)


def test_a_lock_held_past_the_wait_takes_nothing(session, database):
    with held(database):
        assert take_write_lock(session) is False
    assert not in_transaction(session)


@pytest.mark.parametrize(("orig", "busy"), [
    (sqlite3.OperationalError("database is locked"), True),
    (sqlite3.OperationalError("disk I/O error"), False),
], ids=["locked", "another error"])
def test_only_sqlites_own_message_says_busy(orig, busy):
    """Never "locked" in a query's parameters."""
    assert is_busy(OperationalError("UPDATE app_settings SET value = ?", ("locked",), orig)) is busy
    assert is_busy(RuntimeError("database is locked")) is False


BUSY_ANSWERS = [
    (delete_all, (503, "Not deleted: BitcoinTX was busy saving something else. Try again."),
     [("backend.services.wipe", logging.WARNING, "Deleting every transaction: the database is busy, nothing deleted")]),
    (apply_hourly, (503, "Not applied: BitcoinTX was busy saving something else. Try again."), []),
    (fill, False, []),
]


@pytest.mark.parametrize(("step", "said", "logged"), BUSY_ANSWERS, ids=["Delete All", "hourly apply", "timezone fill"])
def test_each_says_a_busy_database_in_its_own_words(session, database, one_to_apply, caplog, step, said, logged):
    with held(database), caplog.at_level(logging.WARNING):
        assert answer(step, session) == said
    assert [(r.name, r.levelno, r.getMessage()) for r in caplog.records if r.name.startswith("backend")] == logged
    assert not in_transaction(session)
    assert session.get(AppSetting, tax_time.SETTING_KEY) is None


@pytest.mark.parametrize("step", [delete_all, apply_hourly, fill], ids=["Delete All", "hourly apply", "timezone fill"])
def test_each_fails_loudly_in_a_session_with_its_own_transaction(session, one_to_apply, step):
    """Only a lock held elsewhere is busy."""
    session.execute(text("UPDATE app_settings SET key = key"))  # a write opens its transaction
    with pytest.raises(OperationalError, match="within a transaction"):
        step(session)


def test_delete_all_holds_the_lock_from_its_check(session, database, monkeypatch):
    seen = []
    real = wipe.refusal

    def check(db, *args):
        seen.append(locked_elsewhere(database))
        return real(db, *args)

    monkeypatch.setattr(wipe, "refusal", check)
    assert delete_all(session) is None
    assert seen == [True]
    assert not locked_elsewhere(database)


def test_the_hourly_apply_takes_the_lock_after_its_copy(session, database, one_to_apply, monkeypatch):
    seen = {}
    real = hourly_review.backup_sqlite

    def copy(*args, **kwargs):
        seen["copy"] = locked_elsewhere(database)
        return real(*args, **kwargs)

    def changes(db, *args):
        seen["changes"] = locked_elsewhere(database)
        return []  # edited meanwhile: nothing left to apply

    monkeypatch.setattr(hourly_review, "backup_sqlite", copy)
    monkeypatch.setattr(hourly_review, "_changes", changes)
    assert apply_hourly(session)["changed"] == []
    assert seen == {"copy": False, "changes": True}
    assert not locked_elsewhere(database)


def test_the_timezone_fill_holds_the_lock_from_its_check_to_its_save(session, database, monkeypatch):
    seen = []
    real = tax_time._never_chosen

    def check(db):
        seen.append(locked_elsewhere(database))
        return real(db)

    monkeypatch.setattr(tax_time, "_never_chosen", check)
    assert fill(session) is True
    assert seen == [True]
    assert not locked_elsewhere(database)
    assert session.get(AppSetting, tax_time.SETTING_KEY).value == NY
