"""
scripts/independent_figures.py recomputes the reference test ledger's tax
figures from the rules, without the app's code (#150, #80 item 2). Here it
must agree to the cent with testdata/reference_figures.json, the app's own
figures, which test_seed_ledger.py keeps current. A difference is a bug in
one of the two calculations or a meant change: find out which before
changing either.
"""

import ast
import json

from backend.tests.conftest import INDEPENDENT_FIGURES, independent_figures


independent = independent_figures()


def test_an_independent_calculation_gives_the_apps_figures():
    # The script shares three conventions with the app on purpose (its
    # docstring): a lot's cost and a disposal's proceeds shared as running
    # totals (#100, #297), and an exact half cent rounded up. With those,
    # every Form 8949 row, Schedule D line, box total, gains summary, income
    # figure, rebate, gift and year-end lot of every year must be the same.
    transactions = json.loads(independent.LEDGER.read_text())["transactions"]
    ledger = independent.replay(transactions, independent.ROUNDING["half-up"])
    saved = json.loads(independent.FIGURES.read_text())["years"]
    found = [f"{year}: {line}" for year, figures in saved.items()
             for line in independent.differences(independent.year_figures(ledger, int(year)), figures)]
    assert not found, "\n".join(found)


def test_the_independent_calculation_uses_nothing_of_the_app():
    imported = set()
    for node in ast.walk(ast.parse(INDEPENDENT_FIGURES.read_text())):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert not imported & {"backend", "btctx_mcp", "scripts"}, imported
