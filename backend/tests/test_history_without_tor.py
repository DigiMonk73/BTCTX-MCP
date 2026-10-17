"""
#241, option 1 (the owner, 2026-10-16): through Tor, Bitstamp refuses
BitcoinTX's requests, so the price card asks once whether to download the
price history without Tor. Before a Yes nothing goes around the proxy;
after it only Bitstamp's fixed history blocks do (the hourly year files, the
hours after them, the daily history), and everything else, the live price
included, stays on Tor. The answer is login only, kept across restarts and
restores, and the owner's even while the server sets the price choice.
Every outside site is faked; each request carries the proxy it took
(outbound.PROXY_TAG).
"""

import asyncio
import threading
from datetime import date, datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from backend.services import bitcoin, outbound, price_status
from backend.services import hourly_prices as hp
from backend.services import price_files as pf
from backend.services import price_history
from backend.tests.conftest import default_login, keep_in_use
from backend.tests.test_hourly_prices import FILES_END, NOW, finish_download, market

# The real functions, captured before the session fixture stubs them.
from backend.services.bitcoin import get_block_height as real_block_height
from backend.services.bitcoin import get_current_price as real_current_price
from backend.services.hourly_prices import find_hours as real_find_hours
from backend.services.hourly_prices import start_download as real_start_download
from backend.services.price_history import find_prices as real_find_prices

HOUR = pf.HOUR
DAY = 86400
TOR = "socks5h://127.0.0.1:9050"
ROUTE = "/api/settings/network/history-without-tor"
UNTAGGED = "a client outbound.py didn't build"
KEYS = ("price_source", "mempool_url", "mempool_fallback", "proxy_url", "price_choice_at", "price_choice_via",
        outbound.DIRECT_KEY, outbound.DIRECT_AT_KEY, outbound.DIRECT_VIA_KEY)
ASKED_HOUR = NOW - 5 * HOUR  # after the year files, not a block start
ASKED_DAY = date(2012, 5, 17)  # before the year files, not a block start


def day_price(d: date) -> int:
    return 5 + d.toordinal() % 1000


class TorWorld:
    """Public sites as Tor's exits and this server see them: Bitstamp refuses
    every request through the proxy (its 403 block page, #241) and answers
    directly; the others answer either way. Each request is recorded with
    the proxy it took (None: directly)."""

    def __init__(self, hours):
        self.hours = hours
        self.seen: list[tuple[str, str | None]] = []
        self.tor_down = False
        # Set: Bitstamp's answer through Tor waits for it (held is set while it waits)
        self.release: threading.Event | None = None
        self.held = threading.Event()

    def handler(self, request: httpx.Request) -> httpx.Response:
        proxy = request.extensions.get(outbound.PROXY_TAG, UNTAGGED)
        self.seen.append((str(request.url), proxy))
        url = request.url
        if proxy and self.tor_down:
            raise httpx.ConnectError("Tor isn't running")
        if url.host == "www.bitstamp.net":
            if proxy and self.release is not None:
                self.held.set()
                assert self.release.wait(10)
            if proxy:
                return httpx.Response(403, text="Request unsuccessful. Incapsula incident ID: 0-0")
            return self.bitstamp(url)
        if url.host == "api.kraken.com" and url.path.endswith("/Ticker"):
            return httpx.Response(200, json={"error": [], "result": {"XXBTZUSD": {"c": ["65000.10", "0.1"]}}})
        if url.host == "api.kraken.com":
            rows = [[NOW - k * DAY, "64000", "0", "0", "0", "0", "0", 1] for k in range(3)]
            return httpx.Response(200, json={"error": [], "result": {"XXBTZUSD": rows, "last": 0}})
        if url.host == "blockchain.info":
            return httpx.Response(200, text="912345")
        return httpx.Response(503)

    def bitstamp(self, url: httpx.URL) -> httpx.Response:
        params = url.params
        if url.path.endswith("/ticker/btcusd/"):
            return httpx.Response(200, json={"last": "65001"})
        step, start = int(params["step"]), int(params.get("start", NOW - 999 * HOUR))
        if step == HOUR:
            rows = [{"timestamp": str(h), "open": str(self.hours[h]), "volume": "1.5"}
                    for h in range(start, min(start + 1000 * HOUR, NOW + HOUR), HOUR) if h in self.hours]
        else:
            first = datetime.fromtimestamp(start, tz=timezone.utc).date()
            days = [date.fromordinal(first.toordinal() + k) for k in range(1000)]
            rows = [{"timestamp": str(int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())),
                     "open": str(day_price(d))} for d in days if d <= date.today()]
        return httpx.Response(200, json={"data": {"pair": "BTC/USD", "ohlc": rows}})

    def direct(self) -> list[str]:
        return [u for u, proxy in self.seen if proxy is None]

    def through_tor(self) -> list[str]:
        return [u for u, proxy in self.seen if proxy == TOR]


