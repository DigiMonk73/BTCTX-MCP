#!/usr/bin/env python
"""
backend/database.py

Sets up the SQLAlchemy database connection, session management, and helper functions for creating tables.
This file underpins the BitcoinTX double-entry system by ensuring all models (e.g., LedgerEntry, BitcoinLot, LotDisposal)
are registered with the ORM and created in the database.

Key Features:
- Loads environment variables from .env at project root
- Handles default SQLite or custom DB URLs
- Provides get_db() for FastAPI dependency injection
- Ensures six hardcoded accounts (IDs 1–6) are always present
- Automatically inserts default user: admin / password (bcrypt-hashed)

Security Notes:
- Password hashed with bcrypt directly
- Works cleanly across dev, test, CI, Docker
"""

import os
import logging
import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.types import TypeDecorator, String
import bcrypt

# ------------------------------------------------------------------
# 0) Logging Setup
# ------------------------------------------------------------------
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# 1) Environment Setup
# ------------------------------------------------------------------
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

# ------------------------------------------------------------------
# 2) SQLAlchemy Engine and Session Setup
# ------------------------------------------------------------------
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}  # For SQLite
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ------------------------------------------------------------------
# 3) Custom UTC DateTime for SQLite
# ------------------------------------------------------------------
class UTCDateTime(TypeDecorator):
    cache_ok = True
    """
    Stores Python datetime objects as ISO8601 strings with 'Z' in SQLite,
    ensuring they are read back as offset-aware UTC datetimes.
    """
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

# ------------------------------------------------------------------
# 4) FastAPI Dependency Injection
# ------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------------------------------------------------------
# 5) Table Initialization + User + Account Seeding
# ------------------------------------------------------------------
def create_tables():
    """
    Always creates all database tables and inserts:
    - Default user 'admin' / 'password' (if none exists)
    - Six core accounts (IDs 1–6) tied to that user
    """
    logger.info("Creating database tables...")
    logger.debug("Starting create_tables()")

    # ✅ Ensure all models are imported so Base.metadata is aware of them
    from backend.models.user import User
    from backend.models.account import Account
    from backend.models.transaction import Transaction, LedgerEntry, BitcoinLot, LotDisposal  # noqa: F401
    from backend.models.app_setting import AppSetting  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.debug("Executed Base.metadata.create_all to create tables")

    db = SessionLocal()
    try:
        # ✅ Insert default user if no user exists
        user = db.query(User).first()
        if not user:
            logger.info("No user found. Inserting default user: admin")
            user = User(
                username="admin",
                password_hash=bcrypt.hashpw(b"password", bcrypt.gensalt()).decode('utf-8'),
            )
            db.add(user)
            db.flush()  # get user.id without commit yet
        else:
            logger.info(f"User already exists: {user.username}")

        user_id = user.id

        # ✅ Define six fixed accounts (IDs 1–6)
        fixed_accounts = [
            {"id": 1, "name": "Bank", "currency": "USD"},
            {"id": 2, "name": "Wallet", "currency": "BTC"},
            {"id": 3, "name": "Exchange USD", "currency": "USD"},
            {"id": 4, "name": "Exchange BTC", "currency": "BTC"},
            {"id": 5, "name": "BTC Fees", "currency": "BTC"},
            {"id": 6, "name": "USD Fees", "currency": "USD"},
        ]

        for acct in fixed_accounts:
            existing = db.query(Account).filter_by(id=acct["id"]).first()
            if existing:
                existing.name = acct["name"]
                existing.currency = acct["currency"]
                existing.user_id = user_id
                logger.debug(f"Updated account ID={acct['id']}")
            else:
                db.add(Account(
                    id=acct["id"],
                    name=acct["name"],
                    currency=acct["currency"],
                    user_id=user_id
                ))
                logger.debug(f"Inserted account ID={acct['id']}")

        db.commit()
        logger.info("Tables created and seed data committed.")

        # ✅ Final check
        found_ids = {acct.id for acct in db.query(Account).all()}
        expected_ids = {1, 2, 3, 4, 5, 6}
        if missing := expected_ids - found_ids:
            raise RuntimeError(f"Missing required account IDs: {missing}")
    except Exception as e:
        db.rollback()
        logger.error(f"create_tables failed: {e}")
        raise
    finally:
        db.close()
        logger.debug("Closed session in create_tables")

    logger.info("Database initialized.")
