#!/usr/bin/env python3
"""
A second, deliberately simple calculation of a ledger's tax figures, to check
BitcoinTX's own (#150, and #80 item 2). It is written from the rules: the
IRS's (FIFO per account unless a wallet's coins are chosen, "more than one
year", Form 8949's boxes and Schedule D's lines) and the ledger's documented
ones (AGENTS.md "Tax invariants", the AI connector's ledger guide). It
imports nothing from backend/, so a mistake in the app's code can't hide in
both.

It replays the reference test ledger (testdata/reference_ledger.json) in
its accounts (the six fixed accounts and External, and those its
`accounts` list adds: each bitcoin account its own FIFO pile, each
exchange its own 1099-DA switch)
and its tax timezone (`tax_timezone`, else UTC), and gives each year's
Form 8949 rows, Schedule D lines, box totals, gains summary, each
exchange's Sells (Sales by exchange), income, rebates, gifts (with the
cost basis and term of what each took from its lots) and the lots held at
the year's start and end:

    python scripts/independent_figures.py --year 2025          # JSON
    python scripts/independent_figures.py --compare            # against reference_figures.json

`--compare` lists every difference from testdata/reference_figures.json for
2024 and 2025 (`--years` for others). backend/tests/test_independent_figures.py
runs it for every year and fails on a difference. Moments are kept in UTC,
as the ledger stores them; the tax timezone decides every date a rule
reads (the tax year, the holding period, Form 8949's dates, a covered
lot's day, a date originally acquired), as it does in the app.

Amounts stay exact (fractions) until they are rounded to the cent. Three
conventions are the ledger's (AGENTS.md "Tax invariants", Lot cost), shared
on purpose so the two agree to the cent:
- a disposal's proceeds are shared among its lots as a running total in
  cents (#297), so the rows report all of them (the amount realized) and
  none is below zero;
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

Chosen coins (#711): a row leaving one of your wallets, a Transfer to
another account or a Withdrawal, may name the coins that leave instead of
the oldest (specific identification, Treas. Reg. §1.1012-1(j)(2)). A Buy, or
a Deposit into a bitcoin account, names its coins with a `key`; the row
lists `chosen_coins`, each `{"key": …, "btc": …}`, together exactly what
leaves (a Transfer's amount, its fee in it; a Withdrawal's amount and its
BTC fee). The fee takes the oldest of the chosen coins first, then the
amount the rest, as oldest first does with all of a wallet's coins, and a
transfer's coins keep their key wherever they go. An exchange's coins, and
a consolidation's fee, always leave oldest first. A choice the rules don't
allow, or one the wallet doesn't hold when the coins leave, stops the
replay.

A test tool: it lives in scripts/, which no build ships.
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import copy
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from decimal import ROUND_HALF_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "testdata" / "reference_ledger.json"
FIGURES = ROOT / "testdata" / "reference_figures.json"

# Copied, not imported: this script shares no code with the app. Every
# ledger has these, a 1.x ledger's; an `accounts` list adds to them.
FIXED_ACCOUNTS = {
    1: {"name": "Bank", "currency": "USD", "kind": "bank"},
    2: {"name": "Wallet", "currency": "BTC", "kind": "wallet"},
    3: {"name": "Exchange USD", "currency": "USD", "kind": "exchange", "exchange_id": 1, "sends_1099da": True},
    4: {"name": "Exchange BTC", "currency": "BTC", "kind": "exchange", "exchange_id": 1, "sends_1099da": True},
    5: {"name": "BTC Fees", "currency": "BTC", "kind": "fee"},
    6: {"name": "USD Fees", "currency": "USD", "kind": "fee"},
    99: {"name": "External", "currency": None, "kind": "external"},
}
EXTERNAL = 99
# Each kind's currencies (2.0 spec, docs/temp/2.0-accounts.md 5.1): External
# is everything outside the ledger, so it has none.
KIND_CURRENCIES = {"bank": ("USD",), "wallet": ("BTC",), "exchange": ("USD", "BTC"), "fee": ("USD", "BTC"),
                   "external": (None,)}
ACCOUNT_FIELDS = ("id", "name", "kind", "currency")
# `hidden` only keeps an account out of the pickers, `renamed_from` is the
# name it had before the owner renamed it (the seed makes it so), and `why`
# and `since` say what a test row is for and from which version: none
# changes a figure.
NOTES = ("hidden", "renamed_from", "why", "since")
OPTIONAL_FIELDS = ("exchange_id", "sends_1099da") + NOTES
INCOME_SOURCES = ("Income", "Interest", "Reward")
# The rows whose coins a choice may name, and those that may choose (#711,
# docs/temp/2.0-coin-choice.md 2.2): only coins leaving a wallet.
ACQUIRING = ("Buy", "Deposit")
CHOOSING = ("Transfer", "Withdrawal")
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


@dataclass(frozen=True)
class Account:
    """One of the ledger's accounts. `id` is what transactions name, and it
    never changes; `name` is the owner's nickname for it, shown on screen
    and in the report and free to change, so nothing here finds an account
    by its name."""

    id: int
    name: str
    kind: str  # bank, wallet, exchange, fee or external
    currency: str | None  # None: External
    exchange_id: int | None = None  # an exchange's two accounts share it
    # "This exchange sends me a Form 1099-DA": on unless the owner turns it
    # off (2.0 spec 5.2, the owner's decision of 2026-10-15).
    sends_1099da: bool = True

    @property
    def holds_lots(self) -> bool:
        """A bitcoin account: a fee account holds fee lines, never lots (2.0 spec 5.1)."""
        return self.currency == "BTC" and self.kind != "fee"

    @property
    def on_1099da(self) -> bool:
        """Its sales are on a Form 1099-DA: an exchange's BTC account with the switch on."""
        return self.kind == "exchange" and self.currency == "BTC" and self.sends_1099da


