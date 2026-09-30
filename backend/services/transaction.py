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
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_DOWN, InvalidOperation
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from backend.models.transaction import (Transaction, LedgerEntry, BitcoinLot, LotDisposal)
from backend.models.account import Account
from backend.services import price_history
from backend.services.tax_time import get_tax_timezone
from backend.constants import (
    ACCOUNT_WALLET,
    ACCOUNT_BANK,
    ACCOUNT_EXCHANGE_USD,
    ACCOUNT_EXCHANGE_BTC,
    ACCOUNT_EXTERNAL,
    BROKER_REPORTING_TYPES,
    INCOME_SOURCES,
)

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
    once, for all its rows).
    """
    ensure_fee_account_exists(db)
    _prepare_input(tx_data, db)
    new_tx = _insert(tx_data, db)

    remove_ledger_entries_for_tx(new_tx, db)
    build_ledger_entries_for_transaction(new_tx, tx_data, db)
    _maybe_verify_balance_for_internal(new_tx, db)
    if new_tx.type == "Transfer":
        _default_btc_transfer_fee(new_tx, db)
    _post_lots(new_tx, tx_data, db)
    _recalculate_if_backdated(new_tx, db)

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
    _value_income_deposit(tx_data, db)
    _value_btc_fee(tx_data, db, manual=tx_data.get("fee_usd") is not None)
    if tx_data.get("fee_usd_from_price") and tx_data.get("fee_usd") is not None:
        # A CSV re-import of a value once priced from the day (not typed):
        # kept as it was, and still re-priced if the date or fee changes.
        tx_data["fee_usd_manual"] = False


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
        is_locked=tx_data.get("is_locked", False),
        created_at=now_utc,
        updated_at=now_utc
    )
    db.add(new_tx)
    db.flush()  # new_tx.id is now available
    return new_tx


def _recalculate_if_backdated(new_tx: Transaction, db: Session) -> None:
    """A transaction dated before the latest one changes which lots the
    later ones used: recalculate everything, in time order."""
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
        recalculate_all_transactions(db)


_VALIDATED_FIELDS = (
    "type", "timestamp", "from_account_id", "to_account_id", "amount", "fee_amount", "fee_currency",
    "cost_basis_usd", "proceeds_usd", "gross_proceeds_usd", "fmv_usd", "source", "purpose",
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
    doesn't exist or is locked.
    """
    tx = get_transaction_by_id(db, transaction_id)
    if not tx or tx.is_locked:
        return None

    old_timestamp = tx.timestamp
    type_changed = _drop_fields_of_old_type(tx, tx_data)
    _check_edit(tx, tx_data, type_changed, db)
    _revalue_btc_fee(tx, tx_data, db)
    _apply_edit(tx, tx_data, type_changed)
    tx.updated_at = datetime.now(timezone.utc)
    db.flush()

    # One full recalculation handles every edit, a backdated one included:
    # replaying only from the new date left the earlier lots short of the
    # BTC the old version of the transaction had used.
    logger.debug(
        f"[Update] Tx {tx.id} timestamp {old_timestamp} => {tx.timestamp}. "
        f"Running scorched earth re-lot."
    )
    recalculate_all_transactions(db)

    db.commit()
    db.refresh(tx)
    return tx


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
    _validate_transaction(merged, db, check_source=check_source)
    if _fill_fee_currency(merged, db):  # e.g. a fee_amount sent on its own
        tx_data["fee_currency"] = merged["fee_currency"]
    for key in ("type", "purpose", "source", "timestamp"):  # canonical spellings, whole seconds
        if merged.get(key) != getattr(tx, key) or key in tx_data:
            tx_data[key] = merged.get(key)
    if any(k in tx_data for k in ("type", "from_account_id", "to_account_id")):
        _enforce_transaction_type_rules(merged, db)
    if any(k in tx_data for k in ("fee_amount", "fee_currency", "type", "amount", "from_account_id")):
        _enforce_fee_rules(merged, db)
    _revalue_income_deposit(tx, tx_data, db)


def _revalue_income_deposit(tx: Transaction, tx_data: dict, db: Session) -> None:
    """An edit that leaves an income deposit without a basis (the form sends
    0 for a blank one) values it, as on create."""
    if not any(k in tx_data for k in ("cost_basis_usd", "source", "type")):
        return
    edited = {
        k: tx_data.get(k, getattr(tx, k))
        for k in ("type", "source", "to_account_id", "amount", "timestamp", "cost_basis_usd")
    }
    if _value_income_deposit(edited, db):
        tx_data["cost_basis_usd"] = edited["cost_basis_usd"]


