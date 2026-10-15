#!/usr/bin/env python3
"""
A second, deliberately simple calculation of a ledger's tax figures, to check
BitcoinTX's own (#150, and #80 item 2). It is written from the rules: the
IRS's (FIFO per account, "more than one year", Form 8949's boxes and
Schedule D's lines) and the ledger's documented ones (AGENTS.md "Tax
invariants", the AI connector's ledger guide). It imports nothing from
backend/, so a mistake in the app's code can't hide in both.

It replays the reference test ledger (testdata/reference_ledger.json) and
gives each year's Form 8949 rows, Schedule D lines, box totals, gains
summary, income, rebates, gifts and year-end lots:

    python scripts/independent_figures.py --year 2025          # JSON
    python scripts/independent_figures.py --compare            # against reference_figures.json

`--compare` lists every difference from testdata/reference_figures.json for
2024 and 2025 (`--years` for others). backend/tests/test_independent_figures.py
runs it for every year and fails on a difference. Dates are taken in UTC,
the reference figures' tax time zone.

Amounts stay exact (fractions) until they are rounded to the cent. Three
conventions are the ledger's (AGENTS.md "Tax invariants", Lot cost), shared
on purpose so the two agree to the cent:
- a disposal's proceeds are shared among its lots in cents, and the last lot
  takes what's left, so the rows report all of them (the amount realized);
- a lot's cost is claimed as a running total (#100): a piece taken from it
  costs what the lot's BTC taken so far costs with it, in cents, less what
  it cost without it, so a lot's pieces add up to its cost, a moved piece
  starts its new lot with that cost, and what's held carries the rest;
- an exact half cent rounds up, as the IRS rounds to whole dollars and the
  app does (#100); `--rounding half-down` rounds it down, as the app did
  before. The app multiplies before it divides with 28 significant digits,
  so for any amount a ledger holds an exact half cent stays exact; only
  products past 28 digits (amounts near the columns' limits) could round a
  tie the other way. None is in the reference ledger, and one would make the
  test fail rather than pass by accident.

A test tool: it lives in scripts/, which no build ships.
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import copy
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_DOWN, ROUND_HALF_UP, Decimal
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "testdata" / "reference_ledger.json"
FIGURES = ROOT / "testdata" / "reference_figures.json"

WALLET, EXCHANGE_BTC = 2, 4
BTC_ACCOUNTS = {WALLET: "Wallet", EXCHANGE_BTC: "Exchange BTC"}
INCOME_SOURCES = ("Income", "Interest", "Reward")
NOT_SALES = ("Gift", "Donation", "Lost")
CENT = Decimal("0.01")
SATS = Decimal("0.00000001")
HALF = Fraction(1, 2)
COLUMNS = ("proceeds", "cost", "gain_loss")
# Brokers report digital-asset basis only for assets bought from 2026 on and
# kept in the same account (Treas. Reg. §1.6045-1(a)(15)(i)(J)): "covered".
COVERED_FROM = date(2026, 1, 1)
# Form 8949's checkbox for (who reported it, long-term?): before 2025 the
# 1099-B boxes A-F; from 2025 digital assets have their own, G-L.
BOXES_UNTIL_2024 = {"basis": "AD", "proceeds": "BE", "none": "CF"}
BOXES_FROM_2025 = {"basis": "GJ", "proceeds": "HK", "none": "IL"}
SCHEDULE_D_LINE = {
    "A": "1b", "B": "2", "C": "3", "D": "8b", "E": "9", "F": "10",
    "G": "1b", "H": "2", "I": "3", "J": "8b", "K": "9", "L": "10",
}
ROUNDING = {"half-up": ROUND_HALF_UP, "half-down": ROUND_HALF_DOWN}


@dataclass
class Lot:
    """BTC acquired together: its basis travels with it, by the satoshi."""

    quantity: Fraction  # left
    basis: Fraction  # the cost of what's left
    acquired: datetime
    covered: bool
    order: int
    inherited: bool = False
    total: Fraction = field(init=False)  # as acquired
    cost: Fraction = field(init=False)
    taken: Fraction = field(init=False)

    def __post_init__(self) -> None:
        self.total, self.cost, self.taken = self.quantity, self.basis, Fraction(0)


@dataclass
class Row:
    """One Form 8949 row: the part of a disposal that came from one lot."""

    kind: str  # "sale", "spend" or "fee"
    quantity: Fraction
    proceeds: Fraction
    basis: Fraction
    acquired: datetime
    sold: datetime
    covered: bool
    broker_reporting: str | None
    inherited: bool = False


@dataclass
class Ledger:
    rounding: str
    lots: dict[int, list[Lot]] = field(default_factory=lambda: {a: [] for a in BTC_ACCOUNTS})
    rows: list[Row] = field(default_factory=list)
    income: list[tuple[datetime, str, Fraction]] = field(default_factory=list)
    rebates: list[tuple[datetime, Fraction, Fraction]] = field(default_factory=list)
    gifts: list[tuple[datetime, str, Fraction, str | None]] = field(default_factory=list)
    holdings: dict[int, list[tuple[str, Lot]]] = field(default_factory=dict)
    year: int | None = None
    next_order: int = 0

    def add_lot(self, account: int, quantity: Fraction, basis: Fraction, acquired: datetime, covered: bool,
                inherited: bool = False) -> None:
        self.lots[account].append(Lot(quantity, basis, acquired, covered, self.next_order, inherited))
        self.next_order += 1

    def take(self, account: int, quantity: Fraction) -> list[tuple[Lot, Fraction, Fraction]]:
        """Remove `quantity` BTC oldest acquisition first: (lot, BTC, basis) per piece."""
        pieces = []
        for lot in sorted(self.lots[account], key=lambda lot: (lot.acquired, lot.order)):
            if quantity == 0:
                break
            used = min(quantity, lot.quantity)
            basis = self.cost_of(lot, lot.taken + used) - self.cost_of(lot, lot.taken)
            pieces.append((lot, used, basis))
            lot.taken += used
            lot.quantity -= used
            lot.basis -= basis
            quantity -= used
        if quantity:
            raise ValueError(f"not enough BTC in account {account}")
        self.lots[account] = [lot for lot in self.lots[account] if lot.quantity]
        return pieces

    def cost_of(self, lot: Lot, btc: Fraction) -> Fraction:
        """What a lot's first `btc` BTC cost, in cents (all of it: exactly its cost)."""
        return lot.cost if btc >= lot.total else Fraction(_cents(lot.cost * btc / lot.total, self.rounding))


