"""
One importer for any exchange's CSV (B5b, 2.0 spec 7.4; the owner's decision
17 on #251, #338). A file is read by its mapping (exchange_mappings) into
river_import's FileRows, which River's adapter turns into proposals for the
exchange and the wallet the owner chose; River's duplicate check (#253) and
River's save then take them as they take River's rows. River's own file is
read by River's reader, exactly as before; Kraken's ledger by its own.

A row that isn't read is never dropped in silence: each reason (another
asset, a row not completed, a kind the mapping doesn't read, dollars alone,
a trade for another asset, a repeat) gives one warning naming its rows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from backend.schemas.csv_import import CSVParseError
from backend.services.csv_import import TOO_MANY_FIELDS
from backend.services.exchange_cells import (
    HEADER_SEARCH,
    Cells,
    FileRead,
    Header,
    LeftOut,
    RowError,
    find_header,
    read_moment,
    read_number,
    records,
    to_cents,
    to_sats,
)
from backend.services.exchange_kraken import KRAKEN_COLUMNS, read_ledger
from backend.services.exchange_mappings import (
    CONVERT,
    DOLLARS,
    EVENTS,
    KRAKEN_LEDGER,
    LEAVE_OUT,
    READY_MADE,
    RIVER_FILE,
    Mapping,
)
from backend.services.river_import import (
    BUY,
    PAYOUT_SOURCES,
    RECEIVE,
    RIVER_REQUIRED_COLUMNS,
    SELL,
    SEND,
    FileRow,
    RiverAccounts,
    RiverProposal,
    adapt_river_rows,
    adapt_rows,
    parse_river_csv,
    rows_in_file,
)

# What the column matcher shows of a file: its first rows, and the words in each column
SAMPLES, MAX_VALUES = 5, 30
NO_ROWS = "No data rows found in file."


@dataclass
class Proposed:
    """A file's proposals, its errors and warnings, and its rows of data."""
    proposals: list[RiverProposal]
    errors: list[CSVParseError]
    warnings: list[CSVParseError]
    total_rows: int


def propose_file(content: bytes, mapping: Mapping, accounts: RiverAccounts) -> Proposed:
    """The file read by `mapping`, as proposals into `accounts`."""
    if mapping.reader == RIVER_FILE:
        rows, errors = parse_river_csv(content)
        proposals, more_errors, warnings = adapt_river_rows(rows, accounts)
        return Proposed(proposals, [*errors, *more_errors], warnings, rows_in_file(rows, errors))
    read = read_file(content, mapping)
    proposals, more_errors, warnings = adapt_rows(read.rows, accounts, from_bank=mapping.funding == "bank")
    problems = sorted([*read.warnings, *warnings], key=lambda w: w.row_number)  # a warning naming rows first
    return Proposed(proposals, [*read.errors, *more_errors], problems, read.total_rows)


def read_file(content: bytes, mapping: Mapping) -> FileRead:
    """The file's events by `mapping` (one row an event, or Kraken's
    ledger), or the error that stops it being read at all."""
    rows = records(content)
    if isinstance(rows, CSVParseError):
        return FileRead(errors=[rows])
    if mapping.reader == KRAKEN_LEDGER:
        return read_ledger(rows, f"{mapping.name}'s")
    header = find_header(rows, _needed(mapping), f"{mapping.name}'s")
    if isinstance(header, CSVParseError):
        return FileRead(errors=[header])
    return _read_rows([(n, cells) for n, cells in rows if n > header.number], header, mapping)


def _needed(mapping: Mapping) -> dict[str, tuple[str, ...]]:
    """The columns a file must have for the mapping: all it names but those
    some versions of the exchange's file lack."""
    return {role: names for role, names in mapping.columns.roles().items() if role not in mapping.optional}


def _read_rows(data: list[tuple[int, list[str]]], header: Header, mapping: Mapping) -> FileRead:
    read, left_out, rows = FileRead(total_rows=len(data)), LeftOut(), []
    for number, cells in data:
        if any(c.strip() for c in cells[len(header.names):]):
            read.errors.append(CSVParseError(row_number=number, column=None, severity="error", message=TOO_MANY_FIELDS))
        else:
            rows.append(Cells(number, header, cells))
    for row, kind in _events(rows, mapping, left_out):
        try:
            read.rows.append(file_row(row, kind, mapping, read.warnings))
        except RowError as exc:
            read.errors.append(exc.problem(row.number))
    read.warnings.extend(left_out.warnings())
    if not data:
        read.errors.append(CSVParseError(row_number=0, column=None, severity="error", message=NO_ROWS))
    return read


