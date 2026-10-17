import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services import bitcoin, hourly_prices, price_history, price_status

router = APIRouter(
    tags=["Bitcoin"]
)


@router.get("/price", summary="Get current Bitcoin price in USD")
async def get_current_bitcoin_price():
    """
    The current BTC price (USD) from the chosen source (services/bitcoin.py):
    503 when prices are off or not chosen, 502 when the chosen source fails.
    """
    return await bitcoin.get_current_price()


@router.get("/price/status", summary="Where newer prices come from now, and the hourly history")
def get_price_status():
    """
    The status line's facts (services/price_status.py): the choice, where
    the last price came from and when, the last problem and why, and the
    hourly history's download. Never makes a request. Login only: the AI
    key isn't allowed here (services/ai_key.py, AI_KEY_ROUTES).
    """
    return price_status.status()


@router.get("/price/history", summary="Get historical Bitcoin price (one day or one moment)")
def get_historical_bitcoin_price(date: str | None = None, at: str | None = None, db: Session = Depends(get_db)):
    """
    A past BTC price (USD) from the local price history:
    - at (an ISO 8601 time, e.g. 2025-03-01T14:47:00Z): the price that
      values that moment, the one the server uses for income, spends and
      fees: the opening price of its UTC hour, else its UTC day's 00:00
      price (services/hourly_prices.py); "moment" says which;
    - date (YYYY-MM-DD): that UTC day's 00:00 price (services/price_history.py).
    Each answer says where the price came from ("source": "bitstamp",
    "kraken", "mempool"; #145).
    400 for a bad or future date or time, 422 when no price is available.
    """
    if at is not None:
        return _price_at(at, db)
    if date is None:
        raise HTTPException(status_code=400, detail="Give a date (YYYY-MM-DD) or a time (at).")
    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    if day > datetime.now(timezone.utc).date():
        raise HTTPException(status_code=400, detail="Date cannot be in the future.")
    price = price_history.daily_price(db, day)
    return {"USD": float(price), "source": price_history.stored_source(db, day) or ""}


# An offset's "+" sent unencoded arrives as a space: "…14:47:00 02:00"
_SPACED_OFFSET = re.compile(r"(\d\d:\d\d(?::\d\d(?:\.\d+)?)?) (\d\d:?\d\d)$")


def _price_at(at: str, db: Session) -> dict:
    text = _SPACED_OFFSET.sub(r"\1+\2", at.strip()).replace("z", "Z").replace("Z", "+00:00")
    try:
        when = datetime.fromisoformat(text)
        when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
        when.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise HTTPException(status_code=400, detail="Invalid time. Use ISO 8601, e.g. 2025-03-01T14:47:00Z.")
    if when > datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Time cannot be in the future.")
    priced = hourly_prices.price_at(db, when)
    return {"USD": float(priced.usd), "moment": priced.moment, "at": priced.at.isoformat().replace("+00:00", "Z"),
            "source": priced.source}


@router.get("/blockheight", summary="Get current Bitcoin block height")
async def get_current_block_height():
    """
    The current block height from the chosen source (services/bitcoin.py):
    503 when prices are off or not chosen, 502 when the chosen source fails.
    """
    return await bitcoin.get_block_height()
