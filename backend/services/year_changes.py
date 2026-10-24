"""
What a write changes, tax year by tax year (2.0 spec 5.8): for each
transaction, Ledger Review's snapshot of its stored figures, its lot
disposals' Form 8949 boxes and column (b), what the year's report counts as
income or a rebate and as a gift, donation or lost coins, and its date and
tax year. The boxes and
dates are compared even when every dollar matches: a covered sale can turn
noncovered with the same gain (G to H), and two lots of the same cost and
term can swap; and a date a filed return prints (Form 8949's column (c),
the report's income and gifts) counts even when it stays in its year. A
row with no figures (dollars only) changes no tax year, wherever it moves.
"""

from typing import Any

from sqlalchemy.orm import Session, joinedload

from backend.constants import GIFT_LIKE_PURPOSES, INCOME_SOURCES, REBATE_SOURCE, normalized
from backend.models.transaction import BitcoinLot, LotDisposal, Transaction
from backend.services import review
from backend.services.account import AccountBook, account_book
from backend.services.reports.form_8949 import acquired_text, disposal_box
from backend.services.tax_time import format_tax_date, local_date

# Compared beside Ledger Review's figures: each disposal's box and column
# (b), in the order they were made, what the year's report counts as income
# or a rebate (the source and value: a deposit made income keeps its basis,
# so no stored figure shows it), and its gifts, donations and lost coins
# (the purpose and value: a donation's can be a charitable deduction; the
# build's lead, 2026-10-24)
COLUMNS = ("boxes", "acquired", "received", "given")
# And, for a row with figures, its tax year; and its date where a filed
# return prints it, even within its year (the build's lead, 2026-10-24): a
# disposal's date sold (Form 8949's column (c)), an income's, rebate's or
# gift's (the report). The dates acquired are its lots' and column (b).
DATES = ("date", "year")
RECEIVED = INCOME_SOURCES | {REBATE_SOURCE}
# A row's figures, any one of which set makes it count (a dollar row never does)
COUNTED = review.FIGURES + ("rows", "lots")
# What an added or deleted row's text names, when it has them
NAMED = review.FIGURES + review.ROW_TOTALS
CHANGES_WITH_THIS_SAVE = "Changes with this save."
PENDING = "Stored figures differ from what the current rules give."


def figures(db: Session, tz) -> dict[int, dict[str, Any]]:
    """Each transaction's stored figures (review.snapshot), its disposals'
    Form 8949 boxes and column (b), what it brings as income or a rebate
    and what it gives, donates or loses, its date and tax year (tax
    timezone), and whether it's dollars only."""
    found = review.snapshot(db, tz)
    book = account_book(db)
    for t in db.query(Transaction):
        dollars = t.type not in ("Buy", "Sell") and not any(book.is_btc(a) for a in (t.from_account_id, t.to_account_id))
        found[t.id].update(date=format_tax_date(t.timestamp, tz), year=local_date(t.timestamp, tz).year,
                           dollars=dollars, boxes=[], acquired=[], received=_received(t, book),
                           given=_given(t, book))
    for disposal in _disposals(db):
        row = found[disposal.transaction_id]
        row["boxes"].append(disposal_box(disposal, row["year"], tz, book))
        row["acquired"].append(acquired_text(disposal, tz))
    return found


def _received(t: Transaction, book: AccountBook) -> tuple[str, str | None] | None:
    """(its source, its value) for a deposit into a bitcoin account the
    report counts as income (Income, Interest, Reward) or as a rebate; None
    for any other row (reporting_core._build_income_summary, its rebates)."""
    source = normalized(t.source)
    if t.type != "Deposit" or source not in RECEIVED or not book.is_btc(t.to_account_id):
        return None
    return source.capitalize(), review.money(t.cost_basis_usd)


def _given(t: Transaction, book: AccountBook) -> tuple[str, str | None] | None:
    """(its purpose, its value) for bitcoin given, donated or lost (the
    report's gifts, donations and lost coins); None for any other row, a
    dollar withdrawal's leftover purpose or value included (#449)."""
    purpose = normalized(t.purpose)
    if t.type != "Withdrawal" or purpose not in GIFT_LIKE_PURPOSES or not book.is_btc(t.from_account_id):
        return None
    return purpose.capitalize(), review.money(t.fmv_usd)


def _disposals(db: Session) -> list[LotDisposal]:
    """Every lot disposal in the order made, with what its box is read from."""
    return (db.query(LotDisposal)
            .options(joinedload(LotDisposal.transaction),
                     joinedload(LotDisposal.lot).joinedload(BitcoinLot.created_transaction))
            .order_by(LotDisposal.transaction_id, LotDisposal.id)
            .all())


def moved(before: dict, after: dict) -> dict[int, dict[str, Any]]:
    """
    Per transaction, what moves from `before` to `after` (figures() each):
    {"diff": {key: (old, new)}, "years": its tax years on either side}. A
    row with figures on one side only is {"added": True} or {"deleted": True}.
    """
    changes = {}
    for tx_id in before.keys() | after.keys():
        old, new = before.get(tx_id), after.get(tx_id)
        diff = _row_diff(tx_id, old, new)
        if diff:
            changes[tx_id] = {"diff": diff, "years": sorted({row["year"] for row in (old, new) if row})}
    return changes


