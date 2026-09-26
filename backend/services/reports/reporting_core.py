# FILE: backend/services/reports/reporting_core.py

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Any, Iterator, List
from decimal import Decimal, ROUND_HALF_DOWN
import logging
import sqlite3

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# Models
from backend.models.transaction import (
    Transaction,
    BitcoinLot,
    LotDisposal,
)
from backend.services.tax_time import get_tax_timezone, get_tax_timezone_name, tax_year_bounds
from backend.services.reports.form_8949 import taxable_disposals

# Services
from backend.services.transaction import (
    recalculate_all_transactions,
    get_btc_price,                        # for fetching historical BTC price
)

logger = logging.getLogger(__name__)


@contextmanager
def _scratch_copy(db: Session) -> Iterator[Session]:
    """
    A throwaway in-memory copy of the database. Start/end-of-year snapshots
    replay the ledger only up to a date; doing that on a copy means building
    a report never rewrites (or even locks) the real ledger.
    """
    memory = sqlite3.connect(":memory:", check_same_thread=False)
    raw = db.get_bind().raw_connection()
    try:
        raw.driver_connection.backup(memory)
    finally:
        raw.close()
    engine = create_engine("sqlite://", creator=lambda: memory, poolclass=StaticPool)
    scratch = Session(bind=engine)
    try:
        yield scratch
    finally:
        scratch.close()
        engine.dispose()
        memory.close()


def generate_report_data(db: Session, year: int) -> Dict[str, Any]:
    """
    Generates a comprehensive dictionary of data for the specified tax year (YYYY).
    This data can be passed to PDF generators or any other reporting interface.

    Pipeline:
      1) Start- and end-of-year holdings: replay the ledger up to each year
         boundary on a throwaway copy of the database (_scratch_copy).
      2) Everything else reads the live ledger, which every write already
         keeps fully recalculated. Building a report changes nothing.
    """
    logger.info(f"Begin building report data for tax_year={year}")

    # ---------------------------------------------------------
    # 1) Gather beginning-of-year balances (snapshot)
    # ---------------------------------------------------------
    start_dt, end_dt = tax_year_bounds(year, get_tax_timezone(db))
    with _scratch_copy(db) as scratch:
        start_of_year_data = _build_start_of_year_balances(scratch, year)

    # ---------------------------------------------------------
    # 1b) End-of-year snapshot: replay only transactions before the
    #     year boundary, so later activity doesn't leak into 12/31 holdings
    # ---------------------------------------------------------
    with _scratch_copy(db) as scratch:
        recalculate_all_transactions(scratch, until=end_dt)
        eoy_list = _build_end_of_year_balances(scratch, year)

    # ---------------------------------------------------------
    # 3) Filter transactions within that tax year
    # ---------------------------------------------------------

    txns = (
        db.query(Transaction)
        .filter(Transaction.timestamp >= start_dt, Transaction.timestamp < end_dt)
        .order_by(Transaction.timestamp.asc(), Transaction.id.asc())
        .all()
    )

    # ---------------------------------------------------------
    # 4) Build each needed section
    # ---------------------------------------------------------
    disposals         = taxable_disposals(db, start_dt, end_dt)
    gains_dict        = _build_capital_gains_summary(disposals)
    income_dict       = _build_income_summary(txns)
    asset_list        = _build_asset_summary(db, start_dt, end_dt)
    cap_gain_txs_sum  = _build_capital_gains_transactions_summary(disposals)
    cap_gain_txs_det  = _build_capital_gains_transactions_detailed(disposals)
    income_txs        = _build_income_transactions(txns)
    gifts_lost        = _build_gifts_donations_lost(txns)
    expense_list      = _build_expenses_list(txns)
    data_sources_list = _gather_data_sources(txns)

    # ---------------------------------------------------------
    # 5) Construct final dictionary
    # ---------------------------------------------------------
    result = {
        "tax_year": year,
        "tax_timezone": get_tax_timezone_name(db)[0],
        "report_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "period": f"{year}-01-01 to {year}-12-31",

        "start_of_year_balances": start_of_year_data,
        "capital_gains_summary": gains_dict,
        "income_summary": income_dict,
        "asset_summary": asset_list,
        "end_of_year_balances": eoy_list,

        # Summaries of disposal transactions
        "capital_gains_transactions": cap_gain_txs_sum,
        "capital_gains_transactions_detailed": cap_gain_txs_det,

        "income_transactions": income_txs,
        "gifts_donations_lost": gifts_lost,
        "expenses": expense_list,
        "data_sources": data_sources_list,
    }
    return result


