"""
Your accounts (2.0 spec 5.9): the list, one account, adding a bank, a
wallet or an exchange, hiding and showing, and deleting an unused one.
Login only.
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from backend.schemas.account import AccountCreate, AccountUpdate, AccountRead
from backend.services import account as account_service
from backend.database import get_db

router = APIRouter(tags=["accounts"])


@router.get("/", response_model=list[AccountRead])
def list_accounts(db: Session = Depends(get_db)):
    """Banks, wallets, exchanges, then the fee accounts. Writes nothing."""
    return account_service.listed(db)


@router.get("/{account_id}", response_model=AccountRead)
def get_account(account_id: int, db: Session = Depends(get_db)):
    """One account, or 404."""
    return account_service.one(db, account_id)


@router.post("/", response_model=list[AccountRead], status_code=201)
def create_account(account: AccountCreate, db: Session = Depends(get_db)):
    """A bank or a wallet (one account), or an exchange (its two); 400 for a name it refuses."""
    made = account_service.add_account(db, account.kind, account.name)
    return account_service.listed(db, made)


@router.put("/{account_id}", response_model=AccountRead)
def update_account(account_id: int, change: AccountUpdate, db: Session = Depends(get_db)):
    """Hide or show an account (an exchange's: both); 400 for a fee account, 404."""
    if change.hidden is not None:
        account_service.set_hidden(db, account_id, change.hidden)
    if change.sends_1099da is not None:  # TEMP: a stand-in for B6c's switch (#353)
        from backend.models.account import Account
        from backend.models.exchange import Exchange
        db.get(Exchange, db.get(Account, account_id).exchange_id).sends_1099da = change.sends_1099da
        db.commit()
    return account_service.one(db, account_id)


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: int, db: Session = Depends(get_db)):
    """204; 400 for your first bank, wallet or exchange and the fee
    accounts; 409 while a transaction or a ledger line names it; 404."""
    account_service.delete_account(db, account_id)
    return Response(status_code=204)
