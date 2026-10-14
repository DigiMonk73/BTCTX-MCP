"""
Adapter + dedup engine for importing River bitcoin-activity CSV exports
into a live ledger. See docs/archive/RIVER_IMPORT_PLAN.md for the full design.

River CSV columns:
    Date, Sent Amount, Sent Currency, Received Amount, Received Currency,
    Fee Amount, Fee Currency, Tag
Dates are "YYYY-MM-DD HH:MM:SS" in UTC. Tag is one of Buy, Sell, Income,
Interest, Withdrawal, or empty (on-chain sends/receives).

Account model (deliberate simplification, see plan doc):
    Exchange USD / Exchange BTC = River; Bank = outside bank; Wallet = cold
    storage; External = everything else.
"""

from __future__ import annotations

import csv
import io
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from backend.constants import (
    ACCOUNT_BANK,
    ACCOUNT_EXCHANGE_BTC,
    ACCOUNT_EXCHANGE_USD,
    ACCOUNT_EXTERNAL,
    ACCOUNT_ID_TO_NAME,
    ACCOUNT_WALLET,
)
from backend.models.transaction import Transaction
from backend.schemas.csv_import import CSVParseError
from backend.schemas.transaction import BTC_PLACES
from backend.services.calculation import btc_text
from backend.services.csv_import import _parse_decimal, number_limits
from backend.services.tax_time import get_tax_timezone, local_date

logger = logging.getLogger(__name__)

RIVER_REQUIRED_COLUMNS = {
    "date", "sent amount", "sent currency", "received amount",
    "received currency", "fee amount", "fee currency", "tag",
}

RIVER_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# The amounts, as River's header names them
RIVER_NUMBER_COLUMNS = ("Sent Amount", "Received Amount", "Fee Amount")

# A buy outlay (sent + USD fee) that repeats at least this many times with no
# fee is treated as a recurring auto-buy pulled from the bank via ACH.
RECURRING_BUY_THRESHOLD = 4

# Dedup: a row within this of a transaction of the same amount is shown as similar (#253)
SIMILAR_WINDOW = timedelta(hours=48)
FUZZY_AMOUNT_TOLERANCE = Decimal("0.20")  # ±20% for transfer near-matches

STATUS_NEW = "new"
STATUS_MATCHED = "matched"
STATUS_DISCREPANCY = "discrepancy"


@dataclass
class RiverRow:
    """One parsed row of the River bitcoin-activity CSV."""
    row_number: int
    timestamp: datetime
    sent: Decimal | None
    sent_currency: str | None
    received: Decimal | None
    received_currency: str | None
    fee: Decimal | None
    fee_currency: str | None
    tag: str | None


@dataclass
class RiverProposal:
    """A proposed BitcoinTX transaction adapted from a River row."""
    row_number: int
    timestamp: datetime
    river_tag: str | None
    type: str
    from_account_id: int
    to_account_id: int
    amount: Decimal
    cost_basis_usd: Decimal | None = None
    proceeds_usd: Decimal | None = None
    fee_amount: Decimal | None = None
    fee_currency: str | None = None
    source: str | None = None
    purpose: str | None = None
    # Preview metadata
    type_choices: list[str] = field(default_factory=list)
    funding_choices: list[str] = field(default_factory=list)
    basis_autofilled: bool = False
    price_moment: str | None = None  # the autofilled basis's price: "hour" or "day"
    status: str = STATUS_NEW
    matched_tx_id: int | None = None
    discrepancy: str | None = None
    # A row given as a date alone (the AI connector's): its day in the tax
    # timezone, which the duplicate check matches instead of the minute
    day: date | None = None

    @property
    def from_account(self) -> str:
        return ACCOUNT_ID_TO_NAME[self.from_account_id]

    @property
    def to_account(self) -> str:
        return ACCOUNT_ID_TO_NAME[self.to_account_id]

    def to_tx_data(self) -> dict[str, Any]:
        """Build the dict create_transaction_record() expects."""
        tx_data: dict[str, Any] = {
            "type": self.type,
            "timestamp": self.timestamp,
            "amount": self.amount,
            "from_account_id": self.from_account_id,
            "to_account_id": self.to_account_id,
        }
        if self.cost_basis_usd is not None:
            tx_data["cost_basis_usd"] = self.cost_basis_usd
        if self.proceeds_usd is not None:
            tx_data["proceeds_usd"] = self.proceeds_usd
        if self.fee_amount is not None and self.fee_amount > 0:
            tx_data["fee_amount"] = self.fee_amount
            tx_data["fee_currency"] = self.fee_currency or (
                "USD" if self.type in ("Buy", "Sell") else "BTC"
            )
        if self.source:
            tx_data["source"] = self.source
        if self.purpose:
            tx_data["purpose"] = self.purpose
        return tx_data


