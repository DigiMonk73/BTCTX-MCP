"""
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
- deposit_without_basis (F15): a BTC deposit that isn't income or a rebate
  (source MyBTC, Gift, Inherited, N/A...) with a $0 or blank cost basis. Its whole value
  becomes gain when it's sold. New deposits must state a basis (0 allowed).
- day_priced_values (#144): values BitcoinTX priced at the day's price
  before hourly prices that the price of their hour would change, by tax
  year (services/hourly_review.py); the owner applies them by item or by
  year (login only), after a backup copy. It took over the fee check (F14:
  a transfer's fee valued far from the day's price, most likely at the live
  price): where there's no hourly price, a value is compared with the day's.
- original_date_missing (#91, a reminder since #128): a My BTC or Gift
  deposit into a BTC account with no date originally acquired: its holding
  period starts at the deposit. It isn't an error (no sale counts as
  long-term too early, though a date can also change which coins FIFO
  sells first), and only the owner knows when the coins were acquired, so
  nothing fills it. After the 1.2.6 upgrade every older such deposit is
  listed, so it is a reminder: one explanation for the group, listed after
  the checks and left out of `total`.
- inherited_without_date (#154): an Inherited deposit into a BTC account
  with no date of death. New ones must have it; a deposit saved before
  1.1.0, when the source was free text, may say "inherited" without one. Its
  coins follow the inheritance rules (long-term, INHERITED in column (b))
  from the next recalculation, but it is valued and sorted by the deposit's
  date, and an edit asks for the date of death.
- income_without_value (#77): an income or rebate deposit (#98) with a $0
  or blank basis: for income, no income is reported for it; either way its
  whole value becomes gain when it's sold. The rules forbid it (a blank is
  valued at the hour's price); older versions and some edits (#76) left such
  rows. Shown with that hour's value (else that day's) when the price is known.
- gift_without_value (#255): a Gift, Donation or Lost withdrawal with a
  blank or $0 value. From 1.2.9 a blank one is valued at that hour's price
  when saved; older versions saved it blank (the report says "not given"),
  and an edit in them could save $0. A donation's deduction starts from
  it (for coins held a year or less, at most their basis), a gift's counts
  toward the gift-tax limit. Shown with that hour's value
  (else that day's) when the price is known.
- income_value_off (F42): an income or rebate deposit whose typed basis is
  more than 5% away from amount x that hour's price (else that day's).
  Before v0.9.2 a lookup for a date more than about two years back could
  return another day's price. Only the owner knows whether a typed value is
  right, so nothing fixes these; a value from a price is day_priced_values'.

- recalc_changes: every transaction whose stored figures Recalculate Ledger
  would change (proceeds, basis, gain), old -> new. Found by running the
  recalculation and rolling it back. After an upgrade this is where the
  fixes that change existing figures show up (Lost at $0 gain, a
  withdrawal's network fee as its own disposal), before anything moves.
  Any add, edit or delete recalculates everything too.

The price checks read the local price history (and fill it from the
network if a day is missing; an hourly year not downloaded yet isn't
waited for: the day's price stands in). A day with no price is counted in
no_price_for: F42 passes over its row, income_without_value lists it
without the value. Any other failure of the lookup is an error.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.constants import BTC_ACCOUNTS, GIFT_LIKE_PURPOSES, INCOME_SOURCES, INHERITED_SOURCE, ORIGINAL_DATE_SOURCES, VALUED_AT_RECEIPT
from backend.models.transaction import LotDisposal, Transaction
from backend.services import hourly_prices, price_history
from backend.services.hourly_review import hourly_changes
from backend.services.calculation import btc_text
from backend.services.tax_time import as_utc, get_tax_timezone


# key -> (title, what the owner can do)
CHECKS: dict[str, tuple] = {
    "recalc_changes": (
        "Figures that Recalculate Ledger would change",
        "Back up first, then run Recalculate Ledger (Settings) when you agree. Adding, editing or "
        "deleting any transaction also recalculates everything.",
    ),
    "day_priced_values": (
        "Values priced at the day's price that the hour would change",
        "Tick the ones to change, or a whole year, and apply them (Settings, or `python -m backend.cli review "
        "--apply-hourly-prices YEAR`): a backup copy is made first, then each is priced at the hour and the "
        "ledger is recalculated. A value you typed is never listed.",
    ),
    "zero_proceeds_spend": (
        "Spent withdrawals saved with $0 proceeds",
        "If you didn't really get $0, edit the proceeds (or clear them to use that hour's price).",
    ),
    "lost_with_loss": (
        "Lost withdrawals still carrying a loss",
        "Recalculate Ledger sets their gain to $0 (Lost now counts like a gift).",
    ),
    "deposit_without_basis": (
        "BTC deposits (not income or a rebate) with a $0 or blank cost basis",
        "If you know what the BTC cost (for a gift, the giver's cost basis), edit the deposit's cost basis.",
    ),
    "inherited_without_date": (
        "Inherited deposits without a date of death",
        "Edit each one: enter the date of death, and check the Cost Basis is the value that day. Until then it "
        "is dated by the deposit. Its coins are long-term, with INHERITED on Form 8949, from the next "
        "recalculation: Recalculate Ledger (Settings), or editing it or any other transaction.",
    ),
    "income_without_value": (
        "Income and rebate deposits with a $0 or blank value",
        "Edit each one: clear its Cost Basis (USD) to use that hour's price, or type its value when you "
        "received it.",
    ),
    "gift_without_value": (
        "Gifts, donations and lost coins with a $0 or blank value",
        "Edit each one: clear its FMV (USD) to use that hour's price, or type its value when it left.",
    ),
    "income_value_off": (
        "Income and rebate values you typed, far from that hour's price",
        "If the value didn't come from your records, edit the deposit's cost basis "
        "(or clear it to use that hour's price).",
    ),
    "original_date_missing": (
        "Reminder: My BTC and Gift deposits counted from their deposit date",
        "To change one, edit the deposit: its Source, or its Date originally acquired.",
    ),
}

# Reminders: these rows aren't errors, so they come after the checks,
# aren't counted in `total`, and carry one explanation for the whole group
# instead of the same sentences on every row.
REMINDERS: dict[str, tuple[str, ...]] = {
    "original_date_missing": (
        "If these are really income, interest, rewards or rebates, change their Source instead: then no "
        "date is needed. Income, Interest and Reward (mining, staking, bonuses) are income; Rebate (card or "
        "shopping sats-back) isn't. Then check the Cost Basis is their value on the day received (clear it "
        "to use that hour's price): for income, that value is also the income reported. Before 1.2.6 there "
        "was no Rebate source, so card sats-back may have been saved as My BTC to keep it out of income.",
        "Otherwise these aren't errors. These deposits have two dates: the deposit date, when the "
        "coins reached you, and the date originally acquired, when they were first owned. The second sets "
        "the holding period, which coins are sold first, and Form 8949's date acquired.",
        "Which date: for My BTC (your own coins, moved in from somewhere BitcoinTX doesn't track), the day "
        "you bought or earned them there; for a Gift, the day the giver got them, along with the giver's "
        "cost basis, so a gift sold the day it arrives is long-term if the giver held it more than a year "
        "(BitcoinTX doesn't apply the rule for a gift worth less that day than the giver paid, IRC §1015: "
        "such coins sold at a loss need adjusting by hand). "
        "Never the day an exchange got the coins it sold you. Buys, income, interest, rewards and rebates "
        "use their own date, so they have no such field.",
        "Left blank, the deposit date is used, so no sale counts as long-term too early: for the holding "
        "period, the cautious choice. But the date also decides which coins are sold first, so adding one "
        "can change a year's gain, up or down. Coins kept more than a year after the deposit are long-term "
        "either way. Enter a date only if you can back it up (a receipt, a statement, a message from the "
        "giver).",
    ),
}

# The deposits whose value is checked against the day's price: income and
# rebates. An inheritance's value can rightly differ from it (the estate's
# Form 8971, or its alternate valuation date six months on, #154), so it is
# checked like My BTC and Gift: only for a $0 or blank basis.
DAY_VALUED = VALUED_AT_RECEIPT - {INHERITED_SOURCE}
# Deposits with a date originally acquired the reminder is about: an
# Inherited one must have its date of death (#154), so it's never missing
DATED_FROM_DEPOSIT = ORIGINAL_DATE_SOURCES - {INHERITED_SOURCE}

# Explanations shown once for a whole group: the reminders', and the hourly check's
EXPLANATIONS: dict[str, tuple[str, ...]] = {
    **REMINDERS,
    "day_priced_values": (
        "Before this version, a value BitcoinTX filled in itself (income or a rebate left blank, a spend's "
        "proceeds left blank, a network fee's value) used that day's midnight (UTC) price. IRS rules value "
        "bitcoin at the date and time of each transaction (Treas. Reg. §1.1001-7(b)(3)); the price when "
        "the transaction's hour began is closer. Nothing changes until you apply it.",
        "A year you haven't filed yet: using the hour is recommended. A year you've already filed: changing "
        "it changes figures on a filed return (for income, the income reported and that coin's basis), and "
        "whether to amend is a question for a tax professional; leaving it as filed is recommended.",
        "Changes under $1.00 aren't listed one by one; each year's totals include them, and applying a "
        "year applies them too. Where there's no hourly price (before 2013), the day's price is used: a "
        "value listed then was not at it (an older version could value a fee at the live price).",
    ),
}
LISTED_FROM = Decimal("1.00")
# What each priced value is called in an item (income: also the income reported)
VALUE_NAMES = {"gross_proceeds_usd": "Proceeds", "fmv_usd": "Value", "fee_usd": "Fee value"}

TOLERANCE = Decimal("0.05")
CENT = Decimal("0.01")


def _money(value) -> str | None:
    return None if value is None else str(Decimal(value).quantize(Decimal("0.01")))


def _item(t: Transaction, tz, issue: str, change: str) -> dict[str, Any]:
    return {
        "id": t.id,
        "date": as_utc(t.timestamp).astimezone(tz).strftime("%Y-%m-%d %H:%M"),
        "type": t.type,
        "purpose": t.purpose,
        "source": t.source,
        "amount": btc_text(t.amount),
        "realized_gain_usd": _money(t.realized_gain_usd),
        "issue": issue,
        "change": change,
    }


def _market_price(db: Session, t: Transaction, missing: list[int]):
    """(price, "that hour's" or "that day's"): its hour's price, else its
    day's; None (and the id in `missing`) when there is none. Any other
    failure is raised: a shorter list would look like nothing to fix."""
    found = hourly_prices.hourly_price(db, t.timestamp, wait=False)
    if found is not None:
        return found[0], "that hour's"
    try:
        return price_history.daily_price(db, t.timestamp), "that day's"
    except HTTPException:
        missing.append(t.id)
        return None


def _off(stored, expected: Decimal) -> bool:
    return expected > 0 and abs(Decimal(stored) - expected) > expected * TOLERANCE


def _is_zero_or_blank(value) -> bool:
    return value is None or Decimal(value) == 0


FIGURES = ("proceeds_usd", "cost_basis_usd", "realized_gain_usd")


def simulate_recalculation(db: Session):
    """
    What Recalculate Ledger would change: {id: {field: (old, new)}}, or an
    error message. Runs it and rolls everything back (the session must have
    nothing else pending).
    """
    from backend.services.transaction import recalculate_all_transactions

    def snapshot():
        figures = {t.id: {f: getattr(t, f) for f in FIGURES} for t in db.query(Transaction).all()}
        for tx_id, gain in db.query(LotDisposal.transaction_id, func.sum(LotDisposal.realized_gain_usd)) \
                .group_by(LotDisposal.transaction_id):
            if tx_id in figures:
                figures[tx_id]["taxable_gain"] = gain
        return figures

    before = snapshot()
    try:
        recalculate_all_transactions(db)
        db.flush()
        after = snapshot()
    except Exception as exc:  # e.g. a missing price: say so, change nothing
        db.rollback()
        return None, str(getattr(exc, "detail", exc))
    db.rollback()

    def same(a, b):
        return (a is None and b is None) or (a is not None and b is not None and Decimal(a) == Decimal(b))

    changes = {}
    for tx_id, old in before.items():
        new = after.get(tx_id, {})
        diff = {f: (old.get(f), new.get(f)) for f in FIGURES + ("taxable_gain",)
                if not same(old.get(f), new.get(f))}
        if diff:
            changes[tx_id] = diff
    return changes, None


def build_review(db: Session) -> dict[str, Any]:
    """Every check's items, in date order. Changes no transaction."""
    tz = get_tax_timezone(db)
    moved, recalc_error = simulate_recalculation(db)
    rows: list[Transaction] = (
        db.query(Transaction)
        .filter(Transaction.type.in_(("Withdrawal", "Deposit")))
        .order_by(Transaction.timestamp, Transaction.id)
        .all()
    )
    found: dict[str, list[dict[str, Any]]] = {key: [] for key in CHECKS}
    for t in rows:
        for key, item in _row_issues(t, tz):
            found[key].append(item)
    found["recalc_changes"] = _recalc_items(db, moved or {}, tz)
    found["day_priced_values"], years = _day_priced_items(db, tz)
    missing: list[int] = []
    found["income_without_value"] = _income_without_value_items(db, rows, tz, missing)
    found["gift_without_value"] = _gift_without_value_items(db, rows, tz, missing)
    found["income_value_off"] = _income_value_items(db, rows, tz, missing)

    checks = [
        {"key": key, "kind": "reminder" if key in REMINDERS else "check", "title": title, "action": action,
         "explanation": list(EXPLANATIONS.get(key, ())), "count": len(found[key]), "items": found[key]}
        for key, (title, action) in CHECKS.items()
    ]
    # Counted: every transaction the hour would change, the unlisted ones under $1.00 too
    hourly = next(c for c in checks if c["key"] == "day_priced_values")
    hourly.update(years=years, count=sum(y["count"] for y in years))
    return {
        "read_only": True,
        "timezone": tz.key,
        "total": sum(c["count"] for c in checks if c["kind"] == "check"),
        "reminders": sum(c["count"] for c in checks if c["kind"] == "reminder"),
        "checks": checks,
        "no_price_for": missing,
        "recalc_error": recalc_error,
    }


