"""
Reading an exchange's file cell by cell (B5b): its rows, its header, and the
numbers and moments exchanges write ("-$1,234.56", "(1.50)", "0.01 BTC",
"Jan 15 2025 06:37:33", "2025-12-30 23:22:22 PST", "2024-11-16
17:39:46+00"). What a cell can't say for sure is refused, never guessed.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from backend.schemas.csv_import import CSVParseError
from backend.services.calculation import CENT, SAT, btc_text
from backend.services.csv_import import unreadable_csv
from backend.services.river_import import FileRow

# The header is looked for among a file's first rows: an exchange may write
# its name and address above it (Swan, Coinbase)
HEADER_SEARCH = 30
# A warning lists this many of its rows, then says how many more
ROWS_LISTED = 20
# A mapping's zone for a file whose every date carries its own
ZONE_IN_DATES = "dates"

Records = list[tuple[int, list[str]]]


@dataclass
class FileRead:
    """What a mapping read from a file: its events, its errors and
    warnings, and how many rows of data the file has."""
    rows: list[FileRow] = field(default_factory=list)
    errors: list[CSVParseError] = field(default_factory=list)
    warnings: list[CSVParseError] = field(default_factory=list)
    total_rows: int = 0


def records(content: bytes) -> Records | CSVParseError:
    """The file's rows, each with its number as a spreadsheet shows it (the
    first row is 1), blank rows left out; or what stops it being read.
    UTF-8, with or without a byte-order mark, else Latin-1, as the CSV
    import reads a file."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error as exc:
        return unreadable_csv(exc)
    return [(number, cells) for number, cells in enumerate(rows, start=1) if any(c.strip() for c in cells)]


class Header:
    """A file's header row: its number, and each column's place by its name (any case)."""

    def __init__(self, number: int, cells: list[str]):
        self.number = number
        self.names = [c.strip() for c in cells]
        self.places: dict[str, int] = {}
        for place, name in enumerate(self.names):
            self.places.setdefault(name.lower(), place)

    def place(self, names: Iterable[str]) -> int | None:
        """The place of the first of `names` the header has."""
        return next((self.places[n.lower()] for n in names if n.lower() in self.places), None)

    def name(self, names: Iterable[str]) -> str | None:
        """That column's name as the file writes it."""
        place = self.place(names)
        return self.names[place] if place is not None else None


def find_header(rows: Records, needed: dict[str, tuple[str, ...]], whose: str) -> Header | CSVParseError:
    """The first of the file's first rows naming a column for each of
    `needed`'s roles (any of its names); else an error naming those the
    likeliest row lacks."""
    best, missing = None, list(needed)
    for number, cells in rows[:HEADER_SEARCH]:
        header = Header(number, cells)
        lacking = [role for role, names in needed.items() if header.place(names) is None]
        if not lacking:
            return header
        if len(lacking) < len(missing):
            best, missing = header, lacking
    said = ", ".join(needed[role][0] for role in missing)
    return CSVParseError(row_number=best.number if best else 0, column=None, severity="error",
                         message=f"This does not look like {whose} file. Missing columns: {said}")


class Cells:
    """One row's cells, by its header; a merged row (Strike's pieces of one
    order) keeps each piece's."""

    def __init__(self, number: int, header: Header, cells: list[str], pieces: list[Cells] | None = None):
        self.number = number
        self.header = header
        self.cells = cells
        self.pieces = pieces or [self]

    def get(self, names: Iterable[str]) -> str:
        """The cell of the first of `names` the header has; "" when none."""
        place = self.header.place(names)
        return self.cells[place].strip() if place is not None and place < len(self.cells) else ""


class RowError(ValueError):
    """A row that can't be read: its error, and the column it's in."""

    def __init__(self, message: str, column: str | None = None):
        super().__init__(message)
        self.column = column

    def problem(self, row_number: int) -> CSVParseError:
        return CSVParseError(row_number=row_number, column=self.column, severity="error", message=str(self))


class LeftOut:
    """The rows not read, by reason: one warning for each reason, naming its
    rows, so a long file's other assets don't give a warning a row."""

    def __init__(self):
        self.reasons: dict[str, list[int]] = {}

    def add(self, reason: str, number: int) -> None:
        self.reasons.setdefault(reason, []).append(number)

    def warnings(self) -> list[CSVParseError]:
        return [CSVParseError(row_number=0, column=None, severity="warning",
                              message=f"{rows_said(numbers)} {reason}: left out.")
                for reason, numbers in self.reasons.items()]