def _revalue_btc_fee(tx: Transaction, tx_data: dict, db: Session) -> None:
    """A BTC fee's USD value: a typed one is kept; otherwise it is priced
    again when the fee or the date changes (fee_usd sent as null clears a
    typed one)."""
    if "fee_usd" not in tx_data and (tx.fee_usd_manual or not _fee_inputs_changed(tx, tx_data)):
        return
    fee = {k: tx_data.get(k, getattr(tx, k)) for k in ("type", "fee_amount", "fee_currency", "timestamp")}
    fee["fee_usd"] = tx_data["fee_usd"] if "fee_usd" in tx_data else (
        tx.fee_usd if tx.fee_usd_manual else None)
    _value_btc_fee(fee, db, manual=fee["fee_usd"] is not None)
    tx.fee_usd, tx.fee_usd_manual = fee["fee_usd"], fee["fee_usd_manual"]


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
    for key in ("cost_basis_usd", "proceeds_usd", "fmv_usd"):
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
    Delete a transaction if not locked.
    Removes ledger entries, partial-lot usage, and re-lots everything.
    Committed only if the ledger still recalculates without it: deleting a
    buy that a later sell or transfer spends is refused and changes nothing.
    """
    tx = get_transaction_by_id(db, transaction_id)
    if not tx or tx.is_locked:
        return False

    db.delete(tx)
    db.flush()
    try:
        recalculate_all_transactions(db)
    except HTTPException as e:
        db.rollback()
        why = "later transactions depend on this one. " if e.status_code == 400 else ""
        raise HTTPException(status_code=e.status_code, detail=f"Not deleted: {why}{e.detail}")
    except Exception:
        db.rollback()
        raise
    db.commit()
    return True


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


# Types whose proceeds are derived (net of fees) from the user's gross input
GROSS_PROCEEDS_TYPES = ("Sell", "Withdrawal")


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
        the day's price, fetched once.
      - Rows saved before the gross was recorded: their proceeds_usd is net of
        the BTC fee offset versions before 0.9.2 applied; undo it once. The
        gross is what was received for the amount spent (the fee is its own
        disposal now).
    """
    if tx.gross_proceeds_usd is not None:
        return Decimal(tx.gross_proceeds_usd)

    purpose = (tx.purpose or "").lower()
    amount = Decimal(tx.amount or 0)
    if purpose != "spent":
        # Gift/Donation/Lost have no proceeds. Their stored proceeds_usd is the
        # network fee's (its own disposal), never a gross to recover.
        return Decimal("0")
    if tx.proceeds_usd is None:
        gross = (_price_for(tx, "it has no Proceeds (USD) value", db) * amount).quantize(Decimal("0.01"))
    else:
        gross = Decimal(tx.proceeds_usd)
        has_btc_fee = (tx.fee_currency or "").upper() == "BTC" and Decimal(tx.fee_amount or 0) > 0
        if purpose == "spent" and has_btc_fee and gross > 0 and amount > 0:
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
    to_acct = db.get(Account, tx.to_account_id)
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
        acquired_date=tx.timestamp,
        total_btc=btc_amount,
        remaining_btc=btc_amount,
        cost_basis_usd=cost_basis,
    )
    db.add(new_lot)
    db.flush()


def maybe_dispose_lots_fifo(tx: Transaction, tx_data: dict, db: Session):
    """
    For a Sell/Withdrawal from a BTC account, do FIFO disposal of partial lots.
    - The proceeds are for the amount sold or spent: a Sell's net proceeds,
      a Spent withdrawal's full proceeds (no fee cut).
    - Gift/Donation/Lost => the amount carries no proceeds and no gain.
    - A withdrawal's BTC network fee is its own disposal (like a transfer's),
      at the fee's stored USD value, taxable whatever the purpose. It uses the
      oldest BTC first, then the amount follows.
    """
    from_acct = db.get(Account, tx.from_account_id)
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
    not_a_sale = tx.type == "Withdrawal" and (tx.purpose or "").lower() in ("gift", "donation", "lost")
    if not_a_sale:
        total_proceeds = Decimal("0")
    fee_usd = _stored_fee_usd(tx, fee_btc, db) if (tx.type == "Withdrawal" and fee_btc > 0) else Decimal("0")

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
            detail=f"Not enough BTC to {tx.type.lower()} {btc_outflow:.8f} BTC"
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


