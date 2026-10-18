"""
Validation, FMV autofill, dedup and dry-run simulation for the JSON entry
import (/api/import/entries). Built for AI/programmatic clients such as the
MCP server in mcp_server/: they parse free-form input (exchange emails,
wallet exports, plain English) into rows, preview them here, and only then
write them.

Reuses the battle-tested pieces of the other importers:
  - csv_import._validate_row         row validation (account names, type rules)
  - river_import.annotate_duplicates  duplicate / similar check against the ledger
  - transaction.create_transaction_record  the real ledger + FIFO logic

The preview runs the real create path inside the request's DB session and
rolls it back, so "Not enough BTC", realized gains, holding periods and
backdating effects on existing sells are exactly what execute would produce.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.constants import ACCOUNT_ID_TO_NAME, BTC_ACCOUNTS, GIFT_LIKE_PURPOSES, INHERITED_SOURCE, VALUED_AT_RECEIPT, normalized
from backend.database import is_busy
from backend.models.transaction import Transaction
from backend.schemas.entry_import import (
    AccountBalance,
    AffectedTransaction,
    EntryResult,
    EntryRow,
    FromPrice,
    SimulatedResult,
)
from backend.services import hourly_prices, price_history
from backend.services.tax_time import DateOutOfRange, as_utc, get_tax_timezone, local_date, local_noon_utc
from backend.services.calculation import get_all_account_balances
from backend.schemas.transaction import USD_PLACES
from backend.services.csv_import import (
    _parse_date, _parse_decimal, _validate_row, number_limits, number_text,
)
from backend.unexpected_errors import log_unexpected
from backend.services.river_import import (
    STATUS_MATCHED,
    STATUS_NEW,
    DuplicateRule,
    RiverProposal,
    annotate_duplicates,
    is_duplicate,
    match_by_moving,
    same_ledger_amount,
)
from backend.services.transaction import (
    create_transaction_record,
    date_of_death,
    date_of_death_price,
    ensure_fee_account_exists,
    find_prices_first,
    price_used,
    values_from_price,
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
# A row the dry run stopped at for a reason other than the ledger's: never
# the error's own text (SQL, a path, a date), which the AI would pass on (#204)
SIMULATION_FAILED = "Unexpected error: the dry run stopped at this row. BitcoinTX's log says what."
SIMULATION_BUSY = "BitcoinTX was busy saving something else: preview again in a moment."


@dataclass
class PreparedRow:
    row: int
    tx_data: dict[str, Any] | None = None
    result: EntryResult = None
    day: date | None = None  # given as a date alone: its day in the tax timezone (#253)
    not_a_duplicate_of: int | None = None  # the user said it's another transaction than this one (#253, #378)


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
        dt = None
    try:
        if dt is None:
            dt = _parse_date(raw, tz)
        elif dt.tzinfo is None:
            dt = local_noon_utc(dt.date(), tz) if _date_only(raw) else dt.replace(tzinfo=tz)
        # None or out of range (#211): _validate_row reports it, as the CSV import does
        return as_utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else raw
    except DateOutOfRange:
        return raw


def _date_only(raw: str) -> bool:
    """A date given without a time ("2025-03-20", "03/20/2025")."""
    raw = (raw or "").strip()
    return bool(raw) and len(raw) <= 10 and ":" not in raw


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
        view["acquired_at"] = tx_data["acquired_at"].isoformat()  # a date (#185)
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
        # The tax timezone: a date originally acquired given with a time is
        # its date there (#185); every row's own date is already in UTC
        tx_data, _preview, errors, warnings = _validate_row(str_row, i, tz)
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
            day=local_date(tx_data["timestamp"], tz) if tx_data and _date_only(row.date) else None,
            not_a_duplicate_of=row.not_a_duplicate_of,
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
        source = normalized(tx_data.get("source"))
        if source in VALUED_AT_RECEIPT and tx_data.get("cost_basis_usd") is None:
            return "cost_basis_usd"
    elif tx_type == "Withdrawal" and tx_data["from_account_id"] in BTC_ACCOUNTS:
        purpose = normalized(tx_data.get("purpose"))
        if purpose == "spent" and tx_data.get("proceeds_usd") is None:
            return "proceeds_usd"
        if purpose in GIFT_LIKE_PURPOSES and tx_data.get("fmv_usd") is None:
            return "fmv_usd"
    return None


async def autofill_fmv(prepared: list[PreparedRow], db: Session) -> None:
    """
    Fill FMV-derived USD values the tax math needs but the caller omitted:
      - Income/Interest/Reward/Rebate deposits: cost basis = FMV at receipt;
        Inherited deposits: FMV on the date of death (acquired_at)
      - Spent withdrawals: proceeds = FMV of what was bought
      - Gift/Donation/Lost withdrawals: fmv_usd for the tax report, as the
        save fills a blank one (#255)
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
        inherited = target == "cost_basis_usd" and normalized(p.tx_data.get("source")) == INHERITED_SOURCE
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
        # From the price, not typed: an edit re-prices it (#76, #255)
        p.tx_data[{"cost_basis_usd": "cost_basis_from_price", "proceeds_usd": "proceeds_from_price",
                   "fmv_usd": "fmv_from_price"}[target]] = True
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
        source=d.get("source"),
        purpose=d.get("purpose"),
        day=p.day,
    )