def parse_river_csv(content: bytes) -> tuple[list[RiverRow], list[CSVParseError]]:
    """Parse raw River bitcoin-activity CSV bytes into RiverRow objects."""
    errors: list[CSVParseError] = []
    rows: list[RiverRow] = []

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except UnicodeDecodeError:
            errors.append(CSVParseError(
                row_number=0, column=None, severity="error",
                message="File encoding not supported. Please save as UTF-8.",
            ))
            return rows, errors

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        errors.append(CSVParseError(
            row_number=0, column=None, severity="error",
            message="CSV file is empty or has no headers.",
        ))
        return rows, errors

    headers = {h.lower().strip() for h in reader.fieldnames if h}
    missing = RIVER_REQUIRED_COLUMNS - headers
    if missing:
        errors.append(CSVParseError(
            row_number=0, column=None, severity="error",
            message=(
                "This does not look like a River bitcoin-activity CSV. "
                f"Missing columns: {', '.join(sorted(missing))}"
            ),
        ))
        return rows, errors

    for row_number, raw in enumerate(reader, start=2):
        if None in raw:
            # More fields than the header (the reader lists the extras under
            # None): the columns no longer line up, so the row can't be read.
            errors.append(CSVParseError(
                row_number=row_number, column=None, severity="error",
                message=(
                    "This row has more fields than the header: a stray comma, or an amount "
                    "written with a comma (write 1000.00, not 1,000.00)?"
                ),
            ))
            continue
        r = {(k or "").lower().strip(): (v or "").strip() for k, v in raw.items()}

        date_str = r.get("date", "")
        try:
            # River exports timestamps in UTC
            ts = datetime.strptime(date_str, RIVER_DATE_FORMAT).replace(tzinfo=timezone.utc)
        except ValueError:
            errors.append(CSVParseError(
                row_number=row_number, column="date", severity="error",
                message=f"Invalid date '{date_str}'. Expected YYYY-MM-DD HH:MM:SS.",
            ))
            continue

        numbers = _river_numbers(r, row_number, errors)
        if numbers is None:
            continue
        sent, received, fee = numbers

        sent_cur = r.get("sent currency", "").upper() or None
        recv_cur = r.get("received currency", "").upper() or None
        fee_cur = r.get("fee currency", "").upper() or None

        rows.append(RiverRow(
            row_number=row_number,
            timestamp=ts,
            sent=sent,
            sent_currency=sent_cur,
            received=received,
            received_currency=recv_cur,
            fee=fee,
            fee_currency=fee_cur,
            tag=r.get("tag", "").title() or None,
        ))

    if not rows and not errors:
        errors.append(CSVParseError(
            row_number=0, column=None, severity="error",
            message="No data rows found in file.",
        ))

    return rows, errors


def _river_numbers(r: dict[str, str], row_number: int,
                   errors: list[CSVParseError]) -> tuple[Decimal | None, ...] | None:
    """
    The row's sent, received and fee amounts (None when blank), or None with
    the row's error when one isn't a number within a BTC column's rule (the
    USD ones too: the import checks their cents when it saves them). Read as
    blank, such a fee would be left out and such an amount would skip its row
    as missing.
    """
    numbers = []
    for column in RIVER_NUMBER_COLUMNS:
        text = r.get(column.lower(), "")
        value = _parse_decimal(text, BTC_PLACES)
        if text and value is None:
            errors.append(CSVParseError(
                row_number=row_number, column=column, severity="error",
                message=f"{column} '{text}' isn't a number with at most {number_limits(BTC_PLACES)}.",
            ))
            return None
        numbers.append(value)
    return tuple(numbers)