@dataclass
class Lot:
    """BTC acquired together: its basis travels with it, by the satoshi."""

    quantity: Fraction  # left
    basis: Fraction  # the cost of what's left
    acquired: datetime
    covered: bool
    order: int
    inherited: bool = False
    # The key of the Buy or Deposit that acquired its coins (#711), wherever
    # they moved since: what a choice names. None: no choice can.
    acquired_by: str | None = None
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
    on_1099da: bool = False  # sold from an account whose exchange sends a 1099-DA
    account: int | None = None  # a sale's exchange account


@dataclass(kw_only=True)
class Ledger:
    """The replay's state: every bitcoin account's lots, and what each
    year's forms need. Built from its accounts, so each pile is there."""

    accounts: dict[int, Account]
    rounding: str
    tax_zone: ZoneInfo
    lots: dict[int, list[Lot]] = field(init=False)
    rows: list[Row] = field(default_factory=list)
    income: list[tuple[datetime, str, Fraction]] = field(default_factory=list)
    rebates: list[tuple[datetime, Fraction, Fraction]] = field(default_factory=list)
    gifts: list[tuple[datetime, str, Fraction, str | None, list[dict]]] = field(default_factory=list)
    holdings: dict[int, list[tuple[int, Lot]]] = field(default_factory=dict)  # year: (account id, lot)
    year: int | None = None
    next_order: int = 0

    def __post_init__(self) -> None:
        # One pile per bitcoin account (2.0 spec 5.15); every other account holds no lots.
        self.lots = {i: [] for i, account in self.accounts.items() if account.holds_lots}

    def day(self, moment: datetime) -> date:
        """A moment's date in the tax timezone: the one every tax rule reads."""
        return moment.astimezone(self.tax_zone).date()

    def tax_year(self, moment: datetime) -> int:
        return self.day(moment).year

    def add_lot(self, account: int, quantity: Fraction, basis: Fraction, acquired: datetime, covered: bool,
                inherited: bool = False, acquired_by: str | None = None) -> None:
        self.lots[account].append(Lot(quantity, basis, acquired, covered, self.next_order, inherited, acquired_by))
        self.next_order += 1

    def take(self, account: int, quantity: Fraction,
             choice: dict[str, Fraction] | None = None) -> list[tuple[Lot, Fraction, Fraction]]:
        """Remove `quantity` BTC oldest acquisition first: (lot, BTC, basis) per
        piece. With a choice (key: BTC still to take), only the lots of those
        acquisitions, each giving at most what's left of its BTC, the first
        made first; what it takes comes off the choice, so a fee's take and
        its amount's share one."""
        pieces = []
        for lot in sorted(self.lots[account], key=lambda lot: (lot.acquired, lot.order)):
            if quantity == 0:
                break
            used = min(quantity, lot.quantity)
            if choice is not None:
                used = min(used, choice.get(lot.acquired_by, Fraction(0)))
                if not used:  # not chosen, or its acquisition's BTC all taken
                    continue
                choice[lot.acquired_by] -= used
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
        return _share_so_far(lot.cost, btc, lot.total, self)


def read_accounts(data: dict) -> dict[int, Account]:
    """A ledger file's accounts by id: the six fixed accounts and External,
    which every ledger has, and its `accounts` list, which adds the accounts
    2.0 lets an owner make (2.0 spec 5.15: the reference ledger lists only
    its new ones) and may give a fixed one another nickname or 1099-DA
    switch. A list that can't be read one way only stops here, before any
    figure."""
    accounts = {i: _account({"id": i, **a}) for i, a in FIXED_ACCOUNTS.items()}
    listed: set[int] = set()
    for entry in data.get("accounts", []):
        account = _account(entry)
        if account.id in listed:
            raise ValueError(f"The ledger's accounts list has account {account.id} twice.")
        listed.add(account.id)
        fixed = accounts.get(account.id)
        if account.id in FIXED_ACCOUNTS and (account.kind, account.currency) != (fixed.kind, fixed.currency):
            raise ValueError(f"The ledger's accounts list: account {account.id} is the fixed {fixed.name}, "
                             f"a {fixed.kind!r} account in {fixed.currency!r}; only its nickname or switch can change.")
        accounts[account.id] = account
    _check_exchanges(accounts)
    return accounts


