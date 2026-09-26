"""
backend/routers/entry_import.py

JSON entry import: preview (dry run) and execute for structured rows.
Mounted at /api/import/entries. Used by the MCP server (mcp_server/) so an
AI assistant can turn pasted text or plain English into ledger entries.

Session-auth only, like the CSV and River imports.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services.tax_time import get_tax_timezone
from backend.routers.csv_import import MAX_ROWS
from backend.services.mcp_key import require_login_or_key
from backend.schemas.entry_import import (
    CreatedTransaction,
    EntryExecuteResponse,
    EntryPreviewResponse,
    EntryRequest,
)
from backend.services.entry_import import (
    STATUS_DUPLICATE,
    STATUS_INVALID,
    STATUS_POSSIBLE_DUPLICATE,
    STATUS_READY,
    STATUS_REJECTED,
    autofill_fmv,
    mark_duplicates,
    normalized_view,
    simulate,
    validate_rows,
    write_rows,
)

router = APIRouter()


def _check_size(payload: EntryRequest) -> None:
    if not payload.rows:
        raise HTTPException(status_code=400, detail="No rows provided.")
    if len(payload.rows) > MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many transactions. Maximum is {MAX_ROWS} rows per request.",
        )


@router.post("/preview", response_model=EntryPreviewResponse)
async def preview_entries(
    request: Request,
    payload: EntryRequest,
    db: Session = Depends(get_db),
):
    """
    Validate rows, autofill FMV-derived USD values, flag duplicates of
    existing transactions, and simulate the write (then roll it back).
    Nothing is saved.
    """
    require_login_or_key(request, db)
    _check_size(payload)

    prepared = validate_rows(payload.rows, get_tax_timezone(db))
    await autofill_fmv(prepared)
    mark_duplicates(prepared, db)
    affected, balances = simulate(prepared, db)

    results = [p.result for p in prepared]
    for p in prepared:
        if p.tx_data is not None:
            p.result.normalized = normalized_view(p.tx_data)

    def count(status: str) -> int:
        return sum(1 for r in results if r.status == status)

    return EntryPreviewResponse(
        ok=all(r.status in (STATUS_READY, STATUS_DUPLICATE) for r in results),
        ready_count=count(STATUS_READY),
        duplicate_count=count(STATUS_DUPLICATE),
        possible_duplicate_count=count(STATUS_POSSIBLE_DUPLICATE),
        invalid_count=count(STATUS_INVALID),
        rejected_count=count(STATUS_REJECTED),
        results=results,
        affected_existing=affected,
        balances_after=balances,
    )


@router.post("/execute", response_model=EntryExecuteResponse)
async def execute_entries(
    request: Request,
    payload: EntryRequest,
    db: Session = Depends(get_db),
):
    """
    Write rows atomically. Rows exactly matching an existing transaction
    are skipped; possible (fuzzy) duplicates ARE written — the caller is
    expected to have removed any the user rejected after preview.
    Any invalid row or ledger rejection aborts the whole batch.
    """
    require_login_or_key(request, db)
    _check_size(payload)

    prepared = validate_rows(payload.rows, get_tax_timezone(db))
    invalid = [p.result for p in prepared if p.result.status == STATUS_INVALID]
    if invalid:
        msgs = [f"Row {r.row}: {'; '.join(r.errors)}" for r in invalid]
        detail = "Rows have errors: " + " | ".join(msgs[:5])
        if len(msgs) > 5:
            detail += f" ...and {len(msgs) - 5} more"
        raise HTTPException(status_code=400, detail=detail + ". No transactions were saved.")

    await autofill_fmv(prepared)
    mark_duplicates(prepared, db, exact_only=True)
    skipped = sum(1 for p in prepared if p.result.status == STATUS_DUPLICATE)

    created = write_rows(prepared, db)
    out = [
        CreatedTransaction(
            row=p.row,
            id=tx.id,
            type=tx.type,
            date=tx.timestamp,
            amount=tx.amount,
            realized_gain_usd=tx.realized_gain_usd,
            holding_period=tx.holding_period,
        )
        for p, tx in sorted(created, key=lambda c: c[0].row)
    ]

    message = f"Imported {len(out)} transaction(s)."
    if skipped:
        message += f" Skipped {skipped} already in the ledger."
    return EntryExecuteResponse(
        success=True,
        imported_count=len(out),
        skipped_duplicates=skipped,
        created=out,
        message=message,
    )
