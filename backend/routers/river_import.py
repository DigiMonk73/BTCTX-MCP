"""
API endpoints for importing River bitcoin-activity CSV exports into a live
ledger (merge with dedup). See docs/archive/RIVER_IMPORT_PLAN.md.

Unlike /api/import (the onboarding CSV import, which requires an empty
database), this flow is designed for ongoing incremental imports.
"""

from __future__ import annotations

import logging
from datetime import timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from backend.constants import ACCOUNT_EXTERNAL, ACCOUNT_NAME_TO_ID
from backend.database import get_db
from backend.routers.csv_import import MAX_ROWS, _read_validated_csv, _require_auth
from backend.schemas.river_import import (
    RiverExecuteRequest,
    RiverExecuteRow,
    RiverImportResponse,
    RiverPreviewResponse,
    RiverProposalOut,
)
from backend.schemas.csv_import import CSVParseError
from backend.services import hourly_prices
from backend.services.csv_import import _validate_row, execute_import, number_text
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


def _autofill_fmv_basis(
    proposals: list[RiverProposal], warnings: list[CSVParseError], db: Session
) -> None:
    """
    Prefill cost_basis_usd (fair market value at receipt) on Deposit
    proposals (Interest/Income) at the BTC price of their hour (else their
    day: services/hourly_prices.py). Degrades gracefully: on lookup failure
    the basis stays blank and a warning tells the user to fill it in.
    """
    price_cache: dict[int, hourly_prices.Priced | None] = {}

    for proposal in proposals:
        if proposal.type != "Deposit" or proposal.cost_basis_usd is not None:
            continue
        hour = hourly_prices.hour_of(proposal.timestamp)
        if hour not in price_cache:
            try:
                price_cache[hour] = hourly_prices.price_at(db, proposal.timestamp)
            except Exception as exc:
                price_cache[hour] = None
                # The time (a transaction's) only in the DEBUG log
                logger.warning("FMV lookup failed (%s)", type(exc).__name__)
                logger.debug("FMV lookup failed for %s: %s", proposal.timestamp, exc)
                warnings.append(CSVParseError(
                    row_number=proposal.row_number, column="cost_basis_usd",
                    severity="warning",
                    message=(
                        f"Could not fetch the BTC price for {proposal.timestamp:%Y-%m-%d %H:00} UTC; "
                        "enter the USD value of this deposit manually."
                    ),
                ))
        priced = price_cache[hour]
        if priced is not None:
            proposal.cost_basis_usd = (priced.usd * proposal.amount).quantize(Decimal("0.01"))
            proposal.basis_autofilled = True
            proposal.price_moment = priced.moment


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
        price_moment=p.price_moment,
        status=p.status,
        matched_tx_id=p.matched_tx_id,
        discrepancy=p.discrepancy,
        near_amount=p.near_amount,
    )