def replay(transactions: list[dict], rounding: str = ROUND_HALF_UP, *,
           accounts: dict[int, Account] | None = None, tax_timezone: str = "UTC") -> Ledger:
    """Every transaction in time order (the file's order on a tie), in the
    ledger's accounts (the fixed ones when None; an empty book stays empty)."""
    accounts = read_accounts({}) if accounts is None else accounts
    _check_accounts(transactions, accounts)
    _check_choices(transactions, accounts)
    ledger = Ledger(accounts=accounts, rounding=rounding, tax_zone=_tax_zone(tax_timezone))
    handlers = {"Deposit": _deposit, "Buy": _buy, "Sell": _sell, "Withdrawal": _withdrawal, "Transfer": _transfer}
    ordered = sorted(enumerate(transactions), key=lambda pair: (_moment(pair[1]["timestamp"]), pair[0]))
    for _, tx in ordered:
        when = _moment(tx["timestamp"])
        _close_years_before(ledger, ledger.tax_year(when))
        handlers[tx["type"]](ledger, tx, when)
    if ledger.year is not None:
        _close_years_before(ledger, ledger.year + 1)
    return ledger


def replay_ledger(data: dict, rounding: str = ROUND_HALF_UP) -> Ledger:
    """A ledger file replayed in its own accounts and tax timezone."""
    return replay(data["transactions"], rounding, accounts=read_accounts(data),
                  tax_timezone=data.get("tax_timezone", "UTC"))


def year_figures(ledger: Ledger, year: int) -> dict:
    rows = [_form_row(row, year, ledger) for row in ledger.rows if ledger.tax_year(row.sold) == year]
    # The account by its nickname, as the report shows it.
    holdings = [{"account": ledger.accounts[account].name, "acquired": lot.acquired.isoformat(),
                 "quantity": _btc(lot.quantity), "cost": str(_cents(lot.basis, ledger.rounding))}
                for account, lot in ledger.holdings.get(year, [])]
    # What the year starts with is what the year before ended with: none
    # before the ledger's first year.
    opening = [{"account": ledger.accounts[account].name, "quantity": _btc(lot.quantity),
                "cost": str(_cents(lot.basis, ledger.rounding))} for account, lot in ledger.holdings.get(year - 1, [])]
    return {
        "tax_timezone": ledger.tax_zone.key,
        "form_8949": rows,
        "schedule_d": _schedule_d(rows),
        "boxes": _box_totals(rows),
        "sales_by_exchange": _sales_by_exchange(ledger, year),
        "gains": _gains_summary(rows),
        "income": _income(ledger, year),
        "rebates": [{"date": when.isoformat(), "amount": _btc(amount), "value_usd": str(_cents(value, ledger.rounding))}
                    for when, amount, value in ledger.rebates if ledger.tax_year(when) == year],
        "gifts_donations_lost": [
            {"date": when.isoformat(), "type": kind, "amount": _btc(amount), "fmv_usd": _usd(fmv), "lots_by_term": terms}
            for when, kind, amount, fmv, terms in ledger.gifts if ledger.tax_year(when) == year],
        "start_of_year_holdings": opening,
        "end_of_year_holdings": holdings,
        "end_of_year_total": {"quantity": _btc(sum(Fraction(lot["quantity"]) for lot in holdings)),
                              "cost": str(sum(Decimal(lot["cost"]) for lot in holdings))},
    }


