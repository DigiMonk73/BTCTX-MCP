"""
Ledger Review's check of values priced at the day (#144). Before hourly
prices, every value BitcoinTX filled in itself (an income or rebate
deposit's basis, a Spent's proceeds, a BTC fee's value; from #255 also a
gift's, donation's or lost coins' value) came from the day's
00:00 UTC price; those transactions are marked price_moment "day". An
inheritance is left out: its value is the date of death's day price by rule
(#173), not one the hour would make closer. hourly_changes() lists the ones the price of their hour would
change; nothing changes until the owner applies them (apply_hourly_prices,
login only): a backup copy first, then each picked transaction's priced
values at its hour's price, marked "hour", and a recalculation. Typed
values are never listed or touched. The apply takes the write lock right
after the copy and works each change out again from the transaction as it
is then, so an edit made while it runs keeps its own amount (#387).

Where there's no hourly price (before 2013, or none here: an own mempool
server without the public fallback, before its record), a value is
compared with the day's price instead and set to it: what the old "fee
values off" check did (F14), now for every priced value.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.constants import BTC_ACCOUNTS, GIFT_LIKE_PURPOSES, INHERITED_SOURCE, VALUED_AT_RECEIPT, normalized
from backend.migrate import REVIEW_COPIES_KEPT, backup_sqlite, sqlite_file
from backend.models.transaction import Transaction
from backend.services import hourly_prices, price_history
from backend.services.tax_time import get_tax_timezone, local_date

CENT = Decimal("0.01")


def hourly_changes(db: Session, ids=None, year: int | None = None, wait: bool = False) -> list[dict[str, Any]]:
    """
    Transactions priced at the day whose priced values the price of their
    hour (else their day's) would change, in date order: {id, tax_year,
    moment, at, price, values: {field: (old, new)}}. ids or year: only
    those. wait: for a year's hourly prices still downloading (the CLI);
    else such a year is compared with the day's price meanwhile.
    """
    return _changes(db, ids, year, lambda t: _price_of(db, t.timestamp, wait))


def _changes(db: Session, ids, year: int | None, price_of) -> list[dict[str, Any]]:
    """hourly_changes(), each transaction priced by price_of(t): (price, moment) or None."""
    tz = get_tax_timezone(db)
    q = db.query(Transaction).filter(Transaction.price_moment == "day")
    if ids is not None:
        q = q.filter(Transaction.id.in_(list(ids)))
    changes = []
    for t in q.order_by(Transaction.timestamp, Transaction.id).all():
        if normalized(t.source) == INHERITED_SOURCE:
            continue  # valued at the date of death's day by rule
        tax_year = local_date(t.timestamp, tz).year
        if year is not None and tax_year != year:
            continue
        priced = price_of(t)
        change = _change_for(t, *priced) if priced is not None else None
        if change is not None:
            changes.append({"id": t.id, "tax_year": tax_year, **change})
    return changes


def apply_hourly_prices(db: Session, ids=None, year: int | None = None, wait: bool = False) -> dict[str, Any]:
    """
    Price the picked transactions' day-priced values at their hour (where
    there's none, the day's), after a backup copy of the database, and
    recalculate. Typed values never change. Commits (rolls back when an
    edit or a delete made meanwhile left nothing to apply).
    """
    from backend.services.transaction import recalculate_all_transactions

    listed = hourly_changes(db, ids=ids, year=year, wait=wait)
    if not listed:
        return {"changed": [], "backup": None}
    path = sqlite_file(db.get_bind())
    backup = backup_sqlite(path, "hourly-prices", kind="review", keep=REVIEW_COPIES_KEPT) if path is not None else None
    _hold_write_lock(db)
    # Each listed transaction as it is now (#387): one deleted meanwhile is
    # gone, one edited is worked out again from its own amount, at the price
    # the check found for its hour. Found as the check found them (a year's
    # ids in one IN (...) could pass SQLite's limit), the listed ones kept.
    db.expire_all()
    seen = {c["id"]: c for c in listed}
    changes = _changes(db, ids, year, lambda t: _price_seen(db, t, seen[t.id]) if t.id in seen else None)
    if not changes:  # each one deleted or edited meanwhile: nothing left to apply
        db.rollback()  # the lock goes
        return {"changed": [], "backup": backup.name if backup else None}
    for change in changes:
        t = db.get(Transaction, change["id"])
        for field, (_old, new) in change["values"].items():
            setattr(t, field, new)
            if field == "gross_proceeds_usd":
                t.proceeds_usd = new  # recalculation nets the fee off the gross
        t.price_moment = change["moment"]
    recalculate_all_transactions(db)
    db.commit()
    return {"changed": changes, "backup": backup.name if backup else None}


def _hold_write_lock(db: Session) -> None:
    """SQLite's write lock until the apply ends: an edit made from now on
    waits until after it (5 s at most, then fails). While another save holds
    the lock longer, nothing is applied (503)."""
    try:
        db.execute(text("BEGIN IMMEDIATE"))
    except OperationalError as e:
        if "locked" not in str(e.orig):  # SQLITE_BUSY's "database is locked"
            raise
        raise HTTPException(
            status_code=503, detail="Not applied: BitcoinTX was busy saving something else. Try again."
        ) from e


def _price_seen(db: Session, t: Transaction, listed: dict[str, Any]) -> tuple[Decimal, str] | None:
    """The price the check found for t's hour (or day), unless an edit has
    moved t since: then the one stored for its new hour, else its day (the
    edit stored what it found). Never a request: the write lock is held."""
    if listed["at"] == _start(hourly_prices.hour_of(t.timestamp), listed["moment"]):
        return listed["price"], listed["moment"]
    for moment in ("hour", "day"):
        stored = hourly_prices.stored_price_at(db, t.timestamp, moment)
        if stored is not None:
            return stored.usd, moment
    return None


def _price_of(db: Session, moment, wait: bool) -> tuple[Decimal, str] | None:
    """(price, "hour") for the moment's hour, else (price, "day") for its day; None when there's none."""
    found = hourly_prices.hourly_price(db, moment, wait=wait)
    if found is not None:
        return found[0], "hour"
    try:
        return price_history.daily_price(db, moment), "day"
    except HTTPException:  # no price at all: nothing to compare
        return None


def _change_for(t: Transaction, price: Decimal, at: str) -> dict[str, Any] | None:
    """What pricing a transaction's priced values at `price` (its hour's or day's) would change, or None."""
    values = {}
    for field, old, quantity in _priced_values(t):
        new = (price * quantity).quantize(CENT)
        if new != Decimal(old).quantize(CENT):
            values[field] = (Decimal(old).quantize(CENT), new)
    if not values:
        return None
    return {"moment": at, "price": price, "at": _start(hourly_prices.hour_of(t.timestamp), at), "values": values}


