from datetime import datetime, timezone, timedelta
from fastapi import HTTPException

from backend.services import outbound

# ---------------------------------------------------------------------
# API endpoints for primary and backup services
# ---------------------------------------------------------------------
COINGECKO_PRICE_URL = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=bitcoin&vs_currencies=usd"
)

# CoinGecko single-date historical (DD-MM-YYYY format)
COINGECKO_HISTORY_URL = (
    "https://api.coingecko.com/api/v3/coins/bitcoin/history?date={date}"
)

# CoinGecko multi-day market chart endpoint (e.g., last 7 days)
COINGECKO_TIMESERIES_URL = (
    "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    "?vs_currency=usd&days={days}&interval=daily"
)

KRAKEN_TICKER_URL = "https://api.kraken.com/0/public/Ticker?pair=XBTUSD"
KRAKEN_OHLC_URL = (
    "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440&since={since}"
)

COINDESK_CURRENT_URL = "https://api.coindesk.com/v1/bpi/currentprice/USD.json"

# CoinDesk single-date historical (YYYY-MM-DD for start/end)
COINDESK_HISTORICAL_URL = (
    "https://api.coindesk.com/v1/bpi/historical/close.json?start={date}&end={date}"
)


# ---------------------------------------------------------------------
# 1) Current Bitcoin Price (live)
# ---------------------------------------------------------------------
async def get_current_price():
    """
    Fetch the current Bitcoin price in USD from multiple sources,
    using CoinGecko as primary, then Kraken, then CoinDesk if needed.
    Raises HTTP 502 if all fail.
    """
    async with outbound.async_client() as client:
        # 1. Try CoinGecko API for current price
        try:
            resp = await client.get(COINGECKO_PRICE_URL)
        except Exception:
            resp = None
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
                # CoinGecko simple price returns {"bitcoin": {"usd": <price>}}
                price = data["bitcoin"]["usd"]
                if price is not None:
                    return {"USD": price}
            except Exception:
                pass

        # 2. If CoinGecko failed, try Kraken API for current price
        try:
            resp = await client.get(KRAKEN_TICKER_URL)
        except Exception:
            resp = None
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
                # Kraken returns an 'error' list; must be empty for success
                if data.get("error") == []:
                    result = data.get("result")
                    if result:
                        # The BTC/USD pair key is e.g. "XXBTZUSD" => look at "c" for last trade
                        pair = next(iter(result))
                        price_str = result[pair]["c"][0]  # last trade price
                        price = float(price_str)
                        return {"USD": price}
            except Exception:
                pass

        # 3. If Kraken failed, try CoinDesk API for current price
        try:
            resp = await client.get(COINDESK_CURRENT_URL)
        except Exception:
            resp = None
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
                # CoinDesk current price is at data["bpi"]["USD"]["rate_float"]
                price = data["bpi"]["USD"]["rate_float"]
                if price is not None:
                    return {"USD": price}
            except Exception:
                pass

    # If all APIs failed, raise an HTTP 502 Bad Gateway
    raise HTTPException(
        status_code=502,
        detail="Unable to retrieve current Bitcoin price from CoinGecko, Kraken, or backup API."
    )


# ---------------------------------------------------------------------
# 2) Single‐Date Historical Price
# ---------------------------------------------------------------------
async def get_historical_price(date: str):
    """
    Fetch the Bitcoin price (USD) for a specific date (YYYY-MM-DD),
    with failover from CoinGecko to Kraken to CoinDesk.

    Raises:
      - 400 if the date is invalid or in the future
      - 502 if all sources fail
    """
    # Validate date format
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    # Disallow future dates. Callers pass UTC dates, so compare with today in
    # UTC: the server's local date (the Mac app runs in the user's zone) is a
    # day behind UTC every evening in the Americas, and today's price was
    # refused then.
    if target_date > datetime.now(timezone.utc).date():
        raise HTTPException(status_code=400, detail="Date cannot be in the future.")

    # Format dates for each API
    coingecko_date = target_date.strftime("%d-%m-%Y")  # DD-MM-YYYY for CoinGecko
    coindesk_date = target_date.strftime("%Y-%m-%d")   # YYYY-MM-DD for CoinDesk

    async with outbound.async_client() as client:
        # 1. Try CoinGecko API for single-day historical price
        try:
            resp = await client.get(COINGECKO_HISTORY_URL.format(date=coingecko_date))
        except Exception:
            resp = None
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
                # CoinGecko returns price under data["market_data"]["current_price"]["usd"]
                market_data = data.get("market_data")
                if market_data and "current_price" in market_data:
                    price = market_data["current_price"].get("usd")
                    if price is not None:
                        return {"USD": price}
            except Exception:
                pass

        # 2. If CoinGecko failed, try Kraken daily OHLC for the given date
        #    Prepare Unix timestamp for the target date at 00:00:00 UTC
        dt_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        timestamp = int(dt_start.timestamp())
        try:
            resp = await client.get(KRAKEN_OHLC_URL.format(since=timestamp))
        except Exception:
            resp = None
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
                if data.get("error") == []:
                    result = data.get("result")
                    if result:
                        pair = next(iter(result))  # e.g., "XXBTZUSD"
                        ohlc_data = result.get(pair, [])
                        # Each OHLC entry => [time, open, high, low, close, vwap, volume, count]
                        for entry in ohlc_data:
                            if len(entry) >= 5 and int(entry[0]) == timestamp:
                                # Use the open price at 00:00 UTC of that day
                                price = float(entry[1])
                                return {"USD": price}
                        # No candle for that day: Kraken only returns its
                        # latest 720 days, whatever `since` asks for. Its
                        # first candle is another day's price, so don't use it.
            except Exception:
                pass

        # 3. If Kraken failed, try CoinDesk API for single-day historical price
        try:
            resp = await client.get(COINDESK_HISTORICAL_URL.format(date=coindesk_date))
        except Exception:
            resp = None
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
                # CoinDesk historical => data["bpi"] is a dict { "YYYY-MM-DD": <price> }
                bpi = data.get("bpi", {})
                if coindesk_date in bpi:
                    price = bpi[coindesk_date]
                    if price is not None:
                        return {"USD": price}
            except Exception:
                pass

    # If all sources fail, return an HTTP 502 error
    raise HTTPException(
        status_code=502,
        detail="Unable to retrieve Bitcoin price for the given date from CoinGecko, Kraken, or backup API."
    )


