"""
The BTC price when an hour began (#144). price_at() is the one place a
valuation at the hour gets its price: the opening price of the UTC hour of
the moment (14:47:12 UTC is priced at 14:00 UTC, known as soon as the hour
starts). The tax timezone never changes which hour.

Lookup order (hourly_price):
  1. btc_price_hourly: an hour this install priced from its source. Never
     replaced, even when a later release's year files cover it.
  2. The year files (services/price_files.py): Bitstamp's hourly opens from
     2013 to the manifest's last hour, downloaded into <data dir>/btc-prices/
     and used only when a year gives the fingerprint this release ships.
  3. The chosen source:
     - the own mempool server's whole history (one request, shared with the
       day lookups): only its live hourly rows (live_hours);
     - public sites, for hours after the year files: Bitstamp's hourly
       candles in fixed blocks of 1,000 hours from the hour after the
       manifest's last, the same requests on every install of a release.
     What it gives is stored (step 1).
  4. With public sites allowed, the year files' download, waiting a little
     for the year asked.
  Nothing: price_at() takes the day's 00:00 UTC price instead
  (price_history.daily_price) and says so ("day").

The download asks for every year, newest first, in fixed blocks: nothing
in it depends on a ledger. It runs in the background once public sites are
the chosen source (at startup, or when the choice is saved), and when a
lookup needs a year whose file isn't here and the own mempool server (if
any) doesn't have the hour. No request ever names the hour asked.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.database import DATABASE_FILE
from backend.models.btc_price import BtcPriceHourly
from backend.services import outbound, price_history
from backend.services import price_files as pf

logger = logging.getLogger(__name__)

HOUR = pf.HOUR
CENT = Decimal("0.01")
DATA_DIR = os.path.dirname(DATABASE_FILE)  # tests point this elsewhere
FOLDER_NAME = "btc-prices"
RETRY_SECONDS = price_history.RETRY_SECONDS
MISMATCH_RETRY_SECONDS = 86400  # a year Bitstamp gives differently is asked again a day later
WAIT_SECONDS = 30.0  # how long a lookup waits for its year's download
PAUSE_SECONDS = 0.2  # between Bitstamp requests
MEMPOOL_FILL_DAYS = 31  # a mempool server's first run fills ~30 days with later prices (#144, finding 3)
CACHED_YEARS = 2
STORE_CHUNK = 300  # rows per insert (SQLite's limit on variables)

_years: OrderedDict = OrderedDict()  # year -> (sha256, {hour: price})
_years_lock = threading.Lock()
_changed = threading.Condition()  # notified as the download saves a year or ends
_state: dict = {}


def reset_state() -> None:
    """Forget downloads and cached years (tests)."""
    with _years_lock:
        _years.clear()
    _state.update(thread=None, failed_at=-1e9, mismatched={}, public_at=-1e9)


reset_state()


@dataclass(frozen=True)
class Priced:
    """A valuation's price: at the hour ("hour") or, failing that, the day ("day")."""
    usd: Decimal
    moment: str
    at: datetime  # the hour's or the day's start, UTC


def hour_of(when: datetime) -> int:
    """The UTC hour whose opening price values `when` (a naive time is UTC), Unix seconds."""
    when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
    return int(when.timestamp()) // HOUR * HOUR


def _utc(hour: int) -> datetime:
    return datetime.fromtimestamp(hour, tz=timezone.utc)


def _current_hour() -> int:
    return int(time.time()) // HOUR * HOUR


def folder() -> Path:
    return Path(DATA_DIR) / FOLDER_NAME


def price_at(db: Session, when: datetime) -> Priced:
    """The price that values `when`: its hour's, else its UTC day's. 422 when neither."""
    hour = hour_of(when)
    if hour > _current_hour():
        raise HTTPException(status_code=422, detail=f"No BTC price for a future time ({pf.label(hour)}).")
    found = hourly_price(db, when)
    if found is not None:
        return Priced(found[0], "hour", _utc(hour))
    usd = price_history.daily_price(db, when)
    day = price_history.utc_day(when)
    return Priced(usd, "day", datetime(day.year, day.month, day.day, tzinfo=timezone.utc))


