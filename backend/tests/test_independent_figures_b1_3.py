"""2.0-B1 step 3 (5.15; 5.1, 5.4): one pile per bitcoin account. A fee account (kind "fee", e.g. BTC Fees 5) is not a bitcoin account and has no pile. Written by Silas; read-only to the implementer."""

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


independent = _script("independent_figures_b1_3")

ACCOUNTS = {"accounts": [
    {"id": 2, "name": "Wallet", "currency": "BTC", "kind": "wallet"},
    {"id": 5, "name": "BTC Fees", "currency": "BTC", "kind": "fee"},
    {"id": 7, "name": "Coldcard", "currency": "BTC", "kind": "wallet"},
    {"id": 99, "name": "External", "currency": None, "kind": "external"},
]}


def test_the_fixed_accounts_have_their_kinds():
    kinds = {i: a["kind"] for i, a in independent.read_accounts({}).items()}
    assert kinds == {1: "bank", 2: "wallet", 3: "exchange", 4: "exchange", 5: "fee", 6: "fee", 99: "external"}


def test_by_default_the_piles_are_wallet_and_exchange_btc():
    assert sorted(independent.replay([]).lots) == [2, 4]


def test_each_bitcoin_account_of_the_ledger_keeps_its_own_pile():
    accounts = independent.read_accounts(ACCOUNTS)
    ledger = independent.replay([
        tx("Deposit", "2024-01-15T10:00:00Z", 99, 7, "1.00000000", source="My BTC", cost_basis_usd="100.00"),
        tx("Transfer", "2024-03-01T10:00:00Z", 7, 2, "0.40000000"),
    ], accounts=accounts)
    assert sorted(ledger.lots) == [2, 7]  # no pile for the fee account
    held = {(h["account"], h["acquired"], h["quantity"], h["cost"])
            for h in independent.year_figures(ledger, 2024)["end_of_year_holdings"]}
    assert held == {("Coldcard", "2024-01-15T10:00:00+00:00", "0.60000000", "60.00"),
                    ("Wallet", "2024-01-15T10:00:00+00:00", "0.40000000", "40.00")}
