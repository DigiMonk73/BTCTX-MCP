"""
The user's accounts by name (BitcoinTX 2.0 spec 5.12).

Every bank, wallet and exchange account BitcoinTX lists (GET /api/accounts/,
hidden ones too) is named by its name now, compared as BitcoinTX compares
names (5.1: name_key); Bank, Wallet, Exchange USD and Exchange BTC are the
reserved names of the first bank, wallet and exchange, and External is
everything outside. A BitcoinTX before 2.0 doesn't let the AI key list its
accounts: the connector then knows its four, by 1.x's names.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

YOUR_KINDS = ("bank", "wallet", "exchange")
EXTERNAL_ID = 99
# The fields get_portfolio shows of each account
SHOWN = ("id", "name", "kind", "currency", "exchange", "hidden")
# The reserved names (backend/constants.py RESERVED_NAMES) that name your
# accounts: in a file they always mean the first bank, wallet and exchange
RESERVED = {"Bank": 1, "Wallet": 2, "Exchange USD": 3, "Exchange BTC": 4}
# A BitcoinTX before 2.0: its four accounts, as 2.0 lists them
ACCOUNTS_1X = [
    {"id": 1, "name": "Bank", "kind": "bank", "currency": "USD", "exchange": None, "hidden": False},
    {"id": 2, "name": "Wallet", "kind": "wallet", "currency": "BTC", "exchange": None, "hidden": False},
    {"id": 3, "name": "Exchange USD", "kind": "exchange", "currency": "USD", "exchange": "Exchange", "hidden": False},
    {"id": 4, "name": "Exchange BTC", "kind": "exchange", "currency": "BTC", "exchange": "Exchange", "hidden": False},
]

UNKNOWN = ("Unknown account '{name}'. The user's accounts: {names}, and External. If it's a wallet or exchange "
           "they haven't added, ask them to add it in BitcoinTX (Settings, Wallets, exchanges and banks); never "
           "put it in another account.")
RENAMED = "'{name}' is now called '{now}'. Use that name."
# A BitcoinTX before 2.0 can't add an account: no point asking the user to
UNKNOWN_1X = "Unknown account '{name}'. This BitcoinTX is older than 2.0 and has only these accounts: {names}, and External."

# Characters nothing shows, left out when names are compared: BitcoinTX's
# own list (backend/services/account.py INVISIBLE; a test checks the two agree)
INVISIBLE = ((0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5),
             (0x180B, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F), (0x2800, 0x2800),
             (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8),
             (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF))


def name_key(name: str) -> str:
    """Two names are alike when this is the same, as BitcoinTX compares them
    (backend/services/account.py name_key): normalised, casefolded, without
    what nothing shows, every run of spaces one space, trimmed."""
    seen = "".join(c for c in unicodedata.normalize("NFC", name) if not _invisible(c))
    text = unicodedata.normalize("NFC", seen.casefold())
    text = "".join(" " if unicodedata.category(c) == "Zs" else c for c in text)
    return re.sub(" +", " ", text).strip(" ")


def _invisible(c: str) -> bool:
    return any(low <= ord(c) <= high for low, high in INVISIBLE)


RESERVED_KEYS = {name_key(name): account_id for name, account_id in RESERVED.items()}


class AccountNames:
    """The user's accounts as BitcoinTX listed them: by name, by id, and
    what to say of a name that's none of them."""

    def __init__(self, listed: list[dict[str, Any]] | None):
        """`listed`: the account list's answer; None from a BitcoinTX before
        2.0 (its four accounts)."""
        self.before_2_0 = listed is None
        listed = ACCOUNTS_1X if listed is None else listed
        self.yours = [{key: account.get(key) for key in SHOWN} for account in listed
                      if account.get("kind") in YOUR_KINDS]
        self._names = {account["id"]: account["name"] for account in self.yours}
        self._by_key = {name_key(account["name"]): (account["id"], account["name"]) for account in self.yours}

    def find(self, name: str) -> tuple[int, str] | None:
        """(id, name now) of the account `name` names, External's too; None
        for a name it doesn't know, or a renamed account's reserved name."""
        key = name_key(name)
        if key == name_key("External"):
            return EXTERNAL_ID, "External"
        return self._by_key.get(key)

    def name(self, account_id: Any) -> Any:
        """An account's name now, External's; the id itself for one not listed."""
        return "External" if account_id == EXTERNAL_ID else self._names.get(account_id, account_id)

    def refusal(self, name: str) -> str:
        """Why `name` names none of the user's accounts."""
        now = self._names.get(RESERVED_KEYS.get(name_key(name)))
        if now is not None:
            return RENAMED.format(name=name, now=now)
        names = ", ".join(account["name"] for account in self.yours)
        return (UNKNOWN_1X if self.before_2_0 else UNKNOWN).format(name=name, names=names)
