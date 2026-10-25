"""
scripts/seed_ledger.py loads the full test ledger (2023-2026) into a running
BitcoinTX over its API. Here against the in-process app on a fresh database:
it loads with the price source Off and asks for no price; every year has
every kind of transaction and every report something in each part (every
Form 8949 box of 2024, 2025 and 2026); every account route the app offers
is in it, between 2.0's multiple wallets, exchanges or accounts too (its
accounts list, made through the account API first); and it refuses a ledger
that isn't empty and the Mac app's address.

2.0's own dimensions (#702) each fail here once empty: each kind of
transaction in more than one account of each kind that holds it, each
route between more than one pair of accounts, each exchange's Sells in the
boxes its 1099-DA switch gives, every Broker form choice against each
switch, gains and losses of both terms and inherited coins in every forms
year, holdings at each year's start, a hidden and a renamed account on the
dashboard, and each Ledger Review item a row can show. And chosen coins
(#711, #730): each withdrawal purpose and each move out of a wallet by a
choice, in 2025 and 2026, inherited coins chosen, a spend's coins of both
terms with its fee, one purchase chosen across two lots, and a choice equal
to oldest first beside choices that aren't.
"""

import csv
import importlib.util
import io
import json
import os
import re
from collections import defaultdict
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import get_args

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.transaction import Transaction
from backend.schemas.transaction import BrokerReporting
from backend.services import first_run, outbound
from backend.services.transaction import DEPOSIT_SOURCES, TX_TYPES, WITHDRAWAL_PURPOSES
from backend.services.reports.form_8949 import INHERITED, build_form_8949_and_schedule_d
from backend.services.reports.reporting_core import generate_report_data
from backend.services.review import build_review
from backend.tests.independent_calc import independent_figures


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[2] / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed_ledger = _script("seed_ledger")
reference_figures = _script("reference_figures")

USER, PASSWORD = "seed-user", "seed-password-123"

