"""
The ledger engine. A transaction is saved as the user entered it; from it
come its debit and credit lines and its effect on the BTC lots: a Deposit
or Buy acquires a lot, a Sell or Withdrawal disposes of the account's
oldest BTC first (FIFO), a Transfer moves lots between accounts, and a BTC
network fee is a disposal of its own. Every edit or delete recalculates the
whole ledger in time order ("scorched earth", recalculate_all_transactions),
so everything derived must follow from the saved transactions alone.
"""

import logging
import unicodedata
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from backend.models.transaction import (Transaction, LedgerEntry, BitcoinLot, LotDisposal)
from backend.models.account import Account
from backend.schemas.transaction import validate_btc_storable, validate_usd_storable
from backend.services import hourly_prices, price_history
from backend.services.tax_time import DateOutOfRange, as_utc, date_out_of_range, get_tax_timezone, local_date, local_noon_utc
from backend.constants import (
    ACCOUNT_WALLET,
    ACCOUNT_BANK,
    ACCOUNT_EXCHANGE_USD,
    ACCOUNT_EXCHANGE_BTC,
    ACCOUNT_EXTERNAL,
    BROKER_REPORTING_TYPES,
    BTC_ACCOUNTS,
    GIFT_LIKE_PURPOSES,
    INHERITED_SOURCE,
    ORIGINAL_DATE_SOURCES,
    VALUED_AT_RECEIPT,
    normalized,
)

CENT = Decimal("0.01")
# How an exact half cent of a share goes (a lot's cost, a disposal's
# proceeds): up, as the IRS rounds to whole dollars (#100)
SHARE_ROUNDING = ROUND_HALF_UP

logger = logging.getLogger(__name__)


def get_all_transactions(db: Session):
    """Every transaction, newest first."""
    return (
        db.query(Transaction)
        .order_by(Transaction.timestamp.desc())
        .all()
    )


def get_transaction_by_id(db: Session, transaction_id: int):
    """The transaction, or None."""
    return db.query(Transaction).filter(Transaction.id == transaction_id).first()


def create_transaction_record(tx_data: dict, db: Session, auto_commit: bool = True) -> Transaction:
    """
    Save a new transaction: check and complete its input, then add its
    ledger lines and its effect on the lots. One dated before the latest
    transaction recalculates the whole ledger, so FIFO stays in time order.
    auto_commit=False leaves the commit to the caller (an import commits
    once, for all its rows). A price the save needs once it holds SQLite's
    write lock (a Spent's proceeds, priced once it's written; an old row's
    missing value, in a recalculation) is looked for with the lock free
    (hourly_prices.with_prices_found, #426); in an import, by the import.
    """
    return hourly_prices.with_prices_found(db, lambda: _create(tx_data, db, auto_commit), tx_data)


def _create(tx_data: dict, db: Session, auto_commit: bool) -> Transaction:
    ensure_fee_account_exists(db)
    _prepare_input(tx_data, db)
    new_tx = _insert(tx_data, db)

    remove_ledger_entries_for_tx(new_tx, db)
    build_ledger_entries_for_transaction(new_tx, tx_data, db)
    _maybe_verify_balance_for_internal(new_tx, db)
    if new_tx.type == "Transfer":
        _default_btc_transfer_fee(new_tx, db)
    if _is_backdated(new_tx, db):
        # Every lot is rebuilt in date order, which also checks the new entry
        # against the account as it was on its date. Checked first against
        # today's lots, a past consolidation (#159) was refused once coins
        # had left the account later, though only its fee leaves it.
        _recalculate_with(new_tx, db)
    else:
        _post_lots(new_tx, tx_data, db)

    if auto_commit:
        db.commit()
        db.refresh(new_tx)
    return new_tx


def _prepare_input(tx_data: dict, db: Session) -> None:
    """Check a new transaction's input against the ledger's rules, and
    complete it: canonical spellings, the fee's currency, the gross
    proceeds, an income deposit's value, a BTC fee's USD value."""
    _validate_transaction(tx_data, db)
    _fill_fee_currency(tx_data, db)
    _enforce_transaction_type_rules(tx_data, db)
    _enforce_fee_rules(tx_data, db)
    _enforce_broker_reporting(tx_data.get("type"), tx_data.get("broker_reporting"))
    _record_gross_proceeds(tx_data)
    with _priced_at_the_day(db, _prices_at_the_day(tx_data)):
        _mark_income_value(tx_data, priced=_value_at_receipt(tx_data, db), db=db)
        _mark_gift_value(tx_data, priced=_value_blank_gift(tx_data, db))
        _value_btc_fee(tx_data, db, manual=tx_data.get("fee_usd") is not None)
    if tx_data.get("fee_usd_from_price") and tx_data.get("fee_usd") is not None:
        # A CSV re-import of a value once priced (not typed): kept as it
        # was, and still re-priced if the time or fee changes.
        tx_data["fee_usd_manual"] = False
    tx_data["proceeds_from_price"] = bool(tx_data.get("proceeds_from_price")) and _is_spent(tx_data) \
        and tx_data.get("gross_proceeds_usd") is not None
    tx_data["price_moment"] = _price_moment(tx_data)


PRICE_MOMENTS = ("hour", "day")


def _prices_at_the_day(tx_data: dict) -> bool:
    """An import's values priced at the day (a file without the moment means
    the day): a value priced now takes the day too, so the transaction's
    priced values share one price."""
    imported = tx_data.get("cost_basis_from_price") or tx_data.get("proceeds_from_price") \
        or tx_data.get("fee_usd_from_price") or tx_data.get("fmv_from_price")
    return tx_data.get("price_moment") == "day" or bool(imported and not tx_data.get("price_moment"))


def values_the_save_prices(tx_data: dict, db: Session) -> list[tuple[str, datetime, str]]:
    """
    The values a new transaction's save fills from the BTC price, and won't
    save without (#125): (the field, the moment it's priced at, "hour" or
    "day"). An "hour" falls back to that day's price, as _price_at does.
    These are a BTC fee's USD value, an income, rebate or inherited
    deposit's basis (an inheritance's at its date of death), and a Spent's
    proceeds, each left out. A gift's value is filled only when there is a
    price, so it's never one.
    """
    moment = tx_data.get("timestamp") or datetime.now(timezone.utc)
    at = "day" if _prices_at_the_day(tx_data) else "hour"
    values = []
    if _valued_at_receipt(tx_data, db) and Decimal(tx_data.get("cost_basis_usd") or 0) <= 0 \
            and Decimal(tx_data.get("amount") or 0) > 0:
        if _is_inherited(tx_data):
            day = date_of_death(tx_data.get("acquired_at") or moment, db)
            values.append(("cost_basis_usd", datetime(day.year, day.month, day.day, tzinfo=timezone.utc), "day"))
        else:
            values.append(("cost_basis_usd", moment, at))
    if _has_btc_fee(tx_data) and tx_data.get("fee_usd") is None:
        values.append(("fee_usd", moment, at))
    if _is_spent(tx_data) and tx_data.get("from_account_id") in BTC_ACCOUNTS and tx_data.get("proceeds_usd") is None:
        values.append(("proceeds_usd", moment, _spent_proceeds_moment(tx_data, at)))
    return values


def _spent_proceeds_moment(tx_data: dict, at: str) -> str:
    """Where a Spent's proceeds left out are priced: at the moment its fee's
    value has when that comes from a price (priced at save, at `at`, or an
    import's, at its price_moment or else the day), else at the hour. The
    save prices them last (_withdrawal_gross_proceeds), at the price_moment
    _prepare_input stores (_price_moment)."""
    if not _has_btc_fee(tx_data):
        return "hour"
    if tx_data.get("fee_usd") is None:
        return at
    if tx_data.get("fee_usd_from_price"):
        return tx_data["price_moment"] if tx_data.get("price_moment") in PRICE_MOMENTS else "day"
    return "hour"


def _has_priced_value(data) -> bool:
    """Whether a transaction (or its input) holds a value that came from a
    price: an income or rebate basis, a Spent's proceeds, a gift's,
    donation's or lost coins' value, a BTC fee's value. A mark without its
    value (a deposit moved to Bank) isn't one."""
    get = data.get if isinstance(data, dict) else lambda key: getattr(data, key)
    return bool((get("cost_basis_from_price") and get("cost_basis_usd") is not None)
                or (get("proceeds_from_price") and get("gross_proceeds_usd") is not None)
                or (get("fmv_from_price") and get("fmv_usd") is not None)
                or (get("fee_usd") is not None and not get("fee_usd_manual")))


def _note_moment(data: dict, moment: str) -> None:
    """Record the moment a value was just priced at: the day wins, so a
    transaction with any value at the day's price is listed by Ledger Review."""
    data["price_moment"] = "day" if "day" in (data.get("price_moment"), moment) else moment


def _price_moment(data) -> str | None:
    """The moment of its priced values' price: the one they were just priced
    at, or one an import says; "day" for an import that doesn't say (every
    value priced before hourly prices was priced at the day); None when
    every value is typed."""
    if not _has_priced_value(data):
        return None
    moment = data.get("price_moment") if isinstance(data, dict) else data.price_moment
    return moment if moment in PRICE_MOMENTS else "day"


def _is_spent(data: dict) -> bool:
    kind = getattr(data.get("type"), "value", data.get("type"))
    return kind == "Withdrawal" and normalized(data.get("purpose")) == "spent"


def counts_as_spent(tx: Transaction) -> bool:
    """
    Whether a BTC withdrawal counts as Spent: its purpose is Spent, or one
    BitcoinTX doesn't know (only a ledger from before 0.9.2 holds one, such
    as "Expenses", or none). A withdrawal of bitcoin is spent, given,
    donated or lost, and an expense paid with it is a spend (the owner's
    rule, #61); Ledger Review lists those until the owner chooses.
    """
    return tx.type == "Withdrawal" and tx.from_account_id in BTC_ACCOUNTS \
        and normalized(tx.purpose) not in GIFT_LIKE_PURPOSES


def received_known(tx: Transaction) -> bool:
    """Whether what a withdrawal counted as Spent received is known: a
    Spent's always is (typed, or priced), one of unknown purpose only when an
    amount above $0 is recorded (#61). Until then it stays as it was, a $0
    sale with its fee at its value, and no 0 is written over what's stored
    (#329). Spent here is the spelling versions 0.8.0 to 0.9.1 matched
    (_spent_as_matched): an old " spent " (#342) is known only as an
    unknown purpose is."""
    return _spent_as_matched(tx) or Decimal(tx.gross_proceeds_usd or 0) > 0


def _spent_as_matched(tx: Transaction) -> bool:
    """Spent in any case, without trimming: the purpose 0.8.0 to 0.9.1 took
    a BTC fee offset off, and priced a missing amount for. To them " spent "
    was a purpose they didn't know, so recovering its gross follows the
    unknown purpose's rules (#61, #329), not a Spent's."""
    return (tx.purpose or "").lower() == "spent"


def listed_spelling(value, choices) -> str | None:
    """A saved purpose or source in its listed spelling (" gift " is Gift),
    as the screens show it (#342); other text as saved."""
    return _canonical(value, choices) or value


def _is_gift_like(data) -> bool:
    """A Gift, Donation or Lost withdrawal from a BTC account (a transaction or its input)."""
    get = data.get if isinstance(data, dict) else lambda key: getattr(data, key)
    kind = getattr(get("type"), "value", get("type"))
    return kind == "Withdrawal" and get("from_account_id") in BTC_ACCOUNTS \
        and normalized(get("purpose")) in GIFT_LIKE_PURPOSES


def _gift_value_at(amount, when: datetime, db: Session) -> tuple[Decimal, str] | None:
    """(the amount's value at the price that values `when`, that price's
    moment), or None without a price: a gift's value is on no form BitcoinTX
    fills (the deduction and the gift-tax limit it counts toward are the owner's
    to claim), so it stays blank for the owner to type, never a 422."""
    try:
        priced = _price_at(when, db)
    except HTTPException:
        return None
    return (priced.usd * Decimal(amount)).quantize(CENT), priced.moment


def _value_blank_gift(tx_data: dict, db: Session) -> bool:
    """A Gift, Donation or Lost withdrawal entered with a blank value (#255):
    the BTC price when its hour began (that day's where there's no hourly
    price) x the amount, as a blank income value and a Spent's proceeds are.
    A typed value, $0 included, is kept. Returns True when it filled it."""
    if not _is_gift_like(tx_data) or tx_data.get("fmv_usd") is not None or Decimal(tx_data.get("amount") or 0) <= 0:
        return False
    found = _gift_value_at(tx_data["amount"], tx_data.get("timestamp") or datetime.now(timezone.utc), db)
    if found is None:
        return False
    tx_data["fmv_usd"] = found[0]
    _note_moment(tx_data, found[1])
    return True


def _mark_gift_value(tx_data: dict, priced: bool) -> None:
    """fmv_from_price: the value was just priced, or an import says it once
    was (a CSV re-import, the AI's autofill), on a gift-like withdrawal.
    Anything else is typed."""
    tx_data["fmv_from_price"] = priced or (
        bool(tx_data.get("fmv_from_price")) and _is_gift_like(tx_data) and tx_data.get("fmv_usd") is not None
    )


def _mark_income_value(tx_data: dict, priced: bool, db: Session) -> None:
    """cost_basis_from_price: the value was just priced, or an
    import says it once was (a CSV re-import, the AI's autofill), on an
    income or rebate deposit into a BTC account. Anything else is typed."""
    tx_data["cost_basis_from_price"] = priced or (
        bool(tx_data.get("cost_basis_from_price")) and _valued_at_receipt(tx_data, db)
    )


def _insert(tx_data: dict, db: Session) -> Transaction:
    now_utc = datetime.now(timezone.utc)
    new_tx = Transaction(
        from_account_id=tx_data.get("from_account_id"),
        to_account_id=tx_data.get("to_account_id"),
        type=tx_data.get("type"),
        amount=tx_data.get("amount"),
        fee_amount=tx_data.get("fee_amount"),
        fee_currency=tx_data.get("fee_currency"),
        timestamp=tx_data.get("timestamp", now_utc),
        source=tx_data.get("source"),
        purpose=tx_data.get("purpose"),
        broker_reporting=tx_data.get("broker_reporting"),
        cost_basis_usd=tx_data.get("cost_basis_usd"),
        proceeds_usd=tx_data.get("proceeds_usd"),
        gross_proceeds_usd=tx_data.get("gross_proceeds_usd"),
        fmv_usd=tx_data.get("fmv_usd"),
        fee_usd=tx_data.get("fee_usd"),
        fee_usd_manual=tx_data.get("fee_usd_manual", False),
        cost_basis_from_price=tx_data.get("cost_basis_from_price", False),
        acquired_at=tx_data.get("acquired_at"),
        price_moment=tx_data.get("price_moment"),
        proceeds_from_price=tx_data.get("proceeds_from_price", False),
        fmv_from_price=tx_data.get("fmv_from_price", False),
        created_at=now_utc,
        updated_at=now_utc
    )
    db.add(new_tx)
    db.flush()  # new_tx.id is now available
    return new_tx