def hourly_price(db: Session, when: datetime) -> tuple[Decimal, str] | None:
    """The opening price of `when`'s UTC hour and its source, or None when there's none."""
    hour = hour_of(when)
    if not pf.year_start(pf.FIRST_YEAR) <= hour <= _current_hour():
        return None
    stored = db.get(BtcPriceHourly, hour)
    if stored is not None:
        return Decimal(stored.usd), stored.source
    lines = pf.read_manifest(pf.MANIFEST)
    line = next((y for y in lines if y.first_hour <= hour <= y.last_hour), None)
    prices = _year_prices(line) if line else None
    if prices is None:
        found = _from_sources(db, hour, lines[-1].last_hour if lines else hour - HOUR)
        if found is not None or line is None or not start_download():
            return found
        prices = _wait_for_year(line)
    return (prices[hour], "bitstamp") if prices is not None else None


# The year files
def _year_prices(line: pf.YearLine) -> dict[int, Decimal] | None:
    """A downloaded year's prices, if its file gives its line's fingerprint."""
    with _years_lock:
        cached = _years.get(line.year)
        if cached is not None and cached[0] == line.sha256:
            _years.move_to_end(line.year)
            return cached[1]
    text = _file_text(line)
    if text is None:
        return None
    prices = pf.parse_year_text(text)
    with _years_lock:
        _years[line.year] = (line.sha256, prices)
        while len(_years) > CACHED_YEARS:
            _years.popitem(last=False)
    return prices


def _file_text(line: pf.YearLine) -> str | None:
    try:
        text = (folder() / f"{line.year}.csv").read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return text if pf.fingerprint(text) == line.sha256 else None


def _wait_for_year(line: pf.YearLine) -> dict[int, Decimal] | None:
    deadline = time.monotonic() + WAIT_SECONDS
    with _changed:
        while True:
            prices = _year_prices(line)
            remaining = deadline - time.monotonic()
            if prices is not None or remaining <= 0 or not _downloading():
                return prices
            _changed.wait(remaining)


def _downloading() -> bool:
    thread = _state["thread"]
    return thread is not None and thread.is_alive()


def start_download() -> bool:
    """
    Download, in the background, the year files that aren't here yet, when
    the owner's choice allows public sites. True while a download runs.
    """
    if not outbound.current().public_allowed:
        return False
    with _changed:
        if _downloading():
            return True
        if time.monotonic() - _state["failed_at"] < RETRY_SECONDS:
            return False
        missing = [line for line in pf.read_manifest(pf.MANIFEST) if _wanted(line)]
        if not missing:
            return False
        thread = threading.Thread(target=_download, args=(missing,), name="btc-price-download", daemon=True)
        _state["thread"] = thread
        thread.start()
        return True


def download_if_public() -> None:
    """At startup and when the price choice is saved: public sites chosen,
    so the hourly history comes in now (with a mempool server and its
    fallback, only when a lookup needs it)."""
    if outbound.current().price_source == "public":
        start_download()


def _wanted(line: pf.YearLine) -> bool:
    mismatched_at = _state["mismatched"].get(line.year, -1e9)
    return time.monotonic() - mismatched_at >= MISMATCH_RETRY_SECONDS and _file_text(line) is None


def _download(lines: list[pf.YearLine]) -> None:
    try:
        asyncio.run(_download_years(lines))
    except Exception as exc:
        logger.warning("Hourly BTC prices: the download from Bitstamp failed: %s", exc)
        _state["failed_at"] = time.monotonic()
    finally:
        with _changed:
            _changed.notify_all()


async def _download_years(lines: list[pf.YearLine]) -> None:
    """Newest year first, each in its fixed blocks: the same requests on every install."""
    for line in sorted(lines, key=lambda y: -y.year):
        if not outbound.current().public_allowed:  # the choice changed meanwhile
            return
        async with outbound.async_client(timeout=30.0) as client:
            prices = await pf.download_year(client, line.year, line.last_hour, _pause)
        _save_year(line, prices)
        with _changed:
            _changed.notify_all()


async def _pause() -> None:
    await asyncio.sleep(PAUSE_SECONDS)


def _save_year(line: pf.YearLine, prices: dict[int, Decimal]) -> None:
    try:
        text = pf.year_text(prices, line.year, line.last_hour)
    except pf.IncompleteYear as exc:
        text, why = None, str(exc)
    else:
        why = "they don't give the fingerprint this release ships"
    if text is None or pf.fingerprint(text) != line.sha256:
        logger.warning("Hourly BTC prices for %d from Bitstamp aren't used (%s): that year is valued "
                       "at the day's price", line.year, why)
        _state["mismatched"][line.year] = time.monotonic()
        return
    folder().mkdir(parents=True, exist_ok=True)
    partial = folder() / f"{line.year}.csv.partial"
    partial.write_bytes(text.encode("utf-8"))
    os.replace(partial, folder() / f"{line.year}.csv")
    logger.info("Hourly BTC prices for %d from Bitstamp: %d hours, checked", line.year, line.hours)


