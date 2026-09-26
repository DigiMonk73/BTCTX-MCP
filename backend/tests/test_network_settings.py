"""
Settings -> Privacy & network (P2, owner decision 2026-09-26): public
services stay the default; live data can be turned off; your own mempool
server is asked first; a proxy (e.g. Tor) carries every outside request,
the bulk price-history download included. services/outbound.py is the only
place HTTP clients for outside services are made.
"""

import ast
import asyncio
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import backend.services.price_history as price_history
from backend.services import outbound

# The real functions, captured before the session fixture stubs them.
from backend.services.bitcoin import get_block_height as real_block_height
from backend.services.bitcoin import get_current_price as real_current_price
from backend.services.bitcoin import get_historical_price as real_single_day
from backend.services.price_history import fetch_range as real_fetch_range

BACKEND = Path(__file__).resolve().parents[1]
NODE = "http://umbrel.local:3006"


@pytest.fixture(autouse=True)
def defaults_after(auth_client):
    yield
    auth_client.put("/api/settings/network", json={"live_data": True, "mempool_url": None, "proxy_url": None})
    outbound._current = outbound.NetworkSettings()


@pytest.fixture
def real_network_code(monkeypatch):
    monkeypatch.setattr("backend.services.bitcoin.get_historical_price", real_single_day)
    monkeypatch.setattr("backend.services.bitcoin.get_current_price", real_current_price)
    monkeypatch.setattr("backend.services.bitcoin.get_block_height", real_block_height)
    monkeypatch.setattr(price_history, "fetch_range", real_fetch_range)


@pytest.fixture
def requests_seen(monkeypatch, real_network_code):
    """Every outside request, answered by a fake mempool server only."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if str(request.url).startswith(NODE + "/api/v1/prices"):
            return httpx.Response(200, json={"time": 1, "USD": 61234})
        if str(request.url).startswith(NODE + "/api/blocks/tip/height"):
            return httpx.Response(200, text="912345")
        return httpx.Response(503)

    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(handler))
    return seen


def test_defaults_are_todays_behavior(auth_client):
    assert auth_client.get("/api/settings/network").json() == {
        "live_data": True, "mempool_url": None, "proxy_url": None}


def test_changing_them_is_login_only_and_checked(auth_client, monkeypatch):
    monkeypatch.setattr("backend.main.API_KEY", "k" * 40)
    r = TestClient(auth_client.app).put("/api/settings/network", json={"live_data": False},
                                        headers={"X-API-Key": "k" * 40})
    assert r.status_code == 403
    for bad in ({"proxy_url": "ftp://x:1"}, {"proxy_url": "socks5h://user:pw@127.0.0.1:9050"},
                {"mempool_url": "umbrel.local"}):
        assert auth_client.put("/api/settings/network", json=bad).status_code == 422, bad
    r = auth_client.put("/api/settings/network", json={
        "live_data": False, "mempool_url": NODE + "/", "proxy_url": " socks5h://127.0.0.1:9050 "})
    assert r.status_code == 200
    assert r.json() == {"live_data": False, "mempool_url": NODE, "proxy_url": "socks5h://127.0.0.1:9050"}


def test_settings_survive_a_restart(auth_client, test_engine):
    auth_client.put("/api/settings/network", json={"live_data": False, "proxy_url": "socks5h://127.0.0.1:9050"})
    outbound._current = outbound.NetworkSettings()  # as a fresh process starts
    with sessionmaker(bind=test_engine)() as db:
        outbound.load(db)
    assert outbound.current().live_data is False
    assert outbound.current().proxy_url == "socks5h://127.0.0.1:9050"


def test_live_data_off_asks_no_public_service(auth_client, requests_seen):
    auth_client.put("/api/settings/network", json={"live_data": False})
    assert auth_client.get("/api/bitcoin/price").status_code == 503
    assert auth_client.get("/api/bitcoin/blockheight").status_code == 503
    assert auth_client.get("/api/bitcoin/price/history/timeseries").status_code == 503
    r = auth_client.get("/api/bitcoin/price/history", params={"date": "2023-03-03"})
    assert r.status_code == 422
    r = auth_client.post("/api/transactions", json=dict(
        type="Deposit", timestamp="2023-03-03T12:00:00Z", from_account_id=99, to_account_id=2,
        amount="0.01", source="Income", fee_amount="0", fee_currency="BTC"))
    assert r.status_code == 422 and "2023-03-03" in r.text
    assert requests_seen == []


def test_live_data_off_still_uses_stored_prices(auth_client, requests_seen, test_engine):
    with sessionmaker(bind=test_engine)() as db:
        price_history._store(db, {date(2023, 3, 3): (price_history.Decimal("22400.00"), "test")})
        db.commit()
    auth_client.put("/api/settings/network", json={"live_data": False})
    r = auth_client.get("/api/bitcoin/price/history", params={"date": "2023-03-03"})
    assert r.status_code == 200 and r.json() == {"USD": 22400.0}
    assert requests_seen == []


def test_your_own_mempool_server_is_asked_first_even_with_live_data_off(auth_client, requests_seen):
    auth_client.put("/api/settings/network", json={"live_data": False, "mempool_url": NODE})
    assert auth_client.get("/api/bitcoin/price").json() == {"USD": 61234.0}
    assert auth_client.get("/api/bitcoin/blockheight").json() == {"height": 912345}
    assert requests_seen == [NODE + "/api/v1/prices", NODE + "/api/blocks/tip/height"]


def test_the_proxy_carries_every_outside_request(auth_client, real_network_code, monkeypatch):
    """Live price, block height, the single-day lookup and the bulk
    price-history download all get a client with the proxy."""
    made = []

    class Recording:
        def __init__(self, **kwargs):
            made.append(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise httpx.ConnectError("offline in tests")

    auth_client.put("/api/settings/network", json={"proxy_url": "socks5h://127.0.0.1:9050", "mempool_url": NODE})
    monkeypatch.setattr(outbound.httpx, "AsyncClient", Recording)
    from backend.services import bitcoin

    for call in (bitcoin.get_current_price(), bitcoin.get_block_height(), bitcoin.get_historical_price("2023-03-03")):
        with pytest.raises(HTTPException):
            asyncio.run(call)
    assert asyncio.run(price_history.fetch_range(date(2023, 1, 1), date(2023, 2, 1))) == {}
    assert len(made) >= 6  # own node twice, public price, height, single day, bulk download
    assert all(kw.get("proxy") == "socks5h://127.0.0.1:9050" for kw in made), made


def test_no_other_module_makes_its_own_http_client():
    """Every outside request goes through services/outbound.py, so the
    settings above can't be bypassed."""
    offenders = []
    for path in BACKEND.rglob("*.py"):
        if "tests" in path.parts or path.name == "outbound.py":
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("AsyncClient", "Client", "get", "post") \
                    and isinstance(node.value, ast.Name) and node.value.id in ("httpx", "requests", "urllib"):
                offenders.append(f"{path.relative_to(BACKEND)}:{node.lineno} {node.value.id}.{node.attr}")
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] + [getattr(node, "module", None) or ""]
                if any(n.split(".")[0] in ("httpx", "requests", "aiohttp", "urllib3") for n in names):
                    offenders.append(f"{path.relative_to(BACKEND)}:{node.lineno} imports {names}")
    assert offenders == []
