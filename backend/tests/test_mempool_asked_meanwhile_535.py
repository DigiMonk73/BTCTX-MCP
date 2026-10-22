"""
Your own Mempool's history is asked at most once every 10 minutes, and its
answer is kept for the day and hour lookups to share (#144). A lookup made
while that request is still under way (the first after a fresh install, or
10 minutes after the last) waits for its answer, at most LOOKUP_SECONDS,
and sends no request of its own (#535): it took the kept answer, still
empty, and refused the value (422) until tried again. Each lookup runs in a
thread and an event loop of its own (price_history._run), as here. One
whose settings a save changed while it waited goes by those in use (#437,
#473), and a save holding SQLite's write lock never waits under it (#426).
"""

import asyncio
import concurrent.futures
import threading
import time
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from backend.models.btc_price import BtcPriceDaily
from backend.services import outbound, price_history

# The real lookup, captured before the session fixture stubs it.
from backend.services.price_history import find_prices as real_find_prices

HOUR = 3600
SLOW = "http://mempool-a.local:3006"  # answers once released
OTHER = "http://mempool-b.local:3006"  # answers at once
LEVEL = {"mempool-a.local": 80000, "mempool-b.local": 86000}  # the two servers never agree
FIRST, END = (int(datetime(*d, tzinfo=timezone.utc).timestamp()) for d in ((2025, 2, 1), (2025, 4, 1)))
FIRST_DAY, SECOND_DAY = date(2025, 3, 1), date(2025, 3, 15)


def price(host: str, day: date) -> Decimal:
    t = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())
    return Decimal(LEVEL[host] + (t // HOUR) % 7)


def rows(host: str) -> list[dict]:
    """A server's hourly record of February and March 2025."""
    return [{"time": t, "USD": LEVEL[host] + (t // HOUR) % 7} for t in range(FIRST, END, HOUR)]


class Mempools:
    """Two stand-in Mempool servers, every request recorded: the slow one
    answers only once released, after `then` (a save landing meanwhile)."""

    def __init__(self):
        self.requests: list[str] = []
        self.asked, self.release = threading.Event(), threading.Event()
        self.then = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        if request.url.host == "mempool-a.local":
            self.asked.set()
            assert self.release.wait(10)
            if self.then:
                self.then()
        return httpx.Response(200, json={"prices": rows(request.url.host), "exchangeRates": {}})

    def answered_as_the_next_lookup_reads_the_settings(self, monkeypatch) -> None:
        """The slow server answers as soon as the next lookup has read the
        settings, which it does holding the lock the kept answer is read and
        kept under: that lookup always finds the request still under way."""
        real_current = outbound.current

        def current() -> outbound.NetworkSettings:
            settings = real_current()
            if self.asked.is_set():
                self.release.set()
            return settings

        monkeypatch.setattr(outbound, "current", current)


@pytest.fixture
def mempools(monkeypatch):
    fake = Mempools()
    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(price_history, "find_prices", real_find_prices)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as fake.pool:
        yield fake
        fake.release.set()  # a test that failed leaves no lookup waiting


def use(mempool_url: str) -> None:
    """A save of your Mempool's address: what load() leaves in memory."""
    outbound._current = outbound.NetworkSettings(price_source="mempool", mempool_url=mempool_url)


def first_lookup(mempools: Mempools) -> concurrent.futures.Future:
    """A lookup in a thread of its own that asks the slow Mempool, under way."""
    first = mempools.pool.submit(lambda: asyncio.run(price_history.own_node_rows()))
    assert mempools.asked.wait(10)
    return first


def test_a_lookup_made_while_the_history_is_asked_gets_its_price(mempools, test_engine, monkeypatch):
    """#535's steps: a second day looked up while the first lookup's request
    is under way gets its price, from that one request, which names no day."""
    use(SLOW)
    mempools.answered_as_the_next_lookup_reads_the_settings(monkeypatch)
    Session = sessionmaker(bind=test_engine)

    def day_price(day: date) -> Decimal:
        with Session() as db:
            return price_history.daily_price(db, day)

    first = mempools.pool.submit(day_price, FIRST_DAY)
    assert mempools.asked.wait(10)
    assert day_price(SECOND_DAY) == price("mempool-a.local", SECOND_DAY)  # was a 422
    assert first.result(10) == price("mempool-a.local", FIRST_DAY)
    assert mempools.requests == [SLOW + "/api/v1/historical-price?currency=USD"]
    with Session() as db:
        for day in (FIRST_DAY, SECOND_DAY):
            stored = db.get(BtcPriceDaily, day)
            assert (Decimal(stored.usd), stored.source) == (price("mempool-a.local", day), "mempool")


def test_a_lookup_waits_for_that_answer_no_longer_than_its_limit(mempools, monkeypatch):
    """Then it has no price (no request of its own), and the answer that
    comes later is kept for the next lookups as before."""
    monkeypatch.setattr(price_history, "LOOKUP_SECONDS", 0.3)
    use(SLOW)
    first = first_lookup(mempools)
    started = time.monotonic()
    assert asyncio.run(price_history.own_node_rows()) == ([], False)
    assert 0.25 < time.monotonic() - started < 5  # it waited, to its limit
    mempools.release.set()
    assert first.result(10) == (rows("mempool-a.local"), True)
    assert asyncio.run(price_history.own_node_rows()) == (rows("mempool-a.local"), False)
    assert len(mempools.requests) == 1


def test_a_lookup_whose_mempool_a_save_changed_while_it_waited_asks_the_new_one(mempools, monkeypatch):
    """The other address is saved while the second lookup waits, and the
    slow Mempool's answer comes after: it serves only the lookup that asked
    for it (#473). The second lookup goes by the settings in use (#437): it
    asks the new Mempool and takes its prices, never the old one's."""
    use(SLOW)
    mempools.answered_as_the_next_lookup_reads_the_settings(monkeypatch)
    mempools.then = lambda: use(OTHER)
    first = first_lookup(mempools)
    assert asyncio.run(price_history.own_node_rows()) == (rows("mempool-b.local"), True)
    assert first.result(10) == (rows("mempool-a.local"), True)
    assert [httpx.URL(u).host for u in mempools.requests] == ["mempool-a.local", "mempool-b.local"]
    assert price_history._state["mempool_base"] == OTHER
    assert price_history._state["mempool_rows"] == rows("mempool-b.local")


def test_a_save_holding_the_write_lock_doesnt_wait_for_that_answer_under_it(mempools, test_engine):
    """#426: a save holding SQLite's write lock sends no request, and waits
    for none either: the owner's other saves wait only 5 s for that lock.
    Its lookup stops it (PriceNeeded), and the save finds the price with the
    lock free (hourly_prices.with_prices_found), then waiting for it. It
    was told there was no price (422)."""
    use(SLOW)
    first = first_lookup(mempools)
    with sessionmaker(bind=test_engine)() as db:
        db.execute(text("BEGIN IMMEDIATE"))  # a save that has written
        db.info[price_history.ASK_FIRST] = True  # in with_prices_found
        with pytest.raises(price_history.PriceNeeded):
            price_history.daily_price(db, SECOND_DAY)
        db.rollback()
    mempools.release.set()
    assert first.result(10) == (rows("mempool-a.local"), True)
    assert len(mempools.requests) == 1