# A saved row naming an account that doesn't exist (an id saved before 0.9.2,
# F28; none, where an account it named was deleted) whose replay fails its
# balance check: the refusal names it (#337). An edit or a delete of one
# goes past the others (#368), which the text says.
ACCOUNT_MISSING = (
    "Transaction {id} (a {kind} of {date}) {what}. Edit it into one of your accounts, or delete it. "
    "Ledger Review lists every such transaction; if it lists more than one that stops saves, fix them one at a "
    "time: an edit or a delete of one goes past the others."
)


# An edit or a delete that went past such rows (#368) and left a later
# transaction short of BTC: the rows it went past may be why.
MISSING_MAY_BE_WHY = (
    "a later transaction would run short of BTC. It may depend on this one; or {rows}, which {names} a missing "
    "account, or another that Ledger Review lists, may be why: fix that one first (edit it into one of your "
    "accounts, or delete it). "
)


class AccountMissing(HTTPException):
    """The replay stopped on a transaction naming a missing account: a 400
    that names it, which a save, an add or a delete passes on as it is."""

    def __init__(self, tx: Transaction, missing: list[int | None], day: date):
        super().__init__(status_code=400, detail=ACCOUNT_MISSING.format(
            id=tx.id, kind=tx.type, date=day.isoformat(), what=what_is_missing(missing)))


def missing_accounts(tx: Transaction, known: set[int]) -> list[int | None]:
    """The accounts a transaction names that aren't in `known` (the accounts'
    ids and External), None for a side that names none."""
    return [a for a in (tx.from_account_id, tx.to_account_id) if a not in known]


def what_is_missing(missing: list[int | None]) -> str:
    """"names account 999, which doesn't exist (a BitcoinTX before 0.9.2
    saved it)", "names no account on one side (the one it named was
    deleted)", or both."""
    named = [a for a in missing if a is not None]
    parts = []
    if named:
        ids = " and ".join(str(a) for a in named)
        parts.append(f"names account {ids}, which doesn't exist" if len(named) == 1
                     else f"names accounts {ids}, which don't exist")
        parts[-1] += " (a BitcoinTX before 0.9.2 saved it)"
    if None in missing:
        parts.append("names no account on one side (the one it named was deleted)" if missing.count(None) == 1
                     else "names no account on either side (the ones it named were deleted)")
    return ", and ".join(parts)


def known_accounts(db: Session) -> set[int]:
    """The ids a transaction may name: every account's, and External."""
    return {account_id for (account_id,) in db.query(Account.id)} | {ACCOUNT_EXTERNAL}


def _recalculate_with(new_tx: Transaction, db: Session) -> None:
    """The whole ledger again, in date order, with a new past entry. Short of
    BTC, the message names the entry that runs short, which may be a later
    one: it says so (as a delete does)."""
    try:
        recalculate_all_transactions(db)
    except HTTPException as e:
        if e.status_code != 400 or isinstance(e, AccountMissing):
            raise
        raise HTTPException(
            status_code=400,
            detail=f"Not saved: with it, the account would lack BTC on its date or later. {e.detail}",
        ) from e


def _is_backdated(new_tx: Transaction, db: Session) -> bool:
    """Whether a new transaction is dated before the latest one: it changes
    which lots the later ones used, so everything is recalculated, in time
    order."""
    latest_other_tx = (
        db.query(Transaction)
        .filter(Transaction.id != new_tx.id)
        .order_by(Transaction.timestamp.desc())
        .first()
    )
    if latest_other_tx and new_tx.timestamp < latest_other_tx.timestamp:
        # DEBUG only, like every line naming a transaction's date or amount
        logger.debug(
            f"[Backdated Create] New tx {new_tx.id} at {new_tx.timestamp} is earlier than "
            f"existing tx {latest_other_tx.id} at {latest_other_tx.timestamp}. Triggering recalculation."
        )
        return True
    return False


_VALIDATED_FIELDS = (
    "type", "timestamp", "from_account_id", "to_account_id", "amount", "fee_amount", "fee_currency",
    "cost_basis_usd", "proceeds_usd", "gross_proceeds_usd", "fmv_usd", "fee_usd", "source", "purpose", "acquired_at",
)

# What each type takes as input. A Sell's or Withdrawal's cost basis (and a
# Sell's net proceeds) is worked out from its lots on every recalculation.
_TYPE_INPUTS = {
    "Deposit": ("source", "cost_basis_usd"),
    "Buy": ("cost_basis_usd",),
    "Sell": ("proceeds_usd", "gross_proceeds_usd"),
    "Withdrawal": ("purpose", "proceeds_usd", "gross_proceeds_usd", "fmv_usd"),
    "Transfer": (),
}
_TYPE_FIELDS = ("purpose", "source", "cost_basis_usd", "proceeds_usd", "gross_proceeds_usd", "fmv_usd")


def update_transaction_record(transaction_id: int, tx_data: dict, db: Session):
    """
    Change a transaction (only the fields in tx_data), checked as the whole
    transaction it becomes, then recalculate the whole ledger. None when it
    doesn't exist. One naming a missing account is fixed past the others
    that do (#368), as a delete of one is. A price the recalculation needs
    is looked for with the lock free (hourly_prices.with_prices_found, #426).
    """
    return hourly_prices.with_prices_found(db, lambda: _update(transaction_id, tx_data, db), tx_data)


def _update(transaction_id: int, tx_data: dict, db: Session):
    tx = get_transaction_by_id(db, transaction_id)
    if not tx:
        return None

    past = [] if missing_accounts(tx, known_accounts(db)) else None
    old_timestamp = tx.timestamp
    type_changed = _drop_fields_of_old_type(tx, tx_data)
    _check_inherited_date_sent(tx, tx_data, db)
    _drop_original_date_if_not_allowed(tx, tx_data, db)
    with _priced_at_the_day(db, _keeps_a_day_price(tx, tx_data)):
        _check_edit(tx, tx_data, type_changed, db)
        _revalue_btc_fee(tx, tx_data, db)
        _revalue_spent_proceeds(tx, tx_data, db)
        _revalue_gift(tx, tx_data, db)
    _apply_edit(tx, tx_data, type_changed)
    tx.price_moment = _price_moment(tx)
    tx.updated_at = datetime.now(timezone.utc)
    db.flush()

    # One full recalculation handles every edit, a backdated one included:
    # replaying only from the new date left the earlier lots short of the
    # BTC the old version of the transaction had used.
    logger.debug(
        f"[Update] Tx {tx.id} timestamp {old_timestamp} => {tx.timestamp}. "
        f"Running scorched earth re-lot."
    )
    _recalculate_past(tx, past, db)

    db.commit()
    db.refresh(tx)
    return tx


def _recalculate_past(edited: Transaction, past: list[Transaction] | None, db: Session) -> None:
    """The replay after an edit, past the other rows naming a missing
    account when the edited one named one (#368). It goes past only the
    others: the edited row must pass its own balance check."""
    try:
        recalculate_all_transactions(db, past_missing=past)
    except HTTPException as e:
        if e.status_code != 400 or isinstance(e, AccountMissing) or not past:
            raise
        _refuse_if_still_missing(edited, past, db)
        raise HTTPException(status_code=400, detail=f"Not changed: {_why_short(past, db)}{e.detail}") from e
    _refuse_if_still_missing(edited, past, db)


def _refuse_if_still_missing(edited: Transaction, past: list[Transaction] | None, db: Session) -> None:
    """An edit that leaves its row failing its balance check on a missing
    account is refused by name, as without #368."""
    if past and edited in past:
        missing = missing_accounts(edited, known_accounts(db))
        raise AccountMissing(edited, missing, local_date(edited.timestamp, get_tax_timezone(db)))


def _drop_fields_of_old_type(tx: Transaction, tx_data: dict) -> bool:
    """
    A type change keeps only the fields the new type takes too (unless the
    edit sends them): a Gift changed into a Sell kept purpose "Gift" and was
    left off Form 8949; a withdrawal changed into an income deposit kept its
    FIFO cost basis as the income. The figures are then worked out afresh.
    Whether the type changes.
    """
    new_type = getattr(tx_data.get("type"), "value", tx_data.get("type"))
    type_changed = "type" in tx_data and new_type != tx.type
    if type_changed:
        kept = set(_TYPE_INPUTS.get(tx.type, ())) & set(_TYPE_INPUTS.get(new_type, ()))
        for key in _TYPE_FIELDS:
            if key in tx_data or key in kept:
                continue
            if key == "gross_proceeds_usd" and "proceeds_usd" in tx_data:
                continue  # a proceeds edit is the new gross (_apply_edit)
            tx_data[key] = None
    return type_changed


def _check_inherited_date_sent(tx: Transaction, tx_data: dict, db: Session) -> None:
    """
    A BTC deposit's source changed to or from Inherited must say its date in
    the same edit (#154): a date of death and a date originally acquired
    aren't the same date, and the stored one would silently become the other
    (a Gift entered with the person's purchase date, then made Inherited, was
    priced and sorted by that purchase date). A row that takes no date after
    the edit (a dollar deposit, an income source) has none to carry over.
    """
    if "source" not in tx_data or "acquired_at" in tx_data:
        return
    edited = {k: tx_data.get(k, getattr(tx, k)) for k in ("type", "source", "to_account_id")}
    to_acct = db.get(Account, edited["to_account_id"]) if edited["to_account_id"] else None
    if not _takes_original_date(getattr(edited["type"], "value", edited["type"]), edited["source"], to_acct):
        return
    was, becomes = _is_inherited({"source": tx.source}), _is_inherited(tx_data)
    if becomes and not was:
        _bad("Changing a deposit's source to Inherited needs its date of death (acquired_at) in the same edit.")
    if was and not becomes and tx.acquired_at is not None:
        _bad("Changing an Inherited deposit to My BTC or Gift needs its date originally acquired (acquired_at, "
             "or null for the deposit's date) in the same edit.")


def _drop_original_date_if_not_allowed(tx: Transaction, tx_data: dict, db: Session) -> None:
    """An edit that makes the row something other than a My BTC, Gift or
    Inherited deposit into a BTC account drops its date originally acquired
    (unless it sends one, which the checks then refuse)."""
    if tx.acquired_at is None or "acquired_at" in tx_data:
        return
    edited = {k: tx_data.get(k, getattr(tx, k)) for k in ("type", "source", "to_account_id")}
    to_acct = db.get(Account, edited["to_account_id"]) if edited["to_account_id"] else None
    if not _takes_original_date(getattr(edited["type"], "value", edited["type"]), edited["source"], to_acct):
        tx_data["acquired_at"] = None


def _check_edit(tx: Transaction, tx_data: dict, type_changed: bool, db: Session) -> None:
    """
    Check the transaction as it will be after the change (a partial edit
    checked on the fields sent only failed with "Unknown transaction type:
    None" or let a mismatch through), and complete the edit as a new
    transaction's input is completed.
    """
    merged = {k: getattr(tx, k) for k in _VALIDATED_FIELDS}
    merged.update({k: v for k, v in tx_data.items() if k in _VALIDATED_FIELDS})
    # Only a source this edit sets (or a new type) is checked against the list
    check_source = ("source" in tx_data and tx_data["source"] != tx.source) or type_changed
    # Text an edit leaves as stored stays as it is (rows saved before the
    # one-line rule load and edit; the form sends them back unchanged)
    kept_text = frozenset(k for k in ("purpose", "source") if tx_data.get(k, getattr(tx, k)) == getattr(tx, k))
    _validate_transaction(merged, db, check_source=check_source, kept_text=kept_text, stored=tx)
    if _fill_fee_currency(merged, db):  # e.g. a fee_amount sent on its own
        tx_data["fee_currency"] = merged["fee_currency"]
    # Canonical spellings, whole seconds, and what a dollar withdrawal can't hold dropped
    for key in ("type", "purpose", "source", "timestamp", "acquired_at", *_BTC_WITHDRAWAL_VALUES):
        if merged.get(key) != getattr(tx, key) or key in tx_data:
            tx_data[key] = merged.get(key)
    if any(k in tx_data for k in ("type", "from_account_id", "to_account_id")):
        _enforce_transaction_type_rules(merged, db)
    if any(k in tx_data for k in ("fee_amount", "fee_currency", "type", "amount", "from_account_id",
                                  "to_account_id")):
        _enforce_fee_rules(merged, db)
    _revalue_income_deposit(tx, tx_data, db)


# What an income, rebate or inherited deposit's value depends on: the price
# x the amount (the hour's when received; an inheritance's, the day's of the
# date of death in acquired_at), and whether it is one into a BTC account.
_INCOME_VALUE_INPUTS = ("type", "source", "to_account_id", "amount", "timestamp", "acquired_at")


def _revalue_income_deposit(tx: Transaction, tx_data: dict, db: Session) -> None:
    """
    An income or rebate deposit's value after an edit (#76). A typed one is
    kept. One that came from a price, or a blank or $0 one (the form sends 0
    for a blank), is valued again at the hour's price (an inheritance: its
    date of death's day price) when the edit changes what it depends on:
    the account, amount or hour (date of death), or a source not
    valued at receipt becoming one (_income_inputs_changed). A type change
    makes the row's figure its own, typed.
    """
    if not any(k in tx_data for k in _INCOME_VALUE_INPUTS + ("cost_basis_usd",)):
        return
    edited = {k: tx_data.get(k, getattr(tx, k)) for k in _INCOME_VALUE_INPUTS + ("cost_basis_usd",)}
    if not _valued_at_receipt(edited, db):
        # Moved to Bank or to another source, the mark stays (and is unused):
        # moved back with a new amount, the value is priced again. A value
        # typed meanwhile, or another type's figure, is the user's.
        is_deposit = getattr(edited["type"], "value", edited["type"]) == "Deposit"
        if not is_deposit or _typed_basis(tx, tx_data):
            tx_data["cost_basis_from_price"] = False
        if is_deposit and "cost_basis_usd" not in tx_data and not _into_btc(edited, db):
            # A USD deposit has no basis: one left from a BTC account by a
            # partial edit was counted as income on the report
            tx_data["cost_basis_usd"] = None
        return
    if _typed_basis(tx, tx_data):
        tx_data["cost_basis_from_price"] = False
        return
    if tx.cost_basis_from_price and _income_inputs_changed(tx, tx_data, db):
        edited["cost_basis_usd"] = None
    if _value_at_receipt(edited, db):
        tx_data["cost_basis_usd"] = edited["cost_basis_usd"]
        tx_data["cost_basis_from_price"] = True
        _note_moment(tx_data, edited["price_moment"])