@pytest.fixture
def world(monkeypatch, tmp_path, test_engine):
    """The year files' manifest of test_hourly_prices (2025, and 2026 to 14
    March), an empty data folder, the real price code against TorWorld; the
    install's price settings and answer put back afterwards."""
    hours = market()
    lines = [pf.line_for(y, pf.year_text(hours, y, last)) for y, last in
             ((2025, pf.year_end(2025)), (2026, FILES_END))]
    manifest = tmp_path / "MANIFEST.csv"
    manifest.write_text(pf.manifest_text(lines), encoding="utf-8")
    fake = TorWorld(hours)
    for target, value in ((pf, {"MANIFEST": manifest, "FIRST_YEAR": 2025}),
                          (hp, {"DATA_DIR": str(tmp_path / "data"), "PAUSE_SECONDS": 0, "WAIT_SECONDS": 10,
                                "_current_hour": lambda: NOW, "find_hours": real_find_hours,
                                "start_download": real_start_download}),
                          (price_history, {"find_prices": real_find_prices}),
                          (bitcoin, {"get_current_price": real_current_price, "get_block_height": real_block_height}),
                          (outbound, {"_transport": httpx.MockTransport(fake.handler)})):
        for name, v in value.items():
            monkeypatch.setattr(target, name, v)
    with test_engine.begin() as conn:
        before = {k: conn.execute(text("SELECT value FROM app_settings WHERE key = :k"), {"k": k}).scalar()
                  for k in KEYS}
    _forget_downloads()
    yield fake
    finish_download()
    with test_engine.begin() as conn:
        for key, value in before.items():
            conn.execute(text("DELETE FROM app_settings WHERE key = :k"), {"k": key})
            if value is not None:
                conn.execute(text("INSERT INTO app_settings (key, value) VALUES (:k, :v)"), {"k": key, "v": value})
    with sessionmaker(bind=test_engine)() as db:
        outbound.load(db)
    _forget_downloads()


def _forget_downloads():
    hp.reset_state()
    price_history.reset_state()
    price_status.reset()
    bitcoin._price_cache.update(settings=None)
    bitcoin._height_cache.update(settings=None)


@pytest.fixture
def db(test_engine):
    with sessionmaker(bind=test_engine)() as session:
        yield session
        session.rollback()


def public_through_tor(client):
    r = client.put("/api/settings/network", json={
        "price_source": "public", "mempool_url": None, "mempool_fallback": False, "proxy_url": TOR})
    assert r.status_code == 200, r.text
    finish_download()  # saving the choice starts the year files' download


def year_starts() -> list[int]:
    return pf.block_starts(2026, FILES_END) + pf.block_starts(2025, pf.year_end(2025))


def daily_starts() -> list[int]:
    first = price_history.FIRST_PRICE_DAY
    return [int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
            for d in price_history._blocks(first, price_history.BITSTAMP_BLOCK)]


def everything_else(db) -> None:
    """The live price, the block height, the latest days, a newer hour and an
    older day: what a ledger can need once the year files are in."""
    asyncio.run(bitcoin.get_current_price())
    asyncio.run(bitcoin.get_block_height())
    asyncio.run(price_history.public_history(full=False))
    hp.hourly_price(db, datetime.fromtimestamp(ASKED_HOUR + 1500, tz=timezone.utc))
    try:
        price_history.daily_price(db, ASKED_DAY)
    except Exception:
        pass  # no price through Tor: a 422


def names_an_asked_moment(urls) -> bool:
    asked_day = int(datetime(ASKED_DAY.year, ASKED_DAY.month, ASKED_DAY.day, tzinfo=timezone.utc).timestamp())
    marks = {str(ASKED_HOUR), str(ASKED_HOUR + 1500), str(asked_day), ASKED_DAY.isoformat()}
    return any(m in u for u in urls for m in marks)