def _open_lots(account_id: int, db: Session) -> list[BitcoinLot]:
    """The account's lots with BTC left, oldest first."""
    return (
        db.query(BitcoinLot)
        .join(Transaction, Transaction.id == BitcoinLot.created_txn_id)
        .filter(
            BitcoinLot.remaining_btc > 0,
            Transaction.to_account_id == account_id
        )
        .order_by(BitcoinLot.acquired_date.asc())
        .all()
    )


class _FifoDisposal:
    """
    A Sell's or Withdrawal's BTC taken from lots, oldest first: the network
    fee's part before the amount's, each with its share of the proceeds.
    The last part of each takes what is left, so the parts add up exactly
    to fee_usd and to the proceeds.
    """

    def __init__(self, tx: Transaction, amount_btc: Decimal, total_proceeds: Decimal, not_a_sale: bool,
                 fee_btc: Decimal, fee_usd: Decimal, db: Session):
        self.tx, self.db = tx, db
        self.amount_btc, self.total_proceeds, self.not_a_sale = amount_btc, total_proceeds, not_a_sale
        self.fee_btc, self.fee_usd = fee_btc, fee_usd
        self.remaining_amount = amount_btc
        self.remaining_fee = fee_btc
        self.proceeds_so_far = Decimal("0")
        self.fee_proceeds_so_far = Decimal("0")
        self.tz = get_tax_timezone(db)

    def take_from(self, lot: BitcoinLot) -> None:
        if self.remaining_fee > 0 and lot.remaining_btc > 0:
            qty = min(lot.remaining_btc, self.remaining_fee)
            if qty == self.remaining_fee:
                proceeds = self.fee_usd - self.fee_proceeds_so_far
            else:
                proceeds = (self.fee_usd * qty / self.fee_btc).quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)
            self.fee_proceeds_so_far += proceeds
            self.record(lot, qty, proceeds, gain_zero=False, is_fee=True)
            self.remaining_fee -= qty
        if self.remaining_amount > 0 and lot.remaining_btc > 0:
            qty = min(lot.remaining_btc, self.remaining_amount)
            if qty == self.remaining_amount:
                proceeds = self.total_proceeds - self.proceeds_so_far
            else:
                proceeds = (qty / self.amount_btc * self.total_proceeds).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_DOWN)
            self.proceeds_so_far += proceeds
            self.record(lot, qty, proceeds, gain_zero=self.not_a_sale, is_fee=False)
            self.remaining_amount -= qty

    def record(self, lot: BitcoinLot, qty: Decimal, proceeds: Decimal, gain_zero: bool, is_fee: bool) -> None:
        cost_per_btc = lot.cost_basis_usd / lot.total_btc if lot.total_btc else Decimal("0")
        basis = (cost_per_btc * qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)
        self.db.add(LotDisposal(
            lot_id=lot.id,
            transaction_id=self.tx.id,
            disposed_btc=qty,
            disposal_basis_usd=basis,
            proceeds_usd_for_that_portion=proceeds,
            realized_gain_usd=Decimal("0.0") if gain_zero else proceeds - basis,
            holding_period=holding_period(lot.acquired_date, self.tx.timestamp, self.tz),
            is_fee=is_fee,
        ))
        lot.remaining_btc -= qty


