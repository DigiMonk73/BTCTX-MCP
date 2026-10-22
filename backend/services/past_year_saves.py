"""The past-year warning's save (5.8).

An add, an edit or a delete is applied on a scratch copy. When that moves
the figures of a year before this one, the save raises PastYearsChange and
nothing is written until the same request comes back with that answer's
fingerprint. That confirmed save takes the write lock, copies the ledger
as it was, and commits only while the fingerprint still matches.
"""

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.database import scratch_copy, take_write_lock
from backend.migrate import (
    AI_CHANGE_LABEL,
    AI_COPIES_KEPT,
    PRE_CHANGE_COPIES_KEPT,
    PRE_CHANGE_KIND,
    PRE_CHANGE_LABEL,
    backup_sqlite,
    sqlite_file,
)
from backend.models.transaction import Transaction
from backend.services import hourly_prices, recalculated, tax_time, year_changes
from backend.services import transaction as tx_service
from backend.services.past_years import PastYearsChange, warning

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Write:
    kind: str                 # "add" | "edit" | "delete"
    tx_id: int | None = None
    data: dict = field(default_factory=dict)

    def parts(self) -> dict:  # {"kind", "tx_id", "data"}: what the fingerprint takes
        return {"kind": self.kind, "tx_id": self.tx_id, "data": self.data}


def run(write: Write, db: Session):
    """The write on db, uncommitted. apply_update completes its dict in
    place, so the fingerprint keeps the request's own data."""
    data = dict(write.data)
    if write.kind == "add":
        return tx_service.apply_create(data, db)
    if write.kind == "edit":
        return tx_service.apply_update(write.tx_id, data, db)
    return tx_service.apply_delete(write.tx_id, db)


def appends(write: Write, db: Session) -> bool:
    """An add dated at or after every stored row, compared in UTC.

    It replays nothing and applies nothing pending, on an empty ledger too.
    """
    if write.kind != "add":
        return False
    when = tax_time.as_utc(write.data["timestamp"])
    latest = db.query(Transaction).order_by(Transaction.timestamp.desc()).first()
    return latest is None or when >= tax_time.as_utc(latest.timestamp)


def earliest_year(write: Write, db: Session, tz) -> int:
    """The earliest tax year this write can move: the add's, or the stored
    row's and the year an edit sends it to."""
    if write.kind == "add":
        return tax_time.local_date(write.data["timestamp"], tz).year
    stored = tax_time.local_date(db.get(Transaction, write.tx_id).timestamp, tz).year
    sent = write.data.get("timestamp")
    if sent is None:
        return stored
    return min(stored, tax_time.local_date(sent, tz).year)


def needs_no_dry_run(write: Write, db: Session) -> bool:
    """The two shortcuts (5.8). An add after every row, dated this tax year
    or later, skips the dry run and never reads recalculated_by. Any other
    write dated this year or later skips it only while that stamp is current."""
    tz = tax_time.get_tax_timezone(db)
    this_year = tax_time.current_tax_year(tz)
    if write.kind == "add" and appends(write, db):
        return earliest_year(write, db, tz) >= this_year
    return earliest_year(write, db, tz) >= this_year and recalculated.is_current(db)


def check(write: Write, db: Session, ai: bool) -> PastYearsChange | None:
    """None when the write can't change an earlier year. Otherwise the 409
    from a dry run, which leaves the live ledger as it was. A with pass that
    fails raises the save's own HTTPException."""
    if needs_no_dry_run(write, db):
        return None
    if write.kind == "add":
        # With the lock free: a price found only on the scratch copy would be
        # lost with it, and asked for again by the confirmed save
        tx_service.find_prices_first(db, [dict(write.data)])
    with scratch_copy(db) as scratch:
        asked, _ = measured(write, scratch, db, ai)
    return asked


