"""
The account API (spec 5.9), login only; on this draft branch over
migration 0013's columns (B7b-0, never merged).
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from backend.schemas.account import AccountCreate, AccountUpdate, AccountRead, LedgerAccountRead
from backend.services import account as account_service
from backend.database import get_db

router = APIRouter(tags=["accounts"])


@router.get("/", response_model=list[LedgerAccountRead])
def list_accounts(db: Session = Depends(get_db)):
    """Every account the owner has, then the fee accounts, in 2.0's shape (spec 5.9)."""
    return account_service.account_book(db)


@router.get("/{account_id}", response_model=AccountRead)
def get_account(account_id: int, db: Session = Depends(get_db)):
    """One account, or 404."""
    account = account_service.get_account_by_id(account_id, db)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found.")
    return account


@router.post("/", response_model=list[LedgerAccountRead], status_code=201)
def create_account(account: AccountCreate, db: Session = Depends(get_db)):
    """A bank or a wallet, or an exchange and its two accounts: the rows made."""
    return account_service.add_account(db, account.kind, account.name)


@router.put("/{account_id}", response_model=list[LedgerAccountRead])
def update_account(account_id: int, account: AccountUpdate, confirm: str | None = None,
                   db: Session = Depends(get_db)):
    """Hide or show an account (an exchange's: both), or its exchange's 1099-DA
    switch; a switch that moves earlier years answers 409 until confirmed (5.8)."""
    try:
        changed = account_service.change_account(
            db, account_id, account.hidden, account.sends_1099da, account.name, confirm)
    except account_service.PastYearsChange as warning:
        db.rollback()
        return JSONResponse(status_code=409, content=warning.body)
    if changed is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    return changed


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: int, db: Session = Depends(get_db)):
    """Delete an account no transaction names: 204; 404 when it doesn't exist;
    400 for 1 to 6; 409 while transactions name it."""
    if not account_service.delete_account(account_id, db):
        raise HTTPException(status_code=404, detail="Account not found.")
    return
