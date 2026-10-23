"""
The account book (2.0 spec 5.4) and the account API's work (5.9).

One place answers every question about an account, from the accounts and
exchanges tables: `account_book(db)`, read once per request, import,
recalculation or report. Accounts are added by kind (an exchange as its
two, "<name> USD" and "<name> BTC"), renamed (an exchange's account: its
exchange and both of its accounts), hidden and shown, and deleted only
while nothing names them. Ids and names follow 5.1. The six fixed accounts
(database.FIXED_ACCOUNTS, put right at every start by seed_defaults) and
External (99, no account) are always there: 1-4 are never deleted (and may
take back the names reserved for them), 5 and 6 neither renamed, hidden nor
deleted, and an internal leftover (5.3) is never shown.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import event, func, select, union_all
from sqlalchemy.orm import Session

from backend.constants import ACCOUNT_BTC_FEES, ACCOUNT_EXTERNAL, ACCOUNT_USD_FEES, RESERVED_NAMES
from backend.database import ACCOUNT_BOOK, FIXED_ACCOUNTS, take_write_lock
from backend.models.account import Account
from backend.models.app_setting import AppSetting, save_setting
from backend.models.exchange import Exchange
from backend.models.transaction import LedgerEntry, Transaction
from backend.models.user import User

YOUR_KINDS = ("bank", "wallet", "exchange")
FEE_ACCOUNTS = (ACCOUNT_BTC_FEES, ACCOUNT_USD_FEES)
# Your first bank, wallet and exchange, never deleted (hidden, if unused)
FIRST_OF_EACH = {1: "bank", 2: "wallet", 3: "exchange", 4: "exchange"}
# The last account id ever given (5.1): no id is given twice, a restore keeps the higher
LAST_ID_KEY = "accounts_last_id"
# A last id as stored: ASCII digits, well inside SQLite's integers
LAST_ID = re.compile("[0-9]{1,18}")
LONGEST_NAME, LONGEST_EXCHANGE_NAME = 40, 36  # an exchange's leaves room for " USD"
# The one format characters a name keeps, inside it: some scripts and emoji need them
JOINERS = ("\u200c", "\u200d")
# Characters nothing shows (Unicode's Default_Ignorable_Code_Point, and the
# blank braille pattern): left out when names are compared and trimmed at a
# name's ends, so "Wallet" with one after it is "Wallet" (5.1). Those that
# are format characters, but the joiners, are refused in a name anyway.
INVISIBLE = ((0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5),
             (0x180B, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F), (0x2800, 0x2800),
             (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8),
             (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF))
# Variation selectors: invisible, but they make the symbol before them an
# emoji ("Cold \u2744\ufe0f"), so a name keeps them, at its ends too
VARIATION_SELECTORS = ((0xFE00, 0xFE0F), (0xE0100, 0xE01EF))
LIST_ORDER = {"bank": 0, "wallet": 1, "exchange": 2, "fee": 3}

BUSY = "Not saved: BitcoinTX was busy saving something else. Try again."
NOT_FOUND = "Account not found."
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
    exchange_id: int | None = None
    hidden: bool = False


class AccountBook:
    """Every question about an account, by id (or a name from a file)."""

    def __init__(self, accounts: Iterable[BookAccount], exchanges: dict[int, tuple[str, bool]] | None = None):
        # External is everything outside the ledger, never an account, whatever row an old database has as 99
        self._accounts = {a.id: a for a in accounts if a.id != ACCOUNT_EXTERNAL}
        self._exchanges = exchanges or {}
        self._by_key = {name_key(a.name): a.id for a in self._accounts.values()}

    def is_btc(self, account_id: int | None) -> bool:
        """One of your bitcoin accounts: a wallet, or an exchange's BTC account (5.1)."""
        account = self._accounts.get(account_id)
        return account is not None and account.kind in ("wallet", "exchange") and account.currency == "BTC"

    def is_yours(self, account_id: int | None) -> bool:
        """A bank, a wallet or an exchange's account, hidden ones too (5.1):
        never a fee account, External or an id with no account."""
        return self.kind(account_id) in YOUR_KINDS

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

    def exchange_name(self, account_id: int | None) -> str | None:
        """An exchange account's exchange's name; None for any other account."""
        exchange = self._exchanges.get(self.exchange_of(account_id))
        return exchange[0] if exchange else None

    def hidden(self, account_id: int | None) -> bool:
        account = self._accounts.get(account_id)
        return account is not None and account.hidden

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
        key = name_key(name)
        return RESERVED_KEYS.get(key, self._by_key.get(key))

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


