"""
Settings -> Privacy & network (v1.1.0, owner decision 2026-09-27): a fresh
install asks nothing until the owner chooses a price source (off, public
sites, or their own mempool server, optionally falling back to the public
sites); older installs keep what they did; a proxy (e.g. Tor) carries every
request to a public site, and the own mempool server is reached directly
unless it's an .onion. services/outbound.py is the only place HTTP clients
for outside services are made.
"""

import ast
import re
import asyncio
import tempfile
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import backend.services.price_history as price_history
from backend.services import bitcoin, outbound
from backend.tests.conftest import init_test_db

# The real functions, captured before the session fixture stubs them.
from backend.services.bitcoin import get_block_height as real_block_height
from backend.services.bitcoin import get_current_price as real_current_price
from backend.services.price_history import find_prices as real_find_prices

BACKEND = Path(__file__).resolve().parents[1]
NODE = "http://umbrel.local:3006"
BRIDGE = "http://10.0.3.1:32768"  # a StartOS bridge address to Mempool
PUBLIC = {"price_source": "public", "mempool_url": None, "mempool_fallback": False, "proxy_url": None}


@pytest.fixture(autouse=True)
def defaults_after(auth_client):
    yield
    auth_client.put("/api/settings/network", json=PUBLIC)
    bitcoin._price_cache.update(settings=None)
    bitcoin._height_cache.update(settings=None)


@pytest.fixture
def real_network_code(monkeypatch):
    monkeypatch.setattr("backend.services.bitcoin.get_current_price", real_current_price)
    monkeypatch.setattr("backend.services.bitcoin.get_block_height", real_block_height)
    monkeypatch.setattr(price_history, "find_prices", real_find_prices)
    bitcoin._price_cache.update(settings=None)
    bitcoin._height_cache.update(settings=None)


NODE_UP = {"up": True}


@pytest.fixture
def requests_seen(monkeypatch, real_network_code):
    """Every outside request, answered by a fake mempool server (while up) only."""
    seen = []
    NODE_UP["up"] = True

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen.append(url)
        if NODE_UP["up"] and any(url.startswith(n + "/api/v1/prices") for n in (NODE, BRIDGE)):
            return httpx.Response(200, json={"time": 1, "USD": 61234})
        if NODE_UP["up"] and any(url.startswith(n + "/api/blocks/tip/height") for n in (NODE, BRIDGE)):
            return httpx.Response(200, text="912345")
        return httpx.Response(503)

    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(handler))
    return seen


def node_down():
    NODE_UP["up"] = False


def fresh_db(**settings) -> sessionmaker:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    engine = create_engine(f"sqlite:///{tmp.name}")
    init_test_db(engine)
    with engine.begin() as con:
        for key, value in settings.items():
            con.execute(text("INSERT INTO app_settings (key, value) VALUES (:k, :v)"), {"k": key, "v": value})
    return sessionmaker(bind=engine)


def test_a_fresh_install_asks_nothing_until_the_owner_chooses():
    with fresh_db()() as db:
        assert outbound.load(db).price_source == "unset"
        assert not outbound.current().public_allowed and outbound.current().own_node is None


@pytest.mark.parametrize("old, expected", [
    ({"live_data": "off"}, ("off", False)),
    ({"live_data": "on"}, ("public", False)),
    ({"live_data": "on", "mempool_url": NODE}, ("mempool", True)),
    ({"live_data": "off", "mempool_url": NODE}, ("mempool", False)),
    ({"mempool_url": NODE}, ("mempool", True)),
])
def test_older_installs_keep_what_they_did(old, expected):
    Session = fresh_db(**old)
    with Session() as db:
        s = outbound.load(db)
        assert (s.price_source, s.mempool_fallback) == expected
    with Session() as db:  # written once, the old key gone
        assert db.execute(text("SELECT value FROM app_settings WHERE key='price_source'")).scalar() == expected[0]
        assert db.execute(text("SELECT count(*) FROM app_settings WHERE key='live_data'")).scalar() == 0


def _add_entry(db):
    db.execute(text(
        "INSERT INTO transactions (type, timestamp, amount, from_account_id, to_account_id, fee_amount, "
        "fee_currency) VALUES ('Deposit', '2024-01-01 00:00:00', 1, 99, 1, 0, 'USD')"))
    db.commit()