def _usd_fee(row: RiverRow) -> Decimal:
    """River's USD fee on a Buy or Sell. River charges those in USD, and the
    proposal records the fee as USD even when Fee Currency is blank, so a
    blank one counts as USD here too (else a Sell's gross would leave out a
    fee the ledger still subtracts)."""
    if row.fee is not None and row.fee_currency in ("USD", None):
        return row.fee
    return Decimal("0")


def _buy_outlay(row: RiverRow) -> Decimal:
    """Total USD that left for a buy: sent + USD fee."""
    return (row.sent or Decimal("0")) + _usd_fee(row)


def _recurring_outlays(rows: list[RiverRow]) -> dict[Decimal, int]:
    """Count identical buy outlays across the file (the heuristic's signal)."""
    counts: dict[Decimal, int] = {}
    for row in rows:
        if row.tag == "Buy":
            outlay = _buy_outlay(row)
            counts[outlay] = counts.get(outlay, 0) + 1
    return counts


def adapt_river_rows(
    rows: list[RiverRow],
) -> tuple[list[RiverProposal], list[CSVParseError], list[CSVParseError]]:
    """
    (proposals, errors, warnings): each River row as a proposed BitcoinTX
    transaction. A row that fits no known pattern, or lacks an amount, is
    skipped with a warning (never silently dropped).
    """
    adapter = _RiverAdapter(rows)
    proposals = [p for p in map(adapter.adapt, rows) if p is not None]
    return proposals, [], adapter.warnings


