"""
Spec 5.5's table as test data (card B3, #348): a book with 1.x's accounts
and a second wallet, bank and exchange, and every kind of pair, allowed or
refused, with the (side, message) list account_problems gives for it. The
engine's and the CSV import's tests both run it, so they must agree.

The ids are the ones the account API gives a fresh ledger for: add a wallet
"Cold Storage", a bank "Credit Union", then an exchange "Kraken" (add_them).
"""

from backend.services.account import AccountBook, BookAccount

BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, BTC_FEES, USD_FEES, EXTERNAL = 1, 2, 3, 4, 5, 6, 99
COLD, CREDIT_UNION, KRAKEN_USD, KRAKEN_BTC = 100, 101, 102, 103

BOOK = AccountBook([
    BookAccount(BANK, "Bank", "bank", "USD"),
    BookAccount(WALLET, "Wallet", "wallet", "BTC"),
    BookAccount(EXCHANGE_USD, "Exchange USD", "exchange", "USD", 1),
    BookAccount(EXCHANGE_BTC, "Exchange BTC", "exchange", "BTC", 1),
    BookAccount(BTC_FEES, "BTC Fees", "fee", "BTC"),
    BookAccount(USD_FEES, "USD Fees", "fee", "USD"),
    BookAccount(COLD, "Cold Storage", "wallet", "BTC"),
    BookAccount(CREDIT_UNION, "Credit Union", "bank", "USD"),
    BookAccount(KRAKEN_USD, "Kraken USD", "exchange", "USD", 2),
    BookAccount(KRAKEN_BTC, "Kraken BTC", "exchange", "BTC", 2),
])

# 5.5's messages, exactly
DEPOSIT_FROM = "A Deposit comes from External."
DEPOSIT_INTO = "A Deposit goes into one of your accounts, not External."
WITHDRAWAL_FROM = "A Withdrawal comes from one of your accounts, not External."
WITHDRAWAL_TO = "A Withdrawal goes to External."
BETWEEN = "A Transfer is between two of your accounts, not External."
TO_ITSELF = "A Transfer goes to another account: only a bitcoin account can send to itself (a consolidation)."
ONE_CURRENCY = "A Transfer stays in one currency: bitcoin between bitcoin accounts, dollars between dollar accounts."
PAID_FROM = "A Buy is paid from a bank or from an exchange's USD account."
BUY_INTO = "A Buy's bitcoin goes into an exchange's BTC account."
SELL_FROM = "A Sell is from an exchange's BTC account."


def buy_on(paid_from: str, its_btc: str) -> str:
    return f"A Buy paid from {paid_from} goes into {its_btc}: an exchange's dollars buy only on that exchange."


def sell_into(sold_from: str, its_usd: str) -> str:
    return f"A Sell from {sold_from} goes into {its_usd}."


