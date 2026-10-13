"""
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
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.constants import ACCOUNT_ID_TO_NAME, BTC_ACCOUNTS, INHERITED_SOURCE, VALUED_AT_RECEIPT
from backend.models.transaction import Transaction
from backend.schemas.entry_import import (
    AccountBalance,
    AffectedTransaction,
    EntryResult,
    EntryRow,
    SimulatedResult,
)
from backend.services import hourly_prices
from backend.services.tax_time import local_noon_utc
from backend.services.calculation import get_all_account_balances
from backend.schemas.transaction import USD_PLACES
from backend.services.csv_import import _parse_date, _parse_decimal, _validate_row, number_limits, number_text
from backend.services.river_import import (
    STATUS_DISCREPANCY,
    STATUS_NEW,
    RiverProposal,
    annotate_duplicates,
)
from backend.services.transaction import (
    create_transaction_record,
    date_of_death,
    date_of_death_price,
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
    tx_data: dict[str, Any] | None = None
    result: EntryResult = None


# Validation
def _dec_str(value: Decimal | None) -> str:
    return format(value, "f") if value is not None else ""


def _normalize_date(raw: str, tz) -> str:
    """
    Parse a user/AI-supplied date into a UTC string _validate_row accepts.
    Explicit offsets, "Z" and " UTC" are honored. Without one, the time is
    local to the tax timezone `tz`; a bare date (no time) means noon there,
    safely inside that calendar day.
    """
    raw = (raw or "").strip()
    if not raw:
        return raw
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        # e.g. 01/15/2024 or "2024-01-15 10:00:00 UTC", read as the CSV import reads them
        dt = _parse_date(raw, tz)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else raw  # None: _validate_row reports it
    date_only = len(raw) <= 10 and ":" not in raw
    if dt.tzinfo is None:
        dt = local_noon_utc(dt.date(), tz) if date_only else dt.replace(tzinfo=tz)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalized_view(tx_data: dict[str, Any]) -> dict[str, str | None]:
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
    if tx_data.get("acquired_at"):
        view["acquired_at"] = tx_data["acquired_at"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return view


def validate_rows(rows: list[EntryRow], tz=timezone.utc) -> list[PreparedRow]:
    """Validate every row with the CSV importer's rules (dates in tax timezone `tz`)."""
    prepared: list[PreparedRow] = []
    for i, row in enumerate(rows, start=1):
        str_row = {
            "date": _normalize_date(row.date, tz),
            "type": row.type or "",
            "amount": number_text(row.amount),
            "from_account": row.from_account or "",
            "to_account": row.to_account or "",
            "cost_basis_usd": number_text(row.cost_basis_usd),
            "proceeds_usd": number_text(row.proceeds_usd),
            "fee_amount": number_text(row.fee_amount),
            "fee_currency": row.fee_currency or "",
            "source": row.source or "",
            "purpose": row.purpose or "",
            "notes": "",
            "acquired_at": _normalize_date(row.acquired_at, tz) if row.acquired_at else "",
        }
        tx_data, _preview, errors, warnings = _validate_row(str_row, i)
        error_msgs = [e.message for e in errors]

        if tx_data is not None and row.fee_usd is not None:
            fee_usd = _parse_decimal(number_text(row.fee_usd), USD_PLACES)
            if fee_usd is None or fee_usd < 0:
                error_msgs.append(f"fee_usd must be a USD amount with at most {number_limits(USD_PLACES)}.")
            else:
                tx_data["fee_usd"] = fee_usd

        if tx_data is not None and row.fmv_usd is not None:
            fmv = _parse_decimal(number_text(row.fmv_usd), USD_PLACES)
            if fmv is None:
                error_msgs.append(f"fmv_usd must be a USD amount with at most {number_limits(USD_PLACES)}.")
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


# FMV autofill
def _autofill_target(tx_data: dict[str, Any]) -> str | None:
    """
    Which USD field (if any) should be filled from the hour's BTC price. Only
    BTC moves: a deposit into or withdrawal from Bank or Exchange USD is in
    USD, so its amount times the BTC price means nothing.
    """
    tx_type = tx_data["type"]
    if tx_type == "Deposit" and tx_data["to_account_id"] in BTC_ACCOUNTS:
        source = (tx_data.get("source") or "").lower()
        if source in VALUED_AT_RECEIPT and tx_data.get("cost_basis_usd") is None:
            return "cost_basis_usd"
    elif tx_type == "Withdrawal" and tx_data["from_account_id"] in BTC_ACCOUNTS:
        purpose = (tx_data.get("purpose") or "").lower()
        if purpose == "spent" and tx_data.get("proceeds_usd") is None:
            return "proceeds_usd"
        if purpose in ("gift", "donation") and tx_data.get("fmv_usd") is None:
            return "fmv_usd"
    return None