def differences(mine: dict, app: dict) -> list[str]:
    """Every figure where this calculation and the app's saved one disagree."""
    report = app["report"]
    found = _compare("tax timezone", mine["tax_timezone"], report["tax_timezone"])
    found += _unmatched("Form 8949 row", mine["form_8949"], app["form_8949"])
    found += _schedule_d_differences(mine["schedule_d"], app["schedule_d"])
    found += _unmatched("box total", mine["boxes"], [
        {"box": b["box"], "line": b["line"], "rows": b["rows"], **{c: _usd(b[c]) for c in COLUMNS}}
        for b in report["form_8949_boxes"]])
    found += _compare("sales by exchange", mine["sales_by_exchange"], [
        {"exchange": s["exchange"], "sends_1099da": s["sends_1099da"], "boxes": s["boxes"], "rows": s["rows"],
         **{c: _usd(s[c]) for c in COLUMNS}} for s in report["sales_by_exchange"]])
    found += _compare("gains summary", mine["gains"], _app_gains(report["capital_gains_summary"]))
    found += _compare("income", mine["income"], {k: _usd(v) for k, v in report["income_summary"].items()})
    found += _unmatched("rebate", mine["rebates"], [
        {"date": r["date"], "amount": _btc(Fraction(str(r["amount"]))), "value_usd": _usd(r["value_usd"])}
        for r in report["rebates"]])
    found += _unmatched("gift, donation or loss", mine["gifts_donations_lost"], [
        {"date": g["date"], "type": g["type"], "amount": _btc(Fraction(str(g["amount"]))), "fmv_usd": _usd(g["fmv_usd"]),
         "lots_by_term": [{"term": t["term"], "btc": _btc(Fraction(str(t["btc"]))), "cost_basis": _usd(t["cost_basis"])}
                          for t in g["lots_by_term"]]}
        for g in report["gifts_donations_lost"]])
    found += _unmatched("start-of-year lot", mine["start_of_year_holdings"], [
        {"account": lot["account"], "quantity": _btc(Fraction(str(lot["quantity"]))),
         # the report gives the average cost of what's left: its cost is that times the BTC, to the cent
         "cost": _usd(Decimal(str(lot["avg_cost_basis"])) * Decimal(str(lot["quantity"])))}
        for lot in report["start_of_year_balances"]])
    return found + _holding_differences(mine, report["end_of_year_balances"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--year", type=int, help="print one year's figures as JSON")
    parser.add_argument("--compare", action="store_true", help="compare with the reference figures")
    parser.add_argument("--years", type=int, nargs="+", default=[2024, 2025])
    parser.add_argument("--rounding", choices=ROUNDING, default="half-up",
                        help="how an exact half cent rounds (the app: half-up)")
    args = parser.parse_args()
    ledger = replay_ledger(json.loads(LEDGER.read_text()), ROUNDING[args.rounding])
    if args.year:
        print(json.dumps(year_figures(ledger, args.year), indent=1))
        return 0
    saved = json.loads(FIGURES.read_text())["years"]
    found = [f"{year}: {line}" for year in args.years
             for line in differences(year_figures(ledger, year), saved[str(year)])]
    print("\n".join(found) or f"No differences in {', '.join(map(str, args.years))}.")
    return 1 if found else 0


def _account(entry: dict) -> Account:
    """One entry of an accounts list, every field checked: nothing is guessed."""
    if not isinstance(entry.get("id"), int) or isinstance(entry["id"], bool):
        raise ValueError(f"An account in the ledger's accounts list has no whole-number id: {entry}.")
    where = f"The ledger's accounts list: account {entry['id']}"
    _check_fields(entry, where)
    _check_kind(entry, where)
    return Account(**{key: value for key, value in entry.items() if key not in NOTES})


def _check_fields(entry: dict, where: str) -> None:
    missing = [key for key in ACCOUNT_FIELDS if key not in entry]
    if missing:
        raise ValueError(f"{where} has no {', '.join(missing)}.")
    unknown = [key for key in entry if key not in ACCOUNT_FIELDS + OPTIONAL_FIELDS]
    if unknown:
        raise ValueError(f"{where} has fields this check doesn't know: {', '.join(unknown)}.")


def _check_kind(entry: dict, where: str) -> None:
    """Its kind, currency, exchange and switch agree (2.0 spec 5.1, 5.2)."""
    kind = entry["kind"]
    if entry["currency"] not in KIND_CURRENCIES.get(kind, ()):
        raise ValueError(f"{where} is a {kind!r} account in {entry['currency']!r}, which no account is.")
    if (kind == "external") != (entry["id"] == EXTERNAL):
        raise ValueError(f"{where}: External is account {EXTERNAL}, and only External is.")
    exchange_id = entry.get("exchange_id")
    if (kind == "exchange") != (isinstance(exchange_id, int) and not isinstance(exchange_id, bool)):
        raise ValueError(f"{where}: an exchange's account names its exchange (exchange_id), and no other does.")
    if "sends_1099da" in entry and (kind != "exchange" or not isinstance(entry["sends_1099da"], bool)):
        raise ValueError(f"{where}: sends_1099da is an exchange's switch, true or false.")


def _check_exchanges(accounts: dict[int, Account]) -> None:
    """Each exchange has one dollar and one bitcoin account, one switch for both (2.0 spec 5.1, 5.2)."""
    exchanges: dict[int, list[Account]] = {}
    for account in accounts.values():
        if account.exchange_id is not None:
            exchanges.setdefault(account.exchange_id, []).append(account)
    for exchange, pair in sorted(exchanges.items()):
        if sorted(account.currency for account in pair) != ["BTC", "USD"]:
            raise ValueError(f"Exchange {exchange} in the ledger's accounts list needs one USD and one BTC account.")
        if pair[0].sends_1099da != pair[1].sends_1099da:
            raise ValueError(f"Exchange {exchange}'s two accounts disagree on its 1099-DA switch (sends_1099da).")


def _check_accounts(transactions: list[dict], accounts: dict[int, Account]) -> None:
    """Each transaction names the ledger's accounts, the way its type allows
    (2.0 spec 5.5). One that doesn't stops the calculation, never skipped
    (5.15): a skipped row would leave its figures out unseen."""
    for position, tx in enumerate(transactions, start=1):
        number = _number(position, tx)
        source, destination = (_named_account(number, tx[side], accounts)
                               for side in ("from_account_id", "to_account_id"))
        if tx["type"] not in ROUTES:
            raise ValueError(f"Transaction {number} is a {tx['type']!r}, which isn't one of {', '.join(ROUTES)}.")
        problem = ROUTES[tx["type"]](source, destination, accounts)
        if problem:
            raise ValueError(f"Transaction {number}: {problem}")


def _number(position: int, tx: dict) -> int:
    """How a message names a row: its id in the ledger, else its place in the file."""
    return position if tx.get("id") is None else tx["id"]


def _named_account(number: int, account_id: int, accounts: dict[int, Account]) -> Account:
    if account_id not in accounts:
        raise ValueError(f"Transaction {number} names account {account_id}, "
                         "which the ledger's accounts list doesn't have.")
    account = accounts[account_id]
    if account.kind == "fee":
        # It holds the ledger's fee lines; a fee is paid from the paying account (2.0 spec 5.1, 5.5).
        raise ValueError(f"Transaction {number} names account {account_id} ({account.name}), a fee account, "
                         "which no transaction names.")
    return account


# 2.0 spec 5.5's rules per type, in its words: what's wrong, or None.
def _deposit_route(source: Account, destination: Account, accounts: dict[int, Account]) -> str | None:
    if source.kind != "external":
        return "A Deposit comes from External."
    if destination.kind == "external":
        return "A Deposit goes into one of your accounts, not External."
    return None


def _withdrawal_route(source: Account, destination: Account, accounts: dict[int, Account]) -> str | None:
    if source.kind == "external":
        return "A Withdrawal comes from one of your accounts, not External."
    if destination.kind != "external":
        return "A Withdrawal goes to External."
    return None


def _transfer_route(source: Account, destination: Account, accounts: dict[int, Account]) -> str | None:
    if "external" in (source.kind, destination.kind):
        return "A Transfer is between two of your accounts, not External."
    if source.currency != destination.currency:
        return ("A Transfer stays in one currency: bitcoin between bitcoin accounts, "
                "dollars between dollar accounts.")
    if source.id == destination.id and not source.holds_lots:
        return "A Transfer goes to another account: only a bitcoin account can send to itself (a consolidation)."
    return None


def _buy_route(source: Account, destination: Account, accounts: dict[int, Account]) -> str | None:
    if source.currency != "USD" or source.kind not in ("bank", "exchange"):
        return "A Buy is paid from a bank or from an exchange's USD account."
    if destination.kind != "exchange" or destination.currency != "BTC":
        return "A Buy's bitcoin goes into an exchange's BTC account."
    if source.kind == "exchange" and source.exchange_id != destination.exchange_id:
        own = _exchange_account(accounts, source.exchange_id, "BTC")
        return f"A Buy paid from {source.name} goes into {own.name}: an exchange's dollars buy only on that exchange."
    return None


def _sell_route(source: Account, destination: Account, accounts: dict[int, Account]) -> str | None:
    if source.kind != "exchange" or source.currency != "BTC":
        return "A Sell is from an exchange's BTC account."
    own = _exchange_account(accounts, source.exchange_id, "USD")
    if destination.id != own.id:
        return f"A Sell from {source.name} goes into {own.name}."
    return None


ROUTES = {"Deposit": _deposit_route, "Withdrawal": _withdrawal_route, "Transfer": _transfer_route,
          "Buy": _buy_route, "Sell": _sell_route}


def _check_choices(transactions: list[dict], accounts: dict[int, Account]) -> None:
    """Each key names one acquisition, and each choice its coins, as the app
    takes them (#711, docs/temp/2.0-coin-choice.md 4.5): one that can't be
    read one way stops here, before any figure, never skipped."""
    keys = _keys(transactions, accounts)
    for position, tx in enumerate(transactions, start=1):
        if tx.get("chosen_coins") not in (None, []):  # nothing chosen: oldest first
            _check_choice(_number(position, tx), tx, accounts, keys)


def _keys(transactions: list[dict], accounts: dict[int, Account]) -> set[str]:
    """Every key, each on the one Buy, or Deposit into a bitcoin account, whose coins it names."""
    rows: dict[str, int] = {}
    for position, tx in enumerate(transactions, start=1):
        if "key" not in tx:
            continue
        number, key = _number(position, tx), tx["key"]
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"Transaction {number}'s key is {key!r}: a key is a name, in text.")
        if tx["type"] not in ACQUIRING or not accounts[tx["to_account_id"]].holds_lots:
            raise ValueError(f"Transaction {number} has a key, {key!r}, but didn't acquire bitcoin: only a Buy, "
                             "or a Deposit into a bitcoin account, has coins a choice can name.")
        if key in rows:
            raise ValueError(f"Transaction {number}'s key {key!r} is transaction {rows[key]}'s too: "
                             "a key names one acquisition.")
        rows[key] = number
    return set(rows)


def _check_choice(number: int, tx: dict, accounts: dict[int, Account], keys: set[str]) -> None:
    source = accounts[tx["from_account_id"]]
    # (j)(1): the units in a single wallet. At an exchange the coins are
    # identified to the broker, so they leave oldest first, as its 1099-DA
    # reports them (#711's call (g)).
    if tx["type"] not in CHOOSING or source.kind != "wallet":
        raise ValueError(f"Transaction {number}, a {tx['type']} from {source.name}, chooses coins: only coins "
                         "leaving one of your wallets, by a Transfer or a Withdrawal, can be chosen; an exchange's "
                         "leave oldest first, as its Form 1099-DA reports them.")
    if tx["to_account_id"] == source.id:
        raise ValueError(f"Transaction {number} moves coins within {source.name}: that records only its network "
                         "fee, from the oldest coins, so it can't choose coins.")
    chosen, leaving = sum(_chosen_lines(number, tx, keys).values()), _leaving(tx)
    # No half choice (#711's call (c)): one that fell short would fill the
    # rest by a rule of its own.
    if chosen != leaving:
        raise ValueError(f"Transaction {number} chooses {_btc(chosen)} BTC, but {_btc(leaving)} BTC leaves "
                         f"{source.name}: a choice covers all of it, the network fee included, or there is none "
                         "and the oldest coins leave.")


def _chosen_lines(number: int, tx: dict, keys: set[str]) -> dict[str, Fraction]:
    """A choice's BTC by key, one line per acquisition."""
    lines = tx["chosen_coins"]
    if not isinstance(lines, list) or not all(isinstance(line, dict) and set(line) == {"key", "btc"}
                                              for line in lines):
        raise ValueError(f"Transaction {number}'s chosen_coins is a list of lines, each with only a key and a btc.")
    chosen: dict[str, Fraction] = {}
    for line in lines:
        key = line["key"]
        if not isinstance(key, str) or key not in keys:
            raise ValueError(f"Transaction {number} chooses the coins from {key!r}, which is no Buy's or Deposit's key.")
        if key in chosen:
            raise ValueError(f"Transaction {number} chooses the coins from {key!r} twice: one line per acquisition.")
        chosen[key] = _chosen_btc(number, key, line["btc"])
    return chosen


def _chosen_btc(number: int, key: str, value) -> Fraction:
    """A line's BTC: above 0, to the satoshi, as the app takes it."""
    try:
        btc = None if isinstance(value, bool) else Fraction(Decimal(str(value)))
    except (InvalidOperation, ValueError, OverflowError):  # not a number; NaN; infinity
        btc = None
    if btc is None or btc <= 0 or (btc * 100_000_000).denominator != 1:
        raise ValueError(f"Transaction {number} chooses {value!r} BTC of the coins from {key!r}: a choice is above "
                         "0 BTC, to the satoshi (at most 8 places).")
    return btc


def _leaving(tx: dict) -> Fraction:
    """What leaves the wallet: a Transfer's amount, its network fee in it; a
    Withdrawal's amount, its network fee on top (AGENTS.md, "Transfer",
    "Withdrawal fee")."""
    return _money(tx["amount"]) + (_btc_fee(tx) if tx["type"] == "Withdrawal" else 0)


def _exchange_account(accounts: dict[int, Account], exchange_id: int | None, currency: str) -> Account:
    """An exchange's dollar or bitcoin account (read_accounts made sure it has one of each)."""
    return next(a for a in accounts.values() if a.exchange_id == exchange_id and a.currency == currency)


def _tax_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"The tax timezone {name!r} isn't a time zone this computer knows.") from None


