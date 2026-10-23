"""
The account book (2.0 spec 5.4) and the account API's work (5.9).

One place answers every question about an account, from the accounts and
exchanges tables: `account_book(db)`, read once per request, import,
recalculation or report. Accounts are added by kind (an exchange as its
two, "<name> USD" and "<name> BTC"), hidden and shown, and deleted only
while no transaction names them. Ids and names follow 5.1. The six fixed
accounts (database.FIXED_ACCOUNTS, put right at every start by
seed_defaults) and External (99, no row) are always there: 1-4 are never
deleted, 5 and 6 neither hidden nor deleted. Renames come with B8.
"""

import re
import unicodedata
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import func, select, union_all
from sqlalchemy.orm import Session

from backend.constants import ACCOUNT_BTC_FEES, ACCOUNT_EXTERNAL, ACCOUNT_USD_FEES, RESERVED_NAMES
from backend.database import take_write_lock
from backend.models.account import Account
from backend.models.app_setting import AppSetting, save_setting
from backend.models.exchange import Exchange
from backend.models.transaction import LedgerEntry, Transaction
from backend.models.user import User

YOUR_KINDS = ("bank", "wallet", "exchange")
FEE_ACCOUNTS = (ACCOUNT_BTC_FEES, ACCOUNT_USD_FEES)
# Your first bank, wallet and exchange: hidden when unused, never deleted
FIRST_OF_EACH = {1: "bank", 2: "wallet", 3: "exchange", 4: "exchange"}
# The last account id ever given (5.1): no id is given twice, a restore keeps the higher
LAST_ID_KEY = "accounts_last_id"
LONGEST_NAME, LONGEST_EXCHANGE_NAME = 40, 36  # an exchange's leaves room for " USD"
# Some scripts and emoji need them: the one format characters a name keeps,
# inside it only, and two names differing by them alone are alike
JOINERS = ("\u200c", "\u200d")
TRIMMED = " " + "".join(JOINERS)
LIST_ORDER = {"bank": 0, "wallet": 1, "exchange": 2, "fee": 3}

BUSY = "Not saved: BitcoinTX was busy saving something else. Try again."
ALREADY = "An account named '{name}' already exists."
EXCHANGE_ALREADY = "An exchange named '{name}' already exists."
RESERVED = "'{name}' always means your first {kind} in files (CSV, River, BitcoinTX 1.x): choose another name."
EXTERNAL = "External means everything outside BitcoinTX: choose another name."
FEES_STAY = "The fee accounts keep their names and can't be hidden."
FEES_NOT_DELETED = "The fee accounts can't be deleted."
FIRST_NOT_DELETED = "Your first bank, wallet and exchange can't be deleted. Hide one you don't use."
IN_USE = "This account has transactions, so it can't be deleted. Hide it instead: its history stays."


@dataclass(frozen=True)
class BookAccount:
    id: int
    name: str
    kind: str
    currency: str
    exchange_id: int | None
    hidden: bool


class AccountBook:
    """Every question about an account, by id (or a name from a file)."""

    def __init__(self, accounts: list[BookAccount], exchanges: dict[int, tuple[str, bool]]):
        self._accounts = {a.id: a for a in accounts}
        self._exchanges = exchanges
        self._by_key = {name_key(a.name): a.id for a in accounts}

    def is_btc(self, account_id: int | None) -> bool:
        """One of your bitcoin accounts: a wallet, or an exchange's BTC account (5.1)."""
        account = self._accounts.get(account_id)
        return account is not None and account.kind in ("wallet", "exchange") and account.currency == "BTC"

    def currency(self, account_id: int | None) -> str | None:
        """"USD" or "BTC"; None for External or an id with no account."""
        account = self._accounts.get(account_id)
        return account.currency if account else None

    def kind(self, account_id: int | None) -> str | None:
        account = self._accounts.get(account_id)
        return account.kind if account else None

    def exchange_of(self, account_id: int | None) -> int | None:
        account = self._accounts.get(account_id)
        return account.exchange_id if account else None

    def usd_of(self, account_id: int | None) -> int | None:
        """An exchange account's exchange's dollar account."""
        return self._pair(account_id, "USD")

    def btc_of(self, account_id: int | None) -> int | None:
        """An exchange account's exchange's bitcoin account."""
        return self._pair(account_id, "BTC")

    def sends_1099da(self, account_id: int | None) -> bool:
        """Whether an exchange account's exchange sends a Form 1099-DA (5.7); no other account's does."""
        exchange = self.exchange_of(account_id)
        return exchange is not None and self._exchanges.get(exchange, ("", False))[1]

    def name(self, account_id: int | None) -> str:
        if account_id == ACCOUNT_EXTERNAL:
            return "External"
        account = self._accounts.get(account_id)
        return account.name if account else f"account {account_id} (missing)"

    def id_for(self, name: str) -> int | None:
        """A reserved name's id first (whatever that account is called now),
        then a current name's, ignoring case; None for a name it doesn't know."""
        key = name_key(clean_name(name))
        reserved = {name_key(n): i for n, i in RESERVED_NAMES.items()}
        return reserved.get(key, self._by_key.get(key))

    def yours(self) -> list[int]:
        """Your accounts' ids: banks, wallets, exchanges, hidden ones too;
        never a fee account or External."""
        return sorted(i for i, a in self._accounts.items() if a.kind in YOUR_KINDS)

    def _pair(self, account_id: int | None, currency: str) -> int | None:
        exchange = self.exchange_of(account_id)
        if exchange is None:
            return None
        return next((a.id for a in self._accounts.values() if a.exchange_id == exchange and a.currency == currency),
                    None)


