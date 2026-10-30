"""
The past-year warning (2.0 spec 5.8; the owner's Q4, widened on
2026-10-15): a write that would change the figures of a tax year before this
one (its gains, Form 8949 boxes, the dates a return prints, income and
rebates, gifts, donations and lost coins) is saved only once confirmed,
after a copy of the database. Adds, edits and deletes are the Write here;
the imports, the tax timezone, an exchange's 1099-DA switch and the AI's
Recalculate Ledger are writes of their own (services/past_year_writes.py),
through the same save.

Unconfirmed, the write is worked out on a scratch copy with the lock free
(the dry run): when nothing earlier moves it saves as it always has, else a
409 says which years and what moves, and gives a fingerprint. Sent again
with ?confirm=<fingerprint>, it's made under the write lock after a copy,
and committed only while what it changes still has that fingerprint. With a
login, changes a recalculation alone would make (rules fixed since a row was
saved) never ask: Recalculate Ledger is the owner's own way to apply them
("Don't warn for fixes", the owner, 2026-10-16). With the AI key, those in
an earlier year do. A dry run that runs past its time budget names the years
from the write's date on instead (the lead's decision, 2026-10-18).
"""

import hashlib
import json
import logging
import sqlite3
import time
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import scratch_copy, take_write_lock
from backend.migrate import (
    AI_CHANGE_LABEL,
    AI_COPIES_KEPT,
    PRE_CHANGE_COPIES_KEPT,
    PRE_CHANGE_KIND,
    backup_sqlite,
    prune_backups,
    sqlite_file,
)
from backend.models.transaction import Transaction
from backend.services import chosen_coins, hourly_prices, recalculated_by, review, tax_time, year_changes
from backend.services import transaction as tx_service
from backend.services.account import account_book

logger = logging.getLogger(__name__)

# How long the exact check may take before the warning names the years from
# the write's date instead (the lead's decision of 2026-10-18, 5 s by
# default). Set from the StartOS test VM's measurement (#352, 2026-10-24):
# one replay takes 4.7 s there at 1,000 rows and 17.6 s at 3,000, so 10 s
# gives the exact list up to about 1,800 rows on it (about half that the
# first time after an upgrade, two passes; about 6,000 on the M6 Mac mini),
# and the form waits about that long at most before asking (the copy and
# the comparisons run outside the replays it times, and so does looking
# first for a stored row's price: transaction.STORED_VALUES_SECONDS).
DRY_RUN_SECONDS = 10
ADD, EDIT, DELETE = "add", "edit", "delete"
COPY_LABEL = "past-year"
CONFIRM = "Confirm to save it: a copy of your ledger is made first."
CHANGES = "This changes the figures of {years}, which you may already have filed. " + CONFIRM
ADDS = "This adds to {years}, which you may already have filed. " + CONFIRM
BY_DATE = ("This is dated in {year}, so it can change {year}'s figures and later years you may have filed. "
           "Save it? A copy of your ledger is made first.")
BY_DATE_WITH_FIXES = ("This can change the figures of tax year {year} and later years you may have filed: "
                      "saving it also applies the rules fixed since they were saved. Save it? A copy of your "
                      "ledger is made first.")
TOO_SLOW = ("BitcoinTX couldn't work out exactly what changes quickly enough here, so it names every year this "
            "can reach.")
# Beside a write that adds or changes a choice of coins on a transaction
# dated in an earlier tax year (#711): what counts is when the owner
# decided, not when it's typed here (Treas. Reg. §1.1012-1(j)(2))
COINS_CHOSEN = "A choice of coins counts only if you made it by the time they left and your records show it."
BUSY = "Not saved: BitcoinTX was busy saving something else. Try again."
NO_COPY = "Not saved: BitcoinTX couldn't make its copy of the database first."
# What a session's replay is held by, carried onto the scratch copy its
# recalculation without the write runs on: the save's price lookups
# (hourly_prices.with_prices_found: none sent under the lock) and the dry
# run's time budget
CARRIED = (*hourly_prices.SAVE_KEYS, tx_service.DEADLINE)


