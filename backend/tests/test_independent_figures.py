"""
scripts/independent_figures.py recomputes the reference test ledger's tax
figures from the rules alone, without the app's code (#150, #80 item 2).
Here it must agree to the cent with testdata/reference_figures.json, the
app's own figures, which test_seed_ledger.py keeps current. A difference is
a bug in one of the two calculations or a meant change: find out which
before changing either.
"""

import ast
import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "independent_figures.py"
YEARS = [2023, 2024, 2025, 2026]


def _script():
    spec = importlib.util.spec_from_file_location("independent_figures", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look their module up
    spec.loader.exec_module(module)
    return module


independent = _script()


def test_an_independent_calculation_gives_the_apps_figures():
    # The one convention the two share on purpose: an exact half cent rounds
    # down, as the app does (#100). Every Form 8949 row, Schedule D line,
    # income and rebate figure, gift and year-end lot must then be the same.
    transactions = json.loads(independent.LEDGER.read_text())["transactions"]
    ledger = independent.replay(transactions, independent.ROUNDING["half-down"])
    saved = json.loads(independent.FIGURES.read_text())["years"]
    found = [f"{year}: {line}" for year in YEARS
             for line in independent.differences(independent.year_figures(ledger, year), saved[str(year)])]
    assert not found, "\n".join(found)


def test_the_independent_calculation_uses_nothing_of_the_app():
    imported = set()
    for node in ast.walk(ast.parse(SCRIPT.read_text())):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert not imported & {"backend", "btctx_mcp", "scripts"}, imported