# The box of every 2026 disposal, by date sold (the "why" notes of testdata/reference_ledger.json)
BOXES_2026 = {
    "01/15/2026": {"K"}, "02/02/2026": {"J"}, "02/09/2026": {"H"}, "03/16/2026": {"I"},
    "05/04/2026": {"G"}, "06/01/2026": {"I"}, "07/01/2026": {"L"}, "08/03/2026": {"G"},
    "08/28/2026": {"I"}, "09/01/2026": {"L"}, "09/02/2026": {"K"}, "09/05/2026": {"L"}, "09/10/2026": {"L"},
    "09/13/2026": {"K"},
    # 2.0's rows (#354): Kraken's sales of coins bought there (G) and moved in from the Coldcard (H),
    # Overseas' (no 1099-DA: I), and the network fees of the moves, the gift and the spend between them (I)
    "02/16/2026": {"G"}, "03/23/2026": {"H"}, "05/11/2026": {"I"},
    **{day: {"I"} for day in ("03/02/2026", "04/06/2026", "04/20/2026", "06/03/2026", "06/10/2026", "06/24/2026",
                              "07/07/2026", "07/21/2026")},
    # #702's: Overseas' gift held since 2023 (L), its own coins (I: the switch is off), its sale with basis
    # reported (G by the override), Kraken's long-term coins (K), its covered coins with proceeds only
    # (H), its spends' choices (G, I), the Jade's donation fee (L), and the network fees and the $0 spend (I)
    "06/16/2026": {"L"}, "06/17/2026": {"I"}, "06/23/2026": {"I"}, "06/25/2026": {"G"}, "08/06/2026": {"L"},
    "08/12/2026": {"K"}, "08/18/2026": {"H", "K"}, "08/20/2026": {"G"}, "08/21/2026": {"I"},
    **{day: {"I"} for day in ("06/30/2026", "07/02/2026", "08/10/2026", "08/25/2026")},
    # #730's chosen coins: the fee of the Sparrow's move to the Jade (L), the Jade's spends of the inherited
    # and the 2023 coins (L), the fee of its move to Kraken (L), and Kraken's sale of the coins moved in (K)
    **{day: {"L"} for day in ("08/27/2026", "09/03/2026", "09/04/2026", "09/07/2026")}, "09/09/2026": {"K"},
}
YEARS = [2023, 2024, 2025, 2026]
# Each year: every deposit source and withdrawal purpose the app has (its own
# lists, so a new one fails here until the reference ledger has it), cash
# withdrawals, transfers both ways, buys and sells
KINDS = {
    *(f"Deposit {s}" for s in DEPOSIT_SOURCES),
    *(f"Withdrawal {p}" for p in (*WITHDRAWAL_PURPOSES, "cash")),
    "Transfer to the exchange", "Transfer from the exchange", "Transfer cash", "Buy", "Sell",
}
# Every account route the app offers (2.0 spec 5.5), by kind (type, from, to)
YOURS = ("bank", "wallet", "exchange USD", "exchange BTC")
ROUTES = {
    *(("Deposit", "External", kind) for kind in YOURS), *(("Withdrawal", kind, "External") for kind in YOURS),
    ("Transfer", "bank", "another bank"), ("Transfer", "bank", "exchange USD"), ("Transfer", "exchange USD", "bank"),
    ("Transfer", "exchange USD", "another exchange's USD"),
    ("Transfer", "wallet", "another wallet"), ("Transfer", "wallet", "exchange BTC"),
    ("Transfer", "exchange BTC", "wallet"), ("Transfer", "exchange BTC", "another exchange's BTC"),
    ("Transfer", "wallet", "itself"), ("Transfer", "exchange BTC", "itself"),  # consolidations (#159)
    ("Buy", "bank", "exchange BTC"), ("Buy", "exchange USD", "its exchange's BTC"),
    ("Sell", "exchange BTC", "its exchange's USD"),
}
# Each deposit source and withdrawal purpose in each kind of account that
# holds it (2.0 spec 5.5), and dollars in and out of each dollar kind, each
# in more than one account of that kind, so every pile rule runs beyond
# 1.x's first account too (#702). A dollar deposit's source is N/A.
CASH = "N/A"
BTC_SIDES, USD_SIDES = ("wallet", "exchange BTC"), ("bank", "exchange USD")
EACH_KIND_IN_EACH_SIDE = {
    *(("Deposit", s, side) for s in DEPOSIT_SOURCES if s != CASH for side in BTC_SIDES),
    *(("Withdrawal", p, side) for p in WITHDRAWAL_PURPOSES for side in BTC_SIDES),
    *(("Deposit", CASH, side) for side in USD_SIDES), *(("Withdrawal", "cash", side) for side in USD_SIDES),
}
# Each exchange's Sells' boxes, by year (Sales by exchange, #349): before
# 2025 the 1099-B boxes by override only; from 2025 the 1099-DA switch's,
# H/K with it on (Exchange, Kraken) and I/L with it off (Overseas); from
# 2026 G for coins bought there; and each Broker form choice beside them
# (an override wins over the switch: Overseas' H in 2025 and G in 2026)
SALES_BOXES = {
    2023: {"Exchange": "C"},
    2024: {"Exchange": "ABCDEF", "Kraken": "CF"},
    2025: {"Exchange": "GHIJK", "Kraken": "HIK", "Overseas": "HIL"},
    2026: {"Exchange": "GHJK", "Kraken": "GHK", "Overseas": "GIL"},
}
# Ledger Review's items (#702): those a row of the reference ledger shows,
# and why no row saved through the API can show the others, so a new item
# fails here until it's one or the other
REVIEW_SHOWN = {"original_date_missing", "sale_may_differ_from_1099da", "gift_without_value",
                "deposit_without_basis", "buy_without_basis", "zero_proceeds_spend"}
REVIEW_OUT_OF_REACH = {
    "withdrawal_purpose_unknown": "the API refuses a purpose it doesn't know",
    "inherited_without_date": "the API refuses an inheritance without its date of death",
    "income_without_value": "a $0 or blank income is priced, and the ledger loads with the price source Off",
    "income_value_off": "it compares a typed value with the hour's price, and no price is stored",
    "day_priced_values": "no value is priced at all: every one is typed",
    "account_missing": "only a database from before 0.9.2, or one whose account was deleted, names one",
    "account_from_before_0_9_2": "only a database from before 0.9.2 has one",
    "lost_with_loss": "every save gives lost coins a $0 gain",
    "recalc_changes": "a seeded ledger is recalculated by every save",
}
# Chosen coins (#711; docs/temp/2.0-coin-choice.md 2.2, 8.3): each
# withdrawal purpose, and each move out of a wallet to another account, by a
# choice
CHOOSING = {*(("Withdrawal", purpose) for purpose in WITHDRAWAL_PURPOSES),
            ("Transfer", "another wallet"), ("Transfer", "exchange BTC")}