# The session's book, kept in Session.info until its database transaction
# ends (or a write lock is taken: database.take_write_lock)
BOOK = ACCOUNT_BOOK


def account_book(db: Session) -> AccountBook:
    """The book from the accounts and exchanges tables, read once per
    database transaction (5.4: once per request, import, recalculation or
    report) and kept in the session until that transaction ends, so an
    account added since is in the next one."""
    if BOOK in db.info:
        return db.info[BOOK]
    accounts = [BookAccount(a.id, a.name, a.kind, a.currency, a.exchange_id, a.hidden)
                for a in db.query(Account).order_by(Account.id)]
    exchanges = {e.id: (e.name, e.sends_1099da) for e in db.query(Exchange)}
    db.info[BOOK] = book = AccountBook(accounts, exchanges)
    return book


# Any end of its transaction: a commit, a rollback, a close (a session used
# again after close() starts afresh) or a savepoint's
@event.listens_for(Session, "after_transaction_end")
def _forget_book(session: Session, _transaction) -> None:
    session.info.pop(BOOK, None)


def clean_name(text: str) -> str:
    """NFC, every run of spaces one ASCII space, trimmed of spaces and of
    characters nothing shows that a name may hold (a format character but
    the joiners stays, for the check to refuse)."""
    text = "".join(" " if unicodedata.category(c) == "Zs" else c for c in unicodedata.normalize("NFC", text))
    return _trimmed(re.sub(" +", " ", text))


def name_key(name: str) -> str:
    """Two names are alike when this is the same (5.1): normalised,
    casefolded, without what nothing shows, its spaces as clean_name's."""
    seen = "".join(c for c in unicodedata.normalize("NFC", name) if not _invisible(c))
    return clean_name(unicodedata.normalize("NFC", seen.casefold()))


def read_last_id(value: str | None) -> int | None:
    """A stored last account id, or None for none or one that isn't one."""
    return int(value) if isinstance(value, str) and LAST_ID.fullmatch(value) else None


def add_account(db: Session, kind: str, name: str) -> list[Account]:
    """A bank or a wallet, or an exchange and its two accounts. The names
    are checked and the ids worked out under the write lock, so what another
    tab added meanwhile is seen, and two adds at once get two ids."""
    _lock(db)
    try:
        made = _exchange(db, clean_name(name)) if kind == "exchange" else [_one(db, kind, clean_name(name))]
        save_setting(db, LAST_ID_KEY, str(max(a.id for a in made)))
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return made


def change_account(db: Session, account_id: int, name: str | None = None, hidden: bool | None = None) -> None:
    """Rename, hide or show an account (an exchange's: its exchange and both
    of its accounts), as one save. The name is checked under the write lock,
    so a name another tab took meanwhile is seen."""
    _lock(db)
    try:
        account = _existing(db, account_id)
        if account.kind == "fee":
            raise HTTPException(status_code=400, detail=FEES_STAY)
        if name is not None:
            _rename(db, account, clean_name(name))
        if hidden is not None:
            for each in _with_its_pair(db, account):
                each.hidden = hidden
        db.commit()
    except BaseException:
        db.rollback()
        raise


