"""
The BTC price for a past day, from one place. Every historical valuation
(an income deposit's basis, a spend's or gift's value, a BTC fee, the
sidebar's Date price, import autofill, year-end values) goes through
daily_price(), so the same day always gets the same price.

A day's price is its 00:00 UTC price (the daily open the sources publish),
keyed by the UTC calendar day of the timestamp.

Lookup order:
  1. the local table btc_price_daily;
  2. the chosen price source (services/outbound.py), asked so that no
     request ever names the day:
     - own mempool server: its whole price history in one request, keeping
       the 00:00 UTC hours its 23:00 and 01:00 hours agree with;
     - public sites: Bitstamp's whole daily history once, in fixed blocks
       that are the same for every install (retried later if it fails), then
       only "the latest days" (Bitstamp, else Kraken). Coinbase is never
       asked: its terms forbid building an end-user app on its data (#161).
       Through Tor, Bitstamp refuses them (#241): after the owner's Yes to
       downloading the history without Tor, the fixed blocks (only they) go
       directly (outbound.history_client); the latest days stay on Tor.
Every price found is stored and a stored day never changes, so tax figures
don't move. There is never a fallback to today's live price: a past value at
today's price is wrong. No price means a clear 422 (type the value in).

Prices found are kept at once (keep()): in a short transaction of their
own, or in the caller's when it has already written, so a lookup never
holds SQLite's write lock until its request ends (#364).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.models.btc_price import BtcPriceDaily
from backend.services import outbound, price_status
from backend.services.price_files import BITSTAMP_OHLC_URL, HOUR, usable_price

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")
# The first day of Bitstamp's daily history; no clean source goes further back.
FIRST_PRICE_DAY = date(2011, 8, 18)
BITSTAMP_BLOCK = 1000  # days per request

KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"
MEMPOOL_HISTORY_PATH = "/api/v1/historical-price"
DAY = 86400
MEMPOOL_TOLERANCE = Decimal("0.02")  # a 00:00 price within 2% of 23:00 and 01:00
RETRY_SECONDS = 600
# The most a lookup from sync code may take (_run): each request in it has its
# own deadline (outbound.BoundedClient); this bounds them all together
LOOKUP_SECONDS = 180
HISTORY_FLAG = "price_history_complete"  # app_settings: the full download is done

# When each download last ran (in memory: a restart may ask again, and every
# public request is the same for every install anyway).
_state: dict = {}


def try_again_now() -> None:
    """The whole history is asked again at the next lookup, not RETRY_SECONDS
    after it failed: after the owner's Yes to it without Tor (#241)."""
    _state["full_failed_at"] = -1e9


def reset_state() -> None:
    """Forget when downloads last ran (tests)."""
    _state.update(full_failed_at=-1e9, latest_day=None, latest_failed_at=-1e9,
                  mempool_at=-1e9, mempool_base=None, mempool_rows=[])


reset_state()


def utc_day(when: date | datetime) -> date:
    """The day whose price values `when`: its UTC day (a naive time is UTC)."""
    if isinstance(when, datetime):
        when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
        return when.astimezone(timezone.utc).date()
    return when


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _midnight(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def _from_unix(ts) -> date:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).date()


# Public sites: requests that never depend on which day is wanted
async def _bitstamp(client, start: date | None = None) -> dict[date, str]:
    """1,000 daily opens from `start` (a fixed block start), or the latest
    1,000, as the site gives them (_kept checks each)."""
    params = {"step": DAY, "limit": BITSTAMP_BLOCK}
    if start is not None:
        params["start"] = _midnight(start)
    resp = await client.get(BITSTAMP_OHLC_URL, params=params)
    resp.raise_for_status()
    return {_from_unix(row["timestamp"]): str(row["open"]) for row in resp.json()["data"]["ohlc"]}


async def _kraken_latest(client) -> dict[date, str]:
    """Kraken's latest 720 daily opens, as it gives them (_kept checks each)."""
    resp = await client.get(KRAKEN_OHLC_URL, params={"pair": "XBTUSD", "interval": 1440})
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise ValueError(str(data["error"]))
    pair = next(k for k in data["result"] if k != "last")
    # [time, open, high, low, close, vwap, volume, count]
    return {_from_unix(row[0]): str(row[1]) for row in data["result"][pair]}


def _blocks(first: date, size: int) -> list[date]:
    """Fixed block starts from `first` to today: the same list for every install."""
    starts, day, today = [], first, _today()
    while day <= today:
        starts.append(day)
        day += timedelta(days=size)
    return starts


def _kept(prices: dict[date, str], source: str) -> dict[date, tuple]:
    today = _today()
    cents = {d: usable_price(p) for d, p in prices.items() if d <= today}
    return {d: (p, source) for d, p in cents.items() if p is not None}