# ---------------------------------------------------------------------
# 3) Multi‐Day Time‐Series (For Charting)
# ---------------------------------------------------------------------
async def get_time_series(days: int = 7):
    """
    Fetch daily BTC prices for the last `days` days (1 <= days <= 365),
    returning a list of { time, price }. Primary: CoinGecko's 'market_chart'.
    Fallback: tries Kraken's OHLC if CoinGecko fails.

    Example output:
      [
        {"time": 1677024000000, "price": 23500.23},
        {"time": 1677110400000, "price": 23825.45},
        ...
      ]
    The 'time' is a UNIX timestamp in milliseconds (UTC), and 'price' is in USD.
    """
    async with outbound.async_client() as client:
        # 1. Try CoinGecko
        try:
            url = COINGECKO_TIMESERIES_URL.format(days=days)
            cg_resp = await client.get(url)
            cg_resp.raise_for_status()  # raises if status != 2xx
            data = cg_resp.json()

            # Expect data["prices"] => [ [ts_ms, price], [ts_ms, price], ... ]
            if "prices" in data:
                results = []
                for entry in data["prices"]:
                    if len(entry) == 2:
                        ts_ms, price_usd = entry
                        results.append({"time": int(ts_ms), "price": float(price_usd)})
                return results
        except Exception:
            pass

        # 2. Fallback: daily OHLC from Kraken
        #    We'll approximate N days by computing a 'since' timestamp for N days ago.
        #    Then parse each day from that up to the present.
        try:
            # e.g., 7 days ago from now
            dt_start = datetime.now(timezone.utc) - timedelta(days=days)
            since_ts = int(dt_start.timestamp())

            kr_resp = await client.get(KRAKEN_OHLC_URL.format(since=since_ts))
            kr_resp.raise_for_status()
            data = kr_resp.json()

            # If there's no error in data["error"], parse the "result"
            if data.get("error") == []:
                kr_result = data.get("result")
                if kr_result:
                    pair = next(iter(kr_result))  # e.g. "XXBTZUSD"
                    ohlc_list = kr_result.get(pair, [])
                    # Each OHLC entry => [time_sec, open, high, low, close, vwap, volume, count]
                    # We'll store them in ascending order
                    results = []
                    for row in ohlc_list:
                        if len(row) >= 5:
                            time_sec = int(row[0])
                            close_price = float(row[4])  # choose "close" as daily price
                            # Convert seconds to ms
                            time_ms = time_sec * 1000
                            results.append({"time": time_ms, "price": close_price})

                    # Sort by time ascending
                    results.sort(key=lambda r: r["time"])
                    return results
        except Exception:
            pass

    # If all fail
    raise HTTPException(
        status_code=502,
        detail="Unable to retrieve multi-day BTC data from CoinGecko or fallback."
    )


# ---------------------------------------------------------------------
# 4) Current Block Height
# ---------------------------------------------------------------------
BLOCKCHAIN_INFO_HEIGHT_URL = "https://blockchain.info/q/getblockcount"
BLOCKSTREAM_HEIGHT_URL = "https://blockstream.info/api/blocks/tip/height"
MEMPOOL_HEIGHT_URL = "https://mempool.space/api/blocks/tip/height"


async def get_block_height():
    """
    Fetch the current Bitcoin block height from multiple sources,
    using Blockchain.info as primary, then Blockstream, then Mempool.space.
    Raises HTTP 502 if all fail.
    """
    async with outbound.async_client() as client:
        # 1. Try Blockchain.info
        try:
            resp = await client.get(BLOCKCHAIN_INFO_HEIGHT_URL)
            if resp.status_code == 200:
                height = int(resp.text.strip())
                return {"height": height}
        except Exception:
            pass

        # 2. Try Blockstream.info
        try:
            resp = await client.get(BLOCKSTREAM_HEIGHT_URL)
            if resp.status_code == 200:
                height = int(resp.text.strip())
                return {"height": height}
        except Exception:
            pass

        # 3. Try Mempool.space
        try:
            resp = await client.get(MEMPOOL_HEIGHT_URL)
            if resp.status_code == 200:
                height = int(resp.text.strip())
                return {"height": height}
        except Exception:
            pass

    # If all APIs failed, raise an HTTP 502 Bad Gateway
    raise HTTPException(
        status_code=502,
        detail="Unable to retrieve Bitcoin block height from any API source."
    )
