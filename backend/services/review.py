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
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from backend.constants import ACCOUNT_EXCHANGE_BTC, ACCOUNT_WALLET, INCOME_SOURCES
from backend.models.transaction import Transaction
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
}


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
    checks = [
        {"key": key, "title": title, "action": action, "count": len(found[key]), "items": found[key]}
        for key, (title, action) in CHECKS.items()
    ]
    return {
        "read_only": True,
        "timezone": tz.key,
        "total": sum(c["count"] for c in checks),
        "checks": checks,
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
