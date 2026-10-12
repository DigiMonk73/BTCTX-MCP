"""
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

The server can set them instead (the StartOS package does, from its Price
Source & Privacy action): when BTCTX_PRICE_SOURCE is set, it and
BTCTX_MEMPOOL_URL, BTCTX_MEMPOOL_FALLBACK and BTCTX_PROXY_URL replace the
stored settings, which stay untouched underneath (an install with none gets
"unset": _mark_unchosen), and Settings shows them read-only ("managed"). A
mempool choice may come without an address (StartOS while Mempool isn't
installed): then nothing answers but the fallback. An invalid value turns
price lookups off rather than guessing ("invalid"). BTCTX_HOST=startos only
changes words: where a server-set choice is changed (host()).

A test checks no other backend module builds its own client. The one
exception is an admin's command, not the app: `python -m backend.cli
install-draft-forms` (services/reports/draft_forms.py) fetches the IRS's
draft forms from irs.gov when run on a test install.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

TIMEOUT = 10.0
SOURCE_KEY, FALLBACK_KEY, MEMPOOL_KEY, PROXY_KEY = (
    "price_source", "mempool_fallback", "mempool_url", "proxy_url")
OLD_LIVE_KEY = "live_data"  # before v1.1.0: "on"/"off"
SOURCES = ("off", "public", "mempool")
PROXY_SCHEMES = ("socks5", "socks5h", "http", "https")
ENV_SOURCE, ENV_FALLBACK, ENV_MEMPOOL, ENV_PROXY = (
    "BTCTX_PRICE_SOURCE", "BTCTX_MEMPOOL_FALLBACK", "BTCTX_MEMPOOL_URL", "BTCTX_PROXY_URL")
ENV_TRUE, ENV_FALSE = ("on", "true", "1", "yes"), ("off", "false", "0", "no", "")
SETTINGS_PAGE = "Settings → Privacy & network"
SET_IN_STARTOS = "StartOS's Price Source & Privacy action"
SET_BY_DOCKER = f"this server's {ENV_SOURCE} setting"
# Where the app runs: StartOS's package sets BTCTX_HOST=startos; the Mac
# app is known by its launcher's BTCTX_DESKTOP; anything else is a server.
ENV_HOST, HOSTS = "BTCTX_HOST", ("mac", "server", "startos")

# Tests set this to an httpx.MockTransport to fake the outside services.
_transport: httpx.AsyncBaseTransport | None = None


@dataclass(frozen=True)
class NetworkSettings:
    price_source: str = "unset"
    mempool_url: str | None = None
    mempool_fallback: bool = False
    proxy_url: str | None = None
    managed: bool = False  # set by the server (environment), not in Settings
    invalid: bool = False  # the server's settings are invalid: nothing is asked

    @property
    def own_node(self) -> str | None:
        """The mempool server to ask, when it's the chosen source."""
        return self.mempool_url if self.price_source == "mempool" else None

    @property
    def public_allowed(self) -> bool:
        return self.price_source == "public" or (
            self.price_source == "mempool" and self.mempool_fallback)


_current = NetworkSettings()


def current() -> NetworkSettings:
    return _current


def host() -> str:
    """Where BitcoinTX runs: "mac", "startos" or "server" (Docker, source).
    Only the words change with it: where a server-set choice is changed."""
    from backend.services.desktop import is_desktop

    named = os.environ.get(ENV_HOST, "").strip().lower()
    if named in HOSTS:
        return named
    return "mac" if is_desktop() else "server"


def as_dict() -> dict:
    return {**asdict(_current), "host": host()}


def where_to_change() -> str:
    """Where the owner changes the price choice in use."""
    if not _current.managed:
        return SETTINGS_PAGE
    return SET_IN_STARTOS if host() == "startos" else SET_BY_DOCKER


def _get(db: Session, key: str) -> str | None:
    from backend.models.app_setting import AppSetting

    row = db.get(AppSetting, key)
    return row.value if row else None


def _set(db: Session, key: str, value: str | None) -> None:
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


