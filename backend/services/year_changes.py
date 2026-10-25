"""
What a write changes, tax year by tax year (2.0 spec 5.8): for each
transaction, Ledger Review's snapshot of its stored figures, its lot
disposals' Form 8949 boxes and column (b) (a gift's, donation's or lost
coins' own: their holding period and date acquired, on no Form 8949),
what the year's report counts as income or a rebate and as a gift, donation
or lost coins, and its date and tax year. The boxes and
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
from backend.services.reports.form_8949 import acquired_text, disposal_box, on_form_8949
from backend.services.tax_time import format_tax_date, local_date

# Compared beside Ledger Review's figures: each disposal's box and column
# (b), in the order they were made; a gift's, donation's or lost coins' own,
# which no Form 8949 lists, by their holding period and date acquired
# instead (a donation's deduction turns on both, #736); what the year's
# report counts as income or a rebate (the source and value: a deposit made
# income keeps its basis, so no stored figure shows it), and its gifts,
# donations and lost coins (the purpose and value: a donation's can be a
# charitable deduction; the build's lead, 2026-10-24)
COLUMNS = ("boxes", "acquired", "given_terms", "given_acquired", "received", "given")
TERMS = {"SHORT": "short-term", "LONG": "long-term"}
# And, for a row with figures, its tax year; and its date where a filed
# return prints it, even within its year (the build's lead, 2026-10-24): a
# disposal's date sold (Form 8949's column (c)), an income's, rebate's or
# gift's, or a deposit's valued from the price (the report). The dates
# acquired are its lots' and column (b).
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
    Form 8949 boxes and column (b) (a gift's own coins' holding period and
    date acquired), what it brings as income or a rebate and what it gives,
    donates or loses, its date and tax year (tax timezone), and whether
    it's dollars only."""
    found = review.snapshot(db, tz)
    book = account_book(db)
    for t in db.query(Transaction):
        dollars = moves_only_dollars(t.type, (t.from_account_id, t.to_account_id), book)
        found[t.id].update(date=format_tax_date(t.timestamp, tz), year=local_date(t.timestamp, tz).year,
                           dollars=dollars, boxes=[], acquired=[], given_terms=[], given_acquired=[],
                           received=_received(t, book), given=_given(t, book), priced=_valued_from_the_price(t))
    for disposal in _disposals(db):
        row = found[disposal.transaction_id]
        if on_form_8949(disposal):
            row["boxes"].append(disposal_box(disposal, row["year"], tz, book))
            row["acquired"].append(acquired_text(disposal, tz))
        else:
            row["given_terms"].append(disposal.holding_period)
            row["given_acquired"].append(acquired_text(disposal, tz))
    return found


def moves_only_dollars(kind: Any, sides: tuple, book: AccountBook) -> bool:
    """A row of this type between these accounts has no figure of any tax
    year: no Buy or Sell, and no bitcoin account on either side (a write's
    too, before it's saved: past_years, past_year_writes)."""
    return getattr(kind, "value", kind) not in ("Buy", "Sell") and not any(book.is_btc(a) for a in sides)  # an enum's


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
    gift, or among its values from the BTC price (an inheritance's). Any
    other deposit's date isn't printed, but its lot's is (column (b)), a
    date originally acquired being the lot's."""
    return bool(row.get("rows")) or row["received"] is not None or row["given"] is not None or row["priced"]


def _valued_from_the_price(t: Transaction) -> bool:
    """A deposit whose value BitcoinTX filled from the price: the report's
    table of values from the BTC price lists it, dated."""
    return t.type == "Deposit" and bool(t.cost_basis_from_price) and t.cost_basis_usd is not None


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
    """What moves, in words: Ledger Review's for the figures, then a gift's
    own coins' holding period and date acquired, the box and column (b) (a
    gift's network fee's, the only Form 8949 rows it has), income and
    rebates, gifts, the date and the tax year; an added or deleted row's
    figures (`row`: its figures as the save leaves them)."""
    if diff.get("added") or diff.get("deleted"):
        named = [f"{review.FIGURE_NAMES[k]} {review.money(row[k])}" for k in NAMED if (row or {}).get(k) is not None]
        return ("Added: " if diff.get("added") else "Deleted: ") + "; ".join(named) + "."
    money = {k: v for k, v in diff.items() if k not in (*COLUMNS, *DATES)}
    parts = [review.change_text(money).rstrip(".")] if money else []
    if "given_terms" in diff:
        parts.append("held " + _moved_text(*([TERMS.get(term, "unknown") for term in side]
                                             for side in diff["given_terms"])))
    if "given_acquired" in diff:
        parts.append("date acquired " + _moved_text(*diff["given_acquired"]))
    form = "network fee's Form 8949" if (row or {}).get("given") else "Form 8949"
    if "boxes" in diff:
        parts.append(f"{form} box " + _moved_text(*diff["boxes"]))
    if "acquired" in diff:
        parts.append(f"{form} column (b), date acquired " + _moved_text(*diff["acquired"]))
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