def _moment(text: str) -> datetime:
    """A transaction's time, in UTC: one without a time zone could be any day's."""
    given = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if given.tzinfo is None:
        raise ValueError(f"The time {text!r} has no time zone: write it in UTC, ending in Z.")
    return given.astimezone(timezone.utc)


def _noon_of(text: str, zone: ZoneInfo) -> datetime:
    """Noon of a date originally acquired, in the tax timezone (AGENTS.md,
    "Holding period"): a time given with it stands for its date there, one
    without a timezone for the date written."""
    given = datetime.fromisoformat(text.replace("Z", "+00:00"))
    day = given.astimezone(zone).date() if given.tzinfo else given.date()
    return datetime.combine(day, time(12), tzinfo=zone).astimezone(timezone.utc)


def _close_years_before(ledger: Ledger, year: int) -> None:
    """Keep each year's closing lots, once the ledger has moved past it."""
    for closed in range(ledger.year or year, year):
        ledger.holdings[closed] = [(account, copy(lot))
                                   for account, lots in ledger.lots.items() for lot in lots]
    ledger.year = max(ledger.year or year, year)


def _deposit(ledger: Ledger, tx: dict, when: datetime) -> None:
    if tx["to_account_id"] not in ledger.lots:
        return
    amount, value = _money(tx["amount"]), _money(tx.get("cost_basis_usd"))
    # A MyBTC or Gift deposit's holding period runs from when it was first
    # acquired (the giver's date for a gift: IRC §1223(2)). Inherited coins
    # are acquired at the death (IRC §1014: their basis is their value then)
    # and long-term whenever sold (§1223(9)). That is a date: noon of it,
    # never after the deposit.
    acquired = min(_noon_of(tx["acquired_at"], ledger.tax_zone), when) if tx.get("acquired_at") else when
    ledger.add_lot(tx["to_account_id"], amount, value, acquired, covered=False,
                   inherited=tx.get("source") == "Inherited", acquired_by=tx.get("key"))
    # Income is its value at receipt, which is also its basis; a rebate is
    # valued the same way but lowers a purchase price instead of being income.
    if tx.get("source") in INCOME_SOURCES:
        ledger.income.append((when, tx["source"], value))
    elif tx.get("source") == "Rebate":
        ledger.rebates.append((when, amount, value))


