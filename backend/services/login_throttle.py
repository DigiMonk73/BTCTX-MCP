"""
Slows down password guessing on the routes that check a password or the
setup code: POST /api/login, POST /api/users/reset-account and a password
change (PATCH /api/users/{id}). In memory (one process, forgotten on a
restart) and thread-safe.

- Per client address: the first FREE_FAILURES failures cost nothing; after
  that the client waits 1 s, 2 s, 4 s... (at most MAX_DELAY) after each
  failure before its next try, which is answered 429 with Retry-After until
  then. A success clears the client's count, and so does an hour without a
  failure.
- Across all clients: once GLOBAL_MAX failures happened within
  GLOBAL_WINDOW seconds, every try waits until the oldest leaves the window.
  Behind StartOS's proxy every request comes from the proxy's address, and
  an attacker may have many addresses, so the per-client count isn't enough.

The address is the connection's (request.client.host), never an
X-Forwarded-For header, which anyone can send.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from typing import Deque, Dict, Tuple

from fastapi import HTTPException, Request

FREE_FAILURES = 5
BASE_DELAY = 1.0  # seconds; doubles with each further failure
MAX_DELAY = 300.0
FORGET_AFTER = 3600.0
GLOBAL_WINDOW = 60.0
GLOBAL_MAX = 30
MAX_CLIENTS = 10_000

_now = time.monotonic  # tests move the clock
_lock = threading.Lock()
_clients: Dict[str, Tuple[int, float]] = {}  # address -> (failures, time of the last)
_recent: Deque[float] = deque()  # times of the failures within GLOBAL_WINDOW, all clients


def client_of(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _delay(failures: int) -> float:
    if failures < FREE_FAILURES:
        return 0.0
    return min(MAX_DELAY, BASE_DELAY * 2 ** (failures - FREE_FAILURES))


def check(request: Request) -> None:
    """429 (with Retry-After) while this client, or everyone, has to wait."""
    client, now = client_of(request), _now()
    with _lock:
        while _recent and _recent[0] <= now - GLOBAL_WINDOW:
            _recent.popleft()
        wait = 0.0
        failures, last = _clients.get(client, (0, now))
        if failures and now - last > FORGET_AFTER:
            del _clients[client]
        elif failures:
            wait = last + _delay(failures) - now
        if len(_recent) >= GLOBAL_MAX:
            wait = max(wait, _recent[0] + GLOBAL_WINDOW - now)
    if wait > 0:
        seconds = max(1, math.ceil(wait))
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {seconds} second{'s' if seconds != 1 else ''}.",
            headers={"Retry-After": str(seconds)},
        )


def failed(request: Request) -> None:
    client, now = client_of(request), _now()
    with _lock:
        failures, _last = _clients.get(client, (0, now))
        _clients[client] = (failures + 1, now)
        _recent.append(now)
        if len(_clients) > MAX_CLIENTS:  # keep the most recent half
            keep = sorted(_clients.items(), key=lambda kv: kv[1][1])[-(MAX_CLIENTS // 2):]
            _clients.clear()
            _clients.update(keep)


def succeeded(request: Request) -> None:
    with _lock:
        _clients.pop(client_of(request), None)


def reset() -> None:
    with _lock:
        _clients.clear()
        _recent.clear()
