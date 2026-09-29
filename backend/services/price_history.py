"""
The BTC price for a past day, from one place. Every historical valuation
(an income deposit's basis, a spend's or gift's value, a BTC fee, the
form's price Refresh, import autofill, year-end values) goes through
daily_price(), so the same day always gets the same price.

A day's price is its 00:00 UTC price (the daily open the sources publish),
keyed by the UTC calendar day of the timestamp.

Lookup order:
  1. the local table btc_price_daily;
  2. the chosen price source (services/outbound.py), asked so that no
     request ever names the day:
     - own mempool server: its whole price history in one request, keeping
       the 00:00 UTC hours its 23:00 and 01:00 hours agree with;
     - public sites: the whole daily history once, in fixed blocks that are
       the same for every install (Bitstamp, else Coinbase), then only "the
       latest days" (Bitstamp, else Kraken, else Coinbase).
Every price found is stored and a stored day never changes, so tax figures
don't move. There is never a fallback to today's live price: a past value at
today's price is wrong. No price means a clear 422 (type the value in).

Prices are added in the caller's session (flush, not commit), so a
recalculation or a dry run keeps them only if it commits; read-only callers
commit themselves.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.models.btc_price import BtcPriceDaily
from backend.services import outbound

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")
# The first day of Bitstamp's daily history; no clean source goes further back.
FIRST_PRICE_DAY = date(2011, 8, 18)
COINBASE_FIRST_DAY = date(2015, 7, 20)
BITSTAMP_BLOCK, COINBASE_BLOCK = 1000, 300  # days per request

BITSTAMP_OHLC_URL = "https://www.bitstamp.net/api/v2/ohlc/btcusd/"
COINBASE_CANDLES_URL = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"
MEMPOOL_HISTORY_PATH = "/api/v1/historical-price"
DAY = 86400
HOUR = 3600
MEMPOOL_TOLERANCE = Decimal("0.02")  # a 00:00 price within 2% of 23:00 and 01:00
RETRY_SECONDS = 600
HISTORY_FLAG = "price_history_complete"  # app_settings: the full download is done

# When each download last ran (in memory: a restart may ask again, and every
# public request is the same for every install anyway).
_state = {"full_failed_at": -1e9, "latest_day": None, "latest_failed_at": -1e9, "mempool_at": -1e9}


def reset_state() -> None:
    """Forget when downloads last ran (tests)."""
    _state.update(full_failed_at=-1e9, latest_day=None, latest_failed_at=-1e9, mempool_at=-1e9)


def _utc_day(when: date | datetime) -> date:
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
async def _bitstamp(client, start: date | None = None) -> dict[date, Decimal]:
    """1,000 daily opens from `start` (a fixed block start), or the latest 1,000."""
    params = {"step": DAY, "limit": BITSTAMP_BLOCK}
    if start is not None:
        params["start"] = _midnight(start)
    resp = await client.get(BITSTAMP_OHLC_URL, params=params)
    resp.raise_for_status()
    return {_from_unix(row["timestamp"]): Decimal(str(row["open"])) for row in resp.json()["data"]["ohlc"]}


async def _coinbase(client, start: date | None = None) -> dict[date, Decimal]:
    """300 daily opens from `start` (a fixed block start), or the latest ones."""
    params = {"granularity": DAY}
    if start is not None:
        end = min(start + timedelta(days=COINBASE_BLOCK - 1), _today())
        params.update(start=f"{start.isoformat()}T00:00:00Z", end=f"{end.isoformat()}T00:00:00Z")
    resp = await client.get(COINBASE_CANDLES_URL, params=params)
    resp.raise_for_status()
    # [time, low, high, open, close, volume]
    return {_from_unix(row[0]): Decimal(str(row[3])) for row in resp.json()}


async def _kraken_latest(client) -> dict[date, Decimal]:
    """Kraken's latest 720 daily opens."""
    resp = await client.get(KRAKEN_OHLC_URL, params={"pair": "XBTUSD", "interval": 1440})
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise ValueError(str(data["error"]))
    pair = next(k for k in data["result"] if k != "last")
    # [time, open, high, low, close, vwap, volume, count]
    return {_from_unix(row[0]): Decimal(str(row[1])) for row in data["result"][pair]}


def _blocks(first: date, size: int) -> list[date]:
    """Fixed block starts from `first` to today: the same list for every install."""
    starts, day, today = [], first, _today()
    while day <= today:
        starts.append(day)
        day += timedelta(days=size)
    return starts


def _kept(prices: dict[date, Decimal], source: str) -> dict[date, tuple]:
    today = _today()
    return {d: (p.quantize(CENT), source) for d, p in prices.items() if d <= today and p > 0}


async def public_history(full: bool) -> tuple[dict[date, tuple], bool]:
    """
    Daily prices from public sites, and whether Bitstamp's whole history came
    in. full: every day since FIRST_PRICE_DAY in fixed blocks (Bitstamp; else
    Coinbase, from 2015). Otherwise the latest days, at most once a UTC day.
    """
    if full:
        return await _whole_public_history()
    return await _latest_public_prices()