def _buy(ledger: Ledger, tx: dict, when: datetime) -> None:
    # The dollar fee is part of what the BTC cost (IRC §1012).
    basis = _money(tx["cost_basis_usd"]) + _money(tx["fee_amount"])
    # Treas. Reg. §1.6045-1(a)(15)(i)(J): covered from 2026-01-01 in the tax
    # timezone, so 2026-01-01 03:00 UTC is still 2025-12-31 in America/Chicago.
    covered = ledger.day(when) >= COVERED_FROM
    ledger.add_lot(tx["to_account_id"], _money(tx["amount"]), basis, when, covered=covered, acquired_by=tx.get("key"))


def _sell(ledger: Ledger, tx: dict, when: datetime) -> None:
    # The fee comes off the gross proceeds (amount realized, IRC §1001).
    proceeds = _gross_proceeds(tx) - _money(tx["fee_amount"])
    pieces = ledger.take(tx["from_account_id"], _money(tx["amount"]))
    _dispose(ledger, "sale", pieces, proceeds, when, tx.get("broker_reporting"),
             on_1099da=ledger.accounts[tx["from_account_id"]].on_1099da, account=tx["from_account_id"])


def _withdrawal(ledger: Ledger, tx: dict, when: datetime) -> None:
    account = tx["from_account_id"]
    if account not in ledger.lots:
        return
    purpose, choice = tx["purpose"], _choice(ledger, tx, account)
    if purpose in NOT_SALES:
        _pay_network_fee(ledger, tx, account, when, choice=choice)
        amount = _money(tx["amount"])
        terms = _by_term(ledger, ledger.take(account, amount, choice), when)
        ledger.gifts.append((when, purpose, amount, tx.get("fmv_usd"), terms))
        return
    # The fee paid to make a spend is a cost of it: it comes off what was
    # received, and the two realize what was received (Treas. Reg.
    # §1.1001-7(b)(2)(ii)(A), Example 4; #157).
    received = _gross_proceeds(tx)
    # A spend with no network fee has no fee value: the app stores none (#703)
    fee_value = min(_fee_value(tx), received) if _btc_fee(tx) else Fraction(0)
    # Its fee goes where the user's 1099-DA put the spend, if they said (#549)
    reporting = tx.get("broker_reporting")
    _pay_network_fee(ledger, tx, account, when, value=fee_value, reporting=reporting, choice=choice)
    pieces = ledger.take(account, _money(tx["amount"]), choice)
    _dispose(ledger, "spend", pieces, received - fee_value, when, reporting)


