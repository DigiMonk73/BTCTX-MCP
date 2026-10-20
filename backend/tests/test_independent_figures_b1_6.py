"""2.0-B1 step 6 (5.6, #490): a dollar transfer between any two dollar accounts moves no bitcoin and makes no figure. Written by Silas; read-only to the implementer."""

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "independent_figures.py"


def _script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def tx(kind, when, src, dst, amount, **more):
    base = {"type": kind, "timestamp": when, "from_account_id": src, "to_account_id": dst, "amount": amount,
            "fee_amount": "0", "fee_currency": "BTC" if kind == "Transfer" else "USD"}
    base.update(more)
    return base


independent = _script("independent_figures_b1_6")

ACCOUNTS = {"accounts": [
    {"id": 1, "name": "Bank", "currency": "USD", "kind": "bank"},
    {"id": 3, "name": "Exchange USD", "currency": "USD", "kind": "exchange", "exchange_id": 1, "sends_1099da": True},
    {"id": 4, "name": "Exchange BTC", "currency": "BTC", "kind": "exchange", "exchange_id": 1, "sends_1099da": True},
    {"id": 6, "name": "USD Fees", "currency": "USD", "kind": "fee"},
    {"id": 7, "name": "Credit union", "currency": "USD", "kind": "bank"},
    {"id": 99, "name": "External", "currency": None, "kind": "external"},
]}


def test_dollar_transfers_between_any_dollar_accounts_make_no_figure():
    ledger = independent.replay([
        tx("Deposit", "2024-01-02T15:00:00Z", 99, 7, "1000.00"),
        tx("Transfer", "2024-01-03T15:00:00Z", 7, 1, "500.00", fee_amount="5.00", fee_currency="USD"),
        tx("Transfer", "2024-01-04T15:00:00Z", 1, 3, "495.00", fee_amount="1.00", fee_currency="USD"),
    ], accounts=independent.read_accounts(ACCOUNTS))
    assert ledger.rows == [] and ledger.lots == {4: []}
    figures = independent.year_figures(ledger, 2024)
    assert figures["form_8949"] == [] and figures["end_of_year_holdings"] == []
