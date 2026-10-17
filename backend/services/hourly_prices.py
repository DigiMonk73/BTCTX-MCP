"""
The BTC price when an hour began (#144). price_at() is the one place a
valuation at the hour gets its price: the opening price of the UTC hour of
the moment (14:47:12 UTC is priced at 14:00 UTC, known as soon as the hour
starts). The tax timezone never changes which hour.

Lookup order (hourly_price):
  1. btc_price_hourly: an hour this install priced from a source, or
     Bitstamp's hours after the year files. Never replaced, even when a
     later release's year files cover it.
  2. The year files (services/price_files.py): Bitstamp's hourly opens from
     2013 to the manifest's last hour, downloaded into <data dir>/btc-prices/
     and used only when a year gives the fingerprint this release ships.
  3. The chosen source:
     - the own mempool server's whole history (one request, shared with the
       day lookups): only its live hourly rows (live_hours), and only the
       hour asked is kept;
     - public sites, for hours after the year files: Bitstamp's hourly
       candles in fixed blocks of 1,000 hours from the hour after the
       manifest's last, the same requests on every install of a release;
       every hour they give is kept.
  4. With public sites allowed, the year files' download, waiting a little
     for the year asked, unless the caller has already written: it holds
     SQLite's write lock (#421).
  Nothing: price_at() takes the day's 00:00 UTC price instead
  (price_history.daily_price) and says so ("day").

The download asks for every year, newest first, in fixed blocks: nothing
in it depends on a ledger. It runs in the background once the choice allows
public sites (public, or your Mempool with its backup: #145), at startup or
when the choice is saved, and when a
lookup needs a year whose file isn't here and the own mempool server (if
any) doesn't have the hour. Each request goes out with the choice as it is
then: none once public sites aren't allowed, through the proxy set then,
or directly after the owner's Yes to downloading the history without Tor,
which Bitstamp refuses (#241, outbound.history_client). No request ever
names the hour asked.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.database import DATABASE_FILE
from backend.models.btc_price import BtcPriceHourly
from backend.services import outbound, price_history, price_status
from backend.services import price_files as pf

logger = logging.getLogger(__name__)

HOUR = pf.HOUR
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


@dataclass(frozen=True)
class Priced:
    """A valuation's price: at the hour ("hour") or, failing that, the day ("day")."""
    usd: Decimal
    moment: str
    at: datetime  # the hour's or the day's start, UTC
    source: str = field(default="", compare=False)  # e.g. "bitstamp", "mempool", "kraken"


def hour_of(when: datetime) -> int:
    """The UTC hour whose opening price values `when` (a naive time is UTC), Unix seconds."""
    when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
    return int(when.timestamp()) // HOUR * HOUR


def price_at(db: Session, when: datetime) -> Priced:
    """
    The price that values `when`: its hour's, else its UTC day's. A time
    later today (an hour not begun: an entry dated today, which an import
    reads as noon in the tax timezone) takes the day's price, marked as
    such; a later day has none (422).
    """
    hour = hour_of(when)
    found = hourly_price(db, when)
    if found is not None:
        return Priced(found[0], "hour", _utc(hour), found[1])
    usd = price_history.daily_price(db, when)
    day = price_history.utc_day(when)
    return Priced(usd, "day", datetime(day.year, day.month, day.day, tzinfo=timezone.utc),
                  price_history.stored_source(db, day) or "")


def stored_price_at(db: Session, when: date | datetime, moment: str, years: dict | None = None) -> Priced | None:
    """
    The price this install already has for `when` at "hour" or "day", from
    its own table and files only: never a request. What a saved value was
    priced at, since a stored price never changes (#145: the form and the
    API say which hour and source).
    """
    if moment == "day":
        day = price_history.utc_day(when)
        usd = price_history.stored_price(db, day)
        at = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        return None if usd is None else Priced(usd, "day", at, price_history.stored_source(db, day) or "")
    hour = hour_of(when)
    row = db.get(BtcPriceHourly, hour)
    if row is not None:
        return Priced(Decimal(row.usd), "hour", _utc(hour), row.source)
    prices = _year_of(hour, {} if years is None else years)
    return Priced(prices[hour], "hour", _utc(hour), "bitstamp") if prices and hour in prices else None