def account_book(db: Session) -> AccountBook:
    accounts = [BookAccount(a.id, a.name, a.kind, a.currency, a.exchange_id, a.hidden)
                for a in db.query(Account).order_by(Account.id)]
    exchanges = {e.id: (e.name, e.sends_1099da) for e in db.query(Exchange)}
    return AccountBook(accounts, exchanges)


# ---------------------------------------------------------------------------
# Names (5.1)
# ---------------------------------------------------------------------------
def clean_name(text: str) -> str:
    """NFC, every run of spaces one ASCII space, trimmed of spaces and joiners."""
    text = "".join(" " if unicodedata.category(c) == "Zs" else c for c in unicodedata.normalize("NFC", text))
    return re.sub(" +", " ", text).strip(TRIMMED)


def name_key(name: str) -> str:
    """Two names are alike when this is the same: normalised, casefolded,
    the joiners left out (5.1)."""
    plain = "".join(c for c in unicodedata.normalize("NFC", name) if c not in JOINERS)
    return unicodedata.normalize("NFC", plain.casefold())


def _one_line(name: str, longest: int) -> None:
    """1 to `longest` characters, with no control or format character (but the joiners)."""
    if not 1 <= len(name) <= longest or any(_not_text(c) for c in name):
        raise HTTPException(status_code=400, detail=f"A name is 1 to {longest} characters on one line.")


def _not_text(c: str) -> bool:
    category = unicodedata.category(c)
    return category in ("Cc", "Zl", "Zp") or (category == "Cf" and c not in JOINERS)


def _free(db: Session, name: str) -> None:
    """No reserved name (5.1), and none alike another account's."""
    key = name_key(name)
    reserved = {name_key(n): i for n, i in RESERVED_NAMES.items()}
    if reserved.get(key) == ACCOUNT_EXTERNAL:
        raise HTTPException(status_code=400, detail=EXTERNAL)
    if reserved.get(key) in FIRST_OF_EACH:
        raise HTTPException(status_code=400, detail=RESERVED.format(name=name, kind=FIRST_OF_EACH[reserved[key]]))
    if key in reserved or any(name_key(n) == key for (n,) in db.query(Account.name)):
        raise HTTPException(status_code=400, detail=ALREADY.format(name=name))


def _free_exchange(db: Session, name: str) -> None:
    if name_key(name) == name_key("External"):
        raise HTTPException(status_code=400, detail=EXTERNAL)
    if any(name_key(n) == name_key(name) for (n,) in db.query(Exchange.name)):
        raise HTTPException(status_code=400, detail=EXCHANGE_ALREADY.format(name=name))


# ---------------------------------------------------------------------------
# Ids (5.1)
# ---------------------------------------------------------------------------
def _next_id(db: Session) -> int:
    """1 + the highest of 99, every account's id, every id a transaction or
    a ledger line names, and the last id given."""
    named = union_all(select(func.max(Account.id)), select(func.max(Transaction.from_account_id)),
                      select(func.max(Transaction.to_account_id)), select(func.max(LedgerEntry.account_id))).subquery()
    highest = db.scalar(select(func.max(named.c[0])))
    last = db.get(AppSetting, LAST_ID_KEY)
    return 1 + max(ACCOUNT_EXTERNAL, highest or 0, int(last.value) if last and last.value.isdigit() else 0)