def _build_start_of_year_balances(db: Session, year: int) -> List[Dict[str, Any]]:
    """
    Build a list of leftover BTC lots as of just before Jan 1 of `year`.

    Steps:
      1) Run `_partial_relot_strictly_after(...)`, removing usage only for
         transactions strictly after Jan 1.
      2) Recreate any old "Buy" or "Deposit" lots (if they were previously deleted
         by a prior scorched-earth), so the leftover from prior years is restored.
      3) Query the leftover open lots (acquired before Jan 1).
      4) Fetch the BTC price for Jan 1 using `get_btc_price(...)` and value them.

    We'll revert to normal for the rest of the year by calling
    `recalculate_all_transactions(...)` after this function.
    """
    logger.info(f"Calculating start-of-year balances for {year}")

    # 1) Remove usage for any transaction with timestamp strictly after Jan 1
    from_dt, _ = tax_year_bounds(year, get_tax_timezone(db))
    _partial_relot_strictly_after(db, from_dt)

    # 2) Recreate any "Buy"/"Deposit" lots from prior to Jan 1 if a previous year’s
    #    scorched-earth had deleted them. Otherwise, they'd never get re-lotted here.
    _restore_buy_deposit_lots_before(db, from_dt)

    # 3) Now query leftover BTC that was actually acquired before Jan 1
    open_lots = (
        db.query(BitcoinLot)
        .filter(
            BitcoinLot.remaining_btc > 0,
            BitcoinLot.acquired_date < from_dt
        )
        .all()
    )

    # 4) Fetch historical BTC price for Jan 1
    january1_price = get_btc_price(from_dt, db)

    results = []
    for lot in open_lots:
        # fraction leftover in the partial-lot
        fraction = Decimal("1.0")
        if lot.total_btc and lot.total_btc > 0:
            fraction = lot.remaining_btc / lot.total_btc

        # cost basis leftover for that fraction
        partial_cost = (lot.cost_basis_usd * fraction).quantize(Decimal("0.01"), ROUND_HALF_DOWN)

        if lot.remaining_btc > 0:
            avg_basis = partial_cost / lot.remaining_btc
        else:
            avg_basis = Decimal("0.0")

        # market value as of Jan 1
        cur_value = (lot.remaining_btc * january1_price).quantize(Decimal("0.01"), ROUND_HALF_DOWN)

        results.append({
            "quantity": float(lot.remaining_btc),
            "avg_cost_basis": float(avg_basis),
            "value": float(cur_value),
        })

    logger.info(f"Found {len(results)} leftover BTC lots as of start-of-year {year}")
    return results


