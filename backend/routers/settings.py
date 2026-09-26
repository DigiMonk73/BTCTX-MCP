"""
backend/routers/settings.py

App settings (logged-in only): the tax timezone, which decides tax-year
boundaries, Form 8949 dates and holding-period anniversaries; and what the
Mac app's launcher reports (port, whether this session is on another port).
Mounted at /api/settings.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services import mcp_key
from backend.services.desktop import desktop_info
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
def put_tax_timezone_setting(payload: TaxTimezone, request: Request, db: Session = Depends(get_db)):
    """
    Save the tax timezone and recalculate: holding periods are decided on
    calendar dates in this timezone, so stored results may change. Login
    only: it moves tax years, so no API key or AI assistant key.
    """
    _require_login(request)
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


@router.get("/desktop")
def get_desktop_info():
    """Mac app details for the UI; {"desktop": false, ...} everywhere else."""
    return desktop_info()


# ---------------------------------------------------------------------------
# AI assistant access (Mac app): login only, never with the key itself, so a
# key can't turn its own access back on or mint a new one.
# ---------------------------------------------------------------------------
def _require_login(request: Request) -> None:
    """A logged-in session (get_current_user already checked it is current)."""
    if not request.session.get("user_id"):
        raise HTTPException(status_code=403, detail="This setting can only be changed while logged in.")


class AiAccess(BaseModel):
    on: bool


def _ai_access_state(db: Session) -> dict:
    path = mcp_key.mcp_file()
    return {
        "available": path is not None,
        "on": mcp_key.access_on(db),
        "key_file": str(path) if path else None,
    }


@router.get("/ai-access")
def get_ai_access(request: Request, db: Session = Depends(get_db)):
    """available: False outside the Mac app (log in with username/password there)."""
    _require_login(request)
    return _ai_access_state(db)


@router.put("/ai-access")
def put_ai_access(payload: AiAccess, request: Request, db: Session = Depends(get_db)):
    _require_login(request)
    if not mcp_key.enabled():
        raise HTTPException(status_code=400, detail="AI assistant keys exist only in the Mac app.")
    mcp_key.set_access(db, payload.on)
    return _ai_access_state(db)


@router.post("/ai-access/reset-key")
def reset_ai_key(request: Request, db: Session = Depends(get_db)):
    """New key in the key file; copies of the old one stop working."""
    _require_login(request)
    if not mcp_key.enabled():
        raise HTTPException(status_code=400, detail="AI assistant keys exist only in the Mac app.")
    mcp_key.rotate(db)
    return _ai_access_state(db)