def compute_sell_summary_from_disposals(tx: Transaction, db: Session):
    """
    Summarize partial-lot disposals (Sell/Withdrawal). Overwrite
    tx.cost_basis_usd, tx.proceeds_usd, tx.realized_gain_usd, holding_period
    based on the earliest acquisition date among those partial-lot disposals.
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
    earliest_date = None

    for disp in disposals:
        total_basis += (disp.disposal_basis_usd or Decimal("0"))
        total_gain += (disp.realized_gain_usd or Decimal("0"))
        total_proceeds += (disp.proceeds_usd_for_that_portion or Decimal("0"))

        lot = disp.lot  # Eager loaded, no additional query
        if lot and (earliest_date is None or lot.acquired_date < earliest_date):
            earliest_date = lot.acquired_date

    tx.cost_basis_usd = total_basis
    tx.realized_gain_usd = total_gain

    if tx.type == "Withdrawal" and (tx.purpose or "").lower() in ("gift", "donation", "lost"):
        # No proceeds for the amount (its fee's are tx.fee_usd): a Spent
        # edited into a Gift kept its old proceeds, printed with the gifts.
        tx.proceeds_usd = None
    elif total_proceeds > 0:
        tx.proceeds_usd = total_proceeds

    if earliest_date:
        tx.holding_period = holding_period(earliest_date, tx.timestamp, get_tax_timezone(db))
    else:
        tx.holding_period = None

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
    def utc(ts):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)

    if "type" in tx_data and getattr(tx_data["type"], "value", tx_data["type"]) != tx.type:
        return True
    if "fee_currency" in tx_data and (tx_data["fee_currency"] or "").upper() != (tx.fee_currency or "").upper():
        return True
    if "fee_amount" in tx_data and Decimal(tx_data["fee_amount"] or 0) != Decimal(tx.fee_amount or 0):
        return True
    if "timestamp" in tx_data and tx_data["timestamp"] is not None and tx.timestamp is not None:
        return utc(tx_data["timestamp"]).astimezone(timezone.utc).date() != \
            utc(tx.timestamp).astimezone(timezone.utc).date()
    return False


def _value_btc_fee(data: dict, db: Session, manual: bool) -> None:
    """
    Set data["fee_usd"] / data["fee_usd_manual"]: the USD value of a
    transfer's or withdrawal's BTC fee, stored with the transaction so
    recalculation never prices it again. A typed value (manual) is kept;
    otherwise fee x that day's price. No BTC fee: no value.
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
        price = get_btc_price(ts, db)
    except HTTPException as e:
        raise HTTPException(
            status_code=422,
            detail=f"{e.detail} For the network fee, type its USD value in Fee value (USD) (fee_usd in an import).",
        )
    data["fee_usd"] = (price * Decimal(data["fee_amount"])).quantize(Decimal("0.01"))
    data["fee_usd_manual"] = False


def _stored_fee_usd(tx: Transaction, fee_btc: Decimal, db: Session) -> Decimal:
    """
    The fee's stored USD value. A row saved before values were stored (and
    not filled by migration 0004) is priced once from the price history and
    the value kept, so later recalculations don't price it again.
    """
    if tx.fee_usd is None:
        price = _price_for(tx, "its network fee has no USD value", db)
        tx.fee_usd = (price * fee_btc).quantize(Decimal("0.01"))
        tx.fee_usd_manual = False
    return Decimal(tx.fee_usd)


def _price_for(tx: Transaction, missing: str, db: Session) -> Decimal:
    """The day's price for a stored transaction's missing value; without one,
    a 422 naming the transaction (a report fails on it, and the day alone
    doesn't say which entry to fix)."""
    try:
        return get_btc_price(tx.timestamp, db)
    except HTTPException as e:
        day = tx.timestamp.date().isoformat() if tx.timestamp else "an unknown day"
        amount = format(Decimal(tx.amount or 0).normalize(), "f")
        raise HTTPException(
            status_code=e.status_code,
            detail=f"{tx.type} of {amount} BTC on {day}: {missing} (enter it in that transaction). {e.detail}",
        ) from e


def get_historical_btc_price(timestamp: datetime, db: Session) -> Decimal:
    """
    The day's BTC price in USD for the timestamp's UTC date, from the local
    price history (services/price_history.py). Never today's live price.
    Raises 422 when no price is available.
    """
    return price_history.daily_price(db, timestamp)


def _value_income_deposit(tx_data: dict, db: Session) -> bool:
    """
    An income deposit (source Income, Interest or Reward into a BTC account)
    has a cost basis equal to its market value at receipt, which is also the
    income on the tax report. Entered without one (blank, or the form's 0),
    value it at the day's BTC price instead of saving $0; refuse to save when
    no price is available. Returns True when it filled cost_basis_usd.
    """
    if tx_data.get("type") != "Deposit":
        return False
    if (tx_data.get("source") or "").lower() not in INCOME_SOURCES:
        return False
    if Decimal(tx_data.get("cost_basis_usd") or 0) > 0:
        return False
    to_acct = db.get(Account, tx_data.get("to_account_id")) if tx_data.get("to_account_id") else None
    amount = Decimal(tx_data.get("amount") or 0)
    if not to_acct or to_acct.currency != "BTC" or amount <= 0:
        return False

    timestamp = tx_data.get("timestamp") or datetime.now(timezone.utc)
    try:
        price = get_historical_btc_price(timestamp, db)
    except HTTPException as e:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{e.detail} Enter this {tx_data['source']} deposit's USD value "
                "at receipt as its cost basis."
            ),
        )
    tx_data["cost_basis_usd"] = (price * amount).quantize(Decimal("0.01"))
    return True