def _events(rows: list[Cells], mapping: Mapping, left_out: LeftOut) -> list[tuple[Cells, str]]:
    """The rows the mapping reads as events, each with its kind; the rest
    left out by reason. Strike's pieces of one order are merged first, so a
    piece reversed is left out with what it reverses."""
    rows = _without_repeats(rows, mapping, left_out)
    if mapping.merge_same_id:
        rows = _merged(rows, mapping, left_out)
    events = []
    for row in rows:
        kind = _kind_if_read(row, mapping, left_out)
        if kind is not None:
            events.append((row, kind))
    return events


def _without_repeats(rows: list[Cells], mapping: Mapping, left_out: LeftOut) -> list[Cells]:
    """A row whose id and every cell repeat an earlier row's is that row
    twice (overlapping exports joined): left out. Rows sharing only an id
    are kept (Strike's pieces of one order)."""
    names = mapping.columns.row_id
    if not rows or rows[0].header.place(names) is None:
        return rows
    seen, kept = set(), []
    for row in rows:
        key = (row.get(names), tuple(c.strip() for c in row.cells))
        if key[0] and key in seen:
            left_out.add(f"repeat an earlier row ({row.header.name(names)} and every cell the same)", row.number)
            continue
        seen.add(key)
        kept.append(row)
    return kept


def _merged(rows: list[Cells], mapping: Mapping, left_out: LeftOut) -> list[Cells]:
    """Rows sharing an id as one row, in the file's order, numbered and
    dated by its bitcoin piece (a target order's coins arrive after its
    dollars leave); a group whose bitcoin and dollars add up to nothing was
    reversed or cancelled, and is left out."""
    groups: dict[str, list[Cells]] = {}
    for row in rows:
        groups.setdefault(row.get(mapping.columns.row_id) or f"row {row.number}", []).append(row)
    kept = []
    for group in groups.values():
        if len(group) == 1:
            kept.append(group[0])
        elif _adds_up_to_nothing(group, mapping):
            for row in group:
                left_out.add("were reversed or cancelled (their pieces add up to nothing)", row.number)
        else:
            face = next((row for row in group if row.get(mapping.columns.btc)), group[0])
            kept.append(Cells(face.number, face.header, face.cells, pieces=group))
    return sorted(kept, key=lambda row: row.number)


def _adds_up_to_nothing(group: list[Cells], mapping: Mapping) -> bool:
    merged = Cells(group[0].number, group[0].header, group[0].cells, pieces=group)
    return all(not _signed(merged, names, mapping) for names in (mapping.columns.btc, mapping.columns.usd) if names)


def _kind_if_read(row: Cells, mapping: Mapping, left_out: LeftOut) -> str | None:
    """The row's kind when the mapping reads it as an event: bitcoin,
    completed, not left out by one of its rules, of a kind it reads, with
    bitcoin moving. Else None, the row left out with its reason."""
    columns = mapping.columns
    asset = row.get(columns.asset)
    word = kind_word(row, mapping)
    if mapping.kinds.get(word.lower()) == CONVERT and _mentions_bitcoin(row, mapping):
        left_out.add(_convert(word), row.number)
        return None
    if row.header.place(columns.asset) is not None and asset.lower() not in mapping.btc_assets:
        left_out.add(_not_bitcoin(asset, word), row.number)
        return None
    status = _unfinished(row, mapping)
    if status is not None:
        left_out.add(f"are {status}, not completed", row.number)
        return None
    rule = next((r for r in mapping.leave_out
                 if row.header.place((r.column,)) is not None and r.applies(row.get((r.column,)))), None)
    if rule is not None:
        left_out.add(rule.reason, row.number)
        return None
    kind = _kind(row, mapping, left_out)
    if kind in (SEND, RECEIVE, *PAYOUT_SOURCES) and not row.get(columns.btc) and row.get(columns.usd):
        left_out.add(f"move dollars, not bitcoin (“{kind_word(row, mapping)}”)", row.number)
        return None
    return kind


