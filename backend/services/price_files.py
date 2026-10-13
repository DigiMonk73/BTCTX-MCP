"""
The hourly BTC price history's year files (#144): their format, the
manifest of fingerprints, and how a year is rebuilt from Bitstamp's hourly
candles. scripts/price_history.py keeps the manifest (refresh, verify,
check-sources, release-check); the app's verified download builds the same
text and checks it against the same fingerprint, so every install holds
exactly the same prices and anyone can check them.

A year file, YYYY.csv (UTF-8, "\\n" line endings):

    hour_utc,usd
    2024-03-10T14:00Z,69123.45

one row per UTC hour from 1 January 00:00 to the manifest's last hour,
in order. `usd` is Bitstamp's BTC/USD hourly opening price, two decimals:
the price when the hour began. Every hour has a row (Bitstamp has a candle
for every hour since 2013; one without a trade opens at the last price),
so a year with a missing hour is incomplete and is never used.

The manifest, MANIFEST.csv beside it, holds one line per year:

    year,first_hour,last_hour,hours,sha256

The SHA-256 is of the year file's exact text. A closed year (all its hours)
never changes; the open year grows at each release, and its old text is
always the start of the new one.

Nothing here names a ledger's dates: a year is asked in fixed blocks of
1,000 hours from 1 January 00:00 UTC, the same requests on every install.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

FIRST_YEAR = 2013  # earlier years had too few trades for an hourly price (#144, finding 2)
HOUR = 3600
BLOCK_HOURS = 1000  # hours per request: Bitstamp's limit
FOLDER = Path(__file__).resolve().parent.parent / "assets" / "btc_prices"
MANIFEST = FOLDER / "MANIFEST.csv"
HEADER = "hour_utc,usd"
MANIFEST_FIELDS = ["year", "first_hour", "last_hour", "hours", "sha256"]
BITSTAMP_OHLC_URL = "https://www.bitstamp.net/api/v2/ohlc/btcusd/"
CENT = Decimal("0.01")
_LABEL = re.compile(r"\d{4}-\d\d-\d\dT\d\d:00Z")


class IncompleteYear(ValueError):
    """A year's prices miss an hour."""


@dataclass(frozen=True)
class YearLine:
    """One line of the manifest: hours are Unix seconds (UTC)."""
    year: int
    first_hour: int
    last_hour: int
    hours: int
    sha256: str

    def is_closed(self) -> bool:
        return self.last_hour == year_end(self.year)


# Hours and their labels
def year_start(year: int) -> int:
    return int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp())


def year_end(year: int) -> int:
    """The year's last hour (31 December 23:00 UTC)."""
    return year_start(year + 1) - HOUR


def year_of(hour: int) -> int:
    return datetime.fromtimestamp(hour, tz=timezone.utc).year


def last_complete_hour(now: float) -> int:
    """The newest hour that has ended."""
    return int(now) // HOUR * HOUR - HOUR


def label(hour: int) -> str:
    return datetime.fromtimestamp(hour, tz=timezone.utc).strftime("%Y-%m-%dT%H:00Z")


def from_label(text: str) -> int:
    if not _LABEL.fullmatch(text):
        raise ValueError(f"not an hour label: {text!r}")
    return int(datetime.strptime(text, "%Y-%m-%dT%H:00Z").replace(tzinfo=timezone.utc).timestamp())


def usd(price: Decimal) -> str:
    """Two decimals, never an exponent (Bitstamp's prices have at most two)."""
    return f"{price.quantize(CENT, rounding=ROUND_HALF_UP):f}"


def usable_price(value) -> Decimal | None:
    """
    A site's price to the cent, or None when it's no price: not a number,
    not finite, or under one cent once rounded (never $0, AGENTS.md). Every
    price a site gives passes here before it's kept (#198), except the year
    files, which their fingerprints check.
    """
    try:
        price = Decimal(str(value))
        cents = price.quantize(CENT) if price.is_finite() else None
    except ArithmeticError:  # not a number, or too large to round
        return None
    return cents if cents is not None and cents > 0 else None


# A year's text and fingerprint
def year_text(prices: dict[int, Decimal], year: int, last_hour: int) -> str:
    """The year file from 1 January 00:00 to `last_hour`; IncompleteYear if an hour is missing."""
    hours = range(year_start(year), last_hour + 1, HOUR)
    missing = [h for h in hours if h not in prices]
    if missing:
        raise IncompleteYear(f"{year}: {len(missing)} hours missing, the first {label(missing[0])}")
    rows = [f"{label(h)},{usd(prices[h])}" for h in hours]
    return "\n".join([HEADER, *rows]) + "\n"


