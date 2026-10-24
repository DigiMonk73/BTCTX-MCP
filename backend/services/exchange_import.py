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
    HEADER_AGAIN,
    another_header,
    HEADER_SEARCH,
    Cells,
    FileRead,
    Header,
    LeftOut,
    RowError,
    find_header,
    read_amount,
    read_moment,
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
        if header.other_than(cells, _needed(mapping)):
            read.errors.append(another_header(number))
            break
        if header.repeated_by(cells):
            left_out.add(HEADER_AGAIN, number)
        elif any(c.strip() for c in cells[len(header.names):]):
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
    """A row whose id an earlier row has is left out (decision 8): with every
    cell the same, the same row twice (overlapping exports joined); else the
    file holds two rows for one record, and only the first is read. With
    `merge_same_id`, only the first: rows sharing an id are one event's
    pieces (Strike's)."""
    names = mapping.columns.row_id
    if not rows or rows[0].header.place(names) is None:
        return rows
    column = rows[0].header.name(names)
    seen_rows, seen_ids, kept = set(), set(), []
    for row in rows:
        row_id = row.get(names)
        cells = (row_id, tuple(c.strip() for c in row.cells))
        if row_id and cells in seen_rows:
            left_out.add(f"repeat an earlier row ({column} and every cell the same)", row.number)
        elif row_id and row_id in seen_ids and not mapping.merge_same_id:
            left_out.add(f"have the id of an earlier row ({column}) with other cells: only the first is read, "
                         "so check the file", row.number)
        else:
            seen_rows.add(cells)
            seen_ids.add(row_id)
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
        elif _adds_up_to_nothing(group, mapping) is True:
            for row in group:
                left_out.add("were reversed or cancelled (their pieces add up to nothing)", row.number)
        else:
            face = next((row for row in group if row.get(mapping.columns.btc)), group[0])
            kept.append(Cells(face.number, face.header, face.cells, pieces=group))
    return sorted(kept, key=lambda row: row.number)


def _adds_up_to_nothing(group: list[Cells], mapping: Mapping) -> bool | None:
    """Whether the pieces' bitcoin and dollars add up to nothing; None when a
    piece can't be read (the merged row's reading says why)."""
    merged = Cells(group[0].number, group[0].header, group[0].cells, pieces=group)
    columns = mapping.columns
    try:
        return all(not _number(merged, names, mapping, unit)[0]
                   for names, unit in ((columns.btc, "BTC"), (columns.usd, "USD")) if names)
    except RowError:
        return None


def _kind_if_read(row: Cells, mapping: Mapping, left_out: LeftOut) -> str | None:
    """The row's kind when the mapping reads it as an event: bitcoin,
    completed, not left out by one of its rules, of a kind it reads, with
    bitcoin moving the kind's way. Else None, the row left out with its
    reason."""
    word = kind_word(row, mapping)
    reason = _left_out_whatever_its_kind(row, mapping, word)
    kind = None if reason is not None else _kind(row, mapping, left_out)
    if kind is not None:
        reason = _not_as_its_kind(row, kind, mapping, word)
    if reason is not None:
        left_out.add(reason, row.number)
        return None
    return kind


def _left_out_whatever_its_kind(row: Cells, mapping: Mapping, word: str) -> str | None:
    """Why the row isn't read, whatever its kind: a trade of bitcoin for
    another coin, another asset, a row not completed, or one of the
    mapping's own rules; else None."""
    columns = mapping.columns
    asset = row.get(columns.asset)
    if mapping.kinds.get(word.lower()) == CONVERT and _mentions_bitcoin(row, mapping):
        return _convert(word)
    if row.header.place(columns.asset) is not None and asset.lower() not in mapping.btc_assets:
        return _not_bitcoin(asset, word)
    status = _unfinished(row, mapping)
    if status is not None:
        return f"are {status}, not completed"
    return next((rule.reason for rule in mapping.leave_out
                 if row.header.place((rule.column,)) is not None and rule.applies(row.get((rule.column,)))), None)


def _not_as_its_kind(row: Cells, kind: str, mapping: Mapping, word: str) -> str | None:
    """Why a row of a kind that's read isn't, after all: a move of dollars
    alone, or money going the other way than its kind's; else None."""
    columns = mapping.columns
    if kind in (SEND, RECEIVE, *PAYOUT_SOURCES) and not row.get(columns.btc) and row.get(columns.usd):
        return f"move dollars, not bitcoin (“{word}”)"
    if _against_kind(row, kind, mapping):
        return (f"go the other way than “{word}” does (a reversal or a refund?): add any that moved bitcoin "
                "by hand")
    return None


