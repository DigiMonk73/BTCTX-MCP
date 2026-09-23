"""
backend/routers/river_import.py

API endpoints for importing River bitcoin-activity CSV exports into a live
ledger (merge with dedup). See docs/RIVER_IMPORT_PLAN.md.

Unlike /api/import (the onboarding CSV import, which requires an empty
database), this flow is designed for ongoing incremental imports.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.routers.csv_import import MAX_ROWS, _read_validated_csv, _require_auth
from backend.schemas.river_import import (
    RiverExecuteRequest,
    RiverImportResponse,
    RiverPreviewResponse,
    RiverProposalOut,
)
from backend.schemas.csv_import import CSVParseError
from backend.services.bitcoin import get_historical_price
from backend.services.csv_import import _validate_row, execute_import
from backend.services.river_import import (
    STATUS_DISCREPANCY,
    STATUS_MATCHED,
    STATUS_NEW,
    RiverProposal,
    adapt_river_rows,
    annotate_duplicates,
    ledger_amount,
    parse_river_csv,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _autofill_fmv_basis(
    proposals: List[RiverProposal], warnings: List[CSVParseError]
) -> None:
    """
    Prefill cost_basis_usd (fair market value at receipt) on Deposit
    proposals (Interest/Income) using the historical daily BTC price.
    Degrades gracefully: on lookup failure the basis stays blank and a
    warning tells the user to fill it in.
    """
    price_cache: Dict[str, Optional[Decimal]] = {}

    for proposal in proposals:
        if proposal.type != "Deposit" or proposal.cost_basis_usd is not None:
            continue
        date_str = proposal.timestamp.strftime("%Y-%m-%d")
        if date_str not in price_cache:
            try:
                price_data = await get_historical_price(date_str)
                price_cache[date_str] = Decimal(str(price_data["USD"]))
            except Exception as exc:
                price_cache[date_str] = None
                logger.warning("FMV lookup failed for %s: %s", date_str, exc)
                warnings.append(CSVParseError(
                    row_number=proposal.row_number, column="cost_basis_usd",
                    severity="warning",
                    message=(
                        f"Could not fetch the BTC price for {date_str}; "
                        "enter the USD value of this deposit manually."
                    ),
                ))
        price = price_cache[date_str]
        if price is not None:
            proposal.cost_basis_usd = (price * proposal.amount).quantize(Decimal("0.01"))
            proposal.basis_autofilled = True


def _proposal_to_out(p: RiverProposal) -> RiverProposalOut:
    return RiverProposalOut(
        row_number=p.row_number,
        date=p.timestamp,
        river_tag=p.river_tag,
        type=p.type,
        from_account=p.from_account,
        to_account=p.to_account,
        amount=p.amount,
        cost_basis_usd=p.cost_basis_usd,
        proceeds_usd=p.proceeds_usd,
        fee_amount=p.fee_amount,
        fee_currency=p.fee_currency,
        source=p.source,
        purpose=p.purpose,
        type_choices=p.type_choices,
        funding_choices=p.funding_choices,
        basis_autofilled=p.basis_autofilled,
        status=p.status,
        matched_tx_id=p.matched_tx_id,
        discrepancy=p.discrepancy,
    )


@router.post("/preview", response_model=RiverPreviewResponse)
async def preview_river_import(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Parse a River bitcoin-activity CSV, map rows to proposed transactions,
    autofill FMV basis for Interest/Income, and mark rows that already
    exist in the ledger. Nothing is written to the database.
    """
    _require_auth(request)

    content = await _read_validated_csv(file)

    rows, errors = parse_river_csv(content)
    proposals, adapt_errors, warnings = adapt_river_rows(rows)
    errors.extend(adapt_errors)

    if len(proposals) > MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many transactions. Maximum is {MAX_ROWS} rows per import.",
        )

    await _autofill_fmv_basis(proposals, warnings)
    annotate_duplicates(proposals, db)

    new_count = sum(1 for p in proposals if p.status == STATUS_NEW)
    matched_count = sum(1 for p in proposals if p.status == STATUS_MATCHED)
    discrepancy_count = sum(1 for p in proposals if p.status == STATUS_DISCREPANCY)

    return RiverPreviewResponse(
        success=len(errors) == 0,
        total_rows=len(rows),
        new_count=new_count,
        matched_count=matched_count,
        discrepancy_count=discrepancy_count,
        proposals=[_proposal_to_out(p) for p in proposals],
        errors=errors,
        warnings=warnings,
    )