async def public_history(full: bool) -> tuple[dict[date, tuple], bool]:
    """
    Daily prices from public sites, and whether Bitstamp's whole history came
    in. full: every day since FIRST_PRICE_DAY in fixed blocks from Bitstamp
    (retried after RETRY_SECONDS if one fails). Otherwise the latest days, at
    most once a UTC day.
    """
    if full:
        return await _whole_public_history()
    return await _latest_public_prices()


async def _whole_public_history() -> tuple[dict[date, tuple], bool]:
    now = time.monotonic()
    if now - _state["full_failed_at"] < RETRY_SECONDS:
        return {}, False
    # Counted before it starts, so a lookup ended at its limit (_run) still
    # waits RETRY_SECONDS before the next try; a success clears it (the
    # caller may not keep what came, and then it's asked again)
    _state["full_failed_at"] = now
    without_tor = outbound.history_without_tor()
    async with outbound.history_client() as client:
        got = await _bitstamp_blocks(client)
    if got:
        _state["full_failed_at"] = -1e9
        how = f", without Tor (agreed on {outbound.agreed_on()})" if without_tor else ""
        logger.info("BTC price history from public site bitstamp%s: %d days", how, len(got))
        return _kept(got, "bitstamp"), True
    return {}, False


async def _bitstamp_blocks(client) -> dict[date, str]:
    """Every block of Bitstamp's daily history, or nothing when one of them fails."""
    got: dict[date, str] = {}
    try:
        for start in _blocks(FIRST_PRICE_DAY, BITSTAMP_BLOCK):
            got.update(await _bitstamp(client, start))
    except Exception as exc:
        logger.info("BTC price history from bitstamp failed: %s", exc)
        price_status.record_refusal(exc)  # through Tor: the card asks (#241)
        return {}
    return got


async def _latest_public_prices() -> tuple[dict[date, tuple], bool]:
    now, today = time.monotonic(), _today()
    if _state["latest_day"] == today or now - _state["latest_failed_at"] < RETRY_SECONDS:
        return {}, False
    async with outbound.async_client() as client:
        for name, fetch in (("bitstamp", _bitstamp), ("kraken", _kraken_latest)):
            try:
                got = _kept(await fetch(client), name)
            except Exception as exc:
                logger.info("Latest BTC prices from %s failed: %s", name, exc)
                continue
            if got:
                logger.info("Latest BTC prices from public site %s", name)
                _state["latest_day"] = today
                return got, False
    _state["latest_failed_at"] = now
    return {}, False


# The owner's mempool server
def midnight_prices(rows: list[dict]) -> dict[date, tuple]:
    """
    mempool's price rows at exactly 00:00 UTC whose 23:00 and 01:00 rows
    exist and agree within 2%: its hourly record. Older weekly rows and
    backfilled daily rows (a day's close stored under its start) never match.
    """
    by_time = {}
    for row in rows:
        try:
            t, price = int(row["time"]), Decimal(str(row["USD"]))
        except (KeyError, TypeError, ValueError, ArithmeticError):
            continue
        if usable_price(price) is not None:
            by_time[t] = price
    out = {}
    for t, price in by_time.items():
        if t % DAY:
            continue
        before, after = by_time.get(t - HOUR), by_time.get(t + HOUR)
        limit = price * MEMPOOL_TOLERANCE
        if before and after and abs(before - price) <= limit and abs(after - price) <= limit:
            out[_from_unix(t)] = (price.quantize(CENT), "mempool")
    return out


async def own_node_rows() -> tuple[list[dict], bool]:
    """
    The own mempool server's whole USD history, and whether it was just
    asked: one request at most every 10 minutes; its answer is kept that
    long, so the day and hour lookups (services/hourly_prices.py) share it.
    """
    base = outbound.current().own_node
    if not base:
        _state.update(mempool_base=None, mempool_rows=[])
        return [], False
    now = time.monotonic()
    if base == _state["mempool_base"] and now - _state["mempool_at"] < RETRY_SECONDS:
        return _state["mempool_rows"], False
    _state.update(mempool_at=now, mempool_base=base, mempool_rows=[])
    try:
        async with outbound.own_node_client(timeout=outbound.HISTORY_TIMEOUT) as client:
            resp = await client.get(base + MEMPOOL_HISTORY_PATH, params={"currency": "USD"})
            resp.raise_for_status()
            rows = resp.json()["prices"]
    except Exception as exc:
        logger.warning("Price history from your mempool server failed: %s", exc)
        return [], False
    _state["mempool_rows"] = rows
    return rows, True


async def own_node_history() -> dict[date, tuple]:
    """The own mempool server's 00:00 UTC prices (own_node_rows): from its
    answer just asked, or the one kept from an hour lookup a moment ago."""
    rows, fresh = await own_node_rows()
    prices = midnight_prices(rows)
    if fresh:
        logger.info("Price history from your mempool server: %d days", len(prices))
    return prices


