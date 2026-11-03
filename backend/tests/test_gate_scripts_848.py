"""
The release gate's scripts (#848, scripts/gate/): figures.py's compare
gives PASS or FAIL per figure with both values and fails on any figure that
moved, never on one a new release only adds; the golden loader is the
golden ledger AGENT-TESTS.md's figures are worked out from.
"""

import ast
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "gate" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


figures = _load("figures")

SNAP = {
    "health": {"status": "ok", "version": "1.2.10", "schema": "0012"},
    "rows": 14,
    "balances": [{"name": "Wallet", "balance": 0.3998}, {"name": "Bank", "balance": 41000.0}],
    "gains": {"short_term_gains": 1192.0, "long_term_gains": 0.0},
    "avg_cost": {"averageCostBasis": 44993.81},
    "accounts": [],
    "review": {"Figures that Recalculate Ledger would change": 0},
    "reports": {"irs_2024": ["$15,000.00", "$11,500.00", "02/02/2024"], "irs_2024_sales_by_exchange": False},
}


def compared(tmp_path, capsys, after):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(SNAP))
    b.write_text(json.dumps(after))
    verdict = figures.compare(str(a), str(b))
    return verdict, capsys.readouterr().out.splitlines()


def test_the_same_figures_pass_each_by_name(tmp_path, capsys):
    verdict, lines = compared(tmp_path, capsys, SNAP)
    assert verdict == 0 and lines[-1].startswith("PASS")
    assert "PASS gains.short_term_gains: 1192.0" in lines and "PASS balance.Wallet: 0.3998" in lines
    assert not [line for line in lines if line.startswith("FAIL")]


@pytest.mark.parametrize("where", ["rows", "gain", "balance", "review", "report"])
def test_a_moved_figure_fails_with_both_values(tmp_path, capsys, where):
    after = copy.deepcopy(SNAP)
    if where == "rows":
        after["rows"] = 13
    elif where == "gain":
        after["gains"]["short_term_gains"] = 1191.99
    elif where == "balance":
        after["balances"][0]["balance"] = 0.3997
    elif where == "review":
        after["review"]["Figures that Recalculate Ledger would change"] = 2
    else:
        after["reports"]["irs_2024"][1] = "$11,500.01"
    verdict, lines = compared(tmp_path, capsys, after)
    failed = [line for line in lines if line.startswith("FAIL ")]
    assert verdict == 1 and lines[-1] == "FAIL: 1 moved" and len(failed) == 1
    assert "->" in failed[0]


def test_what_a_new_release_only_adds_is_noted_not_failed(tmp_path, capsys):
    after = copy.deepcopy(SNAP)
    after["health"] = {"status": "ok", "version": "2.0.0", "schema": "0101"}
    after["review"]["Transactions naming an account that doesn't exist"] = 0
    after["reports"]["irs_2024"].insert(2, "$0.00")
    after["reports"]["irs_2024_sales_by_exchange"] = True
    verdict, lines = compared(tmp_path, capsys, after)
    assert verdict == 0
    assert sum(line.startswith("NOTE ") for line in lines) == 3


def test_a_figure_gone_from_a_report_fails(tmp_path, capsys):
    after = copy.deepcopy(SNAP)
    del after["reports"]["irs_2024"][2]
    verdict, _ = compared(tmp_path, capsys, after)
    assert verdict == 1


def test_a_gain_turned_into_a_loss_of_the_same_size_fails(tmp_path, capsys):
    """The reports print a loss in parentheses: "($1,000.00)", Form 8949's "(9.74)"."""
    assert figures.FIGURE.findall("($1,000.00) (9.74) $5.00 -0.01000000 0.0002 BTC") == [
        "($1,000.00)", "(9.74)", "$5.00", "-0.01000000", "0.0002 BTC"]
    after = copy.deepcopy(SNAP)
    after["reports"]["irs_2024"][1] = "($11,500.00)"
    verdict, _ = compared(tmp_path, capsys, after)
    assert verdict == 1


@pytest.mark.parametrize("where", ["gains", "review", "reports"])
def test_a_figure_or_check_gone_fails(tmp_path, capsys, where):
    after = copy.deepcopy(SNAP)
    del after[where][next(iter(after[where]))]
    verdict, lines = compared(tmp_path, capsys, after)
    assert verdict == 1 and any("gone" in line for line in lines if line.startswith("FAIL "))


def test_an_error_on_both_sides_fails(tmp_path, capsys):
    snap = copy.deepcopy(SNAP)
    snap["reports"]["irs_2025"] = {"_error": 500, "_body": "Internal Server Error"}
    snap["balances"] = {"_error": 500, "_body": ""}
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(snap))
    b.write_text(json.dumps(snap))
    assert figures.compare(str(a), str(b)) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[-1] == "FAIL: 2 moved"
    assert figures.errors_in(snap) == ["snap.balances", "snap.reports.irs_2025"]


def test_the_golden_loader_holds_the_fourteen_rows():
    text = (ROOT / "scripts" / "gate" / "golden_loader.py").read_text()
    ledger = text[text.index("LEDGER = ["):text.index("\n]\n") + 2]
    rows = ast.literal_eval(ledger.split("=", 1)[1])
    assert len(rows) == 14 and rows[0]["timestamp"] == "2023-01-15T17:00:00Z"
    assert "golden_loader.py" in (ROOT / "docs" / "AGENT-TESTS.md").read_text()
