"""
Kraken's ledger file (ledgers.csv, B5b): one line for each asset an event
moves, the lines of one event sharing a reference (refid). Kraken's rule is
balance = previous balance + amount - fee, each line in its own asset, so a
trade is a bitcoin line and a dollar line, either carrying the fee (a fee
Kraken's fee credits paid is a third line of its own, in KFEE); a
withdrawal's amount is what was sent, its fee on top. Its trades file isn't
read: it lacks deposits, withdrawals and rewards. Times are UTC.
"""

from __future__ import annotations

from decimal import Decimal

from backend.schemas.csv_import import CSVParseError
from backend.services.exchange_cells import (
    HEADER_AGAIN,
    another_header,
    Cells,
    FileRead,
    LeftOut,
    Reason,
    Records,
    RowError,
    find_header,
    read_moment,
    read_number,
    rows_said,
    to_cents,
    to_sats,
)
from backend.services.river_import import BUY, RECEIVE, SELL, SEND, FileRow

# The columns read, by Kraken's names; the export lets the others be left out
KRAKEN_COLUMNS = {role: (role,) for role in ("txid", "refid", "time", "type", "asset", "amount", "fee")}
SUBTYPE = ("subtype",)

# Kraken's asset codes, its reward balances' suffixes (.M, .S, .F, .B…) aside
BITCOIN, DOLLARS = frozenset({"XXBT", "XBT", "BTC"}), frozenset({"ZUSD", "USD"})
# Kraken's fee credits, which pay a trade's fee from a promotion, never the owner's dollars (#829)
FEE_CREDITS = "KFEE"
TRADES = frozenset({"trade", "spend", "receive"})
# Moves between Kraken's own balances (spot, staking, earn): never in or out of the exchange
WITHIN = frozenset({"transfer", "allocation", "deallocation", "autoallocation", "autoallocate", "migration"})

PENDING = Reason("are Kraken's pending copies of a deposit or withdrawal (no txid), whose completed row is read",
                 "is Kraken's pending copy of a deposit or withdrawal (no txid), whose completed row is read")
REPEATED = Reason("repeat an earlier line (txid)", "repeats an earlier line (txid)")
WITHIN_KRAKEN = Reason("move coins between Kraken's own balances (spot, staking, earn)",
                       "moves coins between Kraken's own balances (spot, staking, earn)")
DOLLARS_ONLY = Reason("move dollars, not bitcoin", "moves dollars, not bitcoin")


def read_ledger(rows: Records, name: str = "Kraken") -> FileRead:
    """The ledger's events, its lines grouped by refid."""
    header = find_header(rows, KRAKEN_COLUMNS, name)
    if isinstance(header, CSVParseError):
        return FileRead(errors=[header])
    data = [Cells(number, header, cells) for number, cells in rows if number > header.number]
    read, left_out = FileRead(total_rows=len(data)), LeftOut()
    data = _under_the_header(data, header, read, left_out)
    paid_in_credits = []
    for lines in _events(data, left_out).values():
        try:
            event = _event(lines, left_out, read.warnings)
        except RowError as exc:
            read.errors.append(exc.problem(lines[0].number))
            continue
        if event is not None:
            read.rows.append(event)
            if any(_fee_credits(line) for line in lines):
                paid_in_credits.append(event.row_number)
    read.rows.sort(key=lambda r: r.row_number)
    read.warnings.extend(left_out.warnings())
    if paid_in_credits:
        read.warnings.append(_paid_in_credits(sorted(paid_in_credits)))
    return read


def _fee_credits(line: Cells) -> bool:
    """Whether the line is a fee Kraken's fee credits paid: KFEE, moving
    nothing (its fee is the credits used)."""
    return (line.get(("asset",)).upper() == FEE_CREDITS
            and not read_number(line.get(("amount",)), column="amount"))


