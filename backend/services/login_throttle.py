"""
Slows down password guessing on the routes that check a password or the
setup code: POST /api/login, POST /api/users/reset-account and a password
change (PATCH /api/users/{id}). In memory (one process, forgotten on a
restart) and thread-safe.

- Per client: the first FREE_FAILURES failures cost nothing; after that the
  client waits 1 s, 2 s, 4 s... (at most MAX_DELAY) after each failure
  before its next try, which is answered 429 with Retry-After until then.
  A success clears the client's count, and so does an hour without a
  failure.
- A try counts as a failure from the moment check() lets it through,
  before its password or code is checked, until succeeded() says it was
  right. So a route calls check() first and succeeded() once the password
  or code was right; any other ending (a wrong one, an error) leaves the
  try counted.
- Across all clients: once GLOBAL_MAX failures happened within
  GLOBAL_WINDOW seconds, every try waits until the oldest leaves the window.
  Behind StartOS's proxy every request comes from the proxy's address, and
  one sender may have many addresses, so the per-client count isn't enough.
  Known browsers are left out of it.
- A client is a known browser, or else an address. A browser that got one
  of these routes right is given a device cookie (DEVICE_COOKIE, for a
  year): a random id, signed with the app's secret key and bound to the
  account's password, so a new password (in the app, or StartOS's Set
  Login Credentials) turns every earlier cookie into none. Its tries count
  for that id alone, slowed like any client's: neither its address's count
  nor the count across clients stops it, and its failures add to neither.
  Behind a proxy (StartOS's, or one in front of Docker) every request has
  the proxy's address: without the cookie, anyone's failed tries would
  keep the owner out too.
- Any other request is counted by the connection's address
  (request.client.host), never an X-Forwarded-For header, which anyone can
  send.
"""

from __future__ import annotations

import contextlib
import math
import secrets
import threading
import time
from collections import deque

from fastapi import HTTPException, Request, Response
from itsdangerous import BadSignature, TimestampSigner
from sqlalchemy.orm import Session

from backend import secret_key
from backend.models.user import User
from backend.session_auth import credential_stamp

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
DEVICE_PREFIX = "device:"  # an address never starts with it

_now = time.monotonic  # tests move the clock
_lock = threading.Lock()
_clients: dict[str, tuple[int, float]] = {}  # address or known browser -> (failures, time of the last)
_recent: deque[float] = deque()  # times of the failures within GLOBAL_WINDOW, known browsers' left out


def client_of(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def check(request: Request, db: Session) -> None:
    """
    Count this try, before its password or code is checked: 429 (with
    Retry-After), with nothing counted, while this client has to wait or,
    for a request from no known browser, everyone does. Notes on the request
    whose count it is and when it was counted, for succeeded() later in the
    same request.
    """
    request.state.login_device = _known_device(request, db)
    client, known = _counted_as(request)
    with _lock:
        now = _now()
        wait = _wait(client, known, now)
        if wait <= 0:
            _count_try(client, known, now)
            request.state.login_try = now
    if wait > 0:
        seconds = max(1, math.ceil(wait))
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {seconds} second{'s' if seconds != 1 else ''}.",
            headers={"Retry-After": str(seconds)},
        )


def succeeded(request: Request) -> None:
    """The password or code was right: the client's count is cleared, and
    this try leaves the count across clients."""
    client, known = _counted_as(request)
    counted_at = getattr(request.state, "login_try", None)
    with _lock:
        _clients.pop(client, None)
        if counted_at is not None and not known:
            with contextlib.suppress(ValueError):  # already out of the window
                _recent.remove(counted_at)


def remember_device(response: Response, user: User) -> None:
    """
    Give the browser a new device cookie, once it got the password or code
    right (`user` as it is now, with a new password if it was just
    changed). A new id each time, so an older copy of the cookie no longer
    shares this browser's count. Secure over HTTPS: security_headers.py.
    """
    response.set_cookie(
        DEVICE_COOKIE,
        _signer(user).sign(secrets.token_urlsafe(16)).decode(),
        max_age=DEVICE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )


def reset() -> None:
    with _lock:
        _clients.clear()
        _recent.clear()


def _known_device(request: Request, db: Session) -> str | None:
    """The id in the request's device cookie, if this install signed it
    within a year for the account's current password."""
    cookie = request.cookies.get(DEVICE_COOKIE)
    if not cookie:
        return None
    account = db.query(User).order_by(User.id).first()
    if account is None:
        return None
    try:
        return _signer(account).unsign(cookie, max_age=DEVICE_MAX_AGE).decode()
    except BadSignature:
        return None


def _signer(user: User) -> TimestampSigner:
    return TimestampSigner(secret_key.app_secret_key(), salt=f"{DEVICE_SALT}:{credential_stamp(user)}")


def _counted_as(request: Request) -> tuple[str, bool]:
    """Whose count the request's tries go to, as check() found, and whether
    that is a known browser's. Without check() first, its address's: the
    stricter one."""
    device = getattr(request.state, "login_device", None)
    return (DEVICE_PREFIX + device, True) if device else (client_of(request), False)


def _wait(client: str, known: bool, now: float) -> float:
    """Seconds the client has yet to wait (none if 0 or less), once failures
    too old to count are dropped. Under _lock."""
    while _recent and _recent[0] <= now - GLOBAL_WINDOW:
        _recent.popleft()
    wait = 0.0
    failures, last = _clients.get(client, (0, now))
    if failures and now - last > FORGET_AFTER:
        del _clients[client]
    elif failures:
        wait = last + _delay(failures) - now
    if not known and len(_recent) >= GLOBAL_MAX:
        wait = max(wait, _recent[0] + GLOBAL_WINDOW - now)
    return wait


def _count_try(client: str, known: bool, now: float) -> None:
    """One more failure for the client, and across clients unless it's a
    known browser. Under _lock."""
    failures, _last = _clients.get(client, (0, now))
    _clients[client] = (failures + 1, now)
    if not known:
        _recent.append(now)
    if len(_clients) > MAX_CLIENTS:  # keep the most recent half
        keep = sorted(_clients.items(), key=lambda kv: kv[1][1])[-(MAX_CLIENTS // 2):]
        _clients.clear()
        _clients.update(keep)


def _delay(failures: int) -> float:
    if failures < FREE_FAILURES:
        return 0.0
    return min(MAX_DELAY, BASE_DELAY * 2 ** (failures - FREE_FAILURES))
