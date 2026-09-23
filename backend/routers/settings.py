"""
backend/routers/settings.py

App settings (logged-in only). Currently: the tax timezone, which decides
tax-year boundaries, Form 8949 dates and holding-period anniversaries.
Mounted at /api/settings.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services.tax_time import get_tax_timezone_name, set_tax_timezone
from backend.services.transaction import recalculate_all_transactions

router = APIRouter()


class TaxTimezone(BaseModel):
    timezone: str


@router.get("/tax-timezone")
def get_tax_timezone_setting(db: Session = Depends(get_db)):
    """source: 'setting' (chosen), 'env' (BTCTX_TIMEZONE) or 'default' (UTC, never set)."""
    name, source = get_tax_timezone_name(db)
    return {"timezone": name, "source": source}


@router.put("/tax-timezone")
def put_tax_timezone_setting(payload: TaxTimezone, db: Session = Depends(get_db)):
    """
    Save the tax timezone and recalculate: holding periods are decided on
    calendar dates in this timezone, so stored results may change.
    """
    try:
        set_tax_timezone(db, payload.timezone)
        recalculate_all_transactions(db)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        db.rollback()
        raise
    return {"timezone": payload.timezone, "source": "setting"}
