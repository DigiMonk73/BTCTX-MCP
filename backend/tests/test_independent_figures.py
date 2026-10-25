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
