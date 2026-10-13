"""
Every request to an outside service ends in bounded time and size
(services/outbound.py, BoundedClient). httpx's timeouts limit each wait,
not the whole request, so the whole request has a deadline (WAITS times its
timeout), and an answer over MAX_ANSWER_BYTES is refused before it is read
whole; either is a failed request, handled as any other (the backup, "no
price", trying again later). A lookup from sync code (price_history._run)
returns at its limit, with its thread ended. The answers here arrive in
small parts, each well within the timeout: from a real local server for the
live price, faked otherwise.
"""

import asyncio
import gzip
import http.server
import json
import threading
import time
from datetime import date, datetime, timezone

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from backend.services import bitcoin, outbound, price_history
from backend.services import hourly_prices as hp
from backend.tests.test_hourly_prices import sites  # noqa: F401  (fixture)

# The real functions, captured before the session fixture stubs them.
from backend.services.bitcoin import get_current_price as real_current_price
from backend.services.price_history import find_prices as real_find_prices

NODE = "http://umbrel.local:3006"
PRICE = b'{"time":1,"USD":61234}'
GAP = 0.05  # seconds between the parts of an answer arriving in parts: well within each wait's limit here
MARGIN = 1.0  # seconds a lookup may end after its deadline (a slow test machine)
DAY = date(2023, 3, 3)


def use(**settings):
    outbound._current = outbound.NetworkSettings(**settings)
    bitcoin._price_cache.update(settings=None)


def wait_until(check, seconds: float = 2.0) -> bool:
    end = time.monotonic() + seconds
    while not check() and time.monotonic() < end:
        time.sleep(0.01)
    return bool(check())


class InParts(httpx.AsyncByteStream):
    """An answer arriving a byte every GAP seconds; `sent` counts what went out."""

    def __init__(self, body: bytes):
        self.body, self.sent = body, 0

    async def __aiter__(self):
        for i in range(len(self.body)):
            await asyncio.sleep(GAP)
            self.sent += 1
            yield self.body[i:i + 1]


class Sized(httpx.AsyncByteStream):
    """An answer of `size` bytes, sent at once in 1 KiB parts; `sent` counts what went out."""

    def __init__(self, size: int):
        self.size, self.sent = size, 0

    async def __aiter__(self):
        while self.sent < self.size:
            self.sent += 1024
            yield b" " * 1024


def answering(stream: httpx.AsyncByteStream) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))


@pytest.fixture
def db(test_engine):
    with sessionmaker(bind=test_engine)() as session:
        yield session
        session.rollback()


@pytest.fixture
def mempool_in_parts():
    """A real local mempool server: its first answer arrives a byte every GAP
    seconds (over 4 seconds in all), every later one at once. Yields its
    address and the bytes each answer got out."""
    body = PRICE + b" " * 60
    answers, stop = [], threading.Event()

    class Mempool(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            first = not answers
            answers.append(0)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                if not first:
                    self.wfile.write(body)
                    answers[-1] = len(body)
                    return
                for i in range(len(body)):
                    if stop.wait(GAP):
                        return
                    self.wfile.write(body[i:i + 1])
                    answers[0] += 1
            except OSError:  # the client has gone
                pass

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Mempool)
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", answers, len(body)
    stop.set()
    server.shutdown()
    server.server_close()


def test_the_live_price_gives_up_at_the_deadline_and_frees_its_lock(monkeypatch, mempool_in_parts):
    """With a 10 s timeout, an answer arriving in parts kept the live price
    16 s, the other price requests waiting on its lock meanwhile."""
    url, answers, size = mempool_in_parts
    monkeypatch.setattr(outbound, "_transport", None)  # a real request
    monkeypatch.setattr(outbound, "TIMEOUT", 0.2)  # each wait: well over GAP, so only the deadline ends it
    deadline = outbound.WAITS * outbound.TIMEOUT
    use(price_source="mempool", mempool_url=url)

    async def timed(lookup):
        try:
            result = await lookup
        except HTTPException as exc:
            result = exc.status_code
        return result, time.monotonic()

    async def two_lookups():
        start = time.monotonic()
        first = asyncio.ensure_future(timed(real_current_price()))
        await asyncio.sleep(0.01)  # the first one holds the lock
        second = await timed(real_current_price())
        return [(result, at - start) for result, at in (await first, second)]

    (first, first_took), (second, second_took) = asyncio.run(two_lookups())
    assert first == 502 and first_took < deadline + MARGIN  # no backup: "Your Mempool didn't answer"
    assert second["USD"] == 61234 and second["source"] == "mempool" and second_took < deadline + MARGIN
    assert answers[0] < size  # the first answer was left unfinished


def test_a_past_price_lookup_gives_up_at_the_deadline_and_its_thread_ends(monkeypatch, db):
    """A save needing a past price waits in a worker thread: it's free again by the deadline."""
    midnight = int(datetime(DAY.year, DAY.month, DAY.day, tzinfo=timezone.utc).timestamp())
    rows = [{"time": t, "USD": 30000} for t in (midnight - 3600, midnight, midnight + 3600)]
    answer = InParts(json.dumps({"prices": rows, "exchangeRates": {}}).encode())
    monkeypatch.setattr(outbound, "_transport", answering(answer))
    monkeypatch.setattr(outbound, "HISTORY_TIMEOUT", 0.1)
    monkeypatch.setattr(price_history, "find_prices", real_find_prices)
    use(price_source="mempool", mempool_url=NODE)
    threads, start = threading.active_count(), time.monotonic()
    with pytest.raises(HTTPException) as e:
        price_history.daily_price(db, DAY)
    assert e.value.status_code == 422 and time.monotonic() - start < outbound.WAITS * 0.1 + MARGIN
    assert answer.sent < len(answer.body)
    assert wait_until(lambda: threading.active_count() == threads)  # the lookup's own thread has ended


