"""
scripts/independent_figures.py for its tests: loaded once (scripts/ isn't a
package, and one copy keeps one set of its dataclasses), and a transaction
as a ledger file holds it. Kept out of conftest.py: only these tests use it.
"""

import functools
import importlib.util
import sys
from pathlib import Path

INDEPENDENT_FIGURES = Path(__file__).resolve().parents[2] / "scripts" / "independent_figures.py"


@functools.cache
def independent_figures():
    spec = importlib.util.spec_from_file_location("independent_figures", INDEPENDENT_FIGURES)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look their module up
    spec.loader.exec_module(module)
    return module


def ledger_tx(kind, when, src, dst, amount, **more):
    """No fee unless given; a Transfer's fee in BTC, any other's in USD."""
    return {"type": kind, "timestamp": when, "from_account_id": src, "to_account_id": dst, "amount": amount,
            "fee_amount": "0", "fee_currency": "BTC" if kind == "Transfer" else "USD", **more}