def get_btc_price(timestamp: datetime, db: Session) -> Decimal:
    """
    The BTC price in USD for the timestamp's UTC day, from the local price
    history. It used to fall back to the live price when the day's lookup
    failed, which valued past fees and spends at today's price; now a
    missing price is a 422 (services/price_history.py).
    """
    return price_history.daily_price(db, timestamp)


def maybe_transfer_bitcoin_lot(tx: Transaction, tx_data: dict, db: Session):
    """
    Splits source lots for an internal BTC transfer from one BTC account to another,
    disposing the fee portion and carrying forward the remainder as a new partial-lot.
    """
    from_acct = db.get(Account, tx.from_account_id)
    to_acct = db.get(Account, tx.to_account_id)
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

    move = _LotMove(tx, btc_outflow, fee_btc, db)
    for lot in _open_lots(tx.from_account_id, db):
        if move.remaining_outflow <= 0:
            break
        if lot.remaining_btc <= 0:
            continue
        move.take_from(lot)

    if move.remaining_fee > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough BTC to cover fee {fee_btc}"
        )
    if move.remaining_outflow > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough BTC to transfer {btc_outflow} (including fee {fee_btc})"
        )
    move.add_destination_lots()
    db.flush()


class _LotMove:
    """
    A BTC transfer's amount (fee included) taken from the source's lots,
    oldest first. The fee's part is disposed of at the fee's stored USD
    value (split by BTC when it spans lots; the last part takes the
    remainder so the parts add up to fee_usd exactly). The rest becomes
    lots in the destination, each keeping its source lot's acquisition date
    and share of basis.
    """

    def __init__(self, tx: Transaction, btc_outflow: Decimal, fee_btc: Decimal, db: Session):
        self.tx, self.fee_btc, self.db = tx, fee_btc, db
        self.remaining_outflow = btc_outflow
        self.remaining_fee = fee_btc
        self.fee_proceeds_so_far = Decimal("0")
        self.to_destination: list[tuple[Decimal, Decimal, datetime]] = []

    def take_from(self, lot: BitcoinLot) -> None:
        btc_to_use = min(lot.remaining_btc, self.remaining_outflow)
        cost_per_btc = (
            lot.cost_basis_usd / lot.total_btc if lot.total_btc > 0 else Decimal("0")
        )
        lot.remaining_btc -= btc_to_use
        self.db.add(lot)
        self.remaining_outflow -= btc_to_use

        portion_for_fee = min(btc_to_use, self.remaining_fee)
        portion_for_dest = btc_to_use - portion_for_fee
        if portion_for_fee > 0:
            self.dispose_fee(lot, portion_for_fee, cost_per_btc)
        if portion_for_dest > 0:
            self.to_destination.append((portion_for_dest, cost_per_btc, lot.acquired_date))

    def dispose_fee(self, lot: BitcoinLot, portion: Decimal, cost_per_btc: Decimal) -> None:
        disposal_basis = (cost_per_btc * portion).quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)
        fee_usd = _stored_fee_usd(self.tx, self.fee_btc, self.db)
        if portion == self.remaining_fee:
            proceeds_for_fee = fee_usd - self.fee_proceeds_so_far
        else:
            proceeds_for_fee = (fee_usd * portion / self.fee_btc).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_DOWN)
        self.fee_proceeds_so_far += proceeds_for_fee
        self.db.add(LotDisposal(
            lot_id=lot.id,
            transaction_id=self.tx.id,
            disposed_btc=portion,
            disposal_basis_usd=disposal_basis,
            proceeds_usd_for_that_portion=proceeds_for_fee,
            realized_gain_usd=proceeds_for_fee - disposal_basis,
            holding_period=holding_period(lot.acquired_date, self.tx.timestamp, get_tax_timezone(self.db)),
            is_fee=True,
        ))
        self.remaining_fee -= portion

    def add_destination_lots(self) -> None:
        for amt_btc, cost_per_btc, acquired_date in self.to_destination:
            if acquired_date.tzinfo is None:
                acquired_date = acquired_date.replace(tzinfo=timezone.utc)
            cost_portion = (cost_per_btc * amt_btc).quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)
            self.db.add(BitcoinLot(
                created_txn_id=self.tx.id,
                acquired_date=acquired_date,
                total_btc=amt_btc,
                remaining_btc=amt_btc,
                cost_basis_usd=cost_portion
            ))


