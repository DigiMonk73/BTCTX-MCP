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

import logging
import random
import sys
import threading
import time
import traceback
from collections import OrderedDict
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
        self.bitstamp_refuses = None  # a status Bitstamp answers instead (403, 302): what Tor's exits get
        self.requests = []
        self.after_request = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        if self.after_request:
            self.after_request(self)
        if request.url.host == "www.bitstamp.net" and self.bitstamp_down:
            return httpx.Response(503)
        if request.url.host == "www.bitstamp.net" and self.bitstamp_refuses:
            return httpx.Response(self.bitstamp_refuses, headers={"location": str(request.url)},
                                  text="<HTML><HEAD><TITLE>Loading</TITLE></HEAD></HTML>")
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


# The download takes well under a second, but a shared CI runner once held
# one past 10 s with nothing wrong in it (#841): wait as long as it takes,
# up to a limit only a stuck download reaches, and then say where it is
FINISH_SECONDS = 120


def finish_download():
    with hp._changed:
        done = hp._changed.wait_for(lambda: not hp._state["running"], timeout=FINISH_SECONDS)
    assert done, f"the download still runs after {FINISH_SECONDS} s:\n{download_stacks()}"


def download_stacks() -> str:
    """Where each download thread is now."""
    frames = sys._current_frames()
    return "\n".join("".join(traceback.format_stack(frames[thread.ident]))
                     for thread in threading.enumerate()
                     if thread.name == "btc-price-download" and thread.ident in frames)


def test_a_wait_that_runs_out_says_where_the_download_is():
    stop = threading.Event()

    def stuck_on_a_request():
        stop.wait(10)

    thread = threading.Thread(target=stuck_on_a_request, name="btc-price-download", daemon=True)
    thread.start()
    try:
        assert "stuck_on_a_request" in download_stacks()
    finally:
        stop.set()
        thread.join()


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


def test_a_choice_allowing_public_sites_starts_the_download_when_saved(sites, monkeypatch, auth_client):
    """Public sites, or your Mempool with its backup (#145, the amendment's
    choice 1, owner's OK 2026-10-12); never your Mempool alone or Nobody."""
    started = []
    monkeypatch.setattr(hp, "start_download", lambda: started.append(1) or True)
    for choice, starts in (({"price_source": "mempool", "mempool_url": NODE, "mempool_fallback": False}, False),
                           ({"price_source": "off"}, False),
                           ({"price_source": "mempool", "mempool_url": NODE, "mempool_fallback": True}, True),
                           ({"price_source": "public"}, True)):
        started.clear()
        r = auth_client.put("/api/settings/network", json={"mempool_url": None, "mempool_fallback": False,
                                                           "proxy_url": None, **choice})
        assert r.status_code == 200 and started == ([1] if starts else []), choice


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


def test_an_hour_bitstamp_gives_at_no_price_is_never_kept(sites, db):
    """Session 8's review (#151): an hour after the files that Bitstamp gave
    at 0, below 0, under a cent or as no number was kept, and a kept hour is
    never replaced, so a value left blank in that hour was saved at $0 or
    less (AGENTS.md: never $0). Such an hour has no price: the day's is
    used. An open that doesn't parse cost the whole block (#199's review)."""
    hp.start_download()
    finish_download()
    bad = {"2026-03-18T05:00Z": "0", "2026-03-18T06:00Z": "-5", "2026-03-18T07:00Z": "NaN",
           "2026-03-18T09:00Z": "0.004", "2026-03-18T10:00Z": "abc", "2026-03-18T11:00Z": "",
           "2026-03-18T12:00Z": "Infinity"}
    for label, open_ in bad.items():
        sites.bitstamp[at(label)] = open_
    assert hp.hourly_price(db, utc("2026-03-18T05:20Z")) is None
    stored = {row.hour for row in db.query(BtcPriceHourly)}
    assert not stored & {at(label) for label in bad}
    assert {at("2026-03-18T08:00Z"), at("2026-03-18T13:00Z")} <= stored  # the hours around them still are
    for label in bad:
        priced = hp.price_at(db, utc(label))
        assert priced.moment == "day" and priced.usd > 0


def test_a_current_hour_whose_volume_doesnt_parse_costs_no_other_hour(sites, db):
    hp.start_download()
    finish_download()
    sites.volume[NOW] = "abc"
    assert hp.hourly_price(db, utc("2026-03-19T23:30Z"))[0] == sites.prices[at("2026-03-19T23:00Z")]
    assert NOW not in {row.hour for row in db.query(BtcPriceHourly)}


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


def test_a_mempool_servers_row_that_is_no_price_costs_no_other_hour():
    """#199's review: a row that wasn't a number lost every hour."""
    first, odd = at("2026-01-01T00:00Z"), at("2026-02-15T12:00Z")
    rows = live_rows(first, at("2026-03-01T00:00Z"))
    next(row for row in rows if row["time"] == odd)["USD"] = "NaN"
    hours = hp.live_hours(rows)
    assert odd not in hours and at("2026-02-20T12:00Z") in hours and all(p > 0 for p in hours.values())


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


