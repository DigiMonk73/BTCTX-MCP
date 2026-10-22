"""
JSON entry import: preview (dry run) and execute for structured rows.
Mounted at /api/import/entries. Used by the MCP server (mcp_server/) so an
AI assistant can turn pasted text or plain English into ledger entries.

A logged-in session or the AI key (main.get_current_user; the key's
allow-list in services/ai_key.py lists both routes).

The ledger work runs in a worker thread (run_in_threadpool), never on the
event loop: a dry run replays the whole ledger, and on the loop it stopped
the server answering anything else, /api/health included. The endpoints
stay `async` for the one async step, the FMV price fill.

Both hold SQLite's write lock while they work, and the owner's own saves
wait for it only 5 s (sqlite3's timeout) before failing. With the AI key a
request is therefore kept short (_check_ai_request): at most AI_MAX_ROWS
rows, and at most AI_MAX_REPLAYED entries replayed in all, since each row
dated before the ledger's latest entry replays the whole ledger. The body's
size is limited for every route (body_limit.py).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.database import get_db
from backend.models.transaction import Transaction
from backend.services.account import read_book
from backend.services.tax_time import get_tax_timezone
from backend.routers.csv_import import MAX_ROWS
from backend.routers.transaction import _copy_before_ai_changes
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
    WRITABLE_STATUSES,
    PreparedRow,
    autofill_fmv,
    from_price,
    mark_duplicates,
    normalized_view,
    refusal,
    simulate,
    validate_rows,
    writable_now,
    write_rows,
)

router = APIRouter()

# With the AI key: far more than an AI app sends in one call, and under a
# second of work when the rows come after the ledger's latest entry.
AI_MAX_ROWS = 500
# With the AI key: entries replayed in all by the rows dated before the
# ledger's latest entry (each replays the whole ledger, up to 1 ms an entry
# on a laptop). A request then holds the write lock about 1 s, so the
# owner's saves, which wait 5 s for it, go through on a server four times as
# slow (a CI runner, three times as slow, went past 5 s at 2,000).
AI_MAX_REPLAYED = 1000


def _with_ai_key(request: Request) -> bool:
    """No login: the router's get_current_user let the AI key in."""
    return not request.session.get("user_id")


def _check_size(payload: EntryRequest, ai: bool) -> None:
    if not payload.rows:
        raise HTTPException(status_code=400, detail="No rows provided.")
    if len(payload.rows) > MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many transactions. Maximum is {MAX_ROWS} rows per request.",
        )
    if ai and len(payload.rows) > AI_MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many transactions. Maximum is {AI_MAX_ROWS} rows per request with the AI key: "
                   "send them in smaller groups, oldest first. Nothing was saved.",
        )


def _recalculates(prepared: list[PreparedRow], db: Session) -> bool:
    """Whether saving the rows recalculates the whole ledger: one dated
    before the ledger's latest entry does (services/transaction
    _is_backdated), and can move stored figures. The rows are saved oldest
    first, so one can't come before another of the same import."""
    latest = db.query(Transaction).order_by(Transaction.timestamp.desc()).first()
    return latest is not None and any(
        p.tx_data["timestamp"] < latest.timestamp
        for p in prepared if p.tx_data is not None and p.result.status in WRITABLE_STATUSES)


def _copy_if_it_recalculates(rows: list[PreparedRow], db: Session) -> None:
    """The hour's AI copy before rows that recalculate the ledger (#414); a
    copy made this hour already is enough (_copy_before_ai_changes)."""
    if _recalculates(rows, db):
        _copy_before_ai_changes(db, "Not added")


