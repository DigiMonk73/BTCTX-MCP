"""
Make backend/tests/fixtures/old_accounts_1x.db (2.0 spec 5.15, "The
migration"; test_migrations.py): a 1.x database holding what only an old
ledger can, for 2.0's first migration to take in.

- accounts beyond the six fixed ones, made through 1.x's account API before
  v0.9.2 stopped transactions naming them: a BTC "cold2" as 7 and a USD
  "wallet" as 8 (exact-case unique in 1.x, alike "Wallet" ignoring case);
- #289's case: BTC Fees (5) renamed "Fees", then a second "BTC Fees" as 9,
  which 1.x's exact-case uniqueness allows only after that rename;
- a deposit into 7, saved as before v0.9.2 and recalculated by 1.x's engine,
  which acts on it through 7's currency (its ledger lines and lot);
- a transaction naming 999, an account that doesn't exist (no ledger line:
  1.x's recalculation stops on such a row, #337, so it comes last);
- ordinary rows beside them: a deposit into Wallet, a transfer to the
  exchange and a sale there.

Run on 1.x's code (by default the commit this branch forked from
origin/develop), in a child process whose `backend` is that commit's, as
make_reference_1x_db.py does:

    .venv/bin/python backend/tests/fixtures/make_old_accounts_db.py [--code <1.x commit>]

The database's session and AI-key hashes are cleared and the file vacuumed:
the repository is public. Never make it with 2.0's code: its value is that
1.x wrote it.
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

FIXTURES = Path(__file__).resolve().parent
ROOT = FIXTURES.parents[2]
DATABASE = FIXTURES / "old_accounts_1x.db"
SECRETS = ("open_sessions", "mcp_key_sha256")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--code", help="the 1.x commit whose code writes the database "
                        "(default: where this branch forked from origin/develop)")
    parser.add_argument("--inside", metavar="WORK", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.inside:
        write_inside(Path(args.inside))
        return 0
    code = args.code or _git("merge-base", "HEAD", "origin/develop").strip()
    with tempfile.TemporaryDirectory(prefix="btctx-old-accounts-") as tmp:
        work = Path(tmp)
        _run_on(code, work)
        clear_secrets(work / "btctx.db")
        shutil.copyfile(work / "btctx.db", DATABASE)
    print(f"{DATABASE.name} written by {code}'s code")
    return 0


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True).stdout


def _run_on(ref: str, work: Path) -> None:
    """This file again, in a child process whose `backend` is `ref`'s."""
    code = Path(tempfile.mkdtemp(prefix="code-", dir=work))
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", ref, "backend"], check=True, capture_output=True)
    subprocess.run(["tar", "-x", "-C", str(code)], input=archive.stdout, check=True)
    (work / "dist").mkdir(exist_ok=True)  # the app serves no page here
    env = {k: v for k, v in os.environ.items() if not k.startswith("BTCTX_") and k != "DEBUG"}
    env.update(PYTHONPATH=str(code), DATABASE_FILE=str(work / "live" / "btctx.db"),
               BTCTX_FRONTEND_DIST=str(work / "dist"), LOG_LEVEL="ERROR")
    Path(env["DATABASE_FILE"]).parent.mkdir()
    subprocess.run([sys.executable, __file__, "--inside", str(work)], cwd=code, env=env, check=True)


# Raw rows, as only a ledger from before v0.9.2 could hold them
DEPOSIT_INTO_7 = ("INSERT INTO transactions (type, timestamp, from_account_id, to_account_id, amount, "
                  "fee_amount, fee_currency, source, cost_basis_usd) VALUES ('Deposit', "
                  "'2024-03-01T12:00:00Z', 99, 7, 0.50000000, 0, 'BTC', 'MyBTC', 15000.00)")
NAMING_999 = ("INSERT INTO transactions (type, timestamp, from_account_id, to_account_id, amount, "
              "fee_amount, fee_currency, source, cost_basis_usd) VALUES ('Deposit', "
              "'2024-04-01T12:00:00Z', 99, 999, 0.10000000, 0, 'BTC', 'MyBTC', 4000.00)")


def write_inside(work: Path) -> None:
    """In the child, on 1.x's code: the ledger written by its own services."""
    from backend.database import SessionLocal, init_db
    from backend.schemas.transaction import TransactionCreate
    from backend.services.transaction import create_transaction_record, recalculate_all_transactions

    init_db()
    rows = [
        dict(type="Deposit", timestamp="2024-01-10T12:00:00Z", from_account_id=99, to_account_id=2,
             amount="1.00000000", fee_amount="0", fee_currency="BTC", source="MyBTC", cost_basis_usd="40000.00"),
        dict(type="Transfer", timestamp="2024-02-10T12:00:00Z", from_account_id=2, to_account_id=4,
             amount="0.40000000", fee_amount="0", fee_currency="BTC"),
        dict(type="Sell", timestamp="2024-06-10T12:00:00Z", from_account_id=4, to_account_id=3,
             amount="0.25000000", fee_amount="0", fee_currency="USD", proceeds_usd="16000.00"),
    ]
    path = os.environ["DATABASE_FILE"]
    with SessionLocal() as db:
        for row in rows:
            create_transaction_record(TransactionCreate(**row).model_dump(), db)
    with sqlite3.connect(path) as con:
        con.execute("INSERT INTO accounts (id, user_id, name, currency) VALUES (7, 1, 'cold2', 'BTC')")
        con.execute("INSERT INTO accounts (id, user_id, name, currency) VALUES (8, 1, 'wallet', 'USD')")
        con.execute(DEPOSIT_INTO_7)
    with SessionLocal() as db:
        recalculate_all_transactions(db)
        db.commit()
    with sqlite3.connect(path) as con:
        con.execute("UPDATE accounts SET name = 'Fees' WHERE id = 5")
        con.execute("INSERT INTO accounts (id, user_id, name, currency) VALUES (9, 1, 'BTC Fees', 'BTC')")
        con.execute(NAMING_999)
    shutil.copyfile(path, work / "btctx.db")


def clear_secrets(path: Path) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute(f"DELETE FROM app_settings WHERE key IN ({', '.join('?' for _ in SECRETS)})", SECRETS)
        con.commit()
        con.execute("VACUUM")
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
