#!/usr/bin/env python3
# Loads the golden ledger into an EMPTY BitcoinTX through its API.
import http.cookiejar
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

LEDGER = [
    {"type": "Deposit", "timestamp": "2023-01-15T17:00:00Z", "from_account_id": 99, "to_account_id": 1, "amount": "100000", "fee_amount": "0", "fee_currency": "USD", "source": "N/A"},
    {"type": "Buy", "timestamp": "2023-02-01T17:00:00Z", "from_account_id": 1, "to_account_id": 4, "amount": "1.0", "cost_basis_usd": "23000", "fee_amount": "0", "fee_currency": "USD"},
    {"type": "Buy", "timestamp": "2023-03-01T17:00:00Z", "from_account_id": 1, "to_account_id": 4, "amount": "0.5", "cost_basis_usd": "12000", "fee_amount": "0", "fee_currency": "USD"},
    {"type": "Transfer", "timestamp": "2023-06-01T16:00:00Z", "from_account_id": 4, "to_account_id": 2, "amount": "0.6", "fee_amount": "0.0002", "fee_currency": "BTC", "fee_usd": "10"},
    {"type": "Sell", "timestamp": "2023-09-10T16:00:00Z", "from_account_id": 4, "to_account_id": 3, "amount": "0.5", "gross_proceeds_usd": "13000", "fee_amount": "10", "fee_currency": "USD"},
    {"type": "Withdrawal", "timestamp": "2024-01-01T04:30:00Z", "from_account_id": 2, "to_account_id": 99, "amount": "0.01", "proceeds_usd": "400", "fee_amount": "0", "fee_currency": "BTC", "purpose": "Spent"},
    {"type": "Sell", "timestamp": "2024-02-02T17:00:00Z", "from_account_id": 4, "to_account_id": 3, "amount": "0.3", "gross_proceeds_usd": "15000", "fee_amount": "0", "fee_currency": "USD"},
    {"type": "Sell", "timestamp": "2024-03-02T17:00:00Z", "from_account_id": 4, "to_account_id": 3, "amount": "0.1", "gross_proceeds_usd": "6000", "fee_amount": "0", "fee_currency": "USD"},
    {"type": "Deposit", "timestamp": "2024-05-01T16:00:00Z", "from_account_id": 99, "to_account_id": 2, "amount": "0.02", "cost_basis_usd": "1000", "fee_amount": "0", "fee_currency": "BTC", "source": "Income"},
    {"type": "Withdrawal", "timestamp": "2024-06-01T16:00:00Z", "from_account_id": 2, "to_account_id": 99, "amount": "0.1", "fee_amount": "0", "fee_currency": "BTC", "purpose": "Gift", "fmv_usd": "6700"},
    {"type": "Buy", "timestamp": "2025-01-10T17:00:00Z", "from_account_id": 1, "to_account_id": 4, "amount": "0.2", "cost_basis_usd": "20000", "fee_amount": "0", "fee_currency": "USD"},
    {"type": "Sell", "timestamp": "2025-04-01T16:00:00Z", "from_account_id": 4, "to_account_id": 3, "amount": "0.05", "gross_proceeds_usd": "4000", "fee_amount": "0", "fee_currency": "USD"},
    {"type": "Withdrawal", "timestamp": "2025-05-01T16:00:00Z", "from_account_id": 2, "to_account_id": 99, "amount": "0.1", "proceeds_usd": "9000", "fee_amount": "0", "fee_currency": "BTC", "purpose": "Spent"},
    {"type": "Withdrawal", "timestamp": "2025-06-01T16:00:00Z", "from_account_id": 2, "to_account_id": 99, "amount": "0.01", "proceeds_usd": "1000", "fee_amount": "0.0001", "fee_currency": "BTC", "fee_usd": "5", "purpose": "Spent"},
]

URL = os.environ["BTCTX_URL"].rstrip("/")
tls = ssl.create_default_context(cafile=os.environ.get("BTCTX_CA") or None)
web = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                                  urllib.request.HTTPSHandler(context=tls),
                                  urllib.request.ProxyHandler({}))  # a test install, never through a proxy


def call(method, path, body=None, confirm=None):
    query = "" if confirm is None else "?confirm=" + urllib.parse.quote(confirm)
    req = urllib.request.Request(URL + path + query, method=method, headers={"Content-Type": "application/json"},
                                 data=None if body is None else json.dumps(body).encode())
    try:
        with web.open(req) as r:
            return json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        answer = e.read().decode()
        asked = _fingerprint(answer) if e.code == 409 and confirm is None else None
        if asked is not None:  # 2.0's past-year warning: every row here is in an earlier tax year
            return call(method, path, body, asked)
        sys.exit(f"{method} {path}: {e.code} {answer[:300]}")


def _fingerprint(answer):
    """The past-year warning's `confirm`, sent back once; None for any other 409."""
    try:
        asked = json.loads(answer).get("confirm")
    except (ValueError, AttributeError):
        return None
    return asked if isinstance(asked, str) else None


call("POST", "/api/login", {"username": os.environ["BTCTX_USER"], "password": os.environ["BTCTX_PASSWORD"]})
if call("GET", "/api/transactions"):
    sys.exit("The ledger is not empty: load the golden ledger only into an empty test install.")
call("PUT", "/api/settings/tax-timezone", {"timezone": "America/New_York", "chosen": True})
for tx in LEDGER:
    call("POST", "/api/transactions", tx)
print(len(call("GET", "/api/transactions")), "transactions loaded; tax timezone America/New_York")