@router.post("/preview", response_model=RiverPreviewResponse)
def preview_river_import(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Parse a River bitcoin-activity CSV, map rows to proposed transactions,
    autofill FMV basis for Interest/Income, and mark rows that already
    exist in the ledger. Nothing is written to the database.

    Both endpoints here are plain `def`: FastAPI runs them in a worker
    thread, so their ledger work never stops the server answering others.
    """
    _require_auth(request)

    content = _read_validated_csv(file)

    rows, errors = parse_river_csv(content)
    proposals, adapt_errors, warnings = adapt_river_rows(rows)
    errors.extend(adapt_errors)

    if len(proposals) > MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many transactions. Maximum is {MAX_ROWS} rows per import.",
        )

    _autofill_fmv_basis(proposals, warnings, db)
    db.commit()  # keep the prices it looked up (nothing else is written)
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
def execute_river_import(
    request: Request,
    payload: RiverExecuteRequest,
    db: Session = Depends(get_db),
):
    """
    Import the final (possibly user-edited) rows atomically.

    Every row is re-validated server-side with the same rules as the
    onboarding CSV import, then re-checked against the ledger for
    duplicates (double-submit guard), except a row the owner ticked though
    the preview found it in the ledger (not_a_duplicate, #253); a row it
    found there and the owner left unticked (left_out) is checked, never
    imported. All-or-nothing: any failure rolls back the entire batch.
    """
    _require_auth(request)

    kept = [row for row in payload.rows if not row.left_out]
    if not kept:
        raise HTTPException(status_code=400, detail="No rows to import.")
    if len(payload.rows) > MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many transactions. Maximum is {MAX_ROWS} rows per import.",
        )

    new_tx_datas = _rows_to_import(payload.rows, db)
    skipped = len(kept) - len(new_tx_datas)

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


def _rows_to_import(rows: list[RiverExecuteRow], db: Session) -> list[dict]:
    """The checked rows to import. Every row the preview found in the ledger,
    a ticked one and one left out alike, is matched first, so it takes its
    match as in the preview whatever the owner edited (#253); then the ones
    not in the ledger, and those the owner ticked though they are, are
    imported."""
    tx_datas = iter(_validated_rows([row for row in rows if not row.left_out]))
    checked = [(None if row.left_out else next(tx_datas), row) for row in rows]
    stubs = [
        _left_out_stub(i, row) if tx_data is None else _stub(i, tx_data, row)
        for i, (tx_data, row) in enumerate(checked, start=1)
    ]
    annotate_duplicates(stubs, db, exact_only=True)
    return [
        tx_data for (tx_data, row), stub in zip(checked, stubs)
        if tx_data is not None and (stub.status == STATUS_NEW or row.not_a_duplicate)
    ]


def _validated_rows(rows: list[RiverExecuteRow]) -> list[dict]:
    """Each row checked by the CSV import's row check, then a Transfer's
    amount given its BTC fee (BitcoinTX's meaning), once both are known to
    be numbers within their limits; 400 listing the first five errors when
    any row has one."""
    tx_datas = []
    all_errors: list[str] = []
    for i, row in enumerate(rows, start=1):
        tx_data, _preview, errors, _warnings = _validate_row(_csv_row(row), i)
        if errors:
            all_errors.extend(f"Row {e.row_number}: {e.message}" for e in errors)
        else:
            tx_data["amount"] = ledger_amount(tx_data["type"], tx_data["amount"], row.fee_amount, row.fee_currency)
            tx_datas.append(tx_data)
    if all_errors:
        detail = "Rows have errors: " + "; ".join(all_errors[:5])
        if len(all_errors) > 5:
            detail += f" ...and {len(all_errors) - 5} more"
        raise HTTPException(status_code=400, detail=detail)
    return tx_datas


def _csv_row(row: RiverExecuteRow) -> dict[str, str]:
    """A row as the CSV import reads it: text, River's own amounts."""
    ts = row.date
    return {
        "date": ts.strftime("%Y-%m-%dT%H:%M:%S%z") if ts.tzinfo else ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "type": row.type,
        "amount": number_text(row.amount),
        "from_account": row.from_account,
        "to_account": row.to_account,
        "cost_basis_usd": number_text(row.cost_basis_usd),
        "proceeds_usd": number_text(row.proceeds_usd),
        "fee_amount": number_text(row.fee_amount),
        "fee_currency": row.fee_currency or "",
        "source": row.source or "",
        "purpose": row.purpose or "",
        "notes": "",
        "cost_basis_typed": row.cost_basis_typed or "",
        "price_moment": (row.price_moment or "") if row.cost_basis_typed == "no" else "",
    }


def _stub(row_number: int, tx_data: dict, row: RiverExecuteRow) -> RiverProposal:
    """A checked row in the shape the duplicate check reads: River's amount
    and fee, as the preview's proposal had them."""
    return RiverProposal(
        row_number=row_number,
        timestamp=tx_data["timestamp"],
        river_tag=None,
        type=tx_data["type"],
        from_account_id=tx_data["from_account_id"],
        to_account_id=tx_data["to_account_id"],
        amount=row.amount,
        cost_basis_usd=tx_data.get("cost_basis_usd"),
        proceeds_usd=tx_data.get("proceeds_usd"),
        fee_amount=row.fee_amount,
        fee_currency=row.fee_currency,
        matched_before=row.not_a_duplicate,
    )


def _left_out_stub(row_number: int, row: RiverExecuteRow) -> RiverProposal:
    """A row left out, in the same shape: the preview's own (the River screen
    sends it unedited), so it isn't validated (a row the owner doesn't
    import can't stop the import)."""
    ts = row.date if row.date.tzinfo else row.date.replace(tzinfo=timezone.utc)
    return RiverProposal(
        row_number=row_number,
        timestamp=ts.astimezone(timezone.utc),
        river_tag=None,
        type=row.type,
        from_account_id=ACCOUNT_NAME_TO_ID.get(row.from_account.lower(), ACCOUNT_EXTERNAL),
        to_account_id=ACCOUNT_NAME_TO_ID.get(row.to_account.lower(), ACCOUNT_EXTERNAL),
        amount=row.amount,
        fee_amount=row.fee_amount,
        fee_currency=row.fee_currency,
        matched_before=True,
    )