def prefix(text: str, hours: int) -> str:
    """The text of a year's first `hours` hours (an older manifest line's file)."""
    lines = text.split("\n")
    return "\n".join(lines[:hours + 1]) + "\n"


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def line_for(year: int, text: str) -> YearLine:
    rows = text.rstrip("\n").split("\n")[1:]
    first, last = from_label(rows[0].split(",")[0]), from_label(rows[-1].split(",")[0])
    return YearLine(year, first, last, len(rows), fingerprint(text))


def parse_year_text(text: str) -> dict[int, Decimal]:
    """A year file's prices by hour."""
    lines = text.rstrip("\n").split("\n")
    if lines[0] != HEADER:
        raise ValueError("not a price year file")
    out = {}
    for row in lines[1:]:
        hour, price = row.split(",")
        out[from_label(hour)] = Decimal(price)
    return out


# The manifest
def read_manifest(path: Path = MANIFEST) -> list[YearLine]:
    if not path.exists():
        return []
    reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8")))
    if reader.fieldnames != MANIFEST_FIELDS:
        raise ValueError(f"{path.name}: the header must be {','.join(MANIFEST_FIELDS)}")
    return [YearLine(int(r["year"]), from_label(r["first_hour"]), from_label(r["last_hour"]),
                     int(r["hours"]), r["sha256"]) for r in reader]


def manifest_text(lines: list[YearLine]) -> str:
    rows = [",".join(MANIFEST_FIELDS)]
    rows += [f"{y.year},{label(y.first_hour)},{label(y.last_hour)},{y.hours},{y.sha256}" for y in lines]
    return "\n".join(rows) + "\n"


def manifest_problems(lines: list[YearLine], now: float) -> list[str]:
    """What's wrong with the manifest's shape (empty when it's well formed)."""
    if not lines:
        return ["the manifest has no years"]
    problems = []
    for i, line in enumerate(lines):
        problems += _line_problems(line, now, closed=i < len(lines) - 1)
        if line.year != FIRST_YEAR + i:
            problems.append(f"{line.year}: the years must run from {FIRST_YEAR}, one line each")
    return problems


def _line_problems(line: YearLine, now: float, closed: bool) -> list[str]:
    problems = []
    if line.first_hour != year_start(line.year):
        problems.append(f"{line.year}: first_hour isn't 1 January 00:00 UTC")
    if not year_start(line.year) <= line.last_hour <= year_end(line.year):
        problems.append(f"{line.year}: last_hour is outside the year")
    if line.hours != (line.last_hour - line.first_hour) // HOUR + 1:
        problems.append(f"{line.year}: hours doesn't match first_hour to last_hour")
    if closed and not line.is_closed():
        problems.append(f"{line.year}: a year before the last must have every hour")
    if line.last_hour > last_complete_hour(now):
        problems.append(f"{line.year}: last_hour is in the future")
    if not re.fullmatch(r"[0-9a-f]{64}", line.sha256):
        problems.append(f"{line.year}: sha256 isn't 64 hex digits")
    return problems


# Bitstamp: fixed blocks, the same on every install
def block_starts(year: int, last_hour: int) -> list[int]:
    """The year's blocks: 1,000 hours from 1 January 00:00 UTC, then the next 1,000…"""
    return list(range(year_start(year), last_hour + 1, BLOCK_HOURS * HOUR))


async def bitstamp_candles(client, start: int) -> list[dict]:
    """Bitstamp's hourly candles for the 1,000 hours from `start`, as it sends them."""
    resp = await client.get(BITSTAMP_OHLC_URL, params={"step": HOUR, "limit": BLOCK_HOURS, "start": start})
    resp.raise_for_status()
    return resp.json()["data"]["ohlc"]


async def bitstamp_block(client, start: int) -> dict[int, Decimal]:
    """Bitstamp's hourly opens for the 1,000 hours from `start`."""
    rows = await bitstamp_candles(client, start)
    return {int(r["timestamp"]): Decimal(str(r["open"])) for r in rows if int(r["timestamp"]) % HOUR == 0}


async def download_year(client, year: int, last_hour: int, pause=None) -> dict[int, Decimal]:
    """A year's hourly opens up to `last_hour`, in its fixed blocks. `pause` is awaited between requests."""
    prices: dict[int, Decimal] = {}
    for i, start in enumerate(block_starts(year, last_hour)):
        if i and pause:
            await pause()
        prices.update(await bitstamp_block(client, start))
    first = year_start(year)
    return {h: p for h, p in prices.items() if first <= h <= last_hour}
