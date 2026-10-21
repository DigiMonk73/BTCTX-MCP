"""
The accounts (the six fixed ones; database.FIXED_ACCOUNTS). The list is in
2.0's shape (spec 5.9), derived from the fixed ids on this draft branch.
"""

from fastapi import APIRouter, Depends, HTTPException
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


@router.post("/", response_model=AccountRead)
def create_account(account: AccountCreate, db: Session = Depends(get_db)):
    """Create an account (user_id, name, currency)."""
    new_account = account_service.create_account(account, db)
    return new_account


@router.put("/{account_id}", response_model=AccountRead)
def update_account(account_id: int, account: AccountUpdate, db: Session = Depends(get_db)):
    """Change an account's name or currency, or 404."""
    updated_account = account_service.update_account(account_id, account, db)
    if not updated_account:
        raise HTTPException(status_code=404, detail="Account not found.")
    return updated_account


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: int, db: Session = Depends(get_db)):
    """Delete an account: 204; 404 when it doesn't exist; 400 for a fixed
    account; 409 while transactions name it."""
    success = account_service.delete_account(account_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="Account not found or cannot be deleted.")
    return