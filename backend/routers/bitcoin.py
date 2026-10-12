from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services import bitcoin, price_history, price_status

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


@router.get("/blockheight", summary="Get current Bitcoin block height")
async def get_current_block_height():
    """
    The current block height from the chosen source (services/bitcoin.py):
    503 when prices are off or not chosen, 502 when the chosen source fails.
    """
    return await bitcoin.get_block_height()
