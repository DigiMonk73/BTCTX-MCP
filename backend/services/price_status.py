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

_state: dict = {"ok": None, "problem": None}


def reset() -> None:
    """Forget everything (tests)."""
    _state.update(ok=None, problem=None)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def answered(source: str) -> None:
    """A price came in: from "mempool", or a public site's name ("kraken")."""
    _state["ok"] = {"at": _now(), "from": source, "settings": outbound.current()}


def failed(what: str) -> None:
    _state["problem"] = {"at": _now(), "what": what, "settings": outbound.current()}


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
        "host": outbound.host(),
        "last_ok": _current(_state["ok"]),
        "last_problem": _current(_state["problem"]),
        "history": hourly_prices.download_status(),
    }