def _mentions_bitcoin(row: Cells, mapping: Mapping) -> bool:
    """Whether a convert's row is bitcoin's, or its notes name bitcoin (a
    convert into bitcoin, its row the other coin's)."""
    return (row.get(mapping.columns.asset).lower() in mapping.btc_assets
            or re.search(r"\bBTC\b", row.get(mapping.notes), re.IGNORECASE) is not None)


def _convert(word: str) -> str:
    """Why a trade of bitcoin for another coin is left out, and how to add it."""
    return (f"trade bitcoin for another asset (“{word}”): add each by hand, bitcoin given up as a Withdrawal, "
            "purpose Spent, with its dollar value as proceeds (a disposal: IRS Notice 2014-21), bitcoin "
            "received as a Deposit with its dollar value as cost basis")


def _not_bitcoin(asset: str, word: str) -> str:
    """Why a row of another asset is left out."""
    if asset.upper() in ("USD", "ZUSD"):
        return f"move dollars, not bitcoin (“{word}”)" if word else "move dollars, not bitcoin"
    if not asset:
        return "aren't bitcoin (their asset is blank)"
    return f"are {asset}, not bitcoin (BitcoinTX tracks bitcoin only)"


def _unfinished(row: Cells, mapping: Mapping) -> str | None:
    """A status (any piece's) that isn't a completed row's, as the file writes it; else None."""
    names = mapping.columns.status
    if row.header.place(names) is None:
        return None
    for piece in row.pieces:
        status = piece.get(names)
        said = status.lower()
        if (mapping.done and said not in mapping.done) or any(word in said for word in mapping.not_done):
            return status or "no status"
    return None


def _kind(row: Cells, mapping: Mapping, left_out: LeftOut) -> str | None:
    """The event the row's word for its kind means; else None, the row left
    out with the reason that word gives."""
    if mapping.kind is not None:
        return mapping.kind
    word = kind_word(row, mapping)
    kind = mapping.kinds.get(word.lower())
    if kind in EVENTS:
        return kind
    if kind == DOLLARS:
        left_out.add(f"move dollars, not bitcoin (“{word}”)", row.number)
    elif kind == CONVERT:
        left_out.add(_convert(word), row.number)
    elif kind == LEAVE_OUT:
        left_out.add(f"are “{word}”, which this mapping leaves out", row.number)
    else:
        left_out.add(f"are “{word or 'blank'}”, a kind of row this mapping doesn't read (add any that moved "
                     "bitcoin by hand)", row.number)
    return None


def kind_word(row: Cells, mapping: Mapping) -> str:
    """The file's word for the row's kind; a merged row's, its first piece's
    that is an event, so the dollar piece of a buy doesn't name it."""
    if mapping.kind is not None and not mapping.columns.kind:
        return ""
    words = [piece.get(mapping.columns.kind) for piece in row.pieces]
    return next((w for w in words if mapping.kinds.get(w.lower()) in EVENTS), words[0])


def file_row(row: Cells, kind: str, mapping: Mapping, warnings: list[CSVParseError]) -> FileRow:
    """The row as an event, in River's terms: a buy's cost and a sell's
    proceeds before the fee, a send's coins as they arrived, its fee on
    top; RowError when a cell can't be read."""
    columns = mapping.columns
    moment = read_moment(" ".join(filter(None, (row.get(columns.date), row.get(columns.time)))), mapping.zone,
                         mapping.day_first, row.header.name(columns.date) or "Date")
    btc = _signed(row, columns.btc, mapping)
    btc = to_sats(abs(btc), row.number, row.header.name(columns.btc), warnings) if btc is not None else None
    usd = _signed(row, columns.usd, mapping)
    usd = to_cents(abs(usd)) if usd is not None else None
    fee = _fee(row, kind, mapping, warnings) if kind in (BUY, SELL, SEND) else None
    if kind in mapping.after_fee and usd is not None and fee is not None:
        usd = usd - fee if kind == BUY else usd + fee
    if kind == SEND and mapping.send_fee_included and btc is not None and fee is not None:
        btc -= fee
    if kind in PAYOUT_SOURCES and not usd:
        usd = None  # no value given: the hour's price fills it
    currency = None if fee is None else "USD" if kind in (BUY, SELL) else "BTC"
    return FileRow(row.number, moment, kind, btc, usd, fee, currency, kind_word(row, mapping) or None)


