#!/usr/bin/env python3
"""
The figures BitcoinTX computes from a ledger, as plain JSON: each year's
Form 8949 rows and Schedule D lines, the complete tax report's data (start-
and end-of-year holdings, gains, income, rebates, gifts, each box), and the
dashboard's balances and totals.

testdata/reference_figures.json holds them for the reference test ledger
(testdata/reference_ledger.json, loaded by scripts/seed_ledger.py).
backend/tests/test_seed_ledger.py recomputes and compares them on every
change, so no figure moves unnoticed. After a change meant to move figures,
`make reference-figures` rewrites the file and the pull request shows the
difference; a change in tax figures waits for the owner's "merge".

A release's saved database (kept in the test lab) works too, after
`DATABASE_FILE=<copy> python -m backend.cli migrate` if it is older:

    python scripts/reference_figures.py --db <copy of btctx.db> > figures.json
    python scripts/reference_figures.py --db <copy> --compare figures.json

A test tool: it lives in scripts/, which no build ships.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIGURES = ROOT / "testdata" / "reference_figures.json"
YEARS = (2023, 2024, 2025, 2026)
# Depend on when they are computed, not on the ledger
VOLATILE = {"report_date", "year_to_date_capital_gains"}


def figures(db) -> dict:
    """Every figure, by year and for the dashboard, JSON-ready."""
    from backend.services import calculation
    from backend.services.reports.form_8949 import build_form_8949_and_schedule_d
    from backend.services.reports.reporting_core import generate_report_data

    years = {}
    for year in YEARS:
        forms = build_form_8949_and_schedule_d(year, db)
        years[str(year)] = {
            "form_8949": forms["short_term"] + forms["long_term"],
            "schedule_d": forms["schedule_d"],
            "report": generate_report_data(db, year),
        }
    dashboard = {
        "balances": calculation.get_all_account_balances(db),
        "average_cost_basis": calculation.get_average_cost_basis(db),
        "gains_and_losses": calculation.get_gains_and_losses(db),
    }
    return _plain({"years": years, "dashboard": dashboard})


def _plain(value):
    """Decimals, dates and the like as text; volatile keys left out."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def dumps(data: dict) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def differences(saved, now, path: str = "figures"):
    """Where two figure trees differ, as 'path: saved -> now'."""
    if isinstance(saved, dict) and isinstance(now, dict):
        for key in sorted(set(saved) | set(now)):
            yield from differences(saved.get(key), now.get(key), f"{path}.{key}")
    elif isinstance(saved, list) and isinstance(now, list) and len(saved) == len(now):
        for i, (a, b) in enumerate(zip(saved, now)):
            yield from differences(a, b, f"{path}[{i}]")
    elif saved != now:
        yield f"{path}: {json.dumps(saved)[:120]} -> {json.dumps(now)[:120]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", required=True, help="a copy of a BitcoinTX database (never the real one)")
    parser.add_argument("--compare", metavar="FIGURES_JSON",
                        help="compare with saved figures instead of printing them (exit 1 on a difference)")
    args = parser.parse_args(argv)
    os.environ["DATABASE_FILE"] = str(Path(args.db).resolve())
    sys.path.insert(0, str(ROOT))
    from backend.database import SessionLocal

    with SessionLocal() as db:
        now = figures(db)
    if not args.compare:
        sys.stdout.write(dumps(now))
        return 0
    moved = list(differences(json.loads(Path(args.compare).read_text()), now))
    print("\n".join(moved[:50]) if moved else "No figure moved.")
    return 1 if moved else 0


if __name__ == "__main__":
    sys.exit(main())
