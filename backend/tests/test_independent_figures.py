"""
scripts/independent_figures.py recomputes the reference test ledger's tax
figures from the rules, without the app's code (#150, #80 item 2). Here it
must agree to the cent with testdata/reference_figures.json, the app's own
figures, which test_seed_ledger.py keeps current. A difference is a bug in
one of the two calculations or a meant change: find out which before
changing either.
"""

import ast
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "independent_figures.py"


def _script():
    spec = importlib.util.spec_from_file_location("independent_figures", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look their module up
    spec.loader.exec_module(module)
    return module


independent = _script()


def test_an_independent_calculation_gives_the_apps_figures():
    # The script shares three conventions with the app on purpose (its
    # docstring): a lot's cost and a disposal's proceeds shared as running
    # totals (#100, #297), and an exact half cent rounded up. With those,
    # every Form 8949 row, Schedule D line, box total, exchange's Sells,
    # gains summary, income figure, rebate, gift and lot held at the year's
    # start and end of every year must be the same, in the ledger's
    # accounts (its accounts list adds 2.0's, #354; #702).
    ledger = independent.replay_ledger(json.loads(independent.LEDGER.read_text()), independent.ROUNDING["half-up"])
    saved = json.loads(independent.FIGURES.read_text())["years"]
    found = [f"{year}: {line}" for year, figures in saved.items()
             for line in independent.differences(independent.year_figures(ledger, int(year)), figures)]
    assert not found, "\n".join(found)


def test_the_independent_calculation_uses_nothing_of_the_app():
    imported = set()
    for node in ast.walk(ast.parse(SCRIPT.read_text())):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert not imported & {"backend", "btctx_mcp", "scripts"}, imported


WALLET, EXTERNAL = 2, 99
COINS = {"type": "Deposit", "timestamp": "2025-01-10T12:00:00Z", "from_account_id": EXTERNAL, "to_account_id": WALLET,
         "amount": "0.001", "fee_amount": "0", "fee_currency": "BTC", "source": "MyBTC", "cost_basis_usd": "100.00"}


def test_amounts_under_100_sats_are_written_as_the_app_writes_them():
    """#703: str() writes a Decimal under 0.000001 as "1E-8"; Form 8949's
    column (a) reads "0.00000001 BTC", so a 1-sat spend and an 11-sat fee
    showed as differences though every figure agreed."""
    spend = {**COINS, "type": "Withdrawal", "timestamp": "2025-02-10T12:00:00Z", "from_account_id": WALLET,
             "to_account_id": EXTERNAL, "amount": "0.00000001", "fee_amount": "0.00000011", "fee_usd": "0.01",
             "purpose": "Spent", "gross_proceeds_usd": "0.02"}
    figures = independent.year_figures(independent.replay([COINS, spend]), 2025)
    assert sorted(row["description"] for row in figures["form_8949"]) == ["0.00000001 BTC", "0.00000011 BTC"]
    assert [lot["quantity"] for lot in figures["end_of_year_holdings"]] == ["0.00099988"]


def test_a_spend_without_a_network_fee_needs_no_fee_value():
    """#703: the app stores no fee_usd for a bitcoin spend with no fee, so a
    ledger read back from it leaves the key out; the replay read it anyway."""
    spend = {**COINS, "type": "Withdrawal", "timestamp": "2025-02-10T12:00:00Z", "from_account_id": WALLET,
             "to_account_id": EXTERNAL, "amount": "0.0005", "purpose": "Spent", "gross_proceeds_usd": "80.00"}
    [row] = independent.year_figures(independent.replay([COINS, spend]), 2025)["form_8949"]
    assert (row["proceeds"], row["cost"], row["gain_loss"]) == ("80.00", "50.00", "30.00")


@pytest.mark.parametrize("given", [{"fee_usd": None}, {"fee_usd": ""}, {}], ids=["null", "blank", "missing"])
@pytest.mark.parametrize("purpose", ["Spent", "Gift"])
def test_a_network_fee_without_a_value_stops_the_replay(given, purpose):
    """The re-check of #702: a fee with no USD value was counted as $0,
    though the app prices it or refuses the row, never $0. Guessing would
    hide a difference, so it stops, naming the row."""
    out = {**COINS, "type": "Withdrawal", "timestamp": "2025-02-10T12:00:00Z", "from_account_id": WALLET,
           "to_account_id": EXTERNAL, "amount": "0.0005", "fee_amount": "0.00001", "purpose": purpose,
           "gross_proceeds_usd": "80.00", "fmv_usd": "80.00", **given}
    with pytest.raises(ValueError, match="Withdrawal of 2025-02-10T12:00:00Z pays a network fee with no USD value"):
        independent.replay([COINS, out])


# Chosen coins (#711, docs/temp/2.0-coin-choice.md 8.2): a row leaving one
# of your wallets may name the coins that leave (specific identification,
# Treas. Reg. §1.1012-1(j)(2)), each by the key of the Buy or Deposit that
# acquired them. Every figure below is worked out by hand in the comments,
# in UTC, every row at noon.
BANK, EXCHANGE_USD, EXCHANGE_BTC, SPARROW = 1, 3, 4, 100
TWO_WALLETS = independent.read_accounts(
    {"accounts": [{"id": SPARROW, "name": "Sparrow", "kind": "wallet", "currency": "BTC"}]})


def _deposit(day, btc, cost, key, **more):
    """A MyBTC deposit into Wallet, its coins named `key`."""
    return {**COINS, "timestamp": f"{day}T12:00:00Z", "amount": btc, "cost_basis_usd": cost, "key": key, **more}


def _spend(day, btc, proceeds, chosen=None, **more):
    """A Spent from Wallet, with no network fee unless one is given."""
    row = {**COINS, "type": "Withdrawal", "timestamp": f"{day}T12:00:00Z", "from_account_id": WALLET,
           "to_account_id": EXTERNAL, "amount": btc, "purpose": "Spent", "gross_proceeds_usd": proceeds, **more}
    return row if chosen is None else {**row, "chosen_coins": chosen}


def _move(day, btc, source, destination, chosen=None, **more):
    """A Transfer, its amount the BTC that left `source` (its network fee in it)."""
    row = {**COINS, "type": "Transfer", "timestamp": f"{day}T12:00:00Z", "from_account_id": source,
           "to_account_id": destination, "amount": btc, **more}
    return row if chosen is None else {**row, "chosen_coins": chosen}


def _buy(day, btc, cost, key=None):
    """A Buy on the exchange, paid from the bank, with no fee."""
    row = {"type": "Buy", "timestamp": f"{day}T12:00:00Z", "from_account_id": BANK, "to_account_id": EXCHANGE_BTC,
           "amount": btc, "cost_basis_usd": cost, "fee_amount": "0", "fee_currency": "USD"}
    return row if key is None else {**row, "key": key}


def _chosen(**btc):
    return [{"key": key, "btc": amount} for key, amount in btc.items()]


def _row(box, btc, acquired, sold, proceeds, cost, gain, term):
    return {"box": box, "description": f"{btc} BTC", "date_acquired": acquired, "date_sold": sold,
            "proceeds": proceeds, "cost": cost, "gain_loss": gain, "holding_period": term}


def _lot(account, acquired, btc, cost):
    return {"account": account, "acquired": f"{acquired}T12:00:00+00:00", "quantity": btc, "cost": cost}


# Three purchases in Wallet: oldest first would always start with A's.
A = _deposit("2023-03-01", "0.01", "200.00", "a")
B = _deposit("2024-06-01", "0.02", "1000.00", "b")
C = _deposit("2025-03-01", "0.01", "900.00", "c")


def test_a_spend_takes_the_coins_it_chose_its_fee_the_oldest_of_them():
    """(j)(5)(i), Example 1: a record made by the time the coins left says
    they were the later lots', so their basis and holding period are those
    lots'. The network fee is paid by the chosen coins, the oldest of them
    first (plan call (b)): one budget for the fee and the amount."""
    spend = _spend("2025-09-01", "0.015", "1500.00", _chosen(b="0.0051", c="0.01"),
                   fee_amount="0.0001", fee_usd="10.00")
    figures = independent.year_figures(independent.replay([A, B, C, spend]), 2025)
    # The fee, 0.0001 of B's (the older chosen): $1,000 x 0.0001/0.02 = $5.00
    # of cost, $10.00 of value; B was held more than a year, so long-term, L.
    # The spend's $1,500 less the fee's $10 is $1,490 for 0.015 BTC: B's
    # 0.005 gets 1,490/3 = $496.67 and costs $255.00 (B's first 0.0051)
    # less $5.00 = $250.00; C's 0.01, the rest, $993.33, costs all of C's
    # $900.00 and is short-term, I. A is untouched.
    assert figures["form_8949"] == [
        _row("L", "0.00010000", "06/01/2024", "09/01/2025", "10.00", "5.00", "5.00", "LONG"),
        _row("L", "0.00500000", "06/01/2024", "09/01/2025", "496.67", "250.00", "246.67", "LONG"),
        _row("I", "0.01000000", "03/01/2025", "09/01/2025", "993.33", "900.00", "93.33", "SHORT"),
    ]
    # Left: all of A, and B's 0.0149 at $1,000 - $255 = $745.00.
    assert figures["end_of_year_holdings"] == [_lot("Wallet", "2023-03-01", "0.01000000", "200.00"),
                                               _lot("Wallet", "2024-06-01", "0.01490000", "745.00")]


def test_a_gift_and_a_donation_give_the_coins_they_chose():
    """A gift's and a donation's coins are chosen like a spend's (2.2): what
    each took, by term, is what the report gives the donor's deduction."""
    gift = _spend("2025-09-01", "0.005", None, _chosen(c="0.0051"), purpose="Gift", fmv_usd="500.00",
                  fee_amount="0.0001", fee_usd="10.00")
    donation = _spend("2025-10-01", "0.006", None, _chosen(a="0.002", c="0.004"), purpose="Donation",
                      fmv_usd="700.00")
    figures = independent.year_figures(independent.replay([A, B, C, gift, donation]), 2025)
    # The gift's fee, C's first 0.0001: $900 x 0.0001/0.01 = $9.00 of cost,
    # its own $10.00 of value. The gift, C's next 0.005: $459.00 (C's first
    # 0.0051) less $9.00 = $450.00. The donation: A's 0.002, $40.00, long-
    # term; C's 0.004, $819.00 (C's first 0.0091) less $459.00 = $360.00,
    # short-term.
    assert figures["form_8949"] == [_row("I", "0.00010000", "03/01/2025", "09/01/2025", "10.00", "9.00", "1.00",
                                         "SHORT")]
    assert [gift["lots_by_term"] for gift in figures["gifts_donations_lost"]] == [
        [{"term": "SHORT", "btc": "0.00500000", "cost_basis": "450.00"}],
        [{"term": "LONG", "btc": "0.00200000", "cost_basis": "40.00"},
         {"term": "SHORT", "btc": "0.00400000", "cost_basis": "360.00"}],
    ]
    # Left: A's 0.008 ($160.00), all of B, C's 0.0009 ($900 - $819 = $81.00).
    assert figures["end_of_year_holdings"] == [_lot("Wallet", "2023-03-01", "0.00800000", "160.00"),
                                               _lot("Wallet", "2024-06-01", "0.02000000", "1000.00"),
                                               _lot("Wallet", "2025-03-01", "0.00090000", "81.00")]


def test_chosen_coins_move_to_another_wallet_and_can_be_chosen_there():
    """(j)(1) names transfers: the coins moved to another of your wallets are
    the ones identified. They arrive with their date, cost, inheritance and
    acquisition, so a later spend there chooses them by the same key."""
    inherited = {**_deposit("2024-02-01", "0.02", "800.00", "inh"), "source": "Inherited",
                 "acquired_at": "2024-01-15"}
    move = _move("2025-05-01", "0.0201", WALLET, SPARROW, _chosen(inh="0.0101", c="0.01"),
                 fee_amount="0.0001", fee_usd="9.00")
    newer = {**_spend("2025-08-01", "0.004", "500.00", _chosen(c="0.004")), "from_account_id": SPARROW}
    inherited_out = {**_spend("2025-08-02", "0.001", "100.00", _chosen(inh="0.001")), "from_account_id": SPARROW}
    ledger = independent.replay([A, inherited, C, move, newer, inherited_out], accounts=TWO_WALLETS)
    figures = independent.year_figures(ledger, 2025)
    # The fee, the inherited coins' first 0.0001 (the older chosen):
    # $800 x 0.0001/0.02 = $4.00, worth $9.00; inherited, so long-term and
    # INHERITED (§1223(9)). Moved: the inherited 0.01, $404.00 (their first
    # 0.0101) less $4.00 = $400.00, and all of C, $900.00. In Sparrow, C's
    # 0.004 costs $900 x 0.4 = $360.00 (short-term, I) and the inherited
    # 0.001 costs $400 x 0.1 = $40.00 (long-term, L).
    assert figures["form_8949"] == [
        _row("L", "0.00010000", "INHERITED", "05/01/2025", "9.00", "4.00", "5.00", "LONG"),
        _row("I", "0.00400000", "03/01/2025", "08/01/2025", "500.00", "360.00", "140.00", "SHORT"),
        _row("L", "0.00100000", "INHERITED", "08/02/2025", "100.00", "40.00", "60.00", "LONG"),
    ]
    # Wallet keeps A and the inherited 0.0099 ($800 - $404 = $396.00);
    # Sparrow the inherited 0.009 ($360.00) and C's 0.006 ($540.00).
    assert figures["end_of_year_holdings"] == [_lot("Wallet", "2023-03-01", "0.01000000", "200.00"),
                                               _lot("Wallet", "2024-01-15", "0.00990000", "396.00"),
                                               _lot("Sparrow", "2024-01-15", "0.00900000", "360.00"),
                                               _lot("Sparrow", "2025-03-01", "0.00600000", "540.00")]


def test_coins_chosen_for_an_exchange_leave_it_oldest_first():
    """A wallet's choice decides which coins reach the exchange; there they
    leave oldest first, as its 1099-DA reports them (plan call (g))."""
    move = _move("2025-05-01", "0.005", WALLET, EXCHANGE_BTC, _chosen(c="0.005"))
    sell = {"type": "Sell", "timestamp": "2025-06-01T12:00:00Z", "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD, "amount": "0.006", "gross_proceeds_usd": "700.00", "fee_amount": "0",
            "fee_currency": "USD"}
    figures = independent.year_figures(
        independent.replay([A, C, _buy("2025-04-01", "0.01", "955.00"), move, sell]), 2025)
    # On the exchange: C's 0.005 ($450.00, acquired 03/01/2025) and the
    # Buy's 0.01 ($955.00, 04/01/2025). The Sell's 0.006 takes C's first:
    # $700 x 5/6 = $583.33 of proceeds; then the Buy's 0.001, $95.50, with
    # the rest, $116.67. Both moved in or bought before 2026: box H.
    assert figures["form_8949"] == [
        _row("H", "0.00500000", "03/01/2025", "06/01/2025", "583.33", "450.00", "133.33", "SHORT"),
        _row("H", "0.00100000", "04/01/2025", "06/01/2025", "116.67", "95.50", "21.17", "SHORT"),
    ]


def test_one_purchase_in_two_lots_is_chosen_across_both_the_first_made_first():
    """Two transfers of one purchase make two lots of the same coins in the
    wallet. A choice of that purchase takes the lot made first, then the
    next; the cents show which went first."""
    rows = [A, _buy("2025-01-10", "0.03", "1000.00", key="buy"),
            _move("2025-02-01", "0.01", EXCHANGE_BTC, WALLET), _move("2025-03-01", "0.01", EXCHANGE_BTC, WALLET),
            _spend("2025-04-01", "0.015", "600.00", _chosen(buy="0.015"))]
    figures = independent.year_figures(independent.replay(rows), 2025)
    # The first transfer takes the Buy's first 0.01: $1,000/3 = $333.33.
    # The second, its first 0.02 less that: $666.67 - $333.33 = $333.34.
    # The spend takes all of the first lot ($333.33) and half the second
    # ($333.34 / 2 = $166.67); the other way round, the 0.01 would cost
    # $333.34.
    assert figures["form_8949"] == [
        _row("I", "0.01000000", "01/10/2025", "04/01/2025", "400.00", "333.33", "66.67", "SHORT"),
        _row("I", "0.00500000", "01/10/2025", "04/01/2025", "200.00", "166.67", "33.33", "SHORT"),
    ]
    assert figures["end_of_year_holdings"] == [_lot("Wallet", "2023-03-01", "0.01000000", "200.00"),
                                               _lot("Wallet", "2025-01-10", "0.00500000", "166.67"),
                                               _lot("Exchange BTC", "2025-01-10", "0.01000000", "333.33")]


def test_choosing_the_oldest_coins_gives_the_figures_of_no_choice():
    """Oldest first is a way of identifying too ((j)(4)): choosing exactly
    the coins it would take gives the figures of a ledger with no choice and
    no keys (C's key names coins no row chooses)."""
    fee = {"fee_amount": "0.0001", "fee_usd": "10.00"}
    unnamed = [{field: value for field, value in row.items() if field != "key"} for row in (A, B, C)]
    oldest = independent.replay([*unnamed, _spend("2025-09-01", "0.015", "1500.00", **fee)])
    chosen = independent.replay([A, B, C, _spend("2025-09-01", "0.015", "1500.00", _chosen(a="0.01", b="0.0051"),
                                                 **fee)])
    for year in (2023, 2024, 2025):
        assert independent.year_figures(chosen, year) == independent.year_figures(oldest, year)


def test_a_null_key_names_no_coins():
    """`"key": null` is no key, as `"chosen_coins": null` is no choice: two
    rows may have one, and no choice takes their coins."""
    unnamed = [{**A, "key": None}, _deposit("2023-06-01", "0.01", "300.00", None)]
    spend = _spend("2025-09-01", "0.005", "500.00", _chosen(b="0.005"))
    [row] = independent.year_figures(independent.replay([*unnamed, B, spend]), 2025)["form_8949"]
    # B's 0.005 of its 0.02: $1,000 / 4 = $250.00, bought 06/01/2024; the
    # two older deposits are left whole.
    assert (row["date_acquired"], row["cost"]) == ("06/01/2024", "250.00")


D = _deposit("2025-01-01", "0.01", "500.00", "d")
BAD_CHOICES = {
    "more than the wallet holds": (
        [A, B, _spend("2025-09-01", "0.03", "1500.00", _chosen(b="0.03"))],
        "The Withdrawal of 2025-09-01T12:00:00Z chose 0.03000000 BTC of the coins from 'b', "
        "but Wallet holds 0.02000000 BTC of them then."),
    "coins an earlier transfer took": (
        [A, B, _move("2025-05-01", "0.02", WALLET, EXCHANGE_BTC, _chosen(b="0.02")),
         _spend("2025-09-01", "0.005", "500.00", _chosen(b="0.005"))],
        "chose 0.00500000 BTC of the coins from 'b', but Wallet holds 0.00000000 BTC of them then."),
    "coins not acquired yet": (
        [A, _spend("2024-01-01", "0.005", "100.00", _chosen(b="0.005")), B],
        "The Withdrawal of 2024-01-01T12:00:00Z chose 0.00500000 BTC of the coins from 'b', "
        "but Wallet holds 0.00000000 BTC of them then."),
    "coins still on the exchange": (
        [A, _buy("2025-01-10", "0.01", "900.00", key="x"), _spend("2025-09-01", "0.005", "500.00", _chosen(x="0.005"))],
        "of the coins from 'x', but Wallet holds 0.00000000 BTC of them then."),
    "short of a spend's fee": (
        [A, _spend("2025-09-01", "0.005", "100.00", _chosen(a="0.005"), fee_amount="0.0001", fee_usd="1.00")],
        "Transaction 2 chooses 0.00500000 BTC, but 0.00510000 BTC leaves Wallet"),
    "a transfer's fee counted twice": (
        [A, _move("2025-05-01", "0.005", WALLET, EXCHANGE_BTC, _chosen(a="0.0051"), fee_amount="0.0001",
                  fee_usd="1.00")],
        "Transaction 2 chooses 0.00510000 BTC, but 0.00500000 BTC leaves Wallet"),
    "from an exchange": (
        [_buy("2025-01-10", "0.01", "900.00", key="x"), _move("2025-05-01", "0.005", EXCHANGE_BTC, WALLET,
                                                              _chosen(x="0.005"))],
        "Transaction 2, a Transfer from Exchange BTC, chooses coins: only coins leaving one of your wallets"),
    "a Sell": (
        [_buy("2025-01-10", "0.01", "900.00", key="x"),
         {"type": "Sell", "timestamp": "2025-06-01T12:00:00Z", "from_account_id": EXCHANGE_BTC,
          "to_account_id": EXCHANGE_USD, "amount": "0.005", "gross_proceeds_usd": "500.00", "fee_amount": "0",
          "fee_currency": "USD", "chosen_coins": _chosen(x="0.005")}],
        "Transaction 2, a Sell from Exchange BTC, chooses coins"),
    "a Deposit": (
        [A, {**D, "chosen_coins": _chosen(a="0.01")}],
        "Transaction 2, a Deposit from External, chooses coins"),
    "a consolidation": (
        [A, _move("2025-05-01", "0.0001", WALLET, WALLET, _chosen(a="0.0001"), fee_amount="0.0001",
                  fee_usd="1.00")],
        "Transaction 2 moves coins within Wallet: that records only its network fee, from the oldest coins"),
    "a key no row has": (
        [A, _spend("2025-09-01", "0.005", "500.00", _chosen(z="0.005"))],
        "Transaction 2 chooses the coins from 'z', which is no Buy's or Deposit's key."),
    "one acquisition twice": (
        [A, _spend("2025-09-01", "0.005", "500.00", [{"key": "a", "btc": "0.002"}, {"key": "a", "btc": "0.003"}])],
        "Transaction 2 chooses the coins from 'a' twice: one line per acquisition."),
    "0 BTC": (
        [A, D, _spend("2025-09-01", "0.005", "500.00", _chosen(a="0", d="0.005"))],
        "Transaction 3 chooses '0' BTC of the coins from 'a': a choice is above 0 BTC"),
    "below 0 BTC": (
        [A, D, _spend("2025-09-01", "0.005", "500.00", _chosen(a="-0.001", d="0.006"))],
        "Transaction 3 chooses '-0.001' BTC of the coins from 'a'"),
    "past the satoshi": (
        [A, _spend("2025-09-01", "0.005", "500.00", _chosen(a="0.0050000001"))],
        "Transaction 2 chooses '0.0050000001' BTC of the coins from 'a': a choice is above 0 BTC, to the satoshi"),
    "no number": (
        [A, _spend("2025-09-01", "0.005", "500.00", _chosen(a="half"))],
        "Transaction 2 chooses 'half' BTC of the coins from 'a'"),
    "not a list": (
        [A, _spend("2025-09-01", "0.005", "500.00", {"a": "0.005"})],
        "Transaction 2's chosen_coins is a list of lines, each with only a key and a btc."),
    "a line with more": (
        [A, _spend("2025-09-01", "0.005", "500.00", [{"key": "a", "btc": "0.005", "lot": 1}])],
        "Transaction 2's chosen_coins is a list of lines, each with only a key and a btc."),
    "a key twice": (
        [A, _deposit("2024-06-01", "0.02", "1000.00", "a")],
        "Transaction 2's key 'a' is transaction 1's too: a key names one acquisition."),
    "a key on a spend": (
        [A, {**_spend("2025-09-01", "0.005", "500.00"), "key": "s"}],
        "Transaction 2 has a key, 's', but didn't acquire bitcoin: only a Buy, or a Deposit into a bitcoin account"),
    "a key on dollars": (
        [{**COINS, "to_account_id": BANK, "amount": "100.00", "fee_currency": "USD", "key": "usd"}],
        "Transaction 1 has a key, 'usd', but didn't acquire bitcoin"),
    "a key that isn't text": (
        [{**A, "key": 7}],
        "Transaction 1's key is 7: a key is a name, in text."),
    "an empty key": (
        [{**A, "key": " "}],
        "Transaction 1's key is ' ': a key is a name, in text."),
}


@pytest.mark.parametrize("rows, message", BAD_CHOICES.values(), ids=BAD_CHOICES)
def test_a_choice_the_rules_dont_allow_stops_the_replay(rows, message):
    """A choice the app would refuse (plan 4.5, 7.1, call (c)), or one the
    wallet doesn't hold when the coins leave ((j)(2): the units identified
    are units in the wallet), stops the replay, naming the row: guessing
    would hide a difference."""
    with pytest.raises(ValueError, match=re.escape(message)):
        independent.replay(rows)
