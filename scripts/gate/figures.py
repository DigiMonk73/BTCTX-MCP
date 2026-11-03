#!/usr/bin/env python3
"""
A test install's figures through its API, and whether two of them agree:
the release gate's "every figure the same" (docs/AGENT-TESTS.md, UPG-2, the
WAY and BETA tracks), PASS or FAIL per figure with the evidence (#848).
From session 54's scripts for 2.0.0-beta.2's gate.

    BTCTX_URL=… BTCTX_USER=… BTCTX_PASSWORD=… [BTCTX_CA=ca.crt] \\
      scripts/gate/figures.py snap DIR/NAME.json
    scripts/gate/figures.py compare DIR/BEFORE.json DIR/AFTER.json

A snap holds the health, the row count, the Dashboard's balances, gains and
average cost, the accounts, every figure in the reports (IRS forms 2024 and
2025, the Complete Tax Reports and the history CSVs 2023 to 2025: the golden
ledger's years) and Ledger Review's counts. It never holds or prints the
login. compare exits 1 when a figure both snaps have differs; a figure or a
review check only the second has is noted, not failed (a new release may add
one: its CHANGELOG says so).

Only ever against a throwaway install: never a real ledger.
"""

import difflib
import http.cookiejar
import io
import json
import logging
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request

YEARS = {"irs": (2024, 2025), "complete": (2023, 2024, 2025), "history": (2023, 2024, 2025)}
# A report can take minutes on a slow VM (the Complete Tax Report's prices)
TIMEOUT = 300


def opener():
    ca = os.environ.get("BTCTX_CA")
    tls = ssl.create_default_context(cafile=ca) if ca else ssl.create_default_context()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                                       urllib.request.HTTPSHandler(context=tls),
                                       urllib.request.ProxyHandler({}))


def reader(url, web):
    """GET a path: its JSON (or bytes), or the error it answered, saying how long it took."""
    def get(path, raw=False):
        began = time.monotonic()
        try:
            with web.open(url + path, timeout=TIMEOUT) as r:
                body = r.read()
                answer = body if raw else json.loads(body or b"null")
        except urllib.error.HTTPError as e:
            answer = {"_error": e.code, "_body": e.read().decode()[:300]}
        print(f"  GET {path.split('?')[0]} ({time.monotonic() - began:.0f} s)", file=sys.stderr)
        return answer
    return get


def log_in(url, web):
    login = {"username": os.environ["BTCTX_USER"], "password": os.environ["BTCTX_PASSWORD"]}
    req = urllib.request.Request(url + "/api/login", method="POST", headers={"Content-Type": "application/json"},
                                 data=json.dumps(login).encode())
    web.open(req, timeout=60).read()


def review_counts(review):
    if not isinstance(review, dict) or review.get("_error"):
        return review
    return {s.get("title", s.get("key", "?")): s.get("count", len(s.get("items", [])))
            for s in review.get("sections", review.get("checks", []))}


def report_figures(get):
    """Every amount, BTC figure and date each report prints, in order."""
    logging.disable(logging.CRITICAL)  # pypdf's warnings about the IRS forms
    from pypdf import PdfReader
    figures = {}
    for year in YEARS["irs"]:
        figures[f"irs_{year}"] = get(f"/api/reports/irs_reports?year={year}", raw=True)
    for year in YEARS["complete"]:
        figures[f"complete_{year}"] = get(f"/api/reports/complete_tax_report?year={year}", raw=True)
    for year in YEARS["history"]:
        body = get(f"/api/reports/simple_transaction_history?year={year}&format=csv", raw=True)
        figures[f"history_{year}"] = body if isinstance(body, dict) else body.decode()
    for key, body in list(figures.items()):
        if isinstance(body, bytes):
            text = " ".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(body)).pages)
            text = re.sub(r"Date: \d{4}-\d\d-\d\d \d\d:\d\d:\d\d", "Date: X", text)
            figures[key] = re.findall(r"-?\$?\d[\d,]*\.\d\d\b|\d+\.\d{8}(?: BTC)?|\d\d/\d\d/\d{4}|not priced", text)
            figures[key + "_sales_by_exchange"] = "Sales by exchange" in text
    return figures


