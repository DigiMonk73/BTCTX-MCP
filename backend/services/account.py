"""
Accounts: the book (spec 5.4, 5.9) and Settings' changes to it.

Draft branch only (B7b-0, the Grok trial; never merged): the account API
of 5.9, over migration 0013's columns. Any account but the fee accounts
can be renamed (B8-5r), 1 to 4 can't be deleted, and the fee accounts
(5, 6) can't be renamed, hidden or deleted. Two stubs stand in for later
cards: `is_yours` is the gate of 5.10 (B7a), and `_past_years` the dry run
of 5.8's warning for the 1099-DA switch (B6c), which answers with the
warning's one shape (services/past_years.py).
"""

import re
import unicodedata

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.constants import ACCOUNT_EXTERNAL
from backend.database import FIXED_ACCOUNTS, take_write_lock
from backend.models.account import Account, Exchange
from backend.models.app_setting import AppSetting, save_setting
from backend.models.transaction import LedgerEntry, Transaction
from backend.services import tax_time
from backend.services.past_years import warning


SPECIAL_ACCOUNTS = {a["id"]: {"name": a["name"], "currency": a["currency"]} for a in FIXED_ACCOUNTS}
FIXED_NAMES = frozenset(a["name"] for a in FIXED_ACCOUNTS)

YOURS = ("bank", "wallet", "exchange")
KIND_ORDER = ("bank", "wallet", "exchange", "fee")
CURRENCY = {"bank": "USD", "wallet": "BTC"}
FIRST_ONES = frozenset({1, 2, 3, 4})
FEE_ACCOUNTS = frozenset({5, 6})
LAST_ID = "accounts_last_id"

# 5.1's reserved names: each always means one of 1.x's accounts in a file
RESERVED = {"bank": "bank", "wallet": "wallet", "exchange": "exchange",
            "exchange usd": "exchange", "exchange btc": "exchange"}
EXTERNAL = "external"
# 5.1: a name may hold no format character but these two, which some scripts and emoji need
JOINERS = frozenset({"‌", "‍"})

IN_USE = "This account has transactions, so it can't be deleted. Hide it instead: its history stays."
FIRST_ONES_KEPT = "Your first bank, wallet and exchange can't be deleted. Hide one you don't use."
FEES_KEPT = "The fee accounts can't be deleted."
FEES_SHOWN = "The fee accounts keep their names and can't be hidden."
NOT_AN_EXCHANGE = "Only an exchange's accounts have this setting."
BUSY = "BitcoinTX is busy saving something else: try again."


def _account_row(account: Account, exchange: Exchange | None, named: set[int]) -> dict:
    return {
        "id": account.id, "name": account.name, "kind": account.kind, "currency": account.currency,
        "exchange_id": account.exchange_id, "exchange": exchange.name if exchange else None,
        "sends_1099da": exchange.sends_1099da if exchange else None,
        "hidden": bool(account.hidden), "in_use": account.id in named,
    }


def _named_by_transactions(db: Session) -> set[int]:
    """Every account a transaction names, from or to."""
    pairs = db.query(Transaction.from_account_id, Transaction.to_account_id).distinct()
    return {account_id for pair in pairs for account_id in pair if account_id is not None}


def account_book(db: Session, only: set[int] | None = None) -> list[dict]:
    """The accounts as GET /api/accounts/ lists them (5.9): banks, wallets,
    exchanges, then the fee accounts, each by id within its kind. Writes nothing."""
    named = _named_by_transactions(db)
    exchanges = {e.id: e for e in db.query(Exchange).all()}
    rows = [
        _account_row(a, exchanges.get(a.exchange_id), named)
        for a in db.query(Account).all()
        if a.kind in KIND_ORDER and (only is None or a.id in only)
    ]
    return sorted(rows, key=lambda row: (KIND_ORDER.index(row["kind"]), row["id"]))


def get_account_by_id(account_id: int, db: Session):
    """The account, or None."""
    return db.query(Account).filter(Account.id == account_id).first()


def is_yours(account_id: int, db: Session) -> bool:
    """One of your accounts (a bank, a wallet or an exchange's): the gate's stub (5.10, B7a)."""
    account = db.get(Account, account_id)
    return account is not None and account.kind in YOURS


# --- names (5.1) ---

