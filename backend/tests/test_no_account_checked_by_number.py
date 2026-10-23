"""
No account is asked about by its number (spec 5.4, card B3 #348): outside
constants.py, the migrations and the tests, backend code never names
BTC_ACCOUNTS (gone), and names 1.x's account constants or name maps only
where a later card still changes them, listed below with that card. The
list is exact, so a new check by number fails, and so does a place a card
has fixed until its line goes; B7a empties it. External (ACCOUNT_EXTERNAL)
and the fee accounts stay fixed ids everywhere (5.4).
"""

import ast
from collections import Counter
from pathlib import Path

import backend.constants

BACKEND = Path(__file__).resolve().parents[1]
NAMES = {"BTC_ACCOUNTS", "ACCOUNT_ID_TO_NAME", "ACCOUNT_NAME_TO_ID",
         "ACCOUNT_BANK", "ACCOUNT_WALLET", "ACCOUNT_EXCHANGE_USD", "ACCOUNT_EXCHANGE_BTC"}

# (file, name): how many times, and the card that changes them
STILL_BY_NUMBER = {
    # B4: Form 8949's boxes by the book (5.7: _broker_reporting's Sell and covered lot)
    ("services/reports/form_8949.py", "ACCOUNT_EXCHANGE_BTC"): 2,
    # B5: files name accounts by the book (5.11: the CSV preview and export, the AI import, River)
    ("routers/backup.py", "ACCOUNT_ID_TO_NAME"): 2,
    ("routers/river_import.py", "ACCOUNT_NAME_TO_ID"): 1,
    ("services/csv_import.py", "ACCOUNT_ID_TO_NAME"): 2,
    ("services/csv_import.py", "ACCOUNT_NAME_TO_ID"): 3,
    ("services/entry_import.py", "ACCOUNT_ID_TO_NAME"): 4,
    ("services/river_import.py", "ACCOUNT_ID_TO_NAME"): 2,
    ("services/river_import.py", "ACCOUNT_BANK"): 1,
    ("services/river_import.py", "ACCOUNT_WALLET"): 2,
    ("services/river_import.py", "ACCOUNT_EXCHANGE_USD"): 2,
    ("services/river_import.py", "ACCOUNT_EXCHANGE_BTC"): 5,
    # B7a: the gate (5.10: USER_ACCOUNTS, 1 to 4 and 99, until the book's yours())
    ("services/transaction.py", "ACCOUNT_BANK"): 1,
    ("services/transaction.py", "ACCOUNT_WALLET"): 1,
    ("services/transaction.py", "ACCOUNT_EXCHANGE_USD"): 1,
    ("services/transaction.py", "ACCOUNT_EXCHANGE_BTC"): 1,
}


def _uses() -> Counter:
    found = Counter()
    for path in sorted(BACKEND.rglob("*.py")):
        relative = path.relative_to(BACKEND).as_posix()
        if relative.startswith(("tests/", "migrations/")) or relative == "constants.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(), relative)):
            # a bare name, or one read off the module (constants.ACCOUNT_WALLET)
            name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None
            if name in NAMES:
                found[(relative, name)] += 1
    return found


def test_no_account_checked_by_number():
    assert dict(_uses()) == STILL_BY_NUMBER


def test_btc_accounts_is_gone():
    assert not hasattr(backend.constants, "BTC_ACCOUNTS")