def recalculate_all_transactions(db: Session, until: datetime | None = None):
    """
    "Scorched Earth": remove all ledger lines, partial-lot disposals,
    and BitcoinLots. Then re-lot everything in chronological order.

    With `until`, only transactions strictly before it are replayed — a
    snapshot of lots/balances as of that instant (used for year-end
    balances). Callers must run a full recalculation afterwards.
    """
    db.query(LedgerEntry).delete()
    db.query(LotDisposal).delete()
    db.query(BitcoinLot).delete()
    db.flush()

    query = db.query(Transaction)
    if until is not None:
        query = query.filter(Transaction.timestamp < until)
    all_txs = query.order_by(Transaction.timestamp.asc(), Transaction.id.asc()).all()
    for rec_tx in all_txs:
        _fill_stored_fee_currency(rec_tx, db)
        stored = _stored_inputs(rec_tx)
        build_ledger_entries_for_transaction(rec_tx, stored, db)
        _maybe_verify_balance_for_internal(rec_tx, db)
        _post_lots(rec_tx, stored, db)

    db.flush()


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
DEPOSIT_SOURCES = ("MyBTC", "Gift", "Income", "Interest", "Reward", "N/A")
GENESIS = datetime(2009, 1, 3, tzinfo=timezone.utc)
MAX_TEXT = 64
MAX_BTC = Decimal("21000000")
DEPOSIT_BASIS_REQUIRED = "Enter this deposit's cost basis (0 if it's unknown)."
DEPOSIT_SOURCE_UNKNOWN = "A deposit's source must be one of: " + ", ".join(DEPOSIT_SOURCES) + "."


def _canonical(value, choices) -> str | None:
    """The listed spelling of a case-insensitive match, else None."""
    if value is None:
        return None
    lowered = str(value).strip().lower()
    return next((c for c in choices if c.lower() == lowered), None)


def _bad(detail: str):
    raise HTTPException(status_code=422, detail=detail)


def _validate_transaction(data: dict, db: Session, check_source: bool = True) -> None:
    """
    Reject input the ledger would record wrongly, with a clear message; set
    canonical spellings in `data`. Used on create, and on update with the
    stored row merged with the change, so a partial edit is checked as a
    whole transaction. check_source=False keeps a deposit's stored source
    unchecked (an edit that doesn't change it). The checks run in a fixed
    order, and the first that fails is the message.
    """
    tx_type = _checked_type(data)
    _check_timestamp(data)
    from_acct, to_acct = _checked_accounts(data, db)
    _check_amount(data, tx_type, from_acct, to_acct)
    fee = Decimal(data.get("fee_amount") or 0)
    _check_not_negative(data, fee)
    _check_fee_currency(data, tx_type, fee, from_acct, to_acct)
    if tx_type == "Sell":
        _check_sell_proceeds(data, fee)
    _set_canonical_spellings(data)
    _check_type_requirements(data, tx_type, check_source, from_acct, to_acct)


def _checked_type(data: dict) -> str:
    tx_type = data.get("type")
    tx_type = getattr(tx_type, "value", tx_type)
    if tx_type not in TX_TYPES:
        _bad(f"Unknown transaction type: {tx_type}.")
    data["type"] = tx_type
    return tx_type


def _check_timestamp(data: dict) -> None:
    ts = data.get("timestamp")
    if ts is None:
        _bad("A date and time is required.")
    ts_utc = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    if ts_utc < GENESIS:
        _bad("The date is before Bitcoin existed (3 January 2009).")
    if ts_utc > datetime.now(timezone.utc) + timedelta(days=1):
        _bad("The date is in the future.")
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


def _check_amount(data: dict, tx_type: str, from_acct: Account | None, to_acct: Account | None) -> None:
    amount = data.get("amount")
    if amount is None or Decimal(amount) <= 0:
        _bad("The amount must be more than 0.")
    amount = Decimal(amount)
    # The account the amount is counted in: the sender, or for a deposit the receiver.
    main_acct = to_acct if tx_type in ("Deposit", "Buy") else from_acct
    if main_acct is not None and main_acct.currency == "USD" and tx_type != "Buy":
        if -amount.normalize().as_tuple().exponent > 2:
            _bad("A USD amount can have at most 2 decimal places.")
    if main_acct is not None and main_acct.currency == "BTC" and amount > MAX_BTC:
        _bad("A BTC amount can't be more than 21,000,000.")