def _row_issues(t: Transaction, tz):
    """(check, item) for each check a withdrawal or deposit fails on its own."""
    purpose = (t.purpose or "").lower()
    if t.type == "Withdrawal" and purpose == "spent" and t.gross_proceeds_usd is not None \
            and Decimal(t.gross_proceeds_usd) == 0:
        yield "zero_proceeds_spend", _item(
            t, tz, "Saved with $0 proceeds: its whole basis shows as a loss.",
            "Proceeds you enter replace $0; the gain changes by the same amount.",
        )
    if t.type == "Withdrawal" and purpose == "lost" and not (
        t.realized_gain_usd is not None and Decimal(t.realized_gain_usd) == 0
    ):
        yield "lost_with_loss", _item(
            t, tz, f"Stored gain {_money(t.realized_gain_usd) or 'not calculated'}.",
            "Gain becomes $0.00 after Recalculate Ledger.",
        )
    if t.type == "Deposit" and t.to_account_id in BTC_ACCOUNTS \
            and (t.source or "").lower() in DATED_FROM_DEPOSIT and t.acquired_at is None:
        yield "original_date_missing", _item(t, tz, "No date originally acquired.", "")
    if t.type == "Deposit" and t.to_account_id in BTC_ACCOUNTS \
            and (t.source or "").lower() == INHERITED_SOURCE and t.acquired_at is None:
        yield "inherited_without_date", _item(t, tz, "No date of death.", "")
    if t.type == "Deposit" and t.to_account_id in BTC_ACCOUNTS \
            and (t.source or "").lower() not in DAY_VALUED and _is_zero_or_blank(t.cost_basis_usd):
        yield "deposit_without_basis", _item(
            t, tz, "Cost basis " + ("blank" if t.cost_basis_usd is None else "$0.00") + ".",
            "A basis you enter lowers the gain when this BTC is sold by the same amount.",
        )