def measured(write: Write, db: Session, live: Session, ai: bool) -> tuple[PastYearsChange | None, object]:
    """What the write changes on `db`, judged from `live`: None when no
    earlier year moves, else the 409. Pending fixes count as earlier years
    only for the AI key ("Don't warn for fixes" with a login)."""
    tz = tax_time.get_tax_timezone(live)
    this_year = tax_time.current_tax_year(tz)
    adds = appends(write, live)
    stored = year_changes.figures(db, tz)
    rows = year_changes.listed(db, tz)
    without, recalc_error = stored, None
    # A replay of its own, and only when this write is not itself an append
    # and the live stamp is stale: its 400 leaves the stored figures.
    if not adds and not recalculated.is_current(live):
        without, recalc_error = _recalculated(live, tz, stored)
    result = run(write, db)
    db.flush()
    after = year_changes.figures(db, tz)
    rows = year_changes.listed(db, tz) | rows  # the deleted rows as they were, the added ones
    changes = year_changes.earlier_year_items(
        rows, year_changes.moved(without, after), without, after, this_year)
    pending = year_changes.earlier_year_items(
        rows, year_changes.moved(stored, without), stored, without, this_year)
    earlier = {year for item in changes for year in item["years"] if year < this_year}
    if ai:
        earlier.update(year for item in pending for year in item["years"] if year < this_year)
    years = sorted(earlier)
    if not years:
        return None, result
    return warning(
        years, changes, pending, write.parts(), adds=adds, recalc_error=recalc_error), result


def _recalculated(live: Session, tz, stored: dict) -> tuple[dict, str | None]:
    """The figures a recalculation alone would leave, on a scratch copy of
    the live ledger. A 400 (a row naming a missing account) keeps the stored
    figures and that message: the write may be what repairs it."""
    try:
        with scratch_copy(live) as scratch:
            tx_service.recalculate_all_transactions(scratch)
            scratch.flush()
            replayed = year_changes.figures(scratch, tz)
    except HTTPException as error:
        if error.status_code != 400:
            raise
        return stored, error.detail
    return replayed, None


# How each write says it saved nothing, as its route says it
NOT_SAVED = {"add": "Not added", "edit": "Not changed", "delete": "Not deleted"}


def save(write: Write, db: Session, confirm: str | None, ai: bool):
    """Save the write. Sent with confirm, it always takes the confirmed
    path (the lock, a copy, the comparison again), even when that then
    finds nothing earlier to ask about: a confirm can't be sent blind.
    Without one, the dry run's 409, or the save."""
    if confirm is not None:
        # No price is asked for under the lock (#442): one the write still
        # needs rolls it back, is found with the lock free, and it runs again
        return hourly_prices.with_prices_found(db, lambda: _confirmed(write, db, confirm, ai))
    asked = check(write, db, ai)
    if asked is not None:
        raise asked
    return _plain(write, db)


def _confirmed(write: Write, db: Session, confirm: str, ai: bool):
    """The write and its comparison again, under the write lock and after
    a copy of the ledger as it was. Commits only while confirm is still
    that comparison's fingerprint: the owner saves what they were shown."""
    if not take_write_lock(db):
        raise HTTPException(
            status_code=503,
            detail=f"{NOT_SAVED[write.kind]}: BitcoinTX was busy saving something else. Try again.",
        )
    copy = _copy_first(write, db, ai)
    try:
        asked, result = measured(write, db, db, ai)
    except BaseException:
        if copy is not None:
            copy.unlink(missing_ok=True)  # a price it needs, or the save's own refusal: nothing saved, so no copy
        raise
    if asked is not None and asked.body["confirm"] != confirm:
        db.rollback()
        raise asked
    db.commit()
    if isinstance(result, Transaction):
        db.refresh(result)
    return result


def _copy_first(write: Write, db: Session, ai: bool) -> Path | None:
    """The ledger as it was, before the confirmed write: a pre-change copy
    with a login, a fresh AI copy with the AI key. None when there is no
    file to copy. A copy that fails saves nothing."""
    db_path = sqlite_file(db.get_bind())
    if db_path is None:
        return None
    try:
        if ai:
            return backup_sqlite(db_path, AI_CHANGE_LABEL, kind="ai", keep=AI_COPIES_KEPT)
        return backup_sqlite(db_path, PRE_CHANGE_LABEL, kind=PRE_CHANGE_KIND, keep=PRE_CHANGE_COPIES_KEPT)
    except (OSError, sqlite3.Error) as e:
        db.rollback()
        logger.error("No copy before a confirmed save (%s): nothing saved", type(e).__name__)
        raise HTTPException(
            status_code=500,
            detail=f"{NOT_SAVED[write.kind]}: BitcoinTX couldn't make its copy of the database first.",
        ) from e


def _plain(write: Write, db: Session):
    """The route's save, which commits, on the request's own data."""
    data = dict(write.data)
    if write.kind == "add":
        return tx_service.create_transaction_record(data, db)
    if write.kind == "edit":
        return tx_service.update_transaction_record(write.tx_id, data, db)
    return tx_service.delete_transaction_record(write.tx_id, db)