def delete_account(db: Session, account_id: int) -> None:
    """Delete an account nothing names (an exchange's: the exchange and both
    of its accounts, when neither is named)."""
    _lock(db)
    try:
        account = _existing(db, account_id)
        if account.id in FIRST_OF_EACH:
            raise HTTPException(status_code=400, detail=FIRST_NOT_DELETED)
        if account.kind == "fee":
            raise HTTPException(status_code=400, detail=FEES_NOT_DELETED)
        going = _with_its_pair(db, account)
        if _named(db, [a.id for a in going]):
            raise HTTPException(status_code=409, detail=IN_USE)
        exchange = db.get(Exchange, account.exchange_id) if account.exchange_id is not None else None
        for each in [*going, *([exchange] if exchange else [])]:
            db.delete(each)
        db.commit()
    except BaseException:
        db.rollback()
        raise


def listed(db: Session, accounts: list[Account] | None = None) -> list[dict]:
    """Accounts as the API shows them: banks, wallets, exchanges, then the
    fee accounts 5 and 6 (never an internal leftover), each by id. Reads only."""
    if accounts is None:
        accounts = [a for a in db.query(Account) if _shown(a)]
    exchanges = dict(db.query(Exchange.id, Exchange.name))
    used = _named(db, [a.id for a in accounts])
    return [{"id": a.id, "name": a.name, "kind": a.kind, "currency": a.currency, "exchange_id": a.exchange_id,
             "exchange": exchanges.get(a.exchange_id), "hidden": bool(a.hidden), "in_use": a.id in used}
            for a in sorted(accounts, key=lambda a: (LIST_ORDER.get(a.kind, len(LIST_ORDER)), a.id))]


def one(db: Session, account_id: int) -> dict:
    return listed(db, [_existing(db, account_id)])[0]


def _lock(db: Session) -> None:
    if not take_write_lock(db):
        raise HTTPException(status_code=503, detail=BUSY)


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
    first, owner = _next_id(db), _owner(db)
    made = [Account(id=first + n, user_id=owner, name=f"{name} {currency}", kind="exchange", currency=currency,
                    exchange_id=exchange.id) for n, currency in enumerate(("USD", "BTC"))]
    db.add_all(made)
    db.flush()
    return made


def _rename(db: Session, account: Account, name: str) -> None:
    """A bank's or a wallet's new name, or an exchange's and so its two
    accounts'; the same name again changes nothing."""
    if account.exchange_id is None:
        if name != account.name:
            _one_line(name, LONGEST_NAME)
            _free(db, name, own=(account.id,))
            account.name = name
        return
    exchange = db.get(Exchange, account.exchange_id)
    if exchange is None or name == exchange.name:
        return
    _one_line(name, LONGEST_EXCHANGE_NAME)
    _free_exchange(db, name, own=exchange.id)
    halves = _with_its_pair(db, account)
    for half in halves:
        _free(db, f"{name} {half.currency}", own=tuple(h.id for h in halves))
    exchange.name = name
    for half in halves:
        half.name = f"{name} {half.currency}"


def _one_line(name: str, longest: int) -> None:
    """1 to `longest` characters, with no control or format character (but the joiners)."""
    if not 1 <= len(name) <= longest or any(_not_text(c) for c in name):
        raise HTTPException(status_code=400, detail=f"A name is 1 to {longest} characters on one line.")


def _free(db: Session, name: str, own: tuple[int, ...] = ()) -> None:
    """No reserved name (5.1) but one reserved for an account being renamed
    (`own`: 1 to 4 can be renamed back), and none alike another account's."""
    key = name_key(name)
    reserved = RESERVED_KEYS.get(key)
    if reserved == ACCOUNT_EXTERNAL:
        raise HTTPException(status_code=400, detail=EXTERNAL)
    if reserved in FIRST_OF_EACH and reserved not in own:
        raise HTTPException(status_code=400, detail=RESERVED.format(name=name, kind=FIRST_OF_EACH[reserved]))
    if (reserved is not None and reserved not in own) \
            or any(name_key(n) == key for i, n in db.query(Account.id, Account.name) if i not in own):
        raise HTTPException(status_code=400, detail=ALREADY.format(name=name))


