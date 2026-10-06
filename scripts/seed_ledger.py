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

The ledger, 103 transactions: backend/tests/transaction_seed_data.json (65
rows, 2023-2025), what the broker's form showed for three of its sales,
rows it lacks, and 2026. Every year has every kind of transaction (each
deposit source and withdrawal purpose, transfers both ways, cash moves,
buys and sells) and every report has entries in each part, every Form 8949
box of 2024 (A-F), 2025 and 2026 (G-L) included; backend/tests/
test_seed_ledger.py checks it. Every USD value a price lookup would fill is
given (network fees, gift and donation values), so it loads with the price
source Off and contacts nothing but the server. Settings are left as they
are. A test tool: it lives in scripts/, which no build ships.
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

BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 2, 3, 4, 99


def _tx(kind: str, when: str, from_id: int, to_id: int, amount: str, fee: str = "0",
        fee_currency: str = "BTC", **fields: str) -> dict:
    """A row as the API takes it, at noon UTC that day."""
    return {"type": kind, "timestamp": f"{when}T12:00:00Z", "from_account_id": from_id,
            "to_account_id": to_id, "amount": amount, "fee_amount": fee, "fee_currency": fee_currency, **fields}


# What the broker's form showed for some of the 65 rows' sales
# (transactions.broker_reporting), so 2024 and 2025 fill every Form 8949 box.
BROKER_FORMS = {
    "2024-02-15T14:00:00Z": "basis",     # 2024: Box A (its short-term part) and D
    "2024-08-01T10:00:00Z": "proceeds",  # 2024: Box E
    "2025-03-01T11:00:00Z": "basis",     # 2025: Box J
}

# What the 65 rows lack, so every year has every kind of transaction: cash
# moves, each deposit source and withdrawal purpose, transfers both ways.
EXTRA_ROWS = [
    _tx("Transfer", "2023-02-01", BANK, EXCHANGE_USD, "5000", fee_currency="USD"),
    _tx("Withdrawal", "2023-05-02", BANK, EXTERNAL, "2000", fee_currency="USD"),
    _tx("Withdrawal", "2023-10-20", WALLET, EXTERNAL, "0.005", "0.00001", purpose="Spent",
        gross_proceeds_usd="150.00"),
    _tx("Withdrawal", "2023-11-25", WALLET, EXTERNAL, "0.002", purpose="Lost"),
    # Sold on the lot's first anniversary: still short-term (held "more than
    # one year" only from the next day). One the 1099-B showed without basis
    # (Box B), one not on a 1099-B (Box C)
    {**_tx("Sell", "2024-02-15", EXCHANGE_BTC, EXCHANGE_USD, "0.01", "0.75", "USD",
           gross_proceeds_usd="500.00", broker_reporting="proceeds"), "timestamp": "2024-02-15T15:00:00Z"},
    {**_tx("Sell", "2024-02-15", EXCHANGE_BTC, EXCHANGE_USD, "0.01", "0.75", "USD",
           gross_proceeds_usd="500.00"), "timestamp": "2024-02-15T16:00:00Z"},
    _tx("Deposit", "2024-03-20", EXTERNAL, WALLET, "0.003", source="Interest", cost_basis_usd="195.00"),
    _tx("Transfer", "2024-05-01", BANK, EXCHANGE_USD, "10000", fee_currency="USD"),
    _tx("Withdrawal", "2024-06-01", BANK, EXTERNAL, "1500", fee_currency="USD"),
    _tx("Deposit", "2024-07-20", EXTERNAL, WALLET, "0.02", source="Gift", cost_basis_usd="900.00"),
    # The exchange's 2023 BTC to cold storage, so 2025's exchange sales are of
    # 2024 BTC, some held a year or less
    _tx("Transfer", "2024-12-30", EXCHANGE_BTC, WALLET, "1.00981", "0.0001", fee_usd="9.40"),
    # BTC bought 2024-01-15, sold within the year: the 1099-DA showed basis
    # (Box G); a sale the broker didn't report, e.g. abroad (Box I)
    _tx("Sell", "2025-01-12", EXCHANGE_BTC, EXCHANGE_USD, "0.1", "14.25", "USD",
        gross_proceeds_usd="9500.00", broker_reporting="basis"),
    _tx("Sell", "2025-01-13", EXCHANGE_BTC, EXCHANGE_USD, "0.05", "7.13", "USD",
        gross_proceeds_usd="4750.00", broker_reporting="none"),
    _tx("Deposit", "2025-03-20", EXTERNAL, WALLET, "0.002", source="Interest", cost_basis_usd="210.00"),
    _tx("Transfer", "2025-04-05", BANK, EXCHANGE_USD, "8000", fee_currency="USD"),
    _tx("Withdrawal", "2025-07-05", BANK, EXTERNAL, "2500", fee_currency="USD"),
    _tx("Deposit", "2025-08-25", EXTERNAL, WALLET, "0.01", source="Gift", cost_basis_usd="450.00"),
]