# How the recalculation items name the figures.
FIGURE_NAMES = {"proceeds_usd": "proceeds", "cost_basis_usd": "basis", "realized_gain_usd": "gain",
                "taxable_gain": "taxable gain incl. network fees"}


def _recalc_items(db: Session, moved: dict, tz) -> list[dict[str, Any]]:
    """The transactions whose figures Recalculate Ledger would change, in date order."""
    items = []
    for tx_id, diff in sorted(moved.items(), key=lambda kv: (db.get(Transaction, kv[0]).timestamp, kv[0])):
        t = db.get(Transaction, tx_id)
        parts = [f"{FIGURE_NAMES[f]} {_money(old) or 'none'} -> {_money(new) or 'none'}"
                 for f, (old, new) in diff.items()]
        item = _item(t, tz, "Stored figures differ from what the current rules give.", "; ".join(parts) + ".")
        item["changes"] = {f: [_money(old), _money(new)] for f, (old, new) in diff.items()}
        items.append(item)
    return items


def _day_priced_items(db: Session, tz) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The values priced at the day that the hour would change: the items
    (a change of $1.00 or more) and each tax year's totals (all of them)."""
    items, years = [], {}
    for change in hourly_changes(db):
        t = db.get(Transaction, change["id"])
        year = years.setdefault(change["tax_year"], {
            "year": change["tax_year"], "count": 0, "listed": 0, "ids": [], "income": Decimal(0),
            "basis": Decimal(0), "proceeds": Decimal(0), "gift_values": Decimal(0), "fees": Decimal(0)})
        year["count"] += 1
        year["ids"].append(t.id)
        for field, (old, new) in change["values"].items():
            key = {"cost_basis_usd": "basis", "gross_proceeds_usd": "proceeds", "fmv_usd": "gift_values",
                   "fee_usd": "fees"}[field]
            year[key] += new - old
            if field == "cost_basis_usd" and _is_income(t):
                year["income"] += new - old
        if max(abs(new - old) for old, new in change["values"].values()) >= LISTED_FROM:
            year["listed"] += 1
            items.append(_day_priced_item(t, tz, change))
    for year in years.values():
        for key in ("income", "basis", "proceeds", "gift_values", "fees"):
            year[key] = _money(year[key])
    return items, [years[y] for y in sorted(years)]


