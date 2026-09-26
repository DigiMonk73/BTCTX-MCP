"""
backend/routers/review.py

GET /api/review: the read-only Ledger review (backend/services/review.py).
Login, API key or the AI assistant key; it changes no transaction (it may
store BTC prices it had to download).

POST /api/review/fee-prices: set the listed transfers' fee values to the
day's price and recalculate. Login only: it changes tax figures.
"""

from typing import List

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services.review import apply_fee_prices, build_review
from backend.session_auth import require_login

router = APIRouter()


@router.get("")
def get_review(db: Session = Depends(get_db)):
    review = build_review(db)
    db.commit()  # keep downloaded prices; no transaction was touched
    return review


class FeePriceFix(BaseModel):
    ids: List[int] = Field(..., min_length=1, max_length=10000)


@router.post("/fee-prices")
def fix_fee_prices(payload: FeePriceFix, request: Request, db: Session = Depends(get_db)):
    require_login(request, db)
    changes = apply_fee_prices(db, payload.ids)
    return {
        "changed": [{"id": c["id"], "old": str(c["old"]), "new": str(c["new"])} for c in changes],
        "recalculated": bool(changes),
    }