def _typed_basis(tx: Transaction, tx_data: dict) -> bool:
    """Whether the edit types a value: a positive cost_basis_usd that isn't
    the stored price-derived one sent back (the form sends the value it
    shows)."""
    if "cost_basis_usd" not in tx_data or Decimal(tx_data["cost_basis_usd"] or 0) <= 0:
        return False
    sent = Decimal(tx_data["cost_basis_usd"]).quantize(Decimal("0.01"))
    return not (tx.cost_basis_from_price and tx.cost_basis_usd is not None
                and sent == Decimal(tx.cost_basis_usd).quantize(Decimal("0.01")))


def _income_inputs_changed(tx: Transaction, tx_data: dict, db: Session) -> bool:
    """Whether the edit changes an input of the priced value: the account,
    amount, the price's moment (the deposit's UTC hour, or an
    inheritance's date of death: _valuation_point) or type, or a source
    that wasn't valued at receipt. Between two sources that are (Reward to
    Rebate, the fix #98 asks of users) the value can't change, so it isn't
    priced again and needs no price."""
    for key in ("type", "to_account_id"):
        if key in tx_data and getattr(tx_data[key], "value", tx_data[key]) != getattr(tx, key):
            return True
    if "source" in tx_data and tx_data["source"] != tx.source \
            and normalized(tx.source) not in VALUED_AT_RECEIPT:
        return True
    if "amount" in tx_data and Decimal(tx_data["amount"] or 0) != Decimal(tx.amount or 0):
        return True
    tz = get_tax_timezone(db)
    return _valuation_point(tx_data, tx, tz) != _valuation_point({}, tx, tz)


def price_used(tx: Transaction, db: Session, years: dict | None = None) -> dict | None:
    """
    The stored price a transaction's filled-in values came from (an income
    or rebate value, Spent proceeds, a gift's value, a BTC fee's value), for the form and the
    API (#145): its hour or day, source and USD per BTC. Read from this
    install's table and files only, never asked for. Given only when a value
    it filled in is that price times its amount to the cent: a value priced
    elsewhere (an import, another tax timezone since) names no price. One
    matching value names it for the transaction: a Spent's typed proceeds
    beside a priced fee keep their own "typed" mark in the form. None otherwise. `years`: a cache
    of the year files for one request (a list of many transactions).
    """
    values = priced_values(tx)
    if not values or tx.price_moment not in ("hour", "day") or tx.timestamp is None:
        return None
    when = tx.timestamp
    if _is_inherited({"source": tx.source}) and tx.acquired_at is not None:
        when = date_of_death(tx.acquired_at, db)  # a date: its day's price (#154, #177)
    found = hourly_prices.stored_price_at(db, when, tx.price_moment, years)
    if found is None or not any(abs(found.usd * btc - usd) <= CENT for _field, usd, btc in values):
        return None
    return {"at": found.at.isoformat().replace("+00:00", "Z"), "moment": found.moment,
            "source": found.source, "usd_per_btc": found.usd}


def priced_values(tx: Transaction) -> list[tuple[str, Decimal, Decimal]]:
    """
    Each value BitcoinTX filled in from a price, as (its field, USD value, BTC
    it values): an income, rebate or inheritance value, a Spent's proceeds
    before its fee, a gift's, donation's or lost coins' value, and a BTC
    fee's value unless typed. A mark without its value (a deposit moved to
    Bank) isn't one, nor a withdrawal's from a dollar account (one an older
    save left there, #449). For price_used, and for which values the API and
    the AI connector say came from a price (#208).
    """
    out = []
    btc_leaving = tx.from_account_id in BTC_ACCOUNTS
    if tx.cost_basis_from_price and tx.cost_basis_usd is not None:
        out.append(("cost_basis_usd", Decimal(tx.cost_basis_usd), Decimal(tx.amount or 0)))
    if tx.proceeds_from_price and tx.gross_proceeds_usd is not None and btc_leaving:
        out.append(("gross_proceeds_usd", Decimal(tx.gross_proceeds_usd), Decimal(tx.amount or 0)))
    if tx.fmv_from_price and tx.fmv_usd is not None and btc_leaving:
        out.append(("fmv_usd", Decimal(tx.fmv_usd), Decimal(tx.amount or 0)))
    if tx.fee_usd is not None and not tx.fee_usd_manual and Decimal(tx.fee_amount or 0) > 0:
        out.append(("fee_usd", Decimal(tx.fee_usd), Decimal(tx.fee_amount)))
    return out


def values_from_price(tx: Transaction) -> list[str]:
    """The fields priced_values names: the values BitcoinTX filled in from a price (#208)."""
    return [field for field, _usd, _btc in priced_values(tx)]


def _valuation_point(edited: dict, tx: Transaction, tz):
    """When a valued deposit is priced, after the edit `edited`: an
    inheritance on its date of death (date_of_death), anything else at its
    UTC hour."""
    if _is_inherited({"source": edited.get("source", tx.source)}):
        when = edited.get("acquired_at", tx.acquired_at) or edited.get("timestamp", tx.timestamp)
        return original_date(when, tz) if when is not None else None
    moment = edited.get("timestamp", tx.timestamp)
    return hourly_prices.hour_of(moment) if moment is not None else None


def _hour_changed(tx: Transaction, tx_data: dict) -> bool:
    """Whether the edit moves the transaction to another UTC hour: the hour
    whose price values it."""
    if "timestamp" in tx_data and tx_data["timestamp"] is not None and tx.timestamp is not None:
        return hourly_prices.hour_of(tx_data["timestamp"]) != hourly_prices.hour_of(tx.timestamp)
    return False


def _revalue_btc_fee(tx: Transaction, tx_data: dict, db: Session) -> None:
    """A BTC fee's USD value: a typed one is kept; otherwise it is priced
    again when the fee or the hour changes (fee_usd sent as null clears a
    typed one)."""
    if "fee_usd" not in tx_data and (tx.fee_usd_manual or not _fee_inputs_changed(tx, tx_data)):
        return
    fee = {k: tx_data.get(k, getattr(tx, k)) for k in ("type", "fee_amount", "fee_currency", "timestamp")}
    fee["fee_usd"] = tx_data["fee_usd"] if "fee_usd" in tx_data else (
        tx.fee_usd if tx.fee_usd_manual else None)
    _value_btc_fee(fee, db, manual=fee["fee_usd"] is not None)
    tx.fee_usd, tx.fee_usd_manual = fee["fee_usd"], fee["fee_usd_manual"]
    if "price_moment" in fee:
        _note_moment(tx_data, fee["price_moment"])


def _revalue_spent_proceeds(tx: Transaction, tx_data: dict, db: Session) -> None:
    """
    A Spent's proceeds that came from a price, after an edit: a typed value
    is kept (the form sends back the value it shows: that isn't a typed
    one), and a change of purpose or type makes them typed; a blank or $0
    one, or one whose amount or hour the edit changes, is priced again.
    """
    if not tx.proceeds_from_price:
        return
    edited = {k: tx_data.get(k, getattr(tx, k)) for k in ("type", "purpose", "amount", "timestamp")}
    if not _is_spent(edited) or _typed_proceeds(tx, tx_data):
        tx_data["proceeds_from_price"] = False
        return
    if not (_cleared_proceeds(tx_data) or _spent_inputs_changed(tx, tx_data)):
        return
    priced = _price_at(edited["timestamp"], db)
    tx_data["gross_proceeds_usd"] = tx_data["proceeds_usd"] = (priced.usd * Decimal(edited["amount"])).quantize(Decimal("0.01"))
    _note_moment(tx_data, priced.moment)


def _revalue_gift(tx: Transaction, tx_data: dict, db: Session) -> None:
    """
    A Gift, Donation or Lost withdrawal's value after an edit (#255): priced
    when the edit prices it (_gift_priced_by_edit; blank without a price);
    a typed value, or a change to a sale or another type, makes it typed.
    """
    edited = {k: tx_data.get(k, getattr(tx, k)) for k in ("type", "purpose", "amount", "timestamp", "from_account_id")}
    if not _is_gift_like(edited):
        if tx.fmv_from_price:
            tx_data["fmv_from_price"] = False
        return
    if _gift_priced_by_edit(tx, tx_data):
        _price_gift_again(edited, tx_data, db)
    elif tx.fmv_from_price and _typed_gift_value(tx, tx_data):
        tx_data["fmv_from_price"] = False


def _gift_priced_by_edit(tx: Transaction, tx_data: dict) -> bool:
    """Whether an edit that leaves a withdrawal a gift, donation or loss
    prices its value: blank after the edit (sent blank, or left blank: an
    edit saves it, as one saved before #255 was), a sale's $0 it becomes a
    gift with when no value is sent (older forms saved $0 on every
    withdrawal; a value sent, $0 included, is the one wanted), or one from
    the price whose amount or hour the edit changes."""
    after = tx_data["fmv_usd"] if "fmv_usd" in tx_data else tx.fmv_usd
    if after is None:
        return True
    if not _is_gift_like(tx):
        return "fmv_usd" not in tx_data and Decimal(after) <= 0
    if _typed_gift_value(tx, tx_data):
        return False
    return bool(tx.fmv_from_price) and _spent_inputs_changed(tx, tx_data)


def _price_gift_again(edited: dict, tx_data: dict, db: Session) -> None:
    """The edited gift's value at its hour's price, marked; without a price, blank."""
    found = _gift_value_at(edited["amount"], edited["timestamp"], db) if Decimal(edited["amount"] or 0) > 0 else None
    tx_data["fmv_usd"] = found[0] if found else None
    tx_data["fmv_from_price"] = found is not None
    if found:
        _note_moment(tx_data, found[1])


def _typed_gift_value(tx: Transaction, tx_data: dict) -> bool:
    """Whether the edit types the value: one that isn't the stored one sent
    back (the form sends a blank one back blank, so $0 for it is typed)."""
    sent = tx_data.get("fmv_usd")
    if sent is None:
        return False
    return tx.fmv_usd is None or Decimal(sent).quantize(CENT) != Decimal(tx.fmv_usd).quantize(CENT)


def _sent_proceeds(tx_data: dict):
    """The proceeds an edit sends (the gross first: _apply_edit stores it first), or None."""
    return tx_data["gross_proceeds_usd"] if "gross_proceeds_usd" in tx_data else tx_data.get("proceeds_usd")


def _typed_proceeds(tx: Transaction, tx_data: dict) -> bool:
    """Whether the edit types a Spent's proceeds: a positive value that isn't the stored one sent back."""
    sent = _sent_proceeds(tx_data)
    return sent is not None and Decimal(sent) > 0 \
        and Decimal(sent).quantize(Decimal("0.01")) != Decimal(tx.gross_proceeds_usd or 0)


def _cleared_proceeds(tx_data: dict) -> bool:
    """Whether the edit sends the proceeds blank (the form's null for an emptied field) or $0."""
    sent = _sent_proceeds(tx_data)
    return ("gross_proceeds_usd" in tx_data or "proceeds_usd" in tx_data) and (sent is None or Decimal(sent) <= 0)


def _spent_inputs_changed(tx: Transaction, tx_data: dict) -> bool:
    if "amount" in tx_data and Decimal(tx_data["amount"] or 0) != Decimal(tx.amount or 0):
        return True
    return _hour_changed(tx, tx_data)


def _keeps_a_day_price(tx: Transaction, tx_data: dict) -> bool:
    """
    Whether an edit prices one of a withdrawal's values (a Spent's proceeds
    or a gift's value, and its fee's value: priced again, or priced now)
    while the other keeps the day's price: then the one priced takes the
    day's price too, so the transaction's values share one price, and
    Ledger Review offers both at the hour.
    """
    if tx.price_moment != "day":
        return False
    edited = {k: tx_data.get(k, getattr(tx, k))
              for k in ("type", "purpose", "fee_amount", "fee_currency", "from_account_id")}
    edited["type"] = getattr(edited["type"], "value", edited["type"])
    value_priced = _value_priced_by_edit(tx, tx_data, edited)
    if value_priced is None:
        return False
    fee = _fee_after_edit(tx, tx_data, edited)
    return (value_priced and fee == "kept") or (fee == "priced" and not value_priced)


def _value_priced_by_edit(tx: Transaction, tx_data: dict, edited: dict) -> bool | None:
    """A Spent's proceeds that came from a price, or a gift's value, after an
    edit: True when the edit prices it (again, or now), False when it keeps
    one from the price; None when there is none, or the edit types it."""
    if _is_spent(edited) and tx.proceeds_from_price and tx.gross_proceeds_usd is not None:
        if _typed_proceeds(tx, tx_data):
            return None
        return _cleared_proceeds(tx_data) or _spent_inputs_changed(tx, tx_data)
    if _is_gift_like(edited):
        if _gift_priced_by_edit(tx, tx_data):
            return True
        kept = tx.fmv_from_price and tx.fmv_usd is not None and not _typed_gift_value(tx, tx_data)
        return False if kept else None
    return None


def _fee_after_edit(tx: Transaction, tx_data: dict, edited: dict) -> str | None:
    """A BTC fee's value after an edit: "kept" (priced, untouched), "priced"
    (by the edit: a new fee, new fee inputs, a typed value cleared), or None
    (no BTC fee, or a typed value)."""
    if not _has_btc_fee(edited) or tx_data.get("fee_usd") is not None:
        return None
    if "fee_usd" in tx_data or tx.fee_usd is None or _fee_inputs_changed(tx, tx_data):
        return "priced"
    return None if tx.fee_usd_manual else "kept"


@contextmanager
def _priced_at_the_day(db: Session, at_the_day: bool):
    """Within it, a value priced is priced at the day (_price_at)."""
    before = db.info.get(DAY_PRICES)
    db.info[DAY_PRICES] = at_the_day
    try:
        yield
    finally:
        db.info[DAY_PRICES] = before


# Session.info key: price at the day, not the hour (_priced_at_the_day)
DAY_PRICES = "btctx_price_at_the_day"