def test_bitstamps_refusal_through_tor_asks_and_nothing_goes_direct(world, auth_client, db):
    public_through_tor(auth_client)
    status = auth_client.get("/api/bitcoin/price/status").json()
    assert status["bitstamp_refused"] is True
    assert status["history"]["state"] == "failed" and status["history"]["refused"] is True
    assert auth_client.get("/api/settings/network").json()["history_without_tor"] == {
        "answer": None, "at": None, "via": None}
    everything_else(db)
    assert world.direct() == [] and UNTAGGED not in {p for _, p in world.seen}
    assert world.through_tor()  # each refused or answered through Tor


def test_no_keeps_everything_on_tor_and_the_question_answered(world, auth_client, db):
    public_through_tor(auth_client)
    r = auth_client.put(ROUTE, json={"answer": "no", "via": "dashboard"})
    assert r.status_code == 200
    record = r.json()["history_without_tor"]
    assert record["answer"] == "no" and record["via"] == "dashboard" and record["at"].endswith("Z")
    hp.reset_state()
    price_history.reset_state()
    assert hp.start_download()
    finish_download()
    everything_else(db)
    assert world.direct() == []
    assert hp.download_status()["without_tor"] is False


def test_yes_sends_only_bitstamps_fixed_blocks_directly(world, auth_client, db):
    """The owner's choice: the year files, the newer hours after them and the
    daily history go directly; the live price, the block height and the
    latest days stay on Tor. No request names an hour or a day asked."""
    public_through_tor(auth_client)
    world.seen.clear()
    r = auth_client.put(ROUTE, json={"answer": "yes", "via": "dashboard"})
    assert r.status_code == 200 and r.json()["history_without_tor"]["answer"] == "yes"
    finish_download()  # Yes asks again at once
    status = auth_client.get("/api/bitcoin/price/status").json()
    assert status["history"]["state"] == "complete" and status["history"]["without_tor"] is True
    assert status["bitstamp_refused"] is False  # answered: the question is gone

    db.execute(text("DELETE FROM app_settings WHERE key = :k"), {"k": price_history.HISTORY_FLAG})
    everything_else(db)
    assert hp.hourly_price(db, datetime.fromtimestamp(ASKED_HOUR, tz=timezone.utc)) == (
        world.hours[ASKED_HOUR], "bitstamp")
    assert price_history.daily_price(db, ASKED_DAY) == day_price(ASKED_DAY)

    direct = [httpx.URL(u) for u in world.direct()]
    assert all(u.host == "www.bitstamp.net" and u.path == "/api/v2/ohlc/btcusd/" for u in direct)
    assert all(outbound.fixed_block(str(u.copy_with(query=None)), {k: int(v) for k, v in u.params.items()})
               for u in direct)
    hourly = [int(u.params["start"]) for u in direct if u.params["step"] == str(HOUR)]
    daily = [int(u.params["start"]) for u in direct if u.params["step"] == str(DAY)]
    assert hourly == year_starts() + [FILES_END + HOUR]
    assert daily == daily_starts()
    tor_hosts = {httpx.URL(u).host for u in world.through_tor()}
    assert {"api.kraken.com", "blockchain.info", "www.bitstamp.net"} <= tor_hosts  # live, height, latest days
    assert not any("start=" in u for u in world.through_tor())  # every fixed block went direct
    assert not names_an_asked_moment(u for u, _ in world.seen)
    assert UNTAGGED not in {p for _, p in world.seen}


def test_a_yes_while_a_download_through_tor_runs_downloads_at_once(world, auth_client):
    """The review's 2: the Yes came while a block was on its way through Tor;
    its refusal then must not make the download wait 10 minutes."""
    world.release = threading.Event()
    r = auth_client.put("/api/settings/network", json={
        "price_source": "public", "mempool_url": None, "mempool_fallback": False, "proxy_url": TOR})
    assert r.status_code == 200
    assert world.held.wait(10)  # the first block is on its way through Tor
    assert auth_client.put(ROUTE, json={"answer": "yes", "via": "dashboard"}).status_code == 200
    world.release.set()  # Bitstamp's refusal arrives after the Yes
    finish_download()
    assert hp.download_status()["state"] == "complete"
    assert [int(httpx.URL(u).params["start"]) for u in world.direct()] == year_starts()


def test_a_tor_that_isnt_running_is_no_refusal(world, auth_client):
    """Tor down is not Bitstamp refusing: the card never offers to go around it."""
    world.tor_down = True
    public_through_tor(auth_client)
    status = auth_client.get("/api/bitcoin/price/status").json()
    assert status["history"]["state"] == "failed" and status["bitstamp_refused"] is False
    assert world.direct() == []


