"""
The Ledger review: a read-only list of saved transactions worth a second
look after the v0.9.2 fixes. Nothing here changes a row; each item says
what looks odd and what would change if the owner acts on it, and gives
its amount with its unit (`unit`: BTC, or USD for a move of dollars).

Shown by GET /api/review, `python -m backend.cli review`, the MCP tool
`review_ledger` and the Ledger review panel in Settings.

Checks:
- account_missing (#337): a transaction naming an account that doesn't
  exist, which only a BitcoinTX before 0.9.2 could save (F28). Its missing
  side is in no balance; one between the owner's account and a missing one
  stops every replay (transaction.AccountMissing names it), so every save
  that recalculates, until it's edited into an account or deleted.
- account_from_before_0_9_2 (5.13, the owner's decision S7): a transaction
  naming an account made through 1.x's account API (an id from 7 to 98),
  which only a BitcoinTX before 0.9.2 could save. 1.x's checks by number
  left it out of income and the like; 2.0 counts it by its account's
  currency (B3). Only the rows on the list the ledger kept at its first 2.0
  start (`accounts_old_rows`, written by database.seed_defaults) that still
  name such an account; saving such a row, even unchanged, or deleting it
  takes it off, and Delete All empties the list.
- zero_proceeds_spend (F1): a Spent withdrawal saved with $0 proceeds.
  Before v0.9.2 the form sent 0 for a blank, so a spend meant to be valued
  at the day's price was saved at $0, a loss of its whole basis. A real $0
  looks the same; only the owner can tell.
- lost_with_loss (F2): a Lost withdrawal whose stored gain isn't $0. Lost
  now counts like a gift ($0 gain); Recalculate Ledger removes the old loss.
- withdrawal_purpose_unknown (#61): a BTC withdrawal whose purpose isn't
  Spent, Gift, Donation or Lost (blank, or free text such as "Expenses"),
  which only a ledger from before that check can hold. It counts as Spent
  (transaction.counts_as_spent, the owner's rule): at its gross, or, saved
  before 0.8.0 with no gross, at the proceeds_usd saved with it (1.2.8's
  recalculations erased those, #329); with none saved, at $0, so its whole
  basis shows as a loss. The item says which. Only the owner knows which
  purpose it was: they confirm Spent or choose another.
- deposit_without_basis (F15): a BTC deposit that isn't income or a rebate
  (source MyBTC, Gift, Inherited, N/A...) with a $0 or blank cost basis. Its whole value
  becomes gain when it's sold. New deposits must state a basis (0 allowed).
- buy_without_basis (#459): a Buy with a $0 or blank cost basis. Before
  1.2.9 the transactions API saved a Buy sent without one, and an edit
  that made a row a Buy without giving one (a type change drops the old
  type's figures): its lot cost $0, so its whole proceeds become gain when
  it's sold. New Buys must state a basis (0 allowed).
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
- sale_may_differ_from_1099da (2.0 spec 5.7, 5.13; a reminder): a Sell from
  2026 on an exchange that sends a Form 1099-DA that took coins moved into
  its account while that account held coins bought there before they
  arrived. An exchange without the purchase dates of coins moved in treats
  them as bought when they arrived, and sells the coins it dates first;
  BitcoinTX sells the oldest by the date first acquired. So the exchange's
  form may report other coins (a 2025 form reports no basis). Nothing in
  the ledger is wrong, and nothing clears it: a reminder.
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
  would change, old -> new: its proceeds, basis and gain, its lot
  disposals' gain (each term's too when it has both), the cost of the lots
  it made, or else only how its rows split, lot by lot (#296). Found by
  running the recalculation on a scratch copy of the database, the live
  one only read (#335). After an upgrade this is
  where the fixes that change existing figures show up (Lost at $0 gain, a
  withdrawal's network fee as its own disposal), before anything moves.
  Editing or deleting any transaction recalculates everything too (adding
  one only when it's dated before the latest, #172).

The price checks read the local price history (and fill it from the
network if a day is missing, kept at once so the review never holds the
write lock, #364; an hourly year not downloaded yet isn't waited for: the
day's price stands in). A day with no price is counted in
no_price_for: F42 passes over its row, income_without_value lists it
without the value. Any other failure of the lookup is an error.
"""

from __future__ import annotations

