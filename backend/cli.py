"""
backend/cli.py

Maintenance commands, for the StartOS package and for admins of a Docker or
source install. Each command first brings the database to the current schema
(backing it up when there is anything to migrate) and seeds the defaults, so
it works on an empty volume too.

    python -m backend.cli migrate
    python -m backend.cli set-password [--username NAME] [--password-stdin] [--if-default]
    python -m backend.cli recalculate
    python -m backend.cli review [--apply-hourly-prices YEAR]
    python -m backend.cli install-draft-forms [--from-dir DIR | --remove]

set-password reads the new password from stdin with --password-stdin, else
from the BTCTX_NEW_PASSWORD environment variable; never from the command line,
where other processes could read it. With --if-default it changes only an
account still on the shipped admin / password login, and otherwise prints
"Not the default login: nothing changed." (the StartOS package replaces old
default logins this way at update). The database is the one DATABASE_FILE
points at (see backend/database.py).

recalculate and review look up a price only as the app would: run without
the server's price variables the app last started with (on StartOS, by
hand in the service's shell), they ask no one and say so on stderr (#461).

install-draft-forms is for TEST installs only: it puts the IRS's current
DRAFT Form 8949 and Schedule D (from irs.gov, or f8949.pdf and f1040sd.pdf
in DIR) in the data folder, and Reports then offers their year, marked
DRAFT — DO NOT FILE (backend/services/reports/draft_forms.py). --remove
takes them out again.

Exit status: 0 on success, 1 on a failure (message on stderr), 2 on bad usage.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PASSWORD_ENV = "BTCTX_NEW_PASSWORD"


def _init_db(looks_up_prices: bool = False):
    from backend.database import SessionLocal, init_db
    from backend.services import outbound

    result = init_db()
    # The app's price settings: a recalculation or review may look up a price.
    # Never a reason to fail a command (Set Login Credentials runs here too),
    # nor to make a price choice: on StartOS a command may run without the
    # server's variables (#134), so only the app's start upgrades old installs.
    # Without those the app started with, it asks no one (#461), and says so.
    try:
        with SessionLocal() as db:
            outbound.load(db, upgrade=False)
    except Exception as e:
        print(f"warning: couldn't read the price settings, no price lookups: {e}", file=sys.stderr)
        return result
    if looks_up_prices and outbound.current().server_settings_missing:
        print(f"note: {outbound.no_server_settings()}", file=sys.stderr)
    return result


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
    from backend.schemas.user import check_new_password

    return check_new_password(password)  # at least 12 characters


def cmd_set_password(args: argparse.Namespace) -> int:
    password = _read_password(args)
    username = args.username.strip() if args.username is not None else None
    if username == "":
        raise ValueError("The username can't be empty.")

    _init_db()
    from backend.database import SessionLocal
    from backend.models.user import User
    from backend.session_auth import end_all_sessions

    db = SessionLocal()
    try:
        user = db.query(User).order_by(User.id).first()
        if user is None:  # seed_defaults always creates one; be explicit anyway
            raise RuntimeError("No user account in the database.")
        from backend.services import first_run

        if args.if_default and not first_run.is_default_account(user):
            print("Not the default login: nothing changed.")
            return 0
        if username is not None:
            clash = db.query(User).filter(User.username == username, User.id != user.id).first()
            if clash:
                raise ValueError(f"Another user is already named {username!r}.")
            user.username = username
        user.set_password(password)  # bcrypt; refuses more than 72 bytes
        end_all_sessions(db)  # every browser logs in again
        db.commit()
        print(f"Password set for user {user.username!r}.")
        # No longer the default login: the first-run setup code is done with
        first_run.clear_code()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return 0


def cmd_recalculate(args: argparse.Namespace) -> int:
    _init_db(looks_up_prices=True)
    from backend.database import SessionLocal
    from backend.services.transaction import get_all_transactions, recalculate_ledger

    db = SessionLocal()
    try:
        recalculate_ledger(db)
        count = len(get_all_transactions(db))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print(f"Recalculated {count} transaction(s).")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    """
    The Ledger review (backend/services/review.py). Read-only, except with
    --apply-hourly-prices YEAR: then that tax year's values priced at the
    day are priced at their hour, after a backup copy, and the ledger is
    recalculated (services/hourly_review.py).
    """
    _init_db(looks_up_prices=True)
    from backend.database import SessionLocal
    from backend.services.hourly_review import apply_hourly_prices
    from backend.services.review import build_review, format_text

    db = SessionLocal()
    try:
        if args.apply_hourly_prices is not None:
            result = apply_hourly_prices(db, year=args.apply_hourly_prices, wait=True)
            for c in result["changed"]:
                moved = "; ".join(f"{f} ${old} -> ${new}" for f, (old, new) in c["values"].items())
                print(f"  #{c['id']}  {moved}  (at the {c['moment']}'s price)")
            if result["backup"]:
                print(f"Backup copy first: backups/{result['backup']}")
            print(f"Changed {len(result['changed'])} transaction(s)"
                  + (" and recalculated." if result["changed"] else "."))
        else:
            print(format_text(build_review(db)), end="")
    finally:
        db.close()
    return 0


def cmd_install_draft_forms(args: argparse.Namespace) -> int:
    from backend.routers.reports import get_supported_years
    from backend.services.reports import draft_forms

    if args.remove:
        print("IRS draft forms removed." if draft_forms.remove() else "No IRS draft forms were installed.")
        return 0
    year, dest = draft_forms.install(get_supported_years(), args.from_dir)
    print(f"IRS DRAFT forms for {year} installed in {dest}: Reports offers {year} now. "
          "Test only: never file them.")
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
    sp.add_argument(
        "--if-default", action="store_true", help="only if the login is still the default admin / password"
    )
    sp.set_defaults(func=cmd_set_password)

    sub.add_parser(
        "recalculate", help="rebuild every ledger line, lot and disposal from the transactions"
    ).set_defaults(func=cmd_recalculate)

    rp = sub.add_parser("review", help="list transactions to check after upgrading (read-only)")
    rp.add_argument(
        "--apply-hourly-prices", type=int, metavar="YEAR",
        help="price that tax year's values priced at the day at their hour, after a backup copy, "
             "and recalculate (changes figures)",
    )
    rp.set_defaults(func=cmd_review)

    dp = sub.add_parser(
        "install-draft-forms", help="TEST installs only: the IRS's draft forms for the next tax year"
    )
    what = dp.add_mutually_exclusive_group()
    what.add_argument("--from-dir", type=Path, help="f8949.pdf and f1040sd.pdf from this folder, not irs.gov")
    what.add_argument("--remove", action="store_true", help="delete the installed drafts")
    dp.set_defaults(func=cmd_install_draft_forms)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