def test_no_takes_a_yes_back_and_a_yes_matters_only_with_tor(world, auth_client):
    public_through_tor(auth_client)
    auth_client.put(ROUTE, json={"answer": "yes"})
    finish_download()
    assert outbound.history_without_tor()
    auth_client.put(ROUTE, json={"answer": "no", "via": "settings"})
    assert not outbound.history_without_tor()  # the next block goes through Tor again
    auth_client.put(ROUTE, json={"answer": "yes"})
    finish_download()
    for choice in ({"price_source": "public", "proxy_url": None},  # no Tor: everything is direct anyway
                   {"price_source": "off", "proxy_url": TOR}):  # Nobody: nothing is asked at all
        assert auth_client.put("/api/settings/network", json={
            "mempool_url": None, "mempool_fallback": False, **choice}).status_code == 200
        finish_download()
        assert not outbound.history_without_tor()
        assert auth_client.get("/api/settings/network").json()["history_without_tor"]["answer"] == "yes"


@pytest.mark.parametrize("url, params", [
    (pf.BITSTAMP_OHLC_URL, {"step": DAY, "limit": 1000}),  # the latest days: no start
    (pf.BITSTAMP_OHLC_URL, {"step": HOUR, "limit": 1000, "start": FILES_END + 1800}),  # not on the hour
    (pf.BITSTAMP_OHLC_URL, {"step": DAY, "limit": 1000, "start": FILES_END}),  # 23:00, not midnight
    # On the hour, or at midnight, but not a block every install asks for: a ledger's hour or day (the review's 1)
    (pf.BITSTAMP_OHLC_URL, {"step": HOUR, "limit": 1000, "start": ASKED_HOUR}),
    (pf.BITSTAMP_OHLC_URL, {"step": HOUR, "limit": 1000, "start": pf.year_start(2025) + 5 * HOUR}),
    (pf.BITSTAMP_OHLC_URL, {"step": DAY, "limit": 1000, "start": int(datetime(2012, 5, 17, tzinfo=timezone.utc).timestamp())}),
    # On a year's grid, but a block no install asks for (the re-check's B): past the files, another year, far off
    (pf.BITSTAMP_OHLC_URL, {"step": HOUR, "limit": 1000, "start": pf.year_start(2026) + 2000 * HOUR}),
    (pf.BITSTAMP_OHLC_URL, {"step": HOUR, "limit": 1000, "start": pf.year_start(2024)}),
    (pf.BITSTAMP_OHLC_URL, {"step": HOUR, "limit": 1000, "start": pf.year_start(2027)}),
    (pf.BITSTAMP_OHLC_URL, {"step": HOUR, "limit": 1000, "start": 10 ** 15}),
    (pf.BITSTAMP_OHLC_URL, {"step": HOUR, "limit": 10, "start": FILES_END + HOUR}),
    (pf.BITSTAMP_OHLC_URL, {"step": HOUR, "limit": 1000, "start": str(FILES_END + HOUR)}),
    (pf.BITSTAMP_OHLC_URL, {"step": HOUR, "limit": 1000, "start": FILES_END + HOUR, "end": NOW}),
    (pf.BITSTAMP_OHLC_URL + "?start=0", None),
    ("https://www.bitstamp.net/api/v2/ticker/btcusd/", None),
    ("https://api.kraken.com/0/public/Ticker?pair=XBTUSD", None),
    ("https://api.kraken.com/0/public/OHLC", {"pair": "XBTUSD", "interval": 1440}),
])
def test_the_route_around_tor_takes_only_fixed_blocks(world, url, params):
    outbound._current = outbound.NetworkSettings(price_source="public", proxy_url=TOR, history_direct=True)

    async def ask():
        async with outbound.history_client() as client:
            await client.get(url, params=params)

    with pytest.raises(outbound.NotAFixedBlock):
        asyncio.run(ask())
    assert world.seen == []


def test_a_yes_taken_back_stops_the_next_direct_request(world):
    """The daily history reuses one client for its blocks: each request checks the Yes again."""
    outbound._current = outbound.NetworkSettings(price_source="public", proxy_url=TOR, history_direct=True)
    first, second = daily_starts()[:2]

    async def two_blocks():
        async with outbound.history_client() as client:
            await client.get(pf.BITSTAMP_OHLC_URL, params={"step": DAY, "limit": 1000, "start": first})
            outbound._current = outbound.NetworkSettings(price_source="public", proxy_url=TOR)  # No, meanwhile
            await client.get(pf.BITSTAMP_OHLC_URL, params={"step": DAY, "limit": 1000, "start": second})

    with pytest.raises(outbound.NotAFixedBlock):
        asyncio.run(two_blocks())
    assert [(httpx.URL(u).params["start"], p) for u, p in world.seen] == [(str(first), None)]