class _RiverAdapter:
    """Turns River rows into proposals, collecting the warnings."""

    def __init__(self, rows: list[RiverRow]):
        self.outlay_counts = _recurring_outlays(rows)
        self.warnings: list[CSVParseError] = []

    def adapt(self, row: RiverRow) -> RiverProposal | None:
        tag = row.tag
        if tag == "Buy" and row.sent_currency == "USD" and row.received_currency == "BTC":
            return self.buy(row)
        if tag == "Sell" and row.sent_currency == "BTC" and row.received_currency == "USD":
            return self.sell(row)
        if tag in ("Interest", "Income") and row.received_currency == "BTC" and row.received:
            return self.income(row)
        if row.sent_currency == "BTC" and row.received is None:
            return self.send(row)
        if row.received_currency == "BTC" and row.sent is None and tag is None:
            return self.receive(row)
        self.warn(row, (
            f"Unrecognized row pattern (tag={tag or 'none'}, "
            f"sent={row.sent_currency or '-'}, received={row.received_currency or '-'}) — skipped."
        ))
        return None

    def warn(self, row: RiverRow, message: str, column: str | None = None) -> None:
        self.warnings.append(CSVParseError(
            row_number=row.row_number, column=column, severity="warning", message=message,
        ))

    def check_fee_currency(self, row: RiverRow, expected: str) -> None:
        """River's Fee Currency is taken as `expected` for this kind of row;
        say so when the file says otherwise instead of ignoring it."""
        if row.fee and row.fee_currency and row.fee_currency != expected:
            self.warn(row, (
                f"Fee Currency is {row.fee_currency}, but a fee on this kind of row is in {expected}; "
                f"it was read as {row.fee} {expected}. Check the fee before importing."
            ), column="Fee Currency")

    def buy(self, row: RiverRow) -> RiverProposal | None:
        if not row.received or row.received <= 0 or not row.sent or row.sent <= 0:
            self.warn(row, "Buy row missing sent/received amount — skipped.")
            return None
        self.check_fee_currency(row, "USD")
        # Funding heuristic: a recurring no-fee outlay is an auto-buy pulled
        # from the bank via ACH; anything else defaults to the River cash
        # balance. Always user-overridable in the preview.
        recurring = self.outlay_counts.get(_buy_outlay(row), 0) >= RECURRING_BUY_THRESHOLD
        return RiverProposal(
            row_number=row.row_number, timestamp=row.timestamp, river_tag=row.tag,
            type="Buy", from_account_id=ACCOUNT_BANK if (recurring and not row.fee) else ACCOUNT_EXCHANGE_USD,
            to_account_id=ACCOUNT_EXCHANGE_BTC,
            amount=row.received,
            cost_basis_usd=row.sent,
            fee_amount=row.fee, fee_currency="USD" if row.fee else None,
            funding_choices=["Bank", "Exchange USD"],
        )

    def sell(self, row: RiverRow) -> RiverProposal | None:
        if not row.sent or row.sent <= 0 or not row.received or row.received <= 0:
            self.warn(row, "Sell row missing sent/received amount — skipped.")
            return None
        self.check_fee_currency(row, "USD")
        # River's Received Amount is what landed after River's fee (receipt:
        # subtotal - fee = received). BitcoinTX's proceeds_usd is the gross
        # before fees, and the ledger subtracts the USD fee from it, so the
        # gross is received + fee.
        return RiverProposal(
            row_number=row.row_number, timestamp=row.timestamp, river_tag=row.tag,
            type="Sell", from_account_id=ACCOUNT_EXCHANGE_BTC,
            to_account_id=ACCOUNT_EXCHANGE_USD,
            amount=row.sent,
            proceeds_usd=row.received + _usd_fee(row),
            fee_amount=row.fee, fee_currency="USD" if row.fee else None,
        )

    def income(self, row: RiverRow) -> RiverProposal:
        # BTC paid by River (interest on the cash balance too, which River
        # pays in BTC). Its basis, the value at receipt, is filled from the
        # hour's price by the router; editable.
        return RiverProposal(
            row_number=row.row_number, timestamp=row.timestamp, river_tag=row.tag,
            type="Deposit", from_account_id=ACCOUNT_EXTERNAL,
            to_account_id=ACCOUNT_EXCHANGE_BTC,
            amount=row.received,
            source=row.tag,
        )

    def send(self, row: RiverRow) -> RiverProposal | None:
        """
        BTC left River. Untagged, it's almost always a move to cold storage;
        Tag=Withdrawal means the user told River it left their hands. The
        user can flip either in the preview. River's Sent Amount is what the
        destination receives, the network fee on top; the proposal keeps
        River's numbers, and ledger_amount() gives a Transfer's BitcoinTX
        amount (fee included) for dedup and at execute.
        """
        if not row.sent or row.sent <= 0:
            self.warn(row, "BTC send row missing amount — skipped.")
            return None
        self.check_fee_currency(row, "BTC")
        fee = {"fee_amount": row.fee, "fee_currency": "BTC" if row.fee else None}
        if row.tag == "Withdrawal":
            return RiverProposal(
                row_number=row.row_number, timestamp=row.timestamp, river_tag=row.tag,
                type="Withdrawal", from_account_id=ACCOUNT_EXCHANGE_BTC,
                to_account_id=ACCOUNT_EXTERNAL,
                amount=row.sent, **fee,
                purpose="Spent",
                type_choices=["Withdrawal", "Transfer"],
            )
        return RiverProposal(
            row_number=row.row_number, timestamp=row.timestamp, river_tag=row.tag,
            type="Transfer", from_account_id=ACCOUNT_EXCHANGE_BTC,
            to_account_id=ACCOUNT_WALLET,
            amount=row.sent, **fee,
            type_choices=["Transfer", "Withdrawal"],
        )

    def receive(self, row: RiverRow) -> RiverProposal | None:
        """Untagged BTC arriving at River: by default back from cold storage,
        with no fee (River can't see the wallet's network fee; editable)."""
        if not row.received or row.received <= 0:
            self.warn(row, "BTC receive row missing amount — skipped.")
            return None
        return RiverProposal(
            row_number=row.row_number, timestamp=row.timestamp, river_tag=row.tag,
            type="Transfer", from_account_id=ACCOUNT_WALLET,
            to_account_id=ACCOUNT_EXCHANGE_BTC,
            amount=row.received,
            type_choices=["Transfer", "Deposit"],
        )


