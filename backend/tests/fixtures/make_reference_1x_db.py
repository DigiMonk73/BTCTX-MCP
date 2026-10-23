"""
Make backend/tests/fixtures/reference_1x.db and reference_1x_figures.json
(2.0 spec 5.15; test_reference_1x.py):

- the database: the reference test ledger as the last 1.x release saved it.
  The release's own app, on a throwaway database, claims its install, sets
  the tax timezone to UTC and takes every row of
  testdata/reference_ledger.json a 1.x release knows (the "since" rows left
  out) through its API, with the price source off. Its session and AI-key
  hashes are then deleted and the file vacuumed: the repository is public.
- the figures: what 1.x's latest code (by default the commit this branch
  forked from develop) gives from a copy of that database migrated to its
  head and recalculated, as a user's first edit after upgrading would
  (scripts/reference_figures.py). Not the release's own: develop may have
  fixed figures since it shipped (#549 moves a 2026 fee from box K to L),
  and every 2.0 step must keep 1.x's figures as they stand.

    .venv/bin/python backend/tests/fixtures/make_reference_1x_db.py \
        [--release v1.2.10] [--figures-from <develop commit>]

Each side's code comes from git (git archive, into a temp folder), and this
file runs again on it in a process of its own. Rerun it when a develop
merge brings new reference rows, a 1.x migration or moved figures, or when
a new 1.x release ships (--release). Never make the database with 2.0's
code: its value is that the release's code wrote it.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

RELEASE = "v1.2.10"
FIXTURES = Path(__file__).resolve().parent
ROOT = FIXTURES.parents[2]
SCRIPTS = ROOT / "scripts"
DATABASE = FIXTURES / "reference_1x.db"
FIGURES = FIXTURES / "reference_1x_figures.json"
# app_settings rows a public file must not hold
SECRETS = ("open_sessions", "mcp_key_sha256")
USER, PASSWORD = "reference-1x", "reference-1x-password"  # a test login, nothing real


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--release", default=RELEASE, help="the 1.x release whose code saves the ledger")
    parser.add_argument("--figures-from", help="the 1.x code whose figures are kept "
                        "(default: where this branch forked from origin/develop)")
    parser.add_argument("--seed", metavar="WORK", help=argparse.SUPPRESS)
    parser.add_argument("--figures", metavar="WORK", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.seed:
        seed_inside(Path(args.seed))
    elif args.figures:
        figures_inside(Path(args.figures))
    else:
        make(args.release, args.figures_from or _fork_point())
    return 0


def make(release: str, figures_from: str) -> None:
    with tempfile.TemporaryDirectory(prefix="btctx-reference-1x-") as tmp:
        work = Path(tmp)
        _run_on(release, "--seed", work)
        clear_secrets(work / "btctx.db")
        shutil.copyfile(work / "btctx.db", DATABASE)
        _run_on(figures_from, "--figures", work)
        shutil.copyfile(work / "figures.json", FIGURES)
    print(f"{DATABASE.name} saved by {release}'s code; {FIGURES.name} from {figures_from}'s")


def _fork_point() -> str:
    return _git("merge-base", "HEAD", "origin/develop").strip()


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True).stdout


def _run_on(ref: str, step: str, work: Path) -> None:
    """This file again, in a child process whose `backend` is `ref`'s."""
    code = Path(tempfile.mkdtemp(prefix="code-", dir=work))
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", ref, "backend"], check=True, capture_output=True)
    subprocess.run(["tar", "-x", "-C", str(code)], input=archive.stdout, check=True)
    (work / "dist").mkdir(exist_ok=True)  # the app serves no page here
    env = {k: v for k, v in os.environ.items() if not k.startswith("BTCTX_") and k != "DEBUG"}
    env.update(PYTHONPATH=str(code), DATABASE_FILE=str(work / step.strip("-") / "btctx.db"),
               BTCTX_FRONTEND_DIST=str(work / "dist"), LOG_LEVEL="ERROR")
    Path(env["DATABASE_FILE"]).parent.mkdir()
    subprocess.run([sys.executable, __file__, step, str(work)], cwd=code, env=env, check=True)


def seed_inside(work: Path) -> None:
    """In the child, on the release's code: the ledger seeded through its API,
    by this checkout's scripts/seed_ledger.py. Its 1.x rows need only the
    transaction routes every 1.x release has; once seed_ledger.py makes
    2.0's accounts through the account API (B7a), it must still seed a
    ledger with no `accounts` list without calling that API, or this
    script can no longer remake the fixture with a 1.x release."""
    sys.path.append(str(SCRIPTS))  # after the release's code: scripts/ holds no backend
    from equivalence_ledgers_1x import reference_rows_1x
    from fastapi.testclient import TestClient
    from seed_ledger import log_in, seed

    from backend.database import init_db
    from backend.main import app
    from backend.services import first_run, outbound, price_history

    asked = _no_prices(price_history, outbound)
    init_db()
    client = TestClient(app)
    log_in(client, USER, PASSWORD, first_run.ensure_code())
    zone = client.put("/api/settings/tax-timezone", json={"timezone": "UTC", "chosen": True})
    assert zone.status_code == 200, zone.text
    seed(client, reference_rows_1x(ROOT / "testdata" / "reference_ledger.json"))
    assert not asked, f"the release asked for prices: {asked}"
    shutil.copyfile(os.environ["DATABASE_FILE"], work / "btctx.db")


def figures_inside(work: Path) -> None:
    """In the child, on 1.x's latest code: a copy migrated, recalculated, its figures."""
    sys.path.append(str(SCRIPTS))
    shutil.copyfile(work / "btctx.db", os.environ["DATABASE_FILE"])
    from reference_figures import dumps, figures

    from backend.database import SessionLocal, init_db
    from backend.services.transaction import recalculate_all_transactions

    init_db()
    with SessionLocal() as db:
        recalculate_all_transactions(db)
        db.commit()
        (work / "figures.json").write_text(dumps(figures(db)))


def _no_prices(price_history, outbound) -> list:
    """Price source off, and any price asked for noted: the ledger gives
    every value a price would fill."""
    asked = []

    async def find_prices(day, full):
        asked.append(day)
        return {}, False

    price_history.find_prices = find_prices
    outbound._current = outbound.NetworkSettings(price_source="off")
    return asked


def clear_secrets(path: Path) -> None:
    con = sqlite3.connect(str(path))
    try:
        con.execute(f"DELETE FROM app_settings WHERE key IN ({', '.join('?' for _ in SECRETS)})", SECRETS)
        con.commit()
        con.execute("VACUUM")  # no deleted value left in a free page
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
