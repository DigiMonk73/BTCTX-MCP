"""
The transactions: list, read, create, edit and delete them, and recalculate
the whole ledger (services/transaction.py does the work). Timestamps go out
in UTC with a 'Z'.
"""

import logging
import sqlite3
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from backend.schemas.transaction import (
    TransactionCreate,
    TransactionUpdate,
    TransactionRead
)
from backend.services import past_year_saves
from backend.services import transaction as tx_service
from backend.services import wipe
from backend.services.account import read_book
from backend.services.past_years import PastYearsChange
from backend.database import get_db
from backend.migrate import AI_CHANGE_LABEL, AI_COPIES_KEPT, backup_copies, backup_sqlite, sqlite_file

logger = logging.getLogger(__name__)

router = APIRouter(tags=["transactions"])

AI_CHANGE_COPY_EVERY = 3600  # seconds
_now = time.time  # tests move the clock
# One copy at a time (BitcoinTX runs one server process): a change that
# comes while the copy is being written waits for it, then finds it.
_ai_change_copy = threading.Lock()


def _attach_utc_and_build_read_model(tx, db: Session, years: dict | None = None) -> TransactionRead:
    """The transaction as TransactionRead, its UTC times written with 'Z'
    rather than '+00:00', which values BitcoinTX filled in from a price, and
    the stored price they came from (price_used; read only, never asked for)."""
    pyd_model = TransactionRead.model_validate(tx)
    data = pyd_model.model_dump()
    data["values_from_price"] = tx_service.values_from_price(tx, read_book(db))
    data["price_used"] = tx_service.price_used(tx, db, years)

    for field in ["timestamp", "created_at", "updated_at"]:
        val = data.get(field)
        if isinstance(val, datetime):
            iso_str = val.isoformat()
            if iso_str.endswith("+00:00"):
                iso_str = iso_str[:-6] + "Z"
            data[field] = iso_str

    return TransactionRead(**data)


@router.get("", response_model=list[TransactionRead])
def list_transactions(db: Session = Depends(get_db)):
    """Every transaction, newest first."""
    raw_txs = tx_service.get_all_transactions(db)
    years: dict = {}  # the year files, read once for the whole list
    return [_attach_utc_and_build_read_model(tx, db, years) for tx in raw_txs]


def _require_login_to_delete_all(request: Request) -> None:
    if not request.session.get("user_id"):  # never the AI key
        raise HTTPException(status_code=403, detail="Deleting everything needs a login.")


@router.get("/delete_all")
def what_delete_all_deletes(request: Request, db: Session = Depends(get_db)):
    """What Delete All would delete, for its dialog: {"transactions",
    "first_year", "last_year"} (tax years). Login only."""
    _require_login_to_delete_all(request)
    return wipe.extent(db)


