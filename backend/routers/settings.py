"""
App settings: the tax timezone, which decides tax-year boundaries, Form
8949 dates and holding-period anniversaries; what the Mac app's launcher
reports (port, whether this session is on another port); AI access and the
AI key; privacy & network. Changing any of them is login only. Mounted at
/api/settings.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services import ai_key, hourly_prices, mempool_trust, outbound, past_years
from backend.services.desktop import desktop_info
from backend.services.past_year_writes import TaxTimezone as TaxTimezoneWrite
from backend.services.tax_time import (
    fill_tax_timezone, get_tax_timezone_name, never_chosen_with_transactions, validate_timezone,
)

router = APIRouter()


class TaxTimezone(BaseModel):
    timezone: str


class ChosenTaxTimezone(TaxTimezone):
    # Settings' Save sends it (#334). A page from before then, still open
    # after an update, never does: its login set the timezone with this PUT.
    chosen: bool = False


RELOAD_TO_CHOOSE = (
    "Not saved: this page is from before BitcoinTX's update. Reload it, then choose the tax timezone in Settings."
)


@router.get("/tax-timezone")
def get_tax_timezone_setting(db: Session = Depends(get_db)):
    """source: 'setting' (chosen), 'env' (BTCTX_TIMEZONE) or 'default' (UTC, never set)."""
    name, source = get_tax_timezone_name(db)
    return {"timezone": name, "source": source}


@router.put("/tax-timezone")
def put_tax_timezone_setting(payload: ChosenTaxTimezone, request: Request, confirm: str | None = None,
                             db: Session = Depends(get_db)):
    """
    Save the tax timezone and recalculate: holding periods are decided on
    calendar dates in this timezone, so stored results may change. Login
    only: it moves tax years, so never the AI key. While none was ever
    chosen and the ledger has transactions, only with `chosen` (Settings):
    otherwise a 409, so an old page's login can't set it (#334). One that
    changes the figures of an earlier tax year (a holding period, a sale's
    tax year) answers 409 with the years, what changes and a fingerprint,
    and saves nothing until sent again with ?confirm=<fingerprint>; a copy
    of the database comes first.
    """
    _require_login(request)
    if not payload.chosen and never_chosen_with_transactions(db):
        raise HTTPException(status_code=409, detail=RELOAD_TO_CHOOSE)
    try:
        validate_timezone(payload.timezone)
    except ValueError as exc:  # its own words: an unknown timezone
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        saved = past_years.save(TaxTimezoneWrite(payload.timezone), db, confirm, by_ai=False)
    except Exception:  # never its text: an unexpected one answers a fixed sentence (#430)
        db.rollback()
        raise
    if isinstance(saved, JSONResponse):
        return saved  # the warning
    return {"timezone": payload.timezone, "source": "setting"}


@router.post("/tax-timezone/fill")
def fill_tax_timezone_setting(payload: TaxTimezone, request: Request, db: Session = Depends(get_db)):
    """
    The login page's fill (#334): this browser's timezone, saved only while
    none was ever chosen and the ledger has no transactions (nothing to
    recalculate then). Otherwise nothing changes. {"timezone", "source",
    "filled"}. Login only, like the change above.
    """
    _require_login(request)
    try:
        filled = fill_tax_timezone(db, payload.timezone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    name, source = get_tax_timezone_name(db)
    return {"timezone": name, "source": source, "filled": filled}


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
    mempool_url: str | None = Field(default=None, max_length=300)
    mempool_fallback: bool = False
    proxy_url: str | None = Field(default=None, max_length=300)
    # Where the choice was made, for its record (#145, 2.9): the first-run
    # question on the Dashboard, or Settings
    via: Literal["first-run", "settings"] = "settings"


@router.get("/network")
def get_network_settings():
    return outbound.as_dict()


@router.put("/network")
def put_network_settings(payload: NetworkSettingsIn, request: Request, db: Session = Depends(get_db)):
    _require_login(request)
    outbound.save(db, payload.price_source, payload.mempool_url, payload.mempool_fallback, payload.proxy_url,
                  payload.via)
    hourly_prices.download_if_public()
    return outbound.as_dict()


class HistoryWithoutTorIn(BaseModel):
    answer: Literal["yes", "no"]
    # Where it was answered, for its record: the Dashboard's question, or Settings
    via: Literal["dashboard", "settings"] = "settings"


@router.put("/network/history-without-tor")
def put_history_without_tor(payload: HistoryWithoutTorIn, request: Request, db: Session = Depends(get_db)):
    """
    The owner's answer to "Download the price history once without Tor?"
    (#241): Yes lets Bitstamp's fixed-block history downloads go directly,
    and they're asked again at once. Login only, never the AI key; allowed
    while the server sets the price choice (the answer is the owner's).
    """
    _require_login(request)
    outbound.answer_history_without_tor(db, payload.answer, payload.via)
    if payload.answer == "yes":
        hourly_prices.try_again_now()
    return outbound.as_dict()


# A home server's certificate for your own Mempool (#188, services/mempool_trust.py):
# login only, never the AI key; only for the Mempool in use, at a home-network address.
class TrustedRootIn(BaseModel):
    sha256: str = Field(max_length=200)  # the fingerprint the owner was shown


def _mempool_in_use() -> str:
    url = outbound.current().own_node
    if not url:
        raise HTTPException(status_code=409, detail=(
            "A certificate can be trusted only for your own Mempool, while it's the price source in use."))
    return url


@router.get("/network/mempool-certificate")
async def get_mempool_certificate(request: Request):
    """The Mempool's root certificate, as shown to the owner before trusting it (asks the Mempool only)."""
    _require_login(request)
    return await mempool_trust.offer(_mempool_in_use())


@router.put("/network/mempool-certificate")
async def trust_mempool_certificate(payload: TrustedRootIn, request: Request, db: Session = Depends(get_db)):
    _require_login(request)
    url = _mempool_in_use()
    root = await mempool_trust.trusted(url, payload.sha256)
    outbound.trust_root(db, url, root.pem)
    return outbound.as_dict()


@router.delete("/network/mempool-certificate")
def forget_mempool_certificate(request: Request, db: Session = Depends(get_db)):
    _require_login(request)
    outbound.forget_root(db)
    return outbound.as_dict()
