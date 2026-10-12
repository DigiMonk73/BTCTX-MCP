"""
The BTC price when an hour began (#144, PR 2; services/hourly_prices.py):
- the hour is the moment's UTC hour, whatever the tax timezone;
- the year files come in the same fixed requests on every install, newest
  year first, and a year is used only when it gives its fingerprint;
- nothing is asked before a source is chosen, or when it's off, and the
  download stops if public sites stop being allowed;
- a stored hour wins; hours after the files come from the chosen source
  (a mempool server's live rows, Bitstamp's fixed blocks) and are stored;
- no hourly price: the day's, marked as such; a future hour: 422.
Every outside service is faked.
"""

import random
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from backend.models.btc_price import BtcPriceHourly
from backend.services import hourly_prices as hp
from backend.services import outbound
from backend.services import price_files as pf
from backend.services import price_history
from backend.tests.conftest import STUB_HISTORICAL_USD

# The real functions, captured before the session fixture stubs them.
from backend.services.hourly_prices import find_hours as real_find_hours
from backend.services.hourly_prices import start_download as real_start_download
from backend.services.price_history import find_prices as real_find_prices

HOUR = pf.HOUR
D = Decimal
NODE = "http://umbrel.local:3006"


def at(label: str) -> int:
    return pf.from_label(label)


def utc(moment: str) -> datetime:
    return datetime.fromisoformat(moment.replace("Z", "+00:00"))


NOW = at("2026-03-20T10:00Z")  # the current hour in these tests
FILES_END = at("2026-03-14T23:00Z")  # the manifest's last hour


def market() -> dict[int, Decimal]:
    rng, price, out = random.Random(5), 80000.0, {}
    for h in range(pf.year_start(2025), NOW + HOUR, HOUR):
        out[h] = D(f"{price:.2f}")
        price *= 1 + rng.gauss(0, 0.004)
    return out


class Sites:
    """Bitstamp (hourly candles) and a mempool server, faked; every request recorded."""

    def __init__(self, prices):
        self.bitstamp = dict(prices)
        self.volume = {h: "1.5" for h in prices}
        self.mempool = None
        self.bitstamp_down = False
        self.requests = []
        self.after_request = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        if self.after_request:
            self.after_request(self)
        if request.url.host == "www.bitstamp.net" and self.bitstamp_down:
            return httpx.Response(503)
        if request.url.host == "www.bitstamp.net":
            start = int(request.url.params["start"])
            rows = [{"timestamp": str(h), "open": str(self.bitstamp[h]), "volume": self.volume[h]}
                    for h in range(start, min(start + 1000 * HOUR, NOW + HOUR), HOUR) if h in self.bitstamp]
            return httpx.Response(200, json={"data": {"pair": "BTC/USD", "ohlc": rows}})
        if request.url.path == "/api/v1/historical-price" and self.mempool is not None:
            return httpx.Response(200, json={"prices": self.mempool, "exchangeRates": {}})
        return httpx.Response(503)

    def bitstamp_starts(self) -> list[int]:
        return [int(httpx.URL(u).params["start"]) for u in self.requests if "bitstamp" in u]


@pytest.fixture
def sites(monkeypatch, tmp_path):
    """A manifest of 2025 (closed) and 2026 to 14 March, as if 2025 were the
    first year; an empty data folder; the real lookups against fake sites."""
    prices = market()
    lines = [pf.line_for(y, pf.year_text(prices, y, last)) for y, last in
             ((2025, pf.year_end(2025)), (2026, FILES_END))]
    manifest = tmp_path / "MANIFEST.csv"
    manifest.write_text(pf.manifest_text(lines), encoding="utf-8")
    fake = Sites(prices)
    monkeypatch.setattr(pf, "MANIFEST", manifest)
    monkeypatch.setattr(pf, "FIRST_YEAR", 2025)
    monkeypatch.setattr(hp, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(hp, "PAUSE_SECONDS", 0)
    monkeypatch.setattr(hp, "WAIT_SECONDS", 10)
    monkeypatch.setattr(hp, "_current_hour", lambda: NOW)
    monkeypatch.setattr(hp, "find_hours", real_find_hours)
    monkeypatch.setattr(hp, "start_download", real_start_download)
    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(fake.handler))
    fake.prices = prices
    return fake


@pytest.fixture
def db(test_engine):
    with sessionmaker(bind=test_engine)() as session:
        yield session
        session.rollback()


def use(**settings):
    outbound._current = outbound.NetworkSettings(**settings)