def _label(value: str | None) -> str:
    """A source or purpose to compare: case and "N/A" aside."""
    text = (value or "").strip().lower()
    return "" if text == "n/a" else text


def _entry_differences(row: RiverProposal, tx: Transaction) -> list[str]:
    """What else a row the AI sends must share with a transaction to be it
    (D1, #253): its type, its source or purpose, and a Buy's cost basis (a
    Buy at another price can be another purchase). A Sell's proceeds aren't
    compared: the stored ones are recomputed net of fees."""
    if tx.type != row.type:
        return [f"recorded as a {tx.type}, not a {row.type}"]
    out = [
        f"its {name} is {getattr(tx, name) or 'none'}, not {getattr(row, name) or 'none'}"
        for name in ("source", "purpose")
        if _label(getattr(tx, name)) != _label(getattr(row, name))
    ]
    if row.type == "Buy" and row.cost_basis_usd is not None and Decimal(tx.cost_basis_usd or 0) != row.cost_basis_usd:
        out.append(f"its cost basis is ${Decimal(tx.cost_basis_usd or 0):.2f}, not ${Decimal(row.cost_basis_usd):.2f}")
    return out


ENTRY_RULE = DuplicateRule(amounts=(same_ledger_amount,), differences=_entry_differences)


def mark_duplicates(prepared: list[PreparedRow], db: Session, exact_only: bool = False) -> None:
    """
    The duplicate rule (D1, #253). The same type, BTC amount, source or
    purpose and minute as a transaction in the ledger (a row given as a date
    alone: the same day), and for a Buy the same cost basis => duplicate,
    left out. The timed rows take their duplicates before the rows given as
    a date alone, so a date-alone row is the one saved when it and a timed
    row share their only copy (#472). The most rows are matched: a row left
    without one takes a duplicate another row holds when that row can take
    another of its own (#411).
    A row the user says is another transaction names the one the preview
    matched (not_a_duplicate_of) and is freed only from that one: it still
    takes it, so an identical row beside it is checked as in the preview,
    and is checked again against the rest of the ledger, so a repeated
    add_transactions doesn't save it twice. The same amount within 48 hours
    with anything else different, or a BTC move of a near amount =>
    possible_duplicate: written unless removed, the warning naming the
    match and what differs. exact_only (execute's double-submit guard)
    looks for duplicates only.
    """
    valid = [p for p in prepared if p.tx_data is not None]
    if not valid:
        return
    stubs = [_stub(p) for p in valid]
    annotate_duplicates(stubs, db, exact_only=True, rule=ENTRY_RULE)
    _match_the_most(stubs, db)
    if not exact_only:
        matched = {stub.matched_tx_id for stub in stubs if stub.status == STATUS_MATCHED}
        unmatched = [stub for stub in stubs if stub.status == STATUS_NEW]
        annotate_duplicates(unmatched, db, rule=ENTRY_RULE, reserved_tx_ids=matched)  # the similar ones
    _check_overrides_again(valid, stubs, db)
    again = _named_duplicates(valid, stubs, db)
    for i, (p, stub) in enumerate(zip(valid, stubs)):
        if stub.status == STATUS_NEW:
            continue
        p.result.matched_transaction_id = stub.matched_tx_id
        if stub.status == STATUS_MATCHED:
            p.result.status = STATUS_DUPLICATE
            p.result.warnings.append(_duplicate_warning(p, stub.matched_tx_id, i in again))
        else:
            p.result.status = STATUS_POSSIBLE_DUPLICATE
            p.result.warnings.append(f"{stub.discrepancy}. Saved unless you remove it.")


