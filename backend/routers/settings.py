"""
App settings: the tax timezone, which decides tax-year boundaries, Form
8949 dates and holding-period anniversaries; what the Mac app's launcher
reports (port, whether this session is on another port); AI access and the
AI key; privacy & network. Changing any of them is login only. Mounted at
/api/settings.
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services import ai_key, outbound
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
    only: it moves tax years, so never the AI key.
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


# AI access and the AI key (services/ai_key.py): login only, never with the
# key itself, so a key can't turn its own access back on or mint a new one.
def _require_login(request: Request) -> None:
    """A logged-in session (get_current_user already checked it is current)."""
    if not request.session.get("user_id"):
        raise HTTPException(status_code=403, detail="This setting can only be changed while logged in.")


class AiAccess(BaseModel):
    on: bool


def _ai_access_state(db: Session) -> dict:
    path = ai_key.key_file()
    return {
        "mode": ai_key.mode(),  # "mac": key file; "server": created in Settings
        "on": ai_key.access_on(db),
        "has_key": ai_key.has_key(db),
        "key_file": str(path) if path else None,
    }


def _require_mode(mode: str) -> None:
    if ai_key.mode() != mode:
        raise HTTPException(
            status_code=400,
            detail="In the Mac app the key is in its key file: use Reset key."
            if mode == "server" else "Only the Mac app has a key file: use New key.",
        )


@router.get("/ai-access")
def get_ai_access(request: Request, db: Session = Depends(get_db)):
    _require_login(request)
    return _ai_access_state(db)


@router.put("/ai-access")
def put_ai_access(payload: AiAccess, request: Request, db: Session = Depends(get_db)):
    _require_login(request)
    ai_key.set_access(db, payload.on)
    return _ai_access_state(db)


@router.post("/ai-key")
def create_ai_key(request: Request, db: Session = Depends(get_db)):
    """
    Docker/StartOS: a new AI key, replacing any old one. The response is the
    only time the key is shown; only its hash is kept.
    """
    _require_login(request)
    _require_mode("server")
    key = ai_key.create_key(db)
    return {**_ai_access_state(db), "key": key}


@router.delete("/ai-key")
def revoke_ai_key(request: Request, db: Session = Depends(get_db)):
    """Docker/StartOS: the AI key stops working; no key until a new one is made."""
    _require_login(request)
    _require_mode("server")
    ai_key.revoke(db)
    return _ai_access_state(db)


@router.post("/ai-access/reset-key")
def reset_ai_key(request: Request, db: Session = Depends(get_db)):
    """Mac app: new key in the key file; copies of the old one stop working."""
    _require_login(request)
    _require_mode("mac")
    ai_key.rotate(db)
    return _ai_access_state(db)


# Privacy & network (services/outbound.py): anyone logged in can read it;
# changing it is login only, never with the AI key.
class NetworkSettingsIn(BaseModel):
    price_source: Literal["off", "public", "mempool"]
    mempool_url: Optional[str] = Field(default=None, max_length=300)
    mempool_fallback: bool = False
    proxy_url: Optional[str] = Field(default=None, max_length=300)


@router.get("/network")
def get_network_settings():
    return outbound.as_dict()


@router.put("/network")
def put_network_settings(payload: NetworkSettingsIn, request: Request, db: Session = Depends(get_db)):
    _require_login(request)
    outbound.save(db, payload.price_source, payload.mempool_url, payload.mempool_fallback, payload.proxy_url)
    return outbound.as_dict()
