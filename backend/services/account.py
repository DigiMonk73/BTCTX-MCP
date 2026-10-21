"""
Accounts: reading them, and changes to accounts other than the six fixed
ones (database.FIXED_ACCOUNTS: Bank, Wallet, Exchange USD, Exchange BTC,
BTC Fees, USD Fees). Those keep their name, currency and place, and are
recreated if missing, and no other account takes their names: the ledger
finds the fee accounts by name, and every start puts a fixed account's
name back, which a second account of that name would stop (#289).
"""

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.constants import ACCOUNT_EXTERNAL
from backend.database import FIXED_ACCOUNTS
from backend.models.account import Account
from backend.models.transaction import Transaction
from backend.schemas.account import AccountCreate, AccountUpdate


SPECIAL_ACCOUNTS = {a["id"]: {"name": a["name"], "currency": a["currency"]} for a in FIXED_ACCOUNTS}
FIXED_NAMES = frozenset(a["name"] for a in FIXED_ACCOUNTS)


def get_all_accounts(db: Session):
    """Every account, after putting the fixed ones right."""
    ensure_special_accounts_exist(db)
    return db.query(Account).all()


# 2.0's account list (spec 5.9) on the draft branch, a stub (P-2): each fixed
# account's kind and exchange from its id, until B2b stores them in the table
FIXED_KINDS = {1: ("bank", None), 2: ("wallet", None), 3: ("exchange", 1), 4: ("exchange", 1),
               5: ("fee", None), 6: ("fee", None)}
KIND_ORDER = ("bank", "wallet", "exchange", "fee")
FIRST_EXCHANGE = "Exchange"
FEE_NAMES = frozenset(SPECIAL_ACCOUNTS[i]["name"].casefold() for i in (5, 6))


def _kind(account: Account) -> str | None:
    """A fixed account's kind; any other is a wallet when it holds BTC, else a bank
    (5.3). None for one never listed: External, or a second fee account (#289)."""
    if account.id in FIXED_KINDS:
        return FIXED_KINDS[account.id][0]
    if account.id == ACCOUNT_EXTERNAL or account.name.strip().casefold() in FEE_NAMES:
        return None
    return "wallet" if account.currency == "BTC" else "bank"


def _named_by_transactions(db: Session) -> set[int]:
    """Every account a transaction names, from or to."""
    pairs = db.query(Transaction.from_account_id, Transaction.to_account_id).distinct()
    return {account_id for pair in pairs for account_id in pair if account_id is not None}


def account_book(db: Session) -> list[dict]:
    """The accounts as 2.0's GET /api/accounts/ lists them: banks, wallets,
    exchanges, then the fee accounts, each by id within its kind."""
    named = _named_by_transactions(db)
    book = []
    for account in get_all_accounts(db):
        kind = _kind(account)
        if kind is None:
            continue
        exchange_id = FIXED_KINDS.get(account.id, (kind, None))[1]
        book.append({
            "id": account.id, "name": account.name, "kind": kind, "currency": account.currency,
            "exchange_id": exchange_id, "exchange": FIRST_EXCHANGE if exchange_id else None,
            "hidden": False, "in_use": account.id in named,
        })
    return sorted(book, key=lambda row: (KIND_ORDER.index(row["kind"]), row["id"]))


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
    )
    db.add(new_account)
    db.commit()
    db.refresh(new_account)
    return new_account


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

    db.commit()
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