def _start(hour: int, moment: str) -> int:
    """When the price used began, in Unix seconds: the hour's start, or its UTC day's."""
    return hour if moment == "hour" else hour // 86400 * 86400


def _priced_values(t: Transaction):
    """(field, stored value, BTC it values) for each value that came from a price."""
    if t.cost_basis_from_price and t.cost_basis_usd is not None and t.type == "Deposit" \
            and t.to_account_id in BTC_ACCOUNTS and normalized(t.source) in VALUED_AT_RECEIPT:
        yield "cost_basis_usd", t.cost_basis_usd, Decimal(t.amount)
    if t.proceeds_from_price and t.gross_proceeds_usd is not None and t.type == "Withdrawal" \
            and normalized(t.purpose) == "spent":
        yield "gross_proceeds_usd", t.gross_proceeds_usd, Decimal(t.amount)
    if t.fmv_from_price and t.fmv_usd is not None and t.type == "Withdrawal" \
            and normalized(t.purpose) in GIFT_LIKE_PURPOSES:
        yield "fmv_usd", t.fmv_usd, Decimal(t.amount)
    if t.fee_usd is not None and not t.fee_usd_manual and (t.fee_currency or "").upper() == "BTC" \
            and Decimal(t.fee_amount or 0) > 0:
        yield "fee_usd", t.fee_usd, Decimal(t.fee_amount)