async def find_prices(day: date, full: bool) -> tuple[dict[date, tuple], bool]:
    """
    What the chosen sources give while `day` is missing, and whether the
    whole public history came in. `day` only decides whether to ask the
    public sites: no request ever names it.
    """
    settings = outbound.current()
    prices: dict[date, tuple] = {}
    complete = False
    prices.update(await own_node_history())  # nothing (and nothing kept) without a mempool server
    if day not in prices and settings.public_allowed:
        public, complete = await public_history(full)
        for d, value in public.items():
            prices.setdefault(d, value)
    return prices, complete


def _run(coro):
    """
    Run a coroutine from sync code, even inside an event loop's thread, for
    at most LOOKUP_SECONDS: then TimeoutError. The coroutine is cancelled at
    that limit, so its thread ends too, and the caller never waits for it:
    a worker thread waiting here is free again by then.
    """
    def target():
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(asyncio.wait_for(coro, LOOKUP_SECONDS))
        finally:
            loop.close()

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(target).result(timeout=LOOKUP_SECONDS)
    except (asyncio.TimeoutError, concurrent.futures.TimeoutError):  # two classes in Python 3.10
        raise TimeoutError(f"no prices within {LOOKUP_SECONDS} seconds") from None
    finally:
        pool.shutdown(wait=False)


# Table
def stored_price(db: Session, when: date | datetime) -> Decimal | None:
    row = db.get(BtcPriceDaily, utc_day(when))
    return Decimal(row.usd) if row else None


def stored_source(db: Session, when: date | datetime) -> str | None:
    """Where the stored day's price came from, e.g. "bitstamp"."""
    row = db.get(BtcPriceDaily, utc_day(when))
    return row.source if row else None


def _store(db: Session, prices: dict[date, tuple], complete: bool = False) -> None:
    """A lookup's days and, when it finished the full download, the mark that
    it's done, in one transaction: the mark never stands without its days."""
    from backend.models.app_setting import AppSetting

    rows = [{"day": d, "usd": usd, "source": src} for d, (usd, src) in prices.items()]

    def write(session: Session) -> None:
        if rows:
            session.execute(sqlite_insert(BtcPriceDaily).values(rows).on_conflict_do_nothing())
        if complete:
            session.execute(sqlite_insert(AppSetting).values(key=HISTORY_FLAG, value=_today().isoformat())
                            .on_conflict_do_nothing())

    if rows or complete:
        keep(db, write)


def keep(db: Session, write: Callable[[Session], object]) -> None:
    """
    Keep what write(session) adds: prices found, which never change once
    stored. A caller that has already written (an import's later rows, a
    recalculation) holds SQLite's write lock: it keeps them in its own
    transaction, since another one would wait for that lock, and they go if
    it rolls back. Anything else, a new or edited transaction's own pricing
    included, keeps them at once in a short transaction of its own, so it
    never holds the lock until its request ends and a save made meanwhile
    doesn't wait for it and fail (#364).
    """
    if writing(db):
        write(db)
        db.flush()
        return
    with Session(bind=db.get_bind()) as own:
        write(own)
        own.commit()


def writing(db: Session) -> bool:
    """Whether db has written and not committed: its connection holds SQLite's write lock."""
    return db.connection().connection.driver_connection.in_transaction


def no_price(day: date) -> HTTPException:
    settings = outbound.current()
    if settings.own_node or settings.public_allowed:
        detail = f"No BTC price is available for {day.isoformat()}; enter the USD value yourself."
    else:
        detail = (f"No BTC price is stored for {day.isoformat()}. "
                  f"{outbound.refuse_public().detail} Enter the USD value yourself.")
    return HTTPException(status_code=422, detail=detail)


def _history_complete(db: Session) -> bool:
    from backend.models.app_setting import AppSetting

    return db.get(AppSetting, HISTORY_FLAG) is not None


def daily_price(db: Session, when: date | datetime) -> Decimal:
    """The BTC/USD price for the UTC day of `when`. 422 when there is none."""
    day = utc_day(when)
    price = stored_price(db, day)
    if price is not None:
        return price
    if day > _today() or day < FIRST_PRICE_DAY:
        raise no_price(day)
    try:
        prices, complete = _run(find_prices(day, full=not _history_complete(db)))
    except Exception as exc:
        logger.warning("BTC price lookup failed: %s", exc)
        prices, complete = {}, False
    _store(db, prices, complete)
    if day not in prices:
        raise no_price(day)
    return prices[day][0]


async def daily_price_async(db: Session, when: date | datetime) -> Decimal:
    """daily_price() for async routes (runs it in a worker thread)."""
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(daily_price, db, when)