async def autofill_fmv(prepared: list[PreparedRow], db: Session) -> None:
    """
    Fill FMV-derived USD values the tax math needs but the caller omitted:
      - Income/Interest/Reward/Rebate deposits: cost basis = FMV at receipt;
        Inherited deposits: FMV on the date of death (acquired_at)
      - Spent withdrawals: proceeds = FMV of what was bought
      - Gift/Donation withdrawals: fmv_usd for the tax report
    Uses the price of the transaction's hour (else its day:
    services/hourly_prices.py), an inheritance its date of death's day price
    as the form does (#173); on lookup failure the field stays empty and
    the row gets a warning.
    """
    price_cache: dict[tuple, hourly_prices.Priced | None] = {}
    for p in prepared:
        if p.tx_data is None:
            continue
        target = _autofill_target(p.tx_data)
        if target is None:
            continue
        # An inheritance is valued on the date of death (#154), anything else at its own time
        inherited = target == "cost_basis_usd" and str(p.tx_data.get("source") or "").lower() == INHERITED_SOURCE
        when = (p.tx_data.get("acquired_at") if inherited else None) or p.tx_data["timestamp"]
        key = ("day", date_of_death(when, db)) if inherited else ("hour", hourly_prices.hour_of(when))
        if key not in price_cache:
            try:
                lookup = date_of_death_price if inherited else hourly_prices.price_at
                price_cache[key] = await run_in_threadpool(lookup, db, when)
            except Exception as exc:
                # The time (a transaction's) only in the DEBUG log
                logger.warning("FMV lookup failed (%s)", type(exc).__name__)
                logger.debug("FMV lookup failed for %s: %s", when, exc)
                price_cache[key] = None
        priced = price_cache[key]
        if priced is None:
            moment = f"{date_of_death(when, db)}" if inherited else f"{when:%Y-%m-%d %H:00} UTC"
            p.result.warnings.append(f"Could not fetch the BTC price for {moment}; {target} was left empty.")
            continue
        p.tx_data[target] = (priced.usd * p.tx_data["amount"]).quantize(Decimal("0.01"))
        # From the price, not typed: an edit re-prices it (#76). A gift's
        # value isn't on any form, and stays as filled.
        if target == "cost_basis_usd":
            p.tx_data["cost_basis_from_price"] = True
        elif target == "proceeds_usd":
            p.tx_data["proceeds_from_price"] = True
        if target != "fmv_usd":
            p.tx_data["price_moment"] = priced.moment
        p.result.autofilled_fields.append(target)
        # Drop the validator's "no <field> provided" warning — it's filled now
        p.result.warnings = [w for w in p.result.warnings if target not in w]


# Dedup
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


def mark_duplicates(prepared: list[PreparedRow], db: Session, exact_only: bool = False) -> None:
    """
    Exact match (same type family, same BTC amount, ±48h, and for a Buy the
    same cost basis) => duplicate, never written.
    Same amount at another cost basis, or a fuzzy BTC-move match (±20%
    amount) => possible_duplicate: flagged for the AI to ask about, written
    unless removed. (A Buy at another price used to be a duplicate, so a
    second purchase of the same amount could never be saved.)
    """
    valid = [p for p in prepared if p.tx_data is not None]
    if not valid:
        return

    exact_stubs = [_stub(p) for p in valid]
    annotate_duplicates(exact_stubs, db, exact_only=True)
    fuzzy_stubs: list[RiverProposal | None] = [None] * len(valid)
    if not exact_only:
        fuzzy_stubs = [_stub(p) for p in valid]
        annotate_duplicates(fuzzy_stubs, db)

    for p, exact, fuzzy in zip(valid, exact_stubs, fuzzy_stubs):
        if exact.status == STATUS_DISCREPANCY:
            recorded = db.get(Transaction, exact.matched_tx_id)
            p.result.status = STATUS_POSSIBLE_DUPLICATE
            p.result.matched_transaction_id = exact.matched_tx_id
            p.result.warnings.append(
                f"A {exact.type} of the same BTC amount within 48 hours is already recorded "
                f"(#{exact.matched_tx_id}, cost basis ${Decimal(recorded.cost_basis_usd or 0):.2f}); "
                f"this one's is ${Decimal(exact.cost_basis_usd):.2f}. Save it only if it's another purchase."
            )
        elif exact.status != STATUS_NEW:
            p.result.status = STATUS_DUPLICATE
            p.result.matched_transaction_id = exact.matched_tx_id
        elif fuzzy is not None and fuzzy.status == STATUS_DISCREPANCY:
            p.result.status = STATUS_POSSIBLE_DUPLICATE
            p.result.matched_transaction_id = fuzzy.matched_tx_id
            p.result.warnings.append(fuzzy.discrepancy)