def finish_download():
    with hp._changed:
        assert hp._changed.wait_for(lambda: not hp._state["running"], timeout=10)


def year_blocks(year: int, last: int) -> list[int]:
    return pf.block_starts(year, last)


@pytest.mark.parametrize("when, hour", [
    (datetime(2025, 3, 1, 9, 47, 12, tzinfo=timezone(timedelta(hours=-5))), "2025-03-01T14:00Z"),  # New York
    (datetime(2025, 5, 10, 19, 50, tzinfo=timezone(timedelta(hours=5, minutes=30))), "2025-05-10T14:00Z"),
    (datetime(2025, 12, 31, 23, 20, tzinfo=timezone(timedelta(hours=-5))), "2026-01-01T04:00Z"),
    (datetime(2025, 7, 4, 15, 0, 0), "2025-07-04T15:00Z"),  # naive is UTC; exactly on the hour
    (datetime(2025, 7, 4, 15, 59, 59, tzinfo=timezone.utc), "2025-07-04T15:00Z"),
])
def test_the_hour_is_the_moments_utc_hour_whatever_the_timezone(when, hour):
    assert hp.hour_of(when) == at(hour)


def test_the_year_files_come_in_fixed_blocks_newest_year_first_and_are_checked(sites, db):
    assert hp.start_download()
    finish_download()
    assert sites.bitstamp_starts() == year_blocks(2026, FILES_END) + year_blocks(2025, pf.year_end(2025))
    assert all(set(httpx.URL(u).params) == {"step", "limit", "start"} for u in sites.requests)
    for year in (2025, 2026):
        text = (hp.folder() / f"{year}.csv").read_text(encoding="utf-8")
        assert pf.fingerprint(text) == pf.read_manifest(pf.MANIFEST)[year - 2025].sha256
    sites.requests.clear()
    h = at("2025-06-01T13:00Z")
    assert hp.hourly_price(db, utc("2025-06-01T13:00Z") + timedelta(minutes=47)) == (sites.prices[h], "bitstamp")
    assert hp.price_at(db, utc("2025-06-01T13:59Z")) == hp.Priced(sites.prices[h], "hour", utc("2025-06-01T13:00Z"))
    assert sites.requests == []  # from the files: nothing asked
    assert not hp.start_download()  # every year here: nothing to do


def test_a_lookup_waits_for_its_years_download(sites, db):
    h = at("2025-02-02T02:00Z")
    assert hp.hourly_price(db, utc("2025-02-02T02:30Z")) == (sites.prices[h], "bitstamp")
    finish_download()
    # the same requests as any other install: every year, newest first
    assert sites.bitstamp_starts() == year_blocks(2026, FILES_END) + year_blocks(2025, pf.year_end(2025))


def test_a_year_that_doesnt_give_its_fingerprint_is_never_used(sites, db):
    sites.bitstamp[at("2025-08-08T08:00Z")] += D("0.01")
    hp.start_download()
    finish_download()
    assert not (hp.folder() / "2025.csv").exists() and (hp.folder() / "2026.csv").exists()
    priced = hp.price_at(db, utc("2025-08-08T08:15Z"))
    assert priced.moment == "day" and priced.usd == D(str(STUB_HISTORICAL_USD))
    assert priced.at == utc("2025-08-08T00:00Z")
    sites.requests.clear()
    hp.price_at(db, utc("2025-09-09T09:00Z"))
    assert sites.requests == []  # not asked again for a day (MISMATCH_RETRY_SECONDS)


@pytest.mark.parametrize("source", ["unset", "off", "mempool"])
def test_nothing_is_downloaded_unless_public_sites_are_allowed(sites, db, source):
    use(price_source=source, mempool_url=NODE if source == "mempool" else None)
    assert not hp.start_download()
    hp.download_if_public()
    assert hp.hourly_price(db, utc("2025-06-01T13:00Z")) is None
    assert sites.bitstamp_starts() == []


def test_the_download_stops_when_public_sites_stop_being_allowed(sites):
    def switch_off_after_2026(fake):
        if len(fake.bitstamp_starts()) == len(year_blocks(2026, FILES_END)):
            use(price_source="off")

    sites.after_request = switch_off_after_2026
    hp.start_download()
    finish_download()
    assert sites.bitstamp_starts() == year_blocks(2026, FILES_END)
    assert not (hp.folder() / "2025.csv").exists()


