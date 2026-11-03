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
login. compare exits 1 when a figure differs, is gone, or either snap holds an
error answer for it; a figure, an account or a review check only the second
has is noted, not failed (a new release may add one: its CHANGELOG says
so). snap exits 1 when the install answered an error.

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
import threading
import time
import urllib.error
import urllib.request

# A figure as the reports print it: a loss in parentheses (the Complete Tax
# Report's "($1,000.00)", Form 8949's "(9.74)") before a plain amount, so a
# gain that turns into a loss of the same size is a different figure; BTC
# with its sign and every decimal; a date; a value with no price
FIGURE = re.compile(r"\(\$?\d[\d,]*\.\d\d\)|-?\d+\.\d+ BTC|-?\d+\.\d{8}|-?\$?\d[\d,]*\.\d\d\b"
                    r"|\d\d/\d\d/\d{4}|not priced")
YEARS = {"irs": (2024, 2025), "complete": (2023, 2024, 2025), "history": (2023, 2024, 2025)}
# A report can take minutes on a slow VM (the Complete Tax Report's prices)
TIMEOUT = 300
# A request still unanswered after this says so, and again each time after:
# never a silent wait (#848). Most answer in a second or two
SAY_AFTER = 30


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
        done = threading.Event()
        threading.Thread(target=say_while_waiting, args=(path, began, done), daemon=True).start()
        try:
            with web.open(url + path, timeout=TIMEOUT) as r:
                body = r.read()
                answer = body if raw else json.loads(body or b"null")
        except urllib.error.HTTPError as e:
            answer = {"_error": e.code, "_body": e.read().decode()[:300]}
        finally:
            done.set()
        print(f"  GET {path.split('?')[0]} ({time.monotonic() - began:.0f} s)", file=sys.stderr)
        return answer
    return get


def say_while_waiting(path, began, done):
    """Every SAY_AFTER seconds a request is unanswered, a line saying so."""
    while not done.wait(SAY_AFTER):
        print(f"  still waiting on GET {path.split('?')[0]}: {time.monotonic() - began:.0f} s "
              f"(most answer in seconds; it gives up at {TIMEOUT} s)", file=sys.stderr, flush=True)


def log_in(url, web):
    login = {"username": os.environ["BTCTX_USER"], "password": os.environ["BTCTX_PASSWORD"]}
    req = urllib.request.Request(url + "/api/login", method="POST", headers={"Content-Type": "application/json"},
                                 data=json.dumps(login).encode())
    web.open(req, timeout=60).read()


def review_counts(review):
    """Ledger Review's checks by title, each with how many rows it lists."""
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
            figures[key] = FIGURE.findall(text)
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
    errors = errors_in(out)
    for where in errors:
        print(f"FAIL {where}: the install answered an error, recorded in the snap")
    return 1 if errors else 0


def errors_in(value, where="snap"):
    """Where a snap holds an error answer instead of a figure."""
    if isinstance(value, dict):
        if "_error" in value:
            return [where]
        return [e for k, v in value.items() for e in errors_in(v, f"{where}.{k}")]
    if isinstance(value, list):
        return [e for i, v in enumerate(value) for e in errors_in(v, f"{where}[{i}]")]
    return []


class Verdict:
    """Each check's PASS or FAIL, with what was seen."""

    def __init__(self):
        self.failed = 0

    def same(self, name, before, after):
        if errors_in(before) or errors_in(after):  # an error on both sides is no figure
            self.fail(name, f"an error answer: {json.dumps(before)[:200]} -> {json.dumps(after)[:200]}")
        elif before == after:
            print(f"PASS {name}: {json.dumps(before)[:200]}")
        else:
            self.fail(name, f"{json.dumps(before)[:300]} -> {json.dumps(after)[:300]}")

    def fail(self, name, evidence):
        self.failed += 1
        print(f"FAIL {name}: {evidence}")

    def note(self, text):
        print(f"NOTE {text}")


def compare_keyed(v, name, before, after):
    """Two dicts of figures: each one both hold the same, none gone; one only
    the newer holds is noted (a new release may add a figure or a check)."""
    if not isinstance(before, dict) or not isinstance(after, dict) or "_error" in before or "_error" in after:
        v.same(name, before, after)
        return
    for key in sorted(set(before) | set(after)):
        if key not in after:
            v.fail(f"{name}.{key}", f"{json.dumps(before[key])[:200]} -> gone")
        elif key not in before:
            v.note(f"{name}.{key}: new, {json.dumps(after[key])[:200]}")
        else:
            v.same(f"{name}.{key}", before[key], after[key])


def by(rows, key, *fields):
    """A list of the API's rows as a dict keyed by one field (its value the
    other field, or a dict of them), or the error it was."""
    if not isinstance(rows, list):
        return rows
    if len(fields) == 1:
        return {str(row[key]): row.get(fields[0]) for row in rows}
    return {str(row[key]): {f: row.get(f) for f in fields} for row in rows}


def compare_report(v, key, before, after):
    """One report's figures, in order: any figure changed or gone fails."""
    if not (isinstance(before, list) and isinstance(after, list)):
        v.same(f"reports.{key}", before, after)
        return
    ops = [o for o in difflib.SequenceMatcher(a=before, b=after, autojunk=False).get_opcodes() if o[0] != "equal"]
    gone = [f"{before[o[1]:o[2]]} -> {after[o[3]:o[4]]}" for o in ops if o[0] in ("delete", "replace")]
    if gone:
        v.fail(f"reports.{key}", "; ".join(gone)[:600])
    else:
        print(f"PASS reports.{key}: its {len(before)} figures, in order")
    added = [after[o[3]:o[4]] for o in ops if o[0] == "insert"]
    if added:
        v.note(f"reports.{key}: added {added}")


def compare_reports(v, A, B):
    for key in sorted(set(A) | set(B)):
        if key.endswith("_sales_by_exchange"):
            if A.get(key) != B.get(key):  # 2.0's reports add the section to a 1.x ledger's
                v.note(f"{key}: {A.get(key)} -> {B.get(key)}")
        elif key not in B:
            v.fail(f"reports.{key}", "gone")
        elif key not in A:
            v.note(f"reports.{key}: new")
        else:
            compare_report(v, key, A[key], B[key])


def compare(path_a, path_b):
    A, B = (json.load(open(p)) for p in (path_a, path_b))
    for side, path, s in (("before", path_a, A), ("after", path_b, B)):
        print(f"{side}: {path}, {s['health'].get('version')} schema {s['health'].get('schema')}")
    v = Verdict()
    v.same("rows", A["rows"], B["rows"])
    compare_keyed(v, "gains", A["gains"], B["gains"])
    v.same("avg_cost", A["avg_cost"], B["avg_cost"])
    compare_keyed(v, "balance", by(A["balances"], "name", "balance"), by(B["balances"], "name", "balance"))
    compare_keyed(v, "account", by(A["accounts"], "id", "name", "currency"), by(B["accounts"], "id", "name", "currency"))
    compare_keyed(v, "review", A["review"], B["review"])
    compare_reports(v, A["reports"], B["reports"])
    print("PASS: every figure the two share is the same" if not v.failed else f"FAIL: {v.failed} moved")
    return 1 if v.failed else 0


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "snap":
        return snap(sys.argv[2])
    if len(sys.argv) == 4 and sys.argv[1] == "compare":
        return compare(sys.argv[2], sys.argv[3])
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