def _free_exchange(db: Session, name: str, own: int | None = None) -> None:
    """Not External, and none alike another exchange's name (`own` is the one being renamed)."""
    if RESERVED_KEYS.get(name_key(name)) == ACCOUNT_EXTERNAL:
        raise HTTPException(status_code=400, detail=EXTERNAL)
    if any(name_key(n) == name_key(name) for i, n in db.query(Exchange.id, Exchange.name) if i != own):
        raise HTTPException(status_code=400, detail=EXCHANGE_ALREADY.format(name=name))


def _next_id(db: Session) -> int:
    """1 + the highest of 99, every account's id, every id a transaction or
    a ledger line names, and the last id given."""
    named = union_all(select(func.max(Account.id)), select(func.max(Transaction.from_account_id)),
                      select(func.max(Transaction.to_account_id)), select(func.max(LedgerEntry.account_id))).subquery()
    highest = db.scalar(select(func.max(named.c[0])))
    last = db.get(AppSetting, LAST_ID_KEY)
    return 1 + max(ACCOUNT_EXTERNAL, highest or 0, read_last_id(last.value if last else None) or 0)


def _owner(db: Session) -> int:
    return db.query(User.id).order_by(User.id).limit(1).scalar()


def _existing(db: Session, account_id: int) -> Account:
    """An account the API shows, or 404."""
    account = db.get(Account, account_id)
    if account is None or not _shown(account):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return account


def _shown(account: Account) -> bool:
    """Not an internal leftover (5.3): a fee account but 5 and 6, or a row with External's id."""
    return account.id != ACCOUNT_EXTERNAL and (account.kind != "fee" or account.id in FEE_ACCOUNTS)


def _with_its_pair(db: Session, account: Account) -> list[Account]:
    if account.exchange_id is None:
        return [account]
    return db.query(Account).filter(Account.exchange_id == account.exchange_id).order_by(Account.id).all()


def _named(db: Session, ids: list[int]) -> set[int]:
    """Which of these accounts a transaction or a ledger line names."""
    rows = db.query(Transaction.from_account_id, Transaction.to_account_id).filter(
        Transaction.from_account_id.in_(ids) | Transaction.to_account_id.in_(ids))
    lines = db.query(LedgerEntry.account_id).filter(LedgerEntry.account_id.in_(ids))
    return {i for row in [*rows, *lines] for i in row if i in ids}


def _not_text(c: str) -> bool:
    category = unicodedata.category(c)
    return category in ("Cc", "Zl", "Zp") or (category == "Cf" and c not in JOINERS)


def _invisible(c: str) -> bool:
    return _in(c, INVISIBLE)


def _in(c: str, ranges: tuple) -> bool:
    return any(low <= ord(c) <= high for low, high in ranges)


def _trimmed(text: str) -> str:
    start, end = 0, len(text)
    while start < end and _trimmable(text[start]):
        start += 1
    while end > start and _trimmable(text[end - 1]):
        end -= 1
    return text[start:end]


def _trimmable(c: str) -> bool:
    return c == " " or (_invisible(c) and not _not_text(c) and not _in(c, VARIATION_SELECTORS))


# Reserved names (5.1) by their comparison key
RESERVED_KEYS = {name_key(name): account_id for name, account_id in RESERVED_NAMES.items()}


# 1.x's six accounts and its one exchange, as seed_defaults makes them: what
# a file can name until B5a (the reserved names), so the CSV and AI imports'
# book when they're given none
FIXED_BOOK = AccountBook((BookAccount(**a) for a in FIXED_ACCOUNTS), {1: ("Exchange", True)})