def _check_ai_request(prepared: list[PreparedRow], db: Session) -> None:
    """
    With the AI key, refuse (400) rows that would replay more than
    AI_MAX_REPLAYED entries: each row dated before the ledger's latest entry
    replays the whole ledger with the rows added before it
    (services/transaction.create_transaction_record). One such row is always
    allowed, as for an edit made in BitcoinTX.
    """
    latest = db.query(Transaction).order_by(Transaction.timestamp.desc()).first()
    if latest is None:
        return
    rows = [p for p in prepared if p.tx_data is not None]
    earlier = sum(1 for p in rows if p.tx_data["timestamp"] < latest.timestamp)
    replayed_each = db.query(Transaction).count() + len(rows)  # at most
    at_most = max(1, AI_MAX_REPLAYED // replayed_each)
    if earlier > at_most:
        when = latest.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
        raise HTTPException(
            status_code=400,
            detail=f"Too many rows dated before the ledger's latest entry ({when}) for one request with "
                   f"the AI key: each of them recalculates the whole ledger. Send at most {at_most} of "
                   "them per request, oldest first (rows dated after it don't count). Nothing was saved.",
        )


@router.post("/preview", response_model=EntryPreviewResponse)
async def preview_entries(
    payload: EntryRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Validate rows, autofill FMV-derived USD values, flag duplicates of
    existing transactions, and simulate the write (then roll it back).
    Nothing is saved.
    """
    ai = _with_ai_key(request)
    _check_size(payload, ai)

    prepared = await run_in_threadpool(validate_rows, payload.rows, get_tax_timezone(db), read_book(db))
    if ai:
        await run_in_threadpool(_check_ai_request, prepared, db)
    await autofill_fmv(prepared, db)
    await run_in_threadpool(mark_duplicates, prepared, db)
    affected, balances = await run_in_threadpool(simulate, prepared, db)

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


def _created_answers(created: list[tuple[PreparedRow, Transaction]], db: Session) -> list[CreatedTransaction]:
    """What was saved, in the rows' order, each with the values BitcoinTX
    filled in from a price and that price's hour and source (#208)."""
    years: dict = {}  # the year files, read once for every row
    return [
        CreatedTransaction(
            row=p.row,
            id=tx.id,
            type=tx.type,
            date=tx.timestamp,
            amount=tx.amount,
            realized_gain_usd=tx.realized_gain_usd,
            holding_period=tx.holding_period,
            from_price=from_price(tx, db, years),
        )
        for p, tx in sorted(created, key=lambda c: c[0].row)
    ]


@router.post("/execute", response_model=EntryExecuteResponse)
async def execute_entries(
    payload: EntryRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Write rows atomically. Duplicates of a transaction in the ledger
    (mark_duplicates) are skipped unless the row names the one it isn't
    (not_a_duplicate_of);
    possible duplicates ARE written: the caller is expected to have removed
    any the user rejected after preview.
    Any invalid row or ledger rejection aborts the whole batch. The
    duplicate check and the writes hold one write lock, so a request sent
    again while this one runs finds its rows (#454). With the AI key, rows
    that recalculate the ledger come after the hour's AI copy of the
    database (#414), as an edit, a deletion or Recalculate Ledger do.
    """
    ai = _with_ai_key(request)
    _check_size(payload, ai)

    prepared = await run_in_threadpool(validate_rows, payload.rows, get_tax_timezone(db), read_book(db))
    invalid = [p.result for p in prepared if p.result.status == STATUS_INVALID]
    if invalid:
        raise refusal(invalid)
    if ai:
        await run_in_threadpool(_check_ai_request, prepared, db)

    await autofill_fmv(prepared, db)
    if ai:  # with the lock free, as the copy can take a while
        await run_in_threadpool(lambda: _copy_if_it_recalculates(writable_now(prepared, db), db))

    # The duplicate check and the writes hold one write lock (#454); with the
    # key, a save made before it, of a later row, can make the rows
    # recalculate: their copy is then made under the lock
    copy = (lambda: _copy_if_it_recalculates(prepared, db)) if ai else (lambda: None)
    created = await run_in_threadpool(write_rows, prepared, db, copy)
    skipped = sum(1 for p in prepared if p.result.status == STATUS_DUPLICATE)
    out = await run_in_threadpool(_created_answers, created, db)

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
