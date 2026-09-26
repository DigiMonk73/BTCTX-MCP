"""
backend/services/entry_import.py

Validation, FMV autofill, dedup and dry-run simulation for the JSON entry
import (/api/import/entries). Built for AI/programmatic clients such as the
MCP server in mcp_server/: they parse free-form input (exchange emails,
wallet exports, plain English) into rows, preview them here, and only then
write them.

Reuses the battle-tested pieces of the other importers:
  - csv_import._validate_row         row validation (account names, type rules)
  - river_import.annotate_duplicates  exact / fuzzy dedup against the ledger
  - transaction.create_transaction_record  the real ledger + FIFO logic

The preview runs the real create path inside the request's DB session and
rolls it back, so "Not enough BTC", realized gains, holding periods and
backdating effects on existing sells are exactly what execute would produce.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.constants import ACCOUNT_ID_TO_NAME, INCOME_SOURCES
from backend.models.transaction import Transaction
from backend.schemas.entry_import import (
    AccountBalance,
    AffectedTransaction,
    EntryResult,
    EntryRow,
    SimulatedResult,
)
from backend.services import price_history
from backend.services.tax_time import local_noon_utc
from backend.services.calculation import get_all_account_balances
from backend.services.csv_import import _parse_date, _parse_decimal, _validate_row
from backend.services.river_import import (
    STATUS_DISCREPANCY,
    STATUS_NEW,
    RiverProposal,
    annotate_duplicates,
)
from backend.services.transaction import (
    create_transaction_record,
    ensure_fee_account_exists,
)

logger = logging.getLogger(__name__)

# Acquisitions before disposals for same-timestamp rows (mirrors execute_import)
TYPE_ORDER = {"Deposit": 0, "Buy": 1, "Transfer": 2, "Sell": 3, "Withdrawal": 4}

STATUS_READY = "ready"
STATUS_DUPLICATE = "duplicate"
STATUS_POSSIBLE_DUPLICATE = "possible_duplicate"
STATUS_INVALID = "invalid"
STATUS_REJECTED = "rejected"
STATUS_NOT_SIMULATED = "not_simulated"

# Rows with these statuses are written by execute
WRITABLE_STATUSES = (STATUS_READY, STATUS_POSSIBLE_DUPLICATE)


@dataclass
class PreparedRow:
    row: int
    tx_data: Optional[Dict[str, Any]] = None
    result: EntryResult = None


# ------------------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------------------
def _dec_str(value: Optional[Decimal]) -> str:
    return format(value, "f") if value is not None else ""


def _normalize_date(raw: str, tz) -> str:
    """
    Parse a user/AI-supplied date into a UTC string _validate_row accepts.
    Explicit offsets / "Z" are honored. Without one, the time is local to
    the tax timezone `tz`; a bare date (no time) means noon there, safely
    inside that calendar day.
    """
    raw = (raw or "").strip()
    if not raw:
        return raw
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        dt = _parse_date(raw)  # e.g. 01/15/2024 — returned as naive-UTC-tagged
        if dt is None:
            return raw  # let _validate_row report it
        dt = dt.replace(tzinfo=None)
    date_only = len(raw) <= 10 and ":" not in raw
    if dt.tzinfo is None:
        dt = local_noon_utc(dt.date(), tz) if date_only else dt.replace(tzinfo=tz)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalized_view(tx_data: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Echo the validated row back in canonical form."""
    ts: datetime = tx_data["timestamp"]
    view = {
        "date": ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "type": tx_data["type"],
        "amount": _dec_str(tx_data["amount"]),
        "from_account": ACCOUNT_ID_TO_NAME[tx_data["from_account_id"]],
        "to_account": ACCOUNT_ID_TO_NAME[tx_data["to_account_id"]],
    }
    for key in ("cost_basis_usd", "proceeds_usd", "fee_amount", "fmv_usd", "fee_usd"):
        if tx_data.get(key) is not None:
            view[key] = _dec_str(tx_data[key])
    for key in ("fee_currency", "source", "purpose"):
        if tx_data.get(key):
            view[key] = tx_data[key]
    return view