def test_a_lookup_from_sync_code_returns_at_its_limit_and_its_thread_ends(monkeypatch):
    """With result(timeout=1), it returned after 4 s: the executor's `with`
    waited for the thread."""
    monkeypatch.setattr(price_history, "LOOKUP_SECONDS", 0.3)
    ended = []

    async def longer():
        try:
            await asyncio.sleep(3)
        finally:
            ended.append(time.monotonic())

    threads, start = threading.active_count(), time.monotonic()
    with pytest.raises(TimeoutError):
        price_history._run(longer())
    assert time.monotonic() - start < 0.3 + MARGIN
    assert wait_until(lambda: ended and threading.active_count() == threads)
    assert ended[0] - start < 0.3 + MARGIN  # cancelled at the limit, not left running


def test_a_years_download_that_never_ends_stops_at_its_deadline(sites, monkeypatch):  # noqa: F811
    """The hourly history's download runs in its own thread: it ends as a
    failed download (tried again later) instead of running on."""
    monkeypatch.setattr(outbound, "_transport", answering(InParts(b" " * 400)))
    monkeypatch.setattr(outbound, "HISTORY_TIMEOUT", 0.1)
    assert hp.start_download()
    with hp._changed:
        assert hp._changed.wait_for(lambda: not hp._state["running"], timeout=outbound.WAITS * 0.1 + MARGIN)
    assert hp.download_status()["state"] == "failed"


def test_an_answer_over_the_limit_is_refused_before_it_is_read_whole(monkeypatch):
    monkeypatch.setattr(outbound, "MAX_ANSWER_BYTES", 64 * 1024)
    answer = Sized(4 * 64 * 1024)
    monkeypatch.setattr(outbound, "_transport", answering(answer))
    use(price_source="mempool", mempool_url=NODE)
    assert asyncio.run(price_history.own_node_rows()) == ([], False)
    assert 64 * 1024 < answer.sent <= 65 * 1024


def test_a_compressed_answer_counts_at_its_full_size(monkeypatch):
    monkeypatch.setattr(outbound, "MAX_ANSWER_BYTES", 64 * 1024)
    packed = gzip.compress(b" " * (4 * 64 * 1024))  # under 1 KiB sent
    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(
        lambda request: httpx.Response(200, headers={"Content-Encoding": "gzip"}, content=packed)))

    async def ask():
        async with outbound.async_client() as client:
            return await client.get(bitcoin.KRAKEN_TICKER_URL)

    with pytest.raises(outbound.AnswerTooLarge):
        asyncio.run(ask())


def test_the_largest_real_answer_comes_in_whole(monkeypatch):
    """Your Mempool's whole history, even with a row for every hour since
    2010 (~4.3 MiB, more than a real one), is under a third of the limit."""
    first, now = 1279411200, int(time.time()) // 3600 * 3600  # 18 July 2010
    rows = [{"time": t, "USD": 60000} for t in range(first, now, 3600)]
    body = json.dumps({"prices": rows, "exchangeRates": {}}, separators=(",", ":")).encode()
    assert 3 * len(body) < outbound.MAX_ANSWER_BYTES
    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(
        lambda request: httpx.Response(200, headers={"Content-Encoding": "gzip"}, content=gzip.compress(body))))
    use(price_source="mempool", mempool_url=NODE)
    assert asyncio.run(price_history.own_node_rows()) == (rows, True)


# #220's review: compressed answers decoded a bounded step at a time
class Parts(httpx.AsyncByteStream):
    """An answer that arrives as these raw parts (not read whole first)."""

    def __init__(self, *parts: bytes):
        self.parts = parts

    async def __aiter__(self):
        for part in self.parts:
            yield part


def ask_with(monkeypatch, headers, *parts):
    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(
        lambda request: httpx.Response(200, headers=headers, stream=Parts(*parts))))

    async def ask():
        async with outbound.async_client() as client:
            return await client.get(bitcoin.KRAKEN_TICKER_URL)

    return asyncio.run(ask())


def test_a_stacked_or_unknown_encoding_is_refused(monkeypatch):
    twice = gzip.compress(gzip.compress(b'{"result": {}}'))
    for encoding in ("gzip, gzip", "br", "zstd"):
        with pytest.raises(httpx.DecodingError):
            ask_with(monkeypatch, {"Content-Encoding": encoding}, twice)


def test_a_small_compressed_answer_never_decodes_past_the_limit_in_memory(monkeypatch):
    import tracemalloc

    monkeypatch.setattr(outbound, "MAX_ANSWER_BYTES", 64 * 1024)
    packed = gzip.compress(b" " * (64 * 1024 * 1024))  # 64 MiB once decoded, one raw part
    tracemalloc.start()
    try:
        with pytest.raises(outbound.AnswerTooLarge):
            ask_with(monkeypatch, {"Content-Encoding": "gzip"}, packed)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 8 * 1024 * 1024, peak


def test_a_streamed_gzip_answer_still_decodes(monkeypatch):
    body = b'{"error": [], "result": {"XXBTZUSD": {"c": ["65000.0", "1"]}}}'
    packed = gzip.compress(body)
    r = ask_with(monkeypatch, {"Content-Encoding": "gzip"}, packed[:10], packed[10:])
    assert r.status_code == 200 and r.json()["result"]["XXBTZUSD"]["c"][0] == "65000.0"
