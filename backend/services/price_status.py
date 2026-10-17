"""
What the price status line says (#145, 2.3): where the newest price came
from and when, the last problem and its reason, and the hourly history's
download. Kept in memory from the price code's own attempts
(services/bitcoin.py, price_history.py, hourly_prices.py): reading it
never makes a request, and nothing is written to the database every two
minutes. A restart forgets it; the next price asked fills it again.

Each entry remembers the price choice it was made under, so after a change
of choice nothing from the old one is shown.
"""

from __future__ import annotations

import ssl
from datetime import datetime, timezone

from backend.services import outbound

# What went wrong, in the words the screens use (frontend/src/utils/priceStatus.ts)
MEMPOOL_NO_ANSWER = "mempool_no_answer"
MEMPOOL_UNTRUSTED = "mempool_untrusted_certificate"  # #178
MEMPOOL_MISSING = "mempool_missing"  # StartOS: chosen, not installed
PUBLIC_NO_ANSWER = "public_no_answer"
TOR_NO_ANSWER = "tor_no_answer"

# The last price, the last problem, the last problem of your Mempool (kept
# when the backup then fails too, so its reason isn't lost), and the last
# time Bitstamp refused a history download through the proxy (#241)
_state: dict = {"ok": None, "problem": None, "mempool_problem": None, "refused": None}


def reset() -> None:
    """Forget everything (tests)."""
    _state.update(ok=None, problem=None, mempool_problem=None, refused=None)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def answered(source: str) -> None:
    """A price came in: from "mempool", or a public site's name ("kraken")."""
    _state["ok"] = {"at": _now(), "from": source, "settings": outbound.current()}


def failed(what: str) -> None:
    _state["problem"] = {"at": _now(), "what": what, "settings": outbound.current()}
    if what.startswith("mempool"):
        _state["mempool_problem"] = _state["problem"]


def mempool_failed(exc: Exception) -> None:
    """The own mempool server didn't answer: why, as far as can be told
    without asking anything more."""
    failed(MEMPOOL_UNTRUSTED if untrusted_certificate(exc) else MEMPOOL_NO_ANSWER)


def untrusted_certificate(exc: BaseException | None) -> bool:
    """Whether a request failed because the server's certificate isn't
    trusted (a private authority's, e.g. StartOS's home-network address)."""
    seen = 0
    while exc is not None and seen < 10:
        if isinstance(exc, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(exc):
            return True
        exc, seen = exc.__cause__ or exc.__context__, seen + 1
    return False


def bitstamp_refused(exc: BaseException) -> bool:
    """
    Whether a failed history download was Bitstamp refusing it: a 403, or a
    redirect to its challenge page, what it gives Tor's exits (#241). One
    that went through the proxy is remembered: the price card then asks
    whether to download the history without Tor.
    """
    response = getattr(exc, "response", None)  # an HTTP status error's answer
    refused = (response is not None and response.request.url.host == "www.bitstamp.net"
               and (response.status_code == 403 or response.is_redirect))
    settings = outbound.current()
    if refused and settings.proxy_url and not outbound.history_without_tor():
        _state["refused"] = {"at": _now(), "settings": settings}
    return refused


def _current(entry: dict | None) -> dict | None:
    if entry is None or entry["settings"] != outbound.current():
        return None
    return {k: v for k, v in entry.items() if k != "settings"}


def status() -> dict:
    """What the status line shows (GET /api/bitcoin/price/status)."""
    from backend.services import hourly_prices

    s = outbound.current()
    return {
        "source": s.price_source,
        "managed": s.managed,
        "invalid": s.invalid,
        "waiting": s.waiting,
        "host": outbound.host(),
        "last_ok": _current(_state["ok"]),
        "last_problem": _current(_state["problem"]),
        "last_mempool_problem": _current(_state["mempool_problem"]),
        # Bitstamp refused a history download through Tor (#241): the card's question
        "bitstamp_refused": _current(_state["refused"]) is not None,
        "history": hourly_prices.download_status(),
    }
