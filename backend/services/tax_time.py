"""
Tax dates are decided in the user's timezone, not UTC. Timestamps stay stored
in UTC; this module converts at the edges:

  - which tax year a transaction belongs to (a 9 pm Dec 31 sale in New York
    is 2024 even though it's Jan 1 in UTC)
  - the dates printed on Form 8949
  - the holding-period anniversary (IRS counts calendar days where you are)

Source of the timezone, first match wins: the "tax_timezone" setting (set in
Settings, or auto-filled from the browser on first login) -> BTCTX_TIMEZONE
env var -> UTC.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

SETTING_KEY = "tax_timezone"
DEFAULT_TIMEZONE = "UTC"


def validate_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown timezone '{name}'. Use an IANA name like America/Chicago.") from exc
    return name


def get_tax_timezone_name(db: Session) -> tuple[str, str]:
    """(timezone name, source) where source is 'setting', 'env' or 'default'."""
    from backend.models.app_setting import AppSetting

    row = db.get(AppSetting, SETTING_KEY)
    if row and row.value:
        return row.value, "setting"
    env = os.getenv("BTCTX_TIMEZONE")
    if env:
        return validate_timezone(env), "env"
    return DEFAULT_TIMEZONE, "default"


def get_tax_timezone(db: Session) -> ZoneInfo:
    return ZoneInfo(get_tax_timezone_name(db)[0])


def set_tax_timezone(db: Session, name: str) -> str:
    from backend.models.app_setting import AppSetting

    validate_timezone(name)
    row = db.get(AppSetting, SETTING_KEY)
    if row:
        row.value = name
    else:
        db.add(AppSetting(key=SETTING_KEY, value=name))
    db.flush()
    return name


def date_out_of_range(what: str = "The date") -> str:
    return f"{what} is out of range: BitcoinTX takes dates from 3 January 2009 to the present."


DATE_OUT_OF_RANGE = date_out_of_range()


class DateOutOfRange(ValueError):
    """
    A moment that falls outside the years Python's dates hold (1 to 9999)
    once moved to another timezone: 9999-12-31 west of UTC, 0001-01-01 east
    of it. Never a transaction's date: refused with DATE_OUT_OF_RANGE, as a
    422 (main.py) or a row's error, not a server error (#211).
    """

    def __init__(self) -> None:
        super().__init__(DATE_OUT_OF_RANGE)


def moved(ts: datetime, tz) -> datetime:
    """The aware `ts` in `tz`, or DateOutOfRange."""
    try:
        return ts.astimezone(tz)
    except OverflowError:
        raise DateOutOfRange() from None


def as_utc(ts: datetime) -> datetime:
    """Stored timestamps are UTC; SQLite may hand them back naive."""
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else moved(ts, timezone.utc)


def local_date(ts: datetime, tz: ZoneInfo) -> date:
    return moved(as_utc(ts), tz).date()


def format_tax_date(ts: datetime, tz: ZoneInfo) -> str:
    """MM/DD/YYYY in the tax timezone (Form 8949 columns b and c)."""
    return local_date(ts, tz).strftime("%m/%d/%Y")


def tax_year_bounds(year: int, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """[start, end) of the tax year in UTC: local Jan 1 00:00 to next Jan 1 00:00."""
    start = datetime(year, 1, 1, tzinfo=tz).astimezone(timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=tz).astimezone(timezone.utc)
    return start, end


def local_noon_utc(d: date, tz: ZoneInfo) -> datetime:
    """A date with no time (e.g. '2024-03-05') means midday there — safely inside the day.
    At year 1 a zone's old local time can be 14 hours ahead (Alaska's), and at
    year 9999 12 behind (Etc/GMT+12): DateOutOfRange."""
    return moved(datetime(d.year, d.month, d.day, 12, tzinfo=tz), timezone.utc)


__all__ = [
    "validate_timezone", "get_tax_timezone_name", "get_tax_timezone", "set_tax_timezone",
    "DATE_OUT_OF_RANGE", "date_out_of_range", "DateOutOfRange", "moved",
    "as_utc", "local_date", "format_tax_date", "tax_year_bounds", "local_noon_utc",
]