# Dry run
def _chronological(prepared: list[PreparedRow]) -> list[PreparedRow]:
    writable = [
        p for p in prepared
        if p.tx_data is not None and p.result.status in WRITABLE_STATUSES
    ]
    return sorted(
        writable,
        key=lambda p: (p.tx_data["timestamp"], TYPE_ORDER.get(p.tx_data["type"], 99)),
    )


def _gain_snapshot(db: Session) -> dict[int, tuple[Decimal | None, str | None]]:
    return {
        tx.id: (tx.realized_gain_usd, tx.holding_period)
        for tx in db.query(Transaction).all()
    }


def simulate(
    prepared: list[PreparedRow], db: Session
) -> tuple[list[AffectedTransaction], list[AccountBalance]]:
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

    before = _gain_snapshot(db)
    try:
        created, failed_at = _create_until_refused(ordered, db)
        if failed_at is None:
            db.flush()
        else:
            _mark_not_simulated(ordered[failed_at + 1:])
        for p, tx in created:
            p.result.simulated = SimulatedResult(
                cost_basis_usd=tx.cost_basis_usd,
                proceeds_usd=tx.proceeds_usd,
                realized_gain_usd=tx.realized_gain_usd,
                holding_period=tx.holding_period,
            )
        if failed_at is not None:
            return [], []
        return _affected(before, db), _balances(db)
    finally:
        db.rollback()


def _create_until_refused(
    ordered: list[PreparedRow], db: Session
) -> tuple[list[tuple[PreparedRow, Transaction]], int | None]:
    """Create the rows in order until one is refused (it is marked rejected):
    (the rows created with their transactions, the refused row's position)."""
    created: list[tuple[PreparedRow, Transaction]] = []
    for pos, p in enumerate(ordered):
        try:
            tx = create_transaction_record(dict(p.tx_data), db, auto_commit=False)
        except HTTPException as exc:
            _reject(p, str(exc.detail))
            return created, pos
        except Exception as exc:  # defensive: surface, never write
            logger.exception("Entry simulation failed on row %s", p.row)
            _reject(p, f"Unexpected error: {exc}")
            return created, pos
        created.append((p, tx))
    return created, None


def _reject(p: PreparedRow, error: str) -> None:
    p.result.status = STATUS_REJECTED
    p.result.errors.append(error)


def _mark_not_simulated(rows: list[PreparedRow]) -> None:
    for p in rows:
        p.result.status = STATUS_NOT_SIMULATED
        p.result.warnings.append("Not simulated: an earlier row (chronologically) was rejected.")


def _affected(before: dict, db: Session) -> list[AffectedTransaction]:
    """The existing transactions whose gain or holding period the new rows change."""
    affected = []
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
    return affected


def _balances(db: Session) -> list[AccountBalance]:
    return [
        AccountBalance(account=b["name"], currency=b["currency"], balance=b["balance"])
        for b in get_all_account_balances(db)
    ]


# Execute
def write_rows(prepared: list[PreparedRow], db: Session) -> list[tuple[PreparedRow, Transaction]]:
    """
    Atomically create every writable row in chronological order.
    Raises HTTPException(400) and rolls back on the first failure.
    """
    ordered = _chronological(prepared)
    if not ordered:
        return []

    ensure_fee_account_exists(db)
    created: list[tuple[PreparedRow, Transaction]] = []
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
