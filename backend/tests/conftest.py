"""
Shared pytest fixtures for BTCTX test suite.

Uses FastAPI TestClient with an isolated temporary database so tests
never touch the production database.
"""

import os
import pytest
import tempfile
import bcrypt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from backend.database import Base, get_db
from backend.main import app

# Import all models so Base.metadata knows about them
from backend.models.user import User          # noqa: F401
from backend.models.account import Account    # noqa: F401
from backend.models.transaction import (      # noqa: F401
    Transaction, LedgerEntry, BitcoinLot, LotDisposal,
)

LOGIN_CREDS = {"username": "admin", "password": "password"}

# Deterministic BTC prices for the whole test session. Tests must never depend
# on CoinGecko/Kraken/CoinDesk being reachable (CI runners, offline laptops).
# Individual tests can still monkeypatch their own values on top.
# Set BTCTX_LIVE_PRICES=1 to exercise the real price APIs.
STUB_HISTORICAL_USD = 50000.0
STUB_CURRENT_USD = 60000.0


@pytest.fixture(autouse=True, scope="session")
def _stub_price_apis():
    if os.environ.get("BTCTX_LIVE_PRICES") == "1":
        yield
        return

    async def historical(date: str):
        return {"USD": STUB_HISTORICAL_USD}

    async def current():
        return {"USD": STUB_CURRENT_USD}

    import backend.services.bitcoin as bitcoin
    import backend.routers.river_import as river_router
    import backend.services.entry_import as entry_import

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(bitcoin, "get_historical_price", historical)
        mp.setattr(bitcoin, "get_current_price", current)
        # Modules that imported the function by name
        mp.setattr(river_router, "get_historical_price", historical)
        mp.setattr(entry_import, "get_historical_price", historical)
        yield


def _seed_test_db(engine):
    """Seed admin user and 6 core accounts (mirrors database.create_tables)."""
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        user = User(
            username="admin",
            password_hash=bcrypt.hashpw(b"password", bcrypt.gensalt()).decode("utf-8"),
        )
        db.add(user)
        db.flush()

        fixed_accounts = [
            {"id": 1, "name": "Bank", "currency": "USD"},
            {"id": 2, "name": "Wallet", "currency": "BTC"},
            {"id": 3, "name": "Exchange USD", "currency": "USD"},
            {"id": 4, "name": "Exchange BTC", "currency": "BTC"},
            {"id": 5, "name": "BTC Fees", "currency": "BTC"},
            {"id": 6, "name": "USD Fees", "currency": "USD"},
        ]
        for acct in fixed_accounts:
            db.add(Account(
                id=acct["id"],
                name=acct["name"],
                currency=acct["currency"],
                user_id=user.id,
            ))

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@pytest.fixture(scope="session")
def test_engine():
    """Create a temporary SQLite database for the entire test session."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_engine(
        f"sqlite:///{tmp.name}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    _seed_test_db(engine)
    yield engine
    engine.dispose()
    os.unlink(tmp.name)


@pytest.fixture(scope="session")
def auth_client(test_engine, _stub_price_apis):
    """Authenticated TestClient using an isolated test database."""
    TestSessionLocal = sessionmaker(bind=test_engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    r = client.post("/api/login", json=LOGIN_CREDS)
    assert r.status_code == 200, f"TestClient login failed: {r.status_code} {r.text}"
    yield client
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def test_db(test_engine):
    """Direct SQLAlchemy session for tests that need DB access."""
    TestSessionLocal = sessionmaker(bind=test_engine)
    db = TestSessionLocal()
    yield db
    db.close()