def _day_priced_item(t: Transaction, tz, change: dict[str, Any]) -> dict[str, Any]:
    when = datetime.fromtimestamp(change["at"], tz=timezone.utc).strftime("%H:00 UTC")
    at = f"the price when its hour began ({when})"
    if change["moment"] == "hour":
        issue = f"Valued at the day's 00:00 UTC price; at {at}, ${_money(change['price'])}:"
    else:
        issue = f"Not at that day's 00:00 UTC price, ${_money(change['price'])} (no hourly price here):"
    parts = []
    for field, (old, new) in change["values"].items():
        name = VALUE_NAMES.get(field) or ("Income and basis" if _is_income(t) else "Basis")
        parts.append(f"{name} ${_money(old)} -> ${_money(new)}")
    item = _item(t, tz, issue, "; ".join(parts) + ".")
    item.update(year=change["tax_year"], moment=change["moment"],
                values={f: [_money(old), _money(new)] for f, (old, new) in change["values"].items()})
    return item


def _is_valued_deposit(t: Transaction) -> bool:
    """An income or rebate deposit into a BTC account: its basis is its value at receipt."""
    return t.type == "Deposit" and t.to_account_id in BTC_ACCOUNTS and (t.source or "").lower() in DAY_VALUED


def _is_income(t: Transaction) -> bool:
    return (t.source or "").lower() in INCOME_SOURCES


