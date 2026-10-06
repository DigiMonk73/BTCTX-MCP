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
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Depends, Form, HTTPException, BackgroundTasks, Request, UploadFile
from fastapi.responses import StreamingResponse, PlainTextResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.transaction import Transaction
from backend.models.user import User
from backend.migrate import AI_COPIES_KEPT, backup_copies, backup_sqlite, sqlite_file
from backend.services import ai_key, first_run, outbound
from backend.services.backup import make_backup, restore_backup
from backend.services.csv_import import CSV_COLUMNS, GIFT_LIKE_PURPOSES
from backend.services.reports.safe_text import csv_text
from backend.constants import ACCOUNT_ID_TO_NAME

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


def _login_in_use(db: Session) -> tuple | None:
    user = db.query(User).order_by(User.id).first()
    return (user.username, user.password_hash) if user else None


def _keep_login(db: Session, login: tuple | None) -> None:
    """Put the login from before a restore back on the restored account."""
    user = db.query(User).order_by(User.id).first()
    if login is None or user is None:
        return
    user.username, user.password_hash = login
    db.commit()


@router.post("/restore")
def restore_encrypted_backup(
    request: Request,
    password: str = Form(...),
    file: UploadFile = Form(...),
    db: Session = Depends(get_db),
):
    """
    Restore the database from an encrypted backup file. The login in use (and
    the AI key and the price settings) stays: an old backup never brings back an old password, and
    on StartOS the password Set Login Credentials gave stays right. Clears the session after restore
    since the user_id may no longer be valid.
    """
    _require_auth(request)
    if file.size is not None and file.size > MAX_RESTORE_BYTES:
        raise HTTPException(status_code=413, detail=RESTORE_TOO_LARGE)
    temp_path = None
    ai_state = ai_key.snapshot(db)
    price_settings = outbound.snapshot(db)
    login = _login_in_use(db)
    try:
        with NamedTemporaryFile(delete=False, suffix=".btx") as temp_file:
            temp_path = Path(temp_file.name)
            _copy_at_most(file.file, temp_file, MAX_RESTORE_BYTES)

        restore_backup(password, temp_path)
        # The price settings in use stay (a backup from before a switch to
        # Tor or Off must not ask public sites directly again)...
        db.close()  # a fresh connection sees the restored file
        try:
            outbound.carry_over(db, price_settings)
        except Exception:
            logger.exception("Could not keep the price settings after restore")
        # ...and so do the AI key and switch, so an old backup can't bring
        # back a revoked key.
        db.close()
        try:
            ai_key.carry_over(db, ai_state)
        except Exception:
            logger.exception("Could not keep the AI key after restore")
        db.close()
        try:
            _keep_login(db, login)
        except Exception:
            logger.exception("Could not keep the login after restore")
        # The restored login may be the default one (a setup code) or not
        db.close()
        try:
            first_run.prepare(db)
        except Exception:
            logger.exception("Could not prepare the first-run setup code after restore")

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


@router.post("/ai-copy")
def ai_copy(db: Session = Depends(get_db)):
    """
    A plain copy of the database in <database dir>/backups/, which the AI key
    may ask for (a safety net before a large change). Owner-only like the
    database itself; the newest AI_COPIES_KEPT are kept, apart from the
    pre-upgrade copies; one a minute. Only the file name comes back.
    """
    db_path = sqlite_file(db.get_bind())
    if db_path is None:
        raise HTTPException(status_code=400, detail="This database can't be copied to a file.")
    newest = backup_copies(db_path, "ai")
    if newest and time.time() - newest[0].stat().st_mtime < AI_COPY_EVERY:
        raise HTTPException(status_code=429, detail="A backup was made less than a minute ago.")
    dest = backup_sqlite(db_path, "backup", kind="ai", keep=AI_COPIES_KEPT)
    logger.info("AI backup copy made: %s", dest.name)
    created = datetime.fromtimestamp(dest.stat().st_mtime, timezone.utc)
    return {"file": dest.name, "created": created.isoformat(timespec="seconds"), "kept": AI_COPIES_KEPT}


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
    writer.writerows(_export_row(txn) for txn in transactions)
    filename = f"btctx_transactions_{datetime.now().strftime('%Y-%m-%d')}.csv"

    return PlainTextResponse(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        },
    )


def _export_row(txn: Transaction) -> dict[str, str]:
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
    gift_like = txn_type == "withdrawal" and (txn.purpose or "").lower() in GIFT_LIKE_PURPOSES
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
    }


def _csv_number(value, decimals: int) -> str:
    # The Decimal's own digits: a float keeps about 16, and an amount with
    # all eight decimals can have more.
    return "" if value is None else f"{Decimal(value):.{decimals}f}"