def read_year_files(whens, years: dict) -> None:
    """Read into `years`, stored_price_at's cache for one request, the year
    files holding these moments, so its lookups read none: the AI preview
    does it before its dry run takes SQLite's write lock (#204). The years
    kept in memory stay as they were (the dry run's own pricing reads
    those), and a year not here yet isn't noted: a download may bring it."""
    for when in whens:
        _year_of(hour_of(when), years, remember=False)
    for year in [year for year, prices in years.items() if prices is None]:
        del years[year]


def _year_of(hour: int, years: dict, remember: bool = True) -> dict[int, Decimal] | None:
    """The prices of the year file holding `hour`, from one request's cache
    (a list of many transactions): the manifest read and each year file
    parsed once, not once per row."""
    if "manifest" not in years:
        years["manifest"] = pf.read_manifest(pf.MANIFEST)
    line = next((y for y in years["manifest"] if y.first_hour <= hour <= y.last_hour), None)
    if line is not None and line.year not in years:
        years[line.year] = _year_prices(line, remember)
    return years.get(line.year) if line else None


# Session.info keys: the years whose download a lookup waited for, and the
# hours a source had no price for (hourly_price)
WAITED_FOR = "btctx_years_waited_for"
UNPRICED_HOURS = "btctx_hours_without_price"


def hourly_price(db: Session, when: datetime, wait: bool = True) -> tuple[Decimal, str] | None:
    """The opening price of `when`'s UTC hour and its source, or None when
    there's none. wait=False (Ledger Review's many lookups): a year not
    downloaded yet has none, though the download starts. A caller that has
    already written doesn't wait either (an import's later rows): it holds
    SQLite's write lock, which the owner's saves wait only 5 s for (#421).
    A session (a request) waits for a year once, and asks a source once for
    an hour it found none for: an import finds its prices first, then saves
    its rows with them (transaction.find_prices_first, #426); a day the
    sites failed to give isn't asked again soon (price_history's
    RETRY_SECONDS)."""
    hour = hour_of(when)
    if not pf.year_start(pf.FIRST_YEAR) <= hour <= _current_hour():
        return None
    stored = db.get(BtcPriceHourly, hour)
    if stored is not None:
        return Decimal(stored.usd), stored.source
    lines = pf.read_manifest(pf.MANIFEST)
    line = next((y for y in lines if y.first_hour <= hour <= y.last_hour), None)
    prices = _year_prices(line) if line else None
    if prices is not None:
        return prices[hour], "bitstamp"
    unpriced = db.info.setdefault(UNPRICED_HOURS, set())
    if hour in unpriced:  # a source had none a moment ago, in this request
        return None
    files_end = lines[-1].last_hour if lines else None
    found, keep = _from_sources(db, hour, files_end)
    if found is None and line is not None and start_download() and wait and _may_wait(db, line):
        prices = _wait_for_year(line)
        found = (prices[hour], "bitstamp") if prices is not None else None
    _store(db, keep)
    if found is None:
        unpriced.add(hour)
    return found


def _may_wait(db: Session, line: pf.YearLine) -> bool:
    """Whether a lookup may wait for its year's download: not holding the
    write lock (#421), and once a session."""
    waited = db.info.setdefault(WAITED_FOR, set())
    if price_history.writing(db) or line.year in waited:
        return False
    waited.add(line.year)
    return True


def start_download() -> bool:
    """
    Download, in the background, the year files that aren't here yet, when
    the owner's choice allows public sites. True while a download runs.
    """
    if not outbound.current().public_allowed:
        return False
    with _changed:
        if _state["running"]:
            return True
        if time.monotonic() - _state["failed_at"] < RETRY_SECONDS:
            return False
        return _begin()


def _begin() -> bool:
    """Start downloading the years that aren't here (with _changed held);
    False when none is missing."""
    missing = [line for line in pf.read_manifest(pf.MANIFEST) if _wanted(line)]
    if not missing:
        return False
    _state["running"] = True
    threading.Thread(target=_download, args=(missing,), name="btc-price-download", daemon=True).start()
    return True