def _partial_relot_strictly_after(db: Session, boundary_dt: datetime):
    """
    Helper function to remove ledger usage & lots ONLY for transactions
    whose timestamp is strictly > boundary_dt. We then rebuild just those
    transactions so they don't affect the leftover snapshot at boundary_dt.

    If you prefer to include boundary_dt as part of the old year,
    replace '>' with '>=' below.
    """
    logger.info(f"[Strict Partial Re-Lot] Excluding transactions after {boundary_dt.isoformat()}")

    from backend.models.transaction import LedgerEntry, BitcoinLot
    from backend.services.transaction import (
        build_ledger_entries_for_transaction,
        maybe_create_bitcoin_lot,
        maybe_dispose_lots_fifo,
        compute_sell_summary_from_disposals,
        maybe_transfer_bitcoin_lot,
        _maybe_verify_balance_for_internal,
    )

    # 1) Find all transactions strictly after boundary_dt
    affected_txs = (
        db.query(Transaction)
        .filter(Transaction.timestamp > boundary_dt)
        .order_by(Transaction.timestamp.asc(), Transaction.id.asc())
        .all()
    )
    if not affected_txs:
        logger.info("[Strict Partial Re-Lot] No transactions found after boundary_dt.")
        return

    # 2) Delete ledger entries, disposals, and newly created lots for these TXs
    tx_ids = [tx.id for tx in affected_txs]
    db.query(LedgerEntry).filter(LedgerEntry.transaction_id.in_(tx_ids)).delete(synchronize_session=False)

    # Before deleting disposals, restore remaining_btc to the source lots
    # This ensures pre-boundary lots have correct balances for rebuilding
    disposals_to_restore = (
        db.query(LotDisposal)
        .filter(LotDisposal.transaction_id.in_(tx_ids))
        .all()
    )
    for disp in disposals_to_restore:
        if disp.lot and disp.disposed_btc:
            disp.lot.remaining_btc += disp.disposed_btc
            db.add(disp.lot)
    db.flush()

    # For Transfer transactions, the destination lots need to be deleted
    # and their amounts restored to source lots. Track what needs restoring.
    transfer_lots_to_restore = (
        db.query(BitcoinLot)
        .join(Transaction, Transaction.id == BitcoinLot.created_txn_id)
        .filter(
            BitcoinLot.created_txn_id.in_(tx_ids),
            Transaction.type == "Transfer"
        )
        .all()
    )

    # Find the source lots for each transfer and restore their remaining_btc
    for dest_lot in transfer_lots_to_restore:
        transfer_tx = dest_lot.created_transaction
        if not transfer_tx:
            continue
        # The transfer moved BTC from from_account to to_account
        # Find pre-boundary lots in the source account (from_account)
        # and restore the transferred amount to them (LIFO to undo FIFO consumption)
        amount_to_restore = dest_lot.total_btc + (transfer_tx.fee_amount or Decimal("0"))
        source_lots = (
            db.query(BitcoinLot)
            .join(Transaction, Transaction.id == BitcoinLot.created_txn_id)
            .filter(
                Transaction.to_account_id == transfer_tx.from_account_id,
                Transaction.timestamp <= boundary_dt,
                BitcoinLot.created_txn_id.notin_(tx_ids)  # Pre-boundary lots only
            )
            .order_by(BitcoinLot.acquired_date.desc())  # LIFO to undo FIFO
            .all()
        )
        for src_lot in source_lots:
            if amount_to_restore <= 0:
                break
            # Restore up to the lot's original total
            can_restore = src_lot.total_btc - src_lot.remaining_btc
            restore_amt = min(can_restore, amount_to_restore)
            if restore_amt > 0:
                src_lot.remaining_btc += restore_amt
                db.add(src_lot)
                amount_to_restore -= restore_amt
    db.flush()

    db.query(LotDisposal).filter(LotDisposal.transaction_id.in_(tx_ids)).delete(synchronize_session=False)
    db.query(BitcoinLot).filter(BitcoinLot.created_txn_id.in_(tx_ids)).delete(synchronize_session=False)
    db.flush()

    # 3) Rebuild each of those transactions from scratch in chronological order
    for rec_tx in affected_txs:
        # Reconstruct single-entry data
        sub_tx_data = {
            "from_account_id": rec_tx.from_account_id,
            "to_account_id":   rec_tx.to_account_id,
            "type":            rec_tx.type,
            "amount":          rec_tx.amount,
            "fee_amount":      rec_tx.fee_amount,
            "fee_currency":    rec_tx.fee_currency,
            "cost_basis_usd":  rec_tx.cost_basis_usd,
            "proceeds_usd":    rec_tx.proceeds_usd,
            "timestamp":       rec_tx.timestamp,
            "source":          rec_tx.source,
            "purpose":         rec_tx.purpose,
        }

        # Rebuild ledger lines
        build_ledger_entries_for_transaction(rec_tx, sub_tx_data, db)
        _maybe_verify_balance_for_internal(rec_tx, db)

        # Partial-lot logic
        if rec_tx.type in ("Deposit", "Buy"):
            maybe_create_bitcoin_lot(rec_tx, sub_tx_data, db)
        elif rec_tx.type in ("Sell", "Withdrawal"):
            maybe_dispose_lots_fifo(rec_tx, sub_tx_data, db)
            compute_sell_summary_from_disposals(rec_tx, db)
        elif rec_tx.type == "Transfer":
            maybe_transfer_bitcoin_lot(rec_tx, sub_tx_data, db)

    db.flush()
    logger.info("[Strict Partial Re-Lot] Completed re-lot for TXs after boundary_dt.")


