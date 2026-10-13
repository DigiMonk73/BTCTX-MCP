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
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from backend.schemas.transaction import (
    TransactionCreate,
    TransactionUpdate,
    TransactionRead
)
from backend.services import transaction as tx_service
from backend.database import get_db
from backend.migrate import AI_CHANGE_LABEL, AI_COPIES_KEPT, backup_copies, backup_sqlite, sqlite_file

logger = logging.getLogger(__name__)

router = APIRouter(tags=["transactions"])

AI_CHANGE_COPY_EVERY = 3600  # seconds
_now = time.time  # tests move the clock
# One copy at a time (BitcoinTX runs one server process): a change that
# comes while the copy is being written waits for it, then finds it.
_ai_change_copy = threading.Lock()


def _attach_utc_and_build_read_model(tx, db: Session | None = None, years: dict | None = None) -> TransactionRead:
    """The transaction as TransactionRead, its UTC times written with 'Z'
    rather than '+00:00', and the stored price its filled-in values came
    from (price_used; read only, never asked for)."""
    pyd_model = TransactionRead.model_validate(tx)
    data = pyd_model.model_dump()
    if db is not None:
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


@router.get("/{tx_id}", response_model=TransactionRead)
def get_transaction(tx_id: int, db: Session = Depends(get_db)):
    """One transaction, or 404."""
    tx = tx_service.get_transaction_by_id(db, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    final_model = _attach_utc_and_build_read_model(tx, db)
    return final_model


@router.post("", response_model=TransactionRead)
def create_transaction(tx: TransactionCreate, db: Session = Depends(get_db)):
    """
    Save a new transaction with its ledger lines and its lots or lot
    disposals; one dated before others recalculates the ledger.
    """
    tx_data = tx.model_dump()
    new_tx = tx_service.create_transaction_record(tx_data, db)
    if not new_tx:
        raise HTTPException(status_code=400, detail="Transaction creation failed.")
    return _attach_utc_and_build_read_model(new_tx, db)


@router.post("/recalculate")
def recalculate_ledger(db: Session = Depends(get_db)):
    """
    Rebuild every ledger line, lot and disposal from the transactions in
    chronological order (the same "scorched earth" pass edits trigger).
    Run once after upgrading so calculation fixes reach existing data.
    """
    try:
        tx_service.recalculate_all_transactions(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    count = len(tx_service.get_all_transactions(db))
    return {"detail": f"Recalculated {count} transaction(s).", "transactions": count}


@router.put("/{transaction_id}", response_model=TransactionRead)
def update_transaction(transaction_id: int, tx: TransactionUpdate, request: Request, db: Session = Depends(get_db)):
    """
    Change the fields given, then recalculate the whole ledger. 404 when the
    transaction doesn't exist. With the AI key, its first change in an hour
    (an edit or a deletion) comes after an AI copy of the database.
    """
    if not tx_service.get_transaction_by_id(db, transaction_id):
        raise HTTPException(status_code=404, detail="Transaction not found.")
    if not request.session.get("user_id"):  # the AI key
        _copy_before_ai_changes(db, "Not changed")
    tx_data = tx.model_dump(exclude_unset=True)
    updated_tx = tx_service.update_transaction_record(transaction_id, tx_data, db)
    if not updated_tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return _attach_utc_and_build_read_model(updated_tx, db)


@router.delete("/delete_all", status_code=204)
def delete_all_transactions_endpoint(request: Request, db: Session = Depends(get_db)):
    """Delete every transaction with its ledger lines, lots and disposals.
    Login only (never the AI key)."""
    if not request.session.get("user_id"):  # never the AI key
        raise HTTPException(status_code=403, detail="Deleting everything needs a login.")
    # 204 No Content: the deleted count is intentionally not returned.
    tx_service.delete_all_transactions(db)


@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Delete one transaction and recalculate the ledger. 404 when it doesn't
    exist; refused, changing nothing, when later transactions need its BTC.
    With the AI key, its first change in an hour (an edit or a deletion)
    comes after an AI copy of the database (in the backups folder).
    """
    if not tx_service.get_transaction_by_id(db, transaction_id):
        raise HTTPException(status_code=404, detail="Transaction not found.")
    if not request.session.get("user_id"):  # the AI key
        _copy_before_ai_changes(db, "Not deleted")
    success = tx_service.delete_transaction_record(transaction_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return


def _made_this_hour_today(made: float) -> bool:
    """A copy less than an hour old, made on today's UTC day: a change just
    after midnight still gets the new day's first copy (the one
    migrate._ai_copies_held keeps for the week)."""
    now = _now()
    today = datetime.fromtimestamp(now, timezone.utc).date()
    return now - made < AI_CHANGE_COPY_EVERY and datetime.fromtimestamp(made, timezone.utc).date() == today


def _copy_before_ai_changes(db: Session, refused: str) -> None:
    """
    An AI copy before the AI key's first change in an hour (an edit or a
    deletion), which the AI copies the key asks for next never push out
    (migrate._ai_copies_held). No copy, no change: `refused` ("Not changed",
    "Not deleted") opens the message.
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
