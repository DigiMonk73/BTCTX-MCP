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

The ledger is testdata/reference_ledger.json (2023-2026), BitcoinTX's one
reference test ledger: every year has every kind of transaction (each
deposit source and withdrawal purpose, transfers both ways, cash moves, buys
and sells), every report has entries in each part, every Form 8949 box of
2024 (A-F), 2025 and 2026 (G-L) included, in any tax timezone, with rebates
and dates originally acquired; and from 2.0 multiple wallets, exchanges or
accounts: its `accounts` list, which the account API makes first (the ids
must come out as listed, so on a fresh install), and the rows that use them
("since": "2.0"). backend/tests/test_seed_ledger.py checks it and its
figures (testdata/reference_figures.json). Every USD value a price lookup
would fill is given (network fees, gift and donation values), so it loads
with the price source Off and contacts nothing but the server. Settings are
left as they are. A test tool: it lives in scripts/, which no build ships.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
import ssl
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "testdata" / "reference_ledger.json"
MAC_APP_PORT = 8765  # desktop/: the owner's real ledger
PASSWORD_ENV = "BTCTX_PASSWORD"
# A row's notes, never sent to the server
NOTES = ("why", "since")
# The account API's kinds, by the ledger's (an exchange is added once, as its two accounts)
ADDED_AS = ("bank", "wallet", "exchange")


class SeedError(Exception):
    pass


# The ledger
def ledger_rows() -> list[dict]:
    """Every transaction to create, oldest first, each as the API takes it
    (testdata/reference_ledger.json without its notes: "why", and "since",
    which marks a row 2.0 added)."""
    with open(LEDGER) as f:
        rows = json.load(f)["transactions"]
    return [{k: v for k, v in row.items() if k not in NOTES} for row in rows]


def ledger_accounts() -> list[dict]:
    """The accounts the ledger adds to the fixed ones (its `accounts` list,
    2.0 spec 5.15), as the account API adds them: a bank or a wallet by its
    name, an exchange by its own (its accounts "<name> USD" and "<name> BTC"),
    each with the ids it must get and, for an exchange, its 1099-DA switch."""
    with open(LEDGER) as f:
        listed = json.load(f).get("accounts", [])
    added, exchanges = [], {}
    for account in listed:
        if account["kind"] not in ADDED_AS:
            raise SeedError(f"account {account['id']} is a {account['kind']!r} account, which the API doesn't add")
        if account["kind"] != "exchange":
            added.append({"kind": account["kind"], "name": account["name"], "ids": [account["id"]]})
            continue
        pair = exchanges.setdefault(account["exchange_id"], {})
        pair[account["currency"]] = account
    for exchange_id, pair in exchanges.items():
        usd, btc = pair.get("USD"), pair.get("BTC")
        name = usd["name"].removesuffix(" USD") if usd else None
        if not (usd and btc and btc["name"] == f"{name} BTC"):
            raise SeedError(f"exchange {exchange_id} needs a '<name> USD' and a '<name> BTC' account")
        added.append({"kind": "exchange", "name": name, "ids": [usd["id"], btc["id"]],
                      "sends_1099da": usd.get("sends_1099da", True)})
    return sorted(added, key=lambda a: a["ids"][0])


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


def seed(c: httpx.Client, rows: list[dict] | None = None, accounts: list[dict] | None = None) -> int:
    """Create every row on a logged-in client, after the accounts they use:
    the reference ledger's rows and accounts when no rows are given; given
    rows (a 1.x release's, make_reference_1x_db.py) need only the accounts
    given, and none calls the account API, which a 1.x release lacks.
    Refuses a ledger that isn't empty. Returns how many rows were created."""
    r = c.get("/api/transactions")
    if r.status_code != 200:
        raise SeedError(f"couldn't read the ledger: {r.status_code} {r.text[:300]}")
    if r.json():
        raise SeedError(f"the ledger already has {len(r.json())} transactions: seed only an empty test install")
    if rows is None:
        rows, accounts = ledger_rows(), ledger_accounts() if accounts is None else accounts
    for account in accounts or []:
        make_account(c, account)
    for n, row in enumerate(rows, start=1):
        r = send_confirmed(c, "POST", "/api/transactions", row)
        if r.status_code != 200:
            raise SeedError(f"row {n} ({row['timestamp']} {row['type']}) refused: {r.status_code} {r.text[:300]}. "
                            f"The {n - 1} rows before it are in the ledger: delete them all before running again.")
    return len(rows)


def make_account(c: httpx.Client, account: dict) -> None:
    """One of ledger_accounts() through the account API, with the ids it
    lists: one a Delete All left (same name and kind) is used again, and
    an id that comes out otherwise stops the seed, since every row names
    accounts by id. Then an exchange's 1099-DA switch, set as the ledger
    has it, so one left changed by hand is put back."""
    r = c.get("/api/accounts/")
    if r.status_code != 200:
        raise SeedError(f"couldn't read the accounts: {r.status_code} {r.text[:300]}")
    names = ([f"{account['name']} {currency}" for currency in ("USD", "BTC")] if account["kind"] == "exchange"
             else [account["name"]])
    found = [a for name in names for a in r.json() if a["name"].casefold() == name.casefold()]
    if not found:
        r = c.post("/api/accounts/", json={"kind": account["kind"], "name": account["name"]})
        if r.status_code != 201:
            raise SeedError(f"adding {account['name']} failed: {r.status_code} {r.text[:300]}")
        found = r.json()
    if [(a["kind"], a["id"]) for a in found] != [(account["kind"], i) for i in account["ids"]]:
        raise SeedError(f"{account['name']} is account {', '.join(str(a['id']) for a in found)} here, a "
                        f"{found[0]['kind']}, not the ledger's {account['kind']} {', '.join(map(str, account['ids']))}: "
                        "seed only a fresh test install")
    if account["kind"] == "exchange":
        r = send_confirmed(c, "PUT", f"/api/accounts/{account['ids'][0]}", {"sends_1099da": account["sends_1099da"]})
        if r.status_code != 200:
            raise SeedError(f"setting {account['name']}'s 1099-DA switch failed: {r.status_code} {r.text[:300]}")


def send_confirmed(c: httpx.Client, method: str, path: str, body: dict | None = None) -> httpx.Response:
    """A write through 2.0's past-year warning (docs/temp/2.0-accounts.md
    5.8): nearly every row is dated in an earlier tax year, and no switch
    turns the warning off on a running server, so a 409 that gives a
    fingerprint (`confirm`) is sent again, once, with ?confirm=<it>. The
    answer either way: a second 409 (the ledger changed meanwhile) is the
    caller's to report."""
    r = c.request(method, path, json=body)
    fingerprint = _fingerprint_asked(r)
    return r if fingerprint is None else c.request(method, path, json=body, params={"confirm": fingerprint})


def _fingerprint_asked(r: httpx.Response) -> str | None:
    """The `confirm` of the warning's 409; None for any other answer (Delete
    All's 409 asks for a typed DELETE instead)."""
    if r.status_code != 409:
        return None
    try:
        body = r.json()
    except ValueError:  # not JSON
        return None
    confirm = body.get("confirm") if isinstance(body, dict) else None
    return confirm if isinstance(confirm, str) else None


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