def _income_without_value_items(db: Session, rows: list[Transaction], tz, missing: list[int]) -> list[dict[str, Any]]:
    """Income and rebate deposits with a $0 or blank basis, with that day's
    value when the price is known; the ids of those with no price go to
    `missing`."""
    items = []
    for t in rows:
        if not (_is_valued_deposit(t) and _is_zero_or_blank(t.cost_basis_usd)):
            continue
        income = _is_income(t)
        issue = ("Basis blank" if t.cost_basis_usd is None else "Basis $0.00") + (
            ": no income is reported for it" if income else ": its whole value becomes gain when it's sold")
        becomes = "the income and its cost basis" if income else "its cost basis"
        figure = "Basis (and the income reported)" if income else "Basis"
        market = _market_price(db, t, missing)
        if market is None:
            issue += " (no price stored for that day)."
            change = f"Its value when you received it becomes {becomes}."
        else:
            price, which = market
            expected = (price * Decimal(t.amount)).quantize(CENT)
            issue += f"; at {which} price (${_money(price)}) it is ${_money(expected)}."
            change = f"{figure} $0.00 -> ${_money(expected)} if you clear it."
        items.append(_item(t, tz, issue, change))
    return items


def _gift_without_value_items(db: Session, rows: list[Transaction], tz, missing: list[int]) -> list[dict[str, Any]]:
    """Gifts, donations and lost coins with a $0 or blank value, with that
    hour's value when the price is known; the ids of those with no price go
    to `missing`."""
    items = []
    for t in rows:
        if not (t.type == "Withdrawal" and t.from_account_id in BTC_ACCOUNTS
                and (t.purpose or "").lower() in GIFT_LIKE_PURPOSES and _is_zero_or_blank(t.fmv_usd)):
            continue
        issue = "Value blank: the tax report lists it as not given" if t.fmv_usd is None else "Value $0.00"
        market = _market_price(db, t, missing)
        if market is None:
            items.append(_item(t, tz, issue + " (no price stored for that day).",
                               "Its value when it left becomes the value the report shows."))
            continue
        price, which = market
        expected = (price * Decimal(t.amount)).quantize(CENT)
        items.append(_item(t, tz, f"{issue}; at {which} price (${_money(price)}) it is ${_money(expected)}.",
                           f"Value {'blank' if t.fmv_usd is None else '$0.00'} -> ${_money(expected)} if you clear it."))
    return items


