"""
backend/routers/review.py

GET /api/review: the read-only Ledger review (backend/services/review.py).
Login, API key or the AI assistant key; it changes nothing.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services.review import build_review

router = APIRouter()


@router.get("")
def get_review(db: Session = Depends(get_db)):
    return build_review(db)