# (type, from, to, [(side, message)]): every row of 5.5's table, both ways
PAIRS = [
    ("Deposit", EXTERNAL, BANK, []),
    ("Deposit", EXTERNAL, COLD, []),
    ("Deposit", EXTERNAL, KRAKEN_BTC, []),
    ("Deposit", EXTERNAL, CREDIT_UNION, []),
    ("Deposit", BANK, WALLET, [("from", DEPOSIT_FROM)]),
    ("Deposit", EXTERNAL, EXTERNAL, [("to", DEPOSIT_INTO)]),
    ("Deposit", EXTERNAL, BTC_FEES, [("to", DEPOSIT_INTO)]),
    ("Deposit", COLD, EXTERNAL, [("from", DEPOSIT_FROM), ("to", DEPOSIT_INTO)]),
    ("Withdrawal", WALLET, EXTERNAL, []),
    ("Withdrawal", CREDIT_UNION, EXTERNAL, []),
    ("Withdrawal", KRAKEN_USD, EXTERNAL, []),
    ("Withdrawal", EXTERNAL, EXTERNAL, [("from", WITHDRAWAL_FROM)]),
    ("Withdrawal", WALLET, BANK, [("to", WITHDRAWAL_TO)]),
    ("Withdrawal", EXTERNAL, COLD, [("from", WITHDRAWAL_FROM), ("to", WITHDRAWAL_TO)]),
    ("Transfer", BANK, EXCHANGE_USD, []),
    ("Transfer", BANK, CREDIT_UNION, []),
    ("Transfer", EXCHANGE_USD, KRAKEN_USD, []),
    ("Transfer", CREDIT_UNION, KRAKEN_USD, []),
    ("Transfer", WALLET, COLD, []),
    ("Transfer", COLD, KRAKEN_BTC, []),
    ("Transfer", EXCHANGE_BTC, KRAKEN_BTC, []),
    ("Transfer", WALLET, WALLET, []),
    ("Transfer", COLD, COLD, []),
    ("Transfer", KRAKEN_BTC, KRAKEN_BTC, []),
    ("Transfer", EXTERNAL, WALLET, [("from", BETWEEN)]),
    ("Transfer", COLD, EXTERNAL, [("to", BETWEEN)]),
    ("Transfer", EXTERNAL, EXTERNAL, [("from", BETWEEN), ("to", BETWEEN)]),
    ("Transfer", WALLET, USD_FEES, [("to", BETWEEN)]),
    ("Transfer", BANK, BANK, [("to", TO_ITSELF)]),
    ("Transfer", KRAKEN_USD, KRAKEN_USD, [("to", TO_ITSELF)]),
    ("Transfer", BANK, WALLET, [("to", ONE_CURRENCY)]),
    ("Transfer", COLD, CREDIT_UNION, [("to", ONE_CURRENCY)]),
    ("Transfer", KRAKEN_BTC, KRAKEN_USD, [("to", ONE_CURRENCY)]),
    ("Buy", BANK, EXCHANGE_BTC, []),
    ("Buy", EXCHANGE_USD, EXCHANGE_BTC, []),
    ("Buy", CREDIT_UNION, KRAKEN_BTC, []),
    ("Buy", KRAKEN_USD, KRAKEN_BTC, []),
    ("Buy", BANK, KRAKEN_BTC, []),
    ("Buy", WALLET, EXCHANGE_BTC, [("from", PAID_FROM)]),
    ("Buy", EXCHANGE_BTC, EXCHANGE_BTC, [("from", PAID_FROM)]),
    ("Buy", BANK, WALLET, [("to", BUY_INTO)]),
    ("Buy", EXCHANGE_USD, KRAKEN_USD, [("to", BUY_INTO)]),
    ("Buy", KRAKEN_USD, EXCHANGE_BTC, [("to", buy_on("Kraken USD", "Kraken BTC"))]),
    ("Buy", EXCHANGE_USD, KRAKEN_BTC, [("to", buy_on("Exchange USD", "Exchange BTC"))]),
    ("Buy", COLD, WALLET, [("from", PAID_FROM), ("to", BUY_INTO)]),
    ("Sell", EXCHANGE_BTC, EXCHANGE_USD, []),
    ("Sell", KRAKEN_BTC, KRAKEN_USD, []),
    ("Sell", WALLET, EXCHANGE_USD, [("from", SELL_FROM)]),
    ("Sell", EXCHANGE_USD, EXCHANGE_USD, [("from", SELL_FROM)]),
    ("Sell", EXCHANGE_BTC, BANK, [("to", sell_into("Exchange BTC", "Exchange USD"))]),
    ("Sell", KRAKEN_BTC, EXCHANGE_USD, [("to", sell_into("Kraken BTC", "Kraken USD"))]),
    ("Sell", EXCHANGE_BTC, KRAKEN_USD, [("to", sell_into("Exchange BTC", "Exchange USD"))]),
]

MESSAGES = {message for *_pair, found in PAIRS for _side, message in found}


def pair_id(pair) -> str:
    tx_type, from_id, to_id, _found = pair
    return f"{tx_type}-{from_id}-{to_id}"


def add_them(client) -> None:
    """The book's second wallet, bank and exchange, through the account API."""
    for kind, name in (("wallet", "Cold Storage"), ("bank", "Credit Union"), ("exchange", "Kraken")):
        r = client.post("/api/accounts/", json={"kind": kind, "name": name})
        assert r.status_code == 201, r.text