# 1.x's accounts, which every ledger has, by id: (kind, currency, exchange)
FIXED = {1: ("bank", "USD", None), 2: ("wallet", "BTC", None), 3: ("exchange", "USD", 1),
         4: ("exchange", "BTC", 1), 99: ("External", None, None)}
# The report's keys a step adds, which the saved figures may lack until
# `make reference-figures` accepts them (B4's were accepted with B7a's rows)
NEW_KEYS: set[str] = set()


def listed_accounts() -> list[dict]:
    """The ledger's accounts list as written, with its notes."""
    return json.loads(seed_ledger.LEDGER.read_text()).get("accounts", [])


def ledger_accounts() -> dict[int, tuple]:
    """The ledger's accounts by id, 1.x's and its accounts list's: (kind, currency, exchange)."""
    return {**FIXED, **{a["id"]: (a["kind"], a["currency"], a.get("exchange_id")) for a in listed_accounts()}}


def switches() -> dict[int, bool]:
    """Each exchange account's 1099-DA switch: on, unless the list says otherwise (1.x's Exchange is on)."""
    return {3: True, 4: True, **{a["id"]: a.get("sends_1099da", True) for a in listed_accounts()
                                 if a["kind"] == "exchange"}}


def _side(account: tuple) -> str:
    kind, currency, _ = account
    return f"exchange {currency}" if kind == "exchange" else kind


def _route(tx_type: str, from_id: int, to_id: int, accounts: dict[int, tuple]) -> tuple[str, str, str]:
    """(type, from, to) by kind: to the same account, to another of the same
    kind, to an exchange's own other account or another exchange's."""
    source, destination = accounts[from_id], accounts[to_id]
    if from_id == to_id:
        to = "itself"
    elif source[0] == destination[0] == "exchange":
        to = f"{'its' if source[2] == destination[2] else 'another'} exchange's {destination[1]}"
    elif source[0] == destination[0]:
        to = f"another {_side(destination)}"
    else:
        to = _side(destination)
    return tx_type, _side(source), to


def _kind(t: Transaction, accounts: dict[int, tuple]) -> str:
    if t.type == "Deposit":
        return f"Deposit {t.source}"
    if t.type == "Withdrawal":
        return f"Withdrawal {t.purpose or 'cash'}"
    if t.type == "Transfer" and t.from_account_id == t.to_account_id:
        return "Consolidation"
    if t.type == "Transfer":
        _, source, to = _route(t.type, t.from_account_id, t.to_account_id, accounts)
        if accounts[t.from_account_id][1] == "USD":
            return "Transfer cash"
        return {("wallet", "exchange BTC"): "Transfer to the exchange",
                ("exchange BTC", "wallet"): "Transfer from the exchange"}.get((source, to), f"Transfer {source} to {to}")
    return t.type


@pytest.fixture
def seeded(fresh_app, monkeypatch):
    """A fresh install claimed and seeded by the script, price source Off;
    yields (client, Session, the days a price was asked for)."""
    asked = []

    async def find_prices(day, full):
        asked.append(day)
        return {}, False

    monkeypatch.setattr("backend.services.price_history.find_prices", find_prices)
    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings(price_source="off"))
    c = TestClient(app)
    seed_ledger.log_in(c, USER, PASSWORD, first_run.ensure_code())
    assert seed_ledger.seed(c) == len(seed_ledger.ledger_rows())
    yield c, fresh_app, asked


def test_the_whole_ledger_loads_with_prices_off_and_asks_for_none(seeded):
    c, Session, asked = seeded
    assert asked == []
    with Session() as db:
        assert db.query(Transaction).count() == len(seed_ledger.ledger_rows())


def test_every_year_has_every_kind_of_transaction(seeded):
    _, Session, _ = seeded
    accounts = ledger_accounts()
    with Session() as db:
        kinds = {year: set() for year in YEARS}
        for t in db.query(Transaction):
            if t.timestamp.year in kinds:  # 2022's deposit only gives 2023 its opening holdings
                kinds[t.timestamp.year].add(_kind(t, accounts))
    assert {year: KINDS - found for year, found in kinds.items()} == {year: set() for year in YEARS}


