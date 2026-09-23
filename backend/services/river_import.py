"""
backend/services/river_import.py

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
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

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
from backend.services.csv_import import _parse_decimal

logger = logging.getLogger(__name__)

RIVER_REQUIRED_COLUMNS = {
    "date", "sent amount", "sent currency", "received amount",
    "received currency", "fee amount", "fee currency", "tag",
}

RIVER_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# A buy outlay (sent + USD fee) that repeats at least this many times with no
# fee is treated as a recurring auto-buy pulled from the bank via ACH.
RECURRING_BUY_THRESHOLD = 4

# Dedup windows
EXACT_MATCH_WINDOW = timedelta(hours=48)
FUZZY_MATCH_WINDOW = timedelta(hours=48)
FUZZY_AMOUNT_TOLERANCE = Decimal("0.20")  # ±20% for transfer near-matches

STATUS_NEW = "new"
STATUS_MATCHED = "matched"
STATUS_DISCREPANCY = "discrepancy"


@dataclass
class RiverRow:
    """One parsed row of the River bitcoin-activity CSV."""
    row_number: int
    timestamp: datetime
    sent: Optional[Decimal]
    sent_currency: Optional[str]
    received: Optional[Decimal]
    received_currency: Optional[str]
    fee: Optional[Decimal]
    fee_currency: Optional[str]
    tag: Optional[str]


@dataclass
class RiverProposal:
    """A proposed BitcoinTX transaction adapted from a River row."""
    row_number: int
    timestamp: datetime
    river_tag: Optional[str]
    type: str
    from_account_id: int
    to_account_id: int
    amount: Decimal
    cost_basis_usd: Optional[Decimal] = None
    proceeds_usd: Optional[Decimal] = None
    fee_amount: Optional[Decimal] = None
    fee_currency: Optional[str] = None
    source: Optional[str] = None
    purpose: Optional[str] = None
    # Preview metadata
    type_choices: List[str] = field(default_factory=list)
    funding_choices: List[str] = field(default_factory=list)
    basis_autofilled: bool = False
    status: str = STATUS_NEW
    matched_tx_id: Optional[int] = None
    discrepancy: Optional[str] = None

    @property
    def from_account(self) -> str:
        return ACCOUNT_ID_TO_NAME[self.from_account_id]

    @property
    def to_account(self) -> str:
        return ACCOUNT_ID_TO_NAME[self.to_account_id]

    def to_tx_data(self) -> Dict[str, Any]:
        """Build the dict create_transaction_record() expects."""
        tx_data: Dict[str, Any] = {
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


def parse_river_csv(content: bytes) -> Tuple[List[RiverRow], List[CSVParseError]]:
    """Parse raw River bitcoin-activity CSV bytes into RiverRow objects."""
    errors: List[CSVParseError] = []
    rows: List[RiverRow] = []

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

        def dec(col: str, places: int) -> Optional[Decimal]:
            return _parse_decimal(r.get(col, ""), places)

        sent_cur = r.get("sent currency", "").upper() or None
        recv_cur = r.get("received currency", "").upper() or None
        fee_cur = r.get("fee currency", "").upper() or None

        rows.append(RiverRow(
            row_number=row_number,
            timestamp=ts,
            sent=dec("sent amount", 8),
            sent_currency=sent_cur,
            received=dec("received amount", 8),
            received_currency=recv_cur,
            fee=dec("fee amount", 8),
            fee_currency=fee_cur,
            tag=r.get("tag", "").title() or None,
        ))

    if not rows and not errors:
        errors.append(CSVParseError(
            row_number=0, column=None, severity="error",
            message="No data rows found in file.",
        ))

    return rows, errors


def _usd_fee(row: RiverRow) -> Decimal:
    if row.fee is not None and row.fee_currency == "USD":
        return row.fee
    return Decimal("0")


def _buy_outlay(row: RiverRow) -> Decimal:
    """Total USD that left for a buy: sent + USD fee."""
    return (row.sent or Decimal("0")) + _usd_fee(row)


def _recurring_outlays(rows: List[RiverRow]) -> Dict[Decimal, int]:
    """Count identical buy outlays across the file (the heuristic's signal)."""
    counts: Dict[Decimal, int] = {}
    for row in rows:
        if row.tag == "Buy":
            outlay = _buy_outlay(row)
            counts[outlay] = counts.get(outlay, 0) + 1
    return counts


def adapt_river_rows(
    rows: List[RiverRow],
) -> Tuple[List[RiverProposal], List[CSVParseError], List[CSVParseError]]:
    """
    Map parsed River rows to proposed BitcoinTX transactions.

    Rows that don't match a known pattern produce warnings and are skipped
    (never silently dropped).
    """
    proposals: List[RiverProposal] = []
    errors: List[CSVParseError] = []
    warnings: List[CSVParseError] = []

    outlay_counts = _recurring_outlays(rows)

    for row in rows:
        tag = row.tag

        if tag == "Buy" and row.sent_currency == "USD" and row.received_currency == "BTC":
            if not row.received or row.received <= 0 or not row.sent or row.sent <= 0:
                warnings.append(CSVParseError(
                    row_number=row.row_number, column=None, severity="warning",
                    message="Buy row missing sent/received amount — skipped.",
                ))
                continue
            # Funding heuristic: a recurring no-fee outlay is an auto-buy
            # pulled from the bank via ACH; anything else defaults to the
            # River cash balance. Always user-overridable in the preview.
            recurring = outlay_counts.get(_buy_outlay(row), 0) >= RECURRING_BUY_THRESHOLD
            from_id = ACCOUNT_BANK if (recurring and not row.fee) else ACCOUNT_EXCHANGE_USD
            proposals.append(RiverProposal(
                row_number=row.row_number, timestamp=row.timestamp, river_tag=tag,
                type="Buy", from_account_id=from_id, to_account_id=ACCOUNT_EXCHANGE_BTC,
                amount=row.received,
                cost_basis_usd=row.sent,
                fee_amount=row.fee, fee_currency="USD" if row.fee else None,
                funding_choices=["Bank", "Exchange USD"],
            ))

        elif tag == "Sell" and row.sent_currency == "BTC" and row.received_currency == "USD":
            if not row.sent or row.sent <= 0 or not row.received or row.received <= 0:
                warnings.append(CSVParseError(
                    row_number=row.row_number, column=None, severity="warning",
                    message="Sell row missing sent/received amount — skipped.",
                ))
                continue
            proposals.append(RiverProposal(
                row_number=row.row_number, timestamp=row.timestamp, river_tag=tag,
                type="Sell", from_account_id=ACCOUNT_EXCHANGE_BTC,
                to_account_id=ACCOUNT_EXCHANGE_USD,
                amount=row.sent,
                proceeds_usd=row.received,
                fee_amount=row.fee, fee_currency="USD" if row.fee else None,
            ))

        elif tag in ("Interest", "Income") and row.received_currency == "BTC" and row.received:
            # BTC paid by River (incl. interest on the cash balance, which
            # River pays in BTC). cost_basis_usd (FMV at receipt) is filled
            # by the historical-price autofill in the router; editable.
            proposals.append(RiverProposal(
                row_number=row.row_number, timestamp=row.timestamp, river_tag=tag,
                type="Deposit", from_account_id=ACCOUNT_EXTERNAL,
                to_account_id=ACCOUNT_EXCHANGE_BTC,
                amount=row.received,
                source=tag,
            ))

        elif row.sent_currency == "BTC" and row.received is None:
            # BTC left River. Untagged ⇒ almost always a cold-storage move;
            # Tag=Withdrawal ⇒ the user told River it left their ecosystem.
            # Either way the user can flip it in the preview.
            # River's Sent Amount maps to `amount` (what the destination
            # receives); the network fee, when River reports one, is on top.
            # Proposals keep River's numbers so the preview shows them as-is;
            # ledger_amount() converts Transfers to BitcoinTX semantics (fee
            # included) for dedup and at execute, after the user's edits.
            if not row.sent or row.sent <= 0:
                warnings.append(CSVParseError(
                    row_number=row.row_number, column=None, severity="warning",
                    message="BTC send row missing amount — skipped.",
                ))
                continue
            if tag == "Withdrawal":
                proposals.append(RiverProposal(
                    row_number=row.row_number, timestamp=row.timestamp, river_tag=tag,
                    type="Withdrawal", from_account_id=ACCOUNT_EXCHANGE_BTC,
                    to_account_id=ACCOUNT_EXTERNAL,
                    amount=row.sent,
                    fee_amount=row.fee, fee_currency="BTC" if row.fee else None,
                    purpose="Spent",
                    type_choices=["Withdrawal", "Transfer"],
                ))
            else:
                proposals.append(RiverProposal(
                    row_number=row.row_number, timestamp=row.timestamp, river_tag=tag,
                    type="Transfer", from_account_id=ACCOUNT_EXCHANGE_BTC,
                    to_account_id=ACCOUNT_WALLET,
                    amount=row.sent,
                    fee_amount=row.fee, fee_currency="BTC" if row.fee else None,
                    type_choices=["Transfer", "Withdrawal"],
                ))

        elif row.received_currency == "BTC" and row.sent is None and tag is None:
            # BTC arrived at River with no tag ⇒ default: return trip from
            # cold storage. River cannot see the wallet-side network fee, so
            # fee defaults to 0 (editable in preview).
            if not row.received or row.received <= 0:
                warnings.append(CSVParseError(
                    row_number=row.row_number, column=None, severity="warning",
                    message="BTC receive row missing amount — skipped.",
                ))
                continue
            proposals.append(RiverProposal(
                row_number=row.row_number, timestamp=row.timestamp, river_tag=tag,
                type="Transfer", from_account_id=ACCOUNT_WALLET,
                to_account_id=ACCOUNT_EXCHANGE_BTC,
                amount=row.received,
                type_choices=["Transfer", "Deposit"],
            ))

        else:
            warnings.append(CSVParseError(
                row_number=row.row_number, column=None, severity="warning",
                message=(
                    f"Unrecognized row pattern (tag={tag or 'none'}, "
                    f"sent={row.sent_currency or '-'}, received={row.received_currency or '-'}) — skipped."
                ),
            ))

    return proposals, errors, warnings


# ---------------------------------------------------------------------------
# Dedup / merge engine
# ---------------------------------------------------------------------------

# Which existing transaction types can correspond to a proposal of each type.
# BTC sends/receives are ambiguous in River's data, so they match the wider
# set the user might have recorded manually.
_COMPATIBLE_TYPES: Dict[str, Tuple[str, ...]] = {
    "Buy": ("Buy",),
    "Sell": ("Sell",),
    "Deposit": ("Deposit",),
    "Withdrawal": ("Withdrawal", "Transfer"),
    "Transfer": ("Transfer", "Withdrawal", "Deposit"),
}


def ledger_amount(
    tx_type: str,
    amount: Decimal,
    fee_amount: Optional[Decimal],
    fee_currency: Optional[str],
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


def _detail_discrepancy(proposal: RiverProposal, tx: Transaction) -> Optional[str]:
    """
    Compare USD details of a matched pair; return a description if they
    differ. Only Buy cost basis is compared: it is user-provided and stored
    verbatim. Sell proceeds are NOT compared — the app overwrites
    tx.proceeds_usd with recomputed net disposal proceeds
    (compute_sell_summary_from_disposals), so the original input is not
    preserved and any comparison would always flag a false discrepancy.
    """
    if proposal.type == "Buy" and proposal.cost_basis_usd is not None:
        existing = Decimal(tx.cost_basis_usd or 0)
        if existing != proposal.cost_basis_usd:
            return (
                f"River cost basis ${proposal.cost_basis_usd} differs from "
                f"recorded ${existing} (tx #{tx.id})"
            )
    return None


def annotate_duplicates(
    proposals: List[RiverProposal], db: Session, exact_only: bool = False
) -> None:
    """
    Mark proposals that already exist in the ledger.

    Pass 1 (exact): compatible type, identical BTC amount, within ±48 h —
    greedy nearest-timestamp, one existing tx matches at most one proposal.
    A matched pair whose USD details differ is flagged as a discrepancy
    (still excluded from import).

    Pass 2 (fuzzy, BTC moves only): compatible type within ±48 h and amount
    within ±20 % — the user's manual transfer entries are known to be
    approximate, so these are flagged as discrepancies rather than imported
    as duplicates. Skipped when exact_only=True (the execute endpoint's
    double-import guard must not block rows the user deliberately chose to
    import despite a fuzzy flag).
    """
    existing: List[Transaction] = db.query(Transaction).all()
    used_tx_ids: set = set()

    def candidates(proposal: RiverProposal) -> List[Transaction]:
        types = _COMPATIBLE_TYPES.get(proposal.type, (proposal.type,))
        return [
            tx for tx in existing
            if tx.id not in used_tx_ids
            and tx.type in types
            and abs(_as_utc(tx.timestamp) - proposal.timestamp) <= EXACT_MATCH_WINDOW
        ]

    # Pass 1: exact amount
    for proposal in sorted(proposals, key=lambda p: p.timestamp):
        best: Optional[Transaction] = None
        best_delta: Optional[timedelta] = None
        for tx in candidates(proposal):
            if Decimal(tx.amount or 0) != _proposal_ledger_amount(proposal):
                continue
            delta = abs(_as_utc(tx.timestamp) - proposal.timestamp)
            if best_delta is None or delta < best_delta:
                best, best_delta = tx, delta
        if best is not None:
            used_tx_ids.add(best.id)
            proposal.matched_tx_id = best.id
            diff = _detail_discrepancy(proposal, best)
            if diff:
                proposal.status = STATUS_DISCREPANCY
                proposal.discrepancy = diff
            else:
                proposal.status = STATUS_MATCHED

    if exact_only:
        return

    # Pass 2: fuzzy amounts for BTC moves
    for proposal in sorted(proposals, key=lambda p: p.timestamp):
        if proposal.status != STATUS_NEW or proposal.type not in ("Transfer", "Withdrawal"):
            continue
        best = None
        best_delta = None
        for tx in candidates(proposal):
            tx_amount = Decimal(tx.amount or 0)
            if tx_amount <= 0:
                continue
            rel_diff = abs(tx_amount - _proposal_ledger_amount(proposal)) / tx_amount
            if rel_diff > FUZZY_AMOUNT_TOLERANCE:
                continue
            delta = abs(_as_utc(tx.timestamp) - proposal.timestamp)
            if best_delta is None or delta < best_delta:
                best, best_delta = tx, delta
        if best is not None:
            used_tx_ids.add(best.id)
            proposal.matched_tx_id = best.id
            proposal.status = STATUS_DISCREPANCY
            proposal.discrepancy = (
                f"Likely the same event as tx #{best.id} "
                f"({best.type} {Decimal(best.amount or 0)} BTC) recorded with a "
                f"different amount — review before importing"
            )