def download_if_public() -> None:
    """At startup and when the price choice is saved: a choice that allows
    public sites (public, or your Mempool with its backup: a Mempool never
    has the hours before it began recording) brings the hourly history in
    now, so its progress shows (#145, the amendment's choice 1)."""
    if outbound.current().public_allowed:
        start_download()


def download_status() -> dict:
    """
    The hourly history's state, for the status line (services/price_status.py):
    how far it reaches, how many years are here and checked, and whether
    the download runs, failed, or isn't allowed by the choice. Reads only
    this install's files and memory: it never asks anything.
    """
    lines = pf.read_manifest(pf.MANIFEST)
    done = [line.year for line in lines if _verified(line)]
    mismatched = sorted(y for y, at in _state["mismatched"].items()
                        if time.monotonic() - at < MISMATCH_RETRY_SECONDS and y not in done)
    failed = _state["failed_wall"] if time.monotonic() - _state["failed_at"] < RETRY_SECONDS else None
    if lines and len(done) == len(lines):
        state = "complete"
    elif _state["running"]:
        state = "downloading"
    elif not outbound.current().public_allowed:
        state = "not_allowed"
    elif failed:
        state = "failed"
    else:
        state = "waiting"
    return {
        "until": pf.label(lines[-1].last_hour) if lines else None,
        "without_tor": outbound.history_without_tor(),  # #241: the owner's Yes, with Tor on
        "first_year": lines[0].year if lines else None,
        "shipped": False,  # the year files come with the app once Bitstamp agrees (#144)
        "years_total": len(lines),
        "years_done": len(done),
        "state": state,
        "failed_at": failed,
        "refused": state == "failed" and _state["refused"],
        "mismatched": mismatched,
    }


async def find_hours(hour: int, files_end: int | None, stored: set[int]) -> dict[int, tuple[Decimal, str]]:
    """
    What the chosen sources give while `hour` is missing. `hour` only
    decides whether to ask the public sites (after the year files, and
    only when the own mempool server doesn't have it): no request names
    it. `stored`: the hours after the files already kept.
    """
    settings = outbound.current()
    found: dict[int, tuple[Decimal, str]] = {}
    rows, _ = await price_history.own_node_rows()  # none (and none kept) without a mempool server
    price = live_hours(rows).get(hour)
    if price is not None:
        found[hour] = (price, "mempool")
    if hour not in found and files_end is not None and hour > files_end and settings.public_allowed:
        found.update({h: (p, "bitstamp") for h, p in (await _bitstamp_after(files_end, stored)).items()})
    return found


def live_hours(rows: list[dict]) -> dict[int, Decimal]:
    """
    A mempool server's prices it recorded live, each hour: the rows at
    exactly HH:00 from 31 days after its record turns hourly (its first run
    fills the month before with later prices), whose rows an hour before and
    after exist and agree within 2%. Older weekly and daily rows never match.
    The answer for the last rows given is kept (they're asked at most every
    10 minutes).
    """
    if rows is _live["rows"]:
        return _live["hours"]
    by_time: dict[int, Decimal] = {}
    for row in rows:
        try:
            price = Decimal(str(row["USD"]))
            t = int(row["time"])
        except (KeyError, TypeError, ValueError, ArithmeticError):
            continue
        if t % HOUR == 0 and pf.usable_price(price) is not None:
            by_time[t] = price
    start = next((t for t in sorted(by_time) if all(t + k * HOUR in by_time for k in range(1, 24))), None)
    out = {}
    if start is not None:
        begin, limit = start + MEMPOOL_FILL_DAYS * 86400, price_history.MEMPOOL_TOLERANCE
        for t, price in by_time.items():
            before, after = by_time.get(t - HOUR), by_time.get(t + HOUR)
            if t >= begin and before and after and abs(before - price) <= price * limit \
                    and abs(after - price) <= price * limit:
                out[t] = price.quantize(pf.CENT)
    _live.update(rows=rows, hours=out)
    return out


