"""
The complete tax report's data for one tax year: holdings at its start and
end, capital gains (the Form 8949 disposals, spending included), income and gifts.
complete_tax_report.py turns it into the PDF.
"""

from datetime import datetime, timezone
from typing import Any
from collections.abc import Iterator
from decimal import Decimal, ROUND_HALF_DOWN
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.constants import BTC_ACCOUNTS, GIFT_LIKE_PURPOSES, INHERITED_SOURCE, REBATE_SOURCE, VALUED_AT_RECEIPT, normalized
from backend.models.transaction import (
    Transaction,
    BitcoinLot,
    LotDisposal,
)
from backend.database import scratch_copy
from backend.models.account import Account
from backend.services.tax_time import get_tax_timezone, get_tax_timezone_name, tax_year_bounds
from backend.services.reports.form_8949 import (
    INHERITED, SCHEDULE_D_LINE_FOR_BOX, build_form_8949_and_schedule_d, disposal_box, taxable_disposals,
)

from backend.services import hourly_prices, price_history
from backend.unexpected_errors import log_unexpected
from backend.services.transaction import (
    DEPOSIT_SOURCES, WITHDRAWAL_PURPOSES, cost_left, listed_spelling, price_used, recalculate_all_transactions,
)

logger = logging.getLogger(__name__)


def _held_value_price(db: Session, when: datetime) -> hourly_prices.Priced | None:
    """
    The BTC price that values holdings at a tax year's bound `when`: the
    price when that hour began, else that UTC day's 00:00 price (#144,
    hourly_prices.price_at); None when there's none (price lookups off, no
    history, or a bound still to come). The report then shows those values
    as not priced, never $0 or an error.
    """
    if when > datetime.now(timezone.utc):
        return None  # the year isn't over: no year-end value yet
    try:
        return hourly_prices.price_at(db, when)
    except HTTPException as exc:  # no price: the bound (not a transaction's date) and why
        logger.warning("No BTC price for %s: %s", when.isoformat(), exc.detail)
    except Exception as exc:  # never its text at WARNING (#430)
        log_unexpected(f"The BTC price for {when.isoformat()}", exc, logger)
    return None


def _year_end_note(priced: hourly_prices.Priced | None, year: int) -> str:
    """How the year-end holdings are valued, as the report shows it. A year
    not over reads the same (the cover says so): a reference figure mustn't
    change with the day it's computed."""
    if priced is None:
        return f"No BTC price for when {year} ended: not priced"
    usd = priced.usd.quantize(Decimal("0.01"))
    if priced.moment == "hour":
        # A tax year can end at :15 or :45 (Asia/Kathmandu): the price when that hour began
        return f"@ ${usd:,} per BTC, the price at the hour the tax year ended ({priced.at:%Y-%m-%d %H:%M} UTC)"
    return (f"@ ${usd:,} per BTC, {priced.at:%Y-%m-%d}'s 00:00 UTC price (no hourly price for when the "
            "tax year ended)")