@pytest.mark.parametrize("year, boxes", [(2023, "C"), (2024, "ABCDEF"), (2025, "GHIJKL"), (2026, "GHIJKL")])
def test_every_report_has_entries_in_every_part(seeded, year, boxes):
    """Form 8949: every box the year's form has (2023 has no forms here,
    only box C rows for the reports), short- and long-term; Schedule D:
    every line; the complete tax report: gains, income from each source,
    rebates, a gift, a donation and a loss, and holdings at both ends of
    the year (2023's opening ones from a 2022 deposit)."""
    _, Session, _ = seeded
    with Session() as db:
        forms = build_form_8949_and_schedule_d(year, db)
        report = generate_report_data(db, year)
    assert {r["box"] for r in forms["short_term"] + forms["long_term"]} == set(boxes)
    if year >= 2024:
        assert set(forms["schedule_d"]["lines"]) == {"1b", "2", "3", "8b", "9", "10"}
        assert forms["short_term"] and forms["long_term"], year
    for part in ("capital_gains_transactions", "income_transactions", "gifts_donations_lost", "rebates",
                 "start_of_year_balances", "end_of_year_balances"):
        assert report[part], (year, part)
    # Each exchange adding up its Sells' rows (#349), in the boxes its switch and its Sells' choices give
    sales = defaultdict(list)
    for r in report["capital_gains_transactions"]:
        if r["kind"] == "Sale":
            sales[r["account"].removesuffix(" BTC")].append(r)
    assert [(s["exchange"], s["rows"]) for s in report["sales_by_exchange"]] == [
        (name, len(sales[name])) for name in SALES_BOXES[year]]
    assert {s["exchange"]: "".join(s["boxes"]) for s in report["sales_by_exchange"]} == SALES_BOXES[year]
    for exchange in report["sales_by_exchange"]:
        for total in ("proceeds", "cost", "gain_loss"):
            assert round(exchange[total], 2) == round(sum(r[total] for r in sales[exchange["exchange"]]), 2), total
    assert {"Income", "Interest", "Reward"} <= {k for k, v in report["income_summary"].items() if v}
    assert {g["type"] for g in report["gifts_donations_lost"]} == {"Gift", "Donation", "Lost"}


def test_the_ledger_has_everything_the_app_offers():
    """Every transaction type and account route, every broker-reporting
    choice, fees in USD and BTC, and a date originally acquired on a My BTC
    and a Gift deposit: so a full-ledger check exercises all of them."""
    rows, accounts = seed_ledger.ledger_rows(), ledger_accounts()
    assert {r["type"] for r in rows} == set(TX_TYPES)
    assert {_route(r["type"], r["from_account_id"], r["to_account_id"], accounts) for r in rows} == ROUTES
    assert set(get_args(BrokerReporting)) <= {r.get("broker_reporting") for r in rows}
    paid = {(r["type"], r["fee_currency"]) for r in rows if Decimal(r["fee_amount"]) > 0}
    assert {("Buy", "USD"), ("Sell", "USD"), ("Transfer", "BTC"), ("Withdrawal", "BTC")} <= paid
    assert {"MyBTC", "Gift"} <= {r["source"] for r in rows if r.get("acquired_at")}


def test_each_kind_is_in_more_than_one_account_of_each_kind():
    accounts, seen = ledger_accounts(), defaultdict(set)
    for r in seed_ledger.ledger_rows():
        if r["type"] == "Deposit":
            seen[(r["type"], r["source"], _side(accounts[r["to_account_id"]]))].add(r["to_account_id"])
        elif r["type"] == "Withdrawal":
            purpose = r.get("purpose") or "cash"
            seen[(r["type"], purpose, _side(accounts[r["from_account_id"]]))].add(r["from_account_id"])
    assert {kind: sorted(seen[kind]) for kind in EACH_KIND_IN_EACH_SIDE if len(seen[kind]) < 2} == {}


def test_each_route_joins_more_than_one_pair_of_accounts():
    accounts, pairs = ledger_accounts(), defaultdict(set)
    for r in seed_ledger.ledger_rows():
        route = _route(r["type"], r["from_account_id"], r["to_account_id"], accounts)
        pairs[route].add((r["from_account_id"], r["to_account_id"]))
    assert {route: sorted(pairs[route]) for route in ROUTES if len(pairs[route]) < 2} == {}


