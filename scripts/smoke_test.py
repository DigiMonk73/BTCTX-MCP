#!/usr/bin/env python3
"""
End-to-end smoke test for BitcoinTX.

Starts the REAL server (uvicorn, as Docker and the macOS app do) on a
throwaway database and drives it over HTTP like a user: claim the account
with the first-run setup code, login, record a year of activity, import via
the MCP entry API, generate every report, export, recalculate, log out.
Exits non-zero on the first failure.

Usage:
    python scripts/smoke_test.py                 # own server, temp DB, stubbed prices
    python scripts/smoke_test.py --url http://127.0.0.1:8080 --user admin --password password
                                                 # an already-running instance (e.g. Docker)
    python scripts/smoke_test.py --url http://127.0.0.1:8080 --user me --password <12+ chars> \
        --setup-code XXXX-XXXX-XXXX              # claim a fresh instance first (the code is
                                                 # in docker logs and /data/setup-code.txt)

The own-server mode stubs BTC prices so it runs offline. Against --url the
server uses live prices, so price-dependent steps may be skipped if the
price APIs are unreachable. Never point --url at your real data: it
creates transactions.
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
PASSED: list[str] = []
SKIPPED: list[str] = []
# The account the own-server run claims (a new password needs 12+ characters)
SMOKE_USER, SMOKE_PASSWORD = "smoke-user", "smoke-password-123"
# What the own server's price sources give (frontend/e2e/fixtures.ts expects them)
CURRENT_PRICE, PAST_PRICE, BLOCK_HEIGHT = 60000, 50000, 900000


class SmokeFailure(Exception):
    pass


def check(name: str, condition: bool, detail: str = "") -> None:
    if not condition:
        raise SmokeFailure(f"{name}{': ' + detail if detail else ''}")
    PASSED.append(name)
    print(f"  ✓ {name}")


def skip(name: str, why: str) -> None:
    SKIPPED.append(name)
    print(f"  – {name} (skipped: {why})")


# Own server
def serve(port: int, db_path: str) -> None:
    """Child-process entry: run the app with deterministic offline prices.

    Also used by the Playwright suite (frontend/e2e) to serve the app. With
    BTCTX_SMOKE_OUTSIDE_LOG set, the prices come from a fake internet
    instead of stubs (fake_internet), and its requests go to that file.
    """
    os.environ["DATABASE_FILE"] = db_path
    sys.path.insert(0, str(ROOT))

    from backend.services import outbound

    outside_log = os.environ.get("BTCTX_SMOKE_OUTSIDE_LOG")
    if outside_log:
        fake_internet(outside_log)
    else:
        stub_prices()

    # The owner already chose public price sites (a fresh install asks first),
    # unless a test wants to see that question: BTCTX_SMOKE_PRICE_SOURCE=unset;
    # or "unconfirmed": public, stored by an older release with no record of
    # the choice, so the app asks once to confirm it (#145, 2.9).
    chosen = os.environ.get("BTCTX_SMOKE_PRICE_SOURCE", "public")
    if chosen != "unset":
        from backend.database import SessionLocal, init_db

        init_db()
        with SessionLocal() as db:
            if chosen.startswith("unconfirmed"):  # "unconfirmed", "-off" or "-mempool"
                stored = {"unconfirmed": "public"}.get(chosen, chosen.removeprefix("unconfirmed-"))
                outbound._set(db, outbound.SOURCE_KEY, stored)
                if stored == "mempool":
                    outbound._set(db, outbound.MEMPOOL_KEY, "http://umbrel.local:3006")
                db.commit()
            else:
                outbound.save(db, "public", None, False, None)

    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=port, log_level="warning")


def stub_prices() -> None:
    """Replace the price lookups with fixed prices, but only from a source
    the settings allow (as for real)."""
    import backend.services.bitcoin as bitcoin
    import backend.services.hourly_prices as hourly_prices
    import backend.services.price_history as price_history
    from backend.services import outbound, price_status

    def allowed() -> bool:
        return outbound.current().public_allowed or outbound.current().own_node is not None

    async def find_prices(day, full):
        return ({day: (Decimal(f"{PAST_PRICE}.00"), "stub")} if allowed() else {}), False

    async def current():
        if not allowed():
            raise outbound.refuse_public()
        source = "mempool" if outbound.current().own_node else "kraken"
        price_status.answered(source)  # as the real lookup records it for the status line
        return {"USD": float(CURRENT_PRICE), "source": source, "at": bitcoin.now_iso()}

    async def block_height():
        if not allowed():
            raise outbound.refuse_public()
        return {"height": BLOCK_HEIGHT}

    async def no_hours(hour, files_end, stored):
        return {}

    price_history.find_prices = find_prices
    bitcoin.get_current_price = current
    bitcoin.get_block_height = block_height
    # No hourly prices and no download of the year files: valuations at the
    # hour take the stubbed day's price.
    hourly_prices.find_hours = no_hours
    hourly_prices.start_download = lambda: False


# A Tor whose exits Bitstamp refuses (#241), for the fake internet: a proxy at this host
TOR_BITSTAMP_REFUSES = "refused-by-bitstamp.test"


def fake_internet(log_path: str) -> None:
    """
    Answer the app's requests to outside services from a fake internet, so
    its own choice of source, fallback and proxy runs (the e2e sidebar
    matrix). Every price site and mempool server gives the live price and
    block height of the stubs, and each past day its own price
    (fake_past_price), except that a host under .invalid (RFC 2606: it never
    resolves) doesn't answer: a mempool server that's down, or a proxy
    that's stopped; and through a proxy at TOR_BITSTAMP_REFUSES, Bitstamp
    answers its block page, as it does Tor's exits (#241). A request the
    app's code never makes gets a 404, so it can't produce a price. Each
    request goes to `log_path` as a JSON line: its URL and the proxy it was
    sent through.
    """
    class FakeInternetClient(httpx.AsyncClient):
        # transport: a direct client's own connection (#474), replaced by the fake one
        def __init__(self, *, proxy: str | None = None, transport=None, **kwargs):
            def answer(request: httpx.Request) -> httpx.Response:
                with open(log_path, "a") as log:
                    log.write(json.dumps({"url": str(request.url), "proxy": proxy}) + "\n")
                if any(host.endswith(".invalid") for host in (request.url.host, httpx.URL(proxy or "").host)):
                    raise httpx.ConnectError("no answer (fake internet)", request=request)
                if request.url.host == "www.bitstamp.net" and httpx.URL(proxy or "").host == TOR_BITSTAMP_REFUSES:
                    return httpx.Response(403, text="Request unsuccessful. Incapsula incident ID: 0-0")
                return _fake_answer(request)

            super().__init__(transport=httpx.MockTransport(answer), **kwargs)

    # services/outbound.py builds every client for outside services (a
    # backend test checks), and nothing else in this process makes one.
    httpx.AsyncClient = FakeInternetClient


def fake_past_price(midnight: int) -> int:
    """
    The fake internet's price for the UTC day starting at `midnight` (Unix
    seconds): $50,000 plus the day's number mod 100, so a lookup of the day
    before or after shows (frontend/e2e/fixtures.ts, fakePastPrice).
    """
    return PAST_PRICE + (midnight // 86400) % 100


def _fake_answer(request: httpx.Request) -> httpx.Response:
    """What a price site or a mempool server would say (fake_internet)."""
    import backend.services.bitcoin as bitcoin
    import backend.services.price_history as price_history

    url, path, params = str(request.url), request.url.path, request.url.params
    if path.endswith("/api/v1/prices") and not params:  # a mempool server's live price
        return httpx.Response(200, json={"time": int(time.time()), "USD": CURRENT_PRICE})
    if path.endswith(price_history.MEMPOOL_HISTORY_PATH) and dict(params) == {"currency": "USD"}:
        return httpx.Response(200, json={"prices": _mempool_rows(price_history.FIRST_PRICE_DAY)})
    if (path.endswith("/api/blocks/tip/height") and not params) or url == bitcoin.BLOCKCHAIN_INFO_HEIGHT_URL:
        return httpx.Response(200, text=str(BLOCK_HEIGHT))
    tickers = {bitcoin.KRAKEN_TICKER_URL: {"error": [], "result": {"XXBTZUSD": {"c": [str(CURRENT_PRICE), "1"]}}},
               bitcoin.BITSTAMP_TICKER_URL: {"last": str(CURRENT_PRICE)}}
    if url in tickers:
        return httpx.Response(200, json=tickers[url])
    if url.startswith(price_history.BITSTAMP_OHLC_URL) and _is_bitstamp_block(params):
        return httpx.Response(200, json={"data": {"ohlc": _bitstamp_rows(params)}})
    return httpx.Response(404)


def _mempool_rows(first: date) -> list[dict]:
    """A mempool server's hourly record: every day's 00:00 UTC, with the
    23:00 and 01:00 rows around it (the same price, as mempool's 2% check
    wants)."""
    hour, day = 3600, 86400
    today = int(time.time()) // day * day
    midnights = range(calendar.timegm(first.timetuple()), today + 1, day)
    return [{"time": t + offset, "USD": fake_past_price(t)} for t in midnights for offset in (-hour, 0, hour)]


def _is_bitstamp_block(params: httpx.QueryParams) -> bool:
    """Whether it's one of the fixed blocks price_history asks Bitstamp for:
    the latest days, or a block of days from a block start."""
    import backend.services.price_history as price_history

    day, size = price_history.DAY, price_history.BITSTAMP_BLOCK
    if set(params) - {"step", "limit", "start"} or params.get("step") != str(day) or params.get("limit") != str(size):
        return False
    first = calendar.timegm(price_history.FIRST_PRICE_DAY.timetuple())
    return "start" not in params or (int(params["start"]) - first) % (size * day) == 0


def _bitstamp_rows(params: httpx.QueryParams) -> list[dict]:
    """Bitstamp's daily candles: `limit` days from `start`, or the latest ones."""
    day = 86400
    today = int(time.time()) // day * day
    limit = int(params["limit"])
    start = int(params["start"]) if "start" in params else today - (limit - 1) * day
    end = min(start + (limit - 1) * day, today)
    return [{"timestamp": str(t), "open": str(fake_past_price(t))} for t in range(start, end + 1, day)]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server() -> tuple[subprocess.Popen, str, str]:
    workdir = tempfile.mkdtemp(prefix="btctx-smoke-")
    db_path = os.path.join(workdir, "smoke.db")
    port = free_port()
    log = open(os.path.join(workdir, "server.log"), "w")
    proc = subprocess.Popen(
        [sys.executable, __file__, "--serve", str(port), db_path],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        if proc.poll() is not None:
            raise SmokeFailure(f"server exited early with code {proc.returncode}")
        try:
            httpx.get(url + "/api/protected", timeout=1)
            return proc, url, workdir
        except httpx.HTTPError:
            time.sleep(0.5)
    proc.terminate()
    raise SmokeFailure("server did not start within 30s")


# Scenario
def claim(c: httpx.Client, user: str, password: str, code: str) -> None:
    """First run: set the login of the default account, with the setup code."""
    print("\nFirst run")
    status = c.get("/api/users/setup-status").json()
    check("fresh instance has the default login", status["is_default"], str(status))
    check("claiming it needs the setup code", status["setup_code_required"], str(status))
    body = {"username": user, "password": password}
    r = c.post("/api/users/reset-account", json=body)
    check("claim without the code refused", r.status_code == 403, r.text)
    r = c.post("/api/users/reset-account", json={**body, "setup_code": code})
    check("claim with the code", r.status_code == 200, r.text)
    check("default login no more", not c.get("/api/users/setup-status").json()["is_default"])


def run(url: str, user: str, password: str, own_server: bool, setup_code: str | None = None) -> None:
    c = httpx.Client(base_url=url, timeout=120)
    if setup_code:
        claim(c, user, password, setup_code)
    check_serving(c)
    check_auth(c, user, password, setup_code)
    sell = check_ledger(c, own_server)
    check_entry_import(c)
    check_recalculate(c, sell)
    check_reports(c)
    print("\nLogout")
    c.post("/api/logout")
    check("logged out", c.get("/api/transactions").status_code == 401)


def check_serving(c: httpx.Client) -> None:
    print("\nServing")
    r = c.get("/")
    if "text/html" in r.headers.get("content-type", ""):
        check("frontend index served", r.status_code == 200)
        r = c.get("/transactions")
        check("SPA route falls back to index.html", r.status_code == 200 and "<html" in r.text.lower())
    else:
        skip("frontend served", "frontend/dist not built")
    r = c.get("/api/does-not-exist")
    check("unknown API route is a JSON 404", r.status_code == 404 and r.json().get("detail"))


def check_auth(c: httpx.Client, user: str, password: str, setup_code: str | None) -> None:
    print("\nAuth")
    check("protected API rejects anonymous", c.get("/api/transactions").status_code == 401)
    check("wrong password rejected",
          c.post("/api/login", json={"username": user, "password": password + "x"}).status_code == 401)
    r = c.post("/api/login", json={"username": user, "password": password})
    check("login", r.status_code == 200, r.text)
    if setup_code:
        # A fresh install asks nothing until a price source is chosen; this
        # one was just claimed by the smoke test, so choose the public sites.
        r = c.put("/api/settings/network", json={"price_source": "public"})
        check("price source chosen (public sites)", r.status_code == 200, r.text)


def create(c: httpx.Client, **data) -> dict:
    r = send_confirmed(c, "POST", "/api/transactions", data)
    if r.status_code != 200:
        raise SmokeFailure(f"create {data['type']} failed: {r.status_code} {r.text}")
    return r.json()


def send_confirmed(c: httpx.Client, method: str, path: str, body: dict | None = None) -> httpx.Response:
    """A write through 2.0's past-year warning (docs/temp/2.0-accounts.md
    5.8): this test's rows are dated in earlier tax years, and no switch
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


def check_ledger(c: httpx.Client, own_server: bool) -> dict:
    """A deposit, a buy, a move to cold storage and a long-term sale; the
    balances they leave. Returns the sale."""
    print("\nLedger")
    accounts = {a["id"]: a["name"] for a in c.get("/api/accounts/").json()}
    check("six core accounts exist", {1, 2, 3, 4, 5, 6} <= set(accounts), str(accounts))
    if c.get("/api/transactions").json():
        raise SmokeFailure("target already has transactions — use an empty instance")

    create(c, type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=99, to_account_id=1,
           amount="20000", fee_amount="0", fee_currency="USD")
    buy = create(c, type="Buy", timestamp="2024-01-10T12:00:00Z", from_account_id=1, to_account_id=4,
                 amount="0.2", cost_basis_usd="9000.00", fee_amount="10.00", fee_currency="USD")
    check("buy recorded", Decimal(buy["cost_basis_usd"]) == Decimal("9000.00"))
    fee_ok = move_to_cold_storage(c, own_server)
    sell = create(c, type="Sell", timestamp="2025-02-01T12:00:00Z", from_account_id=4, to_account_id=3,
                  amount="0.05", gross_proceeds_usd="5000.00", fee_amount="5.00", fee_currency="USD")
    check("long-term sell realizes a gain", Decimal(sell["realized_gain_usd"]) > 0
          and sell["holding_period"] == "LONG", str(sell))

    balances = {b["name"]: Decimal(str(b["balance"])) for b in
                c.get("/api/calculations/accounts/balances").json()}
    expected_wallet = Decimal("0.0999") if fee_ok else Decimal("0.1")
    check("cold wallet balance", balances["Wallet"] == expected_wallet, str(balances))
    check("exchange balance", balances["Exchange BTC"] == Decimal("0.05"), str(balances))
    return sell


def move_to_cold_storage(c: httpx.Client, own_server: bool) -> bool:
    """A transfer with a network fee; without one when the server can't
    price it (price sites unreachable from a server not our own). Whether
    the fee went in."""
    try:
        create(c, type="Transfer", timestamp="2024-01-12T12:00:00Z", from_account_id=4, to_account_id=2,
               amount="0.1", fee_amount="0.0001", fee_currency="BTC")
        return True
    except SmokeFailure as exc:
        if own_server or "price" not in str(exc).lower():
            raise
        skip("transfer with network fee", "price APIs unreachable from server")
        create(c, type="Transfer", timestamp="2024-01-12T12:00:00Z", from_account_id=4, to_account_id=2,
               amount="0.1", fee_amount="0", fee_currency="BTC")
        return False


def check_entry_import(c: httpx.Client) -> None:
    print("\nMCP entry import")
    rows = [{"date": "2025-03-01", "type": "Deposit", "amount": "0.001",
             "from_account": "External", "to_account": "Wallet",
             "source": "Income", "cost_basis_usd": "80.00"}]
    r = c.post("/api/import/entries/preview", json={"rows": rows})
    check("preview", r.status_code == 200 and r.json()["ready_count"] == 1, r.text)
    check("preview saved nothing", len(c.get("/api/transactions").json()) == 4)
    r = c.post("/api/import/entries/execute", json={"rows": rows})
    check("execute", r.status_code == 200 and r.json()["imported_count"] == 1, r.text)
    r = c.post("/api/import/entries/execute", json={"rows": rows})
    check("re-import skips the duplicate", r.json()["skipped_duplicates"] == 1, r.text)


def check_recalculate(c: httpx.Client, sell: dict) -> None:
    print("\nRecalculate")
    before = c.get(f"/api/transactions/{sell['id']}").json()["realized_gain_usd"]
    r = c.post("/api/transactions/recalculate")
    check("recalculate", r.status_code == 200, r.text)
    after = c.get(f"/api/transactions/{sell['id']}").json()["realized_gain_usd"]
    check("recalculate is stable", before == after, f"{before} -> {after}")


def check_reports(c: httpx.Client) -> None:
    print("\nReports")
    r = c.get("/api/reports/complete_tax_report", params={"year": 2025})
    check("complete tax report PDF", r.status_code == 200 and r.content[:4] == b"%PDF", r.text[:200])
    r = c.get("/api/reports/irs_reports", params={"year": 2025})
    if r.status_code != 200:
        raise SmokeFailure(f"IRS forms failed: {r.status_code} {r.text[:200]}")
    check("IRS Form 8949 / Schedule D PDF", r.content[:4] == b"%PDF")
    r = c.get("/api/reports/simple_transaction_history", params={"year": 2025, "format": "csv"})
    check("transaction history CSV", r.status_code == 200 and "Sell" in r.text, r.text[:200])
    r = c.get("/api/backup/csv")
    check("CSV export", r.status_code == 200 and r.text.count("\n") >= 5, r.text[:200])


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == "--serve":
        serve(int(sys.argv[2]), sys.argv[3])
        return 0

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="test an already-running instance instead of starting one")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="password")
    ap.add_argument("--setup-code", help="claim a fresh --url instance first, as --user/--password")
    args = ap.parse_args()

    proc = workdir = None
    try:
        user, password, code = args.user, args.password, args.setup_code
        if args.url:
            url = args.url.rstrip("/")
        else:
            proc, url, workdir = start_server()
            # Written at startup next to the database, like /data on Docker
            code = Path(workdir, "setup-code.txt").read_text().strip()
            user, password = SMOKE_USER, SMOKE_PASSWORD
        print(f"Smoke testing {url}")
        run(url, user, password, own_server=proc is not None, setup_code=code)
    except SmokeFailure as exc:
        print(f"\n✗ SMOKE TEST FAILED: {exc}")
        log = os.path.join(workdir, "server.log") if workdir else None
        if log and os.path.exists(log):
            print("\n--- last 40 lines of server log ---")
            print("".join(open(log).readlines()[-40:]))
        return 1
    finally:
        if proc:
            proc.terminate()
            proc.wait(timeout=10)
        if workdir:
            shutil.rmtree(workdir, ignore_errors=True)

    print(f"\n✓ Smoke test passed: {len(PASSED)} checks"
          + (f", {len(SKIPPED)} skipped" if SKIPPED else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