def _income_value_items(db: Session, rows: list[Transaction], tz, missing: list[int]) -> list[dict[str, Any]]:
    """Income and rebate deposits whose typed basis is off the market price
    (a value from a price is day_priced_values'); the ids of those with no
    price go to `missing`."""
    items = []
    for t in rows:
        if not (_is_valued_deposit(t) and not _is_zero_or_blank(t.cost_basis_usd)) or t.cost_basis_from_price:
            continue
        market = _market_price(db, t, missing)
        if market is None:
            continue
        price, which = market
        expected = (price * Decimal(t.amount)).quantize(CENT)
        if _off(t.cost_basis_usd, expected):
            items.append(_item(
                t, tz, f"Basis ${_money(t.cost_basis_usd)}; at {which} price (${_money(price)}) "
                       f"it is ${_money(expected)}.",
                f"{'Basis (and the income reported)' if _is_income(t) else 'Basis'} "
                f"${_money(t.cost_basis_usd)} -> ${_money(expected)} if you change it.",
            ))
    return items


def format_text(review: dict[str, Any]) -> str:
    """Plain text for the CLI."""
    lines = [f"Ledger review (read-only; dates in {review['timezone']})"]
    for check in review["checks"]:
        lines.append(f"{check['title']}: {check['count']}")
        for item in check["items"]:
            detail = item["source"] if item["type"] == "Deposit" else item["purpose"]
            lines.append(f"  #{item['id']}  {item['date']}  {item['type']} ({detail})  {item['amount']} BTC  "
                         f"{item['issue']}")
        lines.extend(f"  {year_line(y)}" for y in check.get("years", []))
        if check["count"]:
            lines.extend(f"  {paragraph}" for paragraph in check["explanation"])
            lines.append(f"  -> {check['action']}")
    return "\n".join(lines) + "\n"


def year_line(year: dict[str, Any]) -> str:
    """The hourly check's line for one tax year: how many change, and its totals' change."""
    unlisted = year["count"] - year["listed"]
    moved = ", ".join(f"{name} {_signed(year[key])}" for key, name in (
        ("income", "income"), ("basis", "basis"), ("proceeds", "proceeds before fees"), ("gift_values", "gift values"),
        ("fees", "fee values"))
        if Decimal(year[key]) != 0) or "no net change"
    return (f"{year['year']}: {year['count']} transaction(s)"
            + (f", {unlisted} by less than $1.00 each (not listed)" if unlisted else "") + f"; totals: {moved}")


def _signed(amount: str) -> str:
    """"+$1000.10" or "-$3.00"."""
    return f"-${amount[1:]}" if amount.startswith("-") else f"+${amount}"