def rows_said(numbers: list[int]) -> str:
    """"Row 5", "Rows 5, 9 and 12", "Rows 5, 9, … and 30 more"."""
    if len(numbers) == 1:
        return f"Row {numbers[0]}"
    if len(numbers) > ROWS_LISTED:
        return f"Rows {', '.join(map(str, numbers[:ROWS_LISTED]))}, … and {len(numbers) - ROWS_LISTED} more"
    return f"Rows {', '.join(map(str, numbers[:-1]))} and {numbers[-1]}"


# A number as exchanges write it. A thousands group never starts with a
# zero, and a bitcoin amount has no thousands separator at all: read as one,
# a decimal comma would make "0,005" BTC 5
# (#452). Digits are ASCII: Python's \d would take "٠.٥" too.
_POINT = re.compile(r"([1-9]\d{0,2}(,\d{3})+|\d+)(\.\d+)?|\.\d+", re.ASCII)
_COMMA = re.compile(r"([1-9]\d{0,2}(\.\d{3})+|\d+)(,\d+)?|,\d+", re.ASCII)
_POINT_ONLY = re.compile(r"\d+(\.\d+)?|\.\d+", re.ASCII)
_COMMA_ONLY = re.compile(r"\d+(,\d+)?|,\d+", re.ASCII)
# The currency a cell may write beside its number, by how it writes it
_UNITS = {"US$": "USD", "USD": "USD", "$": "USD", "BTC": "BTC", "XBT": "BTC", "₿": "BTC"}


def read_number(text: str, decimal_comma: bool = False, column: str | None = None,
                bitcoin: bool = False, unit: str | None = None) -> Decimal | None:
    """The number a cell holds (read_amount's, as strictly as a bitcoin
    amount's when `unit` is BTC); a RowError when the cell writes another
    currency than `unit`: "$5.00" is never 5 BTC."""
    value, written = read_amount(text, decimal_comma, column, bitcoin or unit == "BTC")
    if unit and written and written != unit:
        raise RowError(f"{column or 'A number'} '{text.strip()}' isn't {'bitcoin' if unit == 'BTC' else 'dollars'}.",
                       column)
    return value


def read_amount(text: str, decimal_comma: bool = False, column: str | None = None,
                bitcoin: bool = False) -> tuple[Decimal | None, str | None]:
    """
    (the number a cell holds, with its sign; the currency it writes beside
    it, "USD" or "BTC", or None). Blank or a dash: (None, None). Takes what
    exchanges write around a number: a currency sign or code before or
    after it, a minus before or after the sign ("-$100.00", "$-100.00"),
    parentheses for a negative, thousands separators ("1,234.56", or
    "1.234,56" when the file writes a decimal comma; never in a `bitcoin`
    amount). Anything else is a RowError, never read as another number.
    """
    said = text.strip()
    if not said or said in ("-", "—"):
        return None, None
    unreadable = RowError(f"{column or 'A number'} '{said}' isn't a number BitcoinTX can read.", column)
    negative = said.startswith("(") and said.endswith(")")
    rest, units = _without_units(said[1:-1] if negative else said)
    if rest[:1] in ("+", "-"):
        negative = negative or rest[0] == "-"
        rest, more = _without_units(rest[1:])
        units |= more
    if bitcoin:
        pattern = _COMMA_ONLY if decimal_comma else _POINT_ONLY
    else:
        pattern = _COMMA if decimal_comma else _POINT
    if len(units) > 1 or not pattern.fullmatch(rest):
        raise unreadable
    point, thousands = (",", ".") if decimal_comma else (".", ",")
    try:
        value = Decimal(rest.replace(thousands, "").replace(point, "."))
    except InvalidOperation:
        raise unreadable from None
    return (-value if negative else value), next(iter(units), None)


def _without_units(text: str) -> tuple[str, set[str]]:
    """The text without a currency sign or code at either end, and the currencies they write."""
    text, found = text.strip(), set()
    for unit, currency in _UNITS.items():
        if text.upper().startswith(unit):
            text, found = text[len(unit):].strip(), found | {currency}
        if text.upper().endswith(unit):
            text, found = text[:-len(unit)].strip(), found | {currency}
    return text, found


def to_sats(value: Decimal, number: int, column: str | None, warnings: list[CSVParseError]) -> Decimal:
    """A bitcoin amount to the satoshi: a finer one (Kraken writes ten
    places) is rounded, and the warning says so; one too large to hold is
    the row's error."""
    rounded = _quantized(value, SAT, column)
    if rounded != value:
        warnings.append(CSVParseError(
            row_number=number, column=column, severity="warning",
            message=f"{value.normalize():f} BTC is rounded to {btc_text(rounded)} BTC: BitcoinTX counts whole satoshis."))
    return rounded


