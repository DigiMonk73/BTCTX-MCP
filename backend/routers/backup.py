# backend/routers/backup.py

from __future__ import annotations

import csv
import logging
import io
import os
import shutil
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Depends, Form, HTTPException, BackgroundTasks, Request, UploadFile
from fastapi.responses import StreamingResponse, PlainTextResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.transaction import Transaction
from backend.services import mcp_key, outbound
from backend.services.backup import make_backup, restore_backup
from backend.constants import ACCOUNT_ID_TO_NAME

logger = logging.getLogger(__name__)

router = APIRouter()

# CSV columns matching the import template
CSV_COLUMNS = [
    "date",
    "type",
    "amount",
    "from_account",
    "to_account",
    "cost_basis_usd",
    "proceeds_usd",
    "fee_amount",
    "fee_currency",
    "source",
    "purpose",
    "notes",
]


def _require_auth(request: Request):
    """
    Check that user is authenticated via session.

    Intentionally session-only (stricter than main.py's dual-mode
    get_current_user): API-key clients must NOT reach backup/restore.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id

# === POST /api/backup/download ===
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

# === POST /api/backup/restore ===
@router.post("/restore")
def restore_encrypted_backup(
    request: Request,
    password: str = Form(...),
    file: UploadFile = Form(...),
    db: Session = Depends(get_db),
):
    """
    Restore the database from an encrypted backup file.
    Clears the session after restore since the user_id may no longer be valid.
    """
    _require_auth(request)
    temp_path = None
    try:
        with NamedTemporaryFile(delete=False, suffix=".btx") as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_path = Path(temp_file.name)

        restore_backup(password, temp_path)
        # The restored database carries its own network settings.
        db.close()  # a fresh connection sees the restored file
        try:
            outbound.load(db)
        except Exception:
            logger.exception("Could not read the network settings after restore")
        # The restored database has its own record of the AI assistant key;
        # keep the key the MCP server already has (Mac app only).
        if mcp_key.enabled():
            db.close()  # a fresh connection sees the restored file
            try:
                mcp_key.sync(db)
            except Exception:
                logger.exception("Could not re-sync the AI assistant key after restore")

        # Clear session - the restored database may have different user IDs
        request.session.clear()

        return {"message": "✅ Database successfully restored. Please log in again."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Restore failed: {str(e)}")
    finally:
        if temp_path and temp_path.exists():
            os.remove(temp_path)


# === GET /api/backup/csv ===
@router.get("/csv", response_class=PlainTextResponse)
def export_transactions_csv(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Export all transactions as a CSV file matching the import template format.
    This creates a clean roundtrip: Export -> Edit -> Re-import.
    """
    _require_auth(request)

    # Query all transactions ordered by timestamp, then by ID for deterministic ordering
    # This ensures consistent export order for same-timestamp transactions
    transactions = db.query(Transaction).order_by(
        Transaction.timestamp.asc(),
        Transaction.id.asc()
    ).all()

    # Build CSV content
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
    writer.writeheader()

    # Helper to format numeric values (empty string if None)
    def fmt_decimal(val, decimals=2):
        if val is None:
            return ""
        return f"{float(val):.{decimals}f}"

    for txn in transactions:
        # Format date as ISO8601 with Z suffix
        date_str = ""
        if txn.timestamp:
            date_str = txn.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Map account IDs to names
        from_account = ACCOUNT_ID_TO_NAME.get(txn.from_account_id, "")
        to_account = ACCOUNT_ID_TO_NAME.get(txn.to_account_id, "")

        # Determine which fields to export based on transaction type
        # For roundtrip compatibility, we export original user-entered values only
        txn_type = (txn.type or "").lower()

        # cost_basis_usd: Only for Buy and Deposit (user-entered acquisition cost)
        # For Sell/Withdrawal, cost_basis_usd is FIFO-calculated, not user input
        if txn_type in ("buy", "deposit"):
            cost_basis = fmt_decimal(txn.cost_basis_usd, 2)
        else:
            cost_basis = ""

        # proceeds_usd: For Sell/Withdrawal, use gross_proceeds_usd (user-entered)
        # The proceeds_usd field is calculated (after fees), gross_proceeds_usd is the input
        # Fallback to proceeds_usd if gross_proceeds_usd is None (for older transactions)
        if txn_type in ("sell", "withdrawal"):
            proceeds_value = txn.gross_proceeds_usd if txn.gross_proceeds_usd is not None else txn.proceeds_usd
            proceeds = fmt_decimal(proceeds_value, 2)
        else:
            proceeds = ""

        row = {
            "date": date_str,
            "type": txn.type or "",
            "amount": fmt_decimal(txn.amount, 8) if txn.amount else "",
            "from_account": from_account,
            "to_account": to_account,
            "cost_basis_usd": cost_basis,
            "proceeds_usd": proceeds,
            "fee_amount": fmt_decimal(txn.fee_amount, 8),
            "fee_currency": txn.fee_currency or "",
            "source": txn.source or "",
            "purpose": txn.purpose or "",
            "notes": "",  # Transaction model doesn't store notes
        }
        writer.writerow(row)

    csv_content = output.getvalue()
    output.close()

    # Generate filename with current date
    filename = f"btctx_transactions_{datetime.now().strftime('%Y-%m-%d')}.csv"

    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        },
    )
