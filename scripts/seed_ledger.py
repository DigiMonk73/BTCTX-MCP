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
    python scripts/seed_ledger.py --store-prices <a test database>   # before its server starts
    python scripts/seed_ledger.py --url ... --with-prices             # then every row

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
must come out as listed, so on a fresh install), the rows that use them
("since": "2.0"), and then each account named and hidden as the list has
it (one made under an older name is renamed, as an owner renames or hides
an account in use). A row may name the coins it acquired (`key`), and a
later row choose them by that name (`chosen_coins`, #711): the seed sends
each as the id the server gave the row. backend/tests/test_seed_ledger.py
checks it and its figures (testdata/reference_figures.json). Every USD
value a price lookup would fill is given (network fees, gift and donation
values), so it loads with the price source Off and contacts nothing but the
server, but in the rows marked "priced" (#715): those leave a value out for
the price to fill, from the stored-price fixture (testdata/reference_prices.json),
and are sent only with --with-prices, to a server whose database has those
prices stored. --store-prices stores them in a test database's file, before
its server starts (an empty database, or one this seed loaded): never an
installed app's data, never a database holding someone's transactions, and
never a request. Without --with-prices the seed says how many rows it left
out, so its figures aren't taken for reference_figures.json's. Settings are
left as they are. A test tool: it lives in scripts/, which no build ships.
"""

from __future__ import annotations

import argparse
import contextlib
import ipaddress
import json
import os
import socket
import sqlite3
import ssl
import sys
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "testdata" / "reference_ledger.json"
PRICES = ROOT / "testdata" / "reference_prices.json"
MAC_APP_PORT = 8765  # desktop/: the owner's real ledger
# The installed apps' data folders, in ~/Library/Application Support: their ledgers are real
APP_DATA = ("BitcoinTX", "BitcoinTX Preview")
PASSWORD_ENV = "BTCTX_PASSWORD"
# A row's notes, never sent to the server ("priced": valued from a stored price, #715)
NOTES = ("why", "since", "added", "priced")
# The account API's kinds, by the ledger's (an exchange is added once, as its two accounts)
ADDED_AS = ("bank", "wallet", "exchange")
# 1.x's exchange, which every install has (scripts/independent_figures.py's exchange 1)
FIRST_EXCHANGE = {"kind": "exchange", "name": "Exchange", "ids": [3, 4], "sends_1099da": True, "exchange_id": 1}


class SeedError(Exception):
    pass


# The ledger
def ledger_rows(with_prices: bool = False) -> list[dict]:
    """Every transaction to create, oldest first, each as the API takes it
    but for its keys, which create_rows turns into ids
    (testdata/reference_ledger.json without its notes: "why", "since",
    which marks a row 2.0 added, "added", the change that added it, and
    "priced"). The rows marked "priced" only with_prices: they take a value
    from the stored-price fixture, which a server has only once
    store_prices put it in its database (#715)."""
    with open(LEDGER) as f:
        rows = json.load(f)["transactions"]
    return [{k: v for k, v in row.items() if k not in NOTES} for row in rows if with_prices or not row.get("priced")]


def ledger_accounts() -> list[dict]:
    """The accounts the ledger adds to the fixed ones (its `accounts` list,
    2.0 spec 5.15), as the account API adds them: a bank or a wallet by its
    name, an exchange by its own (its accounts "<name> USD" and "<name> BTC"),
    each with the ids it must get, whether it ends hidden, the name it's
    made under when it's renamed after the rows (`renamed_from`) and, for an
    exchange, its 1099-DA switch. A ledger with such a list also sets 1.x's
    first exchange's switch (on, unless the list says otherwise), so a
    reseed puts back one changed by hand; one without (1.x's) adds nothing."""
    with open(LEDGER) as f:
        listed = json.load(f).get("accounts", [])
    added, exchanges = [], {}
    for account in listed:
        if account["kind"] not in ADDED_AS:
            raise SeedError(f"account {account['id']} is a {account['kind']!r} account, which the API doesn't add")
        if account["kind"] != "exchange":
            added.append({"kind": account["kind"], "name": account["name"], "ids": [account["id"]],
                          "hidden": account.get("hidden", False),
                          "made_as": account.get("renamed_from", account["name"])})
            continue
        pair = exchanges.setdefault(account["exchange_id"], {})
        pair[account["currency"]] = account
    added += [_exchange(exchange_id, pair) for exchange_id, pair in exchanges.items()]
    if listed and FIRST_EXCHANGE["exchange_id"] not in exchanges:
        added.append({key: value for key, value in FIRST_EXCHANGE.items() if key != "exchange_id"})
    return sorted(added, key=lambda a: a["ids"][0])


def _exchange(exchange_id: int, pair: dict[str, dict]) -> dict:
    """An exchange of the accounts list, from its two accounts, which must
    be named after it (now and, renamed, before) and agree on its switch
    and on being hidden."""
    usd, btc = pair.get("USD"), pair.get("BTC")
    name = usd["name"].removesuffix(" USD") if usd else None
    if not (usd and btc and btc["name"] == f"{name} BTC"):
        raise SeedError(f"exchange {exchange_id} needs a '<name> USD' and a '<name> BTC' account")
    made_as = usd.get("renamed_from", usd["name"]).removesuffix(" USD")
    if btc.get("renamed_from", btc["name"]) != f"{made_as} BTC":
        raise SeedError(f"exchange {exchange_id}'s two accounts disagree on the name it had (renamed_from)")
    if usd.get("sends_1099da", True) != btc.get("sends_1099da", True):
        raise SeedError(f"exchange {exchange_id}'s two accounts disagree on its 1099-DA switch")
    if usd.get("hidden", False) != btc.get("hidden", False):
        raise SeedError(f"exchange {exchange_id}'s two accounts disagree on whether it's hidden")
    return {"kind": "exchange", "name": name, "ids": [usd["id"], btc["id"]], "sends_1099da": usd.get("sends_1099da", True),
            "hidden": usd.get("hidden", False), "made_as": made_as}


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


def seed(c: httpx.Client, rows: list[dict] | None = None, accounts: list[dict] | None = None,
         with_prices: bool = False) -> int:
    """Create every row on a logged-in client, after the accounts they use,
    then name and hide those accounts as the ledger has them, as an owner
    renames or hides an account in use: the reference ledger's rows and
    accounts when no rows are given (the "priced" rows only with_prices);
    given rows (a 1.x release's,
    make_reference_1x_db.py) need only the accounts given, and none calls
    the account API, which a 1.x release lacks. Refuses a ledger that isn't
    empty. Returns how many rows were created."""
    r = c.get("/api/transactions")
    if r.status_code != 200:
        raise SeedError(f"couldn't read the ledger: {r.status_code} {r.text[:300]}")
    if r.json():
        raise SeedError(f"the ledger already has {len(r.json())} transactions: seed only an empty test install")
    if rows is None:
        rows, accounts = ledger_rows(with_prices), ledger_accounts() if accounts is None else accounts
    check_keys(rows)
    for account in accounts or []:
        make_account(c, account)
    create_rows(rows, lambda n, row: _post_row(c, n, row))
    for account in accounts or []:
        finish_account(c, account)
    return len(rows)


def check_keys(rows: list[dict]) -> None:
    """Each key on one row, before every row whose choice names it, so the
    seed can follow them: checked before anything is sent."""
    defined: dict[str, int] = {}
    for n, row in enumerate(rows, start=1):
        for line in row.get("chosen_coins") or []:
            if "key" not in line:
                raise SeedError(f"row {n} chooses coins without a key: each line names its coins by the key of "
                                "the row that acquired them")
            if line["key"] not in defined:
                raise SeedError(f"row {n} chooses coins by the key {line['key']!r}, which no row before it has: "
                                "a key is defined once, before the rows that choose by it")
        key = row.get("key")
        if key is None:
            continue
        if row["type"] not in ("Buy", "Deposit"):
            raise SeedError(f"row {n} is a {row['type']} with a key: only a Buy or a Deposit acquires coins a "
                            "choice can name")
        if key in defined:
            raise SeedError(f"row {n}'s key {key!r} is row {defined[key]}'s too: a key names one Buy or Deposit")
        defined[key] = n


def make_account(c: httpx.Client, account: dict) -> None:
    """One of ledger_accounts() through the account API, with the ids it
    lists: one a Delete All left (same name and kind) is used again, and
    an id that comes out otherwise stops the seed, since every row names
    accounts by id. Then an exchange's 1099-DA switch, set as the ledger
    has it, so one left changed by hand is put back."""
    r = c.get("/api/accounts/")
    if r.status_code != 200:
        raise SeedError(f"couldn't read the accounts: {r.status_code} {r.text[:300]}")
    found = []
    for name in dict.fromkeys((account["name"], account.get("made_as", account["name"]))):  # renamed: either name
        names = [f"{name} {currency}" for currency in ("USD", "BTC")] if account["kind"] == "exchange" else [name]
        found = found or [a for each in names for a in r.json() if a["name"].casefold() == each.casefold()]
    if not found:
        r = c.post("/api/accounts/", json={"kind": account["kind"], "name": account.get("made_as", account["name"])})
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


def create_rows(rows: list[dict], create: Callable[[int, dict], int]) -> None:
    """Each row created in order by `create` (its number and the row as the
    API takes it, returning the id the server gave it). A row's `key` names
    the coins it acquired, and a later row's chosen coins name them by it
    (#711, docs/temp/2.0-coin-choice.md 8.3), never by position: the file
    is kept in time order, so a row put in later would move every number
    after it. The key isn't sent; a choice is sent with the id its row got."""
    ids: dict[str, int] = {}
    for n, row in enumerate(rows, start=1):
        sent = {field: value for field, value in row.items() if field != "key"}
        if row.get("chosen_coins"):
            sent["chosen_coins"] = [{"acquired_txn_id": ids[line["key"]], "btc": line["btc"]}
                                    for line in row["chosen_coins"]]
        made = create(n, sent)
        if row.get("key") is not None:
            ids[row["key"]] = made


def _post_row(c: httpx.Client, n: int, row: dict) -> int:
    r = send_confirmed(c, "POST", "/api/transactions", row)
    if r.status_code != 200:
        raise SeedError(f"row {n} ({row['timestamp']} {row['type']}) refused: {r.status_code} {r.text[:300]}. "
                        f"The {n - 1} rows before it are in the ledger: delete them all before running again.")
    return r.json()["id"]


def finish_account(c: httpx.Client, account: dict) -> None:
    """One of ledger_accounts() named and hidden (or shown) as the ledger
    has it, once the rows are in: one made under another name is renamed
    (an exchange's: the exchange and both its accounts), and one hidden or
    shown by hand is put back. A name or hidden alone moves no figure, so
    it never meets the past-year warning."""
    r = c.put(f"/api/accounts/{account['ids'][0]}", json={"name": account["name"], "hidden": account.get("hidden", False)})
    if r.status_code != 200:
        raise SeedError(f"naming or hiding {account['name']} failed: {r.status_code} {r.text[:300]}")


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


def loaded(url: str, created: int, with_prices: bool) -> str:
    """What the seed says it did: without the "priced" rows, how many it
    left out, so a ledger seeded without them isn't compared with
    reference_figures.json as if it were whole."""
    said = f"✓ {created} transactions loaded into {url} (2023-2026)"
    if with_prices:
        return said
    left_out = len(ledger_rows(with_prices=True)) - len(ledger_rows())
    return (f"{said}; {left_out} rows valued from a stored price left out, so its figures aren't "
            "reference_figures.json's. To load them: --store-prices <its database> before its server starts, "
            "then the seed with --with-prices.")


# The stored-price fixture (#715)
def store_prices(path: Path, later: bool = False) -> int:
    """The fixture's prices written into a BitcoinTX database's price
    tables, as the app stores the prices it finds: the days and hours the
    "priced" rows are priced from, and later=True also the hours found
    after them (an hour's price arriving once a value was priced at its
    day: Ledger Review's day_priced_values). A price already stored must be
    the same, since a stored price never changes. Plain SQL on the file:
    nothing of the app runs, and nothing is asked of the network. Returns
    how many prices it added."""
    fixture = json.loads(PRICES.read_text())
    hours = fixture["hours"] + (fixture["hours_found_later"] if later else [])
    wanted = [("btc_price_daily", "day", d["day"], d) for d in fixture["days"]] + [
        ("btc_price_hourly", "hour", _unix_hour(h["hour"]), h) for h in hours]
    added = 0
    with contextlib.closing(sqlite3.connect(path)) as con, con:  # committed, or rolled back, then closed
        for table, key, when, price in wanted:
            stored = con.execute(f"SELECT usd, source FROM {table} WHERE {key} = ?", (when,)).fetchone()
            if stored is None:
                con.execute(f"INSERT INTO {table} ({key}, usd, source) VALUES (?, ?, ?)",
                            (when, price["usd"], price["source"]))
                added += 1
            elif (Decimal(str(stored[0])), stored[1]) != (Decimal(price["usd"]), price["source"]):
                raise SeedError(f"{path} already has another price for {price.get('day') or price.get('hour')}: "
                                "a stored price never changes. Use a fresh test database.")
    return added


def _unix_hour(text: str) -> int:
    """An hour as the app keys btc_price_hourly: its UTC start, in Unix seconds."""
    return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())


def refuse_app_data(path: Path) -> Path:
    """The database's path as it is on disk (links resolved), refused in an
    installed app's data folder however it's written: another case, as
    macOS's disks ignore case, or through a link. Checked before the file
    is opened, so a mistyped one never reaches it either."""
    real = path.expanduser().resolve()
    support = Path.home() / "Library" / "Application Support"
    for name in APP_DATA:
        folder = support / name
        folders = {str(folder).casefold(), str(folder.resolve()).casefold()}
        if any(str(p).casefold() in folders for p in (real, *real.parents)):
            raise SeedError(f"{path} is in the installed app's data ({folder}): its ledger is real data. "
                            "Store prices only in a test database.")
    return real


def check_test_database(path: Path) -> bool:
    """Whether `path` is a throwaway BitcoinTX database the fixture may go
    into: one with no transactions (False) or the seed's own, every row of
    the reference ledger and nothing else (True). Anything else is refused,
    never opened for writing: a missing file (never made here), a file that
    isn't a BitcoinTX database, a ledger with transactions the seed didn't
    make."""
    if not path.is_file():
        raise SeedError(f"{path}: no such database. Make it first (backend.cli set-password), then store prices.")
    try:
        with contextlib.closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as con:
            tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if not {"transactions", "btc_price_daily", "btc_price_hourly"} <= tables:
                raise SeedError(f"{path} isn't a BitcoinTX database.")
            stored = Counter((kind, datetime.fromisoformat(moment[:19])) for kind, moment
                             in con.execute("SELECT type, timestamp FROM transactions"))
    except sqlite3.DatabaseError:
        raise SeedError(f"{path} isn't a BitcoinTX database.") from None
    if not stored:
        return False
    if stored in (_moments(ledger_rows()), _moments(ledger_rows(with_prices=True))):
        return True
    raise SeedError(f"{path} has transactions the seed didn't make: it may be someone's ledger. "
                    "Store prices only in a test database.")


def _moments(rows: list[dict]) -> Counter:
    return Counter((row["type"], datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
                    .astimezone(timezone.utc).replace(tzinfo=None)) for row in rows)


def read_password(args: argparse.Namespace) -> str:
    password = sys.stdin.readline().rstrip("\r\n") if args.password_stdin else os.environ.get(PASSWORD_ENV, "")
    if not password:
        raise SeedError(f"No password: pipe it to --password-stdin or set {PASSWORD_ENV}.")
    return password


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="the server, e.g. https://host:port")
    ap.add_argument("--user")
    ap.add_argument("--password-stdin", action="store_true", help=f"read the password from stdin (default: ${PASSWORD_ENV})")
    ap.add_argument("--setup-code", help="claim an install still on the default login first, as --user")
    ap.add_argument("--ca", help="a root certificate to trust (StartOS: your server's root CA)")
    ap.add_argument("--with-prices", action="store_true",
                    help="also the rows valued from a stored price (the server's database has them: --store-prices)")
    ap.add_argument("--store-prices", metavar="DATABASE", type=Path,
                    help="only store the fixture's prices in a test database's file, before its server starts")
    args = ap.parse_args(argv)
    if args.store_prices and args.url:
        ap.error("--store-prices runs alone, before the server starts: then seed with --url and --with-prices")
    if args.store_prices:
        return _store_prices_command(args.store_prices)
    if not (args.url and args.user):
        ap.error("--url and --user are needed to seed (or --store-prices DATABASE alone)")
    url = args.url.rstrip("/")
    try:
        refuse_mac_app(url)
        password = read_password(args)
        with connect(url, args.ca) as c:
            log_in(c, args.user, password, args.setup_code)
            created = seed(c, with_prices=args.with_prices)
            c.post("/api/logout")
    except (SeedError, httpx.HTTPError) as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    print(loaded(url, created, args.with_prices))
    return 0


def _store_prices_command(path: Path) -> int:
    try:
        real = refuse_app_data(path)
        added = store_prices(real, later=check_test_database(real))
    except SeedError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    except sqlite3.Error as e:  # SQLite's own words: "database is locked" while its server runs
        print(f"✗ {path}: {e}. Stop its server first; nothing was stored.", file=sys.stderr)
        return 1
    print(f"✓ {added} prices stored in {real}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
