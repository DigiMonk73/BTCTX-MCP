"""
backend/routers/csv_import.py

API endpoints for CSV import feature.
Provides template download, status check, preview, and execute endpoints.
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

# File size limit: 5MB
MAX_FILE_SIZE = 5 * 1024 * 1024

# Maximum rows allowed
MAX_ROWS = 10000


def _require_auth(request: Request):
    """
    Check that user is authenticated via session.

    Intentionally session-only (stricter than main.py's dual-mode
    get_current_user): API-key clients must NOT reach CSV import.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


async def _read_validated_csv(file: UploadFile) -> bytes:
    """Validate the uploaded file's extension, size, and non-emptiness; return its content."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="File must be a CSV file (.csv extension)"
        )

    content = await file.read()

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
    """
    Download a blank CSV template with headers and sample rows.

    Returns:
        CSV file with Content-Disposition header for download
    """
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
    """
    Download the CSV import instructions PDF.

    Returns:
        PDF file with Content-Disposition header for download
    """
    _require_auth(request)

    # Get path to instructions PDF
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
    """
    Check if the database is ready for import (empty).

    Returns:
        DatabaseStatusResponse with is_empty flag and transaction count
    """
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
async def preview_import(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Parse and validate CSV without writing to database.

    Returns:
        Preview of all transactions with any errors/warnings
    """
    _require_auth(request)

    content = await _read_validated_csv(file)

    # Parse CSV
    result = parse_csv_file(content, get_tax_timezone(db))

    # Check row limit
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
async def execute_csv_import(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Parse, validate, and import transactions atomically.
    Requires database to be empty.

    Returns:
        Import result with success flag and count
    """
    _require_auth(request)

    # Check database is empty
    is_empty, count = check_database_empty(db)
    if not is_empty:
        raise HTTPException(
            status_code=400,
            detail=f"Database has {count} existing transaction(s). Please delete all transactions before importing."
        )

    content = await _read_validated_csv(file)

    # Parse CSV
    result = parse_csv_file(content, get_tax_timezone(db))

    # Check for errors
    if not result.can_import:
        error_messages = [f"Row {e.row_number}: {e.message}" for e in result.errors[:5]]
        detail = "CSV has errors: " + "; ".join(error_messages)
        if len(result.errors) > 5:
            detail += f" ...and {len(result.errors) - 5} more errors"
        raise HTTPException(status_code=400, detail=detail)

    # Check row limit
    if len(result.transactions) > MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many transactions. Maximum is {MAX_ROWS} rows per import."
        )

    # Execute import
    try:
        imported_count = execute_import(db, result.transactions)
        return CSVImportResponse(
            success=True,
            imported_count=imported_count,
            message=f"Successfully imported {imported_count} transaction(s)."
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Import failed: {str(e)}. No transactions were saved."
        )