def test_an_older_install_that_never_touched_the_settings_keeps_public_prices():
    """Before v1.1.0, public sites were on by default and every downloaded
    day was stored: stored prices show the install used them."""
    Session = fresh_db()
    with Session() as db:
        _add_entry(db)
        db.execute(text("INSERT INTO btc_price_daily (day, usd, source) VALUES ('2024-01-01', 42000, 'bitstamp')"))
        db.commit()
        assert outbound.load(db).price_source == "public"


def test_entries_made_before_choosing_never_turn_public_sites_on():
    """Found on a StartOS VM (2026-09-28): a v1.1.0 install with entries but no
    price choice yet was switched to public sites at its next restart (the
    1.2.0 update), and asked CoinGecko. It stays unset: the owner is asked."""
    Session = fresh_db()
    with Session() as db:
        _add_entry(db)
        assert outbound.load(db).price_source == "unset"
    with Session() as db:  # the next restart
        assert outbound.load(db).price_source == "unset"
        assert not outbound.current().public_allowed
        assert db.execute(text("SELECT count(*) FROM app_settings WHERE key='price_source'")).scalar() == 0


def test_changing_them_is_login_only_and_checked(auth_client, ai_key_headers):
    r = TestClient(auth_client.app).put("/api/settings/network", json={"price_source": "off"},
                                        headers=ai_key_headers)
    assert r.status_code == 403
    for bad in ({"price_source": "public", "proxy_url": "ftp://x:1"},
                {"price_source": "public", "proxy_url": "socks5h://user:pw@127.0.0.1:9050"},
                {"price_source": "mempool", "mempool_url": "umbrel.local"},
                {"price_source": "mempool"},  # no address
                {"price_source": "unset"}, {}):
        assert auth_client.put("/api/settings/network", json=bad).status_code == 422, bad
    r = auth_client.put("/api/settings/network", json={
        "price_source": "mempool", "mempool_url": NODE + "/", "mempool_fallback": True,
        "proxy_url": " socks5h://127.0.0.1:9050 "})
    assert r.status_code == 200
    assert r.json() == {"price_source": "mempool", "mempool_url": NODE, "mempool_fallback": True,
                        "proxy_url": "socks5h://127.0.0.1:9050", "managed": False}


def test_settings_survive_a_restart(auth_client, test_engine):
    auth_client.put("/api/settings/network", json={"price_source": "off", "proxy_url": "socks5h://127.0.0.1:9050"})
    outbound._current = outbound.NetworkSettings()  # as a fresh process starts
    with sessionmaker(bind=test_engine)() as db:
        outbound.load(db)
    assert outbound.current().price_source == "off"
    assert outbound.current().proxy_url == "socks5h://127.0.0.1:9050"


@pytest.mark.parametrize("source", ["off", "unset"])
def test_off_or_unchosen_asks_nobody(auth_client, requests_seen, source):
    if source == "off":
        auth_client.put("/api/settings/network", json={**PUBLIC, "price_source": "off"})
    else:
        outbound._current = outbound.NetworkSettings()
    for path in ("/api/bitcoin/price", "/api/bitcoin/blockheight"):
        r = auth_client.get(path)
        assert r.status_code == 503 and "Privacy & network" in r.json()["detail"], path
    r = auth_client.post("/api/transactions", json=dict(
        type="Deposit", timestamp="2023-03-03T12:00:00Z", from_account_id=99, to_account_id=2,
        amount="0.01", source="Income", fee_amount="0", fee_currency="BTC"))
    assert r.status_code == 422 and "2023-03-03" in r.text
    assert requests_seen == []


def test_off_still_uses_stored_prices(auth_client, requests_seen, test_engine):
    with sessionmaker(bind=test_engine)() as db:
        price_history._store(db, {price_history.date(2023, 3, 3): (price_history.Decimal("22400.00"), "test")})
        db.commit()
    auth_client.put("/api/settings/network", json={**PUBLIC, "price_source": "off"})
    r = auth_client.get("/api/bitcoin/price/history", params={"date": "2023-03-03"})
    assert r.status_code == 200 and r.json() == {"USD": 22400.0}
    assert requests_seen == []


def test_your_own_mempool_server_only(auth_client, requests_seen):
    auth_client.put("/api/settings/network", json={**PUBLIC, "price_source": "mempool", "mempool_url": NODE})
    assert auth_client.get("/api/bitcoin/price").json() == {"USD": 61234.0}
    assert auth_client.get("/api/bitcoin/blockheight").json() == {"height": 912345}
    assert requests_seen == [NODE + "/api/v1/prices", NODE + "/api/blocks/tip/height"]
    node_down()
    bitcoin._height_cache.update(settings=None)  # a minute later
    r = auth_client.get("/api/bitcoin/blockheight")
    # 502, an error: the owner chose a source and it failed. 503 means prices
    # are off by choice, which the Dashboard shows as "Prices off".
    assert r.status_code == 502 and "falling back to public price sites is off" in r.json()["detail"]
    assert all(u.startswith(NODE) for u in requests_seen)  # never a public site


