"""
Your accounts (2.0 spec 5.9): the list, one account, adding a bank, a
wallet or an exchange, renaming, hiding and showing, an exchange's 1099-DA
switch (through the past-year warning, 5.8), and deleting an unused one.
Login only.
"""

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from backend.schemas.account import AccountCreate, AccountUpdate, AccountRead
from backend.services import account as account_service
from backend.services import past_years
from backend.services.past_year_writes import AccountChange
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
    """A bank or a wallet (one account), or an exchange (its two) with its
    1099-DA switch (`sends_1099da`; left out, on); 400 for a name it
    refuses, or a switch given with a bank or a wallet. A new exchange has
    no sales, so its switch moves no figure: the past-year warning never asks."""
    made = account_service.add_account(db, account.kind, account.name, account.sends_1099da)
    return account_service.listed(db, made)


@router.put("/{account_id}", response_model=AccountRead)
def update_account(account_id: int, change: AccountUpdate, confirm: str | None = None,
                   db: Session = Depends(get_db)):
    """
    Rename, hide or show an account (an exchange's: its exchange and both),
    and turn an exchange's 1099-DA switch off or on (from either of its
    accounts); 400 for a name it refuses, a fee account renamed or hidden,
    or the switch on an account that isn't an exchange's; 404. A switch that
    moves the Form 8949 box of a sale in an earlier tax year answers 409 with
    the years, what changes and a fingerprint, and saves nothing until sent
    again with ?confirm=<fingerprint>; a copy of the database comes first. A
    name or hidden alone moves no figure, so it never asks.
    """
    account_service.one(db, account_id)  # 404 first
    write = AccountChange(account_id, hidden=change.hidden, sends_1099da=change.sends_1099da, name=change.name)
    done = past_years.save(write, db, confirm, by_ai=False)
    if isinstance(done, JSONResponse):
        return done  # the warning
    return account_service.one(db, account_id)


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: int, db: Session = Depends(get_db)):
    """204; 400 for your first bank, wallet or exchange and the fee
    accounts; 409 while a transaction or a ledger line names it; 404."""
    account_service.delete_account(db, account_id)
    return Response(status_code=204)