class PastYearWrite:
    """
    What the warning asks of a write: how to make it uncommitted (`apply`,
    which both passes and the confirmed save take) and as it always saved
    (`save`), which tax years it can reach, and what its fingerprint takes
    of it (`parts`). The defaults are a write that replays the ledger and
    fills no value from a price.
    """
    kind = ""
    # What it changes is what a recalculation alone would (the AI's
    # Recalculate Ledger): listed as pending, with no recalculation without it
    pending_only = False
    changes_text, adds_text = CHANGES, ADDS
    by_date_text, by_date_with_fixes_text = BY_DATE, BY_DATE_WITH_FIXES

    def apply(self, db: Session) -> Any:
        """The write and what it recalculates, uncommitted."""
        raise NotImplementedError

    def save(self, db: Session) -> Any:
        """The write as it always saved: committed."""
        raise NotImplementedError

    def earliest_year(self, db: Session, tz) -> int | None:
        """The tax year of the earliest moment it can change; None when it
        can change nothing (it saves at once)."""
        raise NotImplementedError

    def parts(self) -> list:
        """What the fingerprint takes of it: the write as its request gives it."""
        raise NotImplementedError

    def this_year(self, tz) -> int:
        """This tax year: the years before it are the ones the warning asks about."""
        return tax_time.current_tax_year(tz)

    def appends(self, db: Session) -> bool:
        """Whether it only adds rows dated after every other: no replay."""
        return False

    def recalculates(self, db: Session) -> bool:
        """Whether its save replays the ledger, applying any pending change."""
        return not self.appends(db)

    def moves_no_figure(self, db: Session) -> bool:
        """Whether it can't move any tax year's figures, whatever its dates."""
        return False

    def priced_rows(self, db: Session) -> list[dict]:
        """The rows whose values it fills from a price, for transaction.find_prices_first."""
        return []

    def own_row(self) -> int | None:
        """The stored row it edits or deletes: what it leaves of that row's values is its own to price."""
        return None

    def gone_item(self, db: Session, tz) -> dict[int, dict]:
        """The rows it deletes, as Ledger Review lists them, taken before they go."""
        return {}

    def coins_chosen(self, db: Session, tz) -> str | None:
        """The warning's line about a choice of coins it makes (COINS_CHOSEN),
        or None; asked before it's made."""
        return None

    def check_there(self, db: Session) -> None:
        """Under the confirmed save's lock: what it changes is still there."""