def replay(transactions: list[dict], rounding: str = ROUND_HALF_UP) -> Ledger:
    """Every transaction in time order (the file's order on a tie)."""
    ledger = Ledger(rounding)
    handlers = {"Deposit": _deposit, "Buy": _buy, "Sell": _sell, "Withdrawal": _withdrawal, "Transfer": _transfer}
    ordered = sorted(enumerate(transactions), key=lambda pair: (_moment(pair[1]["timestamp"]), pair[0]))
    for _, tx in ordered:
        when = _moment(tx["timestamp"])
        _close_years_before(ledger, when.year)
        handlers[tx["type"]](ledger, tx, when)
    _close_years_before(ledger, ledger.year + 1)
    return ledger


def year_figures(ledger: Ledger, year: int) -> dict:
    rows = [_form_row(row, year, ledger.rounding) for row in ledger.rows if row.sold.year == year]
    holdings = [{"account": account, "acquired": lot.acquired.isoformat(), "quantity": _btc(lot.quantity),
                 "cost": str(_cents(lot.basis, ledger.rounding))} for account, lot in ledger.holdings.get(year, [])]
    return {
        "form_8949": rows,
        "schedule_d": _schedule_d(rows),
        "boxes": _box_totals(rows),
        "gains": _gains_summary(rows),
        "income": _income(ledger, year),
        "rebates": [{"date": when.isoformat(), "amount": _btc(amount), "value_usd": str(_cents(value, ledger.rounding))}
                    for when, amount, value in ledger.rebates if when.year == year],
        "gifts_donations_lost": [
            {"date": when.isoformat(), "type": kind, "amount": _btc(amount), "fmv_usd": _usd(fmv)}
            for when, kind, amount, fmv in ledger.gifts if when.year == year],
        "end_of_year_holdings": holdings,
        "end_of_year_total": {"quantity": _btc(sum(Fraction(lot["quantity"]) for lot in holdings)),
                              "cost": str(sum(Decimal(lot["cost"]) for lot in holdings))},
    }