def find_prices_first(db: Session, rows: list[dict]) -> None:
    """
    Before a save of several rows first writes (an import, the AI's preview
    or add), find the prices its rows' values are filled from, so they're
    stored: from its second row on it holds SQLite's write lock, and a price
    asked for then, from the price sites or the owner's Mempool, held the
    owner's saves up behind it (#426). In time order, as the save goes (the
    year files kept in memory are few). The rest of the import waits for no
    year it waited for here, and asks no source again for an hour it had no
    price for (hourly_prices.WARMING): such a row takes the day's price. A
    price it misses is found with the lock free all the same, at the cost
    of starting the import again (hourly_prices.with_prices_found).
    """
    if price_history.writing(db):
        return
    db.info[hourly_prices.WARMING] = True
    try:
        for when, at_the_day in sorted(_moments_priced(db, rows)):
            try:
                with _priced_at_the_day(db, at_the_day):
                    _price_at(when, db)
            except HTTPException:
                pass  # the save looks again, and says which value lacks one
            except Exception:  # a busy database: the save meets it and answers as it does
                return
    finally:
        db.info[hourly_prices.WARMING] = False


def _moments_priced(db: Session, rows: list[dict]) -> set[tuple[datetime, bool]]:
    """When the rows' values filled from a price are priced, as (the moment,
    whether at the day): those a save won't do without
    (values_the_save_prices), and a gift's blank value (_value_blank_gift)."""
    moments = set()
    for row in rows:
        moments |= {(when, at == "day") for _field, when, at in values_the_save_prices(row, db)}
        if _is_gift_like(row) and row.get("fmv_usd") is None and Decimal(row.get("amount") or 0) > 0:
            moments.add((row.get("timestamp") or datetime.now(timezone.utc), _prices_at_the_day(row)))
    return moments


# Written as given when the edit sends them, in this order.
_EDITED_FIELDS = (
    "from_account_id", "to_account_id", "amount", "fee_amount", "fee_currency", "type", "timestamp",
    "source", "purpose",
)


def _apply_edit(tx: Transaction, tx_data: dict, type_changed: bool) -> None:
    for key in _EDITED_FIELDS:
        if key in tx_data:
            setattr(tx, key, tx_data[key])
    if "broker_reporting" in tx_data:
        _enforce_broker_reporting(tx_data.get("type", tx.type), tx_data["broker_reporting"])
        tx.broker_reporting = tx_data["broker_reporting"]
    elif tx.type not in BROKER_REPORTING_TYPES:
        tx.broker_reporting = None  # type changed away from Sell/Withdrawal
    for key in ("cost_basis_usd", "cost_basis_from_price", "proceeds_usd", "fmv_usd", "acquired_at",
                "price_moment", "proceeds_from_price", "fmv_from_price"):
        if key in tx_data:
            setattr(tx, key, tx_data[key])
    if "gross_proceeds_usd" in tx_data:
        tx.gross_proceeds_usd = tx_data["gross_proceeds_usd"]
    elif "proceeds_usd" in tx_data and tx.type in GROSS_PROCEEDS_TYPES:
        # A proceeds edit is user input, i.e. the new gross
        tx.gross_proceeds_usd = tx_data["proceeds_usd"]
    if type_changed:  # the old type's gain; a Sell's or Withdrawal's is worked out again
        tx.realized_gain_usd = tx.holding_period = None


def delete_transaction_record(transaction_id: int, db: Session):
    """
    Delete a transaction: its ledger entries and lot usage go, and every lot
    is rebuilt.
    Committed only if the ledger still recalculates without it: deleting a
    buy that a later sell or transfer spends is refused and changes nothing.
    A transaction naming a missing account is deleted past the others that
    do (#368), so they can be fixed one by one. A price the recalculation
    needs is looked for with the lock free (hourly_prices.with_prices_found,
    #426).
    """
    return hourly_prices.with_prices_found(db, lambda: _delete(transaction_id, db))


def _delete(transaction_id: int, db: Session) -> bool:
    tx = get_transaction_by_id(db, transaction_id)
    if not tx:
        return False

    # One naming a missing account goes even while others like it stop the
    # replay, or none of them could ever go (#368)
    past = [] if missing_accounts(tx, known_accounts(db)) else None
    db.delete(tx)
    db.flush()
    try:
        recalculate_all_transactions(db, past_missing=past)
    except HTTPException as e:
        db.rollback()
        if isinstance(e, AccountMissing):
            raise
        why = _why_short(past, db) if e.status_code == 400 else ""
        raise HTTPException(status_code=e.status_code, detail=f"Not deleted: {why}{e.detail}")
    except Exception:
        db.rollback()
        raise
    db.commit()
    return True


def _why_short(past: list[Transaction] | None, db: Session) -> str:
    """Why an edit or a delete leaves a later transaction short of BTC: it
    needed this one, or a row naming a missing account the replay went past
    (#368) takes its coins, or gets none where they went."""
    if not past:
        return "later transactions depend on this one. "
    tz = get_tax_timezone(db)
    rows = [f"{t.id} (a {t.type} of {local_date(t.timestamp, tz).isoformat()})" for t in past]
    one = len(rows) == 1
    return MISSING_MAY_BE_WHY.format(
        rows=("Transaction " if one else "Transactions ") + " and ".join(rows), names="names" if one else "name")


def holding_period(acquired: datetime, disposed: datetime, tz=timezone.utc) -> str:
    """
    IRS rule (Pub. 544): long-term only if held MORE than one year, counting
    from the day after acquisition — i.e. disposed after the one-year
    anniversary date. Selling on the anniversary itself is short-term.
    (Feb 29 acquisitions: anniversary is Feb 28, so long-term from Mar 1.)
    Calendar dates are taken in the tax timezone `tz`.
    """
    from dateutil.relativedelta import relativedelta
    from backend.services.tax_time import local_date

    anniversary = local_date(acquired, tz) + relativedelta(years=1)
    return "LONG" if local_date(disposed, tz) > anniversary else "SHORT"


def lot_holding_period(lot: BitcoinLot, disposed: datetime, tz=timezone.utc) -> str:
    """A disposal's term from its lot: inherited coins are long-term however
    soon they're sold (IRC §1223(9), #154); others by holding_period()."""
    return "LONG" if lot.inherited else holding_period(lot.acquired_date, disposed, tz)


# Types whose proceeds are derived (net of fees) from the user's gross input
GROSS_PROCEEDS_TYPES = ("Sell", "Withdrawal")
# What a disposal does, for its shortage: "Not enough BTC to withdraw …" (#415)
DISPOSAL_VERBS = {"Sell": "sell", "Withdrawal": "withdraw"}


def _record_gross_proceeds(tx_data: dict) -> None:
    """
    Record the user's proceeds as gross_proceeds_usd on create (the UI already
    sends it for Sells). Stored proceeds_usd is overwritten with the NET value,
    so without the gross every recalculation would net the fee again.
    """
    if (
        tx_data.get("type") in GROSS_PROCEEDS_TYPES
        and tx_data.get("gross_proceeds_usd") is None
        and tx_data.get("proceeds_usd") is not None
    ):
        tx_data["gross_proceeds_usd"] = tx_data["proceeds_usd"]


def _withdrawal_gross_proceeds(tx: Transaction, btc_outflow: Decimal, db: Session) -> Decimal:
    """
    Gross USD proceeds for a BTC Withdrawal, recorded on the transaction so
    recalculation always starts from the same number.
      - Spent with no proceeds given (River/CSV imports): FMV of the amount at
        the hour's price, fetched once, and marked as priced.
      - Rows saved before the gross was recorded: their proceeds_usd is net of
        the BTC fee offset versions before 0.9.2 applied; undo it once. The
        gross is what was received for the amount spent (the fee is its own
        disposal now).
      - A purpose BitcoinTX doesn't know counts as Spent (counts_as_spent,
        #61): its stored proceeds_usd, which had no offset taken off (only a
        Spent's did), becomes its gross. With none stored (blank, or the 0 a
        1.2.8 recalculation wrote over it, #329), $0 and no gross recorded:
        what it received isn't known, Ledger Review sends the owner to the
        copy that still holds it, and a recalculation never fetches a price
        (a missing one would stop every save).
    """
    if tx.gross_proceeds_usd is not None:
        return Decimal(tx.gross_proceeds_usd)

    amount = Decimal(tx.amount or 0)
    if normalized(tx.purpose) in GIFT_LIKE_PURPOSES:
        # Gift/Donation/Lost have no proceeds. Their stored proceeds_usd is the
        # network fee's (its own disposal), never a gross to recover.
        return Decimal("0")
    spent = _spent_as_matched(tx)  # the spelling the offset and the pricing went by
    if not spent and Decimal(tx.proceeds_usd or 0) <= 0:
        return Decimal("0")
    if tx.proceeds_usd is None:
        priced = _price_for(tx, "it has no Proceeds (USD) value", db)
        gross = (priced.usd * amount).quantize(Decimal("0.01"))
        tx.proceeds_from_price = True
        tx.price_moment = "day" if "day" in (tx.price_moment, priced.moment) else priced.moment
    else:
        gross = Decimal(tx.proceeds_usd)
        has_btc_fee = (tx.fee_currency or "").upper() == "BTC" and Decimal(tx.fee_amount or 0) > 0
        if spent and has_btc_fee and gross > 0 and amount > 0:
            gross = (gross * btc_outflow / amount).quantize(Decimal("0.01"))

    tx.gross_proceeds_usd = gross
    return gross


def ensure_fee_account_exists(db: Session):
    """
    If 'BTC Fees' doesn't exist, create it.
    This prevents referencing a non-existent account in fee lines.
    """
    fee_acct = db.query(Account).filter_by(name="BTC Fees").first()
    if not fee_acct:
        fee_acct = Account(user_id=1, name="BTC Fees", currency="BTC")
        db.add(fee_acct)
        db.commit()
        db.refresh(fee_acct)
    return fee_acct


def remove_ledger_entries_for_tx(tx: Transaction, db: Session):
    """
    Remove all LedgerEntries associated with the given transaction.
    """
    for entry in list(tx.ledger_entries):
        db.delete(entry)
    db.flush()


def build_ledger_entries_for_transaction(tx: Transaction, tx_data: dict, db: Session):
    """
    The transaction's debit and credit lines. A Buy or Sell moves USD one
    way and BTC the other (so its lines don't net to zero); a BTC transfer
    sends the amount with its fee included. For a Sell, the net proceeds
    are worked out here and stored in proceeds_usd, which the disposals and
    the totals read; the gross the user entered stays in gross_proceeds_usd.
    """
    from_acct_id = tx_data.get("from_account_id")
    to_acct_id = tx_data.get("to_account_id")
    tx_type = tx_data.get("type", "")
    amount = Decimal(tx_data.get("amount") or 0)
    fee_amount = Decimal(tx_data.get("fee_amount") or "0.0")
    fee_currency = (tx_data.get("fee_currency") or "").upper()  # stored with any fee (_fill_fee_currency)

    from_acct = db.get(Account, from_acct_id) if from_acct_id else None
    to_acct = db.get(Account, to_acct_id) if to_acct_id else None

    if tx_type == "Transfer" and from_acct and from_acct.currency == "BTC" and fee_amount > 0:
        _btc_transfer_lines(tx, from_acct, to_acct, amount, fee_amount, db)
    elif tx_type == "Sell" and _in_currency(from_acct, "BTC") and _in_currency(to_acct, "USD"):
        _sell_lines(tx, tx_data, from_acct, to_acct, amount, fee_amount, fee_currency, db)
    elif tx_type == "Buy" and _in_currency(from_acct, "USD") and _in_currency(to_acct, "BTC"):
        _buy_lines(tx, tx_data, from_acct, to_acct, fee_currency, db)
    else:
        _plain_lines(tx, from_acct, to_acct, amount, fee_amount, fee_currency, db)
    db.flush()


def _in_currency(account: Account | None, currency: str) -> bool:
    return bool(account and account.currency == currency)


def _add_line(tx: Transaction, account_id: int, amount: Decimal, currency: str, entry_type: str, db: Session) -> None:
    db.add(LedgerEntry(
        transaction_id=tx.id,
        account_id=account_id,
        amount=amount,
        currency=currency,
        entry_type=entry_type
    ))


def _fee_account(currency: str, db: Session) -> Account | None:
    """BTC Fees or USD Fees."""
    return db.query(Account).filter_by(name=f"{currency} Fees").first()


def _btc_transfer_lines(tx, from_acct, to_acct, amount: Decimal, fee_amount: Decimal, db: Session) -> None:
    """The amount out of the source (fee included), the amount less the fee
    into the destination, the fee to BTC Fees."""
    _add_line(tx, from_acct.id, -amount, from_acct.currency, "MAIN_OUT", db)
    if to_acct and amount > 0:
        net_in = amount - fee_amount
        _add_line(tx, to_acct.id, net_in if net_in > 0 else Decimal("0"), to_acct.currency, "MAIN_IN", db)
    fee_acct = _fee_account("BTC", db)
    if fee_acct:
        _add_line(tx, fee_acct.id, fee_amount, "BTC", "FEE", db)


def _sell_lines(tx, tx_data: dict, from_acct, to_acct, amount: Decimal, fee_amount: Decimal, fee_currency: str,
                db: Session) -> None:
    """The BTC out, the net USD in, a USD fee to USD Fees."""
    if amount > 0:
        _add_line(tx, from_acct.id, -amount, "BTC", "MAIN_OUT", db)
    net_usd_in = _sell_net_proceeds(tx, tx_data, fee_amount, fee_currency)
    if net_usd_in > 0:
        _add_line(tx, to_acct.id, net_usd_in, "USD", "MAIN_IN", db)
    if fee_amount > 0 and fee_currency == "USD":
        fee_acct = _fee_account("USD", db)
        if fee_acct:
            _add_line(tx, fee_acct.id, fee_amount, "USD", "FEE", db)


def _sell_net_proceeds(tx: Transaction, tx_data: dict, fee_amount: Decimal, fee_currency: str) -> Decimal:
    """
    A Sell's proceeds net of its USD fee, from the gross the user entered,
    stored in tx.proceeds_usd (and tx_data). Always from the gross: the net
    again, less the fee, would shrink with every recalculation.
    """
    gross_usd = Decimal(tx_data.get("gross_proceeds_usd") or "0")
    if gross_usd > 0:
        if fee_currency == "USD":
            net_usd_in = gross_usd - fee_amount
            if net_usd_in < 0:
                net_usd_in = Decimal("0")
        else:
            # A BTC fee doesn't reduce the USD received
            net_usd_in = gross_usd
        tx_data["proceeds_usd"] = str(net_usd_in)
        tx.proceeds_usd = net_usd_in
        tx.gross_proceeds_usd = gross_usd
        return net_usd_in

    # No gross recorded. create_transaction_record always records it, so only
    # rows saved before that reach here, and their stored proceeds_usd is
    # ALREADY net of the USD fee: keep it as the net and recover the gross
    # once.
    proceeds_usd = Decimal(tx_data.get("proceeds_usd") or "0")
    net_usd_in = proceeds_usd if proceeds_usd > 0 else Decimal("0")
    if net_usd_in > 0:
        tx.gross_proceeds_usd = (
            net_usd_in + fee_amount if fee_currency == "USD" else net_usd_in
        )
    tx_data["proceeds_usd"] = str(net_usd_in)
    tx.proceeds_usd = net_usd_in
    return net_usd_in


