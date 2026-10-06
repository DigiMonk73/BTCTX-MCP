#!/usr/bin/env python3
"""
Load a full, realistic TEST ledger (2023 to 2026) into a running BitcoinTX
over its API: a test VM, a Docker container, `make preview`. Never your
real ledger: it refuses one that already has transactions, and the Mac
app's address (127.0.0.1:8765) outright.

    python scripts/seed_ledger.py --url https://your-server.local:PORT \
        --user NAME --password-stdin --ca root-ca.crt < password-file
    python scripts/seed_ledger.py --url http://127.0.0.1:8080 --user me \
        --password-stdin --setup-code XXXX-XXXX-XXXX     # claim a fresh install first

The password comes from stdin (--password-stdin) or BTCTX_PASSWORD, never
the command line, where other processes could read it. --setup-code claims
an install still on the default login (the code is in its log and in
setup-code.txt in its data folder) as --user with that password (12+
characters), as scripts/smoke_test.py does. --ca trusts a root certificate,
e.g. your StartOS server's.

The ledger: backend/tests/transaction_seed_data.json (65 rows, 2023-2025,
every deposit and withdrawal kind), with every USD value a price lookup
would fill given (network fees, gift and donation values), plus 2026 rows
that land in every Form 8949 box a 2026 return can have: G (exchange sale
of BTC bought there in 2026), H and K (older exchange BTC), J (a sale whose
1099-DA showed basis), I and L (self-custody spends and network fees). So
it loads with the price source Off and contacts nothing but the server.
Settings are left as they are.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
import ssl
import sys
from bisect import bisect_left
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parent.parent
LEDGER_2023_2025 = ROOT / "backend" / "tests" / "transaction_seed_data.json"
MAC_APP_PORT = 8765  # desktop/: the owner's real ledger
PASSWORD_ENV = "BTCTX_PASSWORD"
CENT = Decimal("0.01")

EXCHANGE_USD, EXCHANGE_BTC, WALLET, EXTERNAL = 3, 4, 2, 99

# 2026, in order, one box per comment. Exchange BTC starts the year with
# 2.06461 BTC: 1.56461 from 2024, then 0.15 (2025-02-15), 0.05 (2025-05-01),
# 0.12, 0.10 and 0.08 from later in 2025; FIFO sells the oldest first.
LEDGER_2026 = [
    # All but 0.56461 of the 2024 BTC: long-term, not covered: Box K
    {"type": "Sell", "timestamp": "2026-01-15T15:00:00Z", "from_account_id": EXCHANGE_BTC,
     "to_account_id": EXCHANGE_USD, "amount": "1.0", "gross_proceeds_usd": "152000.00",
     "fee_amount": "228.00", "fee_currency": "USD"},
    # The rest of the 2024 BTC, and the 1099-DA showed its basis: Box J
    {"type": "Sell", "timestamp": "2026-02-02T15:00:00Z", "from_account_id": EXCHANGE_BTC,
     "to_account_id": EXCHANGE_USD, "amount": "0.56461", "gross_proceeds_usd": "83562.28",
     "fee_amount": "125.34", "fee_currency": "USD", "broker_reporting": "basis"},
    # 2025 BTC held a year or less, bought before 2026 (not covered): Box H
    {"type": "Sell", "timestamp": "2026-02-09T15:00:00Z", "from_account_id": EXCHANGE_BTC,
     "to_account_id": EXCHANGE_USD, "amount": "0.20", "gross_proceeds_usd": "29200.00",
     "fee_amount": "43.80", "fee_currency": "USD"},
    # The last 0.30 to cold storage; the network fee is a disposal: Box I
    {"type": "Transfer", "timestamp": "2026-03-16T15:00:00Z", "from_account_id": EXCHANGE_BTC,
     "to_account_id": WALLET, "amount": "0.30", "fee_amount": "0.00004", "fee_currency": "BTC",
     "fee_usd": "5.60"},
    # Exchange BTC is empty: from here on it holds BTC bought there in 2026 (covered)
    {"type": "Buy", "timestamp": "2026-03-20T15:00:00Z", "from_account_id": EXCHANGE_USD,
     "to_account_id": EXCHANGE_BTC, "amount": "0.25", "cost_basis_usd": "35052.50",
     "fee_amount": "52.50", "fee_currency": "USD"},
    # Covered, short-term: Box G
    {"type": "Sell", "timestamp": "2026-05-04T15:00:00Z", "from_account_id": EXCHANGE_BTC,
     "to_account_id": EXCHANGE_USD, "amount": "0.10", "gross_proceeds_usd": "13800.00",
     "fee_amount": "20.70", "fee_currency": "USD"},
    # Spent straight from the exchange account: no 1099-DA, short-term: Box I (its fee too)
    {"type": "Withdrawal", "timestamp": "2026-06-01T15:00:00Z", "from_account_id": EXCHANGE_BTC,
     "to_account_id": EXTERNAL, "amount": "0.02", "fee_amount": "0.00002", "fee_currency": "BTC",
     "fee_usd": "2.84", "purpose": "Spent", "gross_proceeds_usd": "2840.00"},
    # Income into self custody
    {"type": "Deposit", "timestamp": "2026-06-15T15:00:00Z", "from_account_id": EXTERNAL,
     "to_account_id": WALLET, "amount": "0.01", "fee_amount": "0", "fee_currency": "BTC",
     "source": "Income", "cost_basis_usd": "1425.00"},
    # Self-custody spend of the wallet's oldest (2023) BTC: Box L (its fee too)
    {"type": "Withdrawal", "timestamp": "2026-07-01T15:00:00Z", "from_account_id": WALLET,
     "to_account_id": EXTERNAL, "amount": "0.05", "fee_amount": "0.00003", "fee_currency": "BTC",
     "fee_usd": "4.35", "purpose": "Spent", "gross_proceeds_usd": "7250.00"},
    # Covered, short-term again: Box G
    {"type": "Sell", "timestamp": "2026-08-03T15:00:00Z", "from_account_id": EXCHANGE_BTC,
     "to_account_id": EXCHANGE_USD, "amount": "0.05", "gross_proceeds_usd": "7500.00",
     "fee_amount": "11.25", "fee_currency": "USD"},
    # A gift is not a sale, but its network fee is: Box L
    {"type": "Withdrawal", "timestamp": "2026-09-01T15:00:00Z", "from_account_id": WALLET,
     "to_account_id": EXTERNAL, "amount": "0.01", "fee_amount": "0.00002", "fee_currency": "BTC",
     "fee_usd": "2.96", "fmv_usd": "1480.00", "purpose": "Gift"},
]


class SeedError(Exception):
    pass


# The ledger
def ledger_rows() -> list[dict]:
    """Every transaction to create, oldest first, each as the API takes it."""
    with open(LEDGER_2023_2025) as f:
        base = [{k: v for k, v in row.items() if k not in ("id", "notes")} for row in json.load(f)]
    rows = sorted(base, key=lambda r: r["timestamp"]) + [dict(r) for r in LEDGER_2026]
    fill_usd_values(rows)
    return rows


def fill_usd_values(rows: list[dict]) -> None:
    """Give each row the USD values the server would otherwise price from
    that day's BTC price: a BTC network fee's value, and a gift's or
    donation's. The price is the ledger's own, from the nearest row that
    names one (a buy, a sale, a valued deposit)."""
    priced = sorted((r["timestamp"], p) for r in rows if (p := _implied_price(r)) is not None)
    times = [t for t, _ in priced]

    def price_at(timestamp: str) -> Decimal:
        i = bisect_left(times, timestamp)
        near = [j for j in (i - 1, i) if 0 <= j < len(priced)]
        return priced[min(near, key=lambda j: abs(_days(times[j]) - _days(timestamp)))][1]

    for r in rows:
        btc_fee = r.get("fee_currency") == "BTC" and Decimal(r.get("fee_amount") or 0) > 0
        if btc_fee and r.get("fee_usd") is None:
            r["fee_usd"] = str((Decimal(r["fee_amount"]) * price_at(r["timestamp"])).quantize(CENT, ROUND_HALF_UP))
        if (r.get("purpose") or "").lower() in ("gift", "donation") and r.get("fmv_usd") is None:
            r["fmv_usd"] = str((Decimal(r["amount"]) * price_at(r["timestamp"])).quantize(CENT, ROUND_HALF_UP))


def _implied_price(row: dict) -> Decimal | None:
    """USD per BTC a row states: a buy's cost (less a USD fee), a sale's or
    spend's gross proceeds, a BTC deposit's basis."""
    amount = Decimal(row.get("amount") or 0)
    usd_fee = Decimal(row.get("fee_amount") or 0) if row.get("fee_currency") == "USD" else Decimal(0)
    if row["type"] == "Buy" and row.get("cost_basis_usd"):
        return (Decimal(row["cost_basis_usd"]) - usd_fee) / amount
    if row["type"] in ("Sell", "Withdrawal") and row.get("gross_proceeds_usd"):
        return Decimal(row["gross_proceeds_usd"]) / amount
    if row["type"] == "Deposit" and row.get("fee_currency") == "BTC" and Decimal(row.get("cost_basis_usd") or 0) > 0:
        return Decimal(row["cost_basis_usd"]) / amount
    return None


def _days(timestamp: str) -> int:
    from datetime import datetime

    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).toordinal()


# The server
def refuse_mac_app(url: str) -> None:
    """The Mac app holds its owner's real ledger and listens on this
    computer's port 8765: refuse any address that reaches it (127.1,
    localhost., [::] too, as the system resolves them)."""
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        raise SeedError(f"{url} is not a valid address") from None
    if port != MAC_APP_PORT:
        return
    host = (parts.hostname or "").rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        raise SeedError(f"{url} is the Mac app's address: its ledger is real data. Never seed it.")
    try:
        addresses = {info[4][0].split("%")[0] for info in socket.getaddrinfo(host, port)}
    except socket.gaierror:
        return  # nothing to connect to
    if any(_this_computer(a) for a in addresses):
        raise SeedError(f"{url} is the Mac app's address: its ledger is real data. Never seed it.")


def _this_computer(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    ip = getattr(ip, "ipv4_mapped", None) or ip  # ::ffff:127.0.0.1
    return ip.is_loopback or ip.is_unspecified


def connect(url: str, ca: str | None) -> httpx.Client:
    verify: ssl.SSLContext | bool = ssl.create_default_context(cafile=ca) if ca else True
    return httpx.Client(base_url=url, timeout=120, verify=verify)


def log_in(c: httpx.Client, user: str, password: str, setup_code: str | None) -> None:
    if setup_code:
        r = c.post("/api/users/reset-account", json={"username": user, "password": password, "setup_code": setup_code})
        if r.status_code != 200:
            raise SeedError(f"claiming the install failed: {r.status_code} {r.text[:300]}")
    r = c.post("/api/login", json={"username": user, "password": password})
    if r.status_code != 200:
        raise SeedError(f"login failed: {r.status_code} {r.text[:300]}")


def seed(c: httpx.Client, rows: list[dict] | None = None) -> int:
    """Create every row on a logged-in client; refuses a ledger that isn't
    empty. Returns how many were created."""
    r = c.get("/api/transactions")
    if r.status_code != 200:
        raise SeedError(f"couldn't read the ledger: {r.status_code} {r.text[:300]}")
    if r.json():
        raise SeedError(f"the ledger already has {len(r.json())} transactions: seed only an empty test install")
    rows = ledger_rows() if rows is None else rows
    for n, row in enumerate(rows, start=1):
        r = c.post("/api/transactions", json=row)
        if r.status_code != 200:
            raise SeedError(f"row {n} ({row['timestamp']} {row['type']}) refused: {r.status_code} {r.text[:300]}. "
                            f"The {n - 1} rows before it are in the ledger: delete them all before running again.")
    return len(rows)


def read_password(args: argparse.Namespace) -> str:
    password = sys.stdin.readline().rstrip("\r\n") if args.password_stdin else os.environ.get(PASSWORD_ENV, "")
    if not password:
        raise SeedError(f"No password: pipe it to --password-stdin or set {PASSWORD_ENV}.")
    return password


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="the server, e.g. https://host:port")
    ap.add_argument("--user", required=True)
    ap.add_argument("--password-stdin", action="store_true", help=f"read the password from stdin (default: ${PASSWORD_ENV})")
    ap.add_argument("--setup-code", help="claim an install still on the default login first, as --user")
    ap.add_argument("--ca", help="a root certificate to trust (StartOS: your server's root CA)")
    args = ap.parse_args(argv)
    url = args.url.rstrip("/")
    try:
        refuse_mac_app(url)
        password = read_password(args)
        with connect(url, args.ca) as c:
            log_in(c, args.user, password, args.setup_code)
            created = seed(c)
            c.post("/api/logout")
    except (SeedError, httpx.HTTPError) as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    print(f"✓ {created} transactions loaded into {url} (2023-2026)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
