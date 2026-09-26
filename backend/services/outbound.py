"""
backend/services/outbound.py

The only place the backend creates HTTP clients for outside services (BTC
prices, block height). Keeping them here means one place decides how the
app talks to the internet; tests check no other module builds its own.
"""

from __future__ import annotations

from typing import Optional

import httpx

TIMEOUT = 10.0

# Tests set this to an httpx.MockTransport to fake the outside services.
_transport: Optional[httpx.AsyncBaseTransport] = None


def async_client(timeout: float = TIMEOUT) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, transport=_transport)
