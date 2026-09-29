"""
Accounts: reading them, and changes to accounts other than the four the
ledger's rules name (Bank, Wallet, Exchange USD, Exchange BTC), which stay
as they are and are recreated if missing.
"""

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.models.account import Account
from backend.schemas.account import AccountCreate, AccountUpdate


SPECIAL_ACCOUNTS = {
    1: {"name": "Bank",         "currency": "USD"},
    2: {"name": "Wallet",       "currency": "BTC"},
    3: {"name": "Exchange USD", "currency": "USD"},
    4: {"name": "Exchange BTC", "currency": "BTC"},
}


def get_all_accounts(db: Session):
    """Every account, after putting the four special ones right."""
    ensure_special_accounts_exist(db)
    return db.query(Account).all()


def get_account_by_id(account_id: int, db: Session):
    """The account, or None."""
    return db.query(Account).filter(Account.id == account_id).first()


def create_account(account_data: AccountCreate, db: Session):
    """A new account; the special accounts' names are refused (400)."""
    ensure_special_accounts_exist(db)

    forbidden_names = {v["name"] for v in SPECIAL_ACCOUNTS.values()}
    if account_data.name in forbidden_names:
        raise HTTPException(
            status_code=400,
            detail="Cannot manually create one of the locked special accounts."
        )

    new_account = Account(
        user_id=account_data.user_id,
        name=account_data.name,
        currency=account_data.currency,
    )
    db.add(new_account)
    db.commit()
    db.refresh(new_account)
    return new_account


def update_account(account_id: int, account_data: AccountUpdate, db: Session):
    """
    A new name or currency for the account (None when it doesn't exist); a
    special account's are refused (400) unless unchanged.
    """
    account = get_account_by_id(account_id, db)
    if not account:
        return None

    if account_id in SPECIAL_ACCOUNTS:
        if account_data.name is not None and account_data.name != account.name:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot rename the special account #{account_id} ({account.name})."
            )
        if account_data.currency is not None and account_data.currency != account.currency:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot change currency of special account #{account_id} ({account.name})."
            )

    if account_data.name is not None:
        account.name = account_data.name
    if account_data.currency is not None:
        account.currency = account_data.currency

    db.commit()
    db.refresh(account)
    return account


def delete_account(account_id: int, db: Session):
    """Delete the account (False when it doesn't exist); a special account is refused (400)."""
    account = get_account_by_id(account_id, db)
    if not account:
        return False

    if account_id in SPECIAL_ACCOUNTS:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete special account #{account_id} ({account.name})."
        )

    db.delete(account)
    db.commit()
    return True


def ensure_special_accounts_exist(db: Session):
    """Create any missing special account and put back a changed name or currency."""
    for acc_id, info in SPECIAL_ACCOUNTS.items():
        special_acc = get_account_by_id(acc_id, db)
        if not special_acc:
            new_acc = Account(
                id=acc_id,
                user_id=1,
                name=info["name"],
                currency=info["currency"],
            )
            db.add(new_acc)
            try:
                db.commit()
                db.refresh(new_acc)
            except Exception:
                db.rollback()
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to create special account ID={acc_id}. Possibly ID in use."
                )
        else:
            if special_acc.name != info["name"]:
                special_acc.name = info["name"]
            if special_acc.currency != info["currency"]:
                special_acc.currency = info["currency"]
            db.commit()
            db.refresh(special_acc)