def test_your_mempool_with_fallback_asks_the_public_sites_when_it_is_down(auth_client, requests_seen):
    auth_client.put("/api/settings/network", json={
        **PUBLIC, "price_source": "mempool", "mempool_url": NODE, "mempool_fallback": True})
    node_down()
    assert auth_client.get("/api/bitcoin/blockheight").status_code == 502  # asked, all "down"
    assert any("blockchain.info" in u for u in requests_seen)


def test_the_live_price_is_asked_once_a_minute(auth_client, requests_seen):
    auth_client.put("/api/settings/network", json={**PUBLIC, "price_source": "mempool", "mempool_url": NODE})
    for _ in range(5):
        assert auth_client.get("/api/bitcoin/price").json() == {"USD": 61234.0}
    assert requests_seen.count(NODE + "/api/v1/prices") == 1


def test_the_dashboard_and_sidebar_asking_at_once_make_one_request(auth_client, monkeypatch):
    """Both ask for the live price as a page loads; with an empty cache both
    requests went out (seen on StartOS: two per page load)."""
    asked = []

    async def slow_node(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        await asyncio.sleep(0.05)
        return httpx.Response(200, json={"time": 1, "USD": 61234})

    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(slow_node))
    auth_client.put("/api/settings/network", json={**PUBLIC, "price_source": "mempool", "mempool_url": NODE})
    bitcoin._price_cache.update(settings=None)

    async def page_load():
        return await asyncio.gather(real_current_price(), real_current_price())

    assert asyncio.run(page_load()) == [{"USD": 61234.0}, {"USD": 61234.0}]
    assert asked == [NODE + "/api/v1/prices"]


@pytest.mark.parametrize("proxy", [None, "socks5h://127.0.0.1:9050"])
def test_a_proxy_that_is_down_is_named(auth_client, monkeypatch, proxy):
    """Seen on StartOS with Tor stopped: every public request failed to
    connect, and the error said only "No public site answered"."""
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("All connection attempts failed")

    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(down))
    auth_client.put("/api/settings/network", json={**PUBLIC, "proxy_url": proxy})
    bitcoin._price_cache.update(settings=None)
    for call in (real_current_price, real_block_height):
        with pytest.raises(HTTPException) as e:
            asyncio.run(call())
        assert e.value.status_code == 502
        assert ("Tor, is it running?" in e.value.detail) == (proxy is not None), e.value.detail


def test_the_proxy_carries_public_requests_and_skips_a_local_mempool(auth_client, real_network_code, monkeypatch):
    made = []

    class Recording:
        def __init__(self, **kwargs):
            made.append(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, *a, **k):
            made[-1]["url"] = url
            raise httpx.ConnectError("offline in tests")

    monkeypatch.setattr(outbound.httpx, "AsyncClient", Recording)
    proxy = "socks5h://127.0.0.1:9050"
    auth_client.put("/api/settings/network", json={
        "price_source": "mempool", "mempool_url": NODE, "mempool_fallback": True, "proxy_url": proxy})
    for call in (bitcoin.get_current_price(), bitcoin.get_block_height()):
        with pytest.raises(HTTPException):
            asyncio.run(call)
    price_history.reset_state()
    assert asyncio.run(price_history.find_prices(price_history.date(2023, 3, 3), full=True)) == ({}, False)
    to_node = [m for m in made if m.get("url", "").startswith(NODE)]
    public = [m for m in made if not m.get("url", "").startswith(NODE)]
    assert to_node and all(m.get("proxy") is None for m in to_node)
    assert public and all(m.get("proxy") == proxy for m in public)

    made.clear()
    onion = "http://abcdefghijklmnop.onion"
    auth_client.put("/api/settings/network", json={
        "price_source": "mempool", "mempool_url": onion, "mempool_fallback": False, "proxy_url": proxy})
    with pytest.raises(HTTPException):
        asyncio.run(bitcoin.get_block_height())
    assert made and all(m.get("proxy") == proxy for m in made)