@dataclass(frozen=True)
class Write(PastYearWrite):
    """
    An add, an edit or a delete as its request gives it: `data` holds the
    new row's or the edit's fields (none for a delete), never completed in
    place, so each pass and the fingerprint take it as given.
    """
    kind: str
    data: dict = field(default_factory=dict)
    tx_id: int | None = None

    def apply(self, db: Session):
        """The write and its recalculation, uncommitted, on its own copy of the data."""
        data = dict(self.data)
        if self.kind == ADD:
            return tx_service.apply_create(data, db)
        if self.kind == EDIT:
            return tx_service.apply_update(self.tx_id, data, db)
        return tx_service.apply_delete(self.tx_id, db)

    def save(self, db: Session):
        """The write as it always saved: committed."""
        data = dict(self.data)
        if self.kind == ADD:
            return tx_service.create_transaction_record(data, db)
        if self.kind == EDIT:
            return tx_service.update_transaction_record(self.tx_id, data, db)
        return tx_service.delete_transaction_record(self.tx_id, db)

    def earliest_year(self, db: Session, tz) -> int | None:
        """The tax year of the earliest moment it can change (the replay runs
        in time order): the add's date, an edit's or a delete's row's date
        before and after. None when a date is out of range, or the row is gone:
        the save refuses it, or answers 404."""
        row = db.get(Transaction, self.tx_id) if self.kind != ADD else None
        moments = [row.timestamp] if row is not None else []
        if self.kind == ADD or (moments and self.data.get("timestamp") is not None):
            moments.append(self.data.get("timestamp") or datetime.now(timezone.utc))
        try:
            return min((tax_time.local_date(when, tz).year for when in moments), default=None)
        except tax_time.DateOutOfRange:
            return None

    def moves_no_figure(self, db: Session) -> bool:
        """Neither the row as stored nor as the write leaves it is a bitcoin
        one (a Buy, a Sell, or a bitcoin account on a side): it moves no
        figure of any year, and with a login nothing pending asks."""
        book = account_book(db)
        stored = db.get(Transaction, self.tx_id) if self.kind != ADD else None
        rows = [(stored.type, (stored.from_account_id, stored.to_account_id))] if stored is not None else []
        if self.kind != DELETE:
            def sent(key):
                return self.data.get(key, getattr(stored, key, None))
            rows.append((sent("type"), (sent("from_account_id"), sent("to_account_id"))))
        return bool(rows) and all(year_changes.moves_only_dollars(kind, sides, book) for kind, sides in rows)

    def appends(self, db: Session) -> bool:
        """An add dated at or after every row: it replays nothing, and so
        applies no pending change (transaction._is_backdated). One choosing
        coins while a lot doesn't know its acquisition replays the whole
        ledger first (#711)."""
        if self.kind != ADD:
            return False
        if chosen_coins.replays_first([self.data], db):
            return False
        latest = db.query(func.max(Transaction.timestamp)).scalar()
        when = self.data.get("timestamp") or datetime.now(timezone.utc)
        return latest is None or tax_time.as_utc(when) >= tax_time.as_utc(latest)

    def priced_rows(self, db: Session) -> list[dict]:
        """The rows whose values the write fills from a price, for
        transaction.find_prices_first."""
        if self.kind == ADD:
            return [dict(self.data)]
        if self.kind == EDIT:
            return [tx_service.edited_inputs(db.get(Transaction, self.tx_id), self.data, db)]
        return []

    def own_row(self) -> int | None:
        return None if self.kind == ADD else self.tx_id

    def gone_item(self, db: Session, tz) -> dict[int, dict]:
        """A delete's row as Ledger Review lists it, taken before it goes;
        none for a row already gone (its save answers 404)."""
        row = db.get(Transaction, self.tx_id) if self.kind == DELETE else None
        return {} if row is None else {self.tx_id: review.row_item(row, tz, account_book(db), "", "")}

    def coins_chosen(self, db: Session, tz) -> str | None:
        """COINS_CHOSEN when it adds or changes a choice of coins on a
        transaction dated in an earlier tax year: never for oldest first,
        the IRS's default, nor a choice sent back as it's stored. Asked
        before the write is made, so the dry run and the confirmed save ask
        the same."""
        if self.kind == DELETE or not self.data.get("chosen_coins"):
            return None
        stored = db.get(Transaction, self.tx_id) if self.kind == EDIT else None
        sent = {line["acquired_txn_id"]: Decimal(str(line["btc"])) for line in self.data["chosen_coins"]}
        if stored is not None and chosen_coins.saved_choice(stored) == sent:
            return None
        when = self.data.get("timestamp") or getattr(stored, "timestamp", None)
        try:
            earlier = when is not None and tax_time.local_date(when, tz).year < self.this_year(tz)
        except tax_time.DateOutOfRange:
            return None  # the save refuses the date
        return COINS_CHOSEN if earlier else None

    def parts(self) -> list:
        return [self.kind, self.tx_id, self.data]

    def check_there(self, db: Session) -> None:
        if self.kind != ADD and db.get(Transaction, self.tx_id) is None:
            raise HTTPException(status_code=404, detail="Transaction not found.")  # deleted meanwhile


def save(write: PastYearWrite, db: Session, confirm: str | None, by_ai: bool,
         before_saving: Callable[[], None] = lambda: None):
    """
    The write, through the warning: what its save returns, or the 409 (a
    JSONResponse). `before_saving` runs before a save made as it always was
    (the AI's hourly copy, made before its changes).
    """
    tz = tax_time.get_tax_timezone(db)
    this_year = write.this_year(tz)
    if not _saves_at_once(write, db, by_ai, tz, this_year):
        if confirm is not None:
            return _save_confirmed(write, db, confirm, by_ai)
        warning = _dry_run(write, db, by_ai, tz, this_year)
        if warning is not None:
            return JSONResponse(status_code=409, content=warning)
    before_saving()
    return write.save(db)


