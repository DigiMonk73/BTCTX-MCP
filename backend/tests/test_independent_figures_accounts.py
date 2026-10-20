"""
2.0-B1 step 1 (docs/temp/2.0-accounts.md 5.15, 7.4 B1): the independent
calculation reads the ledger's accounts, an `accounts` list, else the six
fixed accounts and External. Written by Silas for the Grok trial; read-only
to the implementer.
"""

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "independent_figures.py"


def _script():
    spec = importlib.util.spec_from_file_location("independent_figures_b1", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


independent = _script()

FIXED = {
    1: ("Bank", "USD"),
    2: ("Wallet", "BTC"),
    3: ("Exchange USD", "USD"),
    4: ("Exchange BTC", "BTC"),
    5: ("BTC Fees", "BTC"),
    6: ("USD Fees", "USD"),
    99: ("External", None),
}


def test_read_accounts_defaults_to_the_six_fixed_and_external():
    found = independent.read_accounts({"transactions": []})
    assert {i: (a["name"], a["currency"]) for i, a in found.items()} == FIXED


def test_read_accounts_takes_the_ledgers_own_list():
    data = {"accounts": [
        {"id": 2, "name": "Wallet", "currency": "BTC"},
        {"id": 7, "name": "Coldcard", "currency": "BTC"},
        {"id": 8, "name": "Bank 2", "currency": "USD"},
    ], "transactions": []}
    found = independent.read_accounts(data)
    assert {i: (a["name"], a["currency"]) for i, a in found.items()} == {
        2: ("Wallet", "BTC"), 7: ("Coldcard", "BTC"), 8: ("Bank 2", "USD")}


def test_read_accounts_btc_ids_are_the_bitcoin_accounts():
    found = independent.read_accounts({"transactions": []})
    assert sorted(i for i, a in found.items() if a["currency"] == "BTC") == [2, 4, 5]
