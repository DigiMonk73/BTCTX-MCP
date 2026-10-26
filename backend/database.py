#!/usr/bin/env python
"""
The database: the SQLAlchemy engine and sessions for DATABASE_FILE (SQLite;
DATABASE_URL overrides it) and how a session takes SQLite's write lock, the
UTC timestamp and plain date column types, and the startup step that
migrates the schema and seeds the default login and the six fixed accounts.
Everything persistent lives in DATABASE_FILE's directory
(docs/STARTOS_COMPATIBILITY.md).
"""

import os
import logging
import datetime
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated
from dotenv import load_dotenv
import sqlite3

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import Pool, StaticPool
from sqlalchemy.types import TypeDecorator, String
import bcrypt
from pydantic import Field


def log_level_from_env() -> int:
    """LOG_LEVEL env (DEBUG, INFO, WARNING, ERROR, CRITICAL); INFO if unset or unknown."""
    name = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    level = logging.getLevelName(name)
    return level if isinstance(level, int) else logging.INFO


logging.basicConfig(level=log_level_from_env())
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

dotenv_path = os.path.join(PROJECT_ROOT, ".env")
load_dotenv(dotenv_path=dotenv_path)
logger.debug(f"Loaded .env from: {dotenv_path}")

DATABASE_FILE_ENV = os.getenv("DATABASE_FILE", "backend/bitcoin_tracker.db")
DATABASE_FILE = (
    DATABASE_FILE_ENV if os.path.isabs(DATABASE_FILE_ENV)
    else os.path.join(PROJECT_ROOT, DATABASE_FILE_ENV)
)

db_dir = os.path.dirname(DATABASE_FILE)
if not os.path.exists(db_dir):
    os.makedirs(db_dir)
    logger.debug(f"Created directory: {db_dir}")

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_FILE}")
logger.debug(f"DATABASE_URL: {DATABASE_URL}")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}  # sessions move between FastAPI's worker threads
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