def test_public_sites_chosen_start_the_download_a_mempool_server_with_its_fallback_doesnt(
        sites, monkeypatch, auth_client):
    started = []
    monkeypatch.setattr(hp, "start_download", lambda: started.append(1) or True)
    r = auth_client.put("/api/settings/network", json={
        "price_source": "mempool", "mempool_url": NODE, "mempool_fallback": True, "proxy_url": None})
    assert r.status_code == 200 and started == []
    r = auth_client.put("/api/settings/network", json={
        "price_source": "public", "mempool_url": None, "mempool_fallback": False, "proxy_url": None})
    assert r.status_code == 200 and started == [1]


def test_a_stored_hour_wins_over_the_files(sites, db):
    hp.start_download()
    finish_download()
    h = at("2025-04-04T04:00Z")
    db.add(BtcPriceHourly(hour=h, usd=D("12345.67"), source="mempool"))
    db.flush()
    assert hp.hourly_price(db, utc("2025-04-04T04:30Z")) == (D("12345.67"), "mempool")


def test_hours_after_the_files_come_from_bitstamps_fixed_blocks_and_are_stored(sites, db):
    hp.start_download()
    finish_download()
    sites.requests.clear()
    sites.volume[NOW] = "0"  # no trade yet this hour: its open may still change
    h = at("2026-03-18T05:00Z")
    assert hp.hourly_price(db, utc("2026-03-18T05:20Z")) == (sites.prices[h], "bitstamp")
    assert sites.bitstamp_starts() == [FILES_END + HOUR]  # from the hour after the files, not the hour asked
    stored = {row.hour for row in db.query(BtcPriceHourly)}
    assert stored == set(range(FILES_END + HOUR, NOW, HOUR))
    sites.requests.clear()
    assert hp.hourly_price(db, utc("2026-03-19T23:59Z"))[0] == sites.prices[at("2026-03-19T23:00Z")]
    assert hp.price_at(db, utc("2026-03-20T10:05Z")).moment == "day"
    assert sites.requests == []  # stored, and asked at most every 10 minutes