def warning(write: PastYearWrite, db: Session, by_ai: bool) -> dict | None:
    """The 409's body the write gets as the ledger is now, or None when it
    saves at once: what a preview shows before the write is sent (the AI's
    import). Its fingerprint confirms the write."""
    tz = tax_time.get_tax_timezone(db)
    this_year = write.this_year(tz)
    return None if _saves_at_once(write, db, by_ai, tz, this_year) else _dry_run(write, db, by_ai, tz, this_year)


def years_dated_before(db: Session, moments) -> list[int]:
    """The tax years before this one (tax timezone) that these moments are
    in: a write dated there can change those years' figures."""
    tz = tax_time.get_tax_timezone(db)
    this_year = tax_time.current_tax_year(tz)
    return sorted({year for year in (tax_time.local_date(when, tz).year for when in moments) if year < this_year})


def _saves_at_once(write: PastYearWrite, db: Session, by_ai: bool, tz, this_year: int) -> bool:
    """Nothing earlier can move: no dry run. Its earliest moment is this
    tax year or later, or it moves no figure, while nothing can be pending
    that its save would apply (with the AI key, a pending change asks)."""
    earliest = write.earliest_year(db, tz)
    nothing_pending = not by_ai or not write.recalculates(db) or recalculated_by.matches(db)
    return earliest is None or (nothing_pending and (earliest >= this_year or write.moves_no_figure(db)))


@dataclass
class _Found:
    """What a write changes (year_changes.moved), what else its save applies
    (pending), the figures their words are read from, and the tax timezone
    after the write, which their dates are in."""
    changes: dict
    pending: dict
    recalc_error: str | None
    rows: dict
    gone: dict
    appended: bool
    tz: Any
    coins_chosen: str | None
    result: Any = None


def _dry_run(write: PastYearWrite, db: Session, by_ai: bool, tz, this_year: int) -> dict | None:
    """The 409's body, or None when nothing earlier moves: worked out on a
    scratch copy, with the lock free, within DRY_RUN_SECONDS."""
    # Kept in the live database: the confirm needs them
    tx_service.find_prices_first(db, write.priced_rows(db), _stored_hours(write, db))
    appended = write.appends(db)
    try:
        with scratch_copy(db) as scratch:
            scratch.info[tx_service.DEADLINE] = time.monotonic() + DRY_RUN_SECONDS
            found = _compare(write, scratch, tz, _needs_without(write, db), appended)
            return _warning(write, found, by_ai, this_year, scratch)
    except tx_service.OutOfTime:
        return _by_date(write, db, by_ai, tz, this_year)


def _stored_hours(write: PastYearWrite, db: Session) -> set:
    """The hours the dry run's replays ask for a stored row's missing value
    (#824), for transaction.find_prices_first: the row the write edits or
    deletes only if a recalculation without the write reads it as stored."""
    if not write.recalculates(db):
        return set()
    return tx_service.hours_a_replay_prices(db, None if _needs_without(write, db) else write.own_row())


def _needs_without(write: PastYearWrite, db: Session) -> bool:
    """Whether a recalculation without the write could change anything: not
    for a write that replays nothing (an add dated last, the 1099-DA
    switch: they apply nothing pending), nor for the AI's Recalculate
    Ledger (that recalculation is the write), nor while this BitcoinTX last
    recalculated the ledger (nothing is pending)."""
    return write.recalculates(db) and not write.pending_only and not recalculated_by.matches(db)


def _compare(write: PastYearWrite, db: Session, tz, needs_without: bool, appended: bool) -> _Found:
    """
    What the write changes on `db`, which holds the stored ledger: the write
    and its own recalculation, then, when one could change anything (a
    pending change), a recalculation without it on a copy taken first. The
    dry run and the confirmed save both take this one path, so they give
    one fingerprint; the write goes first, so a refusal of its own answers
    as its save would before the time budget can run out on the other. A
    without pass that fails (a ledger the replay can't pass as it is) is
    compared no further: the write is compared with the stored figures, or
    the edit that repairs such a ledger could never be saved. Each pass
    reads its dates in its own tax timezone: the write's own after it (a
    new tax timezone moves holding periods and tax years).
    """
    stored = year_changes.figures(db, tz)
    gone = write.gone_item(db, tz)
    coins_line = write.coins_chosen(db, tz)
    with scratch_copy(db) if needs_without else nullcontext() as without:
        result = write.apply(db)
        db.flush()
        tz_after = tax_time.get_tax_timezone(db)
        after = year_changes.figures(db, tz_after)
        if without is None:
            before, pending, recalc_error = stored, {}, None
        else:
            without.info.update({key: db.info[key] for key in CARRIED if key in db.info})
            before, pending, recalc_error = _without_pass(without, tz, stored)
    return _Found(year_changes.moved(before, after), pending, recalc_error, {**stored, **before, **after}, gone,
                  appended, tz_after, coins_line, result)