def validate_rows(rows: List[EntryRow], tz=timezone.utc) -> List[PreparedRow]:
    """Validate every row with the CSV importer's rules (dates in tax timezone `tz`)."""
    prepared: List[PreparedRow] = []
    for i, row in enumerate(rows, start=1):
        str_row = {
            "date": _normalize_date(row.date, tz),
            "type": row.type or "",
            "amount": _dec_str(row.amount),
            "from_account": row.from_account or "",
            "to_account": row.to_account or "",
            "cost_basis_usd": _dec_str(row.cost_basis_usd),
            "proceeds_usd": _dec_str(row.proceeds_usd),
            "fee_amount": _dec_str(row.fee_amount),
            "fee_currency": row.fee_currency or "",
            "source": row.source or "",
            "purpose": row.purpose or "",
            "notes": "",
        }
        tx_data, _preview, errors, warnings = _validate_row(str_row, i)
        error_msgs = [e.message for e in errors]

        if tx_data is not None and row.fee_usd is not None:
            fee_usd = _parse_decimal(_dec_str(row.fee_usd), 2)
            if fee_usd is None or fee_usd < 0:
                error_msgs.append("fee_usd must be a USD amount with at most 2 decimals.")
            else:
                tx_data["fee_usd"] = fee_usd

        if tx_data is not None and row.fmv_usd is not None:
            fmv = _parse_decimal(_dec_str(row.fmv_usd), 2)
            if fmv is None:
                error_msgs.append("fmv_usd must be a USD amount with at most 2 decimals.")
            else:
                tx_data["fmv_usd"] = fmv

        result = EntryResult(
            row=i,
            status=STATUS_INVALID if error_msgs else STATUS_READY,
            errors=error_msgs,
            warnings=[w.message for w in warnings],
        )
        prepared.append(PreparedRow(
            row=i,
            tx_data=None if error_msgs else tx_data,
            result=result,
        ))
    return prepared


# ------------------------------------------------------------------------------
# FMV autofill
# ------------------------------------------------------------------------------
def _autofill_target(tx_data: Dict[str, Any]) -> Optional[str]:
    """Which USD field (if any) should be filled from the day's BTC price."""
    tx_type = tx_data["type"]
    if tx_type == "Deposit":
        source = (tx_data.get("source") or "").lower()
        if source in INCOME_SOURCES and tx_data.get("cost_basis_usd") is None:
            return "cost_basis_usd"
    elif tx_type == "Withdrawal":
        purpose = (tx_data.get("purpose") or "").lower()
        if purpose == "spent" and tx_data.get("proceeds_usd") is None:
            return "proceeds_usd"
        if purpose in ("gift", "donation") and tx_data.get("fmv_usd") is None:
            return "fmv_usd"
    return None


async def autofill_fmv(prepared: List[PreparedRow], db: Session) -> None:
    """
    Fill FMV-derived USD values the tax math needs but the caller omitted:
      - Income/Interest/Reward deposits: cost basis = FMV at receipt
      - Spent withdrawals: proceeds = FMV of what was bought
      - Gift/Donation withdrawals: fmv_usd for the tax report
    Uses the daily historical price; on lookup failure the field stays
    empty and the row gets a warning.
    """
    price_cache: Dict[str, Optional[Decimal]] = {}
    for p in prepared:
        if p.tx_data is None:
            continue
        target = _autofill_target(p.tx_data)
        if target is None:
            continue
        date_str = p.tx_data["timestamp"].strftime("%Y-%m-%d")
        if date_str not in price_cache:
            try:
                price_cache[date_str] = await price_history.daily_price_async(db, p.tx_data["timestamp"])
            except Exception as exc:
                logger.warning("FMV lookup failed for %s: %s", date_str, exc)
                price_cache[date_str] = None
        price = price_cache[date_str]
        if price is None:
            p.result.warnings.append(
                f"Could not fetch the BTC price for {date_str}; {target} was left empty."
            )
            continue
        p.tx_data[target] = (price * p.tx_data["amount"]).quantize(Decimal("0.01"))
        p.result.autofilled_fields.append(target)
        # Drop the validator's "no <field> provided" warning — it's filled now
        p.result.warnings = [w for w in p.result.warnings if target not in w]


# ------------------------------------------------------------------------------
# Dedup
# ------------------------------------------------------------------------------
def _stub(p: PreparedRow) -> RiverProposal:
    d = p.tx_data
    return RiverProposal(
        row_number=p.row,
        timestamp=d["timestamp"],
        river_tag=None,
        type=d["type"],
        from_account_id=d["from_account_id"],
        to_account_id=d["to_account_id"],
        amount=d["amount"],
        cost_basis_usd=d.get("cost_basis_usd"),
        proceeds_usd=d.get("proceeds_usd"),
    )


def mark_duplicates(prepared: List[PreparedRow], db: Session, exact_only: bool = False) -> None:
    """
    Exact match (same type family, same BTC amount, ±48h) => duplicate, never written.
    Fuzzy BTC-move match (±20% amount) => possible_duplicate, written unless removed.
    """
    valid = [p for p in prepared if p.tx_data is not None]
    if not valid:
        return

    exact_stubs = [_stub(p) for p in valid]
    annotate_duplicates(exact_stubs, db, exact_only=True)
    fuzzy_stubs: List[Optional[RiverProposal]] = [None] * len(valid)
    if not exact_only:
        fuzzy_stubs = [_stub(p) for p in valid]
        annotate_duplicates(fuzzy_stubs, db)

    for p, exact, fuzzy in zip(valid, exact_stubs, fuzzy_stubs):
        if exact.status != STATUS_NEW:
            p.result.status = STATUS_DUPLICATE
            p.result.matched_transaction_id = exact.matched_tx_id
            if exact.discrepancy:
                p.result.warnings.append(exact.discrepancy)
        elif fuzzy is not None and fuzzy.status == STATUS_DISCREPANCY:
            p.result.status = STATUS_POSSIBLE_DUPLICATE
            p.result.matched_transaction_id = fuzzy.matched_tx_id
            p.result.warnings.append(fuzzy.discrepancy)


