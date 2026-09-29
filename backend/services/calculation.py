"""
The dashboard's figures: account balances from the ledger lines, the
average cost of the BTC still held, and gains and income. Realized gains
come from the lot disposals only (a transaction's own gain would count them
twice); a Spent withdrawal's proceeds are shown, not counted as a loss.
"""

from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from decimal import Decimal, ROUND_HALF_DOWN
import logging

from backend.models.account import Account
from backend.models.transaction import Transaction, LedgerEntry, LotDisposal, BitcoinLot
from backend.services.tax_time import get_tax_timezone, tax_year_bounds

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")
SAT = Decimal("0.00000001")

# The deposit sources the dashboard totals, in USD (their basis) and BTC.
DEPOSIT_TOTALS = ("income", "interest", "reward", "gift")


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


def get_all_account_balances(db: Session) -> list[dict]:
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
            fraction_left = (lot.remaining_btc / lot.total_btc).quantize(SAT, rounding=ROUND_HALF_DOWN)
            # leftover cost basis for that fraction
            leftover_cost_basis = (lot.cost_basis_usd * fraction_left).quantize(CENT, rounding=ROUND_HALF_DOWN)

            total_btc_remaining += lot.remaining_btc
            total_cost_basis_remaining += leftover_cost_basis

    if total_btc_remaining == 0:
        return Decimal("0")

    average_basis = total_cost_basis_remaining / total_btc_remaining
    return average_basis.quantize(CENT, rounding=ROUND_HALF_DOWN)


def get_gains_and_losses(db: Session) -> dict:
    """
    The dashboard's gains and income: realized gains and losses by holding
    period (from the lot disposals only, so nothing counts twice), sale and
    Spent proceeds, deposits by income source in USD and BTC, fees by
    currency, and this tax year's net gain. USD to the cent, BTC to the
    satoshi, as JSON numbers.
    """
    gains = _realized_gains(db.query(LotDisposal).all())
    transactions = db.query(Transaction).all()
    proceeds = _proceeds(transactions)
    deposit_usd, deposit_btc = _deposits_by_source(transactions)
    fees_usd, fees_btc = _fees(transactions)
    short_term_net = gains["short_term_gains"] - gains["short_term_losses"]
    long_term_net = gains["long_term_gains"] - gains["long_term_losses"]
    return {
        "sells_proceeds": _usd(proceeds["sell"]),
        "withdrawals_spent": _usd(proceeds["spent"]),
        "income_earned": _usd(deposit_usd["income"]),
        "interest_earned": _usd(deposit_usd["interest"]),
        "rewards_earned": _usd(deposit_usd["reward"]),
        "gifts_received": _usd(deposit_usd["gift"]),
        "total_income": _usd(deposit_usd["income"] + deposit_usd["interest"] + deposit_usd["reward"]),
        # Spent withdrawals aren't losses: their gain or loss is in the disposals.
        "total_losses": _usd(Decimal("0.0")),
        "short_term_gains": _usd(gains["short_term_gains"]),
        "short_term_losses": _usd(gains["short_term_losses"]),
        "short_term_net": _usd(short_term_net),
        "long_term_gains": _usd(gains["long_term_gains"]),
        "long_term_losses": _usd(gains["long_term_losses"]),
        "long_term_net": _usd(long_term_net),
        "total_net_capital_gains": _usd(short_term_net + long_term_net),
        "income_btc": _btc(deposit_btc["income"]),
        "interest_btc": _btc(deposit_btc["interest"]),
        "rewards_btc": _btc(deposit_btc["reward"]),
        "gifts_btc": _btc(deposit_btc["gift"]),
        "fees": {"USD": _usd(fees_usd), "BTC": _btc(fees_btc)},
        "year_to_date_capital_gains": _usd(_year_to_date_gain(db)),
    }


def _usd(value: Decimal) -> float:
    return float(value.quantize(CENT, rounding=ROUND_HALF_DOWN))


def _btc(value: Decimal) -> float:
    return float(value.quantize(SAT, rounding=ROUND_HALF_DOWN))


def _realized_gains(disposals: list[LotDisposal]) -> dict[str, Decimal]:
    """Gains and losses (as positive amounts) by holding period; a disposal
    without one counts as short-term."""
    totals = {
        key: Decimal("0.0")
        for key in ("short_term_gains", "short_term_losses", "long_term_gains", "long_term_losses")
    }
    for disposal in disposals:
        if not disposal.holding_period:
            logger.warning(
                f"LotDisposal ID={disposal.id} has no holding_period; defaulting to SHORT in aggregator."
            )
        term = "short_term" if (disposal.holding_period or "SHORT").upper() == "SHORT" else "long_term"
        gain = disposal.realized_gain_usd
        if gain is not None and gain > 0:
            totals[f"{term}_gains"] += gain
        elif gain is not None and gain < 0:
            totals[f"{term}_losses"] += abs(gain)
    return totals


def _proceeds(transactions: list[Transaction]) -> dict[str, Decimal]:
    """What Sells brought in, and what Spent withdrawals paid for."""
    totals = {"sell": Decimal("0.0"), "spent": Decimal("0.0")}
    for tx in transactions:
        if tx.proceeds_usd is None:
            continue
        tx_type = tx.type.lower()
        if tx_type == "sell":
            totals["sell"] += Decimal(str(tx.proceeds_usd))
        elif tx_type == "withdrawal" and (tx.purpose or "").lower() == "spent":
            totals["spent"] += Decimal(str(tx.proceeds_usd))
    return totals


def _deposits_by_source(transactions: list[Transaction]) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    """(USD basis, BTC amount) of the deposits from each DEPOSIT_TOTALS source."""
    usd = {source: Decimal("0.0") for source in DEPOSIT_TOTALS}
    btc = {source: Decimal("0.0") for source in DEPOSIT_TOTALS}
    for tx in transactions:
        source = (tx.source or "").lower()
        if tx.type.lower() != "deposit" or source not in usd:
            continue
        if tx.cost_basis_usd is None or tx.amount is None:
            continue
        basis, amount = Decimal(str(tx.cost_basis_usd)), Decimal(str(tx.amount))
        if basis > 0:
            usd[source] += basis
        if amount > 0:
            btc[source] += amount
    return usd, btc


def _fees(transactions: list[Transaction]) -> tuple[Decimal, Decimal]:
    """(USD fees, BTC fees), as entered."""
    fees = {"usd": Decimal("0.0"), "btc": Decimal("0.0")}
    for tx in transactions:
        if tx.fee_amount is None or tx.fee_currency is None:
            continue
        currency = tx.fee_currency.lower()
        if currency in fees:
            fees[currency] += Decimal(str(tx.fee_amount))
    return fees["usd"], fees["btc"]


def _year_to_date_gain(db: Session) -> Decimal:
    """The net gain of the disposals since this tax year began, in the tax
    timezone."""
    tz = get_tax_timezone(db)
    start_of_year, _ = tax_year_bounds(datetime.now(tz).year, tz)
    total = (
        db.query(func.coalesce(func.sum(LotDisposal.realized_gain_usd), 0))
          .join(Transaction, LotDisposal.transaction_id == Transaction.id)
          .filter(Transaction.timestamp >= start_of_year)
          .scalar()
    )
    return Decimal(str(total or 0))