def test_every_broker_form_choice_against_each_switch():
    """From 2025, when an exchange's 1099-DA switch decides a Sell's box
    (2.0 spec 5.7): a Sell of every Broker form choice (blank: the switch's
    rule) on an exchange with it on and one with it off; and a spend with a
    BTC fee of each choice, which its fee follows (#549)."""
    rows, switch = [r for r in seed_ledger.ledger_rows() if r["timestamp"] >= "2025"], switches()
    choices = {None, *get_args(BrokerReporting)}
    sells = {(switch[r["from_account_id"]], r.get("broker_reporting")) for r in rows if r["type"] == "Sell"}
    assert sells == {(on, choice) for on in (True, False) for choice in choices}
    spends = {r.get("broker_reporting") for r in rows if r["type"] == "Withdrawal" and r.get("purpose") == "Spent"
              and r["fee_currency"] == "BTC" and Decimal(r["fee_amount"]) > 0}
    assert spends == choices


def test_coins_are_chosen_for_each_purpose_and_each_move_out_of_a_wallet():
    """In 2025, the year the rule begins (Treas. Reg. §1.1012-1(j)(6)), and
    in 2026, only out of a wallet (2.2)."""
    accounts, years = ledger_accounts(), defaultdict(set)
    for r in seed_ledger.ledger_rows():
        if r.get("chosen_coins"):
            _, source, to = _route(r["type"], r["from_account_id"], r["to_account_id"], accounts)
            assert source == "wallet", r
            years[(r["type"], r["purpose"] if r["type"] == "Withdrawal" else to)].add(r["timestamp"][:4])
    assert {what: sorted(years[what]) for what in CHOOSING if not years[what]} == {}
    assert set().union(*years.values()) >= {"2025", "2026"}


def test_chosen_coins_reach_inherited_coins_both_terms_and_one_purchase_in_two_lots(seeded):
    """What a choice takes, in the seeded ledger's disposals: inherited coins
    (INHERITED, long-term, #154); a spend's coins of both terms with its BTC
    fee, which the chosen coins pay (#711's call (b)); and one purchase
    held in two lots of one wallet, by two transfers, taken from both."""
    _, Session, _ = seeded
    with Session() as db:
        choosing = [tx for tx in db.query(Transaction) if tx.chosen_coins]
        inherited = [tx.id for tx in choosing if any(d.lot.inherited for d in tx.lot_disposals)]
        spends = {(tx.purpose, frozenset(d.holding_period for d in tx.lot_disposals),
                   any(d.is_fee for d in tx.lot_disposals)) for tx in choosing}
        two_lots = [tx.id for tx in choosing for coin in tx.chosen_coins
                    if len({d.lot_id for d in tx.lot_disposals if d.lot.acquired_txn_id == coin.acquired_txn_id}) > 1]
    assert inherited
    assert ("Spent", frozenset({"SHORT", "LONG"}), True) in spends
    assert two_lots


def test_one_choice_is_the_oldest_coins_and_the_others_arent():
    """Oldest first is a way of identifying too ((j)(4)): one choice gives
    oldest first's figures, and the others move some. The independent check
    replays the ledger with each choice left out in turn; one left out can
    also leave a later choice short, which stops the replay."""
    independent, ledger = independent_figures(), json.loads(seed_ledger.LEDGER.read_text())

    def every_year(transactions: list[dict]) -> dict:
        replayed = independent.replay_ledger({**ledger, "transactions": transactions})
        return {year: independent.year_figures(replayed, year) for year in YEARS}

    rows, same = ledger["transactions"], []
    for i, row in enumerate(rows):
        if row.get("chosen_coins"):
            unchosen = {field: value for field, value in row.items() if field != "chosen_coins"}
            try:
                same.append(every_year([*rows[:i], unchosen, *rows[i + 1:]]) == every_year(rows))
            except ValueError:
                same.append(False)
    assert True in same and False in same, same


@pytest.mark.parametrize("year", [2024, 2025, 2026])
def test_each_forms_year_has_gains_and_losses_and_inherited_coins(seeded, year):
    """Schedule D's short- and long-term parts each with a gain and a loss,
    and inherited coins sold (INHERITED in column (b), #154), in each year
    BitcoinTX fills IRS forms for (none for 2023)."""
    _, Session, _ = seeded
    with Session() as db:
        forms = build_form_8949_and_schedule_d(year, db)
    rows = forms["short_term"] + forms["long_term"]
    signs = {(r["holding_period"], r["gain_loss"] > 0) for r in rows if r["gain_loss"]}
    assert signs == {("SHORT", True), ("SHORT", False), ("LONG", True), ("LONG", False)}
    assert INHERITED in {r["date_acquired"] for r in rows}


