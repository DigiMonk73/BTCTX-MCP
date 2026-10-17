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
(BTCTX_TOR_PROXY_URL; StartOS's "Use Tor" with Decide in BitcoinTX instead): it is
the proxy then, locked on, and an invalid one asks nobody (server_tor).

Through Tor, Bitstamp refuses BitcoinTX's requests (#241), so the price
card asks once whether to download the price history without Tor. The
answer is the owner's own (stored here, kept by a restore, changeable in
Settings even while the server sets the choice). After a Yes, and only
then, Bitstamp's fixed-block history downloads go directly
(history_client): the hourly year files, the hours after them and the
daily history, each a block that's the same for every install. Nothing
else ever goes around the proxy; FixedBlocksOnly refuses any other request
on that route (a start that isn't one of those blocks' included) before
it's sent.

Every request ends in bounded time and size (BoundedClient): httpx's
timeouts limit each wait, not the whole request, so the whole of it gets a
deadline (WAITS times its timeout), and an answer over MAX_ANSWER_BYTES is
refused. Either is a failed request, handled as any other.

A test checks no other backend module builds its own client. The one
exception is an admin's command, not the app: `python -m backend.cli
install-draft-forms` (services/reports/draft_forms.py) fetches the IRS's
draft forms from irs.gov when run on a test install.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import json
import logging
import os
import ssl
import zlib
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.services.desktop import is_desktop
from backend.unexpected_errors import log_unexpected
from backend.services import price_files as pf

logger = logging.getLogger(__name__)

# Seconds for each wait within a request: connecting, sending, the next part
# of the answer. The biggest answers (the own Mempool's whole history,
# Bitstamp's hourly blocks) get HISTORY_TIMEOUT.
TIMEOUT, HISTORY_TIMEOUT = 10.0, 30.0
# A whole request, from connecting to its answer's last byte, may take its
# timeout once for each of those three waits: all that a server answering at
# once could need within them, through a slow Tor circuit too. An answer
# still arriving after that is cut off (BoundedClient).
WAITS = 3
# The most an answer may be, decoded (a compressed one counts in full). The
# largest real one is the own Mempool's whole USD history, ~32 bytes an hour
# it recorded: about 1 MiB for three years, 4.3 MiB even for every hour since
# 2010, growing 0.27 MiB a year. A block of Bitstamp's 1,000 candles is ~140 KiB.
MAX_ANSWER_BYTES = 16 * 1024 * 1024
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
# The owner's answer to "Download the price history once without Tor?"
# (#241): "yes" or "no", when, and where ("dashboard" or "settings"); no
# row: not asked. Written only by answer_history_without_tor(), from
# PUT /api/settings/network/history-without-tor (a login, never the AI key).
DIRECT_KEY, DIRECT_AT_KEY, DIRECT_VIA_KEY = (
    "history_without_tor", "history_without_tor_at", "history_without_tor_via")
DIRECT_ANSWERS, DIRECT_VIA = ("yes", "no"), ("dashboard", "settings")
SOURCES = ("off", "public", "mempool")
PROXY_SCHEMES = ("socks5", "socks5h", "http", "https")
ENV_SOURCE, ENV_FALLBACK, ENV_MEMPOOL, ENV_PROXY = (
    "BTCTX_PRICE_SOURCE", "BTCTX_MEMPOOL_FALLBACK", "BTCTX_MEMPOOL_URL", "BTCTX_PROXY_URL")
# Tor on the server, for a choice made in the app (StartOS: the action's
# "Use Tor" with Decide in BitcoinTX instead, #145): used for every request that
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
# The request extension those fake services read: the proxy taken, None for direct
PROXY_TAG = "btctx_proxy"


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
    # The owner answered Yes to downloading the price history without Tor
    # (#241): Bitstamp's fixed blocks go directly (history_client)
    history_direct: bool = False

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
    settings.pop("history_direct")  # the answer's record says it
    certificate = mempool_trust.root_of(root) if root else None
    return {
        **settings, "host": host(), "confirmed": not _current.waiting, **_record,
        # #188: the home server's root trusted for the Mempool, and whether one may be
        "mempool_certificate": {"name": certificate.name, "sha256": certificate.sha256} if certificate else None,
        "mempool_trustable": mempool_trust.private_address(_current.mempool_url),
        # #241: the answer to "Download the price history once without Tor?"
        "history_without_tor": dict(_direct_record),
    }


# When and where the stored choice was made, as load() last read it
_record: dict = {"chosen_at": None, "chosen_via": None}
# The answer about the price history without Tor (#241), as load() last read it
_direct_record: dict = {"answer": None, "at": None, "via": None}


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
    from backend.models.app_setting import save_setting

    save_setting(db, key, value)


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
    switch back to the app's own setting (StartOS: Decide in BitcoinTX instead) asks
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
        FALLBACK_KEY, MEMPOOL_KEY, PROXY_KEY, CHOSEN_AT_KEY, CHOSEN_VIA_KEY, TRUSTED_ROOT_KEY,
        DIRECT_KEY, DIRECT_AT_KEY, DIRECT_VIA_KEY)}
    # Not chosen yet stays "unset": a restored database's stored prices must
    # not pass for a pre-1.1.0 install's public choice (_upgrade_from_live_data)
    kept[SOURCE_KEY] = _get(db, SOURCE_KEY) or "unset"
    kept[OLD_LIVE_KEY] = None
    return kept


def carry_over(db: Session, before: dict) -> None:
    """
    Write the price settings from before a restore into the restored
    database, before it replaces the live one (owner decision 2026-09-29): a
    backup from before a switch to Tor or Off must not ask the public sites
    directly again. As for the AI key and login. The restore commits and
    checks them; nothing in memory changes until load() reads the live
    database.
    """
    for key, value in before.items():
        _set(db, key, value)


def load(db: Session, upgrade: bool = True) -> NetworkSettings:
    """
    Read the settings (at startup, after a restore): the server's, else the
    database's. `upgrade=False` (a command-line run, which on StartOS may lack
    the server's variables) never works out a pre-1.1.0 install's choice:
    the app's start does that (#134).
    """
    global _current
    managed = from_env()
    # The answer about the history without Tor is the owner's, whoever sets the choice (#241)
    direct = _load_direct_answer(db)
    if managed:
        _record.update(chosen_at=None, chosen_via=None)  # the server's choice: nothing to confirm
        _current = replace(managed, mempool_root=_trusted_root(db, managed.mempool_url), history_direct=direct)
        try:
            _mark_unchosen(db)
        except Exception as e:
            # The server's settings apply all the same; only the note is missing.
            db.rollback()
            log_unexpected("Recording that no price source was chosen in the app", e, logger)
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
        history_direct=direct,
    )
    return _current


def _load_direct_answer(db: Session) -> bool:
    """Read the answer about the history without Tor into its record (#241);
    True only for a Yes. Anything but "yes" or "no" counts as not asked."""
    answer = _get(db, DIRECT_KEY)
    if answer in DIRECT_ANSWERS:
        _direct_record.update(answer=answer, at=_get(db, DIRECT_AT_KEY), via=_get(db, DIRECT_VIA_KEY))
    else:
        _direct_record.update(answer=None, at=None, via=None)
    return answer == "yes"


def answer_history_without_tor(db: Session, answer: str, via: str) -> NetworkSettings:
    """
    The owner's answer to "Download the price history once without Tor?"
    (#241), with when and where it was given. Allowed while the server sets
    the price choice too: the answer is the owner's, and only says whether
    Bitstamp's fixed blocks may go around the proxy.
    """
    if answer not in DIRECT_ANSWERS:
        raise HTTPException(status_code=422, detail="The answer must be yes or no.")
    _set(db, DIRECT_KEY, answer)
    _set(db, DIRECT_AT_KEY, datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
    _set(db, DIRECT_VIA_KEY, via if via in DIRECT_VIA else "settings")
    db.commit()
    logger.info("Price history without Tor: %s (answered %s)", answer,
                "on the Dashboard" if via == "dashboard" else "in Settings")
    return load(db)


def history_without_tor() -> bool:
    """Whether Bitstamp's fixed-block history goes directly now (#241): the
    owner's Yes, with a proxy set (without one everything is direct anyway)
    and public price sites allowed."""
    s = _current
    return s.history_direct and bool(s.proxy_url) and s.public_allowed


def agreed_on() -> str:
    """The day the owner's answer was given, for the log (e.g. "2026-10-16")."""
    return (_direct_record["at"] or "")[:10] or "an unknown day"


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
    e.g. Tor stopped), a proxy refusal or a timeout (AnswerTooSlow too)."""
    return isinstance(exc, httpx.TransportError)


def async_client(timeout: float | None = None) -> BoundedClient:
    """A client for public sites: through the proxy when one is set.
    `timeout`: each wait's limit, TIMEOUT unless given."""
    return _client(timeout or TIMEOUT, _current.proxy_url)


def history_client(timeout: float | None = None) -> BoundedClient | FixedBlocksOnly:
    """
    A client for Bitstamp's fixed-block price history (#241: the hourly year
    files, the hours after them, the daily history): through the proxy like
    any public site, unless the owner answered Yes to downloading it without
    Tor (history_without_tor); then directly, for those blocks only.
    """
    if not history_without_tor():
        return async_client(timeout)
    return FixedBlocksOnly(_client(timeout or TIMEOUT, None))


def _client(timeout: float, proxy: str | None, verify: bool | ssl.SSLContext = True) -> BoundedClient:
    """Every client's one builder: through `proxy`, or directly with None."""
    if _transport is not None:
        # Tests: the fake sites answer, and each request carries the proxy it would take
        hooks = {"request": [functools.partial(_tag_proxy, proxy)]}
        client = httpx.AsyncClient(timeout=timeout, transport=_transport, event_hooks=hooks)
    else:
        client = httpx.AsyncClient(timeout=timeout, proxy=proxy, verify=verify)
    return BoundedClient(client, WAITS * timeout)


async def _tag_proxy(proxy: str | None, request: httpx.Request) -> None:
    request.extensions[PROXY_TAG] = proxy


class NotAFixedBlock(RuntimeError):
    """A request that isn't one of Bitstamp's fixed history blocks, refused
    on the route that goes without Tor (#241) before it's sent."""


class FixedBlocksOnly:
    """
    The route around the proxy (#241): only GETs of Bitstamp's OHLC history
    that are one of its fixed blocks (fixed_block: the same requests on every
    install, so none can name a ledger's hour or day), and only while the
    owner's Yes still holds (checked before each request: a download may
    outlast it). Anything else, a request without `start` included, is
    refused before it's sent.
    """

    def __init__(self, client: BoundedClient):
        self._client = client

    async def __aenter__(self) -> FixedBlocksOnly:
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self._client.__aexit__(*exc_info)

    async def get(self, url: str, params: dict | None = None, **kwargs) -> httpx.Response:
        if kwargs or not fixed_block(url, params):
            raise NotAFixedBlock(f"only Bitstamp's fixed history blocks go without Tor, not {url}")
        if not history_without_tor():
            raise NotAFixedBlock("nothing goes without Tor any more: the owner's Yes no longer holds")
        return await self._client.get(url, params=params)


def fixed_block(url: str, params: dict | None) -> bool:
    """
    Whether a request is one of Bitstamp's fixed history blocks, 1,000
    candles from a start every install asks for (no ledger decides it):
    hourly, a block of the release's year files (from 1 January, each 1,000
    hours on, to the year's last hour) or one from the hour after them
    (hourly_prices); daily, from the first price day, each 1,000 days on
    (price_history).
    """
    if url != pf.BITSTAMP_OHLC_URL or not params or set(params) != {"step", "limit", "start"}:
        return False
    step, limit, start = (params[k] for k in ("step", "limit", "start"))
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in (step, limit, start)) or limit != 1000:
        return False
    if step == pf.HOUR:
        return _hourly_block(start)
    return step == 86400 and _on_grid(start, _first_price_midnight(), 1000 * 86400)


def _hourly_block(start: int) -> bool:
    """One of the release's year files' blocks (MANIFEST.csv), or one from
    the hour after them: the hours the app downloads, and no others."""
    lines = pf.read_manifest(pf.MANIFEST)
    if any(start in pf.block_starts(line.year, line.last_hour) for line in lines):
        return True
    return bool(lines) and _on_grid(start, lines[-1].last_hour + pf.HOUR, pf.BLOCK_HOURS * pf.HOUR)


def _on_grid(start: int, first: int, size: int) -> bool:
    return start >= first and (start - first) % size == 0


def _first_price_midnight() -> int:
    from backend.services.price_history import FIRST_PRICE_DAY  # it imports this module

    d = FIRST_PRICE_DAY
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def own_node_client(timeout: float | None = None) -> BoundedClient:
    """
    A client for the owner's mempool server: direct (it's on their network
    or their StartOS), except an .onion, which needs the proxy. `timeout`:
    each wait's limit, TIMEOUT unless given.
    """
    timeout = timeout or TIMEOUT
    onion = _is_onion(_current.mempool_url)
    if onion and not _current.proxy_url:
        # Never directly: the system's DNS resolver would see the .onion name.
        raise RuntimeError("an .onion mempool server needs the proxy, and none is set")
    # A home server's root the owner trusts for this address: it alone (#188)
    verify = trusting(_current.mempool_root) if _current.mempool_root and _transport is None else True
    return _client(timeout, _current.proxy_url if onion else None, verify)


class AnswerTooSlow(httpx.TimeoutException):
    """No whole answer by the request's deadline: a timeout (unreachable())."""


class AnswerTooLarge(httpx.HTTPError):
    """An answer over MAX_ANSWER_BYTES, refused before it is read whole."""


class BoundedClient:
    """
    An httpx client whose every GET ends by `deadline` seconds after it
    starts, connecting and the whole answer included, and refuses an answer
    over MAX_ANSWER_BYTES (AnswerTooSlow, AnswerTooLarge): httpx's own
    timeouts limit each wait, so an answer arriving in small parts, each
    within them, would otherwise keep a request open with no end.
    """

    def __init__(self, client: httpx.AsyncClient, deadline: float):
        self._client, self.deadline = client, deadline

    async def __aenter__(self) -> BoundedClient:
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self._client.__aexit__(*exc_info)

    async def get(self, url: str, **kwargs) -> httpx.Response:
        try:
            return await asyncio.wait_for(self._whole_answer(url, kwargs), self.deadline)
        except asyncio.TimeoutError:
            raise AnswerTooSlow(f"no whole answer within {self.deadline:g} seconds") from None

    async def _whole_answer(self, url: str, kwargs: dict) -> httpx.Response:
        async with self._client.stream("GET", url, **kwargs) as response:
            body = await _bounded_body(response)
        # The body is decoded: the encoding and length the server sent don't fit it
        headers = [(k, v) for k, v in response.headers.multi_items() if k not in ("content-encoding", "content-length")]
        return httpx.Response(response.status_code, headers=headers, content=bytes(body.data), request=response.request)


async def _bounded_body(response: httpx.Response) -> _Body:
    """The answer's body, decoded here a bounded step at a time from its raw
    parts: httpx would decode a whole part (and a stacked encoding) before
    any check."""
    if response.is_stream_consumed:  # built whole (a test transport): httpx decoded it already
        body = _Body(None)
        body.add(response.content)
        return body
    body = _Body(response.headers.get("content-encoding"))
    async with contextlib.aclosing(response.aiter_raw()) as parts:  # as they arrive
        async for part in parts:
            body.add(part)
    body.finish()
    return body


class _Body:
    """
    An answer's body, decoded as it arrives and never past MAX_ANSWER_BYTES
    (AnswerTooLarge), however small the encoded parts. Plain, gzip or
    deflate, as httpx asks for; any other or stacked encoding is refused.
    """

    def __init__(self, encoding: str | None):
        name = (encoding or "identity").strip().lower()
        if name in ("gzip", "x-gzip", "deflate"):
            self._decoder = zlib.decompressobj(zlib.MAX_WBITS | 32)  # a gzip or zlib header
        elif name == "identity":
            self._decoder = None
        else:
            raise httpx.DecodingError(f"an answer encoded as {name!r}")
        self._raw_deflate_allowed = name == "deflate"  # as httpx: deflate may come without its header
        self._fed = False
        self.data = bytearray()

    def add(self, part: bytes) -> None:
        if self._decoder is None:
            self._keep(part)
            return
        room = MAX_ANSWER_BYTES + 1 - len(self.data)
        try:
            out = self._decoder.decompress(part, room)
        except zlib.error as e:
            if not (self._raw_deflate_allowed and not self._fed):
                raise httpx.DecodingError(f"an answer that doesn't decode: {e}") from e
            self._decoder = zlib.decompressobj(-zlib.MAX_WBITS)
            out = self._decoder.decompress(part, room)
        self._fed = self._fed or bool(part)
        self._keep(out)
        if self._decoder.unconsumed_tail:  # more than the room left
            raise AnswerTooLarge(f"an answer over {MAX_ANSWER_BYTES} bytes")

    def finish(self) -> None:
        if self._decoder is None:
            return
        self._keep(self._decoder.flush())  # at most the decoder's window: the input is all consumed
        if self._fed and not self._decoder.eof:
            raise httpx.DecodingError("an answer cut short")

    def _keep(self, data: bytes) -> None:
        self.data += data
        if len(self.data) > MAX_ANSWER_BYTES:
            raise AnswerTooLarge(f"an answer over {MAX_ANSWER_BYTES} bytes")


async def own_node_certificates(host: str, port: int, context: ssl.SSLContext) -> list[bytes]:
    """
    The certificates the owner's Mempool sends (DER, unverified), from a TLS
    handshake alone: no HTTP request (#188, services/mempool_trust.py). Only
    for a home-network address, so direct, like own_node_client.
    """
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
