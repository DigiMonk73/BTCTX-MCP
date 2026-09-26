"""
backend/services/outbound.py

The only place the backend creates HTTP clients for outside services (BTC
prices, block height, the price-history download), so one place applies
the owner's network settings (Settings -> Privacy & network, stored in
app_settings):

- live data: on (default) or off. Off, BitcoinTX asks no public service
  for anything: the live price, block height and chart answer 503, and past
  prices come only from the local price history (a missing day is a 422).
- your own mempool server: a URL (e.g. http://umbrel.local:3006 or an
  .onion). Asked first for the live price and block height; still used
  when live data is off, since it's yours.
- a proxy for every outside request, e.g. socks5h://127.0.0.1:9050 (Tor).

Defaults are today's behavior: public services, no proxy. A test checks no
other backend module builds its own client.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

TIMEOUT = 10.0
LIVE_KEY, MEMPOOL_KEY, PROXY_KEY = "live_data", "mempool_url", "proxy_url"
PROXY_SCHEMES = ("socks5", "socks5h", "http", "https")

# Tests set this to an httpx.MockTransport to fake the outside services.
_transport: Optional[httpx.AsyncBaseTransport] = None


@dataclass(frozen=True)
class NetworkSettings:
    live_data: bool = True
    mempool_url: Optional[str] = None
    proxy_url: Optional[str] = None


_current = NetworkSettings()


def current() -> NetworkSettings:
    return _current


def as_dict() -> dict:
    return asdict(_current)


def _get(db: Session, key: str) -> Optional[str]:
    from backend.models.app_setting import AppSetting

    row = db.get(AppSetting, key)
    return row.value if row else None


def _set(db: Session, key: str, value: Optional[str]) -> None:
    from backend.models.app_setting import AppSetting

    row = db.get(AppSetting, key)
    if value is None:
        if row:
            db.delete(row)
    elif row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.flush()


def load(db: Session) -> NetworkSettings:
    """Read the settings from the database (at startup, after a restore)."""
    global _current
    _current = NetworkSettings(
        live_data=_get(db, LIVE_KEY) != "off",
        mempool_url=_get(db, MEMPOOL_KEY),
        proxy_url=_get(db, PROXY_KEY),
    )
    return _current


def _clean_url(value: Optional[str], schemes, what: str) -> Optional[str]:
    value = (value or "").strip()
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in schemes or not parsed.hostname:
        raise HTTPException(
            status_code=422,
            detail=f"{what} must look like {schemes[0]}://host:port (one of: {', '.join(schemes)}).",
        )
    if parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail=f"{what} can't contain a username or password.")
    return value.rstrip("/")


def save(db: Session, live_data: bool, mempool_url: Optional[str], proxy_url: Optional[str]) -> NetworkSettings:
    mempool = _clean_url(mempool_url, ("http", "https"), "Your mempool server")
    proxy = _clean_url(proxy_url, PROXY_SCHEMES, "The proxy")
    _set(db, LIVE_KEY, "on" if live_data else "off")
    _set(db, MEMPOOL_KEY, mempool)
    _set(db, PROXY_KEY, proxy)
    db.commit()
    return load(db)


def live_data_on() -> bool:
    return _current.live_data


def require_live_data() -> None:
    if not _current.live_data:
        raise HTTPException(status_code=503, detail="Live data is off (Settings → Privacy & network).")


def async_client(timeout: float = TIMEOUT) -> httpx.AsyncClient:
    if _transport is not None:
        return httpx.AsyncClient(timeout=timeout, transport=_transport)
    return httpx.AsyncClient(timeout=timeout, proxy=_current.proxy_url)