def folder() -> Path:
    return Path(DATA_DIR) / FOLDER_NAME


def reset_state() -> None:
    """Forget downloads and cached years (tests)."""
    with _years_lock:
        _years.clear()
    _state.update(running=False, failed_at=-1e9, failed_wall=None, refused=False, mismatched={}, public_at=-1e9,
                  verified={}, again=False)
    _live.update(rows=None, hours={})


_live: dict = {}
reset_state()


def _utc(hour: int) -> datetime:
    return datetime.fromtimestamp(hour, tz=timezone.utc)


def _current_hour() -> int:
    return int(time.time()) // HOUR * HOUR


# The year files
def _year_prices(line: pf.YearLine, remember: bool = True) -> dict[int, Decimal] | None:
    """A downloaded year's prices, if its file gives its line's fingerprint;
    kept in memory with the latest years used, unless `remember` is False."""
    with _years_lock:
        cached = _years.get(line.year)
        if cached is not None and cached[0] == line.sha256:
            if remember:
                _years.move_to_end(line.year)
            return cached[1]
    text = _file_text(line)
    if text is None:
        return None
    prices = pf.parse_year_text(text)
    if remember:
        with _years_lock:
            _years[line.year] = (line.sha256, prices)
            while len(_years) > CACHED_YEARS:
                _years.popitem(last=False)
    return prices


def _verified(line: pf.YearLine) -> bool:
    """Whether the year's file is here and gives its fingerprint (each
    file is checked once while it stays the same size and age)."""
    try:
        stat = (folder() / f"{line.year}.csv").stat()
    except OSError:
        return False
    key = (line.sha256, stat.st_size, stat.st_mtime_ns)
    if _state["verified"].get(line.year) != key:
        if _file_text(line) is None:
            return False
        _state["verified"][line.year] = key
    return True


def _file_text(line: pf.YearLine) -> str | None:
    try:
        text = (folder() / f"{line.year}.csv").read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return text if pf.fingerprint(text) == line.sha256 else None


def _from_sources(db: Session, hour: int, files_end: int | None):
    """The chosen source's price for the hour (or None), and the hours to keep:
    the one asked, and Bitstamp's after the files."""
    stored = set()
    if files_end is not None:
        stored = {h for (h,) in db.query(BtcPriceHourly.hour).filter(BtcPriceHourly.hour > files_end)}
    try:
        found = price_history._run(find_hours(hour, files_end, stored))
    except Exception as exc:
        logger.warning("Hourly BTC price lookup failed: %s", exc)
        price_status.record_refusal(exc)  # through Tor: the card asks (#241)
        found = {}
    keep = {h: v for h, v in found.items() if h == hour or (files_end is not None and h > files_end)}
    return found.get(hour), keep


def _wait_for_year(line: pf.YearLine) -> dict[int, Decimal] | None:
    deadline = time.monotonic() + WAIT_SECONDS
    with _changed:
        while True:
            prices = _year_prices(line)
            remaining = deadline - time.monotonic()
            if prices is not None or remaining <= 0 or not _state["running"]:
                return prices
            _changed.wait(remaining)


def _store(db: Session, prices: dict[int, tuple[Decimal, str]]) -> None:
    rows = [{"hour": h, "usd": usd, "source": src} for h, (usd, src) in sorted(prices.items())]

    def write(session: Session) -> None:
        for i in range(0, len(rows), STORE_CHUNK):
            session.execute(sqlite_insert(BtcPriceHourly).values(rows[i:i + STORE_CHUNK]).on_conflict_do_nothing())

    if rows:
        price_history.keep(db, write)  # at once, unless the caller has already written (#364)


def _wanted(line: pf.YearLine) -> bool:
    mismatched_at = _state["mismatched"].get(line.year, -1e9)
    return time.monotonic() - mismatched_at >= MISMATCH_RETRY_SECONDS and _file_text(line) is None