def differences(mine: dict, app: dict) -> list[str]:
    """Every figure where this calculation and the app's saved one disagree."""
    report = app["report"]
    found = _unmatched("Form 8949 row", mine["form_8949"], app["form_8949"])
    found += _schedule_d_differences(mine["schedule_d"], app["schedule_d"])
    found += _unmatched("box total", mine["boxes"], [
        {"box": b["box"], "line": b["line"], "rows": b["rows"], **{c: _usd(b[c]) for c in COLUMNS}}
        for b in report["form_8949_boxes"]])
    found += _compare("gains summary", mine["gains"], _app_gains(report["capital_gains_summary"]))
    found += _compare("income", mine["income"], {k: _usd(v) for k, v in report["income_summary"].items()})
    found += _unmatched("rebate", mine["rebates"], [
        {"date": r["date"], "amount": _btc(Fraction(str(r["amount"]))), "value_usd": _usd(r["value_usd"])}
        for r in report["rebates"]])
    found += _unmatched("gift, donation or loss", mine["gifts_donations_lost"], [
        {"date": g["date"], "type": g["type"], "amount": _btc(Fraction(str(g["amount"]))), "fmv_usd": _usd(g["fmv_usd"])}
        for g in report["gifts_donations_lost"]])
    return found + _holding_differences(mine, report["end_of_year_balances"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--year", type=int, help="print one year's figures as JSON")
    parser.add_argument("--compare", action="store_true", help="compare with the reference figures")
    parser.add_argument("--years", type=int, nargs="+", default=[2024, 2025])
    parser.add_argument("--rounding", choices=ROUNDING, default="half-up",
                        help="how an exact half cent rounds (the app: half-up)")
    args = parser.parse_args()
    ledger = replay(json.loads(LEDGER.read_text())["transactions"], ROUNDING[args.rounding])
    if args.year:
        print(json.dumps(year_figures(ledger, args.year), indent=1))
        return 0
    saved = json.loads(FIGURES.read_text())["years"]
    found = [f"{year}: {line}" for year in args.years
             for line in differences(year_figures(ledger, year), saved[str(year)])]
    print("\n".join(found) or f"No differences in {', '.join(map(str, args.years))}.")
    return 1 if found else 0


def _moment(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _close_years_before(ledger: Ledger, year: int) -> None:
    """Keep each year's closing lots, once the ledger has moved past it."""
    for closed in range(ledger.year or year, year):
        ledger.holdings[closed] = [(BTC_ACCOUNTS[account], copy(lot))
                                   for account, lots in ledger.lots.items() for lot in lots]
    ledger.year = max(ledger.year or year, year)


def _deposit(ledger: Ledger, tx: dict, when: datetime) -> None:
    if tx["to_account_id"] not in BTC_ACCOUNTS:
        return
    amount, value = _money(tx["amount"]), _money(tx.get("cost_basis_usd"))
    # A My BTC or Gift deposit's holding period runs from when it was first
    # acquired (the giver's date for a gift: IRC §1223(2)). Inherited coins
    # are acquired at the death (IRC §1014: their basis is their value then)
    # and long-term whenever sold (§1223(9)).
    acquired = _moment(tx["acquired_at"]) if tx.get("acquired_at") else when
    ledger.add_lot(tx["to_account_id"], amount, value, acquired, covered=False,
                   inherited=tx.get("source") == "Inherited")
    # Income is its value at receipt, which is also its basis; a rebate is
    # valued the same way but lowers a purchase price instead of being income.
    if tx.get("source") in INCOME_SOURCES:
        ledger.income.append((when, tx["source"], value))
    elif tx.get("source") == "Rebate":
        ledger.rebates.append((when, amount, value))


def _buy(ledger: Ledger, tx: dict, when: datetime) -> None:
    # The dollar fee is part of what the BTC cost (IRC §1012).
    basis = _money(tx["cost_basis_usd"]) + _money(tx["fee_amount"])
    ledger.add_lot(EXCHANGE_BTC, _money(tx["amount"]), basis, when, covered=when.date() >= COVERED_FROM)


def _sell(ledger: Ledger, tx: dict, when: datetime) -> None:
    # The fee comes off the gross proceeds (amount realized, IRC §1001).
    proceeds = _gross_proceeds(tx) - _money(tx["fee_amount"])
    pieces = ledger.take(tx["from_account_id"], _money(tx["amount"]))
    _dispose(ledger, "sale", pieces, proceeds, when, tx.get("broker_reporting"))


def _withdrawal(ledger: Ledger, tx: dict, when: datetime) -> None:
    account = tx["from_account_id"]
    if account not in BTC_ACCOUNTS:
        return
    purpose = tx["purpose"]
    if purpose in NOT_SALES:
        _pay_network_fee(ledger, tx, account, when)
        amount = _money(tx["amount"])
        ledger.take(account, amount)
        ledger.gifts.append((when, purpose, amount, tx.get("fmv_usd")))
        return
    # The fee paid to make a spend is a cost of it: it comes off what was
    # received, and the two realize what was received (Treas. Reg.
    # §1.1001-7(b)(2)(ii)(A), Example 4; #157).
    received = _gross_proceeds(tx)
    fee_value = min(_money(tx["fee_usd"]), received) if tx["fee_currency"] == "BTC" else Fraction(0)
    _pay_network_fee(ledger, tx, account, when, fee_value)
    pieces = ledger.take(account, _money(tx["amount"]))
    _dispose(ledger, "spend", pieces, received - fee_value, when, tx.get("broker_reporting"))


def _transfer(ledger: Ledger, tx: dict, when: datetime) -> None:
    source, destination = tx["from_account_id"], tx["to_account_id"]
    if source not in BTC_ACCOUNTS:
        return
    fee = _pay_network_fee(ledger, tx, source, when)
    if destination == source:
        # A consolidation, or a move between wallets pooled as one (#159):
        # only the fee leaves the account (IRS digital-asset FAQ Q81, Q97).
        return
    # The amount left the source including the fee; what arrives keeps each
    # lot's date and its share of basis: moving your own coins isn't a sale.
    for lot, quantity, basis in ledger.take(source, _money(tx["amount"]) - fee):
        ledger.add_lot(destination, quantity, basis, lot.acquired, covered=False, inherited=lot.inherited)


def _money(value: str | None) -> Fraction:
    return Fraction(Decimal(str(value))) if value not in (None, "") else Fraction(0)


def _gross_proceeds(tx: dict) -> Fraction:
    """What the BTC brought before fees (the ledger guide's proceeds_usd)."""
    return _money(tx.get("gross_proceeds_usd", tx.get("proceeds_usd")))


def _pay_network_fee(ledger: Ledger, tx: dict, account: int, when: datetime,
                     value: Fraction | None = None) -> Fraction:
    """A fee paid in BTC disposes of that BTC, at its value (`fee_usd`
    unless given), oldest first. Returns the BTC it took."""
    fee = _money(tx["fee_amount"]) if tx["fee_currency"] == "BTC" else Fraction(0)
    if fee:
        pieces = ledger.take(account, fee)
        _dispose(ledger, "fee", pieces, _money(tx["fee_usd"]) if value is None else value, when, None)
    return fee


def _dispose(ledger: Ledger, kind: str, pieces: list[tuple[Lot, Fraction, Fraction]], proceeds: Fraction,
             when: datetime, reporting: str | None) -> None:
    """One row per lot. Each gets its share of the proceeds in cents, and the
    last what is left, so the rows report all of them (the amount realized)."""
    total, left = sum(quantity for _, quantity, _ in pieces), proceeds
    for number, (lot, quantity, basis) in enumerate(pieces, 1):
        share = left if number == len(pieces) else Fraction(_cents(proceeds * quantity / total, ledger.rounding))
        left -= share
        ledger.rows.append(Row(kind, quantity, share, basis, lot.acquired, when, lot.covered, reporting, lot.inherited))


def _form_row(row: Row, year: int, rounding: str) -> dict:
    # Inherited property: Part II, "INHERITED" in column (b) (Form 8949 instructions)
    long_term = row.inherited or _is_long_term(row.acquired.date(), row.sold.date())
    proceeds, cost = _cents(row.proceeds, rounding), _cents(row.basis, rounding)
    return {
        "box": _box(row, year, long_term),
        "description": f"{_btc(row.quantity)} BTC",
        "date_acquired": "INHERITED" if row.inherited else row.acquired.strftime("%m/%d/%Y"),
        "date_sold": row.sold.strftime("%m/%d/%Y"),
        "proceeds": str(proceeds),
        "cost": str(cost),
        # Column (h) is (d) minus (e) as printed, so each row adds up.
        "gain_loss": str(proceeds - cost),
        "holding_period": "LONG" if long_term else "SHORT",
    }


def _is_long_term(acquired: date, sold: date) -> bool:
    """IRS: held "more than 1 year", so the anniversary itself is short-term."""
    try:
        anniversary = acquired.replace(year=acquired.year + 1)
    except ValueError:  # bought on February 29
        anniversary = date(acquired.year + 1, 2, 28)
    return sold > anniversary


def _box(row: Row, year: int, long_term: bool) -> str:
    boxes = BOXES_UNTIL_2024 if year <= 2024 else BOXES_FROM_2025
    if row.kind == "fee":
        reported = "none"  # no broker reports a network fee
    elif row.broker_reporting:
        reported = row.broker_reporting  # what the user's 1099 showed
    elif row.kind == "sale" and year >= 2025:
        reported = "basis" if row.covered else "proceeds"  # the exchange's 1099-DA
    else:
        reported = "none"
    return boxes[reported][long_term]


def _schedule_d(rows: list[dict]) -> dict:
    """Each box's rows add up to its Schedule D line; then each Part's total."""
    lines: dict[str, dict] = {}
    totals = {"short_term": _zero(), "long_term": _zero()}
    for row in rows:
        term = "long_term" if row["holding_period"] == "LONG" else "short_term"
        for bucket in (lines.setdefault(SCHEDULE_D_LINE[row["box"]], _zero()), totals[term]):
            _add(bucket, row)
    return {"lines": lines, **totals}


def _box_totals(rows: list[dict]) -> list[dict]:
    """The Complete Tax Report's table: each box, its line, rows and totals."""
    boxes: dict[str, dict] = {}
    for row in rows:
        box = boxes.setdefault(row["box"], {"box": row["box"], "line": SCHEDULE_D_LINE[row["box"]], "rows": 0,
                                            **_zero()})
        box["rows"] += 1
        _add(box, row)
    return list(boxes.values())


def _gains_summary(rows: list[dict]) -> dict:
    """Proceeds, basis and gain per term, with gains and losses apart."""
    summary: dict = {"number_of_disposals": len(rows), "total": _zero()}
    for term in ("SHORT", "LONG"):
        gains = [Decimal(row["gain_loss"]) for row in rows if row["holding_period"] == term]
        part = {**_zero(), "profits": str(sum(g for g in gains if g > 0) + Decimal("0.00")),
                "losses": str(-sum(g for g in gains if g < 0) + Decimal("0.00"))}
        for row in rows:
            if row["holding_period"] == term:
                _add(part, row)
                _add(summary["total"], row)
        summary["long_term" if term == "LONG" else "short_term"] = part
    return summary


def _zero() -> dict:
    return {column: "0.00" for column in COLUMNS}


def _add(bucket: dict, row: dict) -> None:
    for column in COLUMNS:
        bucket[column] = str(Decimal(bucket[column]) + Decimal(row[column]))


def _income(ledger: Ledger, year: int) -> dict:
    income = {source: Fraction(0) for source in INCOME_SOURCES}
    for when, source, value in ledger.income:
        if when.year == year:
            income[source] += value
    income["Total"] = sum(income.values())
    return {source: str(_cents(value, ledger.rounding)) for source, value in income.items()}


def _cents(value: Fraction, rounding: str) -> Decimal:
    """To the cent, exactly; an exact half cent goes the way `rounding` says."""
    if value < 0:
        raise ValueError("amounts rounded here are never negative")
    hundredths, rest = divmod(value * 100, 1)
    if rest > HALF or (rest == HALF and rounding == ROUND_HALF_UP):
        hundredths += 1
    return (Decimal(int(hundredths)) / 100).quantize(CENT)


def _btc(quantity: Fraction) -> str:
    return str((Decimal(quantity.numerator) / Decimal(quantity.denominator)).quantize(SATS))


def _usd(value) -> str | None:
    """The app's figure (a string or a float) in cents, as the forms print it."""
    return None if value is None else str(Decimal(str(value)).quantize(CENT))


def _unmatched(what: str, mine: list[dict], app: list[dict]) -> list[str]:
    """Items on one side only, each once (a list may hold equal items)."""
    left = sorted(json.dumps(item, sort_keys=True) for item in mine)
    right = sorted(json.dumps(item, sort_keys=True) for item in app)
    only_mine, only_app = list(left), list(right)
    for item in left:
        if item in only_app:
            only_app.remove(item)
            only_mine.remove(item)
    return ([f"{what} only here: {item}" for item in only_mine]
            + [f"{what} only in the app: {item}" for item in only_app])


def _schedule_d_differences(mine: dict, app: dict) -> list[str]:
    found = [f"Schedule D line {line}: here {mine['lines'].get(line)}, in the app {app['lines'].get(line)}"
             for line in sorted(set(mine["lines"]) | set(app["lines"]))
             if mine["lines"].get(line) != app["lines"].get(line)]
    return found + [f"Schedule D {term}: here {mine[term]}, in the app {app[term]}"
                    for term in ("short_term", "long_term") if mine[term] != app[term]]


def _app_gains(summary: dict) -> dict:
    """The app's capital-gains summary under this script's names."""
    def part(values: dict, extra: tuple[str, ...]) -> dict:
        named = {"proceeds": values["proceeds"], "cost": values["basis"], "gain_loss": values["gain"],
                 **{key: values[key] for key in extra}}
        return {key: _usd(value) for key, value in named.items()}
    return {"number_of_disposals": summary["number_of_disposals"], "total": part(summary["total"], ()),
            "short_term": part(summary["short_term"], ("profits", "losses")),
            "long_term": part(summary["long_term"], ("profits", "losses"))}


def _holding_differences(mine: dict, app: list[dict]) -> list[str]:
    lots = [{"account": lot["account"], "acquired": lot["acquired"],
             "quantity": _btc(Fraction(str(lot["quantity"]))), "cost": _usd(lot["cost"])}
            for lot in app if "account" in lot]
    total = [{"quantity": _btc(Fraction(str(lot["quantity"]))), "cost": _usd(lot["cost"])}
             for lot in app if "account" not in lot]
    return (_unmatched("year-end lot", mine["end_of_year_holdings"], lots)
            + _compare("year-end total", [mine["end_of_year_total"]], total))


def _compare(what: str, mine, app) -> list[str]:
    return [] if mine == app else [f"{what}: here {mine}, in the app {app}"]


if __name__ == "__main__":
    sys.exit(main())
