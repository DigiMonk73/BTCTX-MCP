"""
The complete tax report's data for one tax year: holdings at its start and
end, capital gains (the Form 8949 disposals, spending included), income and gifts.
complete_tax_report.py turns it into the PDF.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from collections.abc import Iterator
from decimal import Decimal, ROUND_HALF_DOWN
import logging
import sqlite3

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.models.transaction import (
    Transaction,
    BitcoinLot,
    LotDisposal,
)
from backend.models.account import Account
from backend.services.tax_time import get_tax_timezone, get_tax_timezone_name, tax_year_bounds
from backend.services.reports.form_8949 import (
    SCHEDULE_D_LINE_FOR_BOX, build_form_8949_and_schedule_d, disposal_box, taxable_disposals,
)

from backend.services.transaction import (
    recalculate_all_transactions,
    get_btc_price,
)

logger = logging.getLogger(__name__)


def _held_value_price(db: Session, when: datetime, day: str):
    """
    The BTC price that values holdings on `day`, or None when none is stored
    or can be fetched (price lookups off, or no history for that day). The
    report then shows those values as not priced, never $0 or an error.
    """
    try:
        return Decimal(get_btc_price(when, db)).quantize(Decimal("0.01"))
    except Exception as exc:
        logger.warning("No BTC price for %s: %s", day, getattr(exc, "detail", exc))
        return None


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


def generate_report_data(db: Session, year: int) -> dict[str, Any]:
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

    # 1) Gather beginning-of-year balances (snapshot)
    start_dt, end_dt = tax_year_bounds(year, get_tax_timezone(db))
    with _scratch_copy(db) as scratch:
        start_of_year_data = _build_start_of_year_balances(scratch, year)

    # 1b) End-of-year snapshot: replay only transactions before the
    #     year boundary, so later activity doesn't leak into 12/31 holdings
    with _scratch_copy(db) as scratch:
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
    gifts_lost        = _build_gifts_donations_lost(txns)
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
        "gifts_donations_lost": gifts_lost,
        "data_sources": data_sources_list,
    }
    return result


def _build_start_of_year_balances(db: Session, year: int) -> list[dict[str, Any]]:
    """
    BTC held when the tax year begins, valued at the Jan 1 BTC price. Replays
    only the transactions before that instant, as the year-end snapshot does,
    so it always equals the previous year's end-of-year holdings. Runs on a
    scratch copy (see generate_report_data).
    """
    from_dt, _ = tax_year_bounds(year, get_tax_timezone(db))
    recalculate_all_transactions(db, until=from_dt)
    open_lots = db.query(BitcoinLot).filter(BitcoinLot.remaining_btc > 0).all()

    # The Jan 1 price, only if something was held (None: not priced)
    january1_price = _held_value_price(db, from_dt, f"{year}-01-01") if open_lots else None

    results = []
    for lot in open_lots:
        # fraction leftover in the partial-lot
        fraction = Decimal("1.0")
        if lot.total_btc and lot.total_btc > 0:
            fraction = lot.remaining_btc / lot.total_btc

        # cost basis leftover for that fraction
        partial_cost = (lot.cost_basis_usd * fraction).quantize(Decimal("0.01"), ROUND_HALF_DOWN)
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
    BTC still held at the end of `year`, valued at the Dec 31 BTC price.
    Expects the lots to be a year-end snapshot (see generate_report_data).
    """
    open_lots = (
        db.query(BitcoinLot)
        .filter(BitcoinLot.remaining_btc > 0)
        .order_by(BitcoinLot.acquired_date.asc())
        .all()
    )
    account_names = {a.id: a.name for a in db.query(Account)}

    dec31 = datetime(year, 12, 31, 12, tzinfo=timezone.utc)
    eoy_price = _held_value_price(db, dec31, f"{year}-12-31") if open_lots else None
    if eoy_price is not None:
        price_note = f"@ ${eoy_price:,} per BTC on {year}-12-31"
    else:
        price_note = f"No BTC price for {year}-12-31: not priced"

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
            "value": None if cur_value is None else float(cur_value),  # None: no Dec 31 price
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
        "date_acquired": lot.acquired_date.isoformat() if lot and lot.acquired_date else "",
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


def _build_gifts_donations_lost(txns: list[Transaction]) -> list[dict[str, Any]]:
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
