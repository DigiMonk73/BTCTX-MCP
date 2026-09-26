from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services import bitcoin, outbound, price_history

router = APIRouter(
    tags=["Bitcoin"]
)


def _live_or_own_node() -> None:
    """503 when live data is off and there's no own mempool server to ask."""
    if not outbound.current().mempool_url:
        outbound.require_live_data()

@router.get("/price", summary="Get current Bitcoin price in USD")
async def get_current_bitcoin_price():
    """
    Endpoint to retrieve the current Bitcoin price (USD).
    Leverages fallback logic in services/bitcoin.py.
    Raises HTTP 502 if all providers fail.
    """
    _live_or_own_node()
    return await bitcoin.get_current_price()


@router.get("/price/history", summary="Get historical Bitcoin price (one date)")
def get_historical_bitcoin_price(date: str, db: Session = Depends(get_db)):
    """
    The BTC price (USD) for a UTC day (YYYY-MM-DD): its 00:00 UTC price from
    the local price history, the same one the server uses for income, spends
    and fees (services/price_history.py). 400 for a bad or future date, 422
    when no price is available.
    """
    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    if day > datetime.now(timezone.utc).date():
        raise HTTPException(status_code=400, detail="Date cannot be in the future.")
    price = price_history.daily_price(db, day)
    db.commit()  # keep a newly downloaded price
    return {"USD": float(price)}


@router.get("/price/history/timeseries", summary="Get multi-day BTC price data")
async def get_btc_price_time_series(
    days: int = Query(7, ge=1, le=365, description="Number of days (1 to 365)")
):
    """
    Returns daily BTC prices for the last `days` days in USD,
    suitable for line charts (time-series).

    The services/bitcoin.py should have get_time_series(days)
    that fetches from CoinGecko (fallback to Kraken, etc.).
    """
    outbound.require_live_data()
    return await bitcoin.get_time_series(days)


@router.get("/blockheight", summary="Get current Bitcoin block height")
async def get_current_block_height():
    """
    Endpoint to retrieve the current Bitcoin block height.
    Uses Blockchain.info as primary, with Blockstream and Mempool.space as fallbacks.
    Raises HTTP 502 if all providers fail.
    """
    _live_or_own_node()
    return await bitcoin.get_block_height()
