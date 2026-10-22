"""The dry run before a save that changes an earlier tax year (5.8).

An add, an edit or a delete is applied on a scratch copy. When that moves
the figures of a year before this one, the save raises PastYearsChange and
nothing is written until the same request comes back with that answer's
fingerprint.
"""

from dataclasses import dataclass, field

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.database import scratch_copy
from backend.models.transaction import Transaction
from backend.services import recalculated, tax_time, year_changes
from backend.services import transaction as tx_service
from backend.services.past_years import PastYearsChange, warning


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


def save(write: Write, db: Session, confirm: str | None, ai: bool):
    """Save the write, or raise the 409 when it changes an earlier year and
    confirm isn't that answer's fingerprint. A matching fingerprint is
    checked again, then saved."""
    asked = check(write, db, ai)
    if asked is not None and confirm != asked.body["confirm"]:
        raise asked
    return _plain(write, db)


def _plain(write: Write, db: Session):
    """The route's save, which commits, on the request's own data."""
    data = dict(write.data)
    if write.kind == "add":
        return tx_service.create_transaction_record(data, db)
    if write.kind == "edit":
        return tx_service.update_transaction_record(write.tx_id, data, db)
    return tx_service.delete_transaction_record(write.tx_id, db)