# ---------------------------------------------------------------------------
# Set by the server (v1.2.0): the StartOS package passes BTCTX_PRICE_SOURCE and
# co. from its Price Source & Privacy action; they win over Settings, which
# shows them read-only, and the stored settings come back once they're gone.
# ---------------------------------------------------------------------------
@pytest.fixture
def server_env(monkeypatch, test_engine):
    def set_env(**env):
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        with sessionmaker(bind=test_engine)() as db:
            return outbound.load(db)

    yield set_env
    outbound._current = outbound.NetworkSettings()  # before the autouse PUT


def test_the_server_settings_win_and_settings_shows_them_read_only(auth_client, server_env, test_engine):
    auth_client.put("/api/settings/network", json={**PUBLIC, "proxy_url": "socks5h://127.0.0.1:9050"})
    server_env(BTCTX_PRICE_SOURCE="mempool", BTCTX_MEMPOOL_URL=BRIDGE + "/", BTCTX_MEMPOOL_FALLBACK="off")
    assert auth_client.get("/api/settings/network").json() == {
        "price_source": "mempool", "mempool_url": BRIDGE, "mempool_fallback": False, "proxy_url": None,
        "managed": True}
    r = auth_client.put("/api/settings/network", json={**PUBLIC, "price_source": "off"})
    assert r.status_code == 409 and "Price Source & Privacy action" in r.json()["detail"]
    # The stored settings are untouched, and back once the server stops setting them
    server_env(BTCTX_PRICE_SOURCE="")
    assert outbound.current() == outbound.NetworkSettings(
        price_source="public", proxy_url="socks5h://127.0.0.1:9050")


@pytest.mark.parametrize("env", [
    {"BTCTX_PRICE_SOURCE": "coingecko"},
    {"BTCTX_PRICE_SOURCE": "public", "BTCTX_MEMPOOL_FALLBACK": "maybe"},
    {"BTCTX_PRICE_SOURCE": "public", "BTCTX_PROXY_URL": "ftp://x:1"},
    {"BTCTX_PRICE_SOURCE": "mempool", "BTCTX_MEMPOOL_URL": "umbrel.local"},
])
def test_invalid_server_settings_turn_lookups_off(auth_client, server_env, requests_seen, env):
    assert server_env(**env) == outbound.NetworkSettings(price_source="off", managed=True)
    r = auth_client.get("/api/bitcoin/blockheight")
    assert r.status_code == 503 and "Price lookups are off" in r.json()["detail"]
    assert requests_seen == []


def test_server_settings_accept_on_and_off_spellings(server_env):
    for word, on in (("on", True), ("TRUE", True), ("1", True), ("off", False), ("false", False), ("", False)):
        assert server_env(BTCTX_PRICE_SOURCE="Public", BTCTX_MEMPOOL_FALLBACK=word).mempool_fallback is on


def test_mempool_on_startos_through_the_bridge_address(auth_client, server_env, requests_seen):
    server_env(BTCTX_PRICE_SOURCE="mempool", BTCTX_MEMPOOL_URL=BRIDGE,
               BTCTX_PROXY_URL="socks5h://10.0.3.1:9050")
    assert auth_client.get("/api/bitcoin/blockheight").json() == {"height": 912345}
    assert requests_seen == [BRIDGE + "/api/blocks/tip/height"]


ONION = "http://mempoolabcdefghijklmnopqrstuvwxyz234567abcdefghijklmnop.onion"


def test_an_onion_mempool_address_needs_the_proxy(auth_client):
    """Privacy audit 2026-09-29 (1h): saved without a proxy, the .onion name
    went to the system's DNS resolver on every price lookup."""
    r = auth_client.put("/api/settings/network", json={**PUBLIC, "price_source": "mempool", "mempool_url": ONION})
    assert r.status_code == 422 and ".onion" in r.json()["detail"]
    r = auth_client.put("/api/settings/network", json={
        **PUBLIC, "price_source": "mempool", "mempool_url": ONION, "proxy_url": "socks5h://127.0.0.1:9050"})
    assert r.status_code == 200, r.text


def test_a_server_set_onion_without_a_proxy_is_never_asked(auth_client, server_env, requests_seen):
    server_env(BTCTX_PRICE_SOURCE="mempool", BTCTX_MEMPOOL_URL=ONION, BTCTX_PROXY_URL="")
    assert auth_client.get("/api/bitcoin/price").status_code == 502
    assert requests_seen == []