def _restore_buy_deposit_lots_before(db: Session, boundary_dt: datetime):
    """
    After removing usage for TXs after 'boundary_dt', older "Buy" or "Deposit"
    transactions might still have their lots missing if they'd been deleted by
    a previous scorched-earth run. This function re-creates those lots if needed,
    so your partial-lot snapshot for 'boundary_dt' is correct.

    Only re-lots for "Buy"/"Deposit" with timestamp <= boundary_dt.
    We skip sells, withdrawals, etc. because we only need the leftover acquisitions.
    """
    logger.info(f"[Restore Pre-Boundary Lots] Checking for buys/deposits <= {boundary_dt.isoformat()}")

    from backend.services.transaction import maybe_create_bitcoin_lot

    # 1) Find all Buys or Deposits on or before 'boundary_dt'
    pre_lot_txs = (
        db.query(Transaction)
        .filter(
            Transaction.timestamp <= boundary_dt,
            Transaction.type.in_(["Buy", "Deposit"])
        )
        .order_by(Transaction.timestamp.asc(), Transaction.id.asc())
        .all()
    )

    if not pre_lot_txs:
        logger.info("[Restore Pre-Boundary Lots] No pre-boundary buys/deposits found.")
        return

    # 2) For each, re-run maybe_create_bitcoin_lot
    #    This won't duplicate an existing lot if there's already one in place,
    #    but if the lot was deleted, it will be re-created.
    count_restored = 0
    for rec_tx in pre_lot_txs:
        # Build a minimal sub_tx_data for the lot function
        sub_tx_data = {
            "from_account_id": rec_tx.from_account_id,
            "to_account_id":   rec_tx.to_account_id,
            "type":            rec_tx.type,
            "amount":          rec_tx.amount,
            "fee_amount":      rec_tx.fee_amount,
            "fee_currency":    rec_tx.fee_currency,
            "cost_basis_usd":  rec_tx.cost_basis_usd,
            "proceeds_usd":    rec_tx.proceeds_usd,
            "timestamp":       rec_tx.timestamp,
            "source":          rec_tx.source,
            "purpose":         rec_tx.purpose,
        }

        existing_lots = rec_tx.bitcoin_lots_created
        lot_count_before = len(existing_lots)

        maybe_create_bitcoin_lot(rec_tx, sub_tx_data, db)

        # If a new lot was created, we can detect it by comparing list lengths
        new_count = len(rec_tx.bitcoin_lots_created)
        if new_count > lot_count_before:
            count_restored += (new_count - lot_count_before)

    if count_restored > 0:
        logger.info(f"[Restore Pre-Boundary Lots] Recreated {count_restored} older lot(s).")
    else:
        logger.info("[Restore Pre-Boundary Lots] No older lots needed restoring.")


def _build_capital_gains_summary(disposals: List[LotDisposal]) -> Dict[str, Any]:
    """
    Short- and long-term totals from the Form 8949 disposals (form_8949.
    taxable_disposals), each lot slice in its own holding period. It used to
    total whole Sell/Withdrawal transactions by their first lot's holding
    period, leave out transfer fees and add the basis of gifts, so it could
    disagree with Form 8949 and Schedule D.
    """
    zero = Decimal("0")
    terms = {t: {"proceeds": zero, "basis": zero, "gain": zero, "profits": zero, "losses": zero}
             for t in ("short_term", "long_term")}
    for d in disposals:
        t = terms["long_term" if (d.holding_period or "").upper() == "LONG" else "short_term"]
        gain = d.realized_gain_usd or zero
        t["proceeds"] += d.proceeds_usd_for_that_portion or zero
        t["basis"] += d.disposal_basis_usd or zero
        t["gain"] += gain
        t["profits" if gain > 0 else "losses"] += abs(gain)

    def out(t):
        return {k: float(v) for k, v in t.items()}

    total = {k: terms["short_term"][k] + terms["long_term"][k] for k in ("proceeds", "basis", "gain")}
    return {
        "number_of_disposals": len(disposals),
        "short_term": out(terms["short_term"]),
        "long_term": out(terms["long_term"]),
        "total": out(total),
    }


