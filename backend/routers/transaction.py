"""
The transactions: list, read, create, edit and delete them, and recalculate
the whole ledger (services/transaction.py does the work). Timestamps go out
in UTC with a 'Z'.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime

from backend.schemas.transaction import (
    TransactionCreate,
    TransactionUpdate,
    TransactionRead
)
from backend.services import transaction as tx_service
from backend.database import get_db

router = APIRouter(tags=["transactions"])


def _attach_utc_and_build_read_model(tx) -> TransactionRead:
    """The transaction as TransactionRead, its UTC times written with 'Z'
    rather than '+00:00'."""
    pyd_model = TransactionRead.model_validate(tx)
    data = pyd_model.model_dump()

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
    return [_attach_utc_and_build_read_model(tx) for tx in raw_txs]


@router.get("/{tx_id}", response_model=TransactionRead)
def get_transaction(tx_id: int, db: Session = Depends(get_db)):
    """One transaction, or 404."""
    tx = tx_service.get_transaction_by_id(db, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    final_model = _attach_utc_and_build_read_model(tx)
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
    return _attach_utc_and_build_read_model(new_tx)


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
def update_transaction(transaction_id: int, tx: TransactionUpdate, db: Session = Depends(get_db)):
    """
    Change the fields given, then recalculate the whole ledger. 404 when the
    transaction doesn't exist.
    """
    tx_data = tx.model_dump(exclude_unset=True)
    updated_tx = tx_service.update_transaction_record(transaction_id, tx_data, db)
    if not updated_tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return _attach_utc_and_build_read_model(updated_tx)


@router.delete("/delete_all", status_code=204)
def delete_all_transactions_endpoint(request: Request, db: Session = Depends(get_db)):
    """Delete every transaction with its ledger lines, lots and disposals.
    Login only (never the AI key)."""
    if not request.session.get("user_id"):  # never the AI key
        raise HTTPException(status_code=403, detail="Deleting everything needs a login.")
    # 204 No Content: the deleted count is intentionally not returned.
    tx_service.delete_all_transactions(db)


@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    """
    Delete one transaction and recalculate the ledger. 404 when it doesn't
    exist; refused, changing nothing, when later transactions need its BTC.
    """
    success = tx_service.delete_transaction_record(transaction_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return