# ------------------------------------------------------------------------------
# Dry run
# ------------------------------------------------------------------------------
def _chronological(prepared: List[PreparedRow]) -> List[PreparedRow]:
    writable = [
        p for p in prepared
        if p.tx_data is not None and p.result.status in WRITABLE_STATUSES
    ]
    return sorted(
        writable,
        key=lambda p: (p.tx_data["timestamp"], TYPE_ORDER.get(p.tx_data["type"], 99)),
    )


def _gain_snapshot(db: Session) -> Dict[int, Tuple[Optional[Decimal], Optional[str]]]:
    return {
        tx.id: (tx.realized_gain_usd, tx.holding_period)
        for tx in db.query(Transaction).all()
    }


def simulate(
    prepared: List[PreparedRow], db: Session
) -> Tuple[List[AffectedTransaction], List[AccountBalance]]:
    """
    Run the real create path for every writable row, record what the ledger
    computed, then roll everything back. Stops at the first rejected row
    (later rows depend on it for FIFO and are marked not_simulated).
    """
    ordered = _chronological(prepared)
    if not ordered:
        return [], []

    # May commit (only if the fee account is missing) — do it before the dry run.
    ensure_fee_account_exists(db)

    affected: List[AffectedTransaction] = []
    balances: List[AccountBalance] = []
    before = _gain_snapshot(db)
    created: List[Tuple[PreparedRow, Transaction]] = []
    failed_at: Optional[int] = None

    try:
        for pos, p in enumerate(ordered):
            try:
                tx = create_transaction_record(dict(p.tx_data), db, auto_commit=False)
            except HTTPException as exc:
                p.result.status = STATUS_REJECTED
                p.result.errors.append(str(exc.detail))
                failed_at = pos
                break
            except Exception as exc:  # defensive: surface, never write
                logger.exception("Entry simulation failed on row %s", p.row)
                p.result.status = STATUS_REJECTED
                p.result.errors.append(f"Unexpected error: {exc}")
                failed_at = pos
                break
            created.append((p, tx))

        if failed_at is not None:
            for p in ordered[failed_at + 1:]:
                p.result.status = STATUS_NOT_SIMULATED
                p.result.warnings.append(
                    "Not simulated: an earlier row (chronologically) was rejected."
                )
        else:
            db.flush()

        for p, tx in created:
            p.result.simulated = SimulatedResult(
                cost_basis_usd=tx.cost_basis_usd,
                proceeds_usd=tx.proceeds_usd,
                realized_gain_usd=tx.realized_gain_usd,
                holding_period=tx.holding_period,
            )

        if failed_at is None:
            for tx in db.query(Transaction).filter(Transaction.id.in_(before.keys())).all():
                old_gain, old_hp = before[tx.id]
                if (tx.realized_gain_usd, tx.holding_period) != (old_gain, old_hp):
                    affected.append(AffectedTransaction(
                        id=tx.id,
                        type=tx.type,
                        date=tx.timestamp,
                        realized_gain_before=old_gain,
                        realized_gain_after=tx.realized_gain_usd,
                        holding_period_before=old_hp,
                        holding_period_after=tx.holding_period,
                    ))
            balances = [
                AccountBalance(account=b["name"], currency=b["currency"], balance=b["balance"])
                for b in get_all_account_balances(db)
            ]
    finally:
        db.rollback()

    return affected, balances


# ------------------------------------------------------------------------------
# Execute
# ------------------------------------------------------------------------------
def write_rows(prepared: List[PreparedRow], db: Session) -> List[Tuple[PreparedRow, Transaction]]:
    """
    Atomically create every writable row in chronological order.
    Raises HTTPException(400) and rolls back on the first failure.
    """
    ordered = _chronological(prepared)
    if not ordered:
        return []

    ensure_fee_account_exists(db)
    created: List[Tuple[PreparedRow, Transaction]] = []
    try:
        for p in ordered:
            try:
                tx = create_transaction_record(dict(p.tx_data), db, auto_commit=False)
            except HTTPException as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"Row {p.row}: {exc.detail}. No transactions were saved.",
                )
            created.append((p, tx))
        db.commit()
    except Exception:
        db.rollback()
        raise

    for _p, tx in created:
        db.refresh(tx)
    return created
