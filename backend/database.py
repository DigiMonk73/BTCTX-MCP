#!/usr/bin/env python
"""
The database: the SQLAlchemy engine and sessions for DATABASE_FILE (SQLite;
DATABASE_URL overrides it), the UTC timestamp column type, and the startup
step that migrates the schema and seeds the default login and the six fixed
accounts. Everything persistent lives in DATABASE_FILE's directory
(docs/STARTOS_COMPATIBILITY.md).
"""

import os
import logging
import datetime
from dotenv import load_dotenv
import sqlite3

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.types import TypeDecorator, String
import bcrypt


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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

FIXED_ACCOUNTS = [
    {"id": 1, "name": "Bank", "currency": "USD"},
    {"id": 2, "name": "Wallet", "currency": "BTC"},
    {"id": 3, "name": "Exchange USD", "currency": "USD"},
    {"id": 4, "name": "Exchange BTC", "currency": "BTC"},
    {"id": 5, "name": "BTC Fees", "currency": "BTC"},
    {"id": 6, "name": "USD Fees", "currency": "USD"},
]


def seed_defaults(bind=None) -> None:
    """
    Default user 'admin' / 'password' (only if no user exists) and the six
    fixed accounts (IDs 1-6), tied to the first user. Idempotent.
    """
    from backend.models.user import User
    from backend.models.account import Account

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

        for acct in FIXED_ACCOUNTS:
            existing = db.get(Account, acct["id"])
            if existing:
                existing.name = acct["name"]
                existing.currency = acct["currency"]
                existing.user_id = user.id
            else:
                db.add(Account(user_id=user.id, **acct))
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
    Startup: bring the schema up to date with migrations (backing the file up
    first when there is something to migrate), then seed defaults.
    Never uses create_all(): the migrations in backend/migrations/ are the
    only thing that creates or changes tables.
    """
    from backend.migrate import upgrade_database

    result = upgrade_database(bind or engine)
    seed_defaults(bind)
    _make_owner_only(bind or engine)
    logger.info("Database ready (schema %s).", result.to_revision)
    return result


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