async def _whole_public_history() -> tuple[dict[date, tuple], bool]:
    now = time.monotonic()
    if now - _state["full_failed_at"] < RETRY_SECONDS:
        return {}, False
    async with outbound.async_client() as client:
        for name, fetch, first, size in (
            ("bitstamp", _bitstamp, FIRST_PRICE_DAY, BITSTAMP_BLOCK),
            ("coinbase", _coinbase, COINBASE_FIRST_DAY, COINBASE_BLOCK),
        ):
            got = await _every_block(client, name, fetch, first, size)
            if got:
                logger.info("BTC price history from public site %s: %d days", name, len(got))
                return _kept(got, name), name == "bitstamp"
    _state["full_failed_at"] = now
    return {}, False


async def _every_block(client, name: str, fetch, first: date, size: int) -> dict[date, Decimal]:
    """Every block from one site, or nothing when one of them fails."""
    got: dict[date, Decimal] = {}
    try:
        for start in _blocks(first, size):
            got.update(await fetch(client, start))
    except Exception as exc:
        logger.info("BTC price history from %s failed: %s", name, exc)
        return {}
    return got


async def _latest_public_prices() -> tuple[dict[date, tuple], bool]:
    now, today = time.monotonic(), _today()
    if _state["latest_day"] == today or now - _state["latest_failed_at"] < RETRY_SECONDS:
        return {}, False
    async with outbound.async_client() as client:
        for name, fetch in (("bitstamp", _bitstamp), ("kraken", _kraken_latest), ("coinbase", _coinbase)):
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
            by_time[int(row["time"])] = Decimal(str(row["USD"]))
        except (KeyError, TypeError, ValueError, ArithmeticError):
            continue
    out = {}
    for t, price in by_time.items():
        if t % DAY or price <= 0:
            continue
        before, after = by_time.get(t - HOUR), by_time.get(t + HOUR)
        limit = price * MEMPOOL_TOLERANCE
        if before and after and abs(before - price) <= limit and abs(after - price) <= limit:
            out[_from_unix(t)] = (price.quantize(CENT), "mempool")
    return out


async def own_node_history() -> dict[date, tuple]:
    """The own mempool server's whole USD history (one request, at most every 10 minutes)."""
    base = outbound.current().own_node
    now = time.monotonic()
    if not base or now - _state["mempool_at"] < RETRY_SECONDS:
        return {}
    _state["mempool_at"] = now
    try:
        async with outbound.own_node_client(timeout=30.0) as client:
            resp = await client.get(base + MEMPOOL_HISTORY_PATH, params={"currency": "USD"})
            resp.raise_for_status()
            rows = resp.json()["prices"]
    except Exception as exc:
        logger.warning("Price history from your mempool server failed: %s", exc)
        return {}
    prices = midnight_prices(rows)
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
    if settings.own_node:
        prices.update(await own_node_history())
    if day not in prices and settings.public_allowed:
        public, complete = await public_history(full)
        for d, value in public.items():
            prices.setdefault(d, value)
    return prices, complete


def _run(coro):
    """Run a coroutine to completion from sync code, even inside an event loop's thread."""
    def target():
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(target).result(timeout=180)


# Table
def stored_price(db: Session, when: date | datetime) -> Decimal | None:
    row = db.get(BtcPriceDaily, _utc_day(when))
    return Decimal(row.usd) if row else None


def _store(db: Session, prices: dict[date, tuple]) -> None:
    if not prices:
        return
    rows = [{"day": d, "usd": usd, "source": src} for d, (usd, src) in prices.items()]
    db.execute(sqlite_insert(BtcPriceDaily).values(rows).on_conflict_do_nothing())
    db.flush()


def no_price(day: date) -> HTTPException:
    settings = outbound.current()
    if settings.own_node or settings.public_allowed:
        detail = f"No BTC price is available for {day.isoformat()}; enter the USD value yourself."
    else:
        detail = (f"No BTC price is stored for {day.isoformat()}. "
                  f"{outbound.refuse_public().detail} Or enter the USD value yourself.")
    return HTTPException(status_code=422, detail=detail)


def _history_complete(db: Session) -> bool:
    from backend.models.app_setting import AppSetting

    return db.get(AppSetting, HISTORY_FLAG) is not None


def _mark_history_complete(db: Session) -> None:
    from backend.models.app_setting import AppSetting

    if db.get(AppSetting, HISTORY_FLAG) is None:
        db.add(AppSetting(key=HISTORY_FLAG, value=_today().isoformat()))
        db.flush()


def daily_price(db: Session, when: date | datetime) -> Decimal:
    """The BTC/USD price for the UTC day of `when`. 422 when there is none."""
    day = _utc_day(when)
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
    _store(db, prices)
    if complete:
        _mark_history_complete(db)
    if day not in prices:
        raise no_price(day)
    return prices[day][0]


async def daily_price_async(db: Session, when: date | datetime) -> Decimal:
    """daily_price() for async routes (runs it in a worker thread)."""
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(daily_price, db, when)