def _signed(row: Cells, names: tuple[str, ...], mapping: Mapping) -> Decimal | None:
    """A number column's value with its sign, summed over a merged row's pieces."""
    if not names or row.header.place(names) is None:
        return None
    column = row.header.name(names)
    given = [v for v in (read_number(p.get(names), mapping.decimal_comma, column) for p in row.pieces) if v is not None]
    return sum(given, Decimal(0)) if given else None


def _fee(row: Cells, kind: str, mapping: Mapping, warnings: list[CSVParseError]) -> Decimal | None:
    """A buy's or a sell's fee in dollars, a send's in bitcoin. A fee the
    file gives only in the other currency isn't read, and the warning says
    so: a dollar fee read as bitcoin would be a fortune."""
    wanted = "USD" if kind in (BUY, SELL) else "BTC"
    fee, currency = _given_fee(row, wanted, mapping)
    if not fee:
        return None
    fee = abs(fee)
    if currency != wanted:
        cents = currency == "USD" and fee == to_cents(fee)
        shown = f"${fee:,.2f}" if cents else f"{fee.normalize():f} {currency}"
        warnings.append(CSVParseError(
            row_number=row.number, column=None, severity="warning",
            message=(f"This {kind}'s fee is {shown}: BitcoinTX records a {kind}'s fee in {wanted}, so it isn't "
                     f"read. Add it in {wanted} if it belongs in the figures.")))
        return None
    return to_cents(fee) if wanted == "USD" else to_sats(fee, row.number, None, warnings)


def _given_fee(row: Cells, wanted: str, mapping: Mapping) -> tuple[Decimal | None, str | None]:
    """The fee the row gives, and its currency: from the wanted currency's
    own column, else the fee column, in dollars unless its currency column
    says bitcoin (a fee is never taken for bitcoin without the file saying
    so), else the other currency's column."""
    columns = mapping.columns
    own, other = (columns.fee_usd, columns.fee_btc) if wanted == "USD" else (columns.fee_btc, columns.fee_usd)
    if (fee := _signed(row, own, mapping)) is not None:
        return fee, wanted
    if (fee := _signed(row, columns.fee, mapping)) is not None:
        said = row.get(columns.fee_currency).upper() if columns.fee_currency else ""
        return fee, {"XBT": "BTC", "XXBT": "BTC", "$": "USD"}.get(said, said) or "USD"
    return _signed(row, other, mapping), "BTC" if wanted == "USD" else "USD"


# The column matcher: what a file holds, before any mapping

@dataclass
class FileColumns:
    header_row: int
    columns: list[str]
    samples: list[list[str]]
    values: dict[str, list[str]]
    looks_like: str | None


def file_columns(content: bytes) -> FileColumns | CSVParseError:
    """A file's header (the first of its first rows as wide as most of its
    rows), its first rows, the words in each column, for the owner to match;
    and the ready-made mapping whose columns it has, if one does."""
    rows = records(content)
    if isinstance(rows, CSVParseError):
        return rows
    widths = [len([c for c in cells if c.strip()]) for _number, cells in rows]
    usual = max(set(widths), key=widths.count) if widths else 0
    if usual < 2:
        return CSVParseError(row_number=0, column=None, severity="error", message=NO_ROWS)
    at = next(i for i, width in enumerate(widths) if width >= usual)
    header = Header(*rows[at])
    data = [cells for _number, cells in rows[at + 1:]]
    values = {name: list(dict.fromkeys(c[place].strip() for c in data if place < len(c) and c[place].strip()))[:MAX_VALUES]
              for place, name in enumerate(header.names) if name}
    return FileColumns(header.number, header.names, [c[:len(header.names)] for c in data[:SAMPLES]], values,
                       looks_like(rows))


def looks_like(rows) -> str | None:
    """The ready-made mapping whose columns the file has, if one does."""
    for mapping in READY_MADE.values():
        if not isinstance(find_header(rows[:HEADER_SEARCH], _signature(mapping), mapping.name), CSVParseError):
            return mapping.id
    return None


def _signature(mapping: Mapping) -> dict[str, tuple[str, ...]]:
    """The columns that tell a mapping's file from another's."""
    if mapping.reader == RIVER_FILE:
        return {name: (name,) for name in RIVER_REQUIRED_COLUMNS}
    if mapping.reader == KRAKEN_LEDGER:
        return KRAKEN_COLUMNS
    return _needed(mapping)
