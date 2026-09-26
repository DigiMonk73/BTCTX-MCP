"""
backend/services/review.py

The Ledger review: a read-only list of saved transactions worth a second
look after the v0.9.2 fixes. Nothing here changes a row; each item says
what looks odd and what would change if the owner acts on it.

Shown by GET /api/review, `python -m backend.cli review`, the MCP tool
`review_ledger` and the Ledger review panel in Settings.

Checks:
- zero_proceeds_spend (F1): a Spent withdrawal saved with $0 proceeds.
  Before v0.9.2 the form sent 0 for a blank, so a spend meant to be valued
  at the day's price was saved at $0, a loss of its whole basis. A real $0
  looks the same; only the owner can tell.
- lost_with_loss (F2): a Lost withdrawal whose stored gain isn't $0. Lost
  now counts like a gift ($0 gain); Recalculate Ledger removes the old loss.
- deposit_without_basis (F15): a BTC deposit that isn't income (source
  MyBTC, Gift, N/A...) with a $0 or blank cost basis. Its whole value
  becomes gain when it's sold. New deposits must state a basis (0 allowed).
- fee_value_off (F14): a transfer's BTC fee whose stored USD value is more
  than 5% away from fee x that day's price: most likely valued at the live
  price when the day's lookup failed. apply_fee_prices() fixes the ones the
  owner picks (login only), then recalculates.
- income_value_off (F42): an income deposit whose basis is more than 5%
  away from amount x that day's price. Before v0.9.2 a lookup for a date
  more than about two years back could return another day's price. Only
  the owner knows whether a typed value is right, so nothing fixes these.

The price checks read the local price history (and fill it from the
network if a day is missing); a day with no price is skipped and counted.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from backend.constants import ACCOUNT_EXCHANGE_BTC, ACCOUNT_WALLET, INCOME_SOURCES
from backend.models.transaction import Transaction
from backend.services import price_history
from backend.services.tax_time import as_utc, get_tax_timezone

BTC_ACCOUNTS = (ACCOUNT_WALLET, ACCOUNT_EXCHANGE_BTC)

# key -> (title, what the owner can do)
CHECKS: Dict[str, tuple] = {
    "zero_proceeds_spend": (
        "Spent withdrawals saved with $0 proceeds",
        "If you didn't really get $0, edit the proceeds (or clear them to use the day's price).",
    ),
    "lost_with_loss": (
        "Lost withdrawals still carrying a loss",
        "Recalculate Ledger sets their gain to $0 (Lost now counts like a gift).",
    ),
    "deposit_without_basis": (
        "BTC deposits (not income) with a $0 or blank cost basis",
        "If you know what the BTC cost, edit the deposit's cost basis.",
    ),
    "fee_value_off": (
        "Transfer fees valued far from that day's price (probably at the live price)",
        "Fix these (Settings, or `python -m backend.cli review --fix-fee-prices`) sets each to the day's "
        "price and recalculates.",
    ),
    "income_value_off": (
        "Income deposits valued far from that day's price",
        "If the value didn't come from your records, edit the deposit's cost basis "
        "(or clear it to use the day's price).",
    ),
}

TOLERANCE = Decimal("0.05")
CENT = Decimal("0.01")


def _money(value) -> str | None:
    return None if value is None else str(Decimal(value).quantize(Decimal("0.01")))


def _item(t: Transaction, tz, issue: str, change: str) -> Dict[str, Any]:
    return {
        "id": t.id,
        "date": as_utc(t.timestamp).astimezone(tz).strftime("%Y-%m-%d %H:%M"),
        "type": t.type,
        "purpose": t.purpose,
        "source": t.source,
        "amount": str(t.amount),
        "realized_gain_usd": _money(t.realized_gain_usd),
        "issue": issue,
        "change": change,
    }


def _day_price(db: Session, t: Transaction, missing: List[int]):
    try:
        return price_history.daily_price(db, t.timestamp)
    except Exception:
        missing.append(t.id)
        return None


def _off(stored, expected: Decimal) -> bool:
    return expected > 0 and abs(Decimal(stored) - expected) > expected * TOLERANCE


def fee_price_changes(db: Session, ids=None) -> List[Dict[str, Any]]:
    """Transfers whose stored (not typed) fee value is off the day's price: {id, old, new}."""
    q = db.query(Transaction).filter(Transaction.type == "Transfer", Transaction.fee_usd.isnot(None),
                                     Transaction.fee_usd_manual.is_(False))
    if ids is not None:
        q = q.filter(Transaction.id.in_(list(ids)))
    changes = []
    for t in q.order_by(Transaction.timestamp, Transaction.id).all():
        if (t.fee_currency or "").upper() != "BTC" or not t.fee_amount:
            continue
        try:
            price = price_history.daily_price(db, t.timestamp)
        except Exception:
            continue
        expected = (price * Decimal(t.fee_amount)).quantize(CENT)
        if _off(t.fee_usd, expected):
            changes.append({"id": t.id, "old": Decimal(t.fee_usd), "new": expected, "price": price})
    return changes


