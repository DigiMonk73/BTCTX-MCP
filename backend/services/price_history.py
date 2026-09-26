"""
backend/services/price_history.py

The BTC price for a past day, from one place. Every historical valuation
(an income deposit's basis, a spend's or gift's value, a BTC fee, the
form's price Refresh, import autofill, year-end values) goes through
daily_price(), so the same day always gets the same price.

A day's price is its 00:00 UTC price (the daily open the sources publish),
keyed by the UTC calendar day of the timestamp.

Lookup order:
  1. the local table btc_price_daily;
  2. one bulk download of the days around it (Bitstamp, then Coinbase, then
     Kraken's recent candles), which fills every day it returns;
  3. the single-day lookup (services/bitcoin.get_historical_price).
Every price found is stored. There is never a fallback to today's live
price: a past value at today's price is wrong. No price means a clear 422.

Prices are added in the caller's session (flush, not commit), so a
recalculation or a dry run keeps them only if it commits; read-only callers
commit themselves.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Optional, Union

from fastapi import HTTPException
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.models.btc_price import BtcPriceDaily
from backend.services import outbound

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")
# The first day any of the sources has a USD price for (Bitstamp: Sep 2011).
FIRST_PRICE_DAY = date(2010, 7, 17)

BITSTAMP_OHLC_URL = "https://www.bitstamp.net/api/v2/ohlc/btcusd/"
COINBASE_CANDLES_URL = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"
DAY = 86400


def _utc_day(when: Union[date, datetime]) -> date:
    if isinstance(when, datetime):
        when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
        return when.astimezone(timezone.utc).date()
    return when


def _midnight(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def _from_unix(ts) -> date:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).date()


# ---------------------------------------------------------------------------
# Network: bulk range download
# ---------------------------------------------------------------------------
async def _bitstamp(client, start: date, end: date) -> Dict[date, Decimal]:
    days = (end - start).days + 1
    resp = await client.get(BITSTAMP_OHLC_URL, params={
        "step": DAY, "limit": min(days, 1000), "start": _midnight(start),
    })
    resp.raise_for_status()
    out = {}
    for row in resp.json()["data"]["ohlc"]:
        out[_from_unix(row["timestamp"])] = Decimal(str(row["open"]))
    return out


async def _coinbase(client, start: date, end: date) -> Dict[date, Decimal]:
    end = min(end, start + timedelta(days=299))  # 300 candles per request
    resp = await client.get(COINBASE_CANDLES_URL, params={
        "granularity": DAY,
        "start": f"{start.isoformat()}T00:00:00Z",
        "end": f"{end.isoformat()}T00:00:00Z",
    })
    resp.raise_for_status()
    # [time, low, high, open, close, volume]
    return {_from_unix(row[0]): Decimal(str(row[3])) for row in resp.json()}


async def _kraken(client, start: date, end: date) -> Dict[date, Decimal]:
    # Kraken returns at most its latest 720 daily candles whatever `since`
    # says, so only the days it actually returns are used.
    resp = await client.get(KRAKEN_OHLC_URL, params={
        "pair": "XBTUSD", "interval": 1440, "since": _midnight(start) - 1,
    })
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise ValueError(str(data["error"]))
    pair = next(k for k in data["result"] if k != "last")
    # [time, open, high, low, close, vwap, volume, count]
    return {_from_unix(row[0]): Decimal(str(row[1])) for row in data["result"][pair]}


BULK_SOURCES = (("bitstamp", _bitstamp), ("coinbase", _coinbase), ("kraken", _kraken))


async def fetch_range(start: date, end: date) -> Dict[date, tuple]:
    """
    Daily prices for start..end (inclusive) from the first bulk source that
    answers: {day: (usd, source)}. Days outside the range, in the future or
    with a non-positive price are dropped. Empty when every source fails.
    """
    today = datetime.now(timezone.utc).date()
    if not outbound.live_data_on():
        return {}  # live data off: no public service is asked
    async with outbound.async_client() as client:
        for name, fetch in BULK_SOURCES:
            try:
                prices = await fetch(client, start, end)
            except Exception as exc:
                logger.info("BTC price history from %s failed: %s", name, exc)
                continue
            kept = {
                d: (p.quantize(CENT), name) for d, p in prices.items()
                if start <= d <= end and d <= today and p > 0
            }
            if kept:
                return kept
    return {}


async def _fetch_one(day: date) -> Optional[tuple]:
    from backend.services import bitcoin

    try:
        data = await bitcoin.get_historical_price(day.isoformat())
        price = Decimal(str(data["USD"]))
    except Exception as exc:
        logger.info("BTC price for %s from the single-day lookup failed: %s", day, exc)
        return None
    return (price.quantize(CENT), "daily") if price > 0 else None


def _run(coro):
    """Run a coroutine to completion from sync code, even inside an event loop's thread."""
    def target():
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(target).result(timeout=60)


# ---------------------------------------------------------------------------
# Table
# ---------------------------------------------------------------------------
def stored_price(db: Session, when: Union[date, datetime]) -> Optional[Decimal]:
    row = db.get(BtcPriceDaily, _utc_day(when))
    return Decimal(row.usd) if row else None


def _store(db: Session, prices: Dict[date, tuple]) -> None:
    if not prices:
        return
    rows = [{"day": d, "usd": usd, "source": src} for d, (usd, src) in prices.items()]
    db.execute(sqlite_insert(BtcPriceDaily).values(rows).on_conflict_do_nothing())
    db.flush()


def no_price(day: date) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail=f"No BTC price is available for {day.isoformat()}; enter the USD value yourself.",
    )


def daily_price(db: Session, when: Union[date, datetime]) -> Decimal:
    """The BTC/USD price for the UTC day of `when`. 422 when there is none."""
    day = _utc_day(when)
    price = stored_price(db, day)
    if price is not None:
        return price
    today = datetime.now(timezone.utc).date()
    if day > today or day < FIRST_PRICE_DAY:
        raise no_price(day)

    start = max(FIRST_PRICE_DAY, day - timedelta(days=500))
    end = min(today, day + timedelta(days=499))
    try:
        prices = _run(fetch_range(start, end))
    except Exception as exc:
        logger.warning("BTC price history download failed: %s", exc)
        prices = {}
    if day not in prices:
        one = _run(_fetch_one(day))
        if one:
            prices[day] = one
    _store(db, prices)
    if day not in prices:
        raise no_price(day)
    return prices[day][0]


async def daily_price_async(db: Session, when: Union[date, datetime]) -> Decimal:
    """daily_price() for async routes (runs it in a worker thread)."""
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(daily_price, db, when)
