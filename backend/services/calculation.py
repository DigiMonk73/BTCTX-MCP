"""
backend/services/calculation.py

Refactored aggregator to rely solely on 'LotDisposal' records for realized gains,
eliminating double-counting with 'transaction.realized_gain_usd'.
'Spent' withdrawals are still tracked under 'withdrawals_spent' (for personal finance),
but are not treated as a capital loss.

We've also added a small safeguard warning if any disposal lacks holding_period,
and now we compute a new "year_to_date_capital_gains" field by filtering disposals
to only those whose Transaction timestamp is >= January 1 of the current year.
"""

from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from decimal import Decimal, ROUND_HALF_DOWN
from typing import List, Dict
import logging

from backend.models.account import Account
from backend.models.transaction import Transaction, LedgerEntry, LotDisposal, BitcoinLot

logger = logging.getLogger(__name__)

def get_account_balance(db: Session, account_id: int) -> Decimal:
    """
    Return the numeric balance for a given account_id by summing
    LedgerEntry.amount in the ledger_entries table. Returns Decimal("0.0") if none.
    """
    total = (
        db.query(func.sum(LedgerEntry.amount))
          .filter(LedgerEntry.account_id == account_id)
          .scalar()
    )
    return total or Decimal("0.0")


def get_all_account_balances(db: Session) -> List[Dict]:
    """
    Returns a list of all accounts (id, name, currency) plus their current balance.
    Balances are computed in a single grouped query instead of one query per account.
    """
    sums = dict(
        db.query(LedgerEntry.account_id, func.sum(LedgerEntry.amount))
          .group_by(LedgerEntry.account_id)
          .all()
    )
    accounts = db.query(Account).all()
    return [
        {
            "account_id": account.id,
            "name": account.name,
            "currency": account.currency,
            "balance": sums.get(account.id, Decimal("0.0")),
        }
        for account in accounts
    ]


def get_average_cost_basis(db: Session) -> Decimal:
    """
    Returns the average USD cost basis per BTC across all currently held BTC lots,
    i.e. sum of leftover cost basis / sum of remaining_btc, rounded to 2 decimals.
    """
    lots = db.query(BitcoinLot).filter(BitcoinLot.remaining_btc > 0).all()
    total_btc_remaining = Decimal("0")
    total_cost_basis_remaining = Decimal("0")

    for lot in lots:
        if lot.total_btc > 0:
            # fraction of the original lot still held
            fraction_left = (lot.remaining_btc / lot.total_btc).quantize(
                Decimal("0.00000001"),
                rounding=ROUND_HALF_DOWN
            )
            # leftover cost basis for that fraction
            leftover_cost_basis = (
                lot.cost_basis_usd * fraction_left
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)

            total_btc_remaining += lot.remaining_btc
            total_cost_basis_remaining += leftover_cost_basis

    if total_btc_remaining == 0:
        return Decimal("0")

    average_basis = total_cost_basis_remaining / total_btc_remaining
    return average_basis.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)