def snap(path):
    url = os.environ["BTCTX_URL"].rstrip("/")
    web = opener()
    log_in(url, web)
    get = reader(url, web)
    tx = get("/api/transactions")
    out = {
        "health": get("/api/health"),
        "rows": len(tx) if isinstance(tx, list) else tx,
        "balances": get("/api/calculations/accounts/balances"),
        "gains": get("/api/calculations/gains-and-losses"),
        "avg_cost": get("/api/calculations/average-cost-basis"),
        "accounts": get("/api/accounts/"),
        "review": review_counts(get("/api/review")),
        "reports": report_figures(get),
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True, default=str)
    h = out["health"]
    print(f"snap {path}: {h.get('version')} schema {h.get('schema')}, {out['rows']} rows")


class Verdict:
    """Each check's PASS or FAIL, with what was seen."""

    def __init__(self):
        self.failed = 0

    def same(self, name, before, after):
        if before == after:
            print(f"PASS {name}: {json.dumps(before)[:200]}")
        else:
            self.fail(name, f"{json.dumps(before)[:300]} -> {json.dumps(after)[:300]}")

    def fail(self, name, evidence):
        self.failed += 1
        print(f"FAIL {name}: {evidence}")

    def note(self, text):
        print(f"NOTE {text}")


def compare_reports(v, A, B):
    for key, before in sorted(A.items()):
        after = B.get(key)
        if key.endswith("_sales_by_exchange"):
            if before != after:  # 2.0's reports add the section to a 1.x ledger's
                v.note(f"{key}: {before} -> {after}")
        elif isinstance(before, list) and isinstance(after, list):
            ops = [o for o in difflib.SequenceMatcher(a=before, b=after, autojunk=False).get_opcodes()
                   if o[0] != "equal"]
            gone = [f"{before[o[1]:o[2]]} -> {after[o[3]:o[4]]}" for o in ops if o[0] in ("delete", "replace")]
            if gone:
                v.fail(f"reports.{key}", "; ".join(gone)[:600])
            else:
                print(f"PASS reports.{key}: its {len(before)} figures, in order")
            added = [after[o[3]:o[4]] for o in ops if o[0] == "insert"]
            if added:
                v.note(f"reports.{key}: added {added}")
        else:
            v.same(f"reports.{key}", before, after)


def compare(path_a, path_b):
    A, B = (json.load(open(p)) for p in (path_a, path_b))
    for side, s in (("before", A), ("after", B)):
        v_ = s["health"]
        print(f"{side}: {path_a if side == 'before' else path_b}, {v_.get('version')} schema {v_.get('schema')}")
    v = Verdict()
    v.same("rows", A["rows"], B["rows"])
    for k in sorted(set(A["gains"]) & set(B["gains"])):
        v.same(f"gains.{k}", A["gains"][k], B["gains"][k])
    v.same("avg_cost", A["avg_cost"], B["avg_cost"])
    balance = [{b["name"]: b["balance"] for b in s["balances"]} for s in (A, B)]
    for k in sorted(set(balance[0]) | set(balance[1])):
        v.same(f"balance.{k}", balance[0].get(k), balance[1].get(k))
    for k in sorted(set(A["review"]) & set(B["review"])):
        v.same(f"review.{k}", A["review"][k], B["review"][k])
    for k in sorted(set(B["review"]) - set(A["review"])):
        v.note(f"review.{k}: a new check, {B['review'][k]}")
    compare_reports(v, A["reports"], B["reports"])
    print("PASS: every figure the two share is the same" if not v.failed else f"FAIL: {v.failed} moved")
    return 1 if v.failed else 0


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "snap":
        snap(sys.argv[2])
        return 0
    if len(sys.argv) == 4 and sys.argv[1] == "compare":
        return compare(sys.argv[2], sys.argv[3])
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