import heapq
import logging
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.constants import ACCOUNT_EXTERNAL, GIFT_LIKE_PURPOSES, INCOME_SOURCES, INHERITED_SOURCE, ORIGINAL_DATE_SOURCES, VALUED_AT_RECEIPT, normalized
from backend.database import scratch_copy
from backend.models.transaction import BitcoinLot, LotDisposal, Transaction
from backend.services import hourly_prices, old_rows, price_history
from backend.services.hourly_review import hourly_changes
from backend.services.account import AccountBook, account_book
from backend.services.calculation import btc_text
from backend.services.reports.form_8949 import COVERED_DIGITAL_ASSET_START
from backend.services.transaction import known_accounts, missing_accounts, received_known, what_is_missing
from backend.services.tax_time import as_utc, get_tax_timezone, local_date, tax_year_bounds
from backend.unexpected_errors import log_unexpected

logger = logging.getLogger(__name__)

# What the check says when the dry run fails on something that isn't a
# refusal of its own (a bug, a database error): plain words, never SQL; the
# log has the details. Like every recalc_error, it follows "Recalculate
# Ledger would stop with:" (the Settings panel, cli review)
RECALC_STOPS = "Recalculate Ledger would stop with:"
DRY_RUN_FAILED = "an unexpected error (BitcoinTX's log has the details)."

# account_from_before_0_9_2's item (5.13)
OLD_ROW_ISSUE = ("Saved before 0.9.2 into an account made through the old account API; 2.0 counts it by that "
                 "account's currency.")
OLD_ROW_CHANGE = "Saving it, even unchanged, takes it off this list."


