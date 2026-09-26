"""
Historical price lookups take a UTC date. The "future date" check compared it
with the server's local date, so on a machine west of UTC (the Mac app runs in
the user's timezone) today's UTC date was refused every evening: an income
deposit with a blank basis failed with a 422 and the form's FMV Refresh failed.
"""

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import HTTPException

# The real function, captured before the session fixture stubs it.
from backend.services.bitcoin import get_historical_price as real_get_historical_price


class _Offline:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):
        raise httpx.ConnectError("offline in tests")


@pytest.fixture
def pago_pago(monkeypatch):
    """A process timezone 11 hours behind UTC."""
    monkeypatch.setenv("TZ", "Pacific/Pago_Pago")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def _status(date: str) -> int:
    try:
        asyncio.run(real_get_historical_price(date))
    except HTTPException as exc:
        return exc.status_code
    return 200


def test_todays_utc_date_is_not_the_future_west_of_utc(pago_pago, monkeypatch):
    monkeypatch.setattr("backend.services.outbound.async_client", _Offline)
    today_utc = datetime.now(timezone.utc).date()
    assert _status(today_utc.isoformat()) == 502  # looked up (offline here), not refused
    tomorrow_utc = today_utc + timedelta(days=1)
    assert _status(tomorrow_utc.isoformat()) == 400
    assert os.environ["TZ"] == "Pacific/Pago_Pago"