def _check_not_negative(data: dict, fee: Decimal) -> None:
    if fee < 0:
        _bad("The fee can't be negative.")
    for key in ("cost_basis_usd", "proceeds_usd", "gross_proceeds_usd", "fmv_usd", "fee_usd"):
        if data.get(key) is not None and Decimal(data[key]) < 0:
            _bad(f"{key} can't be negative.")


def _check_fee_currency(data: dict, tx_type: str, fee: Decimal, from_acct: Account | None,
                        to_acct: Account | None) -> None:
    """A withdrawal's fee is in the currency of the account it leaves, a
    deposit's in that of the account it reaches."""
    fee_cur = (data.get("fee_currency") or "").upper()
    if fee > 0 and tx_type in ("Withdrawal", "Deposit"):
        acct = from_acct if tx_type == "Withdrawal" else to_acct
        if acct is not None and fee_cur and fee_cur != acct.currency:
            _bad(f"A {tx_type.lower()} fee must be in {acct.currency}, the account's currency.")


def _check_sell_proceeds(data: dict, fee: Decimal) -> None:
    gross = data.get("gross_proceeds_usd")
    if gross is None:
        gross = data.get("proceeds_usd")
    if gross is None:
        _bad("A sell needs its proceeds (gross_proceeds_usd).")
    if fee > Decimal(gross):
        _bad("The sell's fee is more than its proceeds.")


def _set_canonical_spellings(data: dict) -> None:
    """A purpose or source in the listed spelling ("gift" is Gift); either
    one too long is refused."""
    for key, choices in (("purpose", WITHDRAWAL_PURPOSES), ("source", DEPOSIT_SOURCES)):
        value = data.get(key)
        if value is not None and len(str(value)) > MAX_TEXT:
            _bad(f"{key} is too long (at most {MAX_TEXT} characters).")
        canonical = _canonical(value, choices)
        if canonical:
            data[key] = canonical


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

    # A BTC deposit that isn't income (MyBTC, Gift, N/A...) needs its cost
    # basis stated: a blank one would make its whole value gain when it's
    # sold. Income is valued at the day's price instead (_value_income_deposit).
    if tx_type == "Deposit" and to_acct is not None and to_acct.currency == "BTC" \
            and (data.get("source") or "").lower() not in INCOME_SOURCES and data.get("cost_basis_usd") is None:
        _bad(DEPOSIT_BASIS_REQUIRED)


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
    tx_type = data.get("type")
    if tx_type in ("Buy", "Sell"):
        data["fee_currency"] = "USD"
        return True
    acct_id = data.get("to_account_id") if tx_type == "Deposit" else data.get("from_account_id")
    acct = db.get(Account, acct_id) if acct_id else None
    if acct is None:
        return False
    data["fee_currency"] = acct.currency
    return True


def _fill_stored_fee_currency(tx: Transaction, db: Session) -> None:
    """The same for a row saved without it (before the fill above)."""
    data = {k: getattr(tx, k) for k in ("type", "fee_amount", "fee_currency", "from_account_id", "to_account_id")}
    if _fill_fee_currency(data, db):
        tx.fee_currency = data["fee_currency"]


def _enforce_fee_rules(tx_data: dict, db: Session):
    """
    Validate fee usage by transaction type:
      - Transfer => fee must match from_acct currency
      - Buy/Sell => fee must be USD
      - Deposit/Withdrawal => no special fee rule
    """
    tx_type = tx_data.get("type")
    from_id = tx_data.get("from_account_id")
    fee_amt = Decimal(tx_data.get("fee_amount") or 0)
    fee_cur = (tx_data.get("fee_currency") or "").upper()  # filled by _fill_fee_currency

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
        if from_acct and from_acct.currency == "BTC" and amount is not None and fee_amt > Decimal(amount):
            raise HTTPException(
                status_code=400,
                detail="Transfer fee exceeds the amount sent (amount includes the fee)."
            )
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
        (lambda f, t: f == t, "Transfer => from and to must be different accounts."),
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
    them in the same currency, a Buy from Bank or Exchange USD to Exchange
    BTC, a Sell from Exchange BTC to Exchange USD.
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