def _buy_lines(tx, tx_data: dict, from_acct, to_acct, fee_currency: str, db: Session) -> None:
    """The cost and a USD fee out of the USD account, the BTC in, the fee to USD Fees."""
    amount_btc = Decimal(tx_data.get("amount") or 0)
    fee_amt = Decimal(tx_data.get("fee_amount") or 0)
    cost_basis_usd = Decimal(tx_data.get("cost_basis_usd") or 0)

    total_usd_out = cost_basis_usd + fee_amt
    _add_line(tx, from_acct.id, -total_usd_out, "USD", "MAIN_OUT", db)
    if amount_btc > 0:
        _add_line(tx, to_acct.id, amount_btc, "BTC", "MAIN_IN", db)
    if fee_amt > 0 and fee_currency == "USD":
        fee_acct = _fee_account("USD", db)
        if fee_acct:
            _add_line(tx, fee_acct.id, fee_amt, "USD", "FEE", db)


def _plain_lines(tx, from_acct, to_acct, amount: Decimal, fee_amount: Decimal, fee_currency: str,
                 db: Session) -> None:
    """Deposits, withdrawals and USD transfers: the amount and the fee out
    of the sender, the amount into the receiver, the fee to its fee account."""
    if from_acct and amount > 0:
        _add_line(tx, from_acct.id, -(amount + fee_amount), from_acct.currency, "MAIN_OUT", db)
    if to_acct and amount > 0:
        _add_line(tx, to_acct.id, amount, to_acct.currency, "MAIN_IN", db)
    if fee_amount > 0:
        fee_acct = _fee_account("BTC" if fee_currency == "BTC" else "USD", db)
        if fee_acct:
            _add_line(tx, fee_acct.id, fee_amount, fee_currency, "FEE", db)


def maybe_create_bitcoin_lot(tx: Transaction, tx_data: dict, db: Session):
    """
    If Deposit/Buy => create a new BitcoinLot if 'to_acct' is BTC.
    If fee is USD for a Buy, add it to cost basis automatically.
    """
    to_acct = db.get(Account, tx.to_account_id) if tx.to_account_id else None
    if not to_acct or to_acct.currency != "BTC":
        return

    btc_amount = tx.amount or Decimal("0")
    if btc_amount <= 0:
        return

    cost_basis = Decimal(tx_data.get("cost_basis_usd") or 0)
    fee_cur = (tx_data.get("fee_currency") or "").upper()
    fee_amt = Decimal(tx_data.get("fee_amount") or "0.0")

    # If it's a Buy w/ USD fee, add that fee to cost basis
    if tx.type == "Buy" and fee_cur == "USD":
        cost_basis += fee_amt

    new_lot = BitcoinLot(
        created_txn_id=tx.id,
        # Coins already owned (My BTC) or a gift with the giver's basis keep
        # their holding period from when they were first acquired (#91);
        # inherited coins are dated by the date of death (#154)
        acquired_date=_lot_acquired(tx, db),
        total_btc=btc_amount,
        remaining_btc=btc_amount,
        cost_basis_usd=cost_basis,
        inherited=tx.type == "Deposit" and _is_inherited({"source": tx.source}),
    )
    db.add(new_lot)
    db.flush()


def _lot_acquired(tx: Transaction, db: Session) -> datetime:
    """
    When a deposit's coins were acquired: the deposit itself, or its date
    originally acquired (date of death) at noon in the tax timezone, as a
    date alone is read everywhere (#185: the date is stored, so a timezone
    change, which recalculates, moves the lot with it). Never after the
    deposit, so its lot can't sort after its own arrival.
    """
    if tx.acquired_at is None:
        return tx.timestamp
    return min(local_noon_utc(tx.acquired_at, get_tax_timezone(db)), as_utc(tx.timestamp))


def maybe_dispose_lots_fifo(tx: Transaction, tx_data: dict, db: Session):
    """
    For a Sell/Withdrawal from a BTC account, do FIFO disposal of partial lots.
    - The proceeds are for the amount sold or spent, net of its fee: a Sell's
      net proceeds, a Spent withdrawal's (or one counted as Spent, #61)
      gross less its BTC fee's value.
    - Gift/Donation/Lost => the amount carries no proceeds and no gain.
    - A withdrawal's BTC network fee is its own disposal (like a transfer's),
      at the fee's stored USD value, taxable whatever the purpose. It uses the
      oldest BTC first, then the amount follows.
    """
    from_acct = db.get(Account, tx.from_account_id) if tx.from_account_id else None
    if not from_acct or from_acct.currency != "BTC":
        return

    amount_btc = Decimal(tx.amount or 0)
    fee_btc = Decimal(tx.fee_amount or 0) if (tx.fee_currency or "").upper() == "BTC" else Decimal("0")
    btc_outflow = amount_btc + fee_btc
    if btc_outflow <= 0:
        return

    total_proceeds = _amount_proceeds(tx, tx_data, btc_outflow, db)
    # Gift/Donation/Lost => no gain or loss on the amount: not a sale, and
    # not on Form 8949 (form_8949.NON_TAXABLE_PURPOSES); the dashboard and
    # the tax report's summary leave it out too (owner decision 2026-09-26).
    not_a_sale = tx.type == "Withdrawal" and normalized(tx.purpose) in GIFT_LIKE_PURPOSES
    if not_a_sale:
        total_proceeds = Decimal("0")
    fee_usd = _stored_fee_usd(tx, fee_btc, db) if (tx.type == "Withdrawal" and fee_btc > 0) else Decimal("0")
    if counts_as_spent(tx) and received_known(tx):
        total_proceeds, fee_usd = _spend_net_of_fee(total_proceeds, fee_usd)

    disposal = _FifoDisposal(tx, amount_btc, total_proceeds, not_a_sale, fee_btc, fee_usd, db)
    for lot in _open_lots(tx.from_account_id, db):
        if disposal.remaining_fee <= 0 and disposal.remaining_amount <= 0:
            break
        disposal.take_from(lot)

    # Validate that we had enough BTC to complete the disposal. No tolerance:
    # amounts are exact decimals of at most 8 places.
    if disposal.remaining_fee + disposal.remaining_amount > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough BTC to {DISPOSAL_VERBS[tx.type]} {btc_outflow:.8f} BTC"
        )

    db.flush()


def _amount_proceeds(tx: Transaction, tx_data: dict, btc_outflow: Decimal, db: Session) -> Decimal:
    """
    The proceeds for the amount. A Sell's is tx.proceeds_usd, the net that
    build_ledger_entries_for_transaction derived from gross_proceeds_usd;
    a Withdrawal has no ledger-side net step, so it starts from the gross.
    """
    if tx.type == "Withdrawal":
        return _withdrawal_gross_proceeds(tx, btc_outflow, db)
    if tx.proceeds_usd is not None:
        return Decimal(tx.proceeds_usd)
    raw_proceeds = tx_data.get("proceeds_usd")
    if raw_proceeds is None:
        return Decimal("0")
    try:
        return Decimal(str(raw_proceeds))
    except (ValueError, TypeError, InvalidOperation):
        return Decimal("0")


def _spend_net_of_fee(gross: Decimal, fee_usd: Decimal) -> tuple[Decimal, Decimal]:
    """
    A spend's proceeds and its fee disposal's. The fee paid to make the spend
    is a cost of it, so it comes off what the spend brought in (Treas. Reg.
    §1.1001-7(b)(2)(ii)(A) and its Example 4, IRS digital-asset FAQ Q63;
    #157), while the coins that paid it are disposed of at its value (Q97).
    Together they realize the gross. A fee worth more than the gross takes
    only the gross, so no proceeds go below zero. Always from the gross: the
    net again, less the fee, would shrink with every recalculation.
    """
    fee_proceeds = min(fee_usd, gross)
    return gross - fee_proceeds, fee_proceeds


def _open_lots(account_id: int, db: Session) -> list[BitcoinLot]:
    """The account's lots with BTC left, oldest first."""
    return (
        db.query(BitcoinLot)
        .join(Transaction, Transaction.id == BitcoinLot.created_txn_id)
        .filter(
            BitcoinLot.remaining_btc > 0,
            Transaction.to_account_id == account_id
        )
        .order_by(BitcoinLot.acquired_date.asc(), BitcoinLot.id.asc())  # the same date: the first created
        .all()
    )


def _cents_of_part(value: Decimal, part: Decimal, whole: Decimal) -> Decimal:
    """`part` of `whole`'s share of `value`, to the cent; all of it is
    exactly `value`."""
    if not whole or part <= 0:
        return Decimal("0")
    if part >= whole:
        return Decimal(value)
    # Multiplied before divided: for any amount a ledger holds, a share that
    # is exactly half a cent stays exact and rounds up (#295's review)
    return (value * part / whole).quantize(CENT, rounding=SHARE_ROUNDING)


def running_share(value: Decimal, before: Decimal, qty: Decimal, whole: Decimal) -> Decimal:
    """
    The share of `value` for `qty` of `whole`, once `before` of it has had
    its shares: the running total's cents with it, less without it. Rounded
    as a running total, not share by share, so the shares add up to `value`
    to the cent and none is below zero, however small they are: a lot's cost
    among its pieces (#100), a disposal's proceeds or a fee's value among
    its lots (#297).
    """
    return _cents_of_part(value, before + qty, whole) - _cents_of_part(value, before, whole)


def piece_cost(lot: BitcoinLot, qty: Decimal) -> Decimal:
    """The cost of `qty` BTC about to be taken from `lot` (its remaining_btc
    not yet lowered): its running share of the lot's cost (#100)."""
    return running_share(lot.cost_basis_usd, lot.total_btc - lot.remaining_btc, qty, lot.total_btc)


def cost_left(lot: BitcoinLot) -> Decimal:
    """The cost of a lot's BTC not yet taken: its cost less its pieces'."""
    return Decimal(lot.cost_basis_usd) - _cents_of_part(
        lot.cost_basis_usd, lot.total_btc - lot.remaining_btc, lot.total_btc)


class _FifoDisposal:
    """
    A Sell's or Withdrawal's BTC taken from lots, oldest first: the network
    fee's part before the amount's, each with its running share of the
    fee's value (fee_usd; a spend's at most its gross) or of the proceeds,
    so the parts add up to them exactly and none is below zero (#297).
    """

    def __init__(self, tx: Transaction, amount_btc: Decimal, total_proceeds: Decimal, not_a_sale: bool,
                 fee_btc: Decimal, fee_usd: Decimal, db: Session):
        self.tx, self.db = tx, db
        self.amount_btc, self.total_proceeds, self.not_a_sale = amount_btc, total_proceeds, not_a_sale
        self.fee_btc, self.fee_usd = fee_btc, fee_usd
        self.remaining_amount = amount_btc
        self.remaining_fee = fee_btc
        self.tz = get_tax_timezone(db)

    def take_from(self, lot: BitcoinLot) -> None:
        if self.remaining_fee > 0 and lot.remaining_btc > 0:
            qty = min(lot.remaining_btc, self.remaining_fee)
            proceeds = running_share(self.fee_usd, self.fee_btc - self.remaining_fee, qty, self.fee_btc)
            self.record(lot, qty, proceeds, gain_zero=False, is_fee=True)
            self.remaining_fee -= qty
        if self.remaining_amount > 0 and lot.remaining_btc > 0:
            qty = min(lot.remaining_btc, self.remaining_amount)
            proceeds = running_share(self.total_proceeds, self.amount_btc - self.remaining_amount, qty, self.amount_btc)
            self.record(lot, qty, proceeds, gain_zero=self.not_a_sale, is_fee=False)
            self.remaining_amount -= qty

    def record(self, lot: BitcoinLot, qty: Decimal, proceeds: Decimal, gain_zero: bool, is_fee: bool) -> None:
        basis = piece_cost(lot, qty)
        self.db.add(LotDisposal(
            lot_id=lot.id,
            transaction_id=self.tx.id,
            disposed_btc=qty,
            disposal_basis_usd=basis,
            proceeds_usd_for_that_portion=proceeds,
            realized_gain_usd=Decimal("0.0") if gain_zero else proceeds - basis,
            holding_period=lot_holding_period(lot, self.tx.timestamp, self.tz),
            is_fee=is_fee,
        ))
        lot.remaining_btc -= qty


def compute_sell_summary_from_disposals(tx: Transaction, db: Session):
    """
    Summarize partial-lot disposals (Sell/Withdrawal). Overwrite
    tx.cost_basis_usd, tx.proceeds_usd, tx.realized_gain_usd, and
    holding_period: LONG when any part is (the earliest lot's, as before
    inherited coins, #154, which are long-term whatever their date).
    The figures are for the amount sold or spent; a network fee's disposal
    is left out, as for a transfer (its value is tx.fee_usd, its gain is on
    Form 8949 and in the gain totals).
    """
    disposals = (
        db.query(LotDisposal)
        .options(joinedload(LotDisposal.lot))
        .filter(LotDisposal.transaction_id == tx.id, LotDisposal.is_fee.is_(False))
        .all()
    )
    if not disposals:
        return

    total_basis = Decimal("0.0")
    total_gain = Decimal("0.0")
    total_proceeds = Decimal("0.0")

    for disp in disposals:
        total_basis += (disp.disposal_basis_usd or Decimal("0"))
        total_gain += (disp.realized_gain_usd or Decimal("0"))
        total_proceeds += (disp.proceeds_usd_for_that_portion or Decimal("0"))

    tx.cost_basis_usd = total_basis
    tx.realized_gain_usd = total_gain

    purpose = normalized(tx.purpose)
    if tx.type == "Withdrawal" and purpose in GIFT_LIKE_PURPOSES:
        # No proceeds for the amount (its fee's are tx.fee_usd): a Spent
        # edited into a Gift kept its old proceeds, printed with the gifts.
        tx.proceeds_usd = None
    elif total_proceeds > 0 or (counts_as_spent(tx) and received_known(tx)):
        # A spend whose fee took all it brought in has 0 (#157), not the
        # gross. One counted as Spent with nothing recorded (an old ledger's
        # unknown purpose, #61) keeps what's stored: never 0 written over an
        # amount that is the only record of what was received (#329)
        tx.proceeds_usd = total_proceeds

    # Each part's own term, worked out when it was disposed of (lot_holding_period)
    tx.holding_period = "LONG" if any(d.holding_period == "LONG" for d in disposals) else "SHORT"

    db.flush()


FEE_VALUED_TYPES = ("Transfer", "Withdrawal")