def generate_report_data(db: Session, year: int) -> dict[str, Any]:
    """
    Generates a comprehensive dictionary of data for the specified tax year (YYYY).
    This data can be passed to PDF generators or any other reporting interface.

    Pipeline:
      1) Start- and end-of-year holdings: replay the ledger up to each year
         boundary on a throwaway copy of the database (scratch_copy).
      2) Everything else reads the live ledger, which every write already
         keeps fully recalculated. Building a report changes nothing.
    """
    logger.info(f"Begin building report data for tax_year={year}")

    # 1) Gather beginning-of-year balances (snapshot)
    start_dt, end_dt = tax_year_bounds(year, get_tax_timezone(db))
    with scratch_copy(db) as scratch:
        start_of_year_data = _build_start_of_year_balances(scratch, year)

    # 1b) End-of-year snapshot: replay only transactions before the
    #     year boundary, so later activity doesn't leak into 12/31 holdings
    with scratch_copy(db) as scratch:
        recalculate_all_transactions(scratch, until=end_dt)
        eoy_list = _build_end_of_year_balances(scratch, year)

    # 3) Filter transactions within that tax year

    txns = (
        db.query(Transaction)
        .filter(Transaction.timestamp >= start_dt, Transaction.timestamp < end_dt)
        .order_by(Transaction.timestamp.asc(), Transaction.id.asc())
        .all()
    )

    # 4) Build each needed section
    disposals         = taxable_disposals(db, start_dt, end_dt)
    gains_dict        = _build_capital_gains_summary(disposals)
    income_dict       = _build_income_summary(txns)
    asset_list        = _build_asset_summary(db, start_dt, end_dt)
    cap_gain_txs_sum  = _build_capital_gains_transactions_summary(disposals, year, get_tax_timezone(db))
    cap_gain_txs_det  = _build_capital_gains_transactions_detailed(disposals)
    income_txs        = _build_income_transactions(txns)
    rebates           = _build_rebates(txns)
    gifts_lost        = _build_gifts_donations_lost(txns)
    priced_values     = _build_priced_values(txns, get_tax_timezone(db), db)
    data_sources_list = _gather_data_sources(txns)

    # 5) Construct final dictionary
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
        "form_8949_boxes": _build_form_8949_boxes(db, year),

        "income_transactions": income_txs,
        "rebates": rebates,
        "gifts_donations_lost": gifts_lost,
        "priced_values": priced_values,
        "data_sources": data_sources_list,
    }
    return result


def _build_start_of_year_balances(db: Session, year: int) -> list[dict[str, Any]]:
    """
    BTC held when the tax year begins, valued at the price then (the
    previous year's end: _held_value_price). Replays
    only the transactions before that instant, as the year-end snapshot does,
    so it always equals the previous year's end-of-year holdings. Runs on a
    scratch copy (see generate_report_data).
    """
    from_dt, _ = tax_year_bounds(year, get_tax_timezone(db))
    recalculate_all_transactions(db, until=from_dt)
    open_lots = db.query(BitcoinLot).filter(BitcoinLot.remaining_btc > 0).all()

    # The Jan 1 price, only if something was held (None: not priced)
    priced = _held_value_price(db, from_dt) if open_lots else None
    january1_price = priced.usd.quantize(Decimal("0.01")) if priced else None

    results = []
    for lot in open_lots:
        # The cost of what's left: the lot's cost less its pieces' (#100)
        partial_cost = cost_left(lot)
        avg_basis = partial_cost / lot.remaining_btc

        # market value as of Jan 1
        cur_value = None if january1_price is None else \
            float((lot.remaining_btc * january1_price).quantize(Decimal("0.01"), ROUND_HALF_DOWN))

        results.append({
            "quantity": float(lot.remaining_btc),
            "avg_cost_basis": float(avg_basis),
            "value": cur_value,  # None: no Jan 1 price
        })

    logger.debug(f"Found {len(results)} leftover BTC lots as of start-of-year {year}")
    return results


def _build_capital_gains_summary(disposals: list[LotDisposal]) -> dict[str, Any]:
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


def _is_btc_deposit(tx: Transaction) -> bool:
    """A deposit into Wallet or Exchange BTC. One into Bank or Exchange USD
    is dollars, never bitcoin income, whatever value an older version or an
    import left on it."""
    return tx.type == "Deposit" and tx.to_account_id in BTC_ACCOUNTS


def _build_income_summary(txns: list[Transaction]) -> dict[str, Any]:
    """
    Summarizes BTC deposits where source is "Income", "Reward", or "Interest."
    Note: This example interprets cost_basis_usd as the deposit's "value."
    """
    from decimal import Decimal

    total_income   = Decimal("0.0")
    total_reward   = Decimal("0.0")
    total_interest = Decimal("0.0")

    for tx in txns:
        if not _is_btc_deposit(tx) or not tx.source:
            continue
        deposit_usd = tx.cost_basis_usd or Decimal("0.0")
        source_lower = normalized(tx.source)

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


def _build_asset_summary(db: Session, start_dt: datetime, end_dt: datetime) -> list[dict[str, Any]]:
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