def _upgrade_from_live_data(db: Session) -> str | None:
    """
    Installs from before v1.1.0 keep what they did: live data off stays off
    (with their mempool server still asked), on stays public, and a mempool
    server keeps falling back to the public sites. One that never touched
    those settings kept public prices if it stored any past ones (it
    downloaded them). Anything else stays unset, so the owner is asked: a
    v1.1.0+ install with entries but no choice yet has no stored prices,
    since nothing is asked before the choice. Entries alone prove nothing.
    """
    from backend.models.btc_price import BtcPriceDaily

    live = _get(db, OLD_LIVE_KEY)
    mempool = _get(db, MEMPOOL_KEY)
    if live is None and mempool is None and db.query(BtcPriceDaily.day).first() is None:
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


def _mark_unchosen(db: Session) -> None:
    """
    While the server sets the source, prices get stored with no choice made
    in the app. Record that none was ("unset", as a restore does), so a later
    switch back to the app's own setting (StartOS: Choose in BitcoinTX) asks
    the owner instead of taking those prices for a pre-1.1.0 install's public
    choice (#134). A pre-1.1.0 install's own old settings are its choice and
    are left for _upgrade_from_live_data.
    """
    if any(_get(db, key) for key in (SOURCE_KEY, OLD_LIVE_KEY, MEMPOOL_KEY)):
        return
    _set(db, SOURCE_KEY, "unset")
    db.commit()


def from_env() -> NetworkSettings | None:
    """The settings the server sets (BTCTX_PRICE_SOURCE and co.), or None."""
    source = os.environ.get(ENV_SOURCE, "").strip().lower()
    if not source:
        return None
    try:
        if source not in SOURCES:
            raise ValueError(f"{ENV_SOURCE} must be one of: {', '.join(SOURCES)}.")
        fallback = os.environ.get(ENV_FALLBACK, "").strip().lower()
        if fallback not in ENV_TRUE + ENV_FALSE:
            raise ValueError(f"{ENV_FALLBACK} must be on or off.")
        settings = NetworkSettings(
            price_source=source,
            mempool_url=_clean_url(os.environ.get(ENV_MEMPOOL), ("http", "https"), ENV_MEMPOOL),
            mempool_fallback=fallback in ENV_TRUE,
            proxy_url=_clean_url(os.environ.get(ENV_PROXY), PROXY_SCHEMES, ENV_PROXY),
            managed=True,
        )
    except (ValueError, HTTPException) as exc:
        logger.error("Price lookups are off: the server's price settings are invalid: %s",
                     getattr(exc, "detail", exc))
        return NetworkSettings(price_source="off", managed=True, invalid=True)
    logger.info(
        "Price settings from the server: source %s, mempool server %s, fallback to public sites %s, proxy %s",
        settings.price_source, settings.mempool_url or "none", "on" if settings.mempool_fallback else "off",
        "set" if settings.proxy_url else "none")
    return settings


def snapshot(db: Session) -> dict:
    """The owner's own price settings (not the server's), to keep across a restore."""
    kept = {key: _get(db, key) for key in (FALLBACK_KEY, MEMPOOL_KEY, PROXY_KEY)}
    # Not chosen yet stays "unset": a restored database's stored prices must
    # not pass for a pre-1.1.0 install's public choice (_upgrade_from_live_data)
    kept[SOURCE_KEY] = _get(db, SOURCE_KEY) or "unset"
    kept[OLD_LIVE_KEY] = None
    return kept


def carry_over(db: Session, before: dict) -> NetworkSettings:
    """
    After a restore, put back the price settings from before it (owner
    decision 2026-09-29): a backup from before a switch to Tor or Off must
    not ask the public sites directly again. As for the AI key and login.
    """
    for key, value in before.items():
        _set(db, key, value)
    db.commit()
    return load(db)


