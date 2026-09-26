#!/usr/bin/env python3
"""
End-to-end smoke test for BitcoinTX.

Starts the REAL server (uvicorn, as Docker and the macOS app do) on a
throwaway database and drives it over HTTP like a user: login, record a
year of activity, import via the MCP entry API, generate every report,
export, recalculate, log out. Exits non-zero on the first failure.

Usage:
    python scripts/smoke_test.py                 # own server, temp DB, stubbed prices
    python scripts/smoke_test.py --url http://127.0.0.1:8080 --user admin --password password
                                                 # an already-running instance (e.g. Docker)

The own-server mode stubs BTC prices so it runs offline. Against --url the
server uses live prices, so price-dependent steps may be skipped if the
price APIs are unreachable. Never point --url at your real data: it
creates transactions.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from decimal import Decimal
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
PASSED: list[str] = []
SKIPPED: list[str] = []


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


# ---------------------------------------------------------------------------
# Own server
# ---------------------------------------------------------------------------
def serve(port: int, db_path: str) -> None:
    """Child-process entry: run the app with deterministic offline prices.

    Also used by the Playwright suite (frontend/e2e) to serve the app.
    """
    os.environ["DATABASE_FILE"] = db_path
    sys.path.insert(0, str(ROOT))

    async def historical(date: str):
        return {"USD": 50000.0}

    async def current():
        return {"USD": 60000.0}

    async def block_height():
        return {"height": 900000}

    async def time_series(days: int = 7):
        return []

    import backend.services.bitcoin as bitcoin
    import backend.routers.river_import as river_router
    import backend.services.entry_import as entry_import

    bitcoin.get_historical_price = historical
    bitcoin.get_current_price = current
    bitcoin.get_block_height = block_height
    bitcoin.get_time_series = time_series
    river_router.get_historical_price = historical
    entry_import.get_historical_price = historical

    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=port, log_level="warning")


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


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------
def run(url: str, user: str, password: str, own_server: bool) -> None:
    c = httpx.Client(base_url=url, timeout=120)

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

    print("\nAuth")
    check("protected API rejects anonymous", c.get("/api/transactions").status_code == 401)
    check("wrong password rejected",
          c.post("/api/login", json={"username": user, "password": password + "x"}).status_code == 401)
    r = c.post("/api/login", json={"username": user, "password": password})
    check("login", r.status_code == 200, r.text)

    print("\nLedger")
    accounts = {a["id"]: a["name"] for a in c.get("/api/accounts/").json()}
    check("six core accounts exist", {1, 2, 3, 4, 5, 6} <= set(accounts), str(accounts))
    if c.get("/api/transactions").json():
        raise SmokeFailure("target already has transactions — use an empty instance")

    def tx(**data):
        r = c.post("/api/transactions", json=data)
        if r.status_code != 200:
            raise SmokeFailure(f"create {data['type']} failed: {r.status_code} {r.text}")
        return r.json()

    tx(type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=99, to_account_id=1,
       amount="20000", fee_amount="0", fee_currency="USD")
    buy = tx(type="Buy", timestamp="2024-01-10T12:00:00Z", from_account_id=1, to_account_id=4,
             amount="0.2", cost_basis_usd="9000.00", fee_amount="10.00", fee_currency="USD")
    check("buy recorded", Decimal(buy["cost_basis_usd"]) == Decimal("9000.00"))

    fee_ok = True
    try:
        tx(type="Transfer", timestamp="2024-01-12T12:00:00Z", from_account_id=4, to_account_id=2,
           amount="0.1", fee_amount="0.0001", fee_currency="BTC")
    except SmokeFailure as exc:
        if own_server or "price" not in str(exc).lower():
            raise
        fee_ok = False
        skip("transfer with network fee", "price APIs unreachable from server")
        tx(type="Transfer", timestamp="2024-01-12T12:00:00Z", from_account_id=4, to_account_id=2,
           amount="0.1", fee_amount="0", fee_currency="BTC")

    sell = tx(type="Sell", timestamp="2025-02-01T12:00:00Z", from_account_id=4, to_account_id=3,
              amount="0.05", gross_proceeds_usd="5000.00", fee_amount="5.00", fee_currency="USD")
    check("long-term sell realizes a gain", Decimal(sell["realized_gain_usd"]) > 0
          and sell["holding_period"] == "LONG", str(sell))

    balances = {b["name"]: Decimal(str(b["balance"])) for b in
                c.get("/api/calculations/accounts/balances").json()}
    expected_wallet = Decimal("0.0999") if fee_ok else Decimal("0.1")
    check("cold wallet balance", balances["Wallet"] == expected_wallet, str(balances))
    check("exchange balance", balances["Exchange BTC"] == Decimal("0.05"), str(balances))

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

    print("\nRecalculate")
    before = c.get(f"/api/transactions/{sell['id']}").json()["realized_gain_usd"]
    r = c.post("/api/transactions/recalculate")
    check("recalculate", r.status_code == 200, r.text)
    after = c.get(f"/api/transactions/{sell['id']}").json()["realized_gain_usd"]
    check("recalculate is stable", before == after, f"{before} -> {after}")

    print("\nReports")
    r = c.get("/api/reports/complete_tax_report", params={"year": 2025})
    check("complete tax report PDF", r.status_code == 200 and r.content[:4] == b"%PDF", r.text[:200])
    r = c.get("/api/reports/irs_reports", params={"year": 2025})
    if r.status_code == 200:
        check("IRS Form 8949 / Schedule D PDF", r.content[:4] == b"%PDF")
    else:
        raise SmokeFailure(f"IRS forms failed: {r.status_code} {r.text[:200]}")
    r = c.get("/api/reports/simple_transaction_history", params={"year": 2025, "format": "csv"})
    check("transaction history CSV", r.status_code == 200 and "Sell" in r.text, r.text[:200])
    r = c.get("/api/backup/csv")
    check("CSV export", r.status_code == 200 and r.text.count("\n") >= 5, r.text[:200])

    print("\nLogout")
    c.post("/api/logout")
    check("logged out", c.get("/api/transactions").status_code == 401)


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == "--serve":
        serve(int(sys.argv[2]), sys.argv[3])
        return 0

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="test an already-running instance instead of starting one")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="password")
    args = ap.parse_args()

    proc = workdir = None
    try:
        if args.url:
            url = args.url.rstrip("/")
        else:
            proc, url, workdir = start_server()
        print(f"Smoke testing {url}")
        run(url, args.user, args.password, own_server=proc is not None)
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