# The chosen source, for an hour the year files don't give
def _from_sources(db: Session, hour: int, files_end: int) -> tuple[Decimal, str] | None:
    newest = db.query(func.max(BtcPriceHourly.hour)).filter(BtcPriceHourly.hour > files_end).scalar()
    try:
        found = price_history._run(find_hours(hour, files_end, newest or files_end))
    except Exception as exc:
        logger.warning("Hourly BTC price lookup failed: %s", exc)
        found = {}
    # Hours after the files are kept as they come; within them, only the
    # hour asked (the files come first once they're here).
    _store(db, {h: v for h, v in found.items() if h > files_end or h == hour})
    return found.get(hour)


async def find_hours(hour: int, files_end: int, stored_to: int) -> dict[int, tuple[Decimal, str]]:
    """
    What the chosen sources give while `hour` is missing. `hour` only
    decides whether to ask the public sites: no request names it.
    """
    settings = outbound.current()
    found: dict[int, tuple[Decimal, str]] = {}
    if settings.own_node:
        rows, _ = await price_history.own_node_rows()
        found.update({h: (p, "mempool") for h, p in live_hours(rows).items()})
    if hour not in found and hour > files_end and settings.public_allowed:
        for h, p in (await _bitstamp_after(files_end, stored_to)).items():
            found.setdefault(h, (p, "bitstamp"))
    return found


def live_hours(rows: list[dict]) -> dict[int, Decimal]:
    """
    A mempool server's prices it recorded live, each hour: the rows at
    exactly HH:00 from 31 days after its record turns hourly (its first run
    fills the month before with later prices), whose rows an hour before and
    after exist and agree within 2%. Older weekly and daily rows never match.
    """
    by_time: dict[int, Decimal] = {}
    for row in rows:
        try:
            price = Decimal(str(row["USD"]))
            t = int(row["time"])
        except (KeyError, TypeError, ValueError, ArithmeticError):
            continue
        if price > 0 and t % HOUR == 0:
            by_time[t] = price
    start = next((t for t in sorted(by_time) if all(t + k * HOUR in by_time for k in range(1, 24))), None)
    if start is None:
        return {}
    begin, limit = start + MEMPOOL_FILL_DAYS * 86400, price_history.MEMPOOL_TOLERANCE
    out = {}
    for t, price in by_time.items():
        before, after = by_time.get(t - HOUR), by_time.get(t + HOUR)
        if t >= begin and before and after and abs(before - price) <= price * limit >= abs(after - price):
            out[t] = price.quantize(CENT)
    return out


async def _bitstamp_after(files_end: int, stored_to: int) -> dict[int, Decimal]:
    """
    Bitstamp's hours after the year files, in fixed blocks from the hour
    after them (skipping blocks already stored), at most every 10 minutes.
    The current hour only once it has a trade: until then its open can change.
    """
    if time.monotonic() - _state["public_at"] < RETRY_SECONDS:
        return {}
    _state["public_at"] = time.monotonic()
    current, size = _current_hour(), pf.BLOCK_HOURS * HOUR
    out: dict[int, Decimal] = {}
    async with outbound.async_client() as client:
        for start in range(files_end + HOUR, current + 1, size):
            if start + size - HOUR <= stored_to:
                continue
            for row in await pf.bitstamp_candles(client, start):
                h = int(row["timestamp"])
                if h % HOUR == 0 and (h < current or (h == current and Decimal(str(row["volume"])) > 0)):
                    out[h] = Decimal(str(row["open"])).quantize(CENT)
    return out


def _store(db: Session, prices: dict[int, tuple[Decimal, str]]) -> None:
    rows = [{"hour": h, "usd": usd, "source": src} for h, (usd, src) in sorted(prices.items())]
    for i in range(0, len(rows), STORE_CHUNK):
        db.execute(sqlite_insert(BtcPriceHourly).values(rows[i:i + STORE_CHUNK]).on_conflict_do_nothing())
    if rows:
        db.flush()
