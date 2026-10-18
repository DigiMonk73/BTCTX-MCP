"""
Your own Mempool's answer is kept for 10 minutes, so the day and hour
lookups share it (#144). An answer that comes back after its address was
changed (a lookup waiting for a slow Mempool while the owner saves another
one, and a lookup asks the new one meanwhile) serves the lookup that asked
for it, and is never kept (#473): kept, it was filed under the new address,
and for those 10 minutes every lookup took the old server's prices as the
new one's, and stored them.
"""

import asyncio
import threading
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from backend.models.btc_price import BtcPriceDaily, BtcPriceHourly
from backend.services import hourly_prices as hp
from backend.services import outbound, price_history

# The real lookups, captured before the session fixture stubs them.
from backend.services.hourly_prices import find_hours as real_find_hours
from backend.services.price_history import find_prices as real_find_prices

HOUR = 3600
OLD = "http://mempool-a.local:3006"
NEW = "http://mempool-b.local:3006"
LEVEL = {"mempool-a.local": 40000, "mempool-b.local": 46000}  # the two servers never agree
FIRST, END = (int(datetime(*d, tzinfo=timezone.utc).timestamp()) for d in ((2023, 12, 1), (2024, 3, 1)))
DAY = date(2024, 1, 10)
MOMENT = datetime(2024, 2, 10, 14, 30, tzinfo=timezone.utc)


def price(host: str, t: int) -> Decimal:
    return Decimal(LEVEL[host] + (t // HOUR) % 7)


def rows(host: str) -> list[dict]:
    """A server's hourly record from 1 December 2023: live hours from January."""
    return [{"time": t, "USD": int(price(host, t))} for t in range(FIRST, END, HOUR)]


def unix(when: datetime) -> int:
    return int(when.timestamp())


class Servers:
    """Two stand-in Mempool servers, every request recorded: the new one
    answers at once, the old one only once released (a slow Mempool)."""

    def __init__(self):
        self.asked = []
        self.old_asked = self.release = None  # made in the lookups' event loop

    async def handler(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        self.asked.append(host)
        if host == "mempool-a.local":
            self.old_asked.set()
            await self.release.wait()
        return httpx.Response(200, json={"prices": rows(host), "exchangeRates": {}})


@pytest.fixture
def servers(monkeypatch):
    fake = Servers()
    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(price_history, "find_prices", real_find_prices)
    monkeypatch.setattr(hp, "find_hours", real_find_hours)
    return fake


@pytest.fixture
def db(test_engine):
    with sessionmaker(bind=test_engine)() as session:
        yield session
        session.rollback()


def use(mempool_url: str) -> None:
    """A save of your Mempool's address: what load() leaves in memory."""
    outbound._current = outbound.NetworkSettings(price_source="mempool", mempool_url=mempool_url)


async def across_the_change(servers: Servers):
    """Lookup 1 waits for the old Mempool; the new one is saved, and lookup 2
    asks it; then the old one answers lookup 1."""
    servers.old_asked, servers.release = asyncio.Event(), asyncio.Event()
    use(OLD)
    first = asyncio.create_task(price_history.own_node_rows())
    await asyncio.wait_for(servers.old_asked.wait(), 10)
    use(NEW)
    second = await price_history.own_node_rows()
    servers.release.set()
    return await first, second


def test_the_old_mempools_late_answer_isnt_kept_under_the_new_address(servers, db):
    """#473's probe: after the old server's late answer, the day and the hour
    priced (and stored) under the new address are the new server's."""
    (old_rows, _), (new_rows, _) = asyncio.run(across_the_change(servers))
    assert old_rows == rows("mempool-a.local") and new_rows == rows("mempool-b.local")  # each lookup its own server's

    midnight, hour = unix(datetime(2024, 1, 10, tzinfo=timezone.utc)), unix(MOMENT.replace(minute=0))
    assert price_history.daily_price(db, DAY) == price("mempool-b.local", midnight)
    assert hp.hourly_price(db, MOMENT) == (price("mempool-b.local", hour), "mempool")
    stored_day, stored_hour = db.get(BtcPriceDaily, DAY), db.get(BtcPriceHourly, hour)
    assert (Decimal(stored_day.usd), stored_day.source) == (price("mempool-b.local", midnight), "mempool")
    assert Decimal(stored_hour.usd) == price("mempool-b.local", hour)
    assert servers.asked == ["mempool-a.local", "mempool-b.local"]  # the new server's kept answer served both


def test_the_new_mempools_answer_stays_kept_after_the_old_ones(servers):
    """The kept answer is the new server's, and no request goes to either
    server for the rest of its 10 minutes."""
    asyncio.run(across_the_change(servers))
    assert price_history._state["mempool_base"] == NEW
    assert price_history._state["mempool_rows"] == rows("mempool-b.local")
    assert asyncio.run(price_history.own_node_rows()) == (rows("mempool-b.local"), False)
    assert servers.asked == ["mempool-a.local", "mempool-b.local"]


def test_an_answer_with_no_change_meanwhile_is_kept_as_before(servers):
    use(NEW)
    assert asyncio.run(price_history.own_node_rows()) == (rows("mempool-b.local"), True)
    assert asyncio.run(price_history.own_node_rows()) == (rows("mempool-b.local"), False)
    assert servers.asked == ["mempool-b.local"]


def test_the_old_mempools_answer_is_kept_under_its_own_address_when_nothing_asked_since(servers):
    """A save to another address with no lookup meanwhile: the late answer is
    filed under the address it came from, where it is that server's, and the
    new address is asked at its first lookup."""

    async def saved_while_waiting():
        servers.old_asked, servers.release = asyncio.Event(), asyncio.Event()
        use(OLD)
        first = asyncio.create_task(price_history.own_node_rows())
        await asyncio.wait_for(servers.old_asked.wait(), 10)
        use(NEW)
        servers.release.set()
        return await first

    assert asyncio.run(saved_while_waiting()) == (rows("mempool-a.local"), True)
    assert price_history._state["mempool_base"] == OLD
    assert asyncio.run(price_history.own_node_rows()) == (rows("mempool-b.local"), True)
    assert servers.asked == ["mempool-a.local", "mempool-b.local"]


def test_a_lookup_a_save_stopped_leaves_the_new_mempools_kept_answer(servers, monkeypatch):
    """Lookups run in threads of their own: lookup 1 starts under the old
    address, and before its request goes the new one is saved and lookup 2,
    in another thread, asks it. Lookup 1's request is refused unsent (#437);
    the new server's answer stays kept, so it isn't asked again."""
    real_client = outbound.own_node_client

    def saved_before_the_request(timeout=None):
        monkeypatch.setattr(outbound, "own_node_client", real_client)  # lookup 2's client is an ordinary one
        use(NEW)
        lookup_2 = threading.Thread(target=lambda: asyncio.run(price_history.own_node_rows()))
        lookup_2.start()
        lookup_2.join()
        return real_client(timeout)

    use(OLD)
    monkeypatch.setattr(outbound, "own_node_client", saved_before_the_request)
    assert asyncio.run(price_history.own_node_rows()) == ([], False)
    assert asyncio.run(price_history.own_node_rows()) == (rows("mempool-b.local"), False)
    assert servers.asked == ["mempool-b.local"]  # the old server never, the new one once