def _build_income_summary(txns: List[Transaction]) -> Dict[str, Any]:
    """
    Summarizes BTC deposits where source is "Income", "Reward", or "Interest."
    Note: This example interprets cost_basis_usd as the deposit's "value."
    """
    from decimal import Decimal

    total_income   = Decimal("0.0")
    total_reward   = Decimal("0.0")
    total_interest = Decimal("0.0")

    for tx in txns:
        if tx.type != "Deposit":
            continue
        if not tx.source:
            continue
        deposit_usd = tx.cost_basis_usd or Decimal("0.0")
        source_lower = tx.source.lower()

        if source_lower == "income":
            total_income += deposit_usd
        elif source_lower == "reward":
            total_reward += deposit_usd
        elif source_lower == "interest":
            total_interest += deposit_usd

    grand_total = total_income + total_reward + total_interest

    return {
        "Income":   float(total_income),
        "Reward":   float(total_reward),
        "Interest": float(total_interest),
        "Total":    float(grand_total),
    }


def _build_asset_summary(db: Session, start_dt: datetime, end_dt: datetime) -> List[Dict[str, Any]]:
    """Realized profit / loss / net on BTC for the tax year, from the lot disposals."""

    gains = [Decimal(d.realized_gain_usd or 0) for d in taxable_disposals(db, start_dt, end_dt)]
    profit = sum((g for g in gains if g > 0), Decimal("0"))
    loss = -sum((g for g in gains if g < 0), Decimal("0"))
    return [{
        "asset": "BTC",
        "profit": float(profit),
        "loss": float(loss),
        "net": float(profit - loss),
    }]


def _build_end_of_year_balances(db: Session, year: int) -> List[Dict[str, Any]]:
    """
    BTC still held at the end of `year`, valued at the Dec 31 BTC price.
    Expects the lots to be a year-end snapshot (see generate_report_data).
    """
    open_lots = (
        db.query(BitcoinLot)
        .filter(BitcoinLot.remaining_btc > 0)
        .order_by(BitcoinLot.acquired_date.asc())
        .all()
    )

    dec31 = datetime(year, 12, 31, 12, tzinfo=timezone.utc)
    try:
        eoy_price = Decimal(get_btc_price(dec31, db)).quantize(Decimal("0.01"))
        price_note = f"@ ${eoy_price:,} per BTC on {year}-12-31"
    except Exception as exc:  # price APIs down: show holdings, flag the value
        logger.warning("No BTC price for %s-12-31: %s", year, exc)
        eoy_price = Decimal("0")
        price_note = f"BTC price for {year}-12-31 unavailable — value not computed"

    rows = []
    total_btc = Decimal("0.0")
    total_cost = Decimal("0.0")
    total_value = Decimal("0.0")

    for lot in open_lots:
        rem_btc = lot.remaining_btc
        if lot.total_btc > 0:
            fraction_remaining = rem_btc / lot.total_btc
        else:
            fraction_remaining = Decimal("1.0")

        partial_cost = (lot.cost_basis_usd * fraction_remaining).quantize(Decimal("0.01"), ROUND_HALF_DOWN)
        cur_value = (rem_btc * eoy_price).quantize(Decimal("0.01"), ROUND_HALF_DOWN)

        rows.append({
            "asset": "BTC (Bitcoin)",
            "quantity": float(rem_btc),
            "cost": float(partial_cost),
            "value": float(cur_value),
            "description": price_note
        })

        total_btc += rem_btc
        total_cost += partial_cost
        total_value += cur_value

    # Grand total row
    rows.append({
        "asset": "Total",
        "quantity": float(total_btc),
        "cost": float(total_cost),
        "value": float(total_value),
        "description": "",
    })
    return rows


def _disposal_row(d: LotDisposal) -> Dict[str, Any]:
    tx = d.transaction
    lot = d.lot
    return {
        "date_sold": tx.timestamp.isoformat() if tx and tx.timestamp else "",
        "date_acquired": lot.acquired_date.isoformat() if lot and lot.acquired_date else "",
        "asset": "BTC",
        "type": "Transfer fee" if tx and tx.type == "Transfer" else (tx.type if tx else ""),
        "amount": float(d.disposed_btc or 0),
        "cost": float(d.disposal_basis_usd or 0),
        "proceeds": float(d.proceeds_usd_for_that_portion or 0),
        "gain_loss": float(d.realized_gain_usd or 0),
        "holding_period": d.holding_period or "",
    }


