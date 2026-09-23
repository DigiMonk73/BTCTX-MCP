"""
Shared pytest fixtures for BTCTX test suite.

Uses FastAPI TestClient with an isolated temporary database so tests
never touch the production database.
"""

import os
import pytest
import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from backend.database import get_db, seed_defaults
from backend.migrate import upgrade_database
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


def init_test_db(engine):
    """Build the schema with the real migrations (not create_all) and seed
    the default admin/password user and the six fixed accounts, exactly as a
    fresh install does at startup."""
    upgrade_database(engine, backup=False)
    seed_defaults(engine)


@pytest.fixture(scope="session")
def test_engine():
    """Create a temporary SQLite database for the entire test session."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_engine(
        f"sqlite:///{tmp.name}",
        connect_args={"check_same_thread": False},
    )
    init_test_db(engine)
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