def test_the_dashboard_has_each_kind_more_than_once_a_hidden_account_and_a_renamed_one(seeded):
    """2.0's dashboard goes by kind (spec 5.13): more than one bank, wallet
    and exchange holding something; an account the owner hid while it
    still holds coins; and one renamed after its rows, shown by its new
    name (an exchange's: the exchange and both its accounts)."""
    c, _, _ = seeded
    balances = c.get("/api/calculations/accounts/balances").json()
    held = defaultdict(set)
    for b in balances:
        if b["balance"]:
            held[b["kind"]].add(b["exchange_id"] or b["account_id"])
    assert {kind: len(held[kind]) > 1 for kind in ("bank", "wallet", "exchange")} == dict.fromkeys(
        ("bank", "wallet", "exchange"), True)
    hidden = {a["id"] for a in listed_accounts() if a.get("hidden")}
    assert hidden and {b["account_id"] for b in balances if b["hidden"]} == hidden
    assert all(b["balance"] for b in balances if b["hidden"])
    renamed = {a["id"]: (a["name"], a["renamed_from"]) for a in listed_accounts() if "renamed_from" in a}
    names = {b["account_id"]: b["name"] for b in balances}
    assert renamed and {i: names[i] for i in renamed} == {i: new for i, (new, _) in renamed.items()}
    assert not {old for _, old in renamed.values()} & set(names.values())


def test_ledger_review_shows_each_item_a_row_can(seeded):
    _, Session, _ = seeded
    with Session() as db:
        checks = build_review(db)["checks"]
    assert {c["key"] for c in checks if c["count"]} == REVIEW_SHOWN
    assert {c["key"] for c in checks} == REVIEW_SHOWN | set(REVIEW_OUT_OF_REACH)


def test_every_value_a_price_would_fill_is_given():
    for row in seed_ledger.ledger_rows():
        if row.get("fee_currency") == "BTC" and Decimal(row["fee_amount"]) > 0:
            assert Decimal(row["fee_usd"]) > 0, row
        if (row.get("purpose") or "").lower() in ("gift", "donation"):
            assert Decimal(row["fmv_usd"]) > 0, row
        if (row.get("purpose") or "").lower() == "lost":  # filled from the price too since #255
            assert row.get("fmv_usd") is not None, row  # $0 typed, some of them


def test_2026_rows_land_in_their_boxes(seeded):
    _, Session, _ = seeded
    with Session() as db:
        forms = build_form_8949_and_schedule_d(2026, db)
    boxes = defaultdict(set)
    for row in forms["short_term"] + forms["long_term"]:
        boxes[row["date_sold"]].add(row["box"])
    assert dict(boxes) == BOXES_2026
    assert set(forms["schedule_d"]["lines"]) == {"1b", "2", "3", "8b", "9", "10"}


def test_dates_originally_acquired_lead_fifo(seeded):
    """The 2019 My BTC and the 2020 gift are the wallet's oldest coins by
    their date originally acquired, so they go first: long-term, and Form
    8949 column (b) shows that date (#91)."""
    _, Session, _ = seeded
    with Session() as db:
        forms = build_form_8949_and_schedule_d(2026, db)
    rows = forms["short_term"] + forms["long_term"]
    acquired = {(r["date_sold"], r["date_acquired"], r["box"]) for r in rows}
    assert ("07/01/2026", "03/01/2019", "L") in acquired
    assert ("09/01/2026", "01/15/2020", "L") in acquired


def test_the_reference_figures_have_not_moved(seeded):
    """#139: every figure the reference ledger gives (each year's forms and
    report, the dashboard) against testdata/reference_figures.json. A change
    meant to move figures runs `make reference-figures` and shows the
    difference in its pull request. The figures rule (AGENTS.md, "Reviews"):
    a figure moved on purpose gets the owner's OK on a plain-words
    before-and-after, never on code; one moved by mistake is fixed; no figure
    moved, Claude merges after every figures check."""
    _, Session, _ = seeded
    with Session() as db:
        now = reference_figures.figures(db)
    if os.environ.get("BTCTX_UPDATE_REFERENCE_FIGURES"):
        reference_figures.FIGURES.write_text(reference_figures.dumps(now))
    saved = json.loads(reference_figures.FIGURES.read_text())
    moved = list(reference_figures.differences(saved, now, allow_new=True))
    assert not moved, "figures moved (make reference-figures if meant):\n" + "\n".join(moved[:20])
    assert set(_new_keys(saved, now)) <= NEW_KEYS