def _has_btc_fee(data: dict) -> bool:
    return (
        data.get("type") in FEE_VALUED_TYPES
        and (data.get("fee_currency") or "").upper() == "BTC"
        and Decimal(data.get("fee_amount") or 0) > 0
    )


def _fee_inputs_changed(tx: Transaction, tx_data: dict) -> bool:
    """
    Whether an edit really changes what a fee's value depends on. The form
    sends every field on each edit; an unchanged fee keeps its stored value.
    """
    if "type" in tx_data and getattr(tx_data["type"], "value", tx_data["type"]) != tx.type:
        return True
    if "fee_currency" in tx_data and (tx_data["fee_currency"] or "").upper() != (tx.fee_currency or "").upper():
        return True
    if "fee_amount" in tx_data and Decimal(tx_data["fee_amount"] or 0) != Decimal(tx.fee_amount or 0):
        return True
    return _hour_changed(tx, tx_data)


def _value_btc_fee(data: dict, db: Session, manual: bool) -> None:
    """
    Set data["fee_usd"] / data["fee_usd_manual"]: the USD value of a
    transfer's or withdrawal's BTC fee, stored with the transaction so
    recalculation never prices it again. A typed value (manual) is kept;
    otherwise fee x the hour's price, its moment in data["price_moment"].
    No BTC fee: no value.
    """
    if not _has_btc_fee(data):
        data["fee_usd"], data["fee_usd_manual"] = None, False
        return
    if manual:
        data["fee_usd"] = Decimal(data["fee_usd"]).quantize(Decimal("0.01"))
        data["fee_usd_manual"] = True
        return
    ts = data.get("timestamp") or datetime.now(timezone.utc)
    try:
        priced = _price_at(ts, db)
    except HTTPException as e:
        raise HTTPException(
            status_code=422,
            detail=f"{e.detail} For the network fee, type its USD value in Fee value (USD) (fee_usd in an import).",
        )
    data["fee_usd"] = (priced.usd * Decimal(data["fee_amount"])).quantize(Decimal("0.01"))
    data["fee_usd_manual"] = False
    _note_moment(data, priced.moment)


def _stored_fee_usd(tx: Transaction, fee_btc: Decimal, db: Session) -> Decimal:
    """
    The fee's stored USD value. A row saved before values were stored (and
    not filled by migration 0004) is priced once from the price history and
    the value kept, so later recalculations don't price it again.
    """
    if tx.fee_usd is None:
        priced = _price_for(tx, "its network fee has no USD value", db)
        tx.fee_usd = (priced.usd * fee_btc).quantize(Decimal("0.01"))
        tx.fee_usd_manual = False
        tx.price_moment = "day" if "day" in (tx.price_moment, priced.moment) else priced.moment
    return Decimal(tx.fee_usd)


def _price_for(tx: Transaction, missing: str, db: Session) -> hourly_prices.Priced:
    """The price for a stored transaction's missing value: at the moment its
    other priced values have (so they share one price), else at the hour;
    without one, a 422 naming the transaction (a report fails on it, and the
    day alone doesn't say which entry to fix)."""
    try:
        with _priced_at_the_day(db, tx.price_moment == "day"):
            return _price_at(tx.timestamp, db)
    except HTTPException as e:
        day = tx.timestamp.date().isoformat() if tx.timestamp else "an unknown day"
        amount = format(Decimal(tx.amount or 0).normalize(), "f")
        raise HTTPException(
            status_code=e.status_code,
            detail=f"{tx.type} of {amount} BTC on {day}: {missing} (enter it in that transaction). {e.detail}",
        ) from e


def _price_at(timestamp: datetime, db: Session) -> hourly_prices.Priced:
    """
    The BTC price that values `timestamp`: its UTC hour's opening price,
    else its UTC day's, and which (services/hourly_prices.py); the day's
    within _priced_at_the_day. Never today's live price. Raises 422 when no
    price is available.
    """
    if db.info.get(DAY_PRICES):
        day = price_history.utc_day(timestamp)
        return hourly_prices.Priced(price_history.daily_price(db, timestamp), "day",
                                    datetime(day.year, day.month, day.day, tzinfo=timezone.utc))
    return hourly_prices.price_at(db, timestamp)


def date_of_death(when: date | datetime, db: Session) -> date:
    """
    An inheritance's date of death (#154): the calendar date the owner
    entered, which acquired_at holds as it is (#185). A time given with it
    (a file's, before it's saved) stands for its date in the tax timezone,
    never its UTC day (#177).
    """
    return original_date(when, get_tax_timezone(db))


def original_date(when: date | datetime, tz) -> date:
    """
    A date originally acquired (or of death) as the date it is: a date as
    given, a time without a timezone as the date written (it is in the tax
    timezone, as the imports read it), a moment as its date in the tax
    timezone, never its UTC day: more than 12 hours ahead of UTC (UTC+13,
    +14) noon is the day before in UTC, 12 hours behind (UTC-12) the day
    after (#177).
    """
    if not isinstance(when, datetime):
        return when
    return when.date() if when.tzinfo is None else local_date(when, tz)


def date_of_death_price(db: Session, when: date | datetime) -> hourly_prices.Priced:
    """An inheritance's price: the date of death has no hour, so that date's
    00:00 UTC price (price_history.daily_price), marked "day". 422 when
    there's none."""
    day = date_of_death(when, db)
    return hourly_prices.Priced(price_history.daily_price(db, day), "day",
                                datetime(day.year, day.month, day.day, tzinfo=timezone.utc))


def _valued_at_receipt(tx_data: dict, db: Session) -> bool:
    """A deposit with source Income, Interest, Reward, Rebate or Inherited into a BTC account."""
    if tx_data.get("type") != "Deposit" or normalized(tx_data.get("source")) not in VALUED_AT_RECEIPT:
        return False
    return _into_btc(tx_data, db)


def _is_inherited(tx_data: dict) -> bool:
    return normalized(tx_data.get("source")) == INHERITED_SOURCE


def _into_btc(tx_data: dict, db: Session) -> bool:
    to_acct = db.get(Account, tx_data.get("to_account_id")) if tx_data.get("to_account_id") else None
    return to_acct is not None and to_acct.currency == "BTC"


def _value_at_receipt(tx_data: dict, db: Session) -> bool:
    """
    An income or rebate deposit (source Income, Interest, Reward or Rebate
    into a BTC account) has a cost basis equal to its market value at
    receipt, which for income is also the income on the tax report (a rebate
    is never income, #98); an inherited one, its value on the date of death
    (IRC §1014; never income, #154). Entered without one (blank, or the
    form's 0), value it at the hour's BTC price (an inheritance: the date of
    death's day price; its moment in tx_data["price_moment"]) instead of
    saving $0; refuse to save when no price is available. Returns True when
    it filled cost_basis_usd.
    """
    if not _valued_at_receipt(tx_data, db) or Decimal(tx_data.get("cost_basis_usd") or 0) > 0:
        return False
    amount = Decimal(tx_data.get("amount") or 0)
    if amount <= 0:
        return False

    # When it was acquired: the hour received, or an inheritance's date of
    # death (#154; only those deposits of the five have an acquired_at)
    moment = tx_data.get("timestamp") or datetime.now(timezone.utc)
    when = "on the date of death" if _is_inherited(tx_data) else "at receipt"
    try:
        priced = date_of_death_price(db, tx_data.get("acquired_at") or moment) if _is_inherited(tx_data) \
            else _price_at(moment, db)
    except HTTPException as e:
        raise HTTPException(
            status_code=422,
            detail=f"{e.detail} Enter this {tx_data['source']} deposit's USD value {when} as its cost basis.",
        )
    tx_data["cost_basis_usd"] = (priced.usd * amount).quantize(Decimal("0.01"))
    _note_moment(tx_data, priced.moment)
    return True


def maybe_transfer_bitcoin_lot(tx: Transaction, tx_data: dict, db: Session):
    """
    Splits source lots for an internal BTC transfer from one BTC account to another,
    disposing the fee portion and carrying forward the remainder as a new partial-lot.
    A move within one account (a UTXO consolidation, or between two wallets
    BitcoinTX pools, #159) disposes of the fee only: the coins that moved stay
    in their lots, with their dates and basis.
    """
    from_acct = db.get(Account, tx.from_account_id) if tx.from_account_id else None
    to_acct = db.get(Account, tx.to_account_id) if tx.to_account_id else None
    if not from_acct or not to_acct:
        return
    if from_acct.currency != "BTC" or to_acct.currency != "BTC":
        return

    # Transfer amount is what LEFT the source, fee included (the UI's
    # "amount sent"); the destination receives amount - fee. This matches
    # build_ledger_entries_for_transaction, so lots and balances agree.
    btc_outflow = Decimal(tx.amount or 0)
    fee_btc = Decimal(tx.fee_amount or 0) if (tx.fee_currency or "").upper() == "BTC" else Decimal("0")
    if fee_btc > btc_outflow:
        raise HTTPException(
            status_code=400,
            detail=f"Transfer fee {fee_btc} exceeds the amount sent {btc_outflow}"
        )
    if btc_outflow <= 0:
        return

    lots = _open_lots(tx.from_account_id, db)
    if tx.from_account_id == tx.to_account_id:
        btc_outflow = _fee_leaving_account(lots, btc_outflow, fee_btc)

    move = _LotMove(tx, btc_outflow, fee_btc, db)
    move.take_all(lots)
    move.add_destination_lots()
    db.flush()


def _fee_leaving_account(lots: list[BitcoinLot], btc_outflow: Decimal, fee_btc: Decimal) -> Decimal:
    """A move within one account (#159): the coins sent must be there, as for
    any transfer, and only the fee leaves the account (IRS digital-asset FAQ
    Q81, Q97). What leaves it."""
    if sum(lot.remaining_btc for lot in lots) < btc_outflow:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough BTC to transfer {btc_outflow} (including fee {fee_btc})"
        )
    return fee_btc


class _LotMove:
    """
    A BTC transfer's amount (fee included) taken from the source's lots,
    oldest first. The fee's part is disposed of at the fee's stored USD
    value (its running share per lot when it spans lots, so the parts add
    up to fee_usd exactly and none is below zero, #297). The rest becomes
    lots in the destination, each keeping its source lot's acquisition date
    and share of basis.
    """

    def __init__(self, tx: Transaction, btc_outflow: Decimal, fee_btc: Decimal, db: Session):
        self.tx, self.btc_outflow, self.fee_btc, self.db = tx, btc_outflow, fee_btc, db
        self.remaining_outflow = btc_outflow
        self.remaining_fee = fee_btc
        self.to_destination: list[tuple[Decimal, Decimal, datetime, bool]] = []

    def take_all(self, lots: list[BitcoinLot]) -> None:
        """The whole outflow from `lots`, oldest first; too little BTC is a 400."""
        for lot in lots:
            if self.remaining_outflow <= 0:
                break
            if lot.remaining_btc > 0:
                self.take_from(lot)
        if self.remaining_fee > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Not enough BTC to cover fee {self.fee_btc}"
            )
        if self.remaining_outflow > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Not enough BTC to transfer {self.btc_outflow} (including fee {self.fee_btc})"
            )

    def take_from(self, lot: BitcoinLot) -> None:
        btc_to_use = min(lot.remaining_btc, self.remaining_outflow)
        self.remaining_outflow -= btc_to_use

        # The fee's piece first, then the moved one, each with its cost
        # taken from the lot in turn (piece_cost), so none is lost (#100)
        portion_for_fee = min(btc_to_use, self.remaining_fee)
        portion_for_dest = btc_to_use - portion_for_fee
        if portion_for_fee > 0:
            self.dispose_fee(lot, portion_for_fee, piece_cost(lot, portion_for_fee))
            lot.remaining_btc -= portion_for_fee
        if portion_for_dest > 0:
            self.to_destination.append(
                (portion_for_dest, piece_cost(lot, portion_for_dest), lot.acquired_date, lot.inherited))
            lot.remaining_btc -= portion_for_dest
        self.db.add(lot)

    def dispose_fee(self, lot: BitcoinLot, portion: Decimal, disposal_basis: Decimal) -> None:
        fee_usd = _stored_fee_usd(self.tx, self.fee_btc, self.db)
        proceeds_for_fee = running_share(fee_usd, self.fee_btc - self.remaining_fee, portion, self.fee_btc)
        self.db.add(LotDisposal(
            lot_id=lot.id,
            transaction_id=self.tx.id,
            disposed_btc=portion,
            disposal_basis_usd=disposal_basis,
            proceeds_usd_for_that_portion=proceeds_for_fee,
            realized_gain_usd=proceeds_for_fee - disposal_basis,
            holding_period=lot_holding_period(lot, self.tx.timestamp, get_tax_timezone(self.db)),
            is_fee=True,
        ))
        self.remaining_fee -= portion

    def add_destination_lots(self) -> None:
        for amt_btc, cost_portion, acquired_date, inherited in self.to_destination:
            if acquired_date.tzinfo is None:
                acquired_date = acquired_date.replace(tzinfo=timezone.utc)
            self.db.add(BitcoinLot(
                created_txn_id=self.tx.id,
                acquired_date=acquired_date,
                total_btc=amt_btc,
                remaining_btc=amt_btc,
                cost_basis_usd=cost_portion,
                inherited=inherited,  # inherited coins stay inherited (#154)
            ))


def recalculate_ledger(db: Session) -> None:
    """Recalculate Ledger: the whole ledger again, committed. A price it
    needs is looked for with the lock free (hourly_prices.with_prices_found,
    #426)."""
    def save() -> None:
        recalculate_all_transactions(db)
        db.commit()

    hourly_prices.with_prices_found(db, save)


def recalculate_all_transactions(db: Session, until: datetime | None = None, *,
                                 past_missing: list[Transaction] | None = None):
    """
    "Scorched Earth": remove all ledger lines, partial-lot disposals,
    and BitcoinLots. Then re-lot everything in chronological order.

    With `until`, only transactions strictly before it are replayed — a
    snapshot of lots/balances as of that instant (used for year-end
    balances). Callers must run a full recalculation afterwards. A row
    naming a missing account that stops it is refused by name
    (AccountMissing, #337); given a `past_missing` list (an edit or a delete
    of such a row, #368), it's replayed without the balance check it fails,
    and added to the list.
    """
    db.query(LedgerEntry).delete()
    db.query(LotDisposal).delete()
    db.query(BitcoinLot).delete()
    db.flush()

    query = db.query(Transaction)
    if until is not None:
        query = query.filter(Transaction.timestamp < until)
    all_txs = query.order_by(Transaction.timestamp.asc(), Transaction.id.asc()).all()
    known = known_accounts(db)
    for rec_tx in all_txs:
        _replay(rec_tx, db, known, past_missing)

    db.flush()


