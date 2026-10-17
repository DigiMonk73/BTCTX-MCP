"""
Backups: the encrypted backup download and restore and the CSV export (a
logged-in session only), and the plain copy the AI key may ask for.
"""

from __future__ import annotations

import csv
import logging
import io
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from functools import partial
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Depends, Form, HTTPException, BackgroundTasks, Request, UploadFile
from fastapi.responses import StreamingResponse, PlainTextResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.app_setting import AppSetting
from backend.models.transaction import Transaction
from backend.models.user import User
from backend.schemas.user import MIN_PASSWORD_LENGTH, NOT_TEXT, is_text
from backend.migrate import AI_COPIES_KEPT, backup_copies, backup_sqlite, sqlite_file
from backend import session_auth
from backend.services import ai_key, first_run, outbound
from backend.services.backup import make_backup, restore_backup
from backend.services.csv_import import CSV_COLUMNS
from backend.services.reports.safe_text import csv_text
from backend.services.tax_time import get_tax_timezone, local_date
from backend.constants import ACCOUNT_ID_TO_NAME, BTC_ACCOUNTS, GIFT_LIKE_PURPOSES, INHERITED_SOURCE, VALUED_AT_RECEIPT, normalized

logger = logging.getLogger(__name__)

router = APIRouter()