def _transfer(ledger: Ledger, tx: dict, when: datetime) -> None:
    source, destination = tx["from_account_id"], tx["to_account_id"]
    if source not in ledger.lots:
        return
    choice = _choice(ledger, tx, source)
    fee = _pay_network_fee(ledger, tx, source, when, choice=choice)
    if destination == source:
        # A consolidation, or a move between wallets pooled as one (#159):
        # only the fee leaves the account (IRS digital-asset FAQ Q81, Q97).
        return
    # The amount left the source including the fee; what arrives keeps each
    # lot's date and its share of basis: moving your own coins isn't a sale.
    for lot, quantity, basis in ledger.take(source, _money(tx["amount"]) - fee, choice):
        ledger.add_lot(destination, quantity, basis, lot.acquired, covered=False, inherited=lot.inherited,
                       acquired_by=lot.acquired_by)


def _choice(ledger: Ledger, tx: dict, account: int) -> dict[str, Fraction] | None:
    """A row's chosen coins, as the BTC still to take of each acquisition,
    once the wallet is seen to hold them all as the coins leave ((j)(2): the
    units identified are units in the wallet). None: oldest first."""
    if tx.get("chosen_coins") in (None, []):
        return None
    choice = {line["key"]: _money(line["btc"]) for line in tx["chosen_coins"]}
    for key, btc in choice.items():
        held = sum((lot.quantity for lot in ledger.lots[account] if lot.acquired_by == key), Fraction(0))
        if held < btc:
            raise ValueError(f"The {tx['type']} of {tx['timestamp']} chose {_btc(btc)} BTC of the coins from {key!r}, "
                             f"but {ledger.accounts[account].name} holds {_btc(held)} BTC of them then.")
    return choice


def _by_term(ledger: Ledger, pieces: list[tuple[Lot, Fraction, Fraction]], when: datetime) -> list[dict]:
    """A gift's, donation's or loss's BTC and cost basis held more than a
    year, then a year or less (#160): a donation's deduction depends on both."""
    terms: dict[str, list[Fraction]] = {}
    for lot, quantity, basis in pieces:
        long_term = lot.inherited or _is_long_term(ledger.day(lot.acquired), ledger.day(when))
        part = terms.setdefault("LONG" if long_term else "SHORT", [Fraction(0), Fraction(0)])
        part[0] += quantity
        part[1] += basis
    return [{"term": term, "btc": _btc(terms[term][0]), "cost_basis": str(_cents(terms[term][1], ledger.rounding))}
            for term in ("LONG", "SHORT") if term in terms]


def _money(value: str | None) -> Fraction:
    return Fraction(Decimal(str(value))) if value not in (None, "") else Fraction(0)


def _gross_proceeds(tx: dict) -> Fraction:
    """What the BTC brought before fees (the ledger guide's proceeds_usd)."""
    return _money(tx.get("gross_proceeds_usd", tx.get("proceeds_usd")))