# key -> (title, what the owner can do)
CHECKS: dict[str, tuple] = {
    "account_missing": (
        "Transactions naming an account that doesn't exist",
        "A BitcoinTX before 0.9.2 saved these, or an account they named was deleted. The missing account's side "
        "is in none of your balances, and a transfer, deposit or withdrawal between one of your accounts and a "
        "missing one stops every save that recalculates (an edit, a delete, an add dated before the latest) and "
        "Recalculate Ledger. Edit each into one of your accounts, or delete it. If more than one stops saves, fix "
        "them one at a time: an edit or a delete of one goes past the others. Until the last is fixed, figures "
        "can be off, so fix them all before relying on a report.",
    ),
    "account_from_before_0_9_2": (
        "Transactions in an account made through BitcoinTX's old account API",
        "BitcoinTX 1.x left these out of income and some other checks; 2.0 counts them by their account's "
        "currency, so their figures can differ from your 1.x reports. Check each one, and edit it into the right "
        "account if needed. Saving it, even unchanged, takes it off this list.",
    ),
    "recalc_changes": (
        "Figures that Recalculate Ledger would change",
        "Back up first, then run Recalculate Ledger (Settings) when you agree. Editing or deleting any "
        "transaction also recalculates everything.",
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
    "withdrawal_purpose_unknown": (
        "BTC withdrawals whose purpose isn't Spent, Gift, Donation or Lost",
        "Each counts as Spent until you choose. Edit each one and choose its purpose: Spent (you paid for "
        "something with it; enter what you got for it if none is recorded), Gift, Donation or Lost. "
        "One listed as none recorded may have lost "
        "its amount to a recalculation by 1.2.8: the copy of the database made before that update "
        "(backups/btctx-before-schema-0010-….db in BitcoinTX's data folder) still holds it, as proceeds_usd. "
        "Look it up there; don't restore that copy, which would lose everything entered since.",
    ),
    "deposit_without_basis": (
        "BTC deposits (not income or a rebate) with a $0 or blank cost basis",
        "If you know what the BTC cost (for a gift, the giver's cost basis), edit the deposit's cost basis.",
    ),
    "buy_without_basis": (
        "Buys with a $0 or blank cost basis",
        "Edit each one: enter what the BTC cost in USD, before the fee (Amount USD).",
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
    "sale_may_differ_from_1099da": (
        "Reminder: exchange sales your exchange's Form 1099-DA may show differently",
        "Compare each with your exchange's Form 1099-DA. Where they differ, Form 8949 shows the exchange's figures "
        "with an adjustment (code B): ask your tax preparer.",
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
    "sale_may_differ_from_1099da": (
        "Your exchange may have reported other coins for these sales: it may treat coins you moved in as bought "
        "when they arrived, and sell first the coins it dates first. BitcoinTX sells first the oldest coins in each "
        "account by the date each was first acquired, so here it sold coins you moved in, while the exchange may "
        "have sold coins you had bought there before they arrived.",
        "Nothing in your ledger is wrong, and nothing needs editing: these are listed so you can check them "
        "against the form.",
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
# A BTC withdrawal's purposes (transaction.WITHDRAWAL_PURPOSES): any other is
# from before they were checked, and counts as Spent (#61)
KNOWN_PURPOSES = {"spent", *GIFT_LIKE_PURPOSES}

# Explanations shown once for a whole group: the reminders', and the hourly check's
EXPLANATIONS: dict[str, tuple[str, ...]] = {
    **REMINDERS,
    "day_priced_values": (
        "A value BitcoinTX filled in itself (income or a rebate left blank, a spend's proceeds left blank, a "
        "gift's, donation's or lost coins' value, a network fee's value) used that day's midnight (UTC) price "
        "before 1.2.8, and still does when the hour's price isn't available yet (while the hourly history "
        "downloads, for example). IRS rules value "
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


def _item(t: Transaction, tz, book: AccountBook, issue: str, change: str) -> dict[str, Any]:
    return {
        "id": t.id,
        "date": as_utc(t.timestamp).astimezone(tz).strftime("%Y-%m-%d %H:%M"),
        "type": t.type,
        "purpose": t.purpose,
        "source": t.source,
        "amount": _money(t.amount) if _in_dollars(t, book) else btc_text(t.amount),
        "unit": "USD" if _in_dollars(t, book) else "BTC",
        "realized_gain_usd": _money(t.realized_gain_usd),
        "issue": issue,
        "change": change,
    }


def _in_dollars(t: Transaction, book: AccountBook) -> bool:
    """Whether its amount is dollars: a deposit, withdrawal or transfer that
    no bitcoin account is part of, with a dollar account of yours (a bank,
    an exchange's USD) on a side. A Buy's and a Sell's amount is bitcoin;
    so, unknown, is one naming only External and missing accounts."""
    sides = (t.from_account_id, t.to_account_id)
    return t.type not in ("Buy", "Sell") and not any(book.is_btc(a) for a in sides) \
        and any(book.is_yours(a) and book.currency(a) == "USD" for a in sides)


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
# From its lot disposals' gains and the lots it made (#296); each term's
# gain (Schedule D's two lines) where its rows are, or were, of both terms
ROW_TOTALS = ("taxable_gain", "lot_cost")
TERM_GAINS = ("short_term_gain", "long_term_gain")


def simulate_recalculation(db: Session):
    """
    What Recalculate Ledger would change: {id: {field: (old, new)}}, or an
    error message. Runs it on a scratch copy of the database, as committed
    (#335): the live one is only read, so a save made while the check runs
    (a replay of a large ledger takes seconds) doesn't wait for its write
    lock and fail.
    """
    from backend.services.transaction import recalculate_all_transactions

    tz = get_tax_timezone(db)
    with scratch_copy(db) as scratch:
        before = _snapshot(scratch, tz)
        try:
            recalculate_all_transactions(scratch)
            scratch.flush()
            after = _snapshot(scratch, tz)
        except HTTPException as exc:  # e.g. a missing price: say so
            return None, exc.detail
        except Exception as exc:  # never its text in the log at ERROR (#430)
            log_unexpected("Ledger Review: the dry run of Recalculate Ledger", exc, logger)
            return None, DRY_RUN_FAILED
    return _differences(before, after), None


def _snapshot(db: Session, tz) -> dict[int, dict[str, Any]]:
    """Each transaction's stored figures, its lot disposals' and its lots'."""
    figures = {t.id: {f: getattr(t, f) for f in FIGURES} for t in db.query(Transaction).all()}
    for tx_id, rows in _disposal_rows(db).items():
        if tx_id in figures:
            figures[tx_id].update(_row_figures(rows))
    for tx_id, lots in _lots_made(db, tz).items():
        if tx_id in figures:
            figures[tx_id].update(lots)
    return figures


def _differences(before: dict, after: dict) -> dict[int, dict[str, tuple]]:
    """Per transaction, each figure that moves, old -> new; or, when none
    does, its rows or the lots it made, if only how they split moves (#296)."""
    changes = {}
    for tx_id, old in before.items():
        new = after.get(tx_id, {})
        terms = old.get("terms", frozenset()) | new.get("terms", frozenset())
        keys = FIGURES + ROW_TOTALS + (TERM_GAINS if len(terms) == 2 else ())
        diff = {f: (old.get(f), new.get(f)) for f in keys if not _same(old.get(f), new.get(f))}
        if not diff:
            diff = {key: (old.get(part), new.get(part)) for key, part in (("lot_rows", "rows"), ("lot_split", "lots"))
                    if old.get(part) != new.get(part)}
        if diff:
            changes[tx_id] = diff
    return changes


def _same(a, b) -> bool:
    return (a is None and b is None) or (a is not None and b is not None and Decimal(a) == Decimal(b))


def _disposal_rows(db: Session) -> dict[int, list[LotDisposal]]:
    """Each transaction's lot disposals, in the order they were made."""
    rows: dict[int, list[LotDisposal]] = {}
    for d in db.query(LotDisposal).order_by(LotDisposal.transaction_id, LotDisposal.id):
        rows.setdefault(d.transaction_id, []).append(d)
    return rows


def _row_figures(rows: list[LotDisposal]) -> dict[str, Any]:
    """A transaction's taxable gain (its network fees' included), each
    term's gain (Schedule D's two lines), the terms its rows are of, and its
    rows lot by lot."""
    gain = dict.fromkeys(TERM_GAINS, Decimal(0))
    for d in rows:
        gain["long_term_gain" if d.holding_period == "LONG" else "short_term_gain"] += Decimal(d.realized_gain_usd or 0)
    return {
        "taxable_gain": sum(gain.values(), Decimal(0)),
        **gain,
        # A row with no term stored (before 0.7) is short-term, as the reports count it
        "terms": frozenset("LONG" if d.holding_period == "LONG" else "SHORT" for d in rows),
        "rows": [{"term": d.holding_period, "fee": bool(d.is_fee), "btc": btc_text(d.disposed_btc),
                  "basis": _money(d.disposal_basis_usd), "proceeds": _money(d.proceeds_usd_for_that_portion),
                  "gain": _money(d.realized_gain_usd)} for d in rows],
    }


def _lots_made(db: Session, tz) -> dict[int, dict[str, Any]]:
    """The lots each transaction made, and their cost: a transfer's is the
    cost it moved, which a recalculation can change by a cent (#296). Each
    dated in the tax timezone, as the holding period and Form 8949 date it:
    a lot moved to another hour of its day (a deposit's lot is at noon of
    its date originally acquired, whatever time was given with it) changes
    no figure, and a change of order it makes shows in the rows."""
    made: dict[int, list[BitcoinLot]] = {}
    for lot in db.query(BitcoinLot):
        made.setdefault(lot.created_txn_id, []).append(lot)
    return {tx_id: {
        "lot_cost": sum((Decimal(lot.cost_basis_usd or 0) for lot in lots), Decimal(0)),
        "lots": sorted(({"acquired": local_date(lot.acquired_date, tz).isoformat(), "btc": btc_text(lot.total_btc),
                         "cost": _money(lot.cost_basis_usd)} for lot in lots),
                       key=lambda lot: (lot["acquired"], Decimal(lot["btc"]), Decimal(lot["cost"] or 0))),
    } for tx_id, lots in made.items()}


def build_review(db: Session) -> dict[str, Any]:
    """Every check's items, in date order. Changes no transaction."""
    tz = get_tax_timezone(db)
    moved, recalc_error = simulate_recalculation(db)
    rows: list[Transaction] = (
        db.query(Transaction)
        .filter(Transaction.type.in_(("Withdrawal", "Deposit", "Buy")))
        .order_by(Transaction.timestamp, Transaction.id)
        .all()
    )
    found: dict[str, list[dict[str, Any]]] = {key: [] for key in CHECKS}
    book = account_book(db)
    for t in rows:
        for key, item in _row_issues(t, tz, book):
            found[key].append(item)
    found["account_missing"] = _account_missing_items(db, tz, book)
    found["account_from_before_0_9_2"] = _old_account_items(db, tz, book)
    found["recalc_changes"] = _recalc_items(db, moved or {}, tz, book)
    found["day_priced_values"], years = _day_priced_items(db, tz, book)
    missing: list[int] = []
    found["income_without_value"] = _income_without_value_items(db, rows, tz, missing)
    found["gift_without_value"] = _gift_without_value_items(db, rows, tz, missing)
    found["income_value_off"] = _income_value_items(db, rows, tz, missing)
    found["sale_may_differ_from_1099da"] = _sale_may_differ_items(db, tz, book)

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


def _row_issues(t: Transaction, tz, book: AccountBook):
    """(check, item) for each check a withdrawal, deposit or buy fails on its own."""
    yield from _purpose_issues(t, tz, book)
    # Only bitcoin leaving has a bitcoin purpose: a dollar withdrawal's is one an older save left there (#449)
    purpose = normalized(t.purpose) if book.is_btc(t.from_account_id) else ""
    if t.type == "Withdrawal" and purpose == "spent" and t.gross_proceeds_usd is not None \
            and Decimal(t.gross_proceeds_usd) == 0 and received_known(t):  # else listed as an unknown purpose
        yield "zero_proceeds_spend", _item(
            t, tz, book, "Saved with $0 proceeds: its whole basis shows as a loss.",
            "Proceeds you enter replace $0; the gain changes by the same amount.",
        )
    if t.type == "Withdrawal" and purpose == "lost" and not (
        t.realized_gain_usd is not None and Decimal(t.realized_gain_usd) == 0
    ):
        yield "lost_with_loss", _item(
            t, tz, book, f"Stored gain {_money(t.realized_gain_usd) or 'not calculated'}.",
            "Gain becomes $0.00 after Recalculate Ledger.",
        )
    into_btc = t.type == "Deposit" and book.is_btc(t.to_account_id)
    if into_btc and normalized(t.source) in DATED_FROM_DEPOSIT and t.acquired_at is None:
        yield "original_date_missing", _item(t, tz, book, "No date originally acquired.", "")
    if into_btc and normalized(t.source) == INHERITED_SOURCE and t.acquired_at is None:
        yield "inherited_without_date", _item(t, tz, book, "No date of death.", "")
    if into_btc and normalized(t.source) not in DAY_VALUED and _is_zero_or_blank(t.cost_basis_usd):
        yield "deposit_without_basis", _no_basis_item(t, tz, book)
    if t.type == "Buy" and _is_zero_or_blank(t.cost_basis_usd):
        yield "buy_without_basis", _no_basis_item(t, tz, book)


def _no_basis_item(t: Transaction, tz, book: AccountBook) -> dict[str, Any]:
    """A deposit's or a buy's item for its $0 or blank cost basis."""
    return _item(
        t, tz, book, "Cost basis " + ("blank" if t.cost_basis_usd is None else "$0.00") + ".",
        "A basis you enter lowers the gain when this BTC is sold by the same amount.",
    )


def _purpose_issues(t: Transaction, tz, book: AccountBook):
    """A BTC withdrawal with a purpose BitcoinTX doesn't know (#61)."""
    if t.type == "Withdrawal" and book.is_btc(t.from_account_id) \
            and (normalized(t.purpose) not in KNOWN_PURPOSES or _spaced_spent_unknown(t)):
        named = f'"{t.purpose}"' if (t.purpose or "").strip() else "blank"
        yield "withdrawal_purpose_unknown", _item(
            t, tz, book, f"Purpose {named}: {_counted_as(t)}",
            "If it was a spend, choose Spent (with what you got for it, if none is recorded); as Gift, "
            "Donation or Lost it has no gain.",
        )


def _spaced_spent_unknown(t: Transaction) -> bool:
    """An old " spent " (#342) with nothing recorded as received: counted as
    an unknown purpose is (transaction.received_known), so listed as one,
    sending the owner to the copy that may hold its amount (#329)."""
    return normalized(t.purpose) == "spent" and not received_known(t)


def _account_missing_items(db: Session, tz, book: AccountBook) -> list[dict[str, Any]]:
    """Each transaction naming an account that doesn't exist, or none (#337)."""
    known = known_accounts(db)
    rows = (
        db.query(Transaction)
        .filter(Transaction.from_account_id.is_(None) | Transaction.to_account_id.is_(None)
                | ~Transaction.from_account_id.in_(known) | ~Transaction.to_account_id.in_(known))
        .order_by(Transaction.timestamp, Transaction.id)
        .all()
    )
    return [_item(t, tz, book, _sentence(what_is_missing(missing_accounts(t, known))) + _stops_saves(t, known),
                  "Edit it into one of your accounts, or delete it.") for t in rows]


def _old_account_items(db: Session, tz, book: AccountBook) -> list[dict[str, Any]]:
    """Each row on the ledger's list from before 0.9.2 (old_rows) that still
    names an account made through 1.x's account API (5.13). One that also
    names a missing account is account_missing's, so no row is listed
    twice."""
    ids = old_rows.listed(db)
    if not ids:
        return []
    known, old = known_accounts(db), old_rows.old_accounts(db)
    rows = (
        db.query(Transaction)
        .filter(Transaction.id.in_(ids))
        .order_by(Transaction.timestamp, Transaction.id)
        .all()
    )
    return [_item(t, tz, book, OLD_ROW_ISSUE, OLD_ROW_CHANGE) for t in rows
            if {t.from_account_id, t.to_account_id} & old and not missing_accounts(t, known)]


def _sale_may_differ_items(db: Session, tz, book: AccountBook) -> list[dict[str, Any]]:
    """
    Each Sell from 2026 in the tax timezone (a 2025 Form 1099-DA reports no
    basis) from an exchange's BTC account whose exchange sends a Form
    1099-DA, and not marked as on none, that took coins it didn't buy there
    (moved in, or deposited) while that account held coins bought there
    after those were first acquired and before they arrived (5.7, 5.13):
    BitcoinTX sold the moved coins first, as the older; the exchange, dating
    them by their arrival, would sell the coins bought there first.
    """
    start, _ = tax_year_bounds(COVERED_DIGITAL_ASSET_START.year, tz)
    sells = [t for t in db.query(Transaction).filter(Transaction.type == "Sell", Transaction.timestamp >= start)
             .order_by(Transaction.timestamp, Transaction.id)
             if book.is_btc(t.from_account_id) and book.sends_1099da(t.from_account_id) and t.broker_reporting != "none"]
    # (first acquired, arrived) of the coins each took that weren't bought there
    moved = {t.id: [(as_utc(d.lot.acquired_date), as_utc(d.lot.created_transaction.timestamp))
                    for d in t.lot_disposals if not d.is_fee and not _bought_there(d.lot)] for t in sells}
    sells = [t for t in sells if moved[t.id]]
    held: dict[int, dict[BitcoinLot, Decimal]] = {}
    for account_id in {t.from_account_id for t in sells}:
        held.update(replayed_lots(db, account_id, {t.id for t in sells})[0])
    return [_item(t, tz, book, f"Sold coins moved into {book.name(t.from_account_id)} while it held coins bought "
                  "there before they arrived.", "")
            for t in sells if any(acquired < as_utc(lot.acquired_date) < arrived for acquired, arrived in moved[t.id]
                                  for lot in held[t.id] if _bought_there(lot))]


def _bought_there(lot: BitcoinLot) -> bool:
    """Made by a Buy: into the account it's in, the one its exchange bought it for."""
    return lot.created_transaction is not None and lot.created_transaction.type == "Buy"


def replayed_lots(db: Session, account_id: int, wanted: set[int]) \
        -> tuple[dict[int, dict[BitcoinLot, Decimal]], dict[BitcoinLot, Decimal]]:
    """
    A bitcoin account's lots replayed from the stored figures, in the
    ledger's order (timestamp, then id): the lots a transaction made in it
    join it, and what one took from it (its lot disposals there, and the
    lots a transfer made elsewhere from it) leaves it oldest first, by date
    acquired and then the first made, as the engine takes them
    (transaction._open_lots). For each transaction in `wanted`, what each
    lot held just before it (those with BTC); and what each holds at the
    end, its stored remaining_btc. Reads only.
    """
    made: dict[int, list[BitcoinLot]] = defaultdict(list)
    for lot in (db.query(BitcoinLot).join(Transaction, Transaction.id == BitcoinLot.created_txn_id)
                .filter(Transaction.to_account_id == account_id)):
        made[lot.created_txn_id].append(lot)
    taken: dict[int, Decimal] = defaultdict(Decimal)
    for tx_id, btc in (db.query(LotDisposal.transaction_id, LotDisposal.disposed_btc)
                       .join(BitcoinLot, BitcoinLot.id == LotDisposal.lot_id)
                       .join(Transaction, Transaction.id == BitcoinLot.created_txn_id)
                       .filter(Transaction.to_account_id == account_id)):
        taken[tx_id] += btc
    for tx_id, btc in (db.query(BitcoinLot.created_txn_id, BitcoinLot.total_btc)
                       .join(Transaction, Transaction.id == BitcoinLot.created_txn_id)
                       .filter(Transaction.from_account_id == account_id, Transaction.to_account_id != account_id)):
        taken[tx_id] += btc  # what a transfer moved from it
    held: dict[BitcoinLot, Decimal] = {}
    oldest: list[tuple] = []  # (date acquired, id, lot) of each lot with BTC, oldest first
    before: dict[int, dict[BitcoinLot, Decimal]] = {}
    for (tx_id,) in (db.query(Transaction.id)
                     .filter(or_(Transaction.from_account_id == account_id, Transaction.to_account_id == account_id))
                     .order_by(Transaction.timestamp, Transaction.id)):
        if tx_id in wanted:
            before[tx_id] = {lot: btc for lot, btc in held.items() if btc > 0}
        _take_oldest_first(held, oldest, taken.get(tx_id, Decimal(0)))
        for lot in made.get(tx_id, []):
            held[lot] = lot.total_btc
            heapq.heappush(oldest, (as_utc(lot.acquired_date), lot.id, lot))
    return before, held


def _take_oldest_first(held: dict[BitcoinLot, Decimal], oldest: list[tuple], btc: Decimal) -> None:
    while btc > 0 and oldest:
        lot = oldest[0][2]
        piece = min(held[lot], btc)
        held[lot] -= piece
        btc -= piece
        if held[lot] == 0:
            heapq.heappop(oldest)


def _stops_saves(t: Transaction, known: set[int]) -> str:
    """Whether the row stops every save that recalculates (except an edit or
    a delete of another such row, #368): its balance check
    (transaction._verify_double_entry_balance_for_internal) runs, as for any
    type but a Buy or a Sell with no External side, and fails, as one of its
    sides is an account that exists and the other isn't (#367's review)."""
    sides = (t.from_account_id, t.to_account_id)
    stops = t.type not in ("Buy", "Sell") and ACCOUNT_EXTERNAL not in sides and any(a in known for a in sides)
    return (" It stops every save that recalculates, except an edit or a delete of one of these." if stops
            else " It doesn't stop saves.")


def _sentence(text: str) -> str:
    """The text as a sentence: its first letter capital (and only it), a full stop."""
    return text[:1].upper() + text[1:] + "."


def _counted_as(t: Transaction) -> str:
    """What a withdrawal of unknown purpose counts as: Spent (#61), at its
    gross, or at the proceeds_usd a row saved before 0.8.0 holds, which a
    recalculation makes its gross; else at $0, none recorded, whether blank
    or the 0 a 1.2.8 recalculation left (#329)
    (transaction._withdrawal_gross_proceeds)."""
    fee = " before its network fee" if (t.fee_currency or "").upper() == "BTC" \
        and Decimal(t.fee_amount or 0) > 0 else ""
    if Decimal(t.gross_proceeds_usd or 0) > 0:
        return f"counted as Spent, with ${_money(t.gross_proceeds_usd)} proceeds{fee}."
    if t.gross_proceeds_usd is None and Decimal(t.proceeds_usd or 0) > 0:
        return f"counted as Spent, with the ${_money(t.proceeds_usd)} proceeds saved with it{fee}."
    return "counted as Spent at $0 proceeds (none recorded), so its whole basis shows as a loss."


# How the recalculation items name the figures.
FIGURE_NAMES = {"proceeds_usd": "proceeds", "cost_basis_usd": "basis", "realized_gain_usd": "gain",
                "taxable_gain": "taxable gain incl. network fees", "short_term_gain": "short-term gain",
                "long_term_gain": "long-term gain", "lot_cost": "cost of the lots it made"}


# A transaction's totals stay, and only how its rows, or the lots it made,
# split them moves (#296)
SPLITS = {"lot_rows": "Its rows, lot by lot, would be split differently",
          "lot_split": "The lots it made would differ (their dates, BTC or cost)"}


def _change_text(diff: dict) -> str:
    """What would change, in words: old -> new for each figure, or how it splits."""
    if any(f in SPLITS for f in diff):
        return "; ".join(SPLITS[f] for f in SPLITS if f in diff) + "; its totals stay the same."
    return "; ".join(f"{FIGURE_NAMES[f]} {_money(old) or 'none'} -> {_money(new) or 'none'}"
                     for f, (old, new) in diff.items()) + "."


def _recalc_items(db: Session, moved: dict, tz, book: AccountBook) -> list[dict[str, Any]]:
    """The transactions whose figures Recalculate Ledger would change, in
    date order. Each is looked up once on the live database: one deleted
    while the dry run ran on its copy (#335) is no longer listed."""
    rows = [t for tx_id in moved if (t := db.get(Transaction, tx_id)) is not None]
    items = []
    for t in sorted(rows, key=lambda t: (t.timestamp, t.id)):
        diff = moved[t.id]
        item = _item(t, tz, book, "Stored figures differ from what the current rules give.", _change_text(diff))
        item["changes"] = {f: list(pair) if f in SPLITS else [_money(pair[0]), _money(pair[1])]
                           for f, pair in diff.items()}
        items.append(item)
    return items


def _day_priced_items(db: Session, tz, book: AccountBook) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The values priced at the day that the hour would change: the items
    (a change of $1.00 or more) and each tax year's totals (all of them)."""
    items, years = [], {}
    for change in hourly_changes(db):
        t = db.get(Transaction, change["id"])
        if t is None:  # deleted since it was found: nothing left to change
            continue
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
            items.append(_day_priced_item(t, tz, book, change))
    for year in years.values():
        for key in ("income", "basis", "proceeds", "gift_values", "fees"):
            year[key] = _money(year[key])
    return items, [years[y] for y in sorted(years)]


def _day_priced_item(t: Transaction, tz, book: AccountBook, change: dict[str, Any]) -> dict[str, Any]:
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
    item = _item(t, tz, book, issue, "; ".join(parts) + ".")
    item.update(year=change["tax_year"], moment=change["moment"],
                values={f: [_money(old), _money(new)] for f, (old, new) in change["values"].items()})
    return item


def _is_valued_deposit(t: Transaction, book: AccountBook) -> bool:
    """An income or rebate deposit into a BTC account: its basis is its value at receipt."""
    return t.type == "Deposit" and book.is_btc(t.to_account_id) and normalized(t.source) in DAY_VALUED


def _is_income(t: Transaction) -> bool:
    return normalized(t.source) in INCOME_SOURCES


def _income_without_value_items(db: Session, rows: list[Transaction], tz, missing: list[int]) -> list[dict[str, Any]]:
    """Income and rebate deposits with a $0 or blank basis, with that day's
    value when the price is known; the ids of those with no price go to
    `missing`."""
    items = []
    book = account_book(db)
    for t in rows:
        if not (_is_valued_deposit(t, book) and _is_zero_or_blank(t.cost_basis_usd)):
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
        items.append(_item(t, tz, book, issue, change))
    return items


def _gift_without_value_items(db: Session, rows: list[Transaction], tz, missing: list[int]) -> list[dict[str, Any]]:
    """Gifts, donations and lost coins with a $0 or blank value, with that
    hour's value when the price is known; the ids of those with no price go
    to `missing`."""
    items = []
    book = account_book(db)
    for t in rows:
        if not (t.type == "Withdrawal" and book.is_btc(t.from_account_id)
                and normalized(t.purpose) in GIFT_LIKE_PURPOSES and _is_zero_or_blank(t.fmv_usd)):
            continue
        issue = "Value blank: the tax report lists it as not given" if t.fmv_usd is None else "Value $0.00"
        market = _market_price(db, t, missing)
        if market is None:
            items.append(_item(t, tz, book, issue + " (no price stored for that day).",
                               "Its value when it left becomes the value the report shows."))
            continue
        price, which = market
        expected = (price * Decimal(t.amount)).quantize(CENT)
        items.append(_item(t, tz, book, f"{issue}; at {which} price (${_money(price)}) it is ${_money(expected)}.",
                           f"Value {'blank' if t.fmv_usd is None else '$0.00'} -> ${_money(expected)} if you clear it."))
    return items


def _income_value_items(db: Session, rows: list[Transaction], tz, missing: list[int]) -> list[dict[str, Any]]:
    """Income and rebate deposits whose typed basis is off the market price
    (a value from a price is day_priced_values'); the ids of those with no
    price go to `missing`."""
    items = []
    book = account_book(db)
    for t in rows:
        if not (_is_valued_deposit(t, book) and not _is_zero_or_blank(t.cost_basis_usd)) or t.cost_basis_from_price:
            continue
        market = _market_price(db, t, missing)
        if market is None:
            continue
        price, which = market
        expected = (price * Decimal(t.amount)).quantize(CENT)
        if _off(t.cost_basis_usd, expected):
            items.append(_item(
                t, tz, book, f"Basis ${_money(t.cost_basis_usd)}; at {which} price (${_money(price)}) "
                       f"it is ${_money(expected)}.",
                f"{'Basis (and the income reported)' if _is_income(t) else 'Basis'} "
                f"${_money(t.cost_basis_usd)} -> ${_money(expected)} if you change it.",
            ))
    return items


def format_text(review: dict[str, Any]) -> str:
    """Plain text for the CLI."""
    lines = [f"Ledger review (read-only; dates in {review['timezone']})"]
    if review.get("recalc_error"):
        lines.append(f"{RECALC_STOPS} {review['recalc_error']}")
    for check in review["checks"]:
        lines.append(f"{check['title']}: {check['count']}")
        for item in check["items"]:
            lines.append(f"  #{item['id']}  {item['date']}  {_kind(item)}  {_amount(item)}  {item['issue']}")
        lines.extend(f"  {year_line(y)}" for y in check.get("years", []))
        if check["count"]:
            lines.extend(f"  {paragraph}" for paragraph in check["explanation"])
            lines.append(f"  -> {check['action']}")
    return "\n".join(lines) + "\n"


def _kind(item: dict[str, Any]) -> str:
    """"Deposit (Income)", "Withdrawal (Spent)", or the type alone: a
    transfer has no source or purpose, and some rows saved none."""
    detail = item["source"] if item["type"] == "Deposit" else item["purpose"] if item["type"] == "Withdrawal" else None
    return f"{item['type']} ({detail})" if detail else item["type"]


def _amount(item: dict[str, Any]) -> str:
    """"0.10000000 BTC", or "$500.00" for a move of dollars."""
    return f"${item['amount']}" if item.get("unit") == "USD" else f"{item['amount']} BTC"


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