def _build_end_of_year_balances(db: Session, year: int) -> list[dict[str, Any]]:
    """
    BTC still held at the end of `year`, valued at the price when the tax
    year ended (_held_value_price; it was December 31's 00:00 UTC price).
    Expects the lots to be a year-end snapshot (see generate_report_data).
    """
    open_lots = (
        db.query(BitcoinLot)
        .filter(BitcoinLot.remaining_btc > 0)
        .order_by(BitcoinLot.acquired_date.asc())
        .all()
    )
    account_names = {a.id: a.name for a in db.query(Account)}

    _, year_end = tax_year_bounds(year, get_tax_timezone(db))
    priced = _held_value_price(db, year_end) if open_lots else None
    eoy_price = priced.usd.quantize(Decimal("0.01")) if priced else None
    price_note = _year_end_note(priced, year)

    rows = []
    total_btc = Decimal("0.0")
    total_cost = Decimal("0.0")
    total_value = Decimal("0.0")

    for lot in open_lots:
        rem_btc = lot.remaining_btc
        partial_cost = cost_left(lot)  # the lot's cost less its pieces' (#100)
        cur_value = None if eoy_price is None else \
            (rem_btc * eoy_price).quantize(Decimal("0.01"), ROUND_HALF_DOWN)

        origin = lot.created_transaction
        rows.append({
            "asset": "BTC (Bitcoin)",
            # A lot belongs to the account it was created in (FIFO per account)
            "account": account_names.get(origin.to_account_id, "") if origin else "",
            "acquired": lot.acquired_date.isoformat() if lot.acquired_date else "",
            "quantity": float(rem_btc),
            "cost": float(partial_cost),
            "value": None if cur_value is None else float(cur_value),  # None: no year-end price
            "description": price_note
        })

        total_btc += rem_btc
        total_cost += partial_cost
        if cur_value is not None:
            total_value += cur_value

    # Grand total row
    rows.append({
        "asset": "Total",
        "quantity": float(total_btc),
        "cost": float(total_cost),
        "value": None if open_lots and eoy_price is None else float(total_value),
        "description": "",
    })
    return rows


def _disposal_kind(d: LotDisposal) -> str:
    """What gave rise to a disposal: a sale, a spend, or a network fee."""
    tx = d.transaction
    if d.is_fee or (tx is not None and tx.type == "Transfer"):
        return "Network fee"
    if tx is not None and tx.type == "Withdrawal":
        return "Spend"
    return "Sale"


def _disposal_row(d: LotDisposal) -> dict[str, Any]:
    tx = d.transaction
    lot = d.lot
    return {
        "date_sold": tx.timestamp.isoformat() if tx and tx.timestamp else "",
        # As Form 8949's column (b): inherited coins have no date there (#154)
        "date_acquired": INHERITED if lot and lot.inherited else (
            lot.acquired_date.isoformat() if lot and lot.acquired_date else ""),
        "asset": "BTC",
        "type": "Transfer fee" if tx and tx.type == "Transfer" else (tx.type if tx else ""),
        "amount": float(d.disposed_btc or 0),
        "cost": float(d.disposal_basis_usd or 0),
        "proceeds": float(d.proceeds_usd_for_that_portion or 0),
        "gain_loss": float(d.realized_gain_usd or 0),
        "holding_period": d.holding_period or "",
    }


def _build_capital_gains_transactions_summary(disposals: list[LotDisposal], year: int,
                                              tz) -> list[dict[str, Any]]:
    """
    One line per Form 8949 disposal (a sale across lots gives one line per
    lot, each in its own holding period), including transfer fees, with
    its kind and Form 8949 box.
    """
    return [{**_disposal_row(d), "kind": _disposal_kind(d), "box": disposal_box(d, year, tz)} for d in disposals]


