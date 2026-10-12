"""
The live BTC price and the block height, from the source the owner chose
(services/outbound.py): their own mempool server, or public sites (with a
mempool server, only if "fall back to public sites" is on). Nothing is asked
while no source is chosen or lookups are off.

Past-day prices are not here: services/price_history.py fetches them without
ever naming a date.
"""

import asyncio
import logging
import math
import time
from collections.abc import Callable
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import HTTPException

from backend.services import outbound, price_status

logger = logging.getLogger(__name__)

KRAKEN_TICKER_URL = "https://api.kraken.com/0/public/Ticker?pair=XBTUSD"
BITSTAMP_TICKER_URL = "https://www.bitstamp.net/api/v2/ticker/btcusd/"

BLOCKCHAIN_INFO_HEIGHT_URL = "https://blockchain.info/q/getblockcount"
BLOCKSTREAM_HEIGHT_URL = "https://blockstream.info/api/blocks/tip/height"
MEMPOOL_HEIGHT_URL = "https://mempool.space/api/blocks/tip/height"

# The live price is asked at most once a minute, however many tabs poll it;
# requests at the same moment (the dashboard and the sidebar) wait for one.
PRICE_CACHE_SECONDS = 60
_price_cache: dict = {"settings": None, "at": 0.0, "value": None}
# The block height too: the Dashboard asked on every visit
_height_cache: dict = {"settings": None, "at": 0.0, "value": None}
_price_lock: dict = {"loop": None, "lock": None}


def _one_at_a_time() -> asyncio.Lock:
    """The price lock of the running event loop (an asyncio.Lock can't be
    shared between loops, and tests start several)."""
    loop = asyncio.get_running_loop()
    if _price_lock["loop"] is not loop:
        _price_lock.update(loop=loop, lock=asyncio.Lock())
    return _price_lock["lock"]


async def _from_own_node(path: str, parse: Callable):
    """Ask the owner's mempool server when it's the chosen source; None if it fails."""
    settings = outbound.current()
    base = settings.own_node
    if not base:
        if settings.price_source == "mempool" and not settings.waiting:  # no address: StartOS, Mempool not installed
            price_status.failed(price_status.MEMPOOL_MISSING)
        return None
    try:
        async with outbound.own_node_client() as client:
            resp = await client.get(base + path)
            resp.raise_for_status()
            value = parse(resp)
    except Exception as exc:
        logger.warning("Own mempool server %s%s failed: %s", base, path, exc)
        price_status.mempool_failed(exc)
        return None
    if value is None:
        logger.warning("Own mempool server %s%s answered without a price (yet)", base, path)
        price_status.failed(price_status.MEMPOOL_NO_ANSWER)
    else:
        price_status.answered("mempool")
    return value


async def _first_public(urls_and_parsers, what: str) -> tuple:
    """The first public site's answer and the site's name ("kraken"), or
    502 (naming the proxy when none could even be reached through it, e.g.
    Tor stopped)."""
    outbound.require_public()
    unreached = 0
    async with outbound.async_client() as client:
        for url, parse in urls_and_parsers:
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    value = parse(resp)
                    if value is not None:
                        price_status.answered(_site(url))
                        return value, _site(url)
            except Exception as exc:
                unreached += outbound.unreachable(exc)
                logger.info("%s from %s failed: %s", what, url.split("/")[2], exc)
    through_proxy = outbound.current().proxy_url and unreached == len(urls_and_parsers)
    price_status.failed(price_status.TOR_NO_ANSWER if through_proxy else price_status.PUBLIC_NO_ANSWER)
    if through_proxy:
        raise HTTPException(status_code=502, detail=(
            f"No public site answered for the {what}: none could be reached through the proxy for "
            "public sites. If that's Tor, is it running? (On StartOS: start the Tor service.)"))
    raise HTTPException(status_code=502, detail=f"No public site answered for the {what}.")


# A public site's short name, as the live price's "source" gives it
SITES = {"api.kraken.com": "kraken", "www.bitstamp.net": "bitstamp", "blockchain.info": "blockchain.info",
         "blockstream.info": "blockstream", "mempool.space": "mempool.space"}


def _site(url: str) -> str:
    """A public site's short name: https://api.kraken.com/... is "kraken"."""
    host = urlparse(url).hostname or ""
    return SITES.get(host, host)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _usd(value) -> dict | None:
    """A site's price, unless it's no price at all (0, negative, NaN, infinite)."""
    price = float(value)
    return {"USD": price} if math.isfinite(price) and price > 0 else None


def _kraken_price(resp) -> dict | None:
    data = resp.json()
    if data.get("error"):
        return None
    pair = next(iter(data["result"]))
    return _usd(data["result"][pair]["c"][0])  # last trade


def _bitstamp_price(resp) -> dict | None:
    return _usd(resp.json()["last"])  # last trade


async def get_current_price() -> dict:
    """
    The current BTC price in USD, with where it came from ("mempool",
    "kraken" or "bitstamp") and when it arrived ("at", UTC): the own
    mempool server, or Kraken, else Bitstamp (the sites the price history
    already asks). CoinGecko is never asked: its terms ask for a credit and
    discourage storing its data (#161). 503 when the owner chose Nobody or
    hasn't chosen, 502 when the chosen source fails.
    """
    settings = outbound.current()
    async with _one_at_a_time():
        cached = _price_cache
        if cached["settings"] == settings and time.monotonic() - cached["at"] < PRICE_CACHE_SECONDS:
            return cached["value"]
        price = await _from_own_node("/api/v1/prices", lambda r: _usd(r.json()["USD"]))
        source = "mempool"
        if price is None:
            price, source = await _first_public(
                [(KRAKEN_TICKER_URL, _kraken_price), (BITSTAMP_TICKER_URL, _bitstamp_price)], "BTC price")
        price = {**price, "source": source, "at": now_iso()}
        _price_cache.update(settings=settings, at=time.monotonic(), value=price)
        return price


def _height(resp) -> dict:
    return {"height": int(resp.text.strip())}


async def get_block_height() -> dict:
    """
    The current block height: the own mempool server, or Blockchain.info,
    Blockstream, mempool.space. 503 when prices are off or not chosen, 502
    when the chosen source fails.
    """
    settings = outbound.current()
    cached = _height_cache
    if cached["settings"] == settings and time.monotonic() - cached["at"] < PRICE_CACHE_SECONDS:
        return cached["value"]
    height = await _from_own_node("/api/blocks/tip/height", _height)
    if height is None:
        height, _ = await _first_public(
            [(BLOCKCHAIN_INFO_HEIGHT_URL, _height), (BLOCKSTREAM_HEIGHT_URL, _height), (MEMPOOL_HEIGHT_URL, _height)],
            "block height",
        )
    _height_cache.update(settings=settings, at=time.monotonic(), value=height)
    return height