def _clean_name(raw: str) -> str:
    """Normalised: NFC, trimmed, every run of spaces one ASCII space."""
    text = "".join(" " if unicodedata.category(c) == "Zs" else c for c in unicodedata.normalize("NFC", raw))
    return re.sub(" +", " ", text).strip(" ")


def _folded(name: str) -> str:
    return _clean_name(name).casefold()


def _on_one_line(name: str) -> bool:
    return all(unicodedata.category(c) not in ("Cc", "Zl", "Zp") and
               (unicodedata.category(c) != "Cf" or c in JOINERS) for c in name)


def _refuse(detail: str) -> None:
    raise HTTPException(status_code=400, detail=detail)


def _its_own(renamed: Account | None, folded: str) -> bool:
    """A reserved name given back to the account it means (5.1: ids 1 to 4 "can be
    renamed, and renamed back"): Bank to 1, Wallet to 2, Exchange to exchange 1."""
    if renamed is None:
        return False
    return (folded == "bank" and renamed.id == 1) or (folded == "wallet" and renamed.id == 2) \
        or (folded == "exchange" and renamed.exchange_id == 1)


def _check_name(db: Session, name: str, kind: str, renamed: Account | None = None) -> None:
    """5.9's refusals for a new account's name; an exchange's also for its two accounts' names.
    A rename (`renamed`) doesn't collide with the names it replaces."""
    longest = 36 if kind == "exchange" else 40
    if not 1 <= len(name) <= longest or not _on_one_line(name) or name.startswith("'"):
        _refuse(f"A name is 1 to {longest} characters on one line.")
    folded = name.casefold()
    if folded == EXTERNAL:
        _refuse("External means everything outside BitcoinTX: choose another name.")
    if folded in RESERVED and not _its_own(renamed, folded):
        _refuse(f"'{name}' always means your first {RESERVED[folded]} in files (CSV, River, BitcoinTX 1.x): "
                "choose another name.")
    own = {a.id for a in _halves(db, renamed)} if renamed else set()
    own_exchange = renamed.exchange_id if renamed else None
    taken = {_folded(a.name) for a in db.query(Account).all() if a.id not in own} \
        | {_folded(e.name) for e in db.query(Exchange).all() if e.id != own_exchange}
    wanted = {folded} | ({f"{folded} usd", f"{folded} btc"} if kind == "exchange" else set())
    if taken & wanted:
        _refuse(f"An account named '{name}' already exists.")


# --- ids (5.1) ---

def _next_account_id(db: Session) -> int:
    """1 + the highest of 99, every account id, every id a transaction or a ledger
    line names, and the last id given (never given again)."""
    last = db.get(AppSetting, LAST_ID)
    highest = max(
        ACCOUNT_EXTERNAL,
        db.query(func.max(Account.id)).scalar() or 0,
        db.query(func.max(Transaction.from_account_id)).scalar() or 0,
        db.query(func.max(Transaction.to_account_id)).scalar() or 0,
        db.query(func.max(LedgerEntry.account_id)).scalar() or 0,
        int(last.value) if last else 0,
    )
    return highest + 1


def _new_account(db: Session, user_id: int, name: str, kind: str, currency: str,
                 exchange_id: int | None = None) -> int:
    account_id = _next_account_id(db)
    db.add(Account(id=account_id, user_id=user_id, name=name, kind=kind, currency=currency,
                   exchange_id=exchange_id, hidden=False))
    db.flush()
    save_setting(db, LAST_ID, str(account_id))
    return account_id


def add_account(db: Session, kind: str, raw_name: str) -> list[dict]:
    """POST /api/accounts/ (5.9): a bank or a wallet, one account; an exchange,
    the exchange and its two. The book's rows of what was made."""
    name = _clean_name(raw_name)
    if not take_write_lock(db):
        raise HTTPException(status_code=503, detail=BUSY)
    try:
        _check_name(db, name, kind)
        user_id = db.get(Account, 1).user_id
        if kind == "exchange":
            exchange = Exchange(id=(db.query(func.max(Exchange.id)).scalar() or 0) + 1, name=name, sends_1099da=True)
            db.add(exchange)
            db.flush()
            made = {_new_account(db, user_id, f"{name} USD", kind, "USD", exchange.id),
                    _new_account(db, user_id, f"{name} BTC", kind, "BTC", exchange.id)}
        else:
            made = {_new_account(db, user_id, name, kind, CURRENCY[kind])}
        db.commit()
    except Exception:
        db.rollback()
        raise
    return account_book(db, only=made)