# Dedup / merge engine

# Which existing transaction types can correspond to a proposal of each type.
# BTC sends/receives are ambiguous in River's data, so they match the wider
# set the user might have recorded manually.
_COMPATIBLE_TYPES: dict[str, tuple[str, ...]] = {
    "Buy": ("Buy",),
    "Sell": ("Sell",),
    "Deposit": ("Deposit",),
    "Withdrawal": ("Withdrawal", "Transfer"),
    "Transfer": ("Transfer", "Withdrawal", "Deposit"),
}


def ledger_amount(
    tx_type: str,
    amount: Decimal,
    fee_amount: Decimal | None,
    fee_currency: str | None,
) -> Decimal:
    """
    River amounts exclude the network fee. A BitcoinTX Transfer's amount is
    what left the source, fee included (destination receives amount - fee),
    so a BTC fee is added for Transfers. Withdrawals keep the fee on top.
    """
    if tx_type == "Transfer" and fee_amount and (fee_currency or "BTC").upper() == "BTC":
        return amount + fee_amount
    return amount


def _proposal_ledger_amount(proposal: RiverProposal) -> Decimal:
    return ledger_amount(
        proposal.type, proposal.amount, proposal.fee_amount, proposal.fee_currency
    )


def _as_utc(ts: datetime) -> datetime:
    """SQLite returns naive datetimes; all app timestamps are UTC."""
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)


def _nothing_else(_proposal: RiverProposal, _tx: Transaction) -> list[str]:
    """River's rule (owner, 2026-10-14, #253): the same kind, BTC amount and
    minute is the same event. A row's source, purpose and values are the
    preview's defaults or the owner's own edits, so a re-import of an edited
    row isn't recorded twice."""
    return []


def annotate_duplicates(
    proposals: list[RiverProposal],
    db: Session,
    exact_only: bool = False,
    differences: Callable[[RiverProposal, Transaction], list[str]] = _nothing_else,
) -> None:
    """
    Mark proposals that are already in the ledger, or look like it (#253).

    Pass 1 (a duplicate, STATUS_MATCHED): a compatible type, the identical
    BTC amount and the same minute (a row given as a date alone: the same
    day in the tax timezone), and nothing that `differences` names; greedy
    nearest-timestamp, one existing tx matches at most one proposal.

    Pass 2 (similar, STATUS_DISCREPANCY): the same amount within ±48 h,
    anything else different; its note says what. Never left out by itself.

    Pass 3 (BTC moves only): within ±48 h and an amount within ±20 %: the
    user's manual transfer entries are known to be approximate.

    Passes 2 and 3 are skipped when exact_only=True: the execute
    endpoints' double-submit guard leaves out only duplicates.
    """
    existing: list[Transaction] = db.query(Transaction).all()
    tz = get_tax_timezone(db) if any(p.day for p in proposals) else timezone.utc
    used_tx_ids: set = set()
    by_time = sorted(proposals, key=lambda p: p.timestamp)
    for proposal in by_time:
        _match_exactly(proposal, _candidates(proposal, existing, used_tx_ids), used_tx_ids, differences, tz)
    if exact_only:
        return
    for proposal in by_time:
        if proposal.status == STATUS_NEW:
            _match_similar(proposal, _candidates(proposal, existing, used_tx_ids), used_tx_ids, differences, tz)
    for proposal in by_time:
        if proposal.status == STATUS_NEW and proposal.type in ("Transfer", "Withdrawal"):
            _match_roughly(proposal, _candidates(proposal, existing, used_tx_ids), used_tx_ids)


