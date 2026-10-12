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

With a choice made in the app, the server may lend its Tor
(BTCTX_TOR_PROXY_URL; StartOS's "Use Tor" with Choose in BitcoinTX): it is
the proxy then, locked on, and an invalid one asks nobody (server_tor).

A test checks no other backend module builds its own client. The one
exception is an admin's command, not the app: `python -m backend.cli
install-draft-forms` (services/reports/draft_forms.py) fetches the IRS's
draft forms from irs.gov when run on a test install.
"""

from __future__ import annotations

import json
import logging
import os
import ssl
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.services.desktop import is_desktop

logger = logging.getLogger(__name__)

TIMEOUT = 10.0
SOURCE_KEY, FALLBACK_KEY, MEMPOOL_KEY, PROXY_KEY = (
    "price_source", "mempool_fallback", "mempool_url", "proxy_url")
OLD_LIVE_KEY = "live_data"  # before v1.1.0: "on"/"off"
# The record of a choice made in the price card (#145, plan 2.9): when, and
# where ("first-run" or "settings"). Written only by save(), from
# PUT /api/settings/network (a login, never the AI key or a command).
CHOSEN_AT_KEY, CHOSEN_VIA_KEY = "price_choice_at", "price_choice_via"
CHOSEN_VIA = ("first-run", "settings")
# A home server's root certificate the owner trusts for their Mempool (#188,
# services/mempool_trust.py): {"url", "pem"}, for that Mempool address only
TRUSTED_ROOT_KEY = "mempool_trusted_root"
SOURCES = ("off", "public", "mempool")
PROXY_SCHEMES = ("socks5", "socks5h", "http", "https")
ENV_SOURCE, ENV_FALLBACK, ENV_MEMPOOL, ENV_PROXY = (
    "BTCTX_PRICE_SOURCE", "BTCTX_MEMPOOL_FALLBACK", "BTCTX_MEMPOOL_URL", "BTCTX_PROXY_URL")
# Tor on the server, for a choice made in the app (StartOS: the action's
# "Use Tor" with Choose in BitcoinTX, #145): used for every request that
# goes through a proxy, and locked on in Settings
ENV_TOR = "BTCTX_TOR_PROXY_URL"
ENV_TRUE, ENV_FALSE = ("on", "true", "1", "yes"), ("off", "false", "0", "no", "")
SETTINGS_PAGE = "Settings → Privacy & network"
SET_IN_STARTOS = "StartOS's Price Source & Privacy action"
# A server that doesn't say what it is may be StartOS before its package
# passes BTCTX_HOST: words that fit both
SET_BY_SERVER = "the server's price settings (on StartOS: the Price Source & Privacy action)"
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
    # A stored choice with no record of when it was made (#145, 2.9): nothing
    # is asked until the owner confirms it
    waiting: bool = False
    # proxy_url is the server's Tor (BTCTX_TOR_PROXY_URL), not the owner's
    tor_from_server: bool = False
    # The root certificate the owner trusts for this Mempool address (#188):
    # its requests are checked against it alone
    mempool_root: str | None = None

    @property
    def own_node(self) -> str | None:
        """The mempool server to ask, when it's the chosen source."""
        return self.mempool_url if self.price_source == "mempool" and self.asking else None

    @property
    def public_allowed(self) -> bool:
        return self.asking and (self.price_source == "public" or (
            self.price_source == "mempool" and self.mempool_fallback))

    @property
    def asking(self) -> bool:
        """Whether anything may be asked: not while a choice waits to be
        confirmed, nor while the server's settings are invalid (its Tor
        included: never around it)."""
        return not self.waiting and not self.invalid


_current = NetworkSettings()


def current() -> NetworkSettings:
    return _current


def host() -> str:
    """Where BitcoinTX runs: "mac", "startos" or "server" (Docker, source).
    Only the words change with it: where a server-set choice is changed."""
    named = os.environ.get(ENV_HOST, "").strip().lower()
    if named in HOSTS:
        return named
    return "mac" if is_desktop() else "server"


def as_dict() -> dict:
    """The settings in use, where BitcoinTX runs, and the record of the choice
    (`confirmed` is false while a stored choice waits for the owner)."""
    from backend.services import mempool_trust

    settings = asdict(_current)
    root = settings.pop("mempool_root")
    certificate = mempool_trust.root_of(root) if root else None
    return {
        **settings, "host": host(), "confirmed": not _current.waiting, **_record,
        # #188: the home server's root trusted for the Mempool, and whether one may be
        "mempool_certificate": {"name": certificate.name, "sha256": certificate.sha256} if certificate else None,
        "mempool_trustable": mempool_trust.private_address(_current.mempool_url),
    }


# When and where the stored choice was made, as load() last read it
_record: dict = {"chosen_at": None, "chosen_via": None}


def where_to_change() -> str:
    """Where the owner changes the price choice in use."""
    if not _current.managed:
        return SETTINGS_PAGE
    return SET_IN_STARTOS if host() == "startos" else SET_BY_SERVER


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
    kept = {key: _get(db, key) for key in (
        FALLBACK_KEY, MEMPOOL_KEY, PROXY_KEY, CHOSEN_AT_KEY, CHOSEN_VIA_KEY, TRUSTED_ROOT_KEY)}
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
        _record.update(chosen_at=None, chosen_via=None)  # the server's choice: nothing to confirm
        _current = replace(managed, mempool_root=_trusted_root(db, managed.mempool_url))
        try:
            _mark_unchosen(db)
        except Exception:
            # The server's settings apply all the same; only the note is missing.
            db.rollback()
            logger.exception("Could not record that no price source was chosen in the app")
        return _current
    source = _get(db, SOURCE_KEY) or (_upgrade_from_live_data(db) if upgrade else None)
    _record.update(chosen_at=_get(db, CHOSEN_AT_KEY), chosen_via=_get(db, CHOSEN_VIA_KEY))
    chosen = source in SOURCES
    tor = server_tor()
    _current = NetworkSettings(
        price_source=source if chosen else "unset",
        mempool_url=_get(db, MEMPOOL_KEY),
        mempool_fallback=_get(db, FALLBACK_KEY) == "on",
        proxy_url=tor or _get(db, PROXY_KEY),
        waiting=chosen and not _record["chosen_at"],
        tor_from_server=bool(tor),
        invalid=tor == "",
        mempool_root=_trusted_root(db, _get(db, MEMPOOL_KEY)),
    )
    return _current


def _trusted_root(db: Session, mempool_url: str | None) -> str | None:
    """The root the owner trusted for this Mempool address (#188), or None:
    one trusted for another address never applies."""
    try:
        stored = json.loads(_get(db, TRUSTED_ROOT_KEY) or "null")
    except ValueError:
        return None
    if not isinstance(stored, dict) or not mempool_url or stored.get("url") != mempool_url:
        return None
    pem = stored.get("pem")
    try:
        if not isinstance(pem, str) or pem.count("-----BEGIN") != 1 or "-----BEGIN CERTIFICATE-----" not in pem:
            raise ValueError("not one certificate")
        trusting(pem)
    except (ssl.SSLError, ValueError, TypeError):
        return None  # not exactly one certificate (a damaged row): trust nothing
    return pem


def connection_host(url: str) -> str | None:
    """The host httpx connects to for this address (#188: judged, not urlparse's)."""
    try:
        return httpx.URL(url).host
    except (httpx.InvalidURL, ValueError):  # ValueError: idna's, e.g. "xn--zz"
        return None


def trusting(pem: str) -> ssl.SSLContext:
    """
    TLS that trusts this one root and nothing else (#188), the address still
    checked. Python 3.13's strict X.509 checks are left off for it, as in
    earlier versions: a home server's own authority may lack fields they
    require (key usage), and the owner checked its fingerprint.
    """
    if not pem:
        raise ValueError("no certificate")
    context = ssl.create_default_context(cadata=pem)
    context.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
    return context


def trust_root(db: Session, mempool_url: str, pem: str) -> NetworkSettings:
    """Trust a home server's root certificate for this Mempool address (#188)."""
    _set(db, TRUSTED_ROOT_KEY, json.dumps({"url": mempool_url, "pem": pem}))
    db.commit()
    return load(db)


def forget_root(db: Session) -> NetworkSettings:
    _set(db, TRUSTED_ROOT_KEY, None)
    db.commit()
    return load(db)


def server_tor() -> str | None:
    """The server's Tor for a choice made in the app (BTCTX_TOR_PROXY_URL),
    None when it isn't set, or "" when it's invalid: then nothing is asked
    (the server asked for Tor, so never around it), with an error in the
    log and the status line saying the server's settings aren't valid."""
    try:
        return _clean_url(os.environ.get(ENV_TOR), PROXY_SCHEMES, ENV_TOR)
    except HTTPException as exc:
        logger.error("Price lookups are off: %s is invalid: %s", ENV_TOR, exc.detail)
        return ""


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
    via: str = "settings",
) -> NetworkSettings:
    if _current.managed:
        raise HTTPException(status_code=409, detail=f"The price choice is set in {where_to_change()}, so it can't be changed here.")
    if price_source not in SOURCES:
        raise HTTPException(status_code=422, detail=f"Price source must be one of: {', '.join(SOURCES)}.")
    mempool = _clean_url(mempool_url, ("http", "https"), "Your mempool server")
    # With the server's Tor, the owner's own proxy setting stays as it was
    proxy = _get(db, PROXY_KEY) if _current.tor_from_server else _clean_url(proxy_url, PROXY_SCHEMES, "The proxy")
    if price_source == "mempool" and not mempool:
        raise HTTPException(status_code=422, detail="Enter your mempool server's address to use it.")
    if price_source == "mempool" and _is_onion(mempool) and not (proxy or _current.tor_from_server):
        raise HTTPException(status_code=422, detail=(
            "An .onion mempool server is reached through the proxy: set it below "
            "(e.g. Tor, socks5h://127.0.0.1:9050)."))
    if _get(db, MEMPOOL_KEY) != mempool:
        _set(db, TRUSTED_ROOT_KEY, None)  # a new address: the old server's certificate is forgotten (#188)
    _set(db, SOURCE_KEY, price_source)
    _set(db, MEMPOOL_KEY, mempool)
    _set(db, FALLBACK_KEY, "on" if mempool_fallback else "off")
    _set(db, PROXY_KEY, proxy)
    _set(db, CHOSEN_AT_KEY, datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
    _set(db, CHOSEN_VIA_KEY, via if via in CHOSEN_VIA else "settings")
    db.commit()
    return load(db)


def refuse_public() -> HTTPException:
    """Why no public price site may be asked: 503 when the owner chose
    Nobody or hasn't chosen yet (the Dashboard says why), 502 when the chosen
    mempool server is missing or didn't answer (an error, not a choice)."""
    s = _current
    where = where_to_change()
    if s.price_source == "mempool" and s.asking:
        if not s.mempool_url:  # only a server's setting: StartOS while Mempool isn't installed
            return HTTPException(status_code=502, detail=(
                "Mempool isn't available, and the backup (public price sites) is off. Install and start "
                f"Mempool, or change the choice in {where}."))
        return HTTPException(status_code=502, detail=(
            f"Your Mempool didn't answer, and the backup (public price sites) is off. Change that in {where}."))
    if s.waiting:
        detail = ("Confirm where BitcoinTX gets newer prices: open BitcoinTX's Dashboard or "
                  f"{SETTINGS_PAGE}. Nothing is asked until you do.")
    elif s.invalid:
        server = SET_IN_STARTOS if host() == "startos" else SET_BY_SERVER  # the server's, even with a choice made here
        detail = f"This server's price settings aren't valid, so nothing is asked. Fix them in {server}; the log says which."
    elif s.price_source == "off":
        detail = f"You chose Nobody for prices, so none is asked. To change that: {where}."
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
    # A home server's root the owner trusts for this address: it alone (#188)
    verify = trusting(_current.mempool_root) if _current.mempool_root else True
    return httpx.AsyncClient(timeout=timeout, proxy=_current.proxy_url if onion else None, verify=verify)


async def own_node_certificates(host: str, port: int, context: ssl.SSLContext) -> list[bytes]:
    """
    The certificates the owner's Mempool sends (DER, unverified), from a TLS
    handshake alone: no HTTP request (#188, services/mempool_trust.py). Only
    for a home-network address, so direct, like own_node_client.
    """
    import asyncio

    _, writer = await asyncio.open_connection(host, port, ssl=context, server_hostname=host)
    try:
        ssl_object = writer.get_extra_info("ssl_object")
        if hasattr(ssl_object, "get_unverified_chain"):  # Python 3.13+
            return [bytes(c) for c in ssl_object.get_unverified_chain()]
        import _ssl  # Python 3.10–3.12: the same call, not yet public

        return [c.public_bytes(_ssl.ENCODING_DER) for c in ssl_object._sslobj.get_unverified_chain()]
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (OSError, ssl.SSLError):
            pass  # closed either way


def _is_onion(url: str | None) -> bool:
    return (urlparse(url or "").hostname or "").endswith(".onion")