def _replay(tx: Transaction, db: Session, known: set[int], past_missing: list[Transaction] | None) -> None:
    """One saved transaction's ledger lines and lots, in the replay. Its
    balance check failing on a missing account is refused by name, or, with
    a `past_missing` list, it goes on, as a row naming a missing account
    that passes its check does, and is added to it (#368). Any other refusal
    (short of BTC, say) stays its own."""
    _fill_stored_fee_currency(tx, db)
    stored = _stored_inputs(tx)
    build_ledger_entries_for_transaction(tx, stored, db)
    try:
        _maybe_verify_balance_for_internal(tx, db)
    except HTTPException as e:
        missing = missing_accounts(tx, known)
        if e.status_code != 400 or not missing:
            raise
        if past_missing is None:
            raise AccountMissing(tx, missing, local_date(tx.timestamp, get_tax_timezone(db))) from e
        past_missing.append(tx)
    _post_lots(tx, stored, db)


def _stored_inputs(tx: Transaction) -> dict:
    """A saved transaction's inputs, as the ledger steps read them."""
    return {
        "from_account_id": tx.from_account_id,
        "to_account_id": tx.to_account_id,
        "type": tx.type,
        "amount": tx.amount,
        "fee_amount": tx.fee_amount,
        "fee_currency": tx.fee_currency,
        "cost_basis_usd": tx.cost_basis_usd,
        "proceeds_usd": tx.proceeds_usd,
        "timestamp": tx.timestamp,
        "source": tx.source,
        "purpose": tx.purpose,
        "gross_proceeds_usd": tx.gross_proceeds_usd,
        "fmv_usd": tx.fmv_usd,
    }


def _post_lots(tx: Transaction, tx_data: dict, db: Session) -> None:
    """Its effect on the BTC lots: a Deposit or Buy acquires a lot, a Sell or
    Withdrawal disposes of the oldest BTC first (then its figures are summed
    up from those disposals), a Transfer moves lots between accounts."""
    if tx.type in ("Deposit", "Buy"):
        maybe_create_bitcoin_lot(tx, tx_data, db)
    elif tx.type in ("Sell", "Withdrawal"):
        maybe_dispose_lots_fifo(tx, tx_data, db)
        compute_sell_summary_from_disposals(tx, db)
    elif tx.type == "Transfer":
        maybe_transfer_bitcoin_lot(tx, tx_data, db)


def _default_btc_transfer_fee(tx: Transaction, db: Session) -> None:
    """A new BTC transfer without a fee gets 0 in BTC, which its lot move reads."""
    from_acct = db.get(Account, tx.from_account_id)
    if from_acct and from_acct.currency == "BTC":
        if tx.fee_amount is None or tx.fee_amount <= 0:
            logger.warning(f"Transfer {tx.id} missing fee_amount; defaulting to 0")
            tx.fee_amount = Decimal("0")
        if not tx.fee_currency:
            tx.fee_currency = "BTC"


# Double-Entry (with Cross-Currency Skip) & Fee Rules
def _maybe_verify_balance_for_internal(tx: Transaction, db: Session):
    """
    If type=Buy or Sell => skip net-zero check (cross-currency).
    Otherwise, enforce net=0 for internal transactions (not external=99).
    """
    if tx.type in ("Buy", "Sell"):
        return
    _verify_double_entry_balance_for_internal(tx, db)


def _verify_double_entry_balance_for_internal(tx: Transaction, db: Session):
    """
    Ensure that ledger entries net to 0 by currency for internal transactions.
    Skip checks if from or to is external account.
    """
    if tx.from_account_id == ACCOUNT_EXTERNAL or tx.to_account_id == ACCOUNT_EXTERNAL:
        return

    entries = db.query(LedgerEntry).filter(LedgerEntry.transaction_id == tx.id).all()
    sums_by_currency = defaultdict(Decimal)
    for entry in entries:
        if entry.account_id != ACCOUNT_EXTERNAL:
            sums_by_currency[entry.currency] += entry.amount

    for currency, total in sums_by_currency.items():
        if total != Decimal("0"):
            raise HTTPException(
                status_code=400,
                detail=f"Ledger not balanced for {currency}: {total}"
            )


def _enforce_broker_reporting(tx_type, value) -> None:
    """A 1099-DA override only makes sense on a Sell or Withdrawal."""
    if value is not None and tx_type not in BROKER_REPORTING_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"broker_reporting can only be set on a Sell or Withdrawal, not a {tx_type}.",
        )


# Input validation (create, and the merged row on update)
USER_ACCOUNTS = {ACCOUNT_BANK, ACCOUNT_WALLET, ACCOUNT_EXCHANGE_USD, ACCOUNT_EXCHANGE_BTC, ACCOUNT_EXTERNAL}
TX_TYPES = ("Deposit", "Withdrawal", "Transfer", "Buy", "Sell")
WITHDRAWAL_PURPOSES = ("Spent", "Gift", "Donation", "Lost")
DEPOSIT_SOURCES = ("MyBTC", "Gift", "Inherited", "Income", "Interest", "Reward", "Rebate", "N/A")
FEE_CURRENCIES = ("USD", "BTC")
GENESIS = datetime(2009, 1, 3, tzinfo=timezone.utc)
MAX_TEXT = 64
MAX_BTC = Decimal("21000000")
DEPOSIT_BASIS_REQUIRED = "Enter this deposit's cost basis (0 if it's unknown)."
BUY_BASIS_REQUIRED = "A buy needs its cost basis (cost_basis_usd): what the BTC cost in USD, before the fee."
INHERITED_NEEDS_DATE = "An Inherited deposit needs the date of death (acquired_at)."
FEE_CURRENCY_UNKNOWN = "fee_currency must be USD or BTC."
TEXT_ON_ONE_LINE = "{} must be one line of text, without a line break, tab or other control character."
DEPOSIT_SOURCE_UNKNOWN = "A deposit's source must be one of: " + ", ".join(DEPOSIT_SOURCES) + "."
SAME_ACCOUNT_NEEDS_FEE = "A move within the same account records only its network fee: enter the fee."
USD_AMOUNT_CENTS = "A USD amount can have at most 2 decimal places."
USD_FEE_CENTS = "A USD fee can have at most 2 decimal places."
BTC_AMOUNT_CAP = "A BTC amount can't be more than 21,000,000."
BEFORE_BITCOIN = "The date is before Bitcoin existed (3 January 2009)."
DATE_AHEAD = "The date is in the future."
SELL_FEE_OVER_PROCEEDS = "The sell's fee is more than its proceeds."
TRANSFER_FEE_OVER_AMOUNT = "Transfer fee exceeds the amount sent (amount includes the fee)."

# The API's rule for each money field (schemas/transaction.py), checked here
# too, on the value and on the value as stored: the imports build their rows
# without the API's schema, and a value the database can't give back within
# the rule would be saved, then fail every listing. The amount and the fee
# take the BTC rule whatever their account (their columns hold 8 decimals);
# _check_amount adds cents in a USD account.
_MONEY_RULES = {
    "amount": validate_btc_storable,
    "fee_amount": validate_btc_storable,
    "cost_basis_usd": validate_usd_storable,
    "proceeds_usd": validate_usd_storable,
    "gross_proceeds_usd": validate_usd_storable,
    "fmv_usd": validate_usd_storable,
    "fee_usd": validate_usd_storable,
}


def _canonical(value, choices) -> str | None:
    """The listed spelling of a case-insensitive match, else None."""
    if value is None:
        return None
    lowered = str(value).strip().lower()
    return next((c for c in choices if c.lower() == lowered), None)


def _bad(detail: str):
    raise HTTPException(status_code=422, detail=detail)


def _validate_transaction(data: dict, db: Session, check_source: bool = True,
                          kept_text: frozenset = frozenset(), stored: Transaction | None = None) -> None:
    """
    Reject input the ledger would record wrongly, with a clear message; set
    canonical spellings in `data`, and drop what a dollar withdrawal can't
    hold (_drop_btc_withdrawal_fields). Used on create, and on update with the
    stored row merged with the change, so a partial edit is checked as a
    whole transaction. check_source=False keeps a deposit's stored source
    unchecked (an edit that doesn't change it); `stored` is the row an edit
    changes. The checks run in a fixed order, and the first that fails is
    the message.
    """
    tx_type = _checked_type(data)
    _check_timestamp(data)
    from_acct, to_acct = _checked_accounts(data, db)
    _check_money_limits(data)
    _check_amount(data, tx_type, from_acct, to_acct)
    fee = Decimal(data.get("fee_amount") or 0)
    _check_not_negative(data, fee)
    _check_fee_currency(data, tx_type, fee, from_acct, to_acct)
    if tx_type == "Sell":
        _check_sell_proceeds(data, fee)
    _set_canonical_spellings(data, kept_text)
    _drop_btc_withdrawal_fields(data, tx_type, from_acct)
    _check_type_requirements(data, tx_type, check_source, from_acct, to_acct)
    _check_original_date(data, tx_type, to_acct, db, stored)


def _checked_type(data: dict) -> str:
    tx_type = data.get("type")
    tx_type = getattr(tx_type, "value", tx_type)
    if tx_type not in TX_TYPES:
        _bad(f"Unknown transaction type: {tx_type}.")
    data["type"] = tx_type
    return tx_type


# The save's rules as helpers that return what's wrong (None when nothing
# is): the save calls them, and so does the CSV preview, so the preview
# refuses what the save's checks of a row refuse (#266, #285). The ledger's
# balance is the save's alone.

def timestamp_problem(ts: datetime) -> str | None:
    """Not before Bitcoin, nor more than a day ahead (a naive time is UTC)."""
    ts_utc = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    if ts_utc < GENESIS:
        return BEFORE_BITCOIN
    if ts_utc > datetime.now(timezone.utc) + timedelta(days=1):
        return DATE_AHEAD
    return None


def amount_problem(amount: Decimal, tx_type: str, currency: str | None) -> str | None:
    """An amount counted in `currency` (its main account's: the receiver's
    for a Deposit or Buy, else the sender's): cents at most in dollars
    (a Buy's amount is bitcoin), at most 21,000,000 in bitcoin."""
    if currency == "USD" and tx_type != "Buy" and _past_the_cent(amount):
        return USD_AMOUNT_CENTS
    if currency == "BTC" and amount > MAX_BTC:
        return BTC_AMOUNT_CAP
    return None


def fee_currency_problem(tx_type: str, fee: Decimal, fee_cur: str, from_currency: str | None,
                         to_currency: str | None) -> str | None:
    """A withdrawal's fee in the currency of the account it leaves, a
    deposit's in that of the account it reaches."""
    if fee > 0 and tx_type in ("Withdrawal", "Deposit"):
        currency = from_currency if tx_type == "Withdrawal" else to_currency
        if currency is not None and fee_cur and fee_cur != currency:
            return f"A {tx_type.lower()} fee must be in {currency}, the account's currency."
    return None


def fee_currency_used(tx_type: str, fee_cur: str | None, from_currency: str | None,
                      to_currency: str | None) -> str | None:
    """The currency a fee is saved in: the one given, else the one its type
    takes (USD for a Buy or Sell, else the currency of the account it's paid
    from, or for a deposit the one it reaches); None when that's unknown."""
    if fee_cur:
        return fee_cur
    if tx_type in ("Buy", "Sell"):
        return "USD"
    return to_currency if tx_type == "Deposit" else from_currency


def fee_cents_problem(fee: Decimal, currency: str | None) -> str | None:
    """A fee in dollars is in cents: the ledger keeps no fraction of one, so
    a $0.005 fee would be lost from a lot's cost (#298)."""
    return USD_FEE_CENTS if currency == "USD" and _past_the_cent(fee) else None


def sell_fee_problem(gross: Decimal, fee: Decimal) -> str | None:
    """A sell's fee comes out of its proceeds: never more than them."""
    return SELL_FEE_OVER_PROCEEDS if fee > gross else None


def transfer_fee_problem(from_currency: str | None, fee: Decimal, amount: Decimal | None) -> str | None:
    """A bitcoin transfer's amount includes its fee: never less than it."""
    if from_currency == "BTC" and amount is not None and fee > amount:
        return TRANSFER_FEE_OVER_AMOUNT
    return None


def text_problem(key: str, value) -> str | None:
    """A purpose or source the save keeps: at most MAX_TEXT characters."""
    if value is not None and len(str(value)) > MAX_TEXT:
        return f"{key} is too long (at most {MAX_TEXT} characters)."
    return None


def _check_timestamp(data: dict) -> None:
    ts = data.get("timestamp")
    if ts is None:
        _bad("A date and time is required.")
    problem = timestamp_problem(ts)
    if problem:
        _bad(problem)
    # Whole seconds: stored as text and compared as text, a fraction sorted
    # before the whole second ("...00.5Z" < "...00Z", a sale half a second
    # into a year fell in the year before).
    data["timestamp"] = ts.replace(microsecond=0)


def _checked_accounts(data: dict, db: Session) -> tuple[Account | None, Account | None]:
    """(from account, to account); an id that isn't one of the user's
    accounts or External is refused."""
    for key in ("from_account_id", "to_account_id"):
        acct_id = data.get(key)
        if acct_id is not None and acct_id not in USER_ACCOUNTS:
            _bad(f"Unknown account id {acct_id}.")
    from_acct = db.get(Account, data["from_account_id"]) if data.get("from_account_id") else None
    to_acct = db.get(Account, data["to_account_id"]) if data.get("to_account_id") else None
    return from_acct, to_acct


def _check_money_limits(data: dict) -> None:
    """Every money field given is a finite number within its rule, as given
    and as the database will store it."""
    for key, rule in _MONEY_RULES.items():
        if data.get(key) is None:
            continue
        try:
            rule(Decimal(data[key]))
        except InvalidOperation:
            _bad(f"{key} is not a number.")
        except ValueError as problem:
            _bad(f"{key}: {problem}")


def _check_amount(data: dict, tx_type: str, from_acct: Account | None, to_acct: Account | None) -> None:
    amount = data.get("amount")
    if amount is None or Decimal(amount) <= 0:
        _bad("The amount must be more than 0.")
    amount = Decimal(amount)
    # The account the amount is counted in: the sender, or for a deposit the receiver.
    main_acct = to_acct if tx_type in ("Deposit", "Buy") else from_acct
    problem = amount_problem(amount, tx_type, main_acct.currency if main_acct is not None else None)
    if problem:
        _bad(problem)


def _past_the_cent(amount: Decimal) -> bool:
    """More than 2 decimal places, trailing zeros aside ("1.230" has 2)."""
    return -amount.normalize().as_tuple().exponent > 2