def _build_form_8949_boxes(db: Session, year: int) -> list[dict[str, Any]]:
    """
    Each Form 8949 box of the year with its rows' totals, as the IRS forms
    BitcoinTX fills add them up (form_8949.py), and its Schedule D line.
    """
    forms = build_form_8949_and_schedule_d(year, db)
    boxes: dict[str, dict[str, Any]] = {}
    for row in forms["short_term"] + forms["long_term"]:
        box = boxes.setdefault(row["box"], {"box": row["box"], "line": SCHEDULE_D_LINE_FOR_BOX[row["box"]],
                                            "rows": 0, "proceeds": Decimal(0), "cost": Decimal(0),
                                            "gain_loss": Decimal(0)})
        box["rows"] += 1
        for key in ("proceeds", "cost", "gain_loss"):
            box[key] += row[key]
    return [{**b, **{k: float(b[k]) for k in ("proceeds", "cost", "gain_loss")}} for _, b in sorted(boxes.items())]


def _build_capital_gains_transactions_detailed(disposals: list[LotDisposal]) -> list[dict[str, Any]]:
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


def _build_income_transactions(txns: list[Transaction]) -> list[dict[str, Any]]:
    """
    Builds a list of all deposits that might be categorized as "Income", "Reward", or "Interest."
    This is separate from the summarized totals in _build_income_summary; 
    used to show each transaction line in a final PDF or CSV.
    """
    from decimal import Decimal

    results = []
    for tx in txns:
        if not _is_btc_deposit(tx) or not tx.source:
            continue
        source_lower = normalized(tx.source)
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
            "description": listed_spelling(tx.source, DEPOSIT_SOURCES),
        }
        results.append(row)
    return results


def _build_rebates(txns: list[Transaction]) -> list[dict[str, Any]]:
    """Bitcoin received as a rebate on spending (source Rebate, #98): its
    value at receipt is its cost basis, and it is never income."""
    return [{"date": tx.timestamp.isoformat() if tx.timestamp else "", "amount": float(tx.amount or 0),
             "value_usd": float(tx.cost_basis_usd or 0)}
            for tx in txns if _is_btc_deposit(tx) and normalized(tx.source) == REBATE_SOURCE]


def _build_gifts_donations_lost(txns: list[Transaction]) -> list[dict[str, Any]]:
    """
    Gathers any withdrawals of bitcoin with purpose in ("Gift","Donation","Lost").
    Shown separately for tax/record-keeping. A dollar withdrawal isn't one,
    whatever purpose an older save left on it (#449).
    """
    results = []
    for tx in txns:
        if tx.type != "Withdrawal" or tx.from_account_id not in BTC_ACCOUNTS:
            continue
        if not tx.purpose:
            continue
        purpose_lower = normalized(tx.purpose)
        if purpose_lower in GIFT_LIKE_PURPOSES:
            row = {
                "date": tx.timestamp.isoformat() if tx.timestamp else "",
                "asset": "BTC",
                "amount": float(tx.amount or 0),
                "proceeds_usd": float(tx.proceeds_usd or 0),
                # None when no value was given or priced: shown as "not given",
                # not as $0 (which reads like a worthless gift).
                "fmv_usd": float(tx.fmv_usd) if tx.fmv_usd is not None else None,
                "type": listed_spelling(tx.purpose, WITHDRAWAL_PURPOSES),
                "lots_by_term": _lots_by_term(tx),
            }
            results.append(row)
    return results


def _lots_by_term(tx: Transaction) -> list[dict[str, Any]]:
    """
    What a gift, donation or loss took from its lots, by term (#160): the
    BTC and cost basis held more than a year (LONG) and a year or less
    (SHORT), long-term first, a term only when some of it was. A
    donation's deduction depends on both. Its network fee's lots are left
    out: that fee is a disposal of its own (section 2).
    """
    terms: dict[str, dict[str, Decimal]] = {}
    for d in tx.lot_disposals:
        if d.is_fee:
            continue
        term = "LONG" if (d.holding_period or "").upper() == "LONG" else "SHORT"  # as the gains summary
        part = terms.setdefault(term, {"btc": Decimal(0), "cost_basis": Decimal(0)})
        part["btc"] += d.disposed_btc or 0
        part["cost_basis"] += d.disposal_basis_usd or 0
    return [{"term": term, "btc": float(terms[term]["btc"]), "cost_basis": float(terms[term]["cost_basis"])}
            for term in ("LONG", "SHORT") if term in terms]