def _paid_in_credits(numbers: list[int]) -> CSVParseError:
    """The note naming the trades Kraken's fee credits paid a fee of (all of
    it, or what the dollars didn't): no dollars of the owner's, so only a
    fee in dollars is counted, and a buy's cost is the dollars paid."""
    return CSVParseError(row_number=0, column=None, severity="warning",
                         message=f"{rows_said(numbers)} paid a fee with Kraken fee credits (KFEE): they aren't "
                                 "dollars, so only a fee paid in dollars is counted.")


def _under_the_header(lines: list[Cells], header, read, left_out: LeftOut) -> list[Cells]:
    """The lines the header names: a header again is left out (files
    joined); at a header of other columns (a file exported with columns
    left out, joined to this one), the reading stops, with its error."""
    kept = []
    for line in lines:
        if header.other_than(line.cells, KRAKEN_COLUMNS):
            read.errors.append(another_header(line.number))
            break
        if header.repeated_by(line.cells):
            left_out.add(HEADER_AGAIN, line.number)
        else:
            kept.append(line)
    return kept


def _events(lines: list[Cells], left_out: LeftOut) -> dict[str, list[Cells]]:
    """The lines by event (refid), in the file's order; a pending copy left
    out, and a line whose txid an earlier line has (overlapping exports
    joined: summed, it would double the event)."""
    events: dict[str, list[Cells]] = {}
    seen: set[str] = set()
    for line in lines:
        txid = line.get(KRAKEN_COLUMNS["txid"])
        if not txid:
            left_out.add(PENDING, line.number)
        elif txid in seen:
            left_out.add(REPEATED, line.number)
        else:
            seen.add(txid)
            events.setdefault(line.get(KRAKEN_COLUMNS["refid"]) or f"line {line.number}", []).append(line)
    return events


class _Lines:
    """An event's lines summed by asset: bitcoin's and dollars' amounts and
    fees, and any other asset's name."""

    def __init__(self, lines: list[Cells]):
        self.btc = self.btc_fee = self.usd = self.usd_fee = Decimal(0)
        self.has_btc = self.has_usd = False
        self.others: list[str] = []
        for line in lines:
            if _fee_credits(line):
                continue  # no asset the trade moved: its dollar line says what it cost
            asset = line.get(("asset",)).upper().split(".")[0]
            if asset not in BITCOIN | DOLLARS:
                self.others.append(line.get(("asset",)) or "no asset")  # left out, its numbers never read
                continue
            unit = "BTC" if asset in BITCOIN else "USD"
            amount = read_number(line.get(("amount",)), column="amount", unit=unit) or Decimal(0)
            fee = read_number(line.get(("fee",)), column="fee", unit=unit) or Decimal(0)
            if unit == "BTC":
                self.btc, self.btc_fee, self.has_btc = self.btc + amount, self.btc_fee + fee, True
            else:
                self.usd, self.usd_fee, self.has_usd = self.usd + amount, self.usd_fee + fee, True


def _event(lines: list[Cells], left_out: LeftOut, warnings: list[CSVParseError]) -> FileRow | None:
    """An event's lines as a buy, a sell, a send, a receive or a reward;
    None, the lines left out by reason, for anything else."""
    kinds = {line.get(("type",)).lower() for line in lines}
    subtypes = {line.get(SUBTYPE).lower() for line in lines}
    summed = _Lines(lines)
    first = next((line for line in lines if line.get(("asset",)).upper().split(".")[0] in BITCOIN), lines[0])
    numbers = [line.number for line in lines]
    if kinds <= WITHIN or (kinds == {"earn"} and subtypes <= WITHIN):
        return _left(left_out, numbers, WITHIN_KRAKEN)
    if summed.others:
        others = ", ".join(sorted(set(summed.others)))
        how = ("by hand (bitcoin given up as a Withdrawal, purpose Spent, at its dollar value: a disposal, IRS "
               "Notice 2014-21)")
        if summed.has_btc:
            return _left(left_out, numbers, Reason(f"trade bitcoin for {others}: add each {how}",
                                                   f"trades bitcoin for {others}: add it {how}"))
        return _left(left_out, numbers, Reason(f"are {others}, not bitcoin (BitcoinTX tracks bitcoin only)",
                                               f"is {others}, not bitcoin (BitcoinTX tracks bitcoin only)"))
    if not summed.has_btc:
        return _left(left_out, numbers, DOLLARS_ONLY)
    moment = read_moment(first.get(("time",)), "UTC", column="time")
    if kinds <= TRADES:
        return _trade(first, numbers, moment, summed, kinds, left_out, warnings)
    return _move(first, numbers, moment, summed, kinds, subtypes, left_out, warnings)