def _check_not_negative(data: dict, fee: Decimal) -> None:
    if fee < 0:
        _bad("The fee can't be negative.")
    for key in ("cost_basis_usd", "proceeds_usd", "gross_proceeds_usd", "fmv_usd", "fee_usd"):
        if data.get(key) is not None and Decimal(data[key]) < 0:
            _bad(f"{key} can't be negative.")


def _check_fee_currency(data: dict, tx_type: str, fee: Decimal, from_acct: Account | None,
                        to_acct: Account | None) -> None:
    """A fee is in USD or BTC: a withdrawal's in the currency of the account
    it leaves, a deposit's in that of the account it reaches."""
    fee_cur = (data.get("fee_currency") or "").upper()
    if fee_cur and fee_cur not in FEE_CURRENCIES:
        _bad(FEE_CURRENCY_UNKNOWN)
    from_cur, to_cur = (from_acct.currency if from_acct else None), (to_acct.currency if to_acct else None)
    own = fee_currency_used(tx_type, None, from_cur, to_cur)
    # A fee in another currency than its type's gets that message (here or
    # in the fee rules), not the cents one
    cents = fee_cents_problem(fee, fee_cur or own) if fee_cur in ("", own) else None
    problem = fee_currency_problem(tx_type, fee, fee_cur, from_cur, to_cur) or cents
    if problem:
        _bad(problem)


def _check_sell_proceeds(data: dict, fee: Decimal) -> None:
    gross = data.get("gross_proceeds_usd")
    if gross is None:
        gross = data.get("proceeds_usd")
    if gross is None:
        _bad("A sell needs its proceeds (gross_proceeds_usd).")
    problem = sell_fee_problem(Decimal(gross), fee)
    if problem:
        _bad(problem)


def _set_canonical_spellings(data: dict, kept_text: frozenset = frozenset()) -> None:
    """A purpose or source in the listed spelling ("gift" is Gift). Either
    one too long is refused, and so is other text that isn't a single line:
    it is kept as written, and the CSV files and reports show it in one cell.
    `kept_text`: the ones an edit leaves as stored, not checked for that."""
    for key, choices in (("purpose", WITHDRAWAL_PURPOSES), ("source", DEPOSIT_SOURCES)):
        value = data.get(key)
        problem = text_problem(key, value)
        if problem:
            _bad(problem)
        canonical = _canonical(value, choices)
        if canonical:
            data[key] = canonical
        elif value is not None and key not in kept_text and has_control_character(value):
            _bad(TEXT_ON_ONE_LINE.format(key))


def has_control_character(value) -> bool:
    """Whether the text holds a control character (a line break, a tab, any
    other C0 or C1 control) or a line or paragraph separator."""
    return any(unicodedata.category(char) in ("Cc", "Zl", "Zp") for char in str(value))


# What only a withdrawal of bitcoin holds besides its purpose: its proceeds
# or fair market value (#449)
_BTC_WITHDRAWAL_VALUES = ("proceeds_usd", "gross_proceeds_usd", "fmv_usd")


def _drop_btc_withdrawal_fields(data: dict, tx_type: str, from_acct: Account | None) -> None:
    """
    A dollar withdrawal (from Bank or Exchange USD) keeps no value and no
    bitcoin purpose: only bitcoin leaving is spent, given, donated or lost
    (#449). One sent all the same (left from the form's bitcoin fields after
    the account changed, or by the AI connector or an older file) is
    dropped, not refused, as an edit drops a dollar deposit's basis
    (_revalue_income_deposit): kept, the tax report would list it as a gift
    of bitcoin and the dashboard count it as spent. Other text stays: a
    dollar withdrawal's purpose may be a label ("Rent"). Run after
    _set_canonical_spellings, so " gift " is Gift.
    """
    if tx_type == "Withdrawal" and from_acct is not None and from_acct.currency != "BTC":
        data.update(dict.fromkeys(_BTC_WITHDRAWAL_VALUES))
        if data.get("purpose") in WITHDRAWAL_PURPOSES:
            data["purpose"] = None


def _check_type_requirements(data: dict, tx_type: str, check_source: bool, from_acct: Account | None,
                             to_acct: Account | None) -> None:
    # A deposit's source is one of the listed ones (blank means N/A). Rows
    # saved before v1.1.0 may hold other text: they still load, recalculate
    # and keep it through an edit that leaves the source alone.
    if tx_type == "Deposit" and check_source and str(data.get("source") or "").strip() \
            and data.get("source") not in DEPOSIT_SOURCES:
        _bad(DEPOSIT_SOURCE_UNKNOWN)

    if tx_type == "Withdrawal" and from_acct is not None and from_acct.currency == "BTC":
        if data.get("purpose") not in WITHDRAWAL_PURPOSES:
            _bad("A BTC withdrawal needs a purpose: Spent, Gift, Donation or Lost.")

    # Inherited coins are valued, and sorted first in, first out, by the date
    # of death (#154): without it, the deposit's date would stand in silently
    if tx_type == "Deposit" and to_acct is not None and to_acct.currency == "BTC" \
            and _is_inherited(data) and data.get("acquired_at") is None:
        _bad(INHERITED_NEEDS_DATE)

    # A BTC deposit that isn't income or a rebate (MyBTC, Gift, N/A...) needs
    # its cost basis stated: a blank one would make its whole value gain when
    # it's sold. Income and rebates are valued at the hour's price instead
    # (_value_at_receipt).
    if tx_type == "Deposit" and to_acct is not None and to_acct.currency == "BTC" \
            and normalized(data.get("source")) not in VALUED_AT_RECEIPT and data.get("cost_basis_usd") is None:
        _bad(DEPOSIT_BASIS_REQUIRED)

    # A Buy's lot costs its basis: a blank one would be a $0 lot, its whole
    # proceeds gain when sold (#459). Checked on the row an edit makes too,
    # so a type change to a Buy (which drops the old type's figures,
    # _drop_fields_of_old_type) needs one, as does any edit of a Buy saved
    # without one.
    if tx_type == "Buy" and data.get("cost_basis_usd") is None:
        _bad(BUY_BASIS_REQUIRED)


def _takes_original_date(tx_type: str | None, source: str | None, to_acct: Account | None) -> bool:
    return tx_type == "Deposit" and to_acct is not None and to_acct.currency == "BTC" \
        and normalized(source) in ORIGINAL_DATE_SOURCES


def original_date_name(source: str | None) -> str:
    """What acquired_at is, in a message: an Inherited deposit's date of death."""
    return "The date of death" if _is_inherited({"source": source}) else "The date originally acquired"


def original_date_problem(tx_type: str | None, source: str | None, into_btc: bool, acquired: date,
                          deposit: datetime | None, tz) -> str | None:
    """
    Why a date originally acquired can't go on this row, or None. Only on a
    My BTC, Gift or Inherited deposit (its date of death) into a BTC account,
    no earlier than the day Bitcoin began and no later than the deposit's
    day in the tax timezone (deposit None: not compared).
    """
    if not (tx_type == "Deposit" and into_btc and normalized(source) in ORIGINAL_DATE_SOURCES):
        return ("A date originally acquired is only for a My BTC or Gift deposit, or an Inherited one's date of "
                "death, into Wallet or Exchange BTC.")
    what = original_date_name(source)
    if acquired < GENESIS.date():
        return f"{what} is before Bitcoin existed (3 January 2009)."
    if deposit is not None and acquired > local_date(deposit, tz):
        return f"{what} can't be after the deposit's date."
    return None


def _check_original_date(data: dict, tx_type: str, to_acct: Account | None, db: Session,
                         stored: Transaction | None) -> None:
    """
    The date originally acquired, checked and stored as a date (#185): the
    date the owner gave stays that date whatever the tax timezone becomes.
    A time given with it stands for its date in the tax timezone.
    """
    acquired = data.get("acquired_at")
    if acquired is None:
        return
    tz = get_tax_timezone(db)
    try:
        acquired = original_date(acquired, tz)
    except DateOutOfRange:  # a moment past Python's years in the tax timezone (#211)
        _bad(date_out_of_range(original_date_name(data.get("source"))))
    deposit = data["timestamp"]
    # An edit that keeps the date and the deposit's day isn't refused for
    # them: a change of tax timezone since can put the deposit on the day
    # before its date, and every edit of the deposit would fail (its lot is
    # never after the deposit: _lot_acquired)
    if stored is not None and acquired == stored.acquired_at \
            and local_date(deposit, tz) == local_date(stored.timestamp, tz):
        deposit = None
    into_btc = to_acct is not None and to_acct.currency == "BTC"
    problem = original_date_problem(tx_type, data.get("source"), into_btc, acquired, deposit, tz)
    if problem:
        _bad(problem)
    data["acquired_at"] = acquired


def _fill_fee_currency(data: dict, db: Session) -> bool:
    """
    A fee given without its currency gets the one its type allows: USD for
    a Buy or Sell, else the currency of the account it's paid from (for a
    deposit, the account it goes to). It is stored with the transaction, so
    the ledger lines, the lots and the fee rules all read the same value;
    they used to read a missing one as BTC, as no fee and as USD, and a fee
    could leave the balance with no disposal. Returns True when it filled.
    """
    if data.get("fee_currency") or Decimal(data.get("fee_amount") or 0) <= 0:
        return False
    currency = fee_currency_used(data.get("type"), None, _currency_of(data.get("from_account_id"), db),
                                 _currency_of(data.get("to_account_id"), db))
    if currency is None:
        return False
    data["fee_currency"] = currency
    return True


def _currency_of(account_id: int | None, db: Session) -> str | None:
    acct = db.get(Account, account_id) if account_id else None
    return acct.currency if acct else None


def _fill_stored_fee_currency(tx: Transaction, db: Session) -> None:
    """The same for a row saved without it (before the fill above)."""
    data = {k: getattr(tx, k) for k in ("type", "fee_amount", "fee_currency", "from_account_id", "to_account_id")}
    if _fill_fee_currency(data, db):
        tx.fee_currency = data["fee_currency"]


def _enforce_fee_rules(tx_data: dict, db: Session):
    """
    Validate fee usage by transaction type:
      - Transfer => fee must match from_acct currency; a move within one
        account (#159) records only its fee, so it needs one
      - Buy/Sell => fee must be USD
      - Deposit/Withdrawal => no special fee rule
    """
    tx_type = tx_data.get("type")
    from_id = tx_data.get("from_account_id")
    fee_amt = Decimal(tx_data.get("fee_amount") or 0)
    fee_cur = (tx_data.get("fee_currency") or "").upper()  # filled by _fill_fee_currency

    if tx_type == "Transfer" and from_id == tx_data.get("to_account_id") and fee_amt <= 0:
        raise HTTPException(status_code=400, detail=SAME_ACCOUNT_NEEDS_FEE)

    # If there's no fee, skip checks
    if fee_amt <= 0:
        return

    if tx_type == "Transfer":
        if not from_id or from_id == ACCOUNT_EXTERNAL:
            return
        from_acct = db.get(Account, from_id)
        if from_acct and from_acct.currency == "BTC" and fee_cur != "BTC":
            raise HTTPException(
                status_code=400,
                detail="Transfer from BTC => fee must be BTC."
            )
        amount = tx_data.get("amount")  # absent on partial updates
        problem = transfer_fee_problem(from_acct.currency if from_acct else None, fee_amt,
                                       Decimal(amount) if amount is not None else None)
        if problem:
            raise HTTPException(status_code=400, detail=problem)
        if from_acct and from_acct.currency == "USD" and fee_cur != "USD":
            raise HTTPException(
                status_code=400,
                detail="Transfer from USD => fee must be USD."
            )

    elif tx_type in ("Buy", "Sell"):
        if fee_cur != "USD":
            raise HTTPException(
                status_code=400,
                detail=f"{tx_type} => fee must be USD."
            )


# Each type's rules for its accounts: (broken(from_id, to_id), message), in
# the order they're checked.
_TYPE_ACCOUNT_RULES = {
    "Deposit": [
        (lambda f, t: f != ACCOUNT_EXTERNAL, "Deposit => from must be External."),
        (lambda f, t: not t or t == ACCOUNT_EXTERNAL, "Deposit => to must be an internal account."),
    ],
    "Withdrawal": [
        (lambda f, t: not f or f == ACCOUNT_EXTERNAL, "Withdrawal => from must be an internal account."),
        (lambda f, t: t != ACCOUNT_EXTERNAL, "Withdrawal => to must be External."),
    ],
    "Transfer": [
        (lambda f, t: not f or f == ACCOUNT_EXTERNAL or not t or t == ACCOUNT_EXTERNAL,
         "Transfer => both from/to must be internal."),
        # Only a BTC account can send to itself: a consolidation (#159)
        (lambda f, t: f == t and f not in BTC_ACCOUNTS, "Transfer => from and to must be different accounts."),
    ],
    "Buy": [
        (lambda f, t: f not in (ACCOUNT_BANK, ACCOUNT_EXCHANGE_USD), "Buy => from must be Bank or Exchange USD."),
        (lambda f, t: t != ACCOUNT_EXCHANGE_BTC, "Buy => to must be Exchange BTC."),
    ],
    "Sell": [
        (lambda f, t: f != ACCOUNT_EXCHANGE_BTC, "Sell => from must be Exchange BTC."),
        (lambda f, t: t != ACCOUNT_EXCHANGE_USD, "Sell => to must be Exchange USD."),
    ],
}


def _enforce_transaction_type_rules(tx_data: dict, db: Session):
    """
    The accounts each type allows: a Deposit from External to one of the
    user's accounts, a Withdrawal the other way, a Transfer between two of
    them in the same currency (or from a BTC account to itself: a
    consolidation, #159), a Buy from Bank or Exchange USD to Exchange BTC, a
    Sell from Exchange BTC to Exchange USD.
    """
    tx_type = tx_data.get("type")
    from_id = tx_data.get("from_account_id")
    to_id = tx_data.get("to_account_id")
    if tx_type not in _TYPE_ACCOUNT_RULES:
        raise HTTPException(400, f"Unknown transaction type: {tx_type}")
    for broken, message in _TYPE_ACCOUNT_RULES[tx_type]:
        if broken(from_id, to_id):
            raise HTTPException(400, message)
    if tx_type == "Transfer":
        db_from = db.get(Account, from_id)
        db_to = db.get(Account, to_id)
        if db_from and db_to and db_from.currency != db_to.currency:
            raise HTTPException(400, "Transfer => same currency required.")


def delete_all_transactions(db: Session) -> int:
    """
    Bulk cleanup: remove all transactions (and references).
    Return how many were deleted.
    """
    all_txs = db.query(Transaction).all()
    count = len(all_txs)
    for tx in all_txs:
        db.delete(tx)
    db.commit()
    return count