# --- changes (5.9) ---

def _halves(db: Session, account: Account) -> list[Account]:
    """The account, or both of its exchange's accounts."""
    if account.kind != "exchange":
        return [account]
    return db.query(Account).filter(Account.exchange_id == account.exchange_id).all()


def _past_years(db: Session, ids: set[int]) -> list[int]:
    """The tax years before this one with a transaction naming one of `ids`: the
    B6c stub's stand-in for 5.8's dry run (the boxes it could move)."""
    tz = tax_time.get_tax_timezone(db)
    this_year = tax_time.current_tax_year(tz)
    rows = db.query(Transaction.timestamp).filter(
        Transaction.from_account_id.in_(ids) | Transaction.to_account_id.in_(ids))
    return sorted({tax_time.local_date(ts, tz).year for (ts,) in rows} - set(range(this_year, 10000)))


def _switch_1099da(db: Session, account: Account, sends: bool, confirm: str | None) -> None:
    """The exchange's 1099-DA setting, through 5.8's warning (B6c's stub): a change
    that could move earlier years' boxes needs `confirm` to be its fingerprint."""
    if account.kind != "exchange":
        _refuse(NOT_AN_EXCHANGE)
    exchange = db.get(Exchange, account.exchange_id)
    if exchange.sends_1099da == sends:
        return
    years = _past_years(db, {a.id for a in _halves(db, account)})
    if years:
        asked = warning(years, [], [], f"{exchange.id}:{sends}")
        if confirm != asked.body["confirm"]:
            raise asked
    exchange.sends_1099da = sends


def _rename(db: Session, account: Account, raw_name: str) -> None:
    """A new nickname (5.9, B8-5r): an exchange's account renames its exchange and
    both its accounts ("<name> USD", "<name> BTC"); the fee accounts keep theirs."""
    name = _clean_name(raw_name)
    exchange = db.get(Exchange, account.exchange_id) if account.kind == "exchange" else None
    # Its own name sent back (an exchange's, or the account's) changes nothing, as in 1.x
    if name in (account.name, exchange.name if exchange else None):
        return
    if account.kind == "fee":
        _refuse(FEES_SHOWN)
    _check_name(db, name, account.kind, renamed=account)
    if exchange is None:
        account.name = name
        return
    exchange.name = name
    for half in _halves(db, account):
        half.name = f"{name} {half.currency}"


def change_account(db: Session, account_id: int, hidden: bool | None, sends_1099da: bool | None,
                   name: str | None, confirm: str | None) -> list[dict] | None:
    """PUT /api/accounts/{id} (5.9): rename (B8-5r), hide or show, the 1099-DA
    switch. None when it doesn't exist."""
    account = get_account_by_id(account_id, db)
    if not account or account.kind not in KIND_ORDER:
        return None
    if name is not None:
        _rename(db, account, name)
    if hidden is not None:
        if account.kind == "fee":
            _refuse(FEES_SHOWN)
        for half in _halves(db, account):
            half.hidden = hidden
    if sends_1099da is not None:
        _switch_1099da(db, account, sends_1099da, confirm)
    db.commit()
    return account_book(db, only={a.id for a in _halves(db, account)})


def delete_account(account_id: int, db: Session) -> bool:
    """DELETE /api/accounts/{id} (5.9): an account no transaction names (an
    exchange's: the exchange and both, only when neither is named). False when
    it doesn't exist."""
    account = get_account_by_id(account_id, db)
    if not account or account.kind not in KIND_ORDER:
        return False
    if account_id in FIRST_ONES:
        _refuse(FIRST_ONES_KEPT)
    if account_id in FEE_ACCOUNTS:
        _refuse(FEES_KEPT)
    halves = _halves(db, account)
    if {a.id for a in halves} & _named_by_transactions(db):
        raise HTTPException(status_code=409, detail=IN_USE)
    exchange_id = account.exchange_id
    for half in halves:
        db.delete(half)
    if exchange_id is not None:
        db.delete(db.get(Exchange, exchange_id))
    db.commit()
    return True
