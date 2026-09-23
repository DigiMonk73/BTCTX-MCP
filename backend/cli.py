"""
backend/cli.py

Maintenance commands, for the StartOS package and for admins of a Docker or
source install. Each command first brings the database to the current schema
(backing it up when there is anything to migrate) and seeds the defaults, so
it works on an empty volume too.

    python -m backend.cli migrate
    python -m backend.cli set-password [--username NAME] [--password-stdin]
    python -m backend.cli recalculate

set-password reads the new password from stdin with --password-stdin, else
from the BTCTX_NEW_PASSWORD environment variable; never from the command line,
where other processes could read it. The database is the one DATABASE_FILE
points at (see backend/database.py).

Exit status: 0 on success, 1 on a failure (message on stderr), 2 on bad usage.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

PASSWORD_ENV = "BTCTX_NEW_PASSWORD"


def _init_db():
    from backend.database import init_db

    return init_db()


def cmd_migrate(args: argparse.Namespace) -> int:
    result = _init_db()
    if result.changed:
        print(f"Database schema: {result.from_revision or 'new'} -> {result.to_revision}")
        if result.backup:
            print(f"Copy of the previous database: {result.backup}")
    else:
        print(f"Database schema is up to date ({result.to_revision}).")
    return 0


def _read_password(args: argparse.Namespace) -> str:
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = os.environ.get(PASSWORD_ENV, "")
    if not password:
        raise ValueError(
            f"No password given: pipe it to --password-stdin or set {PASSWORD_ENV}."
        )
    return password


def cmd_set_password(args: argparse.Namespace) -> int:
    password = _read_password(args)
    username = args.username.strip() if args.username is not None else None
    if username == "":
        raise ValueError("The username can't be empty.")

    _init_db()
    from backend.database import SessionLocal
    from backend.models.user import User

    db = SessionLocal()
    try:
        user = db.query(User).order_by(User.id).first()
        if user is None:  # seed_defaults always creates one; be explicit anyway
            raise RuntimeError("No user account in the database.")
        if username is not None:
            clash = db.query(User).filter(User.username == username, User.id != user.id).first()
            if clash:
                raise ValueError(f"Another user is already named {username!r}.")
            user.username = username
        user.set_password(password)  # bcrypt; refuses more than 72 bytes
        db.commit()
        print(f"Password set for user {user.username!r}.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return 0


def cmd_recalculate(args: argparse.Namespace) -> int:
    _init_db()
    from backend.database import SessionLocal
    from backend.services.transaction import get_all_transactions, recalculate_all_transactions

    db = SessionLocal()
    try:
        recalculate_all_transactions(db)
        db.commit()
        count = len(get_all_transactions(db))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print(f"Recalculated {count} transaction(s).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m backend.cli", description="BitcoinTX maintenance commands")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="bring the database schema up to date and seed defaults").set_defaults(
        func=cmd_migrate
    )

    sp = sub.add_parser("set-password", help="set the login password (and optionally the username)")
    sp.add_argument("--username", help="also rename the account")
    sp.add_argument(
        "--password-stdin", action="store_true", help=f"read the password from stdin (default: ${PASSWORD_ENV})"
    )
    sp.set_defaults(func=cmd_set_password)

    sub.add_parser(
        "recalculate", help="rebuild every ledger line, lot and disposal from the transactions"
    ).set_defaults(func=cmd_recalculate)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