def apply_fee_prices(db: Session, ids) -> List[Dict[str, Any]]:
    """
    Set the picked transfers' fee values to the day's price and recalculate.
    Only rows the review flags change; typed values never do. Commits.
    """
    from backend.services.transaction import recalculate_all_transactions

    changes = fee_price_changes(db, ids)
    for change in changes:
        tx = db.get(Transaction, change["id"])
        tx.fee_usd = change["new"]
    if changes:
        recalculate_all_transactions(db)
    db.commit()
    return changes


def _is_zero_or_blank(value) -> bool:
    return value is None or Decimal(value) == 0


def build_review(db: Session) -> Dict[str, Any]:
    """Every check's items, in date order. Read-only."""
    tz = get_tax_timezone(db)
    rows: List[Transaction] = (
        db.query(Transaction)
        .filter(Transaction.type.in_(("Withdrawal", "Deposit")))
        .order_by(Transaction.timestamp, Transaction.id)
        .all()
    )
    found: Dict[str, List[Dict[str, Any]]] = {key: [] for key in CHECKS}
    for t in rows:
        purpose = (t.purpose or "").lower()
        if t.type == "Withdrawal" and purpose == "spent" and t.gross_proceeds_usd is not None \
                and Decimal(t.gross_proceeds_usd) == 0:
            found["zero_proceeds_spend"].append(_item(
                t, tz, "Saved with $0 proceeds: its whole basis shows as a loss.",
                "Proceeds you enter replace $0; the gain changes by the same amount.",
            ))
        if t.type == "Withdrawal" and purpose == "lost" and not (
            t.realized_gain_usd is not None and Decimal(t.realized_gain_usd) == 0
        ):
            found["lost_with_loss"].append(_item(
                t, tz, f"Stored gain {_money(t.realized_gain_usd) or 'not calculated'}.",
                "Gain becomes $0.00 after Recalculate Ledger.",
            ))
        if t.type == "Deposit" and t.to_account_id in BTC_ACCOUNTS \
                and (t.source or "").lower() not in INCOME_SOURCES and _is_zero_or_blank(t.cost_basis_usd):
            found["deposit_without_basis"].append(_item(
                t, tz, "Cost basis " + ("blank" if t.cost_basis_usd is None else "$0.00") + ".",
                "A basis you enter lowers the gain when this BTC is sold by the same amount.",
            ))
    missing: List[int] = []
    for change in fee_price_changes(db):
        t = db.get(Transaction, change["id"])
        found["fee_value_off"].append(_item(
            t, tz, f"Fee {t.fee_amount} BTC stored as ${_money(change['old'])}; at that day's price "
                   f"(${_money(change['price'])}) it is ${_money(change['new'])}.",
            f"Fee value ${_money(change['old'])} -> ${_money(change['new'])}; the fee's gain changes by "
            f"${_money(change['new'] - change['old'])}.",
        ))
    for t in rows:
        if not (t.type == "Deposit" and t.to_account_id in BTC_ACCOUNTS
                and (t.source or "").lower() in INCOME_SOURCES and t.cost_basis_usd):
            continue
        price = _day_price(db, t, missing)
        if price is None:
            continue
        expected = (price * Decimal(t.amount)).quantize(CENT)
        if _off(t.cost_basis_usd, expected):
            found["income_value_off"].append(_item(
                t, tz, f"Basis ${_money(t.cost_basis_usd)}; at that day's price (${_money(price)}) "
                       f"it is ${_money(expected)}.",
                f"Basis (and the income reported) ${_money(t.cost_basis_usd)} -> ${_money(expected)} "
                "if you change it.",
            ))

    checks = [
        {"key": key, "title": title, "action": action, "count": len(found[key]), "items": found[key]}
        for key, (title, action) in CHECKS.items()
    ]
    return {
        "read_only": True,
        "timezone": tz.key,
        "total": sum(c["count"] for c in checks),
        "checks": checks,
        "no_price_for": missing,
    }


def format_text(review: Dict[str, Any]) -> str:
    """Plain text for the CLI."""
    lines = [f"Ledger review (read-only; dates in {review['timezone']})"]
    for check in review["checks"]:
        lines.append(f"{check['title']}: {check['count']}")
        for item in check["items"]:
            detail = item["source"] if item["type"] == "Deposit" else item["purpose"]
            lines.append(f"  #{item['id']}  {item['date']}  {item['type']} ({detail})  {item['amount']} BTC  "
                         f"{item['issue']}")
        if check["items"]:
            lines.append(f"  -> {check['action']}")
    return "\n".join(lines) + "\n"
