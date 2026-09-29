"""
backend/services/bitcoin.py

The live BTC price and the block height, from the source the owner chose
(services/outbound.py): their own mempool server, or public sites (with a
mempool server, only if "fall back to public sites" is on). Nothing is asked
while no source is chosen or lookups are off.

Past-day prices are not here: services/price_history.py fetches them without
ever naming a date.
"""

import asyncio
import logging
import time
from typing import Callable, Optional

from fastapi import HTTPException

from backend.services import outbound

logger = logging.getLogger(__name__)

COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
KRAKEN_TICKER_URL = "https://api.kraken.com/0/public/Ticker?pair=XBTUSD"

BLOCKCHAIN_INFO_HEIGHT_URL = "https://blockchain.info/q/getblockcount"
BLOCKSTREAM_HEIGHT_URL = "https://blockstream.info/api/blocks/tip/height"
MEMPOOL_HEIGHT_URL = "https://mempool.space/api/blocks/tip/height"

# The live price is asked at most once a minute, however many tabs poll it;
# requests at the same moment (the dashboard and the sidebar) wait for one.
PRICE_CACHE_SECONDS = 60
_price_cache: dict = {"settings": None, "at": 0.0, "value": None}
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
    base = outbound.current().own_node
    if not base:
        return None
    try:
        async with outbound.own_node_client() as client:
            resp = await client.get(base + path)
            resp.raise_for_status()
            return parse(resp)
    except Exception as exc:
        logger.warning("Own mempool server %s%s failed: %s", base, path, exc)
        return None


async def _first_public(urls_and_parsers, what: str):
    """The first public site that answers, or 502 (naming the proxy when
    none could even be reached through it, e.g. Tor stopped)."""
    outbound.require_public()
    unreached = 0
    async with outbound.async_client() as client:
        for url, parse in urls_and_parsers:
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    value = parse(resp)
                    if value is not None:
                        return value
            except Exception as exc:
                unreached += outbound.unreachable(exc)
                logger.info("%s from %s failed: %s", what, url.split("/")[2], exc)
    if outbound.current().proxy_url and unreached == len(urls_and_parsers):
        raise HTTPException(status_code=502, detail=(
            f"No public site answered for the {what}: none could be reached through the proxy for "
            "public sites. If that's Tor, is it running? (On StartOS: start the Tor service.)"))
    raise HTTPException(status_code=502, detail=f"No public site answered for the {what}.")


def _coingecko_price(resp) -> Optional[dict]:
    price = resp.json()["bitcoin"]["usd"]
    return {"USD": float(price)} if price else None


def _kraken_price(resp) -> Optional[dict]:
    data = resp.json()
    if data.get("error"):
        return None
    pair = next(iter(data["result"]))
    return {"USD": float(data["result"][pair]["c"][0])}  # last trade


async def get_current_price() -> dict:
    """
    The current BTC price in USD: the own mempool server, or CoinGecko then
    Kraken. 503 when prices are off or not chosen, 502 when the chosen source fails.
    """
    settings = outbound.current()
    async with _one_at_a_time():
        cached = _price_cache
        if cached["settings"] == settings and time.monotonic() - cached["at"] < PRICE_CACHE_SECONDS:
            return cached["value"]
        price = await _from_own_node("/api/v1/prices", lambda r: {"USD": float(r.json()["USD"])})
        if price is None:
            price = await _first_public(
                [(COINGECKO_PRICE_URL, _coingecko_price), (KRAKEN_TICKER_URL, _kraken_price)], "BTC price")
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
    height = await _from_own_node("/api/blocks/tip/height", _height)
    if height is not None:
        return height
    return await _first_public(
        [(BLOCKCHAIN_INFO_HEIGHT_URL, _height), (BLOCKSTREAM_HEIGHT_URL, _height), (MEMPOOL_HEIGHT_URL, _height)],
        "block height",
    )