@router.get("/{tx_id}", response_model=TransactionRead)
def get_transaction(tx_id: int, db: Session = Depends(get_db)):
    """One transaction, or 404."""
    tx = tx_service.get_transaction_by_id(db, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    final_model = _attach_utc_and_build_read_model(tx, db)
    return final_model


@router.post("", response_model=TransactionRead)
def create_transaction(tx: TransactionCreate, request: Request, confirm: str | None = None,
                       db: Session = Depends(get_db)):
    """
    Save a new transaction with its ledger lines and its lots or lot
    disposals; one dated before others recalculates the ledger. One that
    changes an earlier tax year answers 409 and saves nothing until it's
    sent again with confirm=<the 409's fingerprint>, after a copy of the
    database (5.8).
    """
    new_tx = _through_the_warning(
        past_year_saves.Write("add", data=tx.model_dump()), request, db, confirm)
    if isinstance(new_tx, JSONResponse):
        return new_tx
    if not new_tx:
        raise HTTPException(status_code=400, detail="Transaction creation failed.")
    return _attach_utc_and_build_read_model(new_tx, db)


@router.post("/recalculate")
def recalculate_ledger(request: Request, db: Session = Depends(get_db)):
    """
    Rebuild every ledger line, lot and disposal from the transactions in
    chronological order (the same "scorched earth" pass edits trigger).
    Run once after upgrading so calculation fixes reach existing data.
    With the AI key, its first change in an hour comes after an AI copy of
    the database: a recalculation can move stored figures (#336).
    """
    if not request.session.get("user_id"):  # the AI key
        _copy_before_ai_changes(db, "Not recalculated")
    try:
        tx_service.recalculate_ledger(db)
    except Exception:
        db.rollback()
        raise
    count = len(tx_service.get_all_transactions(db))
    return {"detail": f"Recalculated {count} transaction(s).", "transactions": count}


@router.put("/{transaction_id}", response_model=TransactionRead)
def update_transaction(transaction_id: int, tx: TransactionUpdate, request: Request, confirm: str | None = None,
                       db: Session = Depends(get_db)):
    """
    Change the fields given, then recalculate the whole ledger. 404 when the
    transaction doesn't exist. With the AI key, its first change in an hour
    (an edit, a deletion, a recalculation, or an import that recalculates)
    comes after an AI copy of the database. One that changes an earlier tax
    year answers 409 until confirmed, as an add does (5.8).
    """
    if not tx_service.get_transaction_by_id(db, transaction_id):
        raise HTTPException(status_code=404, detail="Transaction not found.")
    if not request.session.get("user_id") and confirm is None:  # the AI key; a confirmed write makes its own
        _copy_before_ai_changes(db, "Not changed")
    updated_tx = _through_the_warning(
        past_year_saves.Write("edit", transaction_id, tx.model_dump(exclude_unset=True)),
        request, db, confirm)
    if isinstance(updated_tx, JSONResponse):
        return updated_tx
    if not updated_tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return _attach_utc_and_build_read_model(updated_tx, db)


@router.delete("/delete_all", status_code=204)
def delete_all_transactions_endpoint(
    request: Request, confirm: str | None = None, transactions: int | None = None, first_year: int | None = None,
    last_year: int | None = None, db: Session = Depends(get_db),
):
    """
    Delete every transaction with its ledger lines, lots and disposals, only
    with confirm=DELETE (typed in the dialog, #256) and, when given, while
    the ledger has the transactions and tax years the dialog showed (#377):
    otherwise 409 says what would go now, and nothing is deleted. A copy of
    the database comes first (backups/, "before-delete"). Login only (never
    the AI key).
    """
    _require_login_to_delete_all(request)
    shown = {"transactions": transactions, "first_year": first_year, "last_year": last_year}
    # The 409, or 204 No Content: what went is what the dialog showed.
    return wipe.delete_all(db, confirm, shown)


@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: int, request: Request, confirm: str | None = None,
                       db: Session = Depends(get_db)):
    """
    Delete one transaction and recalculate the ledger. 404 when it doesn't
    exist; refused, changing nothing, when later transactions need its BTC.
    With the AI key, its first change in an hour (an edit, a deletion, a
    recalculation, or an import that recalculates) comes after an AI copy of
    the database (in the backups folder). One that changes an earlier tax
    year answers 409 until confirmed, as an add does (5.8).
    """
    if not tx_service.get_transaction_by_id(db, transaction_id):
        raise HTTPException(status_code=404, detail="Transaction not found.")
    if not request.session.get("user_id") and confirm is None:  # the AI key; a confirmed write makes its own
        _copy_before_ai_changes(db, "Not deleted")
    success = _through_the_warning(
        past_year_saves.Write("delete", transaction_id), request, db, confirm)
    if isinstance(success, JSONResponse):
        return success
    if not success:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return


def _through_the_warning(write: past_year_saves.Write, request: Request, db: Session,
                         confirm: str | None):
    """The write, or 409 when it changes an earlier tax year (5.8). The AI
    key is also warned about a pending fix; a login is not."""
    try:
        return past_year_saves.save(write, db, confirm, ai=not request.session.get("user_id"))
    except PastYearsChange as asked:
        db.rollback()
        return JSONResponse(status_code=409, content=asked.body)


def _made_this_hour_today(made: float) -> bool:
    """A copy less than an hour old, made on today's UTC day: a change just
    after midnight still gets the new day's first copy (the one
    migrate._ai_copies_held keeps for the week)."""
    now = _now()
    today = datetime.fromtimestamp(now, timezone.utc).date()
    return now - made < AI_CHANGE_COPY_EVERY and datetime.fromtimestamp(made, timezone.utc).date() == today


def _copy_before_ai_changes(db: Session, refused: str) -> None:
    """
    An AI copy before the AI key's first change in an hour (an edit, a
    deletion, a recalculation, or an import that recalculates: also
    routers/entry_import), which the AI copies the key asks for next never
    push out (migrate._ai_copies_held). No copy, no change: `refused` ("Not
    changed", "Not deleted", "Not recalculated", "Not added") opens the
    message.
    """
    db_path = sqlite_file(db.get_bind())
    if db_path is None:
        return
    with _ai_change_copy:
        newest = backup_copies(db_path, "ai", label=AI_CHANGE_LABEL)
        if newest and _made_this_hour_today(newest[0].stat().st_mtime):
            return
        try:
            dest = backup_sqlite(db_path, AI_CHANGE_LABEL, kind="ai", keep=AI_COPIES_KEPT)
        except (OSError, sqlite3.Error) as e:
            logger.error("No AI copy before a change (%s): the change was refused", type(e).__name__)
            raise HTTPException(
                status_code=500, detail=f"{refused}: BitcoinTX couldn't make its copy of the database first."
            ) from e
    logger.info("AI backup copy made before a change: %s", dest.name)
