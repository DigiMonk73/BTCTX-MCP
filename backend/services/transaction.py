"""
backend/services/transaction.py

Core logic for BitcoinTX with a hybrid double-entry system:
 - Single-entry inputs (type, amount, from_account, to_account, etc.)
 - Multi-line LedgerEntry creation for same-currency double-entry
 - Cross-currency Buy/Sell skip net-zero checks for simpler personal ledgers
 - BTC FIFO logic for sells/withdrawals
 - Transfer logic that handles partial-lot fee disposal

Implementation Notes:
 - "Scorched Earth": after editing or deleting a transaction, we remove
   all ledger entries and re-lot everything in strict chronological order.
   This is acceptable for a single-user system with a relatively small dataset.
 - If we backdate (change the timestamp to earlier), we run a partial re-lot
   from that timestamp forward, then also do the "scorched earth" re-lot to
   ensure consistency.

"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_DOWN, InvalidOperation
from collections import defaultdict
from typing import Optional

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


# ------------------------------------------------------------------------------
# Public Functions (CRUD + retrieval)
# ------------------------------------------------------------------------------
def get_all_transactions(db: Session):
    """
    Return all Transactions, typically ordered descending by timestamp.
    """
    return (
        db.query(Transaction)
        .order_by(Transaction.timestamp.desc())
        .all()
    )


def get_transaction_by_id(db: Session, transaction_id: int):
    """
    Retrieve a single Transaction by its ID (returns None if not found).
    """
    return db.query(Transaction).filter(Transaction.id == transaction_id).first()


def create_transaction_record(tx_data: dict, db: Session, auto_commit: bool = True) -> Transaction:
    """
    Creates a new Transaction in the hybrid multi-line ledger system.

    Steps:
      1) Ensure "BTC Fees" account exists.
      2) Validate transaction type usage.
      3) Validate fee usage for transaction type.
      4) Create Transaction row in DB.
      5) Convert single-entry fields => multiple ledger lines.
      6) Possibly skip net-zero check if cross-currency (Buy/Sell).
      7) If Deposit/Buy => create BTC lot if to_acct=BTC
      8) If Withdrawal/Sell => do FIFO disposal if from_acct=BTC
      9) If disposal => compute realized gains summary

    Args:
        tx_data: Transaction data dictionary
        db: Database session
        auto_commit: If True (default), commits after creating. Set to False for bulk operations.
    """
    # 1) Ensure BTC Fees account
    ensure_fee_account_exists(db)

    # 2 & 3) Validate the input, the transaction type and fee rules
    _validate_transaction(tx_data, db)
    _enforce_transaction_type_rules(tx_data, db)
    _enforce_fee_rules(tx_data, db)
    _enforce_broker_reporting(tx_data.get("type"), tx_data.get("broker_reporting"))
    _record_gross_proceeds(tx_data)
    _value_income_deposit(tx_data, db)
    _value_btc_fee(tx_data, db, manual=tx_data.get("fee_usd") is not None)

    # 4) Insert Transaction
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
        # If the front end sends gross_proceeds_usd
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

    # 5) Build ledger lines
    remove_ledger_entries_for_tx(new_tx, db)
    build_ledger_entries_for_transaction(new_tx, tx_data, db)

    # 6) Possibly skip net-zero if cross-currency
    _maybe_verify_balance_for_internal(new_tx, db)

    # 7-9) Partial-lot logic
    if new_tx.type in ("Deposit", "Buy"):
        maybe_create_bitcoin_lot(new_tx, tx_data, db)
    elif new_tx.type in ("Withdrawal", "Sell"):
        maybe_dispose_lots_fifo(new_tx, tx_data, db)
        compute_sell_summary_from_disposals(new_tx, db)
    elif new_tx.type == "Transfer":
        from_acct = db.get(Account, new_tx.from_account_id)
        # If from_acct is BTC, ensure fee_amount/currency are set
        if from_acct and from_acct.currency == "BTC":
            if new_tx.fee_amount is None or new_tx.fee_amount <= 0:
                logger.warning(f"Transfer {new_tx.id} missing fee_amount; defaulting to 0")
                new_tx.fee_amount = Decimal("0")
            if not new_tx.fee_currency:
                new_tx.fee_currency = "BTC"
        maybe_transfer_bitcoin_lot(new_tx, tx_data, db)

    # If disposal => finalize realized gain summary
    if new_tx.type in ("Sell", "Withdrawal"):
        compute_sell_summary_from_disposals(new_tx, db)

    # Check if this is a backdated transaction (timestamp earlier than existing transactions)
    # If so, we need to recalculate to ensure FIFO ordering is correct
    latest_other_tx = (
        db.query(Transaction)
        .filter(Transaction.id != new_tx.id)
        .order_by(Transaction.timestamp.desc())
        .first()
    )
    if latest_other_tx and new_tx.timestamp < latest_other_tx.timestamp:
        logger.info(
            f"[Backdated Create] New tx {new_tx.id} at {new_tx.timestamp} is earlier than "
            f"existing tx {latest_other_tx.id} at {latest_other_tx.timestamp}. Triggering recalculation."
        )
        recalculate_all_transactions(db)

    if auto_commit:
        db.commit()
        db.refresh(new_tx)
    return new_tx


_VALIDATED_FIELDS = (
    "type", "timestamp", "from_account_id", "to_account_id", "amount", "fee_amount", "fee_currency",
    "cost_basis_usd", "proceeds_usd", "gross_proceeds_usd", "fmv_usd", "source", "purpose",
)


def update_transaction_record(transaction_id: int, tx_data: dict, db: Session):
    """
    Update an existing Transaction if not locked.

    Steps:
      1) If locked => return None
      2) Re-validate usage & fee rules if relevant fields changed
      3) Overwrite transaction fields
      4) Rebuild ledger lines & partial-lot usage
      5) Possibly do partial-lot re-lot if backdated
      6) Finally do "scorched earth" re-lot of everything
    """
    tx = get_transaction_by_id(db, transaction_id)
    if not tx or tx.is_locked:
        return None

    old_timestamp = tx.timestamp

    # Step 2) Validate the transaction as it will be after the change (a
    # partial edit was checked on the fields sent only, which failed with
    # "Unknown transaction type: None" or let a mismatch through).
    merged = {k: getattr(tx, k) for k in _VALIDATED_FIELDS}
    merged.update({k: v for k, v in tx_data.items() if k in _VALIDATED_FIELDS})
    _validate_transaction(merged, db)
    for key in ("type", "purpose", "source"):  # canonical spellings
        if merged.get(key) != getattr(tx, key) or key in tx_data:
            tx_data[key] = merged.get(key)
    if any(k in tx_data for k in ("type", "from_account_id", "to_account_id")):
        _enforce_transaction_type_rules(merged, db)
    if any(k in tx_data for k in ("fee_amount", "fee_currency", "type", "amount", "from_account_id")):
        _enforce_fee_rules(merged, db)
    # An edit that leaves an income deposit without a basis (the form sends
    # 0 for a blank one) values it, as on create.
    if any(k in tx_data for k in ("cost_basis_usd", "source", "type")):
        merged = {
            k: tx_data.get(k, getattr(tx, k))
            for k in ("type", "source", "to_account_id", "amount", "timestamp", "cost_basis_usd")
        }
        if _value_income_deposit(merged, db):
            tx_data["cost_basis_usd"] = merged["cost_basis_usd"]

    # A BTC fee's USD value: a typed one is kept; otherwise it is priced again
    # when the fee or the date changes (fee_usd sent as null clears a typed one).
    if "fee_usd" in tx_data or (not tx.fee_usd_manual and _fee_inputs_changed(tx, tx_data)):
        fee = {k: tx_data.get(k, getattr(tx, k)) for k in ("type", "fee_amount", "fee_currency", "timestamp")}
        fee["fee_usd"] = tx_data["fee_usd"] if "fee_usd" in tx_data else (
            tx.fee_usd if tx.fee_usd_manual else None)
        _value_btc_fee(fee, db, manual=fee["fee_usd"] is not None)
        tx.fee_usd, tx.fee_usd_manual = fee["fee_usd"], fee["fee_usd_manual"]

    # Step 3) Overwrite relevant fields
    if "from_account_id" in tx_data:
        tx.from_account_id = tx_data["from_account_id"]
    if "to_account_id" in tx_data:
        tx.to_account_id = tx_data["to_account_id"]
    if "amount" in tx_data:
        tx.amount = tx_data["amount"]
    if "fee_amount" in tx_data:
        tx.fee_amount = tx_data["fee_amount"]
    if "fee_currency" in tx_data:
        tx.fee_currency = tx_data["fee_currency"]
    if "type" in tx_data:
        tx.type = tx_data["type"]
    if "timestamp" in tx_data:
        tx.timestamp = tx_data["timestamp"]
    if "source" in tx_data:
        tx.source = tx_data["source"]
    if "purpose" in tx_data:
        tx.purpose = tx_data["purpose"]
    if "broker_reporting" in tx_data:
        _enforce_broker_reporting(tx_data.get("type", tx.type), tx_data["broker_reporting"])
        tx.broker_reporting = tx_data["broker_reporting"]
    elif tx.type not in BROKER_REPORTING_TYPES:
        tx.broker_reporting = None  # type changed away from Sell/Withdrawal
    if "cost_basis_usd" in tx_data:
        tx.cost_basis_usd = tx_data["cost_basis_usd"]
    if "proceeds_usd" in tx_data:
        tx.proceeds_usd = tx_data["proceeds_usd"]
    if "fmv_usd" in tx_data:
        tx.fmv_usd = tx_data["fmv_usd"]
    # Partial update of gross_proceeds_usd
    if "gross_proceeds_usd" in tx_data:
        tx.gross_proceeds_usd = tx_data["gross_proceeds_usd"]
    elif "proceeds_usd" in tx_data and tx.type in GROSS_PROCEEDS_TYPES:
        # A proceeds edit is user input, i.e. the new gross
        tx.gross_proceeds_usd = tx_data["proceeds_usd"]

    tx.updated_at = datetime.now(timezone.utc)

    # Flush the transaction field changes first
    db.flush()

    # Do a single "Scorched Earth" re-lot to rebuild everything correctly.
    # This handles all cases (backdating, forward-dating, same timestamp) uniformly.
    # The partial recalculate_subsequent_transactions was causing issues when
    # lots from before the new timestamp still had reduced remaining_btc from
    # the original transaction's consumption.
    new_timestamp = tx.timestamp
    logger.info(
        f"[Update] Tx {tx.id} timestamp {old_timestamp} => {new_timestamp}. "
        f"Running scorched earth re-lot."
    )
    recalculate_all_transactions(db)

    db.commit()
    db.refresh(tx)
    return tx


def delete_transaction_record(transaction_id: int, db: Session):
    """
    Delete a transaction if not locked.
    Removes ledger entries, partial-lot usage, and re-lots everything.
    """
    tx = get_transaction_by_id(db, transaction_id)
    if not tx or tx.is_locked:
        return False

    db.delete(tx)
    db.commit()

    recalculate_all_transactions(db)
    return True


# ------------------------------------------------------------------------------
# Internal Helpers
# ------------------------------------------------------------------------------
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
        gross = (get_btc_price(tx.timestamp, db) * amount).quantize(Decimal("0.01"))
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


def remove_lot_usage_for_tx(tx: Transaction, db: Session):
    """
    Remove partial-lot disposals & newly created lots for the transaction.

    Note: This function is currently unused - update_transaction_record and
    delete_transaction_record both use scorched earth (recalculate_all_transactions)
    instead. Kept for potential future use.
    """
    for disp in list(tx.lot_disposals):
        db.delete(disp)
    for lot in list(tx.bitcoin_lots_created):
        db.delete(lot)
    db.flush()


def build_ledger_entries_for_transaction(tx: Transaction, tx_data: dict, db: Session):
    """
    Convert single-entry data => multi-line ledger.
    Handles cross-currency Buy/Sell logic, Transfer fees, etc.

    CHANGES FOR GROSS_PROCEEDS_USD:
    For Sells, we now read 'gross_proceeds_usd' and subtract fees
    to produce a net 'proceeds_usd' value. That net is stored in
    the DB (used by partial-lot disposal and aggregator). Meanwhile,
    the original user-typed gross remains in 'gross_proceeds_usd'.
    """
    from_acct_id = tx_data.get("from_account_id")
    to_acct_id = tx_data.get("to_account_id")
    tx_type = tx_data.get("type", "")
    amount = Decimal(tx_data.get("amount") or 0)
    fee_amount = Decimal(tx_data.get("fee_amount") or "0.0")
    fee_currency = (tx_data.get("fee_currency") or "BTC").upper()

    # If user provided None or empty proceeds_usd, treat it as "0"
    proceeds_raw = tx_data.get("proceeds_usd") or "0"
    proceeds_usd = Decimal(proceeds_raw)

    from_acct = db.get(Account, from_acct_id) if from_acct_id else None
    to_acct = db.get(Account, to_acct_id) if to_acct_id else None

    # -------------------------------------------------------------------------
    # 1) Transfer with BTC fee
    # -------------------------------------------------------------------------
    if (
        tx_type == "Transfer"
        and from_acct
        and from_acct.currency == "BTC"
        and fee_amount > 0
    ):
        # Debit from_acct
        db.add(LedgerEntry(
            transaction_id=tx.id,
            account_id=from_acct.id,
            amount=-amount,
            currency=from_acct.currency,
            entry_type="MAIN_OUT"
        ))
        # Credit to_acct minus fee
        if to_acct and amount > 0:
            net_in = amount - fee_amount
            db.add(LedgerEntry(
                transaction_id=tx.id,
                account_id=to_acct.id,
                amount=net_in if net_in > 0 else Decimal("0"),
                currency=to_acct.currency,
                entry_type="MAIN_IN"
            ))
        fee_acct = db.query(Account).filter_by(name="BTC Fees").first()
        if fee_acct:
            db.add(LedgerEntry(
                transaction_id=tx.id,
                account_id=fee_acct.id,
                amount=fee_amount,
                currency="BTC",
                entry_type="FEE"
            ))
        db.flush()
        return

    # -------------------------------------------------------------------------
    # 2) Sell => from BTC => to USD
    # -------------------------------------------------------------------------
    if (
        tx_type == "Sell"
        and from_acct and from_acct.currency == "BTC"
        and to_acct and to_acct.currency == "USD"
    ):
        # Subtract BTC out of from_acct
        if amount > 0:
            db.add(LedgerEntry(
                transaction_id=tx.id,
                account_id=from_acct.id,
                amount=-amount,
                currency="BTC",
                entry_type="MAIN_OUT"
            ))

        # Check if user typed 'gross_proceeds_usd'; if present, derive net from that.
        gross_raw = tx_data.get("gross_proceeds_usd") or "0"
        gross_usd = Decimal(gross_raw)

        if gross_usd > 0:
            # If fee is in USD, net = (gross - fee)
            if fee_currency == "USD":
                net_usd_in = gross_usd - fee_amount
                if net_usd_in < 0:
                    net_usd_in = Decimal("0")
            else:
                # If fee is BTC, we do not reduce the gross USD
                net_usd_in = gross_usd

            # Overwrite proceeds_usd so aggregator & partial-lot disposal see net
            tx_data["proceeds_usd"] = str(net_usd_in)
            tx.proceeds_usd = net_usd_in
            # Also store the user's typed gross in DB
            tx.gross_proceeds_usd = gross_usd
        else:
            # No gross recorded. create_transaction_record always records it,
            # so only rows saved before that reach here, and their stored
            # proceeds_usd is ALREADY net of the USD fee. Keep it as the net
            # and recover the gross once; re-subtracting the fee here is what
            # used to shrink proceeds on every recalculation.
            net_usd_in = proceeds_usd if proceeds_usd > 0 else Decimal("0")
            if net_usd_in > 0:
                tx.gross_proceeds_usd = (
                    net_usd_in + fee_amount if fee_currency == "USD" else net_usd_in
                )
            tx_data["proceeds_usd"] = str(net_usd_in)
            tx.proceeds_usd = net_usd_in

        # Credit net to the to_acct
        if net_usd_in > 0:
            db.add(LedgerEntry(
                transaction_id=tx.id,
                account_id=to_acct.id,
                amount=net_usd_in,
                currency="USD",
                entry_type="MAIN_IN"
            ))
        # Fee line if fee is USD
        if fee_amount > 0 and fee_currency == "USD":
            fee_acct = db.query(Account).filter_by(name="USD Fees").first()
            if fee_acct:
                db.add(LedgerEntry(
                    transaction_id=tx.id,
                    account_id=fee_acct.id,
                    amount=fee_amount,
                    currency="USD",
                    entry_type="FEE"
                ))

        db.flush()
        return

    # -------------------------------------------------------------------------
    # 3) Buy => from USD => to BTC
    # -------------------------------------------------------------------------
    if (
        tx_type == "Buy"
        and from_acct and from_acct.currency == "USD"
        and to_acct and to_acct.currency == "BTC"
    ):
        amount_btc = Decimal(tx_data.get("amount") or 0)
        fee_amt = Decimal(tx_data.get("fee_amount") or 0)
        cost_basis_usd = Decimal(tx_data.get("cost_basis_usd") or 0)

        total_usd_out = cost_basis_usd + fee_amt
        db.add(LedgerEntry(
            transaction_id=tx.id,
            account_id=from_acct.id,
            amount=-total_usd_out,
            currency="USD",
            entry_type="MAIN_OUT"
        ))
        if amount_btc > 0:
            db.add(LedgerEntry(
                transaction_id=tx.id,
                account_id=to_acct.id,
                amount=amount_btc,
                currency="BTC",
                entry_type="MAIN_IN"
            ))
        if fee_amt > 0 and fee_currency == "USD":
            fee_acct = db.query(Account).filter_by(name="USD Fees").first()
            if fee_acct:
                db.add(LedgerEntry(
                    transaction_id=tx.id,
                    account_id=fee_acct.id,
                    amount=fee_amt,
                    currency="USD",
                    entry_type="FEE"
                ))
        db.flush()
        return

    # -------------------------------------------------------------------------
    # 4) Fallback: Deposits, Withdrawals, or other
    # -------------------------------------------------------------------------
    if from_acct and amount > 0:
        main_out_amt = -(amount + fee_amount)
        db.add(LedgerEntry(
            transaction_id=tx.id,
            account_id=from_acct.id,
            amount=main_out_amt,
            currency=from_acct.currency,
            entry_type="MAIN_OUT"
        ))
    if to_acct and amount > 0:
        db.add(LedgerEntry(
            transaction_id=tx.id,
            account_id=to_acct.id,
            amount=amount,
            currency=to_acct.currency,
            entry_type="MAIN_IN"
        ))
    if fee_amount > 0:
        # Fee to either BTC Fees or USD Fees
        if fee_currency == "BTC":
            fee_acct = db.query(Account).filter_by(name="BTC Fees").first()
        else:
            fee_acct = db.query(Account).filter_by(name="USD Fees").first()
        if fee_acct:
            db.add(LedgerEntry(
                transaction_id=tx.id,
                account_id=fee_acct.id,
                amount=fee_amount,
                currency=fee_currency,
                entry_type="FEE"
            ))
    db.flush()


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

    # 1) Proceeds for the amount. Use tx.proceeds_usd as the authoritative
    # value for a Sell (build_ledger_entries_for_transaction derived it from
    # gross_proceeds_usd). Withdrawals have no ledger-side net step, so they
    # start from the gross.
    if tx.type == "Withdrawal":
        total_proceeds = _withdrawal_gross_proceeds(tx, btc_outflow, db)
    elif tx.proceeds_usd is not None:
        total_proceeds = Decimal(tx.proceeds_usd)
    else:
        raw_proceeds = tx_data.get("proceeds_usd")
        if raw_proceeds is None:
            total_proceeds = Decimal("0")
        else:
            try:
                total_proceeds = Decimal(str(raw_proceeds))
            except (ValueError, TypeError, InvalidOperation):
                total_proceeds = Decimal("0")

    # 2) Gift/Donation/Lost => no gain or loss on the amount: not a sale, and
    # not on Form 8949 (form_8949.NON_TAXABLE_PURPOSES). Lost used to carry a
    # loss of its basis, which the dashboard and the tax report's summary
    # counted although the forms leave it out (owner decision 2026-09-26).
    purpose_lower = (tx.purpose or "").lower()
    not_a_sale = tx.type == "Withdrawal" and purpose_lower in ("gift", "donation", "lost")
    if not_a_sale:
        total_proceeds = Decimal("0")
    fee_usd = _stored_fee_usd(tx, fee_btc, db) if (tx.type == "Withdrawal" and fee_btc > 0) else Decimal("0")

    # 3) FIFO disposal across lots (account-specific)
    # Only consume lots from the account we're selling/withdrawing from
    lots = (
        db.query(BitcoinLot)
        .join(Transaction, Transaction.id == BitcoinLot.created_txn_id)
        .filter(
            BitcoinLot.remaining_btc > 0,
            Transaction.to_account_id == tx.from_account_id
        )
        .order_by(BitcoinLot.acquired_date.asc())
        .all()
    )
    tz = get_tax_timezone(db)
    remaining_fee = fee_btc
    remaining_amount = amount_btc
    fee_proceeds_so_far = Decimal("0")

    def dispose(lot, qty, proceeds, gain_zero, is_fee):
        cost_per_btc = lot.cost_basis_usd / lot.total_btc if lot.total_btc else Decimal("0")
        basis = (cost_per_btc * qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)
        db.add(LotDisposal(
            lot_id=lot.id,
            transaction_id=tx.id,
            disposed_btc=qty,
            disposal_basis_usd=basis,
            proceeds_usd_for_that_portion=proceeds,
            realized_gain_usd=Decimal("0.0") if gain_zero else proceeds - basis,
            holding_period=holding_period(lot.acquired_date, tx.timestamp, tz),
            is_fee=is_fee,
        ))
        lot.remaining_btc -= qty

    for lot in lots:
        if remaining_fee <= 0 and remaining_amount <= 0:
            break
        if remaining_fee > 0 and lot.remaining_btc > 0:
            qty = min(lot.remaining_btc, remaining_fee)
            if qty == remaining_fee:  # last part takes the remainder: the parts add up to fee_usd
                proceeds = fee_usd - fee_proceeds_so_far
            else:
                proceeds = (fee_usd * qty / fee_btc).quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)
            fee_proceeds_so_far += proceeds
            dispose(lot, qty, proceeds, gain_zero=False, is_fee=True)
            remaining_fee -= qty
        if remaining_amount > 0 and lot.remaining_btc > 0:
            qty = min(lot.remaining_btc, remaining_amount)
            proceeds = (qty / amount_btc * total_proceeds).quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)
            dispose(lot, qty, proceeds, gain_zero=not_a_sale, is_fee=False)
            remaining_amount -= qty

    # Validate that we had enough BTC to complete the disposal
    if remaining_fee + remaining_amount > Decimal("0.00000001"):  # 1 satoshi tolerance for rounding
        raise HTTPException(
            status_code=400,
            detail=f"Not enough BTC to {tx.type.lower()} {btc_outflow:.8f} BTC"
        )

    db.flush()


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

    if total_proceeds > 0:
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
            detail=f"{e.detail} (for the network fee: enter its value in USD as fee_usd)",
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
        tx.fee_usd = (get_btc_price(tx.timestamp, db) * fee_btc).quantize(Decimal("0.01"))
        tx.fee_usd_manual = False
    return Decimal(tx.fee_usd)


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
    total_outflow = btc_outflow
    if total_outflow <= 0:
        return

    # Gather lots from 'from_acct' in FIFO
    lots = (
        db.query(BitcoinLot)
        .join(Transaction, Transaction.id == BitcoinLot.created_txn_id)
        .filter(
            BitcoinLot.remaining_btc > 0,
            Transaction.to_account_id == tx.from_account_id
        )
        .order_by(BitcoinLot.acquired_date.asc())
        .all()
    )

    remaining_outflow = total_outflow
    remaining_fee = fee_btc
    fee_proceeds_so_far = Decimal("0")
    transfers_for_destination = []

    for lot in lots:
        if remaining_outflow <= 0:
            break
        if lot.remaining_btc <= 0:
            continue

        btc_to_use = min(lot.remaining_btc, remaining_outflow)
        cost_per_btc = (
            lot.cost_basis_usd / lot.total_btc if lot.total_btc > 0 else Decimal("0")
        )
        cost_portion = (cost_per_btc * btc_to_use).quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)

        lot.remaining_btc -= btc_to_use
        db.add(lot)
        remaining_outflow -= btc_to_use

        portion_for_fee = min(btc_to_use, remaining_fee)
        portion_for_dest = btc_to_use - portion_for_fee

        # Fee disposal, at the fee's stored USD value (split by BTC when the
        # fee spans lots; the last part takes the remainder so the parts add
        # up to fee_usd exactly).
        if portion_for_fee > 0:
            disposal_basis = (cost_per_btc * portion_for_fee).quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)
            fee_usd = _stored_fee_usd(tx, fee_btc, db)
            if portion_for_fee == remaining_fee:
                proceeds_for_fee = fee_usd - fee_proceeds_so_far
            else:
                proceeds_for_fee = (fee_usd * portion_for_fee / fee_btc).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_DOWN)
            fee_proceeds_so_far += proceeds_for_fee
            realized_gain = proceeds_for_fee - disposal_basis

            hp = holding_period(lot.acquired_date, tx.timestamp, get_tax_timezone(db))

            disp = LotDisposal(
                lot_id=lot.id,
                transaction_id=tx.id,
                disposed_btc=portion_for_fee,
                disposal_basis_usd=disposal_basis,
                proceeds_usd_for_that_portion=proceeds_for_fee,
                realized_gain_usd=realized_gain,
                holding_period=hp,
                is_fee=True,
            )
            db.add(disp)
            remaining_fee -= portion_for_fee

        # Destination partial-lot
        if portion_for_dest > 0:
            transfers_for_destination.append((lot, portion_for_dest, cost_per_btc, lot.acquired_date))

    if remaining_fee > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough BTC to cover fee {fee_btc}"
        )
    if remaining_outflow > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough BTC to transfer {btc_outflow} (including fee {fee_btc})"
        )

    # Create partial-lot(s) in the destination
    for (orig_lot, amt_btc, cost_per_btc, acquired_date) in transfers_for_destination:
        if acquired_date.tzinfo is None:
            acquired_date = acquired_date.replace(tzinfo=timezone.utc)
        cost_portion = (cost_per_btc * amt_btc).quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)
        new_lot = BitcoinLot(
            created_txn_id=tx.id,
            acquired_date=acquired_date,
            total_btc=amt_btc,
            remaining_btc=amt_btc,
            cost_basis_usd=cost_portion
        )
        db.add(new_lot)

    db.flush()


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
        sub_tx_data = {
            "from_account_id": rec_tx.from_account_id,
            "to_account_id": rec_tx.to_account_id,
            "type": rec_tx.type,
            "amount": rec_tx.amount,
            "fee_amount": rec_tx.fee_amount,
            "fee_currency": rec_tx.fee_currency,
            "cost_basis_usd": rec_tx.cost_basis_usd,
            "proceeds_usd": rec_tx.proceeds_usd,
            "timestamp": rec_tx.timestamp,
            "source": rec_tx.source,
            "purpose": rec_tx.purpose,
            "gross_proceeds_usd": rec_tx.gross_proceeds_usd,
            "fmv_usd": rec_tx.fmv_usd,
        }
        build_ledger_entries_for_transaction(rec_tx, sub_tx_data, db)
        _maybe_verify_balance_for_internal(rec_tx, db)

        if rec_tx.type in ("Deposit", "Buy"):
            maybe_create_bitcoin_lot(rec_tx, sub_tx_data, db)
        elif rec_tx.type in ("Sell", "Withdrawal"):
            maybe_dispose_lots_fifo(rec_tx, sub_tx_data, db)
            compute_sell_summary_from_disposals(rec_tx, db)
        elif rec_tx.type == "Transfer":
            maybe_transfer_bitcoin_lot(rec_tx, sub_tx_data, db)

    db.flush()


def recalculate_subsequent_transactions(db: Session, from_timestamp: datetime):
    """
    Partial-lot re-lot for transactions >= from_timestamp, more efficient
    than "scorched earth" for large datasets.
    """
    logger.info(f"[Partial Re-Lot] Starting from {from_timestamp.isoformat()}")

    affected_txs = (
        db.query(Transaction)
        .filter(Transaction.timestamp >= from_timestamp)
        .order_by(Transaction.timestamp.asc(), Transaction.id.asc())
        .all()
    )
    tx_ids = [t.id for t in affected_txs]

    db.query(LedgerEntry).filter(LedgerEntry.transaction_id.in_(tx_ids)).delete(synchronize_session=False)
    db.query(LotDisposal).filter(LotDisposal.transaction_id.in_(tx_ids)).delete(synchronize_session=False)
    db.query(BitcoinLot).filter(BitcoinLot.created_txn_id.in_(tx_ids)).delete(synchronize_session=False)
    db.flush()

    for rec_tx in affected_txs:
        sub_tx_data = {
            "from_account_id": rec_tx.from_account_id,
            "to_account_id": rec_tx.to_account_id,
            "type": rec_tx.type,
            "amount": rec_tx.amount,
            "fee_amount": rec_tx.fee_amount,
            "fee_currency": rec_tx.fee_currency,
            "cost_basis_usd": rec_tx.cost_basis_usd,
            "proceeds_usd": rec_tx.proceeds_usd,
            "timestamp": rec_tx.timestamp,
            "source": rec_tx.source,
            "purpose": rec_tx.purpose,
            # If present, re-inject gross_proceeds_usd
            "gross_proceeds_usd": rec_tx.gross_proceeds_usd,
            "fmv_usd": rec_tx.fmv_usd,
        }
        build_ledger_entries_for_transaction(rec_tx, sub_tx_data, db)
        _maybe_verify_balance_for_internal(rec_tx, db)

        if rec_tx.type in ("Deposit", "Buy"):
            maybe_create_bitcoin_lot(rec_tx, sub_tx_data, db)
        elif rec_tx.type in ("Sell", "Withdrawal"):
            maybe_dispose_lots_fifo(rec_tx, sub_tx_data, db)
            compute_sell_summary_from_disposals(rec_tx, db)
        elif rec_tx.type == "Transfer":
            maybe_transfer_bitcoin_lot(rec_tx, sub_tx_data, db)

    db.flush()
    logger.info("[Partial Re-Lot] Completed partial-lot recalculation.")


# --------------------------------------------------------------------------------
# Double-Entry (with Cross-Currency Skip) & Fee Rules
# --------------------------------------------------------------------------------
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


# ------------------------------------------------------------------------------
# Input validation (create, and the merged row on update)
# ------------------------------------------------------------------------------
USER_ACCOUNTS = {ACCOUNT_BANK, ACCOUNT_WALLET, ACCOUNT_EXCHANGE_USD, ACCOUNT_EXCHANGE_BTC, ACCOUNT_EXTERNAL}
TX_TYPES = ("Deposit", "Withdrawal", "Transfer", "Buy", "Sell")
WITHDRAWAL_PURPOSES = ("Spent", "Gift", "Donation", "Lost")
DEPOSIT_SOURCES = ("MyBTC", "Gift", "Income", "Interest", "Reward", "N/A")
GENESIS = datetime(2009, 1, 3, tzinfo=timezone.utc)
MAX_TEXT = 64
MAX_BTC = Decimal("21000000")
DEPOSIT_BASIS_REQUIRED = "Enter this deposit's cost basis (0 if it's unknown)."


def _canonical(value, choices) -> Optional[str]:
    """The listed spelling of a case-insensitive match, else None."""
    if value is None:
        return None
    lowered = str(value).strip().lower()
    return next((c for c in choices if c.lower() == lowered), None)


def _bad(detail: str):
    raise HTTPException(status_code=422, detail=detail)


def _validate_transaction(data: dict, db: Session) -> None:
    """
    Reject input the ledger would record wrongly, with a clear message; set
    canonical spellings in `data`. Used on create, and on update with the
    stored row merged with the change, so a partial edit is checked as a
    whole transaction.
    """
    tx_type = data.get("type")
    tx_type = getattr(tx_type, "value", tx_type)
    if tx_type not in TX_TYPES:
        _bad(f"Unknown transaction type: {tx_type}.")
    data["type"] = tx_type

    ts = data.get("timestamp")
    if ts is None:
        _bad("A date and time is required.")
    ts_utc = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    if ts_utc < GENESIS:
        _bad("The date is before Bitcoin existed (3 January 2009).")
    if ts_utc > datetime.now(timezone.utc) + timedelta(days=1):
        _bad("The date is in the future.")

    for key in ("from_account_id", "to_account_id"):
        acct_id = data.get(key)
        if acct_id is not None and acct_id not in USER_ACCOUNTS:
            _bad(f"Unknown account id {acct_id}.")
    from_acct = db.get(Account, data["from_account_id"]) if data.get("from_account_id") else None
    to_acct = db.get(Account, data["to_account_id"]) if data.get("to_account_id") else None

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

    fee = Decimal(data.get("fee_amount") or 0)
    if fee < 0:
        _bad("The fee can't be negative.")
    for key in ("cost_basis_usd", "proceeds_usd", "gross_proceeds_usd", "fmv_usd", "fee_usd"):
        if data.get(key) is not None and Decimal(data[key]) < 0:
            _bad(f"{key} can't be negative.")

    fee_cur = (data.get("fee_currency") or "").upper()
    if fee > 0 and tx_type in ("Withdrawal", "Deposit"):
        acct = from_acct if tx_type == "Withdrawal" else to_acct
        if acct is not None and fee_cur and fee_cur != acct.currency:
            _bad(f"A {tx_type.lower()} fee must be in {acct.currency}, the account's currency.")

    if tx_type == "Sell":
        gross = data.get("gross_proceeds_usd")
        if gross is None:
            gross = data.get("proceeds_usd")
        if gross is None:
            _bad("A sell needs its proceeds (gross_proceeds_usd).")
        if fee > Decimal(gross):
            _bad("The sell's fee is more than its proceeds.")

    for key, choices in (("purpose", WITHDRAWAL_PURPOSES), ("source", DEPOSIT_SOURCES)):
        value = data.get(key)
        if value is not None and len(str(value)) > MAX_TEXT:
            _bad(f"{key} is too long (at most {MAX_TEXT} characters).")
        canonical = _canonical(value, choices)
        if canonical:
            data[key] = canonical

    if tx_type == "Withdrawal" and from_acct is not None and from_acct.currency == "BTC":
        if data.get("purpose") not in WITHDRAWAL_PURPOSES:
            _bad("A BTC withdrawal needs a purpose: Spent, Gift, Donation or Lost.")

    # F15: a BTC deposit that isn't income (MyBTC, Gift, N/A...) needs its
    # cost basis stated; blank used to mean $0, all gain when it's sold.
    # Income is valued at the day's price instead (_value_income_deposit).
    if tx_type == "Deposit" and to_acct is not None and to_acct.currency == "BTC" \
            and (data.get("source") or "").lower() not in INCOME_SOURCES and data.get("cost_basis_usd") is None:
        _bad(DEPOSIT_BASIS_REQUIRED)


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
    fee_cur = (tx_data.get("fee_currency") or "USD").upper()

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


def _enforce_transaction_type_rules(tx_data: dict, db: Session):
    """
    Enforce correct usage of from/to for each transaction type:
      - Deposit => from=External => to=any internal account (BTC or USD)
      - Withdrawal => from=any internal account => to=External
      - Transfer => from/to internal & same currency
      - Buy => from=Exchange USD => to=Exchange BTC
      - Sell => from=Exchange BTC => to=Exchange USD
      - Otherwise => error
    """
    tx_type = tx_data.get("type")
    from_id = tx_data.get("from_account_id")
    to_id = tx_data.get("to_account_id")

    if tx_type == "Deposit":
        if from_id != ACCOUNT_EXTERNAL:
            raise HTTPException(400, "Deposit => from must be External.")
        if not to_id or to_id == ACCOUNT_EXTERNAL:
            raise HTTPException(400, "Deposit => to must be an internal account.")

    elif tx_type == "Withdrawal":
        if not from_id or from_id == ACCOUNT_EXTERNAL:
            raise HTTPException(400, "Withdrawal => from must be an internal account.")
        if to_id != ACCOUNT_EXTERNAL:
            raise HTTPException(400, "Withdrawal => to must be External.")

    elif tx_type == "Transfer":
        if not from_id or from_id == ACCOUNT_EXTERNAL or not to_id or to_id == ACCOUNT_EXTERNAL:
            raise HTTPException(400, "Transfer => both from/to must be internal.")
        if from_id == to_id:
            raise HTTPException(400, "Transfer => from and to must be different accounts.")
        db_from = db.get(Account, from_id)
        db_to = db.get(Account, to_id)
        if db_from and db_to and db_from.currency != db_to.currency:
            raise HTTPException(400, "Transfer => same currency required.")

    elif tx_type == "Buy":
        if from_id not in (ACCOUNT_BANK, ACCOUNT_EXCHANGE_USD):
            raise HTTPException(400, "Buy => from must be Bank or Exchange USD.")
        if to_id != ACCOUNT_EXCHANGE_BTC:
            raise HTTPException(400, "Buy => to must be Exchange BTC.")

    elif tx_type == "Sell":
        if from_id != ACCOUNT_EXCHANGE_BTC:
            raise HTTPException(400, "Sell => from must be Exchange BTC.")
        if to_id != ACCOUNT_EXCHANGE_USD:
            raise HTTPException(400, "Sell => to must be Exchange USD.")

    else:
        raise HTTPException(400, f"Unknown transaction type: {tx_type}")


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
