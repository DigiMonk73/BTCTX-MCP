"""
A save of Settings -> Privacy & network while BitcoinTX asks Bitstamp for
the hours after the year files (#475): the blocks not yet asked aren't sent
(#437), the hours the blocks before it gave are kept, and the stop is no
failure. Once the choice allows public sites again, the next lookup asks
for the rest at once, not RETRY_SECONDS (10 minutes) later.
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from backend.services import hourly_prices as hp
from backend.services import outbound
from backend.services import price_files as pf

# The real function, captured before the session fixture stubs it.
from backend.services.hourly_prices import find_hours as real_find_hours

HOUR = pf.HOUR
NODE = "http://umbrel.local:3006"
PUBLIC = outbound.NetworkSettings(price_source="public")
NOBODY = outbound.NetworkSettings(price_source="off")
MEMPOOL_NO_BACKUP = outbound.NetworkSettings(price_source="mempool", mempool_url=NODE)
FILES_END = pf.read_manifest(pf.MANIFEST)[-1].last_hour  # the year files' last hour
NOW = FILES_END + 2500 * HOUR  # the current hour: three blocks after the files
BLOCKS = [FILES_END + HOUR + i * pf.BLOCK_HOURS * HOUR for i in range(3)]


def price(hour: int) -> Decimal:
    return Decimal("60000.00") + (hour - FILES_END) // HOUR  # a price of its own for each hour


def utc(hour: int) -> datetime:
    return datetime.fromtimestamp(hour, tz=timezone.utc)


class Bitstamp:
    """Bitstamp's hourly candles, every block's start recorded; `then`
    runs at the first request, standing for a save landing while it's under
    way (that request's answer is the one it was sent for)."""

    def __init__(self):
        self.starts, self.then = [], None

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.host != "www.bitstamp.net":
            return httpx.Response(503)
        start = int(request.url.params["start"])
        self.starts.append(start)
        then, self.then = self.then, None
        if then:
            then()
        rows = [{"timestamp": str(h), "open": str(price(h)), "volume": "1.5"}
                for h in range(start, min(start + pf.BLOCK_HOURS * HOUR, NOW + HOUR), HOUR)]
        return httpx.Response(200, json={"data": {"pair": "BTC/USD", "ohlc": rows}})


@pytest.fixture
def bitstamp(monkeypatch):
    fake = Bitstamp()
    monkeypatch.setattr(hp, "find_hours", real_find_hours)
    monkeypatch.setattr(hp, "_current_hour", lambda: NOW)
    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(outbound, "_current", PUBLIC)  # put back afterwards
    return fake


@pytest.fixture
def db(test_engine):
    with sessionmaker(bind=test_engine)() as session:
        yield session
        session.rollback()


def saved(settings: outbound.NetworkSettings):
    """A save of `settings`: what load() leaves in memory."""
    return lambda: setattr(outbound, "_current", settings)


@pytest.mark.parametrize("choice", [NOBODY, MEMPOOL_NO_BACKUP], ids=["nobody", "mempool, no backup"])
def test_a_history_download_a_save_stopped_is_asked_again_as_the_new_choice_says(bitstamp, db, caplog, choice):
    """The issue's probe: a choice without public sites is saved as the
    first of three blocks answers. The rest isn't asked, and nothing is
    logged as a failure. Public sites saved again at once: the next lookup
    asks the two blocks still missing and finds the hour, without waiting
    10 minutes."""
    hour = BLOCKS[2] + 10 * HOUR
    bitstamp.then = saved(choice)
    assert hp.hourly_price(db, utc(hour) + timedelta(minutes=30)) is None
    assert bitstamp.starts == BLOCKS[:1]
    assert not [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    outbound._current = PUBLIC
    assert hp.hourly_price(db, utc(hour) + timedelta(minutes=30)) == (price(hour), "bitstamp")
    assert bitstamp.starts == BLOCKS  # the first block's hours were kept: it isn't asked again


def test_the_hours_a_block_gave_before_the_save_are_kept(bitstamp, db):
    """The first block's answer came under the choice it was sent with:
    its hours are kept, and the hour asked in it is found. While Nobody
    holds, nothing more is asked."""
    bitstamp.then = saved(NOBODY)
    hour = BLOCKS[0] + 5 * HOUR
    assert hp.hourly_price(db, utc(hour)) == (price(hour), "bitstamp")
    last = BLOCKS[1] - HOUR
    assert hp.hourly_price(db, utc(last)) == (price(last), "bitstamp")  # stored
    assert hp.hourly_price(db, utc(BLOCKS[1])) is None
    assert bitstamp.starts == BLOCKS[:1]