def test_mempool_chosen_on_startos_before_it_is_installed(auth_client, server_env, requests_seen):
    """StartOS passes no address while Mempool is missing: nothing is asked, and the reason says so."""
    server_env(BTCTX_PRICE_SOURCE="mempool", BTCTX_MEMPOOL_URL="")
    assert outbound.current().own_node is None
    r = auth_client.get("/api/bitcoin/blockheight")
    # VM test 2026-09-29 (F6): the Dashboard said "Prices off" for this; and
    # one pair of brackets, not "(… (on StartOS: …))".
    assert r.status_code == 502 and "install and start Mempool" in r.json()["detail"]
    assert "))" not in r.json()["detail"]
    r = auth_client.post("/api/transactions", json=dict(
        type="Deposit", timestamp="2023-03-03T12:00:00Z", from_account_id=99, to_account_id=2,
        amount="0.01", source="Income", fee_amount="0", fee_currency="BTC"))
    assert r.status_code == 422 and "install and start Mempool" in r.text
    assert requests_seen == []


# Not the app: the admin command that fetches a test install's IRS draft
# forms (outbound.py's docstring, docs/IRS_FORM_GENERATION.md)
OWN_REQUESTS_ALLOWED = {"services/reports/draft_forms.py"}


def test_no_other_module_makes_its_own_http_client():
    """Every outside request goes through services/outbound.py, so the
    settings above can't be bypassed. Review of #52: urllib.request
    (stdlib) wasn't caught."""
    offenders = []
    for path in BACKEND.rglob("*.py"):
        if "tests" in path.parts or path.name == "outbound.py":
            continue
        where = str(path.relative_to(BACKEND))
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("AsyncClient", "Client", "get", "post", "request") \
                    and isinstance(node.value, ast.Name) and node.value.id in ("httpx", "requests", "urllib"):
                offenders.append(f"{where}:{node.lineno} {node.value.id}.{node.attr}")
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] + [getattr(node, "module", None) or ""]
                if any(n.split(".")[0] in ("httpx", "requests", "aiohttp", "urllib3") or n.startswith("urllib.request")
                       or (getattr(node, "module", None) == "urllib" and n == "request") for n in names):
                    offenders.append(f"{where}:{node.lineno} imports {names}")
    assert [o for o in offenders if o.split(":")[0] not in OWN_REQUESTS_ALLOWED] == []
    assert {o.split(":")[0] for o in offenders} == OWN_REQUESTS_ALLOWED  # the exception is still needed


def test_the_startos_package_passes_the_names_the_app_reads():
    """startos/startos/priceSource.ts sets exactly these; a rename on one side would silently drop the choice."""
    package = (BACKEND.parent / "startos" / "startos" / "priceSource.ts").read_text()
    passed = set(re.findall(r"\b(BTCTX_[A-Z_]+)\b", package))
    assert passed == {outbound.ENV_SOURCE, outbound.ENV_FALLBACK, outbound.ENV_MEMPOOL, outbound.ENV_PROXY}
    for source in ("off", "public", "mempool"):
        assert source in outbound.SOURCES and f"'{source}'" in package


def test_the_live_price_asks_kraken_first(auth_client, monkeypatch):
    """Privacy audit 2026-09-29 (1k), owner decision: CoinGecko was asked
    first and refuses VPN and Tor users, so each refresh contacted two
    sites. Kraken first; CoinGecko only when Kraken fails."""
    asked = []

    def sites(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.host)
        if request.url.host == "api.kraken.com" and "kraken-down" in asked_mode:
            return httpx.Response(503)
        if request.url.host == "api.kraken.com":
            return httpx.Response(200, json={"error": [], "result": {"XXBTZUSD": {"c": ["61000.5", "1"]}}})
        return httpx.Response(200, json={"bitcoin": {"usd": 60999}})

    asked_mode: list = []
    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(sites))
    auth_client.put("/api/settings/network", json=PUBLIC)
    bitcoin._price_cache.update(settings=None)
    assert asyncio.run(real_current_price()) == {"USD": 61000.5}
    assert asked == ["api.kraken.com"]

    asked.clear(); asked_mode.append("kraken-down")
    bitcoin._price_cache.update(settings=None)
    assert asyncio.run(real_current_price()) == {"USD": 60999.0}
    assert asked == ["api.kraken.com", "api.coingecko.com"]


def test_the_block_height_is_asked_at_most_once_a_minute(auth_client, requests_seen):
    """Privacy audit 2026-09-29 (1d): every Dashboard visit asked for it."""
    auth_client.put("/api/settings/network", json={**PUBLIC, "price_source": "mempool", "mempool_url": NODE})
    bitcoin._height_cache.update(settings=None)
    assert asyncio.run(real_block_height()) == {"height": 912345}
    assert asyncio.run(real_block_height()) == {"height": 912345}
    assert requests_seen == [NODE + "/api/blocks/tip/height"]