def _candidates(proposal: RiverProposal, existing: list[Transaction], used_tx_ids: set) -> list[Transaction]:
    """The unmatched transactions of a compatible type within the window."""
    types = _COMPATIBLE_TYPES.get(proposal.type, (proposal.type,))
    return [
        tx for tx in existing
        if tx.id not in used_tx_ids
        and tx.type in types
        and abs(_as_utc(tx.timestamp) - proposal.timestamp) <= SIMILAR_WINDOW
    ]


def _nearest(proposal: RiverProposal, txs: list[Transaction]) -> Transaction | None:
    """The transaction closest in time; the first of equally close ones."""
    return min(txs, key=lambda tx: abs(_as_utc(tx.timestamp) - proposal.timestamp), default=None)


def _same_moment(proposal: RiverProposal, tx: Transaction, tz) -> bool:
    """The same minute; for a row given as a date alone, the same day in the tax timezone."""
    if proposal.day is not None:
        return local_date(_as_utc(tx.timestamp), tz) == proposal.day
    return _as_utc(tx.timestamp).replace(second=0, microsecond=0) == proposal.timestamp.replace(second=0, microsecond=0)


def _match_exactly(proposal: RiverProposal, candidates: list[Transaction], used_tx_ids: set, differences, tz) -> None:
    amount = _proposal_ledger_amount(proposal)
    same = [
        tx for tx in candidates
        if Decimal(tx.amount or 0) == amount and _same_moment(proposal, tx, tz) and not differences(proposal, tx)
    ]
    best = _nearest(proposal, same)
    if best is None:
        return
    used_tx_ids.add(best.id)
    proposal.matched_tx_id = best.id
    proposal.status = STATUS_MATCHED


def _match_similar(proposal: RiverProposal, candidates: list[Transaction], used_tx_ids: set, differences, tz) -> None:
    amount = _proposal_ledger_amount(proposal)
    best = _nearest(proposal, [tx for tx in candidates if Decimal(tx.amount or 0) == amount])
    if best is None:
        return
    used_tx_ids.add(best.id)
    proposal.matched_tx_id = best.id
    proposal.status = STATUS_DISCREPANCY
    what = [_when_recorded(proposal, best, tz), *differences(proposal, best)]
    proposal.discrepancy = (
        f"Same BTC amount as tx #{best.id} ({best.type} {btc_text(best.amount or 0)} BTC), "
        f"{'; '.join(what)}: it may be the same transaction"
    )


def _when_recorded(proposal: RiverProposal, tx: Transaction, tz) -> str:
    """When the similar transaction is, from this row: "recorded 3 hours earlier", "recorded on 2026-02-01"."""
    if _same_moment(proposal, tx, tz):
        return "the same day" if proposal.day is not None else "the same minute"
    if proposal.day is not None:
        return f"recorded on {local_date(_as_utc(tx.timestamp), tz).isoformat()}"
    gap = _as_utc(tx.timestamp) - proposal.timestamp
    return f"recorded {_gap_text(gap)} {'earlier' if gap < timedelta(0) else 'later'}"


def _gap_text(gap: timedelta) -> str:
    """A gap as the note says it: "3 minutes", "1 hour", "24 hours"."""
    minutes = round(abs(gap).total_seconds() / 60)
    count, unit = (minutes, "minute") if minutes < 60 else (round(minutes / 60), "hour")
    return f"{count} {unit}{'' if count == 1 else 's'}"


def _match_roughly(proposal: RiverProposal, candidates: list[Transaction], used_tx_ids: set) -> None:
    amount = _proposal_ledger_amount(proposal)
    close = [
        tx for tx in candidates
        if Decimal(tx.amount or 0) > 0
        and abs(Decimal(tx.amount or 0) - amount) / Decimal(tx.amount or 0) <= FUZZY_AMOUNT_TOLERANCE
    ]
    best = _nearest(proposal, close)
    if best is None:
        return
    used_tx_ids.add(best.id)
    proposal.matched_tx_id = best.id
    proposal.status = STATUS_DISCREPANCY
    proposal.discrepancy = (
        f"Likely the same event as tx #{best.id} "
        f"({best.type} {btc_text(best.amount or 0)} BTC) recorded with a "
        f"different amount"
    )
