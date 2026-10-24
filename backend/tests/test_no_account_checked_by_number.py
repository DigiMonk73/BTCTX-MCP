"""
No account is asked about by its number (spec 5.4, cards B3 #348 and B7a
#354): outside constants.py, the migrations and the tests, backend code
never names BTC_ACCOUNTS or the name maps (gone), nor 1.x's first bank,
wallet or exchange by its constant: the book answers. A place that would is
listed below with the card that changes it; since B7a's gate, none is.
External (ACCOUNT_EXTERNAL) and the fee accounts stay fixed ids everywhere
(5.4).
"""

import ast
from collections import Counter
from pathlib import Path

import pytest

import backend.constants

BACKEND = Path(__file__).resolve().parents[1]
NAMES = {"BTC_ACCOUNTS", "ACCOUNT_ID_TO_NAME", "ACCOUNT_NAME_TO_ID",
         "ACCOUNT_BANK", "ACCOUNT_WALLET", "ACCOUNT_EXCHANGE_USD", "ACCOUNT_EXCHANGE_BTC"}

# (file, name): how many times, and the card that changes them
STILL_BY_NUMBER: dict[tuple[str, str], int] = {}


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


@pytest.mark.parametrize("name", ["BTC_ACCOUNTS", "ACCOUNT_ID_TO_NAME", "ACCOUNT_NAME_TO_ID"])
def test_1xs_account_lists_are_gone(name):
    """5.4: BTC_ACCOUNTS went with B3, the name maps with B5a (#350), once
    nothing used them: the book answers both ways."""
    assert not hasattr(backend.constants, name)