def _build_priced_values(txns: list[Transaction], tz, db: Session | None = None) -> list[dict[str, Any]]:
    """
    The year's values BitcoinTX filled in from the BTC price, and which
    price each used (#144): an income, rebate or inherited deposit's value,
    a Spent's proceeds, a gift's, donation's or lost coins' value (#255), a
    BTC network fee's value. Every other such value was entered with its
    transaction (or filled in, unmarked, by the AI connector before 1.2.9).
    """
    years: dict = {}  # the stored history's year files, read once for the report
    return [
        {"date": tx.timestamp.isoformat(), "transaction": _transaction_label(tx), "value": name,
         "usd": float(usd), "priced_at": priced_at + _from_where(tx, db, years)}
        for tx in txns for name, usd, priced_at in _priced_values(tx, tz)
    ]


# The stored price's source, as the report names it (#145)
_SOURCE_NAMES = {"bitstamp": "Bitstamp", "kraken": "Kraken", "mempool": "your Mempool"}


def _from_where(tx: Transaction, db: Session | None, years: dict) -> str:
    """", Bitstamp": where the stored price a transaction's values came from
    was found (services/transaction.price_used, read only); nothing when
    it isn't known."""
    used = price_used(tx, db, years) if db is not None else None
    source = (used or {}).get("source", "")
    return f", {_SOURCE_NAMES.get(source, source)}" if source in _SOURCE_NAMES else ""


def _priced_values(tx: Transaction, tz) -> Iterator[tuple[str, Decimal, str]]:
    """(what, USD, which price) for each of a transaction's values from a price."""
    source = normalized(tx.source)
    if tx.cost_basis_from_price and tx.cost_basis_usd is not None and _is_btc_deposit(tx) \
            and source in VALUED_AT_RECEIPT:
        if source == INHERITED_SOURCE and tx.acquired_at is not None:
            yield "Value (cost basis)", tx.cost_basis_usd, \
                f"Its date of death's ({tx.acquired_at}) 00:00 UTC price"
        else:
            name = "Value (cost basis)" if source == REBATE_SOURCE else "Value (income and basis)"
            yield name, tx.cost_basis_usd, _price_used(tx)
    if tx.proceeds_from_price and tx.gross_proceeds_usd is not None and tx.type == "Withdrawal" \
            and normalized(tx.purpose) == "spent":
        yield "Proceeds (before fees)", tx.gross_proceeds_usd, _price_used(tx)
    if tx.fmv_from_price and tx.fmv_usd is not None and tx.type == "Withdrawal" \
            and normalized(tx.purpose) in GIFT_LIKE_PURPOSES:
        yield "Value (fair market value)", tx.fmv_usd, _price_used(tx)
    if tx.fee_usd is not None and not tx.fee_usd_manual and (tx.fee_currency or "").upper() == "BTC" \
            and Decimal(tx.fee_amount or 0) > 0:
        yield "Network fee value", tx.fee_usd, _price_used(tx)


def _price_used(tx: Transaction) -> str:
    """Which price valued a transaction's priced values: its hour's, or its
    UTC day's (marked "day", or saved before the mark existed)."""
    if tx.price_moment == "hour":
        hour = datetime.fromtimestamp(hourly_prices.hour_of(tx.timestamp), tz=timezone.utc)
        return f"When its hour began ({hour:%Y-%m-%d %H:00} UTC)"
    return f"That day's ({price_history.utc_day(tx.timestamp)}) 00:00 UTC price"


def _transaction_label(tx: Transaction) -> str:
    """"Deposit (Reward)", "Withdrawal (Spent)", "Transfer"."""
    detail = listed_spelling(tx.source, DEPOSIT_SOURCES) if tx.type == "Deposit" \
        else listed_spelling(tx.purpose, WITHDRAWAL_PURPOSES) if tx.type == "Withdrawal" else None
    return f"{tx.type} ({detail})" if detail else tx.type


def _gather_data_sources(txns: list[Transaction]) -> list[str]:
    """
    Example function that collects any unique `tx.source` strings to show
    where the data originated. Expand to handle additional fields if needed.
    """
    sources = set()
    for tx in txns:
        if tx.source:
            sources.add(tx.source)
    return sorted(list(sources))
