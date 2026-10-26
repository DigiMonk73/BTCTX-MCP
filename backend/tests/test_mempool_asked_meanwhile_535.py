"""
Your own Mempool's history is asked at most once every 10 minutes, and its
answer is kept for the day and hour lookups to share (#144). A lookup made
while that request is still under way (the first after a fresh install, or
10 minutes after the last) waits for its answer, at most LOOKUP_SECONDS,
and sends no request of its own (#535): it took the kept answer, still
empty, and refused the value (422) until tried again, or, for an hour
whose day was stored, took the day's 00:00 price, marked as priced at the
day (tax figures). Each lookup runs in a thread and an event loop of its
own (price_history._run), as here. One whose settings a save changed while
it waited goes by those in use (#437, #473), and a save holding SQLite's
write lock never waits under it (#426). However the request ends (answered,
failed, refused unsent, cut off at its lookup's limit), its waiters go on
at once.
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
from backend.services import hourly_prices as hp
from backend.services import outbound, price_history

# The real lookups, captured before the session fixture stubs them.
from backend.services.hourly_prices import find_hours as real_find_hours
from backend.services.price_history import find_prices as real_find_prices

HOUR = 3600
SLOW = "http://mempool-a.local:3006"  # answers once released
OTHER = "http://mempool-b.local:3006"  # answers at once
LEVEL = {"mempool-a.local": 80000, "mempool-b.local": 86000}  # the two servers never agree
FIRST, END = (int(datetime(*d, tzinfo=timezone.utc).timestamp()) for d in ((2025, 2, 1), (2025, 4, 1)))
FIRST_DAY, SECOND_DAY = date(2025, 3, 1), date(2025, 3, 15)


def price(host: str, when: date | datetime) -> Decimal:
    """The server's price when `when`'s hour began (a day: at its 00:00 UTC)."""
    if not isinstance(when, datetime):
        when = datetime(when.year, when.month, when.day, tzinfo=timezone.utc)
    t = int(when.timestamp()) // HOUR * HOUR
    return Decimal(LEVEL[host] + (t // HOUR) % 7)


def rows(host: str) -> list[dict]:
    """A server's hourly record of February and March 2025."""
    return [{"time": t, "USD": LEVEL[host] + (t // HOUR) % 7} for t in range(FIRST, END, HOUR)]


class Mempools:
    """Two stand-in Mempool servers, every request recorded: the slow one
    answers only once released, after `then` (a save landing meanwhile),
    with a 503 when it `fails`."""

    def __init__(self):
        self.requests: list[str] = []
        self.asked, self.release = threading.Event(), threading.Event()
        self.then = None
        self.fails = False
        self.reads, self.read = 0, threading.Condition()

    async def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        if request.url.host == "mempool-a.local":
            self.asked.set()
            # Awaited, so a lookup's limit (_run) cuts the request off as it would a real one
            assert await asyncio.to_thread(self.release.wait, 10)
            if self.then:
                self.then()
            if self.fails:
                return httpx.Response(503)
        return httpx.Response(200, json={"prices": rows(request.url.host), "exchangeRates": {}})

    def count_settings_reads(self, monkeypatch) -> None:
        """Each reading of the settings counted: a lookup reads them first,
        holding the lock its kept answer is read under."""
        real_current = outbound.current

        def current() -> outbound.NetworkSettings:
            settings = real_current()
            with self.read:
                self.reads += 1
                self.read.notify_all()
            return settings

        monkeypatch.setattr(outbound, "current", current)

    def reads_reach(self, count: int) -> bool:
        with self.read:
            return self.read.wait_for(lambda: self.reads >= count, timeout=10)

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
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as fake.pool:
        yield fake
        fake.release.set()  # a test that failed leaves no lookup waiting


def use(mempool_url: str) -> None:
    """A save of your Mempool's address: what load() leaves in memory."""
    outbound._current = outbound.NetworkSettings(price_source="mempool", mempool_url=mempool_url)


def lookup() -> tuple[list[dict], bool]:
    """A lookup of your Mempool's history in an event loop of its own."""
    return asyncio.run(price_history.own_node_rows())


def first_lookup(mempools: Mempools) -> concurrent.futures.Future:
    """A lookup in a thread of its own that asks the slow Mempool, under way."""
    first = mempools.pool.submit(lookup)
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


def test_an_hour_looked_up_while_the_history_is_asked_gets_its_hours_price(mempools, test_engine, monkeypatch):
    """The review of #535 (tax figures): an hour looked up meanwhile found
    no hour in the empty answer and took its day's 00:00 UTC price, stored
    already, as priced at the day ($69,000.00 here, where the Mempool had
    the hour). A value saved then kept it. It gets its hour's price."""
    monkeypatch.setattr(hp, "find_hours", real_find_hours)
    use(SLOW)
    mempools.answered_as_the_next_lookup_reads_the_settings(monkeypatch)
    Session = sessionmaker(bind=test_engine)
    with Session() as db:
        db.add(BtcPriceDaily(day=SECOND_DAY, usd=Decimal("69000.00"), source="bitstamp"))
        db.commit()
    first = first_lookup(mempools)
    when = datetime(2025, 3, 15, 7, 10, tzinfo=timezone.utc)
    with Session() as db:
        priced = hp.price_at(db, when)
    assert (priced.moment, priced.usd, priced.source) == ("hour", price("mempool-a.local", when), "mempool")
    assert priced.at == datetime(2025, 3, 15, 7, tzinfo=timezone.utc)
    assert first.result(10) == (rows("mempool-a.local"), True)
    assert mempools.requests == [SLOW + "/api/v1/historical-price?currency=USD"]


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


# The review of #535, finding 2: however the request ends, its waiters go on
# at once, not at their limit (LOOKUP_SECONDS, 30 s here, so "at once", under
# 5 s, holds on a busy test machine too, clear of the fixture's own 10 s: #781)
def test_a_failed_request_frees_its_waiters_at_once(mempools, monkeypatch):
    """None of them has a price, and none asks again (a failure waits 10
    minutes, as before)."""
    monkeypatch.setattr(price_history, "LOOKUP_SECONDS", 30)
    use(SLOW)
    mempools.fails = True
    mempools.count_settings_reads(monkeypatch)
    first = first_lookup(mempools)
    reads = mempools.reads
    waiters = [mempools.pool.submit(lookup) for _ in range(3)]
    assert mempools.reads_reach(reads + 3)  # each read the settings with the request under way
    started = time.monotonic()
    mempools.release.set()
    assert [waiter.result(10) for waiter in waiters] == [([], False)] * 3
    assert time.monotonic() - started < 5
    assert first.result(10) == ([], False)
    assert len(mempools.requests) == 1


def test_a_request_a_save_refused_frees_its_waiters_to_ask_the_new_mempool_once(mempools, monkeypatch):
    """The other address is saved as the first lookup's request is about to
    go: it's refused unsent (#437). Its waiters go by the new address: one
    asks it, the other takes that answer."""
    monkeypatch.setattr(price_history, "LOOKUP_SECONDS", 30)
    use(SLOW)
    mempools.count_settings_reads(monkeypatch)
    real_client, waiters = outbound.own_node_client, []

    def saved_as_its_client_is_made(timeout=None):
        monkeypatch.setattr(outbound, "own_node_client", real_client)  # the waiters' clients are ordinary
        client, reads = real_client(timeout), mempools.reads
        waiters.extend(mempools.pool.submit(lookup) for _ in range(2))
        assert mempools.reads_reach(reads + 2)  # both read the slow Mempool's address, its request under way
        use(OTHER)
        return client  # made for the slow Mempool

    monkeypatch.setattr(outbound, "own_node_client", saved_as_its_client_is_made)
    started = time.monotonic()
    assert lookup() == ([], False)
    answers = [waiter.result(10) for waiter in waiters]
    assert time.monotonic() - started < 5
    assert sorted(answers, key=lambda answer: answer[1]) == [(rows("mempool-b.local"), False),
                                                              (rows("mempool-b.local"), True)]
    assert mempools.requests == [OTHER + "/api/v1/historical-price?currency=USD"]


def test_a_request_cut_off_at_its_lookups_limit_frees_its_waiter_at_once(mempools, monkeypatch):
    """The first lookup's limit (_run) cuts its request off: the waiter,
    whose own limit is later, has no price at that moment, and asks
    nothing (a request cut off waits 10 minutes, as before)."""
    monkeypatch.setattr(price_history, "LOOKUP_SECONDS", 0.5)
    use(SLOW)
    first = mempools.pool.submit(lambda: price_history._run(price_history.own_node_rows()))
    assert mempools.asked.wait(10)
    monkeypatch.setattr(price_history, "LOOKUP_SECONDS", 30)  # the waiter's
    started = time.monotonic()
    assert lookup() == ([], False)
    assert time.monotonic() - started < 5
    with pytest.raises(TimeoutError):
        first.result(10)
    assert len(mempools.requests) == 1