def _download(lines: list[pf.YearLine]) -> None:
    try:
        asyncio.run(_download_years(lines))
    except ChoiceChanged:
        logger.info("Hourly BTC prices: the download stopped (public price sites are no longer allowed)")
    except Exception as exc:
        logger.warning("Hourly BTC prices: the download from Bitstamp failed: %s", exc)
        price_status.record_refusal(exc)
        _state["refused"] = price_status.refused_by_bitstamp(exc)
        _state["failed_at"] = time.monotonic()
        _state["failed_wall"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    finally:
        _end_run()


def _end_run() -> None:
    """A download ended. One the owner's Yes came during (#241, try_again_now)
    starts again at once, by the route in force now: its failure through
    Tor doesn't make it wait RETRY_SECONDS."""
    with _changed:
        _state["running"] = False
        if _state["again"]:
            _state.update(again=False, failed_at=-1e9, failed_wall=None, refused=False)
            if outbound.current().public_allowed:
                _begin()
        _changed.notify_all()


async def _download_years(lines: list[pf.YearLine]) -> None:
    """Newest year first, each in its fixed blocks: the same requests on every install."""
    _log_without_tor("the year files")
    for line in sorted(lines, key=lambda y: -y.year):
        prices = await pf.download_year(ChoiceClient(), line.year, line.last_hour, _pause)
        _save_year(line, prices)
        with _changed:
            _changed.notify_all()


class ChoiceChanged(Exception):
    """Public price sites are no longer allowed: nothing more is asked."""


class ChoiceClient:
    """Asks each request with the owner's choice as it is then: never once
    public sites aren't allowed, and through the proxy (Tor) set then, or
    directly after the owner's Yes to the history without Tor (#241)."""

    async def get(self, url, **kwargs):
        if not outbound.current().public_allowed:
            raise ChoiceChanged
        async with outbound.history_client(timeout=outbound.HISTORY_TIMEOUT) as client:
            return await client.get(url, **kwargs)


def _log_without_tor(what: str) -> None:
    if outbound.history_without_tor():
        logger.info("Hourly BTC prices: Bitstamp's fixed blocks for %s go without Tor (agreed on %s)",
                    what, outbound.agreed_on())


def try_again_now() -> None:
    """After the owner's Yes to the history without Tor (#241): what Bitstamp
    refused through Tor is asked again now, not RETRY_SECONDS later; a
    download under way starts again once it ends (_end_run)."""
    with _changed:
        _state.update(failed_at=-1e9, failed_wall=None, refused=False, public_at=-1e9, again=_state["running"])
    price_history.try_again_now()
    download_if_public()


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


# Bitstamp after the year files
async def _bitstamp_after(files_end: int, stored: set[int]) -> dict[int, Decimal]:
    """
    Bitstamp's hours after the year files, in fixed blocks from the hour
    after them, skipping blocks whose every hour is kept already, at most
    every 10 minutes. The current hour only once it has a trade: until
    then its open can change.
    """
    if time.monotonic() - _state["public_at"] < RETRY_SECONDS:
        return {}
    _state["public_at"] = time.monotonic()
    current, size = _current_hour(), pf.BLOCK_HOURS * HOUR
    starts = [start for start in range(files_end + HOUR, current + 1, size)
              if not all(h in stored for h in range(start, min(start + size, current + HOUR), HOUR))]
    if starts:
        _log_without_tor("the hours after the year files")
    client, out = ChoiceClient(), {}
    for start in starts:
        for row in await pf.bitstamp_candles(client, start):
            kept = _kept_open(row, current)
            if kept:
                out[kept[0]] = kept[1]
    return out


def _kept_open(row: dict, current: int) -> tuple[int, Decimal] | None:
    """
    A Bitstamp candle's hour and open, or None: its open is no price
    (pf.usable_price), its time isn't an hour, or it's the current hour
    before its first trade. A candle that doesn't parse is skipped, so it
    never costs the block's other hours.
    """
    try:
        h = int(row["timestamp"])
        traded = h < current or (h == current and Decimal(str(row["volume"])) > 0)
        price = pf.usable_price(row["open"])
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return None
    return (h, price) if traded and h % HOUR == 0 and price is not None else None