# 2026, in order. Exchange BTC starts the year with 0.8848 BTC: 0.0348
# (2024-10-01) and 0.35 (2024-12-01), then 0.15 (2025-02-15), 0.05, 0.12,
# 0.10 and 0.08 from later in 2025; FIFO sells the oldest first.
LEDGER_2026 = [
    _tx("Deposit", "2026-01-05", EXTERNAL, BANK, "20000", fee_currency="USD", source="N/A"),
    # 2024 BTC, long-term, not covered: Box K
    _tx("Sell", "2026-01-15", EXCHANGE_BTC, EXCHANGE_USD, "0.20", "45.60", "USD", gross_proceeds_usd="30400.00"),
    # The rest of the 2024 BTC, and the 1099-DA showed its basis: Box J
    _tx("Sell", "2026-02-02", EXCHANGE_BTC, EXCHANGE_USD, "0.1848", "41.03", "USD",
        gross_proceeds_usd="27350.40", broker_reporting="basis"),
    # Bought 2025-02-15, held a year or less, before 2026 (not covered): Box H
    _tx("Sell", "2026-02-09", EXCHANGE_BTC, EXCHANGE_USD, "0.15", "32.85", "USD", gross_proceeds_usd="21900.00"),
    _tx("Transfer", "2026-02-20", BANK, EXCHANGE_USD, "10000", fee_currency="USD"),
    # The last 0.35 to cold storage; the network fee is a disposal: Box I
    _tx("Transfer", "2026-03-16", EXCHANGE_BTC, WALLET, "0.35", "0.00004", fee_usd="5.60"),
    # Exchange BTC is empty: from here on it holds BTC bought there in 2026 (covered)
    _tx("Buy", "2026-03-20", EXCHANGE_USD, EXCHANGE_BTC, "0.25", "52.50", "USD", cost_basis_usd="35052.50"),
    _tx("Deposit", "2026-04-10", EXTERNAL, WALLET, "0.03", source="MyBTC", cost_basis_usd="4140.00"),
    # Covered, short-term: Box G
    _tx("Sell", "2026-05-04", EXCHANGE_BTC, EXCHANGE_USD, "0.10", "20.70", "USD", gross_proceeds_usd="13800.00"),
    _tx("Deposit", "2026-05-15", EXTERNAL, WALLET, "0.005", source="Gift", cost_basis_usd="300.00"),
    # Spent straight from the exchange account: no 1099-DA, short-term: Box I (its fee too)
    _tx("Withdrawal", "2026-06-01", EXCHANGE_BTC, EXTERNAL, "0.02", "0.00002", fee_usd="2.84",
        purpose="Spent", gross_proceeds_usd="2840.00"),
    _tx("Deposit", "2026-06-15", EXTERNAL, WALLET, "0.01", source="Income", cost_basis_usd="1425.00"),
    _tx("Deposit", "2026-06-20", EXTERNAL, WALLET, "0.001", source="Interest", cost_basis_usd="142.00"),
    # Self-custody spend of the wallet's oldest (2024) BTC: Box L (its fee too)
    _tx("Withdrawal", "2026-07-01", WALLET, EXTERNAL, "0.05", "0.00003", fee_usd="4.35",
        purpose="Spent", gross_proceeds_usd="7250.00"),
    _tx("Deposit", "2026-07-15", EXTERNAL, WALLET, "0.002", source="Reward", cost_basis_usd="290.00"),
    # Covered, short-term again: Box G
    _tx("Sell", "2026-08-03", EXCHANGE_BTC, EXCHANGE_USD, "0.05", "11.25", "USD", gross_proceeds_usd="7500.00"),
    # A gift, a donation and a loss are not sales, but their network fees are: Box L
    _tx("Withdrawal", "2026-09-01", WALLET, EXTERNAL, "0.01", "0.00002", fee_usd="2.96", fmv_usd="1480.00",
        purpose="Gift"),
    _tx("Withdrawal", "2026-09-05", WALLET, EXTERNAL, "0.004", "0.00001", fee_usd="1.48", fmv_usd="592.00",
        purpose="Donation"),
    _tx("Withdrawal", "2026-09-08", WALLET, EXTERNAL, "0.001", purpose="Lost"),
    # Back to the exchange after its last sale: its fee is another Box L
    _tx("Transfer", "2026-09-10", WALLET, EXCHANGE_BTC, "0.02", "0.00002", fee_usd="2.96"),
    _tx("Withdrawal", "2026-09-15", BANK, EXTERNAL, "3000", fee_currency="USD"),
]


class SeedError(Exception):
    pass


# The ledger
def ledger_rows() -> list[dict]:
    """Every transaction to create, oldest first, each as the API takes it."""
    with open(LEDGER_2023_2025) as f:
        base = [{k: v for k, v in row.items() if k not in ("id", "notes")} for row in json.load(f)]
    for row in base:
        if row["timestamp"] in BROKER_FORMS:
            row["broker_reporting"] = BROKER_FORMS[row["timestamp"]]
    rows = sorted(base + [dict(r) for r in EXTRA_ROWS], key=lambda r: r["timestamp"])
    rows += [dict(r) for r in LEDGER_2026]
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
    except UnicodeError:  # a..b, a label over 63 characters
        raise SeedError(f"{url} is not a valid address") from None
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
