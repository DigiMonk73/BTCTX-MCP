"""
Shared pytest fixtures for BTCTX test suite.

Uses FastAPI TestClient with an isolated temporary database so tests
never touch the production database.
"""

import os
import pytest
import tempfile
from decimal import Decimal
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
# on the price sites being reachable (CI runners, offline laptops). Individual
# tests can still stub their own values on top (stub_daily_prices).
# Set BTCTX_LIVE_PRICES=1 to exercise the real price sites.
STUB_HISTORICAL_USD = 50000.0
STUB_CURRENT_USD = 60000.0


def price_finder(price_for):
    """
    A stand-in for price_history.find_prices: every missing day gets
    price_for(day) (a number, None for no price, or an exception to raise).
    """
    async def find_prices(day, full):
        usd = price_for(day)
        if usd is None:
            return {}, False
        return {day: (Decimal(str(usd)).quantize(Decimal("0.01")), "stub")}, False

    return find_prices


def stub_daily_prices(monkeypatch, price_for):
    monkeypatch.setattr("backend.services.price_history.find_prices", price_finder(price_for))


@pytest.fixture(autouse=True, scope="session")
def _stub_price_apis():
    if os.environ.get("BTCTX_LIVE_PRICES") == "1":
        yield
        return

    async def current():
        return {"USD": STUB_CURRENT_USD}

    import backend.services.bitcoin as bitcoin
    import backend.services.price_history as price_history

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(price_history, "find_prices", price_finder(lambda day: STUB_HISTORICAL_USD))
        mp.setattr(bitcoin, "get_current_price", current)
        yield


@pytest.fixture(autouse=True)
def _public_price_source():
    """
    Tests run with the public price source chosen (a fresh install has none
    until the owner picks) and with fresh download timers.
    """
    from backend.services import outbound, price_history

    saved = outbound._current
    outbound._current = outbound.NetworkSettings(price_source="public")
    price_history.reset_state()
    yield
    outbound._current = saved


@pytest.fixture(autouse=True)
def _empty_price_history(request):
    """Each test starts with no stored BTC prices, so a price a test stubs
    isn't hidden by one an earlier test stored for the same day."""
    if "test_engine" in request.fixturenames:
        from sqlalchemy import text

        with request.getfixturevalue("test_engine").begin() as con:
            con.execute(text("DELETE FROM btc_price_daily"))
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


@pytest.fixture
def ai_key_headers(auth_client):
    """
    An AI key made the Docker/StartOS way (Settings, logged in) with AI access
    on, as request headers; revoked and switched off afterwards.
    """
    assert auth_client.put("/api/settings/ai-access", json={"on": True}).status_code == 200
    r = auth_client.post("/api/settings/ai-key")
    assert r.status_code == 200, r.text
    yield {"Authorization": f"Bearer {r.json()['key']}"}
    auth_client.delete("/api/settings/ai-key")
    auth_client.put("/api/settings/ai-access", json={"on": False})


@pytest.fixture(scope="session")
def test_db(test_engine):
    """Direct SQLAlchemy session for tests that need DB access."""
    TestSessionLocal = sessionmaker(bind=test_engine)
    db = TestSessionLocal()
    yield db
    db.close()
