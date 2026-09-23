"""
backend/routers/transaction.py

Router for Transaction endpoints in a full double-entry environment.
The user might still pass single-entry fields (from_account_id, amount, etc.),
but the service transforms them into LedgerEntries plus optional BTC lot usage.

We keep these endpoints minimal, delegating actual multi-line ledger creation,
BTC lot tracking (BitcoinLot), and disposal (LotDisposal) to the service layer.

Refactor Notes:
 - We ensure that all datetime fields are coerced to UTC (tzinfo=timezone.utc)
   before returning them. Then we convert to ISO8601 with trailing 'Z' instead
   of '+00:00'.
 - This applies to both the "list" route and "get by ID" route, ensuring
   consistent format across the entire API.
 - Added a 404 check in get_transaction(tx_id).
 - Otherwise, we've retained your existing create, update, and delete endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import List
from sqlalchemy.orm import Session
from datetime import datetime, timezone

# The Pydantic schemas for transaction CRUD
from backend.schemas.transaction import (
    TransactionCreate,
    TransactionUpdate,
    TransactionRead
)

# The service layer that handles double-entry creation, BTC lots, FIFO disposal, etc.
from backend.services import transaction as tx_service

# The FastAPI "dependency" for getting a database session
from backend.database import get_db

# Create a router instance
router = APIRouter(tags=["transactions"])


def _attach_utc_and_build_read_model(tx) -> TransactionRead:
    """
    Utility function to:
      1) (Previously) attach tzinfo=UTC if missing, but now we store offset-aware in DB
      2) Convert to TransactionRead Pydantic model
      3) Replace '+00:00' with 'Z' in the resulting dict
      4) Return a new TransactionRead object with corrected ISO strings

    We still do the final step of turning '+00:00' into 'Z' for a clean UTC display,
    but no longer force tzinfo=UTC since our DB / schemas already handle that.
    """

    # 1) Convert to Pydantic
    pyd_model = TransactionRead.model_validate(tx)
    data = pyd_model.model_dump()

    # 2) Turn any '+00:00' suffix into 'Z'
    for field in ["timestamp", "created_at", "updated_at"]:
        val = data.get(field)
        if isinstance(val, datetime):
            iso_str = val.isoformat()
            if iso_str.endswith("+00:00"):
                iso_str = iso_str[:-6] + "Z"
            data[field] = iso_str

    # 3) Return a new TransactionRead
    return TransactionRead(**data)


@router.get("", response_model=List[TransactionRead])
def list_transactions(db: Session = Depends(get_db)):
    """
    List all transactions in the database, ensuring each timestamp
    is returned with a 'Z' suffix (UTC).
    """
    raw_txs = tx_service.get_all_transactions(db)
    return [_attach_utc_and_build_read_model(tx) for tx in raw_txs]


@router.get("/{tx_id}", response_model=TransactionRead)
def get_transaction(tx_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a single transaction by ID, ensuring
    timestamps have 'Z' (UTC) in the final JSON.
    """
    tx = tx_service.get_transaction_by_id(db, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    final_model = _attach_utc_and_build_read_model(tx)
    return final_model


@router.post("", response_model=TransactionRead)
def create_transaction(tx: TransactionCreate, db: Session = Depends(get_db)):
    """
    Create a new transaction in the double-entry system.

    - The front end may supply 'from_account_id', 'to_account_id', 'amount',
      'fee_amount', etc.
    - The service layer:
        1) Builds LedgerEntries (MAIN_OUT, MAIN_IN, FEE) for each debit/credit.
        2) If it's a Deposit/Buy, creates a BitcoinLot.
        3) If it's a Withdrawal/Sell, disposes from existing lots (LotDisposal),
           computing partial or final cost basis if desired.
        4) Runs the double-entry balance check (if both sides are internal).
    - Returns the newly created Transaction with an 'id'.
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
    Update an existing transaction's data if it's not locked.

    - The service might remove old ledger lines/lot usage and re-create them
      if the user changed critical fields like amount or type.
    - If the transaction is locked or nonexistent, return 404 or 400.
    """
    tx_data = tx.model_dump(exclude_unset=True)
    updated_tx = tx_service.update_transaction_record(transaction_id, tx_data, db)
    if not updated_tx:
        raise HTTPException(status_code=404, detail="Transaction not found or is locked.")
    return _attach_utc_and_build_read_model(updated_tx)


@router.delete("/delete_all", status_code=204)
def delete_all_transactions_endpoint(db: Session = Depends(get_db)):
    """
    Delete all transactions from the database. This will remove all Transaction records,
    and cascade delete associated LedgerEntries, BitcoinLots, and LotDisposals.
    """
    # 204 No Content: the deleted count is intentionally not returned.
    tx_service.delete_all_transactions(db)


@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    """
    Delete a transaction if it's not locked. The service layer also
    cascades removal of any LedgerEntries, BitcoinLots, or LotDisposals
    tied to this transaction.
    """
    success = tx_service.delete_transaction_record(transaction_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="Transaction not found or cannot be deleted.")
    return
