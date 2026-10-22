"""What a write changes, tax year by tax year (5.8): Ledger Review's stored
figures, each disposal's Form 8949 box and date acquired, and the row's tax
year. Dollars moved alone change no tax year.
"""

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from backend.models.transaction import LotDisposal, Transaction
from backend.services.reports.form_8949 import acquired_text, disposal_box
from backend.services.review import FIGURES, _change_text, _differences, _item, _snapshot
from backend.services.tax_time import local_date

ISSUE = "Changes with this save."


def figures(db: Session, tz) -> dict[int, dict[str, Any]]:
    # _snapshot(db, tz), each row also "year" (local_date(timestamp, tz).year) and
    # "boxes": [[disposal_box(d, year, tz), acquired_text(d, tz)], ...] in LotDisposal id order
    found = _snapshot(db, tz)
    years = {tx.id: local_date(tx.timestamp, tz).year for tx in db.query(Transaction)}
    boxes: dict[int, list[list[str]]] = {}
    for disposal in db.query(LotDisposal).order_by(LotDisposal.id):
        year = years[disposal.transaction_id]
        pair = [disposal_box(disposal, year, tz), acquired_text(disposal, tz)]
        boxes.setdefault(disposal.transaction_id, []).append(pair)
    for tx_id, row in found.items():
        row["year"] = years[tx_id]
        row["boxes"] = boxes.get(tx_id, [])
    return found


def listed(db: Session, tz) -> dict[int, dict[str, Any]]:  # {t.id: _item(t, tz, ISSUE, "")}
    return {t.id: _item(t, tz, ISSUE, "") for t in db.query(Transaction)}


def moved(before: dict, after: dict) -> dict[int, dict[str, Any]]:
    changes: dict[int, dict[str, Any]] = {}
    for tx_id in before.keys() | after.keys():
        old = before.get(tx_id)
        new = after.get(tx_id)
        if old is None or new is None:
            row = new if old is None else old
            if _has_figures(row):
                changes[tx_id] = {"added": True} if old is None else {"deleted": True}
            continue
        diff = _differences({tx_id: old}, {tx_id: new}).get(tx_id, {})
        columns = {
            "boxes": (_column(old.get("boxes"), 0), _column(new.get("boxes"), 0)),
            "acquired": (_column(old.get("boxes"), 1), _column(new.get("boxes"), 1)),
        }
        # A year moves only when a figure does: dollars re-dated change no tax year.
        if any(_has_figures(row) for row in (old, new)):
            columns["year"] = (old.get("year"), new.get("year"))
        diff.update({key: pair for key, pair in columns.items() if pair[0] != pair[1]})
        if diff:
            changes[tx_id] = diff
    return changes


def earlier_year_items(
    rows: dict, moved_rows: dict, before: dict, after: dict, this_year: int
) -> list[dict]:
    items = []
    for tx_id, diff in moved_rows.items():
        years = sorted({
            side["year"]
            for side in (before.get(tx_id), after.get(tx_id))
            if side is not None and "year" in side
        })
        if years and min(years) < this_year:
            items.append({**rows[tx_id], "years": years, "change": change_text(diff)})
    return sorted(items, key=lambda item: (item["date"], item["id"]))


# Each moved row's line, as Ledger Review gives its own
def change_text(diff: dict) -> str:
    if "added" in diff:
        return "Added."
    if "deleted" in diff:
        return "Deleted."
    money = {key: value for key, value in diff.items() if key not in ("boxes", "acquired", "year")}
    parts: list[str] = [_change_text(money)] if money else []
    if "boxes" in diff:
        old, new = diff["boxes"]
        parts.append(f"Form 8949 box {old} → {new}.")
    if "acquired" in diff:
        old, new = diff["acquired"]
        parts.append(f"Form 8949 date acquired {old} → {new}.")
    if "year" in diff:
        old, new = diff["year"]
        parts.append(f"Tax year {old} → {new}.")
    return " ".join(parts)


def _has_figures(row: dict) -> bool:  # boxes, or "lots", or any FIGURES value
    if row.get("boxes") or row.get("lots"):
        return True
    return any(value is not None and Decimal(value) != 0 for value in (row.get(name) for name in FIGURES))


def _column(boxes: list, column: int) -> str:  # distinct values in order, ", "-joined, or "none"
    seen: list[str] = []
    for pair in boxes or []:
        value = pair[column]
        if value not in seen:
            seen.append(value)
    return ", ".join(seen) if seen else "none"