def _without_pass(db: Session, tz, stored: dict) -> tuple[dict, dict, str | None]:
    """The recalculation without the write, on a scratch copy of the stored
    ledger: (its figures, what it changes, why it failed)."""
    try:
        tx_service.recalculate_all_transactions(db)
        db.flush()
    except HTTPException as e:
        return stored, {}, e.detail
    before = year_changes.figures(db, tz)
    return before, year_changes.moved(stored, before), None


def _warning(write: PastYearWrite, found: _Found, by_ai: bool, this_year: int, db: Session) -> dict | None:
    """The 409's body, or None when nothing asks: with a login only the
    write's own changes to an earlier year, with the AI key also those its
    save applies (pending) there; the AI's Recalculate Ledger's changes are
    all pending."""
    changes = year_changes.reaching(found.changes, this_year)
    pending = year_changes.reaching(found.pending, this_year)
    if write.pending_only:
        changes, pending = {}, changes
    if not changes and not (by_ai and pending):
        return None
    book, tz = account_book(db), found.tz
    years = year_changes.years({**changes, **pending} if by_ai else changes)
    text = write.adds_text if found.appended else write.changes_text
    return _with_fingerprint(write, {
        "detail": text.format(years=_years_text(years)),
        "years": years,
        "changes": year_changes.items(changes, found.rows, db, tz, book, gone=found.gone),
        "pending": year_changes.items(pending, found.rows, db, tz, book, issue=year_changes.PENDING),
        "recalc_error": found.recalc_error,
        "exact": True,
        "why_not_exact": None,
        "timezone": tz.key,  # the one its rows' dates are in, which no device's clock need match (#737)
        **_coins_chosen(found.coins_chosen),
    })


def _by_date(write: PastYearWrite, db: Session, by_ai: bool, tz, this_year: int) -> dict | None:
    """The 409's body when the exact check took too long: every year from
    the write's date, or, with the AI key while a change a recalculation
    alone would make may be pending in any year, from the ledger's first."""
    start = own = write.earliest_year(db, tz)
    if start is None:  # a row gone meanwhile
        return None
    if by_ai and _needs_without(write, db):
        first = db.query(func.min(Transaction.timestamp)).scalar()
        start = min(start, tax_time.local_date(first, tz).year) if first is not None else start
    years = list(range(start, this_year))
    if not years:
        return None
    text = write.by_date_text if start == own else write.by_date_with_fixes_text
    return _with_fingerprint(write, {
        "detail": text.format(year=start),
        "years": years,
        "changes": [],
        "pending": [],
        "recalc_error": None,
        "exact": False,
        "why_not_exact": TOO_SLOW,
        "timezone": tz.key,
        **_coins_chosen(write.coins_chosen(db, tz)),
    })


def _coins_chosen(line: str | None) -> dict:
    """The 409's line about a choice of coins, only when it has one: every
    other 409, and its fingerprint, stays as it was."""
    return {"coins_chosen": line} if line else {}


def _with_fingerprint(write: PastYearWrite, body: dict) -> dict:
    """The body with its confirm: a SHA-256 of the write as given, of what
    it changes and of what its save applies, so a confirm can't be sent
    blind and holds only while they stay the same."""
    payload = json.dumps([write.parts(), body], sort_keys=True, default=str)
    return {**body, "confirm": hashlib.sha256(payload.encode()).hexdigest()}


