"""
GET /api/review: the read-only Ledger review (backend/services/review.py).
Login or the AI key; it changes no transaction (it may
store BTC prices it had to download).

POST /api/review/hourly-prices: price the listed transactions' values
priced at the day (or a whole tax year's) at their hour, after a backup
copy, and recalculate (services/hourly_review.py). Login only: it changes
tax figures.
"""


from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, conint
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services.hourly_review import apply_hourly_prices
from backend.services.review import build_review
from backend.session_auth import require_login

router = APIRouter()


@router.get("")
def get_review(db: Session = Depends(get_db)):
    review = build_review(db)
    db.commit()  # keep downloaded prices; no transaction was touched
    return review


class HourlyPrices(BaseModel):
    """The transactions to price at their hour: these ids, or a whole tax year."""
    # One SQL IN (...) each: well under SQLite's 32,766 variables
    ids: list[conint(ge=1, le=2**63 - 1)] | None = Field(default=None, min_length=1, max_length=10000)
    year: int | None = Field(default=None, ge=2009, le=2100)


@router.post("/hourly-prices")
def apply_hourly(payload: HourlyPrices, request: Request, db: Session = Depends(get_db)):
    require_login(request, db)
    if (payload.ids is None) == (payload.year is None):
        raise HTTPException(status_code=422, detail="Give the transactions' ids or a tax year, not both.")
    result = apply_hourly_prices(db, ids=payload.ids, year=payload.year)
    return {
        "changed": [{"id": c["id"], "moment": c["moment"],
                     "values": {f: [str(old), str(new)] for f, (old, new) in c["values"].items()}}
                    for c in result["changed"]],
        "backup": result["backup"],
        "recalculated": bool(result["changed"]),
    }