def _require_auth(request: Request):
    """
    Check that user is authenticated via session.

    Intentionally session-only (stricter than main.py's get_current_user):
    the AI key must never reach backup download, restore or CSV export.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


def _require_text_password(password: str) -> None:
    """A backup's password is form data, which a part's own charset (such
    as unicode_escape) can fill with a lone surrogate: the key can't be
    derived from it, so a 422 rather than a server error (#313)."""
    if not is_text(password):
        raise HTTPException(status_code=422, detail=NOT_TEXT.format("password"))


# A new backup's password: the login passwords' rule (#204). The file holds
# the whole ledger and the login's hash; PBKDF2 slows guessing, but a short
# password still falls offline. A backup made before with a shorter one
# still restores: the restore asks only for the right password.
BACKUP_PASSWORD_TOO_SHORT = (f"A new backup's password must be at least {MIN_PASSWORD_LENGTH} "
                             "characters. (A backup made earlier with a shorter one still restores.)")


@router.post("/download", response_class=StreamingResponse)
def download_encrypted_backup(
    request: Request,
    background_tasks: BackgroundTasks,
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    Download an encrypted backup of the database.
    Uses BackgroundTasks to clean up temp file after streaming completes.
    """
    _require_auth(request)
    _require_text_password(password)
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=422, detail=BACKUP_PASSWORD_TOO_SHORT)
    with NamedTemporaryFile(delete=False, suffix=".btx") as temp_file:
        temp_path = Path(temp_file.name)
        make_backup(password, temp_path)

    def cleanup():
        if temp_path.exists():
            os.remove(temp_path)

    background_tasks.add_task(cleanup)

    return StreamingResponse(
        open(temp_path, "rb"),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename=bitcoin_backup.btx"
        },
    )

# A backup holds the SQLite database: a few MB even for years of activity.
MAX_RESTORE_BYTES = 1 << 30  # 1 GiB
RESTORE_TOO_LARGE = "This file is too large to be a BitcoinTX backup (the limit is 1 GiB)."


def _copy_at_most(src, dst, limit: int) -> None:
    """Copy in chunks, stopping with 413 once more than `limit` bytes came."""
    copied = 0
    while chunk := src.read(1024 * 1024):
        copied += len(chunk)
        if copied > limit:
            raise HTTPException(status_code=413, detail=RESTORE_TOO_LARGE)
        dst.write(chunk)


# A restore that couldn't keep this install's settings in the restored
# database stops before the live one is touched (#201).
NOT_KEPT = (
    "This install's login, AI key and price settings couldn't be kept in the restored backup, "
    "so the restore stopped. Your database is unchanged."
)


def _in_use(db: Session, request: Request) -> dict:
    """What a restore keeps from this install: the login, the AI key and
    switch, the price settings, and the sessions open in other browsers
    (this one logs in again: the restored database may have other user ids).
    The backup's own list of sessions never comes back, so a session that
    ended since it was made stays ended."""
    own = session_auth.session_hash(request)
    sessions = [h for h in session_auth.open_sessions(db) if h != own][-session_auth.MAX_OPEN_SESSIONS:]
    return {"login": _login_in_use(db), "ai": ai_key.snapshot(db), "prices": outbound.snapshot(db),
            "sessions": sessions}


def _login_in_use(db: Session) -> tuple | None:
    user = db.query(User).order_by(User.id).first()
    return (user.username, user.password_hash) if user else None


def _write_kept(kept: dict, restored: Session) -> None:
    """
    Write this install's login, AI key and switch, and price settings into
    the restored database before it replaces the live one, then read them
    back from the file, with its one login. An error, or a value that
    doesn't read back as written, stops the restore with the live database
    untouched (#201).
    """
    try:
        outbound.carry_over(restored, kept["prices"])
        ai_key.carry_over(restored, kept["ai"])
        _keep_login(restored, kept["login"])
        session_auth.put_open_sessions(restored, kept["sessions"])
        restored.commit()
        restored.close()  # read back on a fresh connection, from the file
        as_written = restored.query(User).count() == 1 and _as_stored(restored, kept) == kept
    except SQLAlchemyError as e:
        logger.error("Restore stopped: this install's settings couldn't be written into the restored database (%s)",
                     type(e).__name__)
        raise ValueError(NOT_KEPT) from e
    if not as_written:
        logger.error("Restore stopped: this install's settings didn't read back as written in the restored database")
        raise ValueError(NOT_KEPT)


def _keep_login(db: Session, login: tuple | None) -> None:
    """Put the login from before a restore on the restored account."""
    user = db.query(User).order_by(User.id).first()
    if login is None or user is None:
        return
    user.username, user.password_hash = login
    db.flush()


def _as_stored(db: Session, kept: dict) -> dict:
    """The same, as the restored database holds them. The settings are read
    as rows, not through snapshot(), which takes a missing price source for
    "unset": a restore that lost it would pass the check."""
    login = _login_in_use(db) if kept["login"] is not None else None
    return {"login": login, "ai": _rows(db, kept["ai"]), "prices": _rows(db, kept["prices"]),
            "sessions": session_auth.open_sessions(db)}


def _rows(db: Session, keys) -> dict:
    """These app_settings rows' values, None for a missing one."""
    return {key: row.value if (row := db.get(AppSetting, key)) else None for key in keys}


def _refresh_after_restore(db: Session) -> None:
    """
    The restored database is live, with this install's settings in it: read
    the price settings into memory and make or remove the first-run setup
    code. The Mac app's key file isn't touched (ai_key.sync would write a new
    key): the key the connector holds is this install's and keeps working.
    An error is only logged: the restored database already holds this
    install's settings, and what's in memory and on disk was made from those
    same settings before the restore.
    """
    steps = ((outbound.load, "the price settings"), (first_run.prepare, "the first-run setup code"))
    for step, what in steps:
        db.close()  # a fresh connection sees the restored file
        try:
            step(db)
        except Exception:
            logger.exception("Could not refresh %s after restore", what)


@router.post("/restore")
def restore_encrypted_backup(
    request: Request,
    password: str = Form(...),
    file: UploadFile = Form(...),
    db: Session = Depends(get_db),
):
    """
    Restore the database from an encrypted backup file. The login in use (and
    the AI key and switch, and the price settings) stays: an old backup never
    brings back an old password, and on StartOS the password Set Login
    Credentials gave stays right. The restored database is rebuilt from
    BitcoinTX's own migrations with only the backup's own data, and these are
    written into it before it replaces the live one; if anything fails,
    nothing is restored.
    Clears the session after restore since the user_id may no longer be valid.
    """
    _require_auth(request)
    _require_text_password(password)
    if file.size is not None and file.size > MAX_RESTORE_BYTES:
        raise HTTPException(status_code=413, detail=RESTORE_TOO_LARGE)
    temp_path = None
    kept = _in_use(db, request)
    db.close()  # this request holds no connection to the database being replaced
    try:
        with NamedTemporaryFile(delete=False, suffix=".btx") as temp_file:
            temp_path = Path(temp_file.name)
            _copy_at_most(file.file, temp_file, MAX_RESTORE_BYTES)

        restore_backup(password, temp_path, carry_over=partial(_write_kept, kept))
        _refresh_after_restore(db)

        # Clear session - the restored database may have different user IDs
        request.session.clear()

        return {"message": "✅ Database successfully restored. Log in again with your current username and password."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Restore failed: {str(e)}")
    finally:
        if temp_path and temp_path.exists():
            os.remove(temp_path)


AI_COPY_EVERY = 60  # seconds
AI_COPY_LABEL = "backup"


@router.post("/ai-copy")
def ai_copy(db: Session = Depends(get_db)):
    """
    A plain copy of the database in <database dir>/backups/, which the AI key
    may ask for (a safety net before a large change). Owner-only like the
    database itself; the newest AI_COPIES_KEPT AI copies are kept (and more:
    migrate.prune_backups), apart from the pre-upgrade copies; one a minute.
    Only the file name comes back, and how many AI copies are kept now.
    """
    db_path = sqlite_file(db.get_bind())
    if db_path is None:
        raise HTTPException(status_code=400, detail="This database can't be copied to a file.")
    # Only the copies asked for count: the one made before the key's
    # changes never refuses the copy the AI asks for next.
    newest = backup_copies(db_path, "ai", label=AI_COPY_LABEL)
    if newest and time.time() - newest[0].stat().st_mtime < AI_COPY_EVERY:
        raise HTTPException(status_code=429, detail="A backup was made less than a minute ago.")
    dest = backup_sqlite(db_path, AI_COPY_LABEL, kind="ai", keep=AI_COPIES_KEPT)
    logger.info("AI backup copy made: %s", dest.name)
    created = datetime.fromtimestamp(dest.stat().st_mtime, timezone.utc)
    return {"file": dest.name, "created": created.isoformat(timespec="seconds"),
            "kept": len(backup_copies(db_path, "ai"))}


@router.get("/csv", response_class=PlainTextResponse)
def export_transactions_csv(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Every transaction as a CSV file in the import template's columns, so an
    export imports back to the same ledger.
    """
    _require_auth(request)

    # Same-time transactions in the order they were saved, as the ledger
    # replays them: a round trip gives the same FIFO results.
    transactions = db.query(Transaction).order_by(
        Transaction.timestamp.asc(),
        Transaction.id.asc()
    ).all()

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    tz = get_tax_timezone(db)
    writer.writerows(_export_row(txn, tz) for txn in transactions)
    filename = f"btctx_transactions_{datetime.now().strftime('%Y-%m-%d')}.csv"

    return PlainTextResponse(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        },
    )


def _date_acquired(txn: Transaction, tz) -> str:
    """
    The date originally acquired (or of death) as stored. A change of tax
    timezone since the save can put the deposit on the day before its date:
    its coins then count from the deposit itself (_lot_acquired, #185), as
    a My BTC or Gift row without a date does, so that one goes blank and
    imports back to the same lot (its own day, at noon, could sort before
    another lot of that day). An Inherited deposit needs its date of death,
    which also prices it: it goes as stored, and the import names the row
    to correct.
    """
    if txn.acquired_at is None:
        return ""
    if txn.acquired_at > local_date(txn.timestamp, tz) and normalized(txn.source) != INHERITED_SOURCE:
        return ""
    return txn.acquired_at.isoformat()


def _export_row(txn: Transaction, tz) -> dict[str, str]:
    """
    The transaction as a CSV row of the values the user entered: a Sell's or
    Withdrawal's basis comes from its lots and isn't exported, and its
    proceeds are the gross before fees (else, for older rows, the stored
    ones). A BTC fee's stored USD value goes too, so a re-import never
    prices it again (the same figures, even with price lookups off), and a
    gift's FMV. Text cells can't start a spreadsheet formula
    (safe_text.csv_text); the numbers are written as they are.
    """
    txn_type = (txn.type or "").lower()
    btc_fee = (txn.fee_currency or "").upper() == "BTC" and bool(txn.fee_amount)
    gift_like = txn_type == "withdrawal" and normalized(txn.purpose) in GIFT_LIKE_PURPOSES
    entered_proceeds = txn.gross_proceeds_usd if txn.gross_proceeds_usd is not None else txn.proceeds_usd
    return {
        "date": txn.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ") if txn.timestamp else "",
        "type": csv_text(txn.type),
        "amount": _csv_number(txn.amount, 8) if txn.amount else "",
        "from_account": csv_text(ACCOUNT_ID_TO_NAME.get(txn.from_account_id, "")),
        "to_account": csv_text(ACCOUNT_ID_TO_NAME.get(txn.to_account_id, "")),
        "cost_basis_usd": _csv_number(txn.cost_basis_usd, 2) if txn_type in ("buy", "deposit") else "",
        "proceeds_usd": _csv_number(entered_proceeds, 2) if txn_type in ("sell", "withdrawal") else "",
        "fee_amount": _csv_number(txn.fee_amount, 8),
        "fee_currency": csv_text(txn.fee_currency),
        "source": csv_text(txn.source),
        "purpose": csv_text(txn.purpose),
        "notes": "",  # not stored
        "fee_usd": _csv_number(txn.fee_usd, 2) if btc_fee else "",
        "fmv_usd": _csv_number(txn.fmv_usd, 2) if gift_like else "",
        "broker_reporting": csv_text(txn.broker_reporting),
        "fee_usd_typed": ("yes" if txn.fee_usd_manual else "no") if btc_fee and txn.fee_usd is not None else "",
        "cost_basis_typed": _basis_typed(txn),
        "acquired_at": _date_acquired(txn, tz),
        "proceeds_typed": _proceeds_typed(txn),
        "price_moment": csv_text(txn.price_moment),
        "fmv_typed": ("no" if txn.fmv_from_price else "yes") if gift_like and txn.fmv_usd is not None else "",
    }


def _proceeds_typed(txn: Transaction) -> str:
    """A Spent's proceeds: yes if typed, no if priced (an edit prices them
    again); blank otherwise."""
    spent = (txn.type or "").lower() == "withdrawal" and normalized(txn.purpose) == "spent"
    if not spent or txn.gross_proceeds_usd is None:
        return ""
    return "no" if txn.proceeds_from_price else "yes"


def _basis_typed(txn: Transaction) -> str:
    """An income or rebate deposit's basis: yes if typed, no if priced (so a
    re-import keeps re-pricing it on edits, #76); blank otherwise."""
    valued = (txn.type or "").lower() == "deposit" and normalized(txn.source) in VALUED_AT_RECEIPT \
        and txn.to_account_id in BTC_ACCOUNTS
    if not valued or txn.cost_basis_usd is None:
        return ""
    return "no" if txn.cost_basis_from_price else "yes"


def _csv_number(value, decimals: int) -> str:
    # The Decimal's own digits: a float keeps about 16, and an amount with
    # all eight decimals can have more.
    return "" if value is None else f"{Decimal(value):.{decimals}f}"