@event.listens_for(Engine, "connect")
def _erase_deleted_data(dbapi_connection, _record):
    """Every SQLite connection overwrites what it deletes: a deleted
    transaction doesn't stay readable in the file (or in copies of it)."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.execute("PRAGMA secure_delete = ON")


@event.listens_for(Pool, "reset")
def _end_what_a_failed_commit_left_open(dbapi_connection, _record, reset_state):
    """
    Every SQLite connection goes back to the pool with no transaction open.
    A COMMIT that waited past the 5 s for a reader fails ("database is
    locked") and leaves its changes open, and SQLAlchemy, counting the
    transaction as ended, skips its own rollback there: the next request
    on that connection would save them with its own (a transaction answered
    busy, saved twice after "Try again"; a Delete All finished later), and
    they'd hold SQLite's lock meanwhile (#580's re-check). A rollback that
    fails makes SQLAlchemy close the connection, which ends it too.
    """
    if (not reset_state.terminate_only and isinstance(dbapi_connection, sqlite3.Connection)
            and dbapi_connection.in_transaction):
        dbapi_connection.rollback()


class UTCDateTime(TypeDecorator):
    """
    A datetime stored in SQLite as an ISO 8601 string in UTC ('Z'), and read
    back offset-aware; a naive value is taken as UTC.
    """
    cache_ok = True
    impl = String

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=datetime.timezone.utc)
        return value.isoformat().replace("+00:00", "Z")

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        value = value.replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(value)


class PlainDate(TypeDecorator):
    """
    A calendar date with no time or timezone, stored as 'YYYY-MM-DD' (#185):
    a date the owner typed reads back as that date whatever the tax
    timezone becomes. A datetime is refused: the caller decides its date.
    """
    cache_ok = True
    impl = String

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, datetime.datetime) or not isinstance(value, datetime.date):
            raise TypeError(f"PlainDate takes a date, not {type(value).__name__}")
        return value.isoformat()

    def process_result_value(self, value, dialect):
        return None if value is None else datetime.date.fromisoformat(value)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def scratch_copy(db: Session) -> Iterator[Session]:
    """
    A throwaway in-memory copy of the database, as committed. A replay run
    on it (a report's start- and end-of-year holdings, Ledger Review's dry
    run, #335) never rewrites the real ledger or holds its write lock, so a
    save made meanwhile goes through; making the copy only reads.
    """
    memory = sqlite3.connect(":memory:", check_same_thread=False)
    try:
        raw = db.get_bind().raw_connection()
        try:
            raw.driver_connection.backup(memory)
        finally:
            raw.close()
        engine = create_engine("sqlite://", creator=lambda: memory, poolclass=StaticPool)
        try:
            scratch = Session(bind=engine)
            scratch.info[SCRATCH] = True
            try:
                yield scratch
            finally:
                scratch.close()
        finally:
            engine.dispose()
    finally:
        memory.close()


# Session.info key: a scratch copy's session (scratch_copy), whose writes are
# thrown away with it
SCRATCH = "btctx_scratch_copy"

# An id a request sends, a whole number SQLite's INTEGER holds (64-bit):
# one beyond it is a 422 naming it, never bound into a query, where it
# raised OverflowError and answered 500 (#744)
RowId = Annotated[int, Field(ge=-(2 ** 63), le=2 ** 63 - 1)]

# Where services/account.py keeps a session's account book (Session.info)
ACCOUNT_BOOK = "account_book"


def take_write_lock(db: Session) -> bool:
    """
    SQLite's write lock for db's transaction, until its commit or rollback,
    for a step that must see the ledger unchanged until it saves (Delete
    All, the hourly prices' apply, a login's timezone fill): other saves
    wait for it, 5 s at most (sqlite3's timeout), then fail. False, nothing
    taken, when another save held it longer; the caller answers that in its
    own words. A session that has a transaction open already fails here,
    loudly.
    """
    try:
        db.execute(text("BEGIN IMMEDIATE"))
    except OperationalError as e:
        if not is_busy(e):
            raise
        return False
    # A book read before the lock (pysqlite begins no transaction on a
    # read) may be out of date: it is read again under the lock
    db.info.pop(ACCOUNT_BOOK, None)
    return True


def is_busy(error: Exception) -> bool:
    """Whether SQLite's write lock was held past the 5 s wait: SQLite's own
    message ("database is locked"), never a query's parameters, says so."""
    return isinstance(error, OperationalError) and "locked" in str(error.orig)


def was_replaced(error: Exception) -> bool:
    """Whether a save was refused because a restore replaced the database
    file it was writing to (it waited for the restore's lock): SQLite writes
    nothing to a file that has been replaced. Python 3.11+ names SQLite's
    code; on 3.10 it's an error like any other."""
    return (isinstance(error, OperationalError)
            and getattr(error.orig, "sqlite_errorname", None) == "SQLITE_READONLY_DBMOVED")


# The six fixed accounts, with their 1.x names, kinds and exchange (2.0
# spec 5.1, 5.2). Exchange 1's two accounts are named after it.
FIXED_ACCOUNTS = [
    {"id": 1, "name": "Bank", "currency": "USD", "kind": "bank", "exchange_id": None},
    {"id": 2, "name": "Wallet", "currency": "BTC", "kind": "wallet", "exchange_id": None},
    {"id": 3, "name": "Exchange USD", "currency": "USD", "kind": "exchange", "exchange_id": 1},
    {"id": 4, "name": "Exchange BTC", "currency": "BTC", "kind": "exchange", "exchange_id": 1},
    {"id": 5, "name": "BTC Fees", "currency": "BTC", "kind": "fee", "exchange_id": None},
    {"id": 6, "name": "USD Fees", "currency": "USD", "kind": "fee", "exchange_id": None},
]
FIRST_EXCHANGE = {"id": 1, "name": "Exchange"}
# Ids whose name is the owner's to change (2.0 spec 5.1, Q2): a start puts
# back only 5's and 6's
RENAMEABLE_FIXED = (1, 2, 3, 4)


def seed_defaults(bind=None) -> None:
    """
    Default user 'admin' / 'password' (only if no user exists), exchange 1,
    and the six fixed accounts (IDs 1-6), tied to the first user, each with
    its currency, kind and exchange; 5 and 6 with their names too, while
    1-4 keep the names given them (2.0 spec 5.2). A missing one is made with
    its 1.x name (3 and 4 named after exchange 1); the list of rows from
    before 0.9.2, once (services/old_rows.py). Idempotent.
    """
    from backend.models.user import User
    from backend.models.account import Account
    from backend.models.exchange import Exchange
    from backend.services import old_rows

    db = sessionmaker(bind=bind or engine)()
    try:
        user = db.query(User).order_by(User.id).first()
        if not user:
            logger.info("No user found. Inserting default user: admin")
            user = User(
                username="admin",
                password_hash=bcrypt.hashpw(b"password", bcrypt.gensalt()).decode("utf-8"),
            )
            db.add(user)
            db.flush()

        exchange = db.get(Exchange, FIRST_EXCHANGE["id"])
        if not exchange:
            exchange = Exchange(**FIRST_EXCHANGE)
            db.add(exchange)
            db.flush()
        for acct in FIXED_ACCOUNTS:
            existing = db.get(Account, acct["id"])
            if existing:
                for key in ("currency", "kind", "exchange_id"):
                    setattr(existing, key, acct[key])
                if acct["id"] not in RENAMEABLE_FIXED:
                    existing.name = acct["name"]
                existing.user_id = user.id
            else:
                name = f"{exchange.name} {acct['currency']}" if acct["exchange_id"] else acct["name"]
                db.add(Account(user_id=user.id, **{**acct, "name": name}))
        old_rows.note_once(db)
        db.commit()

        found_ids = {a.id for a in db.query(Account).all()}
        if missing := {a["id"] for a in FIXED_ACCOUNTS} - found_ids:
            raise RuntimeError(f"Missing required account IDs: {missing}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db(bind=None):
    """
    Startup: the rollback journal, then bring the schema up to date with
    migrations (backing the file up first when there is something to
    migrate), then seed defaults.
    Never uses create_all(): the migrations in backend/migrations/ are the
    only thing that creates or changes tables.
    """
    from backend.migrate import upgrade_database

    use_rollback_journal(bind or engine)
    result = upgrade_database(bind or engine)
    seed_defaults(bind)
    _make_owner_only(bind or engine)
    logger.info("Database ready (schema %s).", result.to_revision)
    return result


def use_rollback_journal(bind) -> None:
    """
    A database an earlier version's restore left in write-ahead-log mode
    goes back to SQLite's rollback journal, the mode BitcoinTX makes its
    databases in: in it, SQLite refuses a save that waited while a restore
    replaced the file (services/backup._swap), where the log would take the
    save into the file replaced. It needs the database to itself, as at the
    start; if something else has it open, it stays as it is for now (a
    restore tries again, and stops while it stays so). The file's header
    says which mode it's in, read without waiting for any lock.
    """
    path = getattr(getattr(bind, "url", None), "database", None)
    if not isinstance(bind, Engine) or bind.dialect.name != "sqlite" or not path or path == ":memory:":
        return
    if not _in_write_ahead_log_mode(path):
        return
    bind.dispose()  # its own idle connections would keep the log open
    try:
        with bind.connect() as conn:
            mode = conn.exec_driver_sql("PRAGMA journal_mode = DELETE").scalar()
        logger.info("The database's journal mode is now %s (it was wal).", mode)
    except OperationalError as e:
        if not is_busy(e):  # a database that can't be opened stops the start, as the migrations did
            raise
        logger.warning("The database stays in write-ahead-log mode for now: something else has it open.")


def _in_write_ahead_log_mode(path: str) -> bool:
    """Whether SQLite opens a database file in write-ahead-log mode: its
    header says so (its format version bytes, 18 and 19, are 2 for it, 1
    for the rollback journal), or a log with writes in it lies beside it,
    which SQLite opens whatever the header says (an earlier version's
    restore could leave one). A file that can't be read: no, and the
    migrations say why."""
    try:
        with open(path, "rb") as f:
            header = f.read(20)[18:20]
    except OSError:
        return False
    return header == b"\x02\x02" or _log_size(path) > 0


def _log_size(path: str) -> int:
    try:
        return os.path.getsize(path + "-wal")
    except OSError:
        return 0


def _make_owner_only(bind) -> None:
    """The database holds the whole ledger: readable by its owner only
    (0600), like the secret key and the migration backups beside it. SQLite
    gives its journal files the database file's permissions."""
    path = getattr(getattr(bind, "url", None), "database", None)
    if not path or path == ":memory:" or not os.path.exists(path):
        return
    try:
        os.chmod(path, 0o600)
    except OSError as exc:  # e.g. a mounted volume that refuses chmod
        logger.warning("Couldn't make the database owner-only: %s", exc)


# The StartOS wrapper calls backend.database.create_tables() at install time
# (docs/STARTOS_COMPATIBILITY.md): keep this name.
create_tables = init_db
