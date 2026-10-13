"""
Slows down password guessing on the routes that check a password or the
setup code: POST /api/login, POST /api/users/reset-account and a password
change (PATCH /api/users/{id}). In memory (one process, forgotten on a
restart) and thread-safe.

- Per client: the first FREE_FAILURES failures cost nothing; after that
  the client waits 1 s, 2 s, 4 s... (at most MAX_DELAY) after each failure
  before its next try, which is answered 429 with Retry-After until then.
  A success clears the client's count, and so does an hour without a
  failure.
- Across all clients: once GLOBAL_MAX failures happened within
  GLOBAL_WINDOW seconds, every try waits until the oldest leaves the window.
  Behind StartOS's proxy every request comes from the proxy's address, and
  an attacker may have many addresses, so the per-client count isn't enough.
- A browser that got one of these routes right is given a device cookie
  (DEVICE_COOKIE: a random id signed with the app's secret key, for a
  year). Its tries count for that device alone: neither its address's count
  nor the count across clients stops it, and its failures add to neither.
  Otherwise, behind that shared address, other people's failures would keep
  the owner out. A request without a valid device cookie is counted by its
  address.

The address is the connection's (request.client.host), never an
X-Forwarded-For header, which anyone can send.
"""

from __future__ import annotations

import math
import secrets
import threading
import time
from collections import deque

from fastapi import HTTPException, Request, Response
from itsdangerous import BadSignature, TimestampSigner

from backend.secret_key import app_secret_key

FREE_FAILURES = 5
BASE_DELAY = 1.0  # seconds; doubles with each further failure
MAX_DELAY = 300.0
FORGET_AFTER = 3600.0
GLOBAL_WINDOW = 60.0
GLOBAL_MAX = 30
MAX_CLIENTS = 10_000

DEVICE_COOKIE = "btc_device"
DEVICE_MAX_AGE = 365 * 24 * 3600  # seconds
DEVICE_SALT = "btctx-device"  # so a session cookie's signature never passes for a device's
_signer = TimestampSigner(app_secret_key(), salt=DEVICE_SALT)

_now = time.monotonic  # tests move the clock
_lock = threading.Lock()
_clients: dict[str, tuple[int, float]] = {}  # address or device -> (failures, time of the last)
_recent: deque[float] = deque()  # times of the failures within GLOBAL_WINDOW, clients without a device


def client_of(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def device_of(request: Request) -> str | None:
    """The id in the request's device cookie, if this install signed it within a year."""
    cookie = request.cookies.get(DEVICE_COOKIE)
    if not cookie:
        return None
    try:
        return _signer.unsign(cookie, max_age=DEVICE_MAX_AGE).decode()
    except BadSignature:
        return None


def _counted_as(request: Request) -> tuple[str, bool]:
    """Whose count a try goes to, and whether that is a known device's."""
    device = device_of(request)
    return (f"device:{device}", True) if device else (client_of(request), False)


def _delay(failures: int) -> float:
    if failures < FREE_FAILURES:
        return 0.0
    return min(MAX_DELAY, BASE_DELAY * 2 ** (failures - FREE_FAILURES))


def check(request: Request) -> None:
    """429 (with Retry-After) while this client has to wait, or, without a
    device cookie, everyone does."""
    (counted, known), now = _counted_as(request), _now()
    with _lock:
        while _recent and _recent[0] <= now - GLOBAL_WINDOW:
            _recent.popleft()
        wait = 0.0
        failures, last = _clients.get(counted, (0, now))
        if failures and now - last > FORGET_AFTER:
            del _clients[counted]
        elif failures:
            wait = last + _delay(failures) - now
        if not known and len(_recent) >= GLOBAL_MAX:
            wait = max(wait, _recent[0] + GLOBAL_WINDOW - now)
    if wait > 0:
        seconds = max(1, math.ceil(wait))
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {seconds} second{'s' if seconds != 1 else ''}.",
            headers={"Retry-After": str(seconds)},
        )


def failed(request: Request) -> None:
    (counted, known), now = _counted_as(request), _now()
    with _lock:
        failures, _last = _clients.get(counted, (0, now))
        _clients[counted] = (failures + 1, now)
        if not known:
            _recent.append(now)
        if len(_clients) > MAX_CLIENTS:  # keep the most recent half
            keep = sorted(_clients.items(), key=lambda kv: kv[1][1])[-(MAX_CLIENTS // 2):]
            _clients.clear()
            _clients.update(keep)


def succeeded(request: Request) -> None:
    with _lock:
        _clients.pop(_counted_as(request)[0], None)


def remember_device(response: Response) -> None:
    """Give the browser a new device cookie (after a right password or code).
    Secure over HTTPS: security_headers.py."""
    response.set_cookie(
        DEVICE_COOKIE,
        _signer.sign(secrets.token_urlsafe(16)).decode(),
        max_age=DEVICE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )


def reset() -> None:
    with _lock:
        _clients.clear()
        _recent.clear()