def _new_keys(saved, now, path: str = "") -> Iterator[str]:
    """Where `now` has a key `saved` hasn't, as a path: a list's items as
    [], each year as *."""
    if isinstance(saved, dict) and isinstance(now, dict):
        for key in now:
            where = re.sub(r"^years\.\d+$", "years.*", f"{path}.{key}" if path else key)
            yield from [where] if key not in saved else _new_keys(saved[key], now[key], where)
    elif isinstance(saved, list) and isinstance(now, list):
        for a, b in zip(saved, now):
            yield from _new_keys(a, b, f"{path}[]")


@pytest.mark.parametrize("tz", ["Asia/Tokyo", "Australia/Adelaide", "Pacific/Honolulu", "America/New_York"])
def test_every_box_in_any_tax_timezone(seeded, tz):
    """Review of #57: the anniversary sales stay on the lot's day, so short-
    term, wherever the owner's tax timezone is."""
    c, Session, _ = seeded
    assert c.put("/api/settings/tax-timezone", json={"timezone": tz, "chosen": True}).status_code == 200
    try:
        with Session() as db:
            forms = {year: build_form_8949_and_schedule_d(year, db) for year in (2024, 2025, 2026)}
        boxes = {year: {r["box"] for r in f["short_term"] + f["long_term"]} for year, f in forms.items()}
    finally:
        c.put("/api/settings/tax-timezone", json={"timezone": "UTC", "chosen": True})
    assert boxes == {2024: set("ABCDEF"), 2025: set("GHIJKL"), 2026: set("GHIJKL")}


def test_the_history_csv_writes_ordinary_text_as_it_is(seeded):
    """Each year's transaction history CSV of the reference ledger is the
    plain file a spreadsheet or a diff expects: a line per row and none after
    the last, every cell as it is, quoted only when it holds a comma or a
    quote."""
    c, _, _ = seeded

    def cell(value: str) -> str:
        return '"' + value.replace('"', '""') + '"' if "," in value or '"' in value else value

    for year in YEARS:
        r = c.get("/api/reports/simple_transaction_history", params={"year": year, "format": "csv"})
        assert r.status_code == 200, r.text
        rows = list(csv.reader(io.StringIO(r.text)))
        assert len(rows) > 10, year
        assert r.text == "\n".join(",".join(cell(value) for value in row) for row in rows), year


def test_a_ledger_with_transactions_is_refused(seeded):
    c, Session, _ = seeded
    with pytest.raises(seed_ledger.SeedError, match="already has"):
        seed_ledger.seed(c)
    with Session() as db:
        assert db.query(Transaction).count() == len(seed_ledger.ledger_rows())


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8765", "http://localhost:8765/", "http://[::1]:8765", "http://LOCALHOST:8765",
    # Review of #52: other spellings of this computer
    "http://127.1:8765", "http://2130706433:8765", "http://localhost.:8765", "http://foo.localhost:8765",
    "http://[::]:8765", "http://0.0.0.0:8765", "http://[::ffff:127.0.0.1]:8765",
])
def test_the_mac_app_is_refused_before_anything_is_sent(url, monkeypatch, capsys):
    def no_connection(*args, **kwargs):
        raise AssertionError("connected to the Mac app")

    monkeypatch.setattr(seed_ledger, "connect", no_connection)
    monkeypatch.setenv(seed_ledger.PASSWORD_ENV, PASSWORD)
    assert seed_ledger.main(["--url", url, "--user", USER]) == 1
    assert "Mac app" in capsys.readouterr().err


def test_other_local_ports_are_allowed():
    seed_ledger.refuse_mac_app("http://127.0.0.1:8777")  # make preview
    seed_ledger.refuse_mac_app("https://192.0.2.10:8765")  # another computer


def test_a_bad_address_is_a_message_not_a_traceback(monkeypatch, capsys):
    monkeypatch.setenv(seed_ledger.PASSWORD_ENV, PASSWORD)
    for url in ("http://host:abc", "http://a..b:8765"):
        assert seed_ledger.main(["--url", url, "--user", USER]) == 1
        assert "not a valid address" in capsys.readouterr().err