def _left(left_out: LeftOut, numbers: list[int], reason: Reason) -> None:
    """Each of the event's lines left out for `reason`; None, the event's place."""
    for number in numbers:
        left_out.add(reason, number)
    return None


def _trade(first: Cells, numbers: list[int], moment, summed: _Lines, kinds: set, left_out: LeftOut,
           warnings: list[CSVParseError]) -> FileRow | None:
    """A trade (or Buy Crypto's spend and receive): bitcoin in for dollars
    out is a buy, its cost the dollars before the fee; the other way a sell,
    its proceeds the dollars before the fee. A fee taken in bitcoin is in
    the coins: a buy's are those that arrived, a sell's all that left."""
    if not summed.has_usd:
        return _left(left_out, numbers, Reason("are a trade with no dollar side", "is a trade with no dollar side"))
    coins = summed.btc - summed.btc_fee
    tag = "/".join(sorted(kinds))
    fee = to_cents(summed.usd_fee, "fee") if summed.usd_fee else None
    if coins > 0 and summed.usd < 0:
        return FileRow(first.number, moment, BUY, to_sats(coins, first.number, "amount", warnings),
                       to_cents(-summed.usd, "amount"), fee, "USD" if fee else None, tag)
    if coins < 0 and summed.usd > 0:
        return FileRow(first.number, moment, SELL, to_sats(-coins, first.number, "amount", warnings),
                       to_cents(summed.usd, "amount"), fee, "USD" if fee else None, tag)
    return _left(left_out, numbers, Reason("are a trade whose bitcoin and dollars don't go opposite ways",
                                           "is a trade whose bitcoin and dollars don't go opposite ways"))


def _move(first: Cells, numbers: list[int], moment, summed: _Lines, kinds: set, subtypes: set, left_out: LeftOut,
          warnings: list[CSVParseError]) -> FileRow | None:
    """Bitcoin in or out: a withdrawal is a send (its fee on top), a deposit
    a receive (what was credited), a staking or earn reward a reward."""
    credited = summed.btc - summed.btc_fee
    if kinds == {"withdrawal"}:
        if summed.btc >= 0:
            return _left(left_out, numbers, Reason("are a withdrawal Kraken sent back (they add up to nothing)",
                                                   "is a withdrawal Kraken sent back (it adds up to nothing)"))
        fee = to_sats(summed.btc_fee, first.number, "fee", warnings) if summed.btc_fee else None
        return FileRow(first.number, moment, SEND, to_sats(-summed.btc, first.number, "amount", warnings),
                       None, fee, "BTC" if fee else None, "withdrawal")
    if kinds == {"deposit"} and credited > 0:
        return FileRow(first.number, moment, RECEIVE, to_sats(credited, first.number, "amount", warnings),
                       tag="deposit")
    if (kinds == {"staking"} or (kinds == {"earn"} and subtypes == {"reward"})) and credited > 0:
        return FileRow(first.number, moment, "reward", to_sats(credited, first.number, "amount", warnings),
                       tag="/".join(sorted(kinds)))
    said = ", ".join(sorted(f"{k} ({s})" if s else k for k in kinds for s in subtypes))
    return _left(left_out, numbers, Reason(f"are Kraken's “{said}” rows, which BitcoinTX doesn't read (add any "
                                           "that moved bitcoin in or out by hand)",
                                           f"is a Kraken “{said}” row, which BitcoinTX doesn't read (add it by "
                                           "hand if it moved bitcoin in or out)"))
