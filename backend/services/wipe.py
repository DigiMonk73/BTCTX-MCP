"""
Deleting every transaction (#256): Settings' Delete All, and Create account
on an install that has transactions. Either needs the confirmation the
owner types in its dialog ("DELETE"), and gets a safety copy of the database
first, in the same request (<data dir>/backups/, kind "before-delete").
"""

from __future__ import annotations

import logging
import sqlite3

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

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


def refusal(db: Session, confirm: str | None) -> JSONResponse | None:
    """None when the delete may go ahead: confirmed, or nothing to delete.
    Otherwise the 409 that says what would go; nothing is deleted."""
    if confirm == CONFIRMATION:
        return None
    what = extent(db)
    if what["transactions"] == 0:
        return None
    detail = f"This deletes all {_describe(what)}. To go ahead, confirm with {CONFIRMATION}."
    return JSONResponse(status_code=409, content={"detail": detail, **what})


def copy_then_delete(db: Session) -> int:
    """A copy of the database, then every transaction deleted; how many.
    No copy, nothing deleted (500)."""
    if db.query(Transaction.id).first() is None:
        return 0
    db_path = sqlite_file(db.get_bind())
    if db_path is not None:
        try:
            dest = backup_sqlite(db_path, COPY_LABEL, kind=DELETE_KIND, keep=DELETE_COPIES_KEPT)
        except (OSError, sqlite3.Error) as e:
            logger.error("No copy before deleting every transaction (%s): nothing deleted", type(e).__name__)
            raise HTTPException(
                status_code=500, detail="Not deleted: BitcoinTX couldn't make its copy of the database first."
            ) from e
        logger.info("Copy made before deleting every transaction: %s", dest.name)
    return delete_all_transactions(db)
