"""
Past-day prices are keyed by the UTC date. The "future date" check once
compared it with the server's local date, so on a machine west of UTC (the Mac
app runs in the user's timezone) today's UTC date was refused every evening:
an income deposit with a blank basis failed with a 422 and the form's FMV
Refresh failed.
"""

import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from backend.services import price_history
from backend.tests.conftest import STUB_HISTORICAL_USD


@pytest.fixture
def pago_pago(monkeypatch):
    """A process timezone 11 hours behind UTC."""
    monkeypatch.setenv("TZ", "Pacific/Pago_Pago")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_todays_utc_date_is_not_the_future_west_of_utc(pago_pago, test_engine):
    today_utc = datetime.now(timezone.utc).date()
    with sessionmaker(bind=test_engine)() as db:
        assert price_history.daily_price(db, today_utc) == Decimal(str(STUB_HISTORICAL_USD))
        with pytest.raises(HTTPException) as exc:
            price_history.daily_price(db, today_utc + timedelta(days=1))
        assert exc.value.status_code == 422
        db.rollback()
    assert os.environ["TZ"] == "Pacific/Pago_Pago"