def _row_diff(tx_id: int, old: dict | None, new: dict | None) -> dict[str, Any]:
    if old is None or new is None:
        if not counts(new or old):
            return {}
        return {"added": True} if old is None else {"deleted": True}
    if not (counts(old) or counts(new)):
        return {}
    diff = review.differences({tx_id: old}, {tx_id: new}).get(tx_id, {})
    diff.update({key: (old[key], new[key]) for key in COLUMNS if old[key] != new[key]})
    if old["date"] != new["date"] and (_date_printed(old) or _date_printed(new)):
        diff["date"] = (old["date"], new["date"])
    if old["year"] != new["year"]:
        diff["year"] = (old["year"], new["year"])
    return diff


def _date_printed(row: dict) -> bool:
    """Whether a filed return prints the row's own date: it has lot
    disposals (column (c)), or the report lists it as income, a rebate or a
    gift. A deposit's date isn't: its lot's is (a date originally acquired
    being the lot's)."""
    return bool(row.get("rows")) or row["received"] is not None or row["given"] is not None


def counts(row: dict) -> bool:
    """Whether a row has figures of a tax year: a gain, a basis, proceeds,
    lot disposals or lots made. A dollar row has none, whatever value it
    carries (a dollar deposit's $0 basis from before 0.9.2)."""
    return not row["dollars"] and any(row.get(key) not in (None, []) for key in COUNTED)


def reaching(changes: dict, this_year: int) -> dict:
    """Those changes that touch a tax year before `this_year`."""
    return {tx_id: c for tx_id, c in changes.items() if c["years"][0] < this_year}


def years(changes: dict) -> list[int]:
    """The tax years the changes touch, oldest first."""
    return sorted({year for c in changes.values() for year in c["years"]})


def items(changes: dict, rows: dict, db: Session, tz, book: AccountBook, issue: str = CHANGES_WITH_THIS_SAVE,
          gone: dict[int, dict] | None = None) -> list[dict[str, Any]]:
    """
    Ledger Review's item for each change, in date order, with what moves in
    words and its tax years. `rows` are the figures the words take an added
    or deleted row's from; `gone` the items of rows `db` no longer has (a
    delete's, built before it). An added row's id is left out: the dry run's
    copy and the confirmed save may number it differently.
    """
    listed = []
    for tx_id, change in changes.items():
        tx = db.get(Transaction, tx_id)
        if tx is None and tx_id not in (gone or {}):
            continue
        item = review.row_item(tx, tz, book, issue, "") if tx is not None else dict(gone[tx_id], issue=issue)
        item["change"] = change_text(change["diff"], rows.get(tx_id))
        item["years"] = change["years"]
        if change["diff"].get("added"):
            item["id"] = None
        listed.append(item)
    return sorted(listed, key=lambda item: (item["date"], item["id"] or 0))


def change_text(diff: dict, row: dict | None = None) -> str:
    """What moves, in words: Ledger Review's for the figures, then the box,
    column (b), income and rebates, gifts, the date and the tax year; an
    added or deleted row's figures (`row`)."""
    if diff.get("added") or diff.get("deleted"):
        named = [f"{review.FIGURE_NAMES[k]} {review.money(row[k])}" for k in NAMED if (row or {}).get(k) is not None]
        return ("Added: " if diff.get("added") else "Deleted: ") + "; ".join(named) + "."
    money = {k: v for k, v in diff.items() if k not in (*COLUMNS, *DATES)}
    parts = [review.change_text(money).rstrip(".")] if money else []
    if "boxes" in diff:
        parts.append("Form 8949 box " + _moved_text(*diff["boxes"]))
    if "acquired" in diff:
        parts.append("Form 8949 column (b), date acquired " + _moved_text(*diff["acquired"]))
    if "received" in diff:
        parts.append("income and rebates: " + " -> ".join(_received_text(side) for side in diff["received"]))
    if "given" in diff:
        parts.append("gifts, donations and lost coins: " + " -> ".join(_received_text(side) for side in diff["given"]))
    if "date" in diff:
        parts.append(f"date {diff['date'][0]} -> {diff['date'][1]}")
    if "year" in diff:
        parts.append(f"tax year {diff['year'][0]} -> {diff['year'][1]}")
    text = "; ".join(parts) + "."
    return text[:1].upper() + text[1:] if not money else text


def _received_text(received: tuple[str, str | None] | None) -> str:
    """ "Income 1000.00", "Rebate 6.00", "Gift 500.00", or "none"."""
    return "none" if received is None else f"{received[0]} {received[1] or 'none'}"


def _moved_text(old: list[str], new: list[str]) -> str:
    """ "G -> H", each side's values once in their order, or all of them when
    only their order moves."""
    once_old, once_new = list(dict.fromkeys(old)), list(dict.fromkeys(new))
    if once_old == once_new:
        once_old, once_new = old, new
    return f"{', '.join(once_old) or 'none'} -> {', '.join(once_new) or 'none'}"