def test_every_block_the_app_asks_for_is_a_fixed_block():
    """The guard's grid is the callers' own: each year's blocks, the newer hours' and the daily history's."""
    lines = pf.read_manifest(pf.MANIFEST)
    hourly = [s for line in lines for s in pf.block_starts(line.year, line.last_hour)]
    hourly += [lines[-1].last_hour + HOUR + k * 1000 * HOUR for k in range(3)]
    for step, starts in ((HOUR, hourly), (DAY, daily_starts())):
        assert all(outbound.fixed_block(pf.BITSTAMP_OHLC_URL, {"step": step, "limit": 1000, "start": s})
                   for s in starts), step


def test_the_answer_is_login_only_and_checked(world, auth_client, ai_key_headers):
    anonymous = TestClient(auth_client.app)
    assert anonymous.put(ROUTE, json={"answer": "yes"}).status_code == 401
    assert TestClient(auth_client.app).put(ROUTE, json={"answer": "yes"}, headers=ai_key_headers).status_code == 403
    for bad in ({}, {"answer": "maybe"}, {"answer": True}, {"answer": "yes", "via": "ai"}):
        assert auth_client.put(ROUTE, json=bad).status_code == 422, bad
    assert auth_client.get("/api/settings/network").json()["history_without_tor"]["answer"] is None


def test_the_answer_survives_a_restart_and_a_restore(world, auth_client, test_engine, monkeypatch):
    from backend.routers import backup

    public_through_tor(auth_client)
    auth_client.put(ROUTE, json={"answer": "yes", "via": "settings"})
    finish_download()
    outbound._current = outbound.NetworkSettings()  # as a fresh process starts
    with sessionmaker(bind=test_engine)() as db:
        outbound.load(db)
    assert outbound.current().history_direct and outbound.history_without_tor()
    record = auth_client.get("/api/settings/network").json()["history_without_tor"]
    assert (record["answer"], record["via"]) == ("yes", "settings")

    def restore_old_backup(password, path, carry_over):  # a backup from before the answer
        with test_engine.begin() as conn:
            conn.execute(text("DELETE FROM app_settings WHERE key LIKE 'history_without_tor%'"))
        keep_in_use(test_engine, carry_over)

    monkeypatch.setattr(backup, "restore_backup", restore_old_backup)
    r = auth_client.post("/api/backup/restore", data={"password": "pw"}, files={"file": ("b.btx", b"x")})
    assert r.status_code == 200, r.text
    assert auth_client.post("/api/login", json=default_login()).status_code == 200
    assert auth_client.get("/api/settings/network").json()["history_without_tor"] == record
    assert outbound.history_without_tor()


def test_the_answer_is_the_owners_while_the_server_sets_tor(world, auth_client, monkeypatch, test_engine):
    """StartOS's action sets Public price sites with Use Tor: the card is
    read-only, but the answer stays the owner's to give and change."""
    for key, value in (("BTCTX_PRICE_SOURCE", "public"), ("BTCTX_MEMPOOL_FALLBACK", "off"),
                       ("BTCTX_PROXY_URL", TOR), ("BTCTX_HOST", "startos")):
        monkeypatch.setenv(key, value)
    with sessionmaker(bind=test_engine)() as db:
        outbound.load(db)
    try:
        r = auth_client.put(ROUTE, json={"answer": "yes", "via": "dashboard"})
        assert r.status_code == 200
        assert r.json()["managed"] is True and r.json()["history_without_tor"]["answer"] == "yes"
        assert outbound.history_without_tor()
        finish_download()
        assert world.direct() and all("ohlc" in u for u in world.direct())
        assert auth_client.put("/api/settings/network", json={
            "price_source": "off", "proxy_url": None}).status_code == 409  # the choice stays the server's
    finally:
        for key in ("BTCTX_PRICE_SOURCE", "BTCTX_MEMPOOL_FALLBACK", "BTCTX_PROXY_URL", "BTCTX_HOST"):
            monkeypatch.delenv(key)