def to_cents(value: Decimal, column: str | None = None) -> Decimal:
    """A dollar amount to the cent, an exact half cent to the even one, as a
    value worked out from a price is (#556): Kraken writes four places. One
    too large to hold is the row's error."""
    return _quantized(value, CENT, column)


def _quantized(value: Decimal, places: Decimal, column: str | None) -> Decimal:
    try:
        return value.quantize(places, rounding=ROUND_HALF_EVEN)
    except InvalidOperation:
        raise RowError(f"{column or 'An amount'} '{value}' is too large to be one.", column) from None


# A moment as exchanges write it

# US zone abbreviations (Cash App writes the account's), each one fixed offset
ZONE_ABBREVIATIONS = {
    "UTC": 0, "GMT": 0, "EST": -5, "EDT": -4, "CST": -6, "CDT": -5, "MST": -7, "MDT": -6,
    "PST": -8, "PDT": -7, "AKST": -9, "AKDT": -8, "HST": -10,
}
_OFFSET = re.compile(r"\s?([+-])(\d{2}):?(\d{2})?$")
_ENDS_WITH_TIME = re.compile(r"\d:\d{2}(:\d{2}(\.\d+)?)?$")
_ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}T")
_FRACTION = re.compile(r"(:\d{2})\.\d+")
_TIMES = ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p")
_DAYS = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%b %d %Y", "%b %d, %Y", "%B %d %Y", "%B %d, %Y", "%d %b %Y")


def read_moment(text: str, zone: str, day_first: bool = False, column: str = "Date") -> datetime:
    """
    The moment in UTC. An offset or zone the text gives ("Z", "+00",
    "-05:00", "UTC", "PST") is honored; a time without one is in `zone`
    ("UTC", a tzdata name; ZONE_IN_DATES: refused). A local time the clocks
    skip or repeat there is refused, never guessed: an hour off moves a
    payout's price and the minute the duplicate check matches (#253). A
    date needs its time, for that minute.
    """
    said = " ".join(text.split())
    rest, offset = _zone_of(said)
    if _ISO_DAY.match(rest):
        rest = rest.replace("T", " ", 1)
    naive = _naive(_FRACTION.sub(r"\1", rest), day_first)
    if naive is None:
        raise RowError(f"{column} '{said}' isn't a date and time BitcoinTX can read.", column)
    if offset is not None:
        return naive.replace(tzinfo=timezone(offset)).astimezone(timezone.utc)
    if zone == ZONE_IN_DATES:
        raise RowError(f"{column} '{said}' doesn't say its timezone, which this file's dates do.", column)
    return _local(naive, zone, said, column)


def _zone_of(text: str) -> tuple[str, timedelta | None]:
    """The text without its zone, and the zone's offset (None when it gives none)."""
    if text.endswith("Z") and text[-2:-1].isdigit():
        return text[:-1], timedelta(0)
    head, _space, word = text.rpartition(" ")
    if head and word.upper() in ZONE_ABBREVIATIONS:
        return head, timedelta(hours=ZONE_ABBREVIATIONS[word.upper()])
    found = _OFFSET.search(text)
    if found and _ENDS_WITH_TIME.search(text[:found.start()]):
        sign = -1 if found.group(1) == "-" else 1
        offset = timedelta(hours=int(found.group(2)), minutes=int(found.group(3) or 0))
        return text[:found.start()].strip(), sign * offset
    return text, None


def _naive(text: str, day_first: bool) -> datetime | None:
    days = tuple(d.replace("%m/%d", "%d/%m") for d in _DAYS) if day_first else _DAYS
    for day in days:
        for time in _TIMES:
            try:
                return datetime.strptime(text, f"{day} {time}")
            except ValueError:
                continue
    return None


def _local(naive: datetime, zone: str, said: str, column: str) -> datetime:
    """A local time in `zone`, refused where the clocks change."""
    tz = timezone.utc if zone == "UTC" else ZoneInfo(zone)
    first, second = naive.replace(tzinfo=tz, fold=0), naive.replace(tzinfo=tz, fold=1)
    if first.utcoffset() != second.utcoffset():
        raise RowError(f"{column} '{said}' is when the clocks change in {zone}, so its time is unclear: "
                       "write it with its offset (such as -05:00).", column)
    return first.astimezone(timezone.utc)
