"""
The accounts (the six fixed ones; database.FIXED_ACCOUNTS).
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import List
from sqlalchemy.orm import Session
from backend.schemas.account import AccountCreate, AccountUpdate, AccountRead
from backend.services import account as account_service
from backend.database import get_db

router = APIRouter(tags=["accounts"])


@router.get("/", response_model=List[AccountRead])
def list_accounts(db: Session = Depends(get_db)):
    """Every account."""
    return account_service.get_all_accounts(db)


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
    """Delete an account: 204, or 404 when it doesn't exist or is in use."""
    success = account_service.delete_account(account_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="Account not found or cannot be deleted.")
    return