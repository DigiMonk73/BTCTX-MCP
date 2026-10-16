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
values are never listed or touched.

Where there's no hourly price (before 2013, or none here: an own mempool
server without the public fallback, before its record), a value is
compared with the day's price instead and set to it: what the old "fee
values off" check did (F14), now for every priced value.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import HTTPException
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
        if wait:
            db.commit()  # prices stored so far: no write lock held while a lookup waits for a download
        change = _change_for(db, t, wait)
        if change is not None:
            changes.append({"id": t.id, "tax_year": tax_year, **change})
    return changes


def apply_hourly_prices(db: Session, ids=None, year: int | None = None, wait: bool = False) -> dict[str, Any]:
    """
    Price the picked transactions' day-priced values at their hour (where
    there's none, the day's), after a backup copy of the database, and
    recalculate. Typed values never change. Commits.
    """
    from backend.services.transaction import recalculate_all_transactions

    changes = hourly_changes(db, ids=ids, year=year, wait=wait)
    db.commit()  # prices downloaded meanwhile; the copy is of the ledger as it is
    if not changes:
        return {"changed": [], "backup": None}
    path = sqlite_file(db.get_bind())
    backup = backup_sqlite(path, "hourly-prices", kind="review", keep=REVIEW_COPIES_KEPT) if path is not None else None
    applied = []
    for change in changes:
        t = db.get(Transaction, change["id"])
        if t is None:  # deleted while the copy was made: nothing left to price
            continue
        applied.append(change)
        for field, (_old, new) in change["values"].items():
            setattr(t, field, new)
            if field == "gross_proceeds_usd":
                t.proceeds_usd = new  # recalculation nets the fee off the gross
        t.price_moment = change["moment"]
    recalculate_all_transactions(db)
    db.commit()
    return {"changed": applied, "backup": backup.name if backup else None}


def _change_for(db: Session, t: Transaction, wait: bool) -> dict[str, Any] | None:
    """What pricing a transaction's priced values at their hour would change, or None."""
    moment = t.timestamp
    found = hourly_prices.hourly_price(db, moment, wait=wait)
    if found is not None:
        price, at = found[0], "hour"
    else:
        try:
            price, at = price_history.daily_price(db, moment), "day"
        except HTTPException:  # no price at all: nothing to compare
            return None
    values = {}
    for field, old, quantity in _priced_values(t):
        new = (price * quantity).quantize(CENT)
        if new != Decimal(old).quantize(CENT):
            values[field] = (Decimal(old).quantize(CENT), new)
    if not values:
        return None
    hour = hourly_prices.hour_of(moment)
    return {"moment": at, "price": price, "at": hour if at == "hour" else hour // 86400 * 86400,
            "values": values}


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