# ---------------------------------------------------------------------------
# The API's work (5.9)
# ---------------------------------------------------------------------------
def add_account(db: Session, kind: str, name: str) -> list[Account]:
    """A bank or a wallet, or an exchange and its two accounts. The names
    are checked and the ids worked out under the write lock, so what another
    tab added meanwhile is seen, and two adds at once get two ids."""
    if not take_write_lock(db):
        raise HTTPException(status_code=503, detail=BUSY)
    try:
        made = _exchange(db, clean_name(name)) if kind == "exchange" else [_one(db, kind, clean_name(name))]
        save_setting(db, LAST_ID_KEY, str(max(a.id for a in made)))
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return made


def _one(db: Session, kind: str, name: str) -> Account:
    _one_line(name, LONGEST_NAME)
    _free(db, name)
    account = Account(id=_next_id(db), user_id=_owner(db), name=name, kind=kind,
                      currency="BTC" if kind == "wallet" else "USD")
    db.add(account)
    db.flush()
    return account


def _exchange(db: Session, name: str) -> list[Account]:
    _one_line(name, LONGEST_EXCHANGE_NAME)
    _free_exchange(db, name)
    for currency in ("USD", "BTC"):
        _free(db, f"{name} {currency}")
    exchange = Exchange(name=name)
    db.add(exchange)
    db.flush()
    first = _next_id(db)
    made = [Account(id=first + n, user_id=_owner(db), name=f"{name} {currency}", kind="exchange",
                    currency=currency, exchange_id=exchange.id) for n, currency in enumerate(("USD", "BTC"))]
    db.add_all(made)
    db.flush()
    return made


def _owner(db: Session) -> int:
    return db.query(User.id).order_by(User.id).limit(1).scalar()


def set_hidden(db: Session, account_id: int, hidden: bool) -> Account:
    """Hide or show an account (an exchange's: both of its accounts)."""
    account = _existing(db, account_id)
    if account.kind == "fee":
        raise HTTPException(status_code=400, detail=FEES_STAY)
    for each in _with_its_pair(db, account):
        each.hidden = hidden
    db.commit()
    return account


def delete_account(db: Session, account_id: int) -> None:
    """Delete an account no transaction names (an exchange's: the exchange
    and both of its accounts, when neither is named)."""
    account = _existing(db, account_id)
    if account.id in FIRST_OF_EACH:
        raise HTTPException(status_code=400, detail=FIRST_NOT_DELETED)
    if account.kind == "fee":
        raise HTTPException(status_code=400, detail=FEES_NOT_DELETED)
    if not take_write_lock(db):
        raise HTTPException(status_code=503, detail=BUSY)
    try:
        going = _with_its_pair(db, account)
        if _named_by_transactions(db, [a.id for a in going]):
            raise HTTPException(status_code=409, detail=IN_USE)
        for each in going:
            db.delete(each)
        if account.exchange_id is not None:
            db.delete(db.get(Exchange, account.exchange_id))
        db.commit()
    except BaseException:
        db.rollback()
        raise


def _existing(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    return account


def _with_its_pair(db: Session, account: Account) -> list[Account]:
    if account.exchange_id is None:
        return [account]
    return db.query(Account).filter(Account.exchange_id == account.exchange_id).order_by(Account.id).all()


def _named_by_transactions(db: Session, ids: list[int]) -> set[int]:
    rows = db.query(Transaction.from_account_id, Transaction.to_account_id).filter(
        Transaction.from_account_id.in_(ids) | Transaction.to_account_id.in_(ids))
    return {i for row in rows for i in row if i in ids}


def listed(db: Session, accounts: list[Account] | None = None) -> list[dict]:
    """Accounts as the API shows them: banks, wallets, exchanges, then the
    fee accounts 5 and 6 (an internal leftover isn't listed), each by id.
    Reads only."""
    if accounts is None:
        accounts = [a for a in db.query(Account) if a.kind != "fee" or a.id in FEE_ACCOUNTS]
    names = dict(db.query(Exchange.id, Exchange.name))
    used = _named_by_transactions(db, [a.id for a in accounts])
    return [{"id": a.id, "name": a.name, "kind": a.kind, "currency": a.currency, "exchange_id": a.exchange_id,
             "exchange": names.get(a.exchange_id), "hidden": bool(a.hidden), "in_use": a.id in used}
            for a in sorted(accounts, key=lambda a: (LIST_ORDER.get(a.kind, 4), a.id))]


def one(db: Session, account_id: int) -> dict:
    return listed(db, [_existing(db, account_id)])[0]