def get_gains_and_losses(db: Session) -> dict:
    """
    Aggregates various crypto metrics (deposits for income, fees, realized gains/losses,
    etc.) for display in the frontend. Uses only 'LotDisposal' for capital gain events,
    thus avoiding double-counting with transaction-level fields.

    - 'Spent' withdrawals:
         We track the USD proceeds in 'withdrawals_spent' for personal finance,
         but do NOT treat that as a separate capital loss. The actual gain/loss
         is accounted for in partial-lot usage (LotDisposal).

    - year_to_date_capital_gains:
         We now filter disposals to only those whose Transaction.timestamp
         is >= Jan 1 of the current year, summing realized_gain_usd.
    """
    # --------------------- 1) Initialize Aggregators ---------------------
    sells_proceeds = Decimal("0.0")
    withdrawals_spent = Decimal("0.0")

    # Per-source deposit aggregators (USD cost basis and BTC amount per source)
    deposit_usd = {s: Decimal("0.0") for s in ("income", "interest", "reward", "gift")}
    deposit_btc = {s: Decimal("0.0") for s in deposit_usd}

    fees_usd = Decimal("0.0")
    fees_btc = Decimal("0.0")

    # Gains vs. Losses
    short_term_gains = Decimal("0.0")
    short_term_losses = Decimal("0.0")
    long_term_gains = Decimal("0.0")
    long_term_losses = Decimal("0.0")

    # --------------------- 2) Summarize Gains from LotDisposal ---------------------
    disposals = db.query(LotDisposal).all()
    for disposal in disposals:
        gain = disposal.realized_gain_usd
        # If no holding_period is set, we default to SHORT but log a warning
        if not disposal.holding_period:
            logger.warning(
                f"LotDisposal ID={disposal.id} has no holding_period; defaulting to SHORT in aggregator."
            )
        holding_period = disposal.holding_period.upper() if disposal.holding_period else "SHORT"

        if gain is not None:
            if gain > 0:
                if holding_period == "SHORT":
                    short_term_gains += gain
                else:
                    long_term_gains += gain
            elif gain < 0:
                abs_loss = abs(gain)
                if holding_period == "SHORT":
                    short_term_losses += abs_loss
                else:
                    long_term_losses += abs_loss

    # --------------------- 3) Parse Transactions for Non-Disposal Aggregations ---------------------
    transactions = db.query(Transaction).all()
    for tx in transactions:
        tx_type = tx.type.lower()

        # SELL => track proceeds for reference
        if tx_type == "sell" and tx.proceeds_usd is not None:
            try:
                sells_proceeds += Decimal(str(tx.proceeds_usd))
            except Exception as e:
                logger.warning(f"Error converting proceeds_usd for Sell txn {tx.id}: {e}")

        # WITHDRAWAL (Spent) => track how many USD were spent, but not as a capital loss
        if (
            tx_type == "withdrawal"
            and (tx.purpose or "").lower() == "spent"
            and tx.proceeds_usd is not None
        ):
            try:
                withdrawals_spent += Decimal(str(tx.proceeds_usd))
            except Exception as e:
                logger.warning(f"Error converting proceeds_usd for Spent withdrawal txn {tx.id}: {e}")

        # DEPOSIT (Income / Interest / Reward / Gift) => per-source USD + BTC totals
        if tx_type == "deposit" and tx.cost_basis_usd is not None and tx.amount is not None:
            source = (tx.source or "").lower()
            if source in deposit_usd:
                try:
                    cb = Decimal(str(tx.cost_basis_usd))
                    amt = Decimal(str(tx.amount))
                    if cb > 0:
                        deposit_usd[source] += cb
                    if amt > 0:
                        deposit_btc[source] += amt
                except Exception as e:
                    logger.warning(
                        f"Error converting cost_basis_usd for {source.title()} Deposit txn {tx.id}: {e}"
                    )

        # FEES (USD or BTC)
        if tx.fee_amount is not None and tx.fee_currency is not None:
            try:
                fee_amt = Decimal(str(tx.fee_amount))
                currency = tx.fee_currency.lower()
                if currency == "usd":
                    fees_usd += fee_amt
                elif currency == "btc":
                    fees_btc += fee_amt
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse fee_amount {tx.fee_amount} for tx {tx.id}: {e}")

    # --------------------- 4) Final Summaries & YTD Gains Logic ---------------------
    income_earned, income_btc = deposit_usd["income"], deposit_btc["income"]
    interest_earned, interest_btc = deposit_usd["interest"], deposit_btc["interest"]
    rewards_earned, rewards_btc = deposit_usd["reward"], deposit_btc["reward"]
    gifts_received, gifts_btc = deposit_usd["gift"], deposit_btc["gift"]

    total_income = income_earned + interest_earned + rewards_earned

    # 'total_losses' no longer includes 'withdrawals_spent'
    total_losses = Decimal("0.0")

    short_term_net = short_term_gains - short_term_losses
    long_term_net = long_term_gains - long_term_losses
    total_net_capital_gains = short_term_net + long_term_net

    # (NEW) Year-to-Date Gains logic
    from backend.services.tax_time import get_tax_timezone, tax_year_bounds
    tz = get_tax_timezone(db)
    start_of_year, _ = tax_year_bounds(datetime.now(tz).year, tz)

    ytd_gain_sum = (
        db.query(func.coalesce(func.sum(LotDisposal.realized_gain_usd), 0))
          .join(Transaction, LotDisposal.transaction_id == Transaction.id)
          .filter(Transaction.timestamp >= start_of_year)
          .scalar()
    )
    ytd_gain_sum = Decimal(str(ytd_gain_sum or 0))

    # Convert ytd_gain_sum => float
    year_to_date_capital_gains = float(
        ytd_gain_sum.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)
    )

    return {
        # --------------- USD-based fields => 2 decimals ---------------
        "sells_proceeds": float(sells_proceeds.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)),
        "withdrawals_spent": float(withdrawals_spent.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)),
        "income_earned": float(income_earned.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)),
        "interest_earned": float(interest_earned.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)),
        "rewards_earned": float(rewards_earned.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)),
        "gifts_received": float(gifts_received.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)),
        "total_income": float(total_income.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)),
        "total_losses": float(total_losses.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)),

        # --------------- Gains/Losses ---------------
        "short_term_gains": float(short_term_gains.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)),
        "short_term_losses": float(short_term_losses.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)),
        "short_term_net": float(short_term_net.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)),

        "long_term_gains": float(long_term_gains.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)),
        "long_term_losses": float(long_term_losses.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)),
        "long_term_net": float(long_term_net.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)),
        "total_net_capital_gains": float(
            total_net_capital_gains.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)
        ),

        # --------------- BTC-based fields => 8 decimals ---------------
        "income_btc": float(income_btc.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_DOWN)),
        "interest_btc": float(interest_btc.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_DOWN)),
        "rewards_btc": float(rewards_btc.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_DOWN)),
        "gifts_btc": float(gifts_btc.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_DOWN)),

        # --------------- Fees ---------------
        "fees": {
            "USD": float(fees_usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)),
            "BTC": float(fees_btc.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_DOWN)),
        },

        # --------------- YTD Gains ---------------
        "year_to_date_capital_gains": year_to_date_capital_gains,
    }