def live_rows(first_live: int, until: int, spike: int | None = None) -> list[dict]:
    """A mempool server's history: weekly rows, then hourly from `first_live`."""
    rows = [{"time": t, "USD": 30000} for t in range(first_live - 400 * 86400, first_live, 7 * 86400)]
    for t in range(first_live, until + HOUR, HOUR):
        rows.append({"time": t, "USD": 70000 + (t // HOUR) % 7 + (5000 if t == spike else 0)})
    return rows


def test_a_mempool_servers_live_hours_skip_its_first_month_and_any_odd_hour():
    first = at("2026-01-01T00:00Z")
    spike = at("2026-02-15T12:00Z")
    hours = hp.live_hours(live_rows(first, at("2026-03-01T00:00Z"), spike))
    assert min(hours) == first + 31 * 86400 and max(hours) == at("2026-02-28T23:00Z")
    assert spike not in hours and spike - HOUR not in hours and spike + 2 * HOUR in hours
    assert hp.live_hours([{"time": t, "USD": 1} for t in range(first, first + 30 * 86400, 86400)]) == {}


def test_a_mempool_server_gives_hours_after_the_files_and_the_asked_hour_within_them(sites, db):
    use(price_source="mempool", mempool_url=NODE)
    sites.mempool = live_rows(at("2025-10-01T00:00Z"), NOW)
    within, after = at("2026-02-02T02:00Z"), at("2026-03-16T16:00Z")
    assert hp.hourly_price(db, utc("2026-02-02T02:10Z"))[1] == "mempool"
    assert hp.hourly_price(db, utc("2026-03-16T16:10Z"))[1] == "mempool"
    # only the hours used are kept: a later release's year files come first for the rest
    assert {row.hour for row in db.query(BtcPriceHourly)} == {within, after}
    assert sites.requests == [NODE + "/api/v1/historical-price?currency=USD"]  # once; no Bitstamp


def test_a_mempool_server_without_the_hour_leaves_it_to_the_fallbacks_download(sites, db):
    use(price_source="mempool", mempool_url=NODE, mempool_fallback=True)
    sites.mempool = live_rows(at("2026-01-01T00:00Z"), NOW)
    h = at("2025-05-05T05:00Z")
    assert hp.hourly_price(db, utc("2025-05-05T05:05Z")) == (sites.prices[h], "bitstamp")
    finish_download()
    assert sites.requests[0].startswith(NODE)  # the own server first


def test_no_hourly_price_before_the_first_year_or_for_an_hour_not_begun(sites, db, monkeypatch):
    """Review of #173: an entry dated today (noon in the tax timezone) was
    refused until that hour came; it takes the day's price, marked as such.
    A later day has no price."""
    monkeypatch.setattr(price_history, "_today", lambda: datetime(2026, 3, 20, tzinfo=timezone.utc).date())
    priced = hp.price_at(db, utc("2024-12-31T23:30Z"))
    assert priced.moment == "day" and sites.requests == []
    later_today = hp.price_at(db, utc("2026-03-20T17:00Z"))
    assert later_today.moment == "day" and later_today.at == utc("2026-03-20T00:00Z")
    with pytest.raises(HTTPException) as exc:
        hp.price_at(db, utc("2026-03-21T09:00Z"))
    assert exc.value.status_code == 422


def test_a_file_that_doesnt_give_its_fingerprint_is_never_read(sites, db):
    """A tampered or corrupt file, or an older release's shorter one: not used, downloaded again."""
    hp.start_download()
    finish_download()
    path = hp.folder() / "2025.csv"
    path.write_text(path.read_text().replace(str(sites.prices[at("2025-06-01T13:00Z")]), "1.00", 1))
    hp.reset_state()
    sites.requests.clear()
    h = at("2025-06-01T13:00Z")
    assert hp.hourly_price(db, utc("2025-06-01T13:30Z")) == (sites.prices[h], "bitstamp")
    finish_download()
    assert sites.bitstamp_starts() == year_blocks(2025, pf.year_end(2025))  # that year again, only


def test_a_stored_hour_is_never_replaced_by_a_source(sites, db):
    hp.start_download()
    finish_download()
    h = at("2026-03-18T05:00Z")
    db.add(BtcPriceHourly(hour=h, usd=D("1.00"), source="mempool"))
    db.flush()
    hp.hourly_price(db, utc("2026-03-19T05:00Z"))  # Bitstamp's block, which holds the stored hour too
    assert db.get(BtcPriceHourly, h).usd == D("1.00")


def test_while_the_mempool_server_answers_bitstamp_isnt_asked(sites, db):
    use(price_source="mempool", mempool_url=NODE, mempool_fallback=True)
    sites.mempool = live_rows(at("2025-10-01T00:00Z"), NOW)
    assert hp.hourly_price(db, utc("2026-03-17T07:00Z"))[1] == "mempool"
    assert hp.hourly_price(db, utc("2025-12-24T07:00Z"))[1] == "mempool"
    assert sites.bitstamp_starts() == []


def test_a_block_with_an_hour_missing_is_asked_again(sites, db, monkeypatch):
    """With a mempool server and its fallback, an hour its record rejects is
    filled from Bitstamp's block even when later hours are kept already."""
    monkeypatch.setattr(pf, "BLOCK_HOURS", 24)
    hp.start_download()
    finish_download()
    gap = at("2026-03-16T12:00Z")
    for h in range(FILES_END + HOUR, NOW, HOUR):
        if h != gap:
            db.add(BtcPriceHourly(hour=h, usd=sites.prices[h], source="mempool"))
    db.flush()
    sites.requests.clear()
    assert hp.hourly_price(db, utc("2026-03-16T12:30Z")) == (sites.prices[gap], "bitstamp")
    # the blocks missing an hour: the gap's, and the current hour's
    assert sites.bitstamp_starts() == [at("2026-03-16T00:00Z"), at("2026-03-20T00:00Z")]


def test_a_failed_download_waits_before_it_is_tried_again(sites, db):
    sites.bitstamp_down = True
    hp.start_download()
    finish_download()
    assert not hp.start_download() and hp._state["failed_at"] > 0
    hp._state["failed_at"] -= hp.RETRY_SECONDS
    assert hp.start_download()
    finish_download()


def test_many_hours_are_kept_in_chunks(sites, db, monkeypatch):
    monkeypatch.setattr(hp, "STORE_CHUNK", 7)
    hp.start_download()
    finish_download()
    hp.hourly_price(db, utc("2026-03-18T05:00Z"))
    assert db.query(BtcPriceHourly).count() == (NOW - FILES_END) // HOUR  # to the current hour, traded


def test_the_day_lookup_after_the_hour_lookup_gets_the_mempool_servers_day(sites, db, monkeypatch):
    """Review of #169: the hour lookup used up the one request, and the day
    fallback right after got nothing from the server."""
    monkeypatch.setattr(price_history, "find_prices", real_find_prices)
    use(price_source="mempool", mempool_url=NODE)
    first = at("2026-03-01T00:00Z")
    sites.mempool = live_rows(first, NOW)  # hourly only from 1 March: its first 31 days aren't live hours
    priced = hp.price_at(db, utc("2026-03-10T05:00Z"))
    assert priced.moment == "day" and priced.usd == D(70000 + (at("2026-03-10T00:00Z") // HOUR) % 7)
    assert len(sites.requests) == 1


def test_the_download_stops_at_the_next_request_when_public_sites_stop_being_allowed(sites):
    def switch_off_after_one_block(fake):
        if len(fake.bitstamp_starts()) == 1:
            use(price_source="off")

    sites.after_request = switch_off_after_one_block
    hp.start_download()
    finish_download()
    assert len(sites.bitstamp_starts()) == 1
    assert hp._state["failed_at"] < 0  # a stop isn't a failure: switched back on, it goes on at once


def test_a_proxy_set_during_the_download_carries_the_next_request(sites, monkeypatch):
    proxies, real_client = [], outbound.async_client

    def recorded(timeout=outbound.TIMEOUT):
        proxies.append(outbound.current().proxy_url)
        return real_client(timeout=timeout)

    def tor_after_one_block(fake):
        if len(fake.bitstamp_starts()) == 1:
            use(price_source="public", proxy_url="socks5h://127.0.0.1:9050")

    monkeypatch.setattr(outbound, "async_client", recorded)
    sites.after_request = tor_after_one_block
    hp.start_download()
    finish_download()
    assert proxies[0] is None and set(proxies[1:]) == {"socks5h://127.0.0.1:9050"}
    assert len(proxies) == len(sites.bitstamp_starts())  # a client for each request: the next one uses Tor


def test_the_current_hour_comes_from_bitstamp_once_it_has_traded(sites, db):
    """Re-check of #169: with every earlier hour kept, the current hour's
    block was skipped and the hour got the day's price."""
    hp.start_download()
    finish_download()
    for h in range(FILES_END + HOUR, NOW, HOUR):
        db.add(BtcPriceHourly(hour=h, usd=sites.prices[h], source="bitstamp"))
    db.flush()
    sites.requests.clear()
    assert hp.price_at(db, utc("2026-03-20T10:05Z")) == hp.Priced(sites.prices[NOW], "hour", utc("2026-03-20T10:00Z"))
    assert sites.bitstamp_starts() == [FILES_END + HOUR]  # its block, the one after the files


def test_a_lookup_waiting_for_a_download_that_fails_ends_at_once(sites, db, monkeypatch):
    monkeypatch.setattr(hp, "WAIT_SECONDS", 20)
    sites.bitstamp_down = True
    started = time.monotonic()
    assert hp.price_at(db, utc("2025-06-01T13:00Z")).moment == "day"
    assert time.monotonic() - started < 5


def test_a_mempool_servers_answer_isnt_kept_once_it_is_no_longer_the_source(sites, db):
    use(price_source="mempool", mempool_url=NODE)
    sites.mempool = live_rows(at("2025-10-01T00:00Z"), NOW)
    hp.hourly_price(db, utc("2026-03-17T07:00Z"))
    assert price_history._state["mempool_rows"]
    use(price_source="public")
    hp.hourly_price(db, utc("2026-03-17T08:00Z"))
    assert price_history._state["mempool_rows"] == [] and not hp._live["rows"]


def test_the_day_lookup_drops_the_kept_mempool_answer_too(sites, db, monkeypatch):
    monkeypatch.setattr(price_history, "find_prices", real_find_prices)
    use(price_source="mempool", mempool_url=NODE)
    sites.mempool = live_rows(at("2025-10-01T00:00Z"), NOW)
    price_history.daily_price(db, utc("2026-03-17T00:00Z"))
    assert price_history._state["mempool_rows"]
    use(price_source="public")
    try:
        price_history.daily_price(db, utc("2025-01-05T00:00Z"))  # a day not stored: asked
    except HTTPException:
        pass  # no public price in this fake world: what matters is what was kept
    assert price_history._state["mempool_rows"] == []


def test_without_a_manifest_no_public_site_is_asked(sites, db, tmp_path, monkeypatch):
    monkeypatch.setattr(pf, "MANIFEST", tmp_path / "none.csv")
    assert hp.price_at(db, utc("2026-03-18T05:00Z")).moment == "day"
    assert sites.bitstamp_starts() == []
