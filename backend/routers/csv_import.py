"""
CSV import into an empty ledger: the template and instructions, the status
check, the preview and the import (a logged-in session only).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services.tax_time import get_tax_timezone
from backend.schemas.csv_import import (
    CSVPreviewResponse,
    CSVImportResponse,
    DatabaseStatusResponse,
)
from backend.services.csv_import import (
    parse_csv_file,
    check_database_empty,
    execute_import,
    generate_template_csv,
)


router = APIRouter()

MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_ROWS = 10000


def _require_auth(request: Request):
    """
    The logged-in user's id, or 401. Session only, stricter than main.py's
    get_current_user: the AI key must never reach CSV import.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


def _read_validated_csv(file: UploadFile) -> bytes:
    """The uploaded file's content, once its extension and size are checked.

    For the plain `def` import endpoints: FastAPI runs those in a worker
    thread, so the parsing and ledger work never hold up the event loop and
    every other request (/api/health included), and they read the upload
    with the file's own blocking read.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="File must be a CSV file (.csv extension)"
        )

    content = file.file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)}MB."
        )

    if len(content) == 0:
        raise HTTPException(
            status_code=400,
            detail="File is empty."
        )

    return content


@router.get("/template", response_class=PlainTextResponse)
async def download_template(request: Request):
    """The CSV template: the header and a sample row of each kind."""
    _require_auth(request)

    content = generate_template_csv()

    return PlainTextResponse(
        content=content,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=btctx_import_template.csv"
        }
    )


@router.get("/instructions", response_class=FileResponse)
async def download_instructions(request: Request):
    """The CSV import instructions (backend/assets/csv_import_instructions.pdf)."""
    _require_auth(request)

    pdf_path = Path(__file__).parent.parent / "assets" / "csv_import_instructions.pdf"

    if not pdf_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Instructions PDF not found. Please contact support."
        )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename="BitcoinTX_CSV_Import_Guide.pdf",
    )


@router.get("/status", response_model=DatabaseStatusResponse)
async def check_import_status(
    request: Request,
    db: Session = Depends(get_db)
):
    """Whether the ledger is empty, as an import needs it to be."""
    _require_auth(request)

    is_empty, count = check_database_empty(db)

    if is_empty:
        message = "Database is empty. You can import transactions."
    else:
        message = f"Database has {count} existing transaction(s). Please delete all transactions before importing, or start with a fresh database."

    return DatabaseStatusResponse(
        is_empty=is_empty,
        transaction_count=count,
        message=message
    )


@router.post("/preview", response_model=CSVPreviewResponse)
def preview_import(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Every row checked, with its errors and warnings; nothing is saved."""
    _require_auth(request)

    content = _read_validated_csv(file)

    result = parse_csv_file(content, get_tax_timezone(db))

    if len(result.transactions) > MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many transactions. Maximum is {MAX_ROWS} rows per import."
        )

    return CSVPreviewResponse(
        success=True,
        total_rows=len(result.previews) + len(result.errors),
        valid_rows=len(result.previews),
        transactions=result.previews,
        errors=result.errors,
        warnings=result.warnings,
        can_import=result.can_import
    )


@router.post("/execute", response_model=CSVImportResponse)
def execute_csv_import(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Import every row, or none: the ledger must be empty."""
    _require_auth(request)

    is_empty, count = check_database_empty(db)
    if not is_empty:
        raise HTTPException(
            status_code=400,
            detail=f"Database has {count} existing transaction(s). Please delete all transactions before importing."
        )

    content = _read_validated_csv(file)

    result = parse_csv_file(content, get_tax_timezone(db))

    if not result.can_import:
        error_messages = [f"Row {e.row_number}: {e.message}" for e in result.errors[:5]]
        detail = "CSV has errors: " + "; ".join(error_messages)
        if len(result.errors) > 5:
            detail += f" ...and {len(result.errors) - 5} more errors"
        raise HTTPException(status_code=400, detail=detail)

    if len(result.transactions) > MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many transactions. Maximum is {MAX_ROWS} rows per import."
        )

    try:
        imported_count = execute_import(db, result.transactions)
        return CSVImportResponse(
            success=True,
            imported_count=imported_count,
            message=f"Successfully imported {imported_count} transaction(s)."
        )
    except HTTPException as e:
        # A row the ledger refused (no price for a fee, not enough BTC...)
        detail = str(e.detail).rstrip(".") + "."
        if "Not enough BTC" in detail:
            detail += (" Rows are imported by date, and rows at the same time in the file's order:"
                       " list a buy before a sale or move it pays for.")
        raise HTTPException(
            status_code=e.status_code,
            detail=f"Import failed: {detail} No transactions were saved."
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Import failed: {str(e)}. No transactions were saved."
        )
