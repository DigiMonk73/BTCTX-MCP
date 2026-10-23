"""
Accounts: reading them, and changes to accounts other than the six fixed
ones (database.FIXED_ACCOUNTS: Bank, Wallet, Exchange USD, Exchange BTC,
BTC Fees, USD Fees). Those keep their currency, kind and place, and are
recreated if missing; 5 and 6 keep their names too, and no other account
takes a fixed account's name: the ledger finds the fee accounts by name,
and every start puts 5's and 6's names back, which a second account of
that name would stop (#289). 2.0's account book replaces this (B2b).
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.database import FIXED_ACCOUNTS, RENAMEABLE_FIXED
from backend.models.account import Account
from backend.models.exchange import Exchange
from backend.models.transaction import Transaction
from backend.schemas.account import AccountCreate, AccountUpdate


SPECIAL_ACCOUNTS = {a["id"]: a for a in FIXED_ACCOUNTS}
FIXED_NAMES = frozenset(a["name"] for a in FIXED_ACCOUNTS)


def get_all_accounts(db: Session):
    """Every account, after putting the fixed ones right."""
    ensure_special_accounts_exist(db)
    return db.query(Account).all()


def get_account_by_id(account_id: int, db: Session):
    """The account, or None."""
    return db.query(Account).filter(Account.id == account_id).first()


def create_account(account_data: AccountCreate, db: Session):
    """A new account; the special accounts' names are refused (400)."""
    ensure_special_accounts_exist(db)

    if account_data.name in FIXED_NAMES:
        raise HTTPException(
            status_code=400,
            detail="Cannot manually create one of the locked special accounts."
        )

    new_account = Account(
        user_id=account_data.user_id,
        name=account_data.name,
        currency=account_data.currency,
        # 1.x's accounts: a BTC one a wallet, else a bank (2.0 spec 5.3),
        # until 2.0's account API adds by kind
        kind="wallet" if account_data.currency == "BTC" else "bank",
    )
    db.add(new_account)
    _commit_name(db, account_data.name)
    db.refresh(new_account)
    return new_account


def _commit_name(db: Session, name: str | None) -> None:
    """Commit; a name alike another account's ignoring case, which the
    database refuses (accounts.name COLLATE NOCASE), is a 400."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"An account named {name} already exists.")


def update_account(account_id: int, account_data: AccountUpdate, db: Session):
    """
    A new name or currency for the account (None when it doesn't exist); a
    special account's are refused (400) unless unchanged, and so is a fixed
    account's name for any other.
    """
    account = get_account_by_id(account_id, db)
    if not account:
        return None
    if account_id not in SPECIAL_ACCOUNTS and account_data.name in FIXED_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot rename account #{account_id} to {account_data.name}: that is a fixed account's name."
        )

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

    _commit_name(db, account_data.name)
    db.refresh(account)
    return account


def delete_account(account_id: int, db: Session):
    """Delete the account (False when it doesn't exist); a special account is
    refused (400), and so is one transactions name (409): deleting it left
    them naming no account, and each such row stops every save that
    recalculates (#337)."""
    account = get_account_by_id(account_id, db)
    if not account:
        return False

    if account_id in SPECIAL_ACCOUNTS:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete special account #{account_id} ({account.name})."
        )
    naming = db.query(Transaction.id).filter(
        (Transaction.from_account_id == account_id) | (Transaction.to_account_id == account_id)).count()
    if naming:
        raise HTTPException(status_code=409, detail=(
            f"Not deleted: {naming} transaction{'s' if naming > 1 else ''} name{'' if naming > 1 else 's'} "
            f"{account.name}. Move {'them' if naming > 1 else 'it'} to another account, or delete "
            f"{'them' if naming > 1 else 'it'}, first."))

    db.delete(account)
    db.commit()
    return True


def ensure_special_accounts_exist(db: Session):
    """Create any missing special account and put back a changed currency,
    kind or exchange, and 5's and 6's names, as a start does (database.seed_defaults)."""
    for acc_id, info in SPECIAL_ACCOUNTS.items():
        special_acc = get_account_by_id(acc_id, db)
        if not special_acc:
            exchange = db.get(Exchange, info["exchange_id"]) if info["exchange_id"] else None
            name = f"{exchange.name} {info['currency']}" if exchange else info["name"]
            new_acc = Account(user_id=1, **{**info, "name": name})
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
            if acc_id not in RENAMEABLE_FIXED:
                special_acc.name = info["name"]
            for key in ("currency", "kind", "exchange_id"):
                setattr(special_acc, key, info[key])
            db.commit()
            db.refresh(special_acc)