def _match_the_most(stubs: list[RiverProposal], db: Session) -> None:
    """Each row the duplicates pass left new matched after all when a
    duplicate of it can be freed (match_by_moving): the pass gives each row
    its nearest duplicate, the timed rows first (#472), and a row matching
    more copies than another can still have taken that one's only copy
    (#411). The names rows give (not_a_duplicate_of) count for nothing here,
    so the answer is the one the AI's preview without them gave."""
    stuck = [stub for stub in stubs if stub.status == STATUS_NEW]
    holders = [stub for stub in stubs if stub.status == STATUS_MATCHED]
    match_by_moving(stuck, holders, db, ENTRY_RULE, kept_tx_ids=())


def _check_overrides_again(valid: list[PreparedRow], stubs: list[RiverProposal], db: Session) -> None:
    """Each row that matched the transaction it says it isn't
    (not_a_duplicate_of), checked again without the transactions the rows
    matched: it's new unless the ledger holds another copy (the one an
    earlier add_transactions saved), whichever row beside it holds that
    copy, if that row has another duplicate of its own (match_by_moving). A
    row that matched another copy is that copy: an identical row beside it
    took the one it names, so a request sent again saves nothing more
    (#378)."""
    taken = {stub.matched_tx_id for stub in stubs if stub.status == STATUS_MATCHED}
    again = {
        i: _stub(p) for i, (p, stub) in enumerate(zip(valid, stubs))
        if stub.status == STATUS_MATCHED and stub.matched_tx_id == p.not_a_duplicate_of
    }
    annotate_duplicates(list(again.values()), db, exact_only=True, rule=ENTRY_RULE, reserved_tx_ids=taken)
    # No row is moved onto a transaction any row names
    names = {p.not_a_duplicate_of for p in valid if p.not_a_duplicate_of is not None}
    for i, stub in again.items():
        stubs[i] = stub
    # Another row may hold the copy one of these needs, and have another of its own
    stuck = [stub for stub in again.values() if stub.status == STATUS_NEW]
    holders = [stub for stub in stubs if stub.status == STATUS_MATCHED]
    match_by_moving(stuck, holders, db, ENTRY_RULE, kept_tx_ids=names)


def _named_duplicates(valid: list[PreparedRow], stubs: list[RiverProposal], db: Session) -> set[int]:
    """The rows left out whose not_a_duplicate_of names a duplicate of
    theirs: each is recorded again (the same request sent twice). A row
    naming anything else names it in error, and is left out as any other."""
    named = {
        i: p.not_a_duplicate_of for i, (p, stub) in enumerate(zip(valid, stubs))
        if p.not_a_duplicate_of is not None and stub.status == STATUS_MATCHED
    }
    if not named:
        return set()
    txs = {tx.id: tx for tx in db.query(Transaction).filter(Transaction.id.in_(set(named.values())))}
    tz = get_tax_timezone(db) if any(valid[i].day for i in named) else timezone.utc
    return {i for i, tx_id in named.items() if tx_id in txs and is_duplicate(stubs[i], txs[tx_id], ENTRY_RULE, tz)}