def _build_capital_gains_transactions_summary(disposals: List[LotDisposal]) -> List[Dict[str, Any]]:
    """
    One line per Form 8949 disposal (a sale across lots gives one line per
    lot, each in its own holding period), including transfer fees.
    """
    return [_disposal_row(d) for d in disposals]


def _build_capital_gains_transactions_detailed(disposals: List[LotDisposal]) -> List[Dict[str, Any]]:
    """The same lines under the per-lot field names older callers use."""
    return [
        {
            "date_sold": row["date_sold"],
            "date_acquired": row["date_acquired"],
            "asset": "BTC",
            "amount_disposed": row["amount"],
            "disposal_basis_usd": row["cost"],
            "proceeds_usd_for_that_portion": row["proceeds"],
            "realized_gain_usd": row["gain_loss"],
            "holding_period": row["holding_period"],
        }
        for row in map(_disposal_row, disposals)
    ]


def _build_income_transactions(txns: List[Transaction]) -> List[Dict[str, Any]]:
    """
    Builds a list of all deposits that might be categorized as "Income", "Reward", or "Interest."
    This is separate from the summarized totals in _build_income_summary; 
    used to show each transaction line in a final PDF or CSV.
    """
    from decimal import Decimal

    results = []
    for tx in txns:
        if tx.type != "Deposit":
            continue
        if not tx.source:
            continue
        source_lower = tx.source.lower()
        if source_lower not in ("income", "reward", "interest"):
            continue

        deposit_usd = tx.cost_basis_usd or Decimal("0.0")
        tx_timestamp = tx.timestamp.isoformat() if tx.timestamp else ""

        # Label the row by the category
        if source_lower == "income":
            row_type = "Income"
        elif source_lower == "reward":
            row_type = "Reward"
        else:
            row_type = "Interest"

        row = {
            "date": tx_timestamp,
            "asset": "BTC",
            "amount": float(tx.amount or 0),
            "value_usd": float(deposit_usd),
            "type": row_type,
            "description": tx.source,
        }
        results.append(row)
    return results


def _build_gifts_donations_lost(txns: List[Transaction]) -> List[Dict[str, Any]]:
    """
    Gathers any withdrawals with purpose in ("Gift","Donation","Lost").
    Shown separately for tax/record-keeping.
    """
    results = []
    for tx in txns:
        if tx.type != "Withdrawal":
            continue
        if not tx.purpose:
            continue
        purpose_lower = tx.purpose.lower()
        if purpose_lower in ("gift", "donation", "lost"):
            row = {
                "date": tx.timestamp.isoformat() if tx.timestamp else "",
                "asset": "BTC",
                "amount": float(tx.amount or 0),
                "proceeds_usd": float(tx.proceeds_usd or 0),
                # None when no value was given or priced: shown as "not given",
                # not as $0 (which reads like a worthless gift).
                "fmv_usd": float(tx.fmv_usd) if tx.fmv_usd is not None else None,
                "type": tx.purpose,
            }
            results.append(row)
    return results


def _build_expenses_list(txns: List[Transaction]) -> List[Dict[str, Any]]:
    """
    Identifies transactions marked as a "Withdrawal" with purpose="Expenses."
    Useful for business expense tracking or personal record-keeping.
    """
    results = []
    for tx in txns:
        if tx.type == "Withdrawal" and tx.purpose and tx.purpose.lower() == "expenses":
            row = {
                "date": tx.timestamp.isoformat() if tx.timestamp else "",
                "asset": "BTC",
                "amount": float(tx.amount or 0),
                "value_usd": float(tx.proceeds_usd or 0),
                "type": "Expense",
            }
            results.append(row)
    return results


def _gather_data_sources(txns: List[Transaction]) -> List[str]:
    """
    Example function that collects any unique `tx.source` strings to show
    where the data originated. Expand to handle additional fields if needed.
    """
    sources = set()
    for tx in txns:
        if tx.source:
            sources.add(tx.source)
    return sorted(list(sources))