def _pay_network_fee(ledger: Ledger, tx: dict, account: int, when: datetime, *,
                     value: Fraction | None = None, reporting: str | None = None,
                     choice: dict[str, Fraction] | None = None) -> Fraction:
    """A fee paid in BTC disposes of that BTC, at its value (`fee_usd`
    unless given), oldest first: of the chosen coins, when the row chose
    them, since they pay it (#711's call (b); IRS digital-asset FAQ Q81,
    Q97). Returns the BTC it took. `reporting`: what a spend's 1099-DA
    showed for it, when the user recorded that (#549); a gift's or a
    transfer's fee has none."""
    fee = _btc_fee(tx)
    if fee:
        pieces = ledger.take(account, fee, choice)
        _dispose(ledger, "fee", pieces, _fee_value(tx) if value is None else value, when, reporting)
    return fee


def _btc_fee(tx: dict) -> Fraction:
    """The BTC a row's network fee takes from its account: none when the fee is in dollars."""
    return _money(tx["fee_amount"]) if tx["fee_currency"] == "BTC" else Fraction(0)


def _fee_value(tx: dict) -> Fraction:
    """A bitcoin fee's USD value. The app prices a fee that has none, or
    refuses the row; it never counts one as $0, so one missing here stops
    the replay instead of being guessed."""
    if tx.get("fee_usd") in (None, ""):
        raise ValueError(f"The {tx['type']} of {tx['timestamp']} pays a network fee with no USD value (fee_usd).")
    return _money(tx["fee_usd"])


def _dispose(ledger: Ledger, kind: str, pieces: list[tuple[Lot, Fraction, Fraction]], proceeds: Fraction,
             when: datetime, reporting: str | None, *, on_1099da: bool = False, account: int | None = None) -> None:
    """One row per lot, each with its share of the proceeds as a running
    total in cents: the proceeds for the BTC so far with this lot, less
    without it. So the rows report all of the proceeds (the amount realized)
    and none is below zero (#297)."""
    total, before = sum(quantity for _, quantity, _ in pieces), Fraction(0)
    for lot, quantity, basis in pieces:
        share = _share_so_far(proceeds, before + quantity, total, ledger) - _share_so_far(proceeds, before, total, ledger)
        before += quantity
        ledger.rows.append(Row(kind, quantity, share, basis, lot.acquired, when, covered=lot.covered,
                               broker_reporting=reporting, inherited=lot.inherited, on_1099da=on_1099da,
                               account=account))


def _share_so_far(value: Fraction, part: Fraction, whole: Fraction, ledger: Ledger) -> Fraction:
    """`part` of `whole`'s share of `value`, in cents (all of it: exactly `value`)."""
    return value if part >= whole else Fraction(_cents(value * part / whole, ledger.rounding))


def _form_row(row: Row, year: int, ledger: Ledger) -> dict:
    acquired, sold = ledger.day(row.acquired), ledger.day(row.sold)
    # Inherited property: Part II, "INHERITED" in column (b) (Form 8949 instructions)
    long_term = row.inherited or _is_long_term(acquired, sold)
    proceeds, cost = _cents(row.proceeds, ledger.rounding), _cents(row.basis, ledger.rounding)
    return {
        "box": _box(row, year, long_term),
        "description": f"{_btc(row.quantity)} BTC",
        "date_acquired": "INHERITED" if row.inherited else acquired.strftime("%m/%d/%Y"),
        "date_sold": sold.strftime("%m/%d/%Y"),
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
    if row.broker_reporting:
        reported = row.broker_reporting  # what the user's 1099 showed (a fee's: its spend's, #549)
    elif row.kind == "sale" and row.on_1099da and year >= 2025:
        reported = "basis" if row.covered else "proceeds"  # the exchange's 1099-DA
    else:
        reported = "none"  # a spend, a network fee, or a sale no broker reports
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


def _sales_by_exchange(ledger: Ledger, year: int) -> list[dict]:
    """Each exchange with Sells in the year, by its id (2.0 spec 5.7): its
    name (its accounts are "<name> USD" and "<name> BTC", 5.1), whether it
    sends a 1099-DA, and its Sells' boxes, rows and totals, to set beside
    the form it sends. Sells only: a network fee is on no 1099-DA by itself."""
    exchanges: dict[int, dict] = {}
    for row in ledger.rows:
        if row.kind != "sale" or ledger.tax_year(row.sold) != year:
            continue
        account, form = ledger.accounts[row.account], _form_row(row, year, ledger)
        sales = exchanges.setdefault(account.exchange_id, {
            "exchange": account.name.removesuffix(" BTC"), "sends_1099da": account.sends_1099da,
            "boxes": set(), "rows": 0, **_zero()})
        sales["boxes"].add(form["box"])
        sales["rows"] += 1
        _add(sales, form)
    return [{**sales, "boxes": sorted(sales["boxes"])} for _, sales in sorted(exchanges.items())]


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
        if ledger.tax_year(when) == year:
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
    """To the satoshi, fixed-point as the app writes it: str() would write 1 sat as "1E-8" (#703)."""
    return format((Decimal(quantity.numerator) / Decimal(quantity.denominator)).quantize(SATS), "f")


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