def load(db: Session, upgrade: bool = True) -> NetworkSettings:
    """
    Read the settings (at startup, after a restore): the server's, else the
    database's. `upgrade=False` (a command-line run, which on StartOS may lack
    the server's variables) never works out a pre-1.1.0 install's choice:
    the app's start does that (#134).
    """
    global _current
    managed = from_env()
    if managed:
        _current = managed
        try:
            _mark_unchosen(db)
        except Exception:
            # The server's settings apply all the same; only the note is missing.
            db.rollback()
            logger.exception("Could not record that no price source was chosen in the app")
        return _current
    source = _get(db, SOURCE_KEY) or (_upgrade_from_live_data(db) if upgrade else None)
    _current = NetworkSettings(
        price_source=source if source in SOURCES else "unset",
        mempool_url=_get(db, MEMPOOL_KEY),
        mempool_fallback=_get(db, FALLBACK_KEY) == "on",
        proxy_url=_get(db, PROXY_KEY),
    )
    return _current


def _clean_url(value: str | None, schemes, what: str) -> str | None:
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
    mempool_url: str | None,
    mempool_fallback: bool,
    proxy_url: str | None,
) -> NetworkSettings:
    if _current.managed:
        raise HTTPException(status_code=409, detail=f"The price choice is set in {where_to_change()}, so it can't be changed here.")
    if price_source not in SOURCES:
        raise HTTPException(status_code=422, detail=f"Price source must be one of: {', '.join(SOURCES)}.")
    mempool = _clean_url(mempool_url, ("http", "https"), "Your mempool server")
    proxy = _clean_url(proxy_url, PROXY_SCHEMES, "The proxy")
    if price_source == "mempool" and not mempool:
        raise HTTPException(status_code=422, detail="Enter your mempool server's address to use it.")
    if price_source == "mempool" and _is_onion(mempool) and not proxy:
        raise HTTPException(status_code=422, detail=(
            "An .onion mempool server is reached through the proxy: set it below "
            "(e.g. Tor, socks5h://127.0.0.1:9050)."))
    _set(db, SOURCE_KEY, price_source)
    _set(db, MEMPOOL_KEY, mempool)
    _set(db, FALLBACK_KEY, "on" if mempool_fallback else "off")
    _set(db, PROXY_KEY, proxy)
    db.commit()
    return load(db)


def refuse_public() -> HTTPException:
    """Why no public price site may be asked: 503 when the owner chose
    Nobody or hasn't chosen yet (the Dashboard says why), 502 when the chosen
    mempool server is missing or didn't answer (an error, not a choice)."""
    s = _current
    where = where_to_change()
    if s.price_source == "mempool":
        if not s.mempool_url:  # only a server's setting: StartOS while Mempool isn't installed
            missing, fix = (("Mempool isn't installed on this server yet", "Install and start Mempool")
                            if host() == "startos" else (f"{ENV_MEMPOOL} isn't set", f"Set {ENV_MEMPOOL}"))
            return HTTPException(status_code=502, detail=(
                f"{missing}, and the backup (public price sites) is off. {fix}, or change the choice in {where}."))
        return HTTPException(status_code=502, detail=(
            f"Your Mempool didn't answer, and the backup (public price sites) is off. Change that in {where}."))
    if s.invalid:
        detail = f"This server's price settings aren't valid, so nothing is asked. Fix them in {where}."
    elif s.price_source == "off":
        detail = f"You chose Nobody for prices, so none is asked ({where})."
    else:
        detail = f"Prices: not chosen yet. Choose where BitcoinTX gets them in {where}."
    return HTTPException(status_code=503, detail=detail)


def require_public() -> None:
    if not _current.public_allowed:
        raise refuse_public()


def unreachable(exc: Exception) -> bool:
    """Whether a request never got an answer: no connection (a proxy down,
    e.g. Tor stopped), a proxy refusal or a timeout."""
    return isinstance(exc, httpx.TransportError)


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
    onion = _is_onion(_current.mempool_url)
    if onion and not _current.proxy_url:
        # Never directly: the system's DNS resolver would see the .onion name.
        raise RuntimeError("an .onion mempool server needs the proxy, and none is set")
    if _transport is not None:
        return httpx.AsyncClient(timeout=timeout, transport=_transport)
    return httpx.AsyncClient(timeout=timeout, proxy=_current.proxy_url if onion else None)


def _is_onion(url: str | None) -> bool:
    return (urlparse(url or "").hostname or "").endswith(".onion")