@router.post("/execute", response_model=RiverImportResponse)
async def execute_river_import(
    request: Request,
    payload: RiverExecuteRequest,
    db: Session = Depends(get_db),
):
    """
    Import the final (possibly user-edited) rows atomically.

    Every row is re-validated server-side with the same rules as the
    onboarding CSV import, then re-checked against the ledger for exact
    duplicates (double-submit guard). All-or-nothing: any failure rolls
    back the entire batch.
    """
    _require_auth(request)

    if not payload.rows:
        raise HTTPException(status_code=400, detail="No rows to import.")
    if len(payload.rows) > MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many transactions. Maximum is {MAX_ROWS} rows per import.",
        )

    # Re-validate via the battle-tested CSV row validator
    tx_datas = []
    stubs: List[RiverProposal] = []
    all_errors: List[str] = []
    for i, row in enumerate(payload.rows, start=1):
        ts = row.date
        str_row = {
            "date": ts.strftime("%Y-%m-%dT%H:%M:%S%z") if ts.tzinfo else ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "type": row.type,
            "amount": format(
                ledger_amount(row.type, row.amount, row.fee_amount, row.fee_currency), "f"
            ),
            "from_account": row.from_account,
            "to_account": row.to_account,
            "cost_basis_usd": format(row.cost_basis_usd, "f") if row.cost_basis_usd is not None else "",
            "proceeds_usd": format(row.proceeds_usd, "f") if row.proceeds_usd is not None else "",
            "fee_amount": format(row.fee_amount, "f") if row.fee_amount is not None else "",
            "fee_currency": row.fee_currency or "",
            "source": row.source or "",
            "purpose": row.purpose or "",
            "notes": "",
        }
        tx_data, _preview, errors, _warnings = _validate_row(str_row, i)
        if errors:
            all_errors.extend(f"Row {e.row_number}: {e.message}" for e in errors)
            continue
        tx_datas.append(tx_data)
        stubs.append(RiverProposal(
            row_number=i,
            timestamp=tx_data["timestamp"],
            river_tag=None,
            type=tx_data["type"],
            from_account_id=tx_data["from_account_id"],
            to_account_id=tx_data["to_account_id"],
            amount=tx_data["amount"],
            cost_basis_usd=tx_data.get("cost_basis_usd"),
            proceeds_usd=tx_data.get("proceeds_usd"),
        ))

    if all_errors:
        detail = "Rows have errors: " + "; ".join(all_errors[:5])
        if len(all_errors) > 5:
            detail += f" ...and {len(all_errors) - 5} more"
        raise HTTPException(status_code=400, detail=detail)

    # Double-submit guard: skip rows that exactly match an existing tx
    annotate_duplicates(stubs, db, exact_only=True)
    new_tx_datas = [
        tx_data for tx_data, stub in zip(tx_datas, stubs) if stub.status == STATUS_NEW
    ]
    skipped = len(tx_datas) - len(new_tx_datas)

    if not new_tx_datas:
        return RiverImportResponse(
            success=True,
            imported_count=0,
            skipped_existing=skipped,
            message=f"Nothing to import — {skipped} row(s) already exist in the ledger.",
        )

    try:
        imported_count = execute_import(db, new_tx_datas)
    except HTTPException as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Import failed: {exc.detail}. No transactions were saved.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Import failed: {exc}. No transactions were saved.",
        )

    message = f"Imported {imported_count} transaction(s)."
    if skipped:
        message += f" Skipped {skipped} already in the ledger."
    return RiverImportResponse(
        success=True,
        imported_count=imported_count,
        skipped_existing=skipped,
        message=message,
    )