def test_the_mempools_history_is_logged_once_whichever_lookup_downloads_it(sites, db, monkeypatch, caplog):
    """#557: the log names where each download of past prices came from
    (the StartOS docs, AGENT-TESTS PRC-4), but the mempool server's history
    downloaded by an hour lookup was never named, nor by the day lookup that
    took its kept answer next."""
    monkeypatch.setattr(price_history, "find_prices", real_find_prices)
    use(price_source="mempool", mempool_url=NODE)
    sites.mempool = live_rows(at("2025-10-01T00:00Z"), NOW)
    with caplog.at_level(logging.INFO, logger=price_history.__name__):
        priced = hp.price_at(db, utc("2026-03-17T07:10Z"))  # the hour: its lookup downloads the history
        assert (priced.moment, priced.source) == ("hour", "mempool")
        assert price_history.daily_price(db, utc("2026-03-01T00:00Z")) > 0  # the day: the kept answer
    days = len(price_history.midnight_prices(sites.mempool))
    assert [r.getMessage() for r in caplog.records if "mempool server" in r.getMessage()] == [
        f"Price history from your mempool server: {days} days"]
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


# The status line's view of the download (#145): read from this install's
# files and memory, never a request.
def test_the_download_status_follows_the_download(sites, db):
    use(price_source="off")
    status = hp.download_status()
    assert status == {"until": "2026-03-14T23:00Z", "first_year": 2025, "shipped": False, "years_total": 2,
                      "years_done": 0, "state": "not_allowed", "failed_at": None, "refused": False,
                      "mismatched": [], "without_tor": False}
    use(price_source="public")
    assert hp.download_status()["state"] == "waiting"
    seen = []
    sites.after_request = lambda fake: seen.append(hp.download_status())
    hp.start_download()
    finish_download()
    assert seen[0]["state"] == "downloading" and seen[0]["years_done"] == 0
    assert seen[-1]["years_done"] == 1  # 2026 checked and saved, 2025 on its way
    done = hp.download_status()
    assert done["state"] == "complete" and done["years_done"] == 2
    use(price_source="off")
    assert hp.download_status()["state"] == "complete"  # it stays here, whatever the choice
    assert len(sites.requests) == len(year_blocks(2026, FILES_END) + year_blocks(2025, pf.year_end(2025)))


def test_the_download_status_names_a_failure_and_a_year_that_didnt_match(sites, db):
    sites.bitstamp_down = True
    hp.start_download()
    finish_download()
    status = hp.download_status()
    assert status["state"] == "failed" and status["failed_at"].endswith("Z")
    hp._state["failed_at"] -= hp.RETRY_SECONDS  # ten minutes later: tried again
    assert hp.download_status()["state"] == "waiting"
    sites.bitstamp_down = False
    sites.bitstamp[at("2025-08-08T08:00Z")] += D("0.01")
    hp.start_download()
    finish_download()
    status = hp.download_status()
    assert status["years_done"] == 1 and status["mismatched"] == [2025] and status["state"] == "waiting"
    (hp.folder() / "2026.csv").write_text("hour_utc,usd\n", encoding="utf-8")  # damaged on disk
    assert hp.download_status()["years_done"] == 0


@pytest.mark.parametrize("answer", [403, 302])
def test_a_refused_download_says_so_and_a_silent_one_doesnt(sites, db, answer):
    """Bitstamp gives Tor's exits a block (403) or a challenge page (302)
    instead of prices (#241): the status says it refused, so the card
    doesn't ask whether Tor is running. A site that doesn't answer isn't
    a refusal."""
    sites.bitstamp_refuses = answer
    hp.start_download()
    finish_download()
    status = hp.download_status()
    assert status["state"] == "failed" and status["refused"] is True
    hp._state["failed_at"] -= hp.RETRY_SECONDS
    assert hp.download_status()["refused"] is False  # only while the failure is shown
    sites.bitstamp_refuses, sites.bitstamp_down = None, True
    hp.start_download()
    finish_download()
    assert hp.download_status()["refused"] is False


def _three_year_files(monkeypatch, kept: OrderedDict, missing=()):
    """Year files for 2019-2021 (2019's cached as `kept` holds it), without disk."""
    monkeypatch.setattr(hp, "_years", kept)
    lines = [pf.YearLine(y, pf.year_start(y), pf.year_end(y), 1, f"sha{y}") for y in (2019, 2020, 2021)]
    monkeypatch.setattr(pf, "read_manifest", lambda path=None: lines)
    monkeypatch.setattr(hp, "_file_text", lambda line: None if line.year in missing else str(line.year))
    monkeypatch.setattr(pf, "parse_year_text", lambda text: {int(text): Decimal("1.00")})
    return [datetime(y, 3, 1, tzinfo=timezone.utc) for y in (2019, 2020, 2021)]


def test_a_requests_year_files_leave_the_years_kept_in_memory(monkeypatch):
    """#419's review: the AI preview reads its rows' year files before its
    dry run (#204); keeping them in memory (two years) pushed out a year the
    dry run's own pricing then read again under the write lock."""
    kept = OrderedDict({2019: ("sha2019", {2019: Decimal("1.00")})})
    years: dict = {}
    hp.read_year_files(_three_year_files(monkeypatch, kept), years)
    assert list(kept) == [2019]
    assert {y for y in years if y != "manifest"} == {2019, 2020, 2021}


def test_a_year_not_downloaded_yet_is_looked_up_again(monkeypatch):
    """#419's review: a year file missing when read before the dry run was
    noted as missing, so a price the dry run waited for went unnamed."""
    years: dict = {}
    hp.read_year_files(_three_year_files(monkeypatch, OrderedDict(), missing={2020}), years)
    assert 2020 not in years and 2021 in years
