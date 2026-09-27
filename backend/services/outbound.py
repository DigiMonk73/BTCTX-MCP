"""
backend/services/outbound.py

The only place the backend creates HTTP clients for outside services (BTC
prices, block height, the price-history download), so one place applies
the owner's network settings (Settings -> Privacy & network, stored in
app_settings):

- price source: where the live price, block height and past prices come
  from.
  - "unset": a fresh install before the owner chose; nothing is asked.
  - "off": nothing is asked. Past prices come only from those already
    stored (a missing day is a 422: type the value in).
  - "public": public price sites (services/bitcoin.py, price_history.py).
  - "mempool": the owner's own mempool server only, e.g.
    http://umbrel.local:3006 or an .onion; with "fall back to public sites"
    on, the public sites answer when it can't.
- a proxy for requests to public sites, e.g. socks5h://127.0.0.1:9050
  (Tor). The own mempool server is reached directly unless it's an .onion.

A test checks no other backend module builds its own client.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

TIMEOUT = 10.0
SOURCE_KEY, FALLBACK_KEY, MEMPOOL_KEY, PROXY_KEY = (
    "price_source", "mempool_fallback", "mempool_url", "proxy_url")
OLD_LIVE_KEY = "live_data"  # before v1.1.0: "on"/"off"
SOURCES = ("off", "public", "mempool")
PROXY_SCHEMES = ("socks5", "socks5h", "http", "https")

# Tests set this to an httpx.MockTransport to fake the outside services.
_transport: Optional[httpx.AsyncBaseTransport] = None


@dataclass(frozen=True)
class NetworkSettings:
    price_source: str = "unset"
    mempool_url: Optional[str] = None
    mempool_fallback: bool = False
    proxy_url: Optional[str] = None

    @property
    def own_node(self) -> Optional[str]:
        """The mempool server to ask, when it's the chosen source."""
        return self.mempool_url if self.price_source == "mempool" else None

    @property
    def public_allowed(self) -> bool:
        return self.price_source == "public" or (
            self.price_source == "mempool" and self.mempool_fallback)


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


def _upgrade_from_live_data(db: Session) -> Optional[str]:
    """
    Installs from before v1.1.0 keep what they did: live data off stays off
    (with their mempool server still asked), on stays public, and a mempool
    server keeps falling back to the public sites. A fresh install (no old
    setting, no transaction) stays unset, so the owner is asked.
    """
    from backend.models.transaction import Transaction

    live = _get(db, OLD_LIVE_KEY)
    mempool = _get(db, MEMPOOL_KEY)
    if live is None and mempool is None and db.query(Transaction.id).first() is None:
        return None
    if mempool:
        source, fallback = "mempool", live != "off"
    else:
        source, fallback = ("off" if live == "off" else "public"), False
    _set(db, SOURCE_KEY, source)
    _set(db, FALLBACK_KEY, "on" if fallback else "off")
    _set(db, OLD_LIVE_KEY, None)
    db.commit()
    return source


def load(db: Session) -> NetworkSettings:
    """Read the settings from the database (at startup, after a restore)."""
    global _current
    source = _get(db, SOURCE_KEY) or _upgrade_from_live_data(db)
    _current = NetworkSettings(
        price_source=source if source in SOURCES else "unset",
        mempool_url=_get(db, MEMPOOL_KEY),
        mempool_fallback=_get(db, FALLBACK_KEY) == "on",
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


def save(
    db: Session,
    price_source: str,
    mempool_url: Optional[str],
    mempool_fallback: bool,
    proxy_url: Optional[str],
) -> NetworkSettings:
    if price_source not in SOURCES:
        raise HTTPException(status_code=422, detail=f"Price source must be one of: {', '.join(SOURCES)}.")
    mempool = _clean_url(mempool_url, ("http", "https"), "Your mempool server")
    proxy = _clean_url(proxy_url, PROXY_SCHEMES, "The proxy")
    if price_source == "mempool" and not mempool:
        raise HTTPException(status_code=422, detail="Enter your mempool server's address to use it.")
    _set(db, SOURCE_KEY, price_source)
    _set(db, MEMPOOL_KEY, mempool)
    _set(db, FALLBACK_KEY, "on" if mempool_fallback else "off")
    _set(db, PROXY_KEY, proxy)
    db.commit()
    return load(db)


def refuse_public() -> HTTPException:
    """503 saying why no public price site may be asked."""
    s = _current
    if s.price_source == "mempool":
        detail = ("Your mempool server didn't answer, and falling back to public price sites is off "
                  "(Settings → Privacy & network).")
    elif s.price_source == "off":
        detail = "Price lookups are off (Settings → Privacy & network)."
    else:
        detail = "Choose where BitcoinTX gets prices: Settings → Privacy & network."
    return HTTPException(status_code=503, detail=detail)


def require_public() -> None:
    if not _current.public_allowed:
        raise refuse_public()


def async_client(timeout: float = TIMEOUT) -> httpx.AsyncClient:
    """A client for public sites: through the proxy when one is set."""
    if _transport is not None:
        return httpx.AsyncClient(timeout=timeout, transport=_transport)
    return httpx.AsyncClient(timeout=timeout, proxy=_current.proxy_url)


def own_node_client(timeout: float = TIMEOUT) -> httpx.AsyncClient:
    """
    A client for the owner's mempool server: direct (it's on their network
    or their StartOS), except an .onion, which needs the proxy.
    """
    if _transport is not None:
        return httpx.AsyncClient(timeout=timeout, transport=_transport)
    host = urlparse(_current.mempool_url or "").hostname or ""
    proxy = _current.proxy_url if host.endswith(".onion") else None
    return httpx.AsyncClient(timeout=timeout, proxy=proxy)