def _years_text(years: list[int]) -> str:
    """ "tax year 2025", "tax years 2024 and 2025", "tax years 2023, 2024 and 2025"."""
    if len(years) == 1:
        return f"tax year {years[0]}"
    return f"tax years {', '.join(str(y) for y in years[:-1])} and {years[-1]}"


def _save_confirmed(write: PastYearWrite, db: Session, confirm: str, by_ai: bool):
    """The confirmed write, in hourly_prices.with_prices_found: no price is
    asked for under the lock (#442). A run rolled back for one removes its
    own copy, so one confirmed save leaves one copy."""
    return hourly_prices.with_prices_found(db, lambda: _confirmed(write, db, confirm, by_ai))


def _confirmed(write: PastYearWrite, db: Session, confirm: str, by_ai: bool):
    """
    Under the write lock: the copy, then the write, then its fingerprint
    worked out again as the dry run did (the date-based one first, which
    needs no replay). Committed only if it matches; otherwise rolled back,
    its copy removed, and the new 409.
    """
    if not take_write_lock(db):
        logger.warning("A confirmed past-year save: the database is busy, nothing saved")
        raise HTTPException(status_code=503, detail=BUSY)
    copy = None
    try:
        write.check_there(db)
        copy = _copy(db, by_ai)
        tz = tax_time.get_tax_timezone(db)
        this_year = write.this_year(tz)
        result, warning = _checked_write(write, db, confirm, by_ai, tz, this_year)
        if warning is not None and warning["confirm"] != confirm:
            raise _Stale(warning)
        db.commit()
    except BaseException as e:
        db.rollback()
        _remove(copy)
        if isinstance(e, _Stale):
            return JSONResponse(status_code=409, content=e.warning)
        raise
    _prune(db, copy, by_ai)
    return result


class _Stale(Exception):
    """The ledger changed since the 409: its new body."""

    def __init__(self, warning: dict):
        super().__init__("stale")
        self.warning = warning


def _checked_write(write: PastYearWrite, db: Session, confirm: str, by_ai: bool, tz, this_year: int):
    """(the write's result, the 409's body it gives now, or None). A confirm
    of the date-based warning checks the write and its years only."""
    by_date = _by_date(write, db, by_ai, tz, this_year)
    if by_date is not None and by_date["confirm"] == confirm:
        return write.apply(db), None
    found = _compare(write, db, tz, _needs_without(write, db), write.appends(db))
    return found.result, _warning(write, found, by_ai, this_year, db)


def _copy(db: Session, by_ai: bool) -> Path | None:
    """The copy before a confirmed save, made under its lock, unpruned
    until the save is made: a pre-change copy with a login, a fresh AI copy
    with the key (its kind and limits: the AI's writes never push out the
    owner's copies). No copy, no save (500)."""
    db_path = sqlite_file(db.get_bind())
    if db_path is None:  # not a database file (a test's in-memory one): nothing to copy
        logger.warning("A confirmed past-year save on a database that isn't a file: no copy")
        return None
    kind, label = ("ai", AI_CHANGE_LABEL) if by_ai else (PRE_CHANGE_KIND, COPY_LABEL)
    try:
        copy = backup_sqlite(db_path, label, kind=kind, keep=None)
    except (OSError, sqlite3.Error) as e:
        logger.error("No copy before a confirmed past-year save (%s): nothing saved", type(e).__name__)
        raise HTTPException(status_code=500, detail=NO_COPY) from e
    logger.info("Copy made before a confirmed past-year save: %s", copy.name)
    return copy


def _remove(copy: Path | None) -> None:
    """A copy whose save wasn't made (rolled back for a price, refused, or
    stale): it never counts as a copy."""
    if copy is not None:
        try:
            copy.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Couldn't remove the copy of a save that wasn't made: %s", e)


def _prune(db: Session, copy: Path | None, by_ai: bool) -> None:
    """The copies of its kind past their limit, once the save is made."""
    if copy is not None:
        kind, keep = ("ai", AI_COPIES_KEPT) if by_ai else (PRE_CHANGE_KIND, PRE_CHANGE_COPIES_KEPT)
        prune_backups(sqlite_file(db.get_bind()), keep, kind, spare=copy)