def _duplicate_warning(p: PreparedRow, tx_id: int, again: bool) -> str:
    if again:
        return (f"Recorded again as tx #{tx_id}, besides tx #{p.not_a_duplicate_of} the user said it isn't (the "
                f"same request sent twice?): left out.")
    warning = (f"Already recorded as tx #{tx_id} (the same type, BTC amount, source or purpose, a Buy's cost "
               f"basis, and time): left out. If the user says it's another transaction, send it with "
               f"not_a_duplicate_of: {tx_id}.")
    if p.not_a_duplicate_of is not None:
        warning += f" (not_a_duplicate_of names tx #{p.not_a_duplicate_of}, which isn't a duplicate of this row.)"
    return warning


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
    (later rows depend on it for FIFO and are marked not_simulated). A
    price a row needs once earlier rows are written is looked for with the
    lock free, and the dry run made again (hourly_prices.with_prices_found,
    #426).
    """
    ordered = _chronological(prepared)
    if not ordered:
        return [], []

    # The year files the price lookups below (from_price) may read, read
    # first: the dry run holds SQLite's write lock, and reading and
    # fingerprinting them would hold it the longer (#204). Looked up after
    # the rollback instead, a price the dry run itself stored would be gone.
    years: dict = {}
    hourly_prices.read_year_files((p.tx_data["timestamp"] for p in ordered), years)

    # May commit (only if the fee account is missing) — do it before the dry run.
    ensure_fee_account_exists(db)
    return hourly_prices.with_prices_found(db, lambda: _dry_run(ordered, db, years))


def _dry_run(
    ordered: list[PreparedRow], db: Session, years: dict
) -> tuple[list[AffectedTransaction], list[AccountBalance]]:
    find_prices_first(db, [p.tx_data for p in ordered])  # before the first row is written (#426)
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
                gross_proceeds_usd=tx.gross_proceeds_usd,
                fmv_usd=tx.fmv_usd,
                fee_usd=tx.fee_usd if (tx.fee_currency or "").upper() == "BTC" else None,
                from_price=from_price(tx, db, years),
            )
        if failed_at is not None:
            return [], []
        return _affected(before, db), _balances(db)
    finally:
        db.rollback()


def from_price(tx: Transaction, db: Session, years: dict | None = None) -> FromPrice | None:
    """
    Which of a saved (or simulated) transaction's values BitcoinTX filled in
    from a price (transaction.values_from_price), and that price
    (transaction.price_used, which reads the stored one and asks nobody), for
    the AI connector (#208): its preview and add answers say which hour and
    source each came from. None when every value was given.
    """
    values = values_from_price(tx)
    return FromPrice(values=values, **(price_used(tx, db, years) or {})) if values else None


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
        except price_history.PriceNeeded:  # the dry run is made again once it's found (simulate)
            raise
        except Exception as exc:  # defensive: surface, never write
            if not is_busy(exc):
                log_unexpected(f"Entry simulation of row {p.row}", exc, logger)
            _reject(p, SIMULATION_BUSY if is_busy(exc) else SIMULATION_FAILED)
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
    # A price a row needs once earlier rows are written is looked for with
    # the lock free, and the rows written again (#426)
    created = hourly_prices.with_prices_found(db, lambda: _write_in_order(ordered, db))
    for _p, tx in created:
        db.refresh(tx)
    return created


def _write_in_order(ordered: list[PreparedRow], db: Session) -> list[tuple[PreparedRow, Transaction]]:
    find_prices_first(db, [p.tx_data for p in ordered])  # before the first row is written (#426)
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
    return created
