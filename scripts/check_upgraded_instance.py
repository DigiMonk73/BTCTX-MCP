#!/usr/bin/env python3
"""
Check a running BitcoinTX that was started on the v0.7.0 test database
(backend/tests/fixtures/v0_7_0.db): it must have upgraded the schema and
still serve the old ledger. Used by CI against the Docker image.

    python scripts/check_upgraded_instance.py --url http://127.0.0.1:8081
"""

import argparse
import sys

import httpx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--transactions", type=int, default=7, help="expected count (the fixture has 7)")
    a = ap.parse_args()

    with httpx.Client(base_url=a.url.rstrip("/"), timeout=60) as c:
        checks = []
        r = c.post("/api/login", json={"username": "admin", "password": "password"})
        checks.append(("login with the v0.7.0 credentials", r.status_code == 200))
        n = len(c.get("/api/transactions").json()) if r.status_code == 200 else -1
        checks.append((f"{a.transactions} transactions survived (found {n})", n == a.transactions))
        checks.append(("tax timezone setting works (migration 0002)",
                       c.get("/api/settings/tax-timezone").status_code == 200))
        pdf = c.get("/api/reports/irs_reports", params={"year": 2024})
        checks.append(("2024 IRS forms generate", pdf.status_code == 200 and pdf.content[:4] == b"%PDF"))

    for name, ok in checks:
        print(f"  {'✓' if ok else '✗'} {name}")
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
