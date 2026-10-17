"""
Deleting every transaction (#256): Settings' Delete All, and Create account
on an install that has transactions. Either needs the confirmation the
owner types in its dialog ("DELETE"), for the transactions and tax years
it showed (#377), and gets a safety copy of the database first, in the same
request (<data dir>/backups/, kind "before-delete").
The check of that confirmation, the copy and the delete hold SQLite's write
lock together (#276): a transaction saved meanwhile (the AI connector's)
waits until after the delete.
"""

from __future__ import annotations

import logging
import sqlite3

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import take_write_lock
from backend.migrate import DELETE_COPIES_KEPT, DELETE_KIND, backup_sqlite, sqlite_file
from backend.models.transaction import Transaction
from backend.services.tax_time import get_tax_timezone, local_date
from backend.services.transaction import delete_all_transactions

logger = logging.getLogger(__name__)

CONFIRMATION = "DELETE"
COPY_LABEL = "all"


def extent(db: Session) -> dict:
    """What a delete would take: how many transactions, and their first and
    last tax years (None with none)."""
    count, first, last = db.query(
        func.count(Transaction.id), func.min(Transaction.timestamp), func.max(Transaction.timestamp)
    ).one()
    tz = get_tax_timezone(db)
    return {
        "transactions": count,
        "first_year": local_date(first, tz).year if first else None,
        "last_year": local_date(last, tz).year if last else None,
    }


def _describe(what: dict) -> str:
    """ "118 transactions, 2023–2026" (one year: "2024")."""
    years = str(what["first_year"])
    if what["last_year"] != what["first_year"]:
        years += f"–{what['last_year']}"
    noun = "transaction" if what["transactions"] == 1 else "transactions"
    return f"{what['transactions']} {noun}, {years}"


def refusal(db: Session, confirm: str | None, shown: dict | None = None) -> JSONResponse | None:
    """None when the delete may go ahead: confirmed, or nothing to delete.
    A confirmation that says what its dialog showed (`shown`: the count and
    tax years, as extent() gives them, #377) holds only while the ledger
    still has that: a transaction saved or deleted since (the AI
    connector's) is refused, so the owner deletes what they were shown.
    Otherwise the 409 that says what would go now; nothing is deleted."""
    what = extent(db)
    changed = any(value is not None and value != what[key] for key, value in (shown or {}).items())
    if not changed and (confirm == CONFIRMATION or what["transactions"] == 0):
        return None
    return JSONResponse(status_code=409, content={"detail": _refusal_text(what, changed), **what})


def _refusal_text(what: dict, changed: bool) -> str:
    """What would go, and how to go ahead."""
    if what["transactions"] == 0:  # only when the dialog showed some
        return "The ledger changed since you were asked: there's nothing to delete now."
    every = "all " if what["transactions"] > 1 else ""
    deletes = "The ledger changed since you were asked: this now deletes" if changed else "This deletes"
    return f"{deletes} {every}{_describe(what)}. To go ahead, confirm with {CONFIRMATION}."


def delete_all(db: Session, confirm: str | None, shown: dict | None = None) -> JSONResponse | None:
    """
    Every transaction deleted, after a copy of the database: None. Only
    when confirmed (for what the dialog showed, when it says), or with
    nothing to delete; otherwise the 409 refusal, nothing deleted. The
    check, the copy and the delete hold one write lock (#276): they see the
    same ledger, and what is saved meanwhile waits until after the delete.
    """
    if not take_write_lock(db):
        logger.warning("Deleting every transaction: the database is busy, nothing deleted")
        raise HTTPException(
            status_code=503, detail="Not deleted: BitcoinTX was busy saving something else. Try again."
        )
    refused = refusal(db, confirm, shown)
    if refused is not None:
        db.rollback()  # the lock goes
        return refused
    _copy_then_delete(db)
    return None


def _copy_then_delete(db: Session) -> int:
    """A copy of the database, then every transaction deleted; how many.
    A copy that fails deletes nothing (500). Ends the lock's transaction."""
    if db.query(Transaction.id).first() is None:
        db.commit()  # nothing to delete: the lock goes
        return 0
    db_path = sqlite_file(db.get_bind())
    if db_path is None:  # not a database file (a test's in-memory one): nothing to copy
        logger.warning("Deleting every transaction of a database that isn't a file: no copy")
    else:
        try:
            dest = backup_sqlite(db_path, COPY_LABEL, kind=DELETE_KIND, keep=DELETE_COPIES_KEPT)
        except (OSError, sqlite3.Error) as e:
            db.rollback()
            logger.error("No copy before deleting every transaction (%s): nothing deleted", type(e).__name__)
            raise HTTPException(
                status_code=500, detail="Not deleted: BitcoinTX couldn't make its copy of the database first."
            ) from e
        logger.info("Copy made before deleting every transaction: %s", dest.name)
    return delete_all_transactions(db)