# Which way each kind's money goes, bitcoin's and dollars': + into the exchange
_WAYS = {BUY: (1, -1), SELL: (-1, 1), SEND: (-1, None), RECEIVE: (1, None), **{k: (1, None) for k in PAYOUT_SOURCES}}


def _against_kind(row: Cells, kind: str, mapping: Mapping) -> bool:
    """Whether a column whose sign follows the money (`mapping.signs`) has
    it going the other way than the kind's: a reversal written as a buy is
    never read as a second buy. Coins coming in (a buy, a receive, a
    payout) are never negative, whatever a file's signs mean. A cell that
    can't be read isn't judged here: the row's reading says what's wrong."""
    for role, unit, way in (("btc", "BTC", _WAYS[kind][0]), ("usd", "USD", _WAYS[kind][1])):
        if way is None or (role not in mapping.signs and not (role == "btc" and way > 0)):
            continue
        try:
            value = _number(row, getattr(mapping.columns, role), mapping, unit)[0]
        except RowError:
            return False
        if value and (value > 0) != (way > 0) and (role in mapping.signs or value < 0):
            return True
    return False


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
    btc = _number(row, columns.btc, mapping, "BTC")[0]
    btc = to_sats(abs(btc), row.number, row.header.name(columns.btc), warnings) if btc is not None else None
    usd = _number(row, columns.usd, mapping, "USD")[0]
    usd = to_cents(abs(usd), row.header.name(columns.usd)) if usd is not None else None
    fee = _fee(row, kind, mapping, warnings) if kind in (BUY, SELL, SEND) else None
    if kind in mapping.after_fee and usd is not None and fee is not None:
        usd = usd - fee if kind == BUY else usd + fee
    if kind == SEND and mapping.send_fee_included and btc is not None and fee is not None:
        btc -= fee
    if kind in PAYOUT_SOURCES and not usd:
        usd = None  # no value given: the hour's price fills it
    currency = None if fee is None else "USD" if kind in (BUY, SELL) else "BTC"
    return FileRow(row.number, moment, kind, btc, usd, fee, currency, kind_word(row, mapping) or None)


def _number(row: Cells, names: tuple[str, ...], mapping: Mapping, unit: str | None) -> tuple[Decimal | None, str | None]:
    """A number column's value with its sign, summed over a merged row's
    pieces, and the currency its cells write. A bitcoin column (`unit`
    BTC) takes no thousands separator; a cell writing another currency than
    `unit` is a RowError: "$5.00" is never read as 5 BTC."""
    if not names or row.header.place(names) is None:
        return None, None
    column = row.header.name(names)
    values, units = [], set()
    for piece in row.pieces:
        value, said = read_amount(piece.get(names), mapping.decimal_comma, column, bitcoin=unit == "BTC")
        values += [value] if value is not None else []
        units |= {said} if said else set()
    if (unit and units - {unit}) or len(units) > 1:
        shown = "bitcoin" if unit == "BTC" else "dollars" if unit == "USD" else "in one currency"
        raise RowError(f"{column} '{row.get(names)}' isn't {shown}.", column)
    return (sum(values, Decimal(0)) if values else None), next(iter(units), None)


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
    return to_cents(fee, "Fee") if wanted == "USD" else to_sats(fee, row.number, None, warnings)


def _given_fee(row: Cells, wanted: str, mapping: Mapping) -> tuple[Decimal | None, str | None]:
    """The fee the row gives, and its currency: from the wanted currency's
    own column, else the fee column, in the currency its cell or its
    currency column writes, dollars when neither says (a fee is never taken
    for bitcoin without the file saying so), else the other currency's
    column."""
    columns = mapping.columns
    other = "BTC" if wanted == "USD" else "USD"
    own_column, other_column = (columns.fee_usd, columns.fee_btc) if wanted == "USD" else (columns.fee_btc, columns.fee_usd)
    if (fee := _number(row, own_column, mapping, wanted)[0]) is not None:
        return fee, wanted
    fee, written = _number(row, columns.fee, mapping, None)
    if fee is not None:
        named = row.get(columns.fee_currency).upper() if columns.fee_currency else ""
        named = {"XBT": "BTC", "XXBT": "BTC", "$": "USD"}.get(named, named)
        if written and named and written != named:
            raise RowError(f"{row.header.name(columns.fee)} '{row.get(columns.fee)}' isn't {named}.",
                           row.header.name(columns.fee))
        currency = written or named or "USD"
        return (_number(row, columns.fee, mapping, "BTC")[0] if currency == "BTC" else fee), currency
    return _number(row, other_column, mapping, other)[0], other


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
    data = [cells for _number, cells in rows[at + 1:] if not header.repeated_by(cells)]
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
