"""
The transactions: list, read, create, edit and delete them, and recalculate
the whole ledger (services/transaction.py does the work). Timestamps go out
in UTC with a 'Z'.
"""

import logging
import sqlite3
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from backend.schemas.transaction import (
    TransactionCreate,
    TransactionUpdate,
    TransactionRead
)
from backend.services import past_years
from backend.services.past_year_writes import Recalculation
from backend.services import transaction as tx_service
from backend.services import chosen_coins, transfer_coins, wipe
from backend.services.account import account_book
from backend.database import get_db
from backend.migrate import AI_CHANGE_LABEL, AI_COPIES_KEPT, backup_copies, backup_sqlite, sqlite_file

logger = logging.getLogger(__name__)

router = APIRouter(tags=["transactions"])

AI_CHANGE_COPY_EVERY = 3600  # seconds
_now = time.time  # tests move the clock
# One copy at a time (BitcoinTX runs one server process): a change that
# comes while the copy is being written waits for it, then finds it.
_ai_change_copy = threading.Lock()


def _attach_utc_and_build_read_model(tx, db: Session, years: dict | None = None) -> TransactionRead:
    """The transaction as TransactionRead, its UTC times written with 'Z'
    rather than '+00:00', which values BitcoinTX filled in from a price, and
    the stored price they came from (price_used; read only, never asked for)."""
    pyd_model = TransactionRead.model_validate(tx)
    data = pyd_model.model_dump()
    data["values_from_price"] = tx_service.values_from_price(tx, account_book(db))
    data["price_used"] = tx_service.price_used(tx, db, years)

    for field in ["timestamp", "created_at", "updated_at", "coins_chosen_at"]:
        val = data.get(field)
        if isinstance(val, datetime):
            iso_str = val.isoformat()
            if iso_str.endswith("+00:00"):
                iso_str = iso_str[:-6] + "Z"
            data[field] = iso_str

    return TransactionRead(**data)


@router.get("", response_model=list[TransactionRead])
def list_transactions(db: Session = Depends(get_db)):
    """Every transaction, newest first."""
    raw_txs = tx_service.get_all_transactions(db)
    years: dict = {}  # the year files, read once for the whole list
    return [_attach_utc_and_build_read_model(tx, db, years) for tx in raw_txs]


def _require_login_to_delete_all(request: Request) -> None:
    if not request.session.get("user_id"):  # never the AI key
        raise HTTPException(status_code=403, detail="Deleting everything needs a login.")


@router.get("/delete_all")
def what_delete_all_deletes(request: Request, db: Session = Depends(get_db)):
    """What Delete All would delete, for its dialog: {"transactions",
    "first_year", "last_year"} (tax years). Login only."""
    _require_login_to_delete_all(request)
    return wipe.extent(db)


@router.get("/{tx_id}", response_model=TransactionRead)
def get_transaction(tx_id: int, db: Session = Depends(get_db)):
    """One transaction, or 404."""
    tx = tx_service.get_transaction_by_id(db, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    final_model = _attach_utc_and_build_read_model(tx, db)
    return final_model


@router.post("", response_model=TransactionRead)
def create_transaction(tx: TransactionCreate, request: Request, confirm: str | None = None,
                       db: Session = Depends(get_db)):
    """
    Save a new transaction with its ledger lines and its lots or lot
    disposals; one dated before others recalculates the ledger. One that
    changes the figures of an earlier tax year answers 409 with the years,
    what changes and a fingerprint, and saves nothing until sent again with
    ?confirm=<fingerprint>; a copy of the database comes first.
    """
    write = past_years.Write(past_years.ADD, tx.model_dump())
    new_tx = past_years.save(write, db, confirm, by_ai=_by_ai(request))
    if isinstance(new_tx, JSONResponse):
        return new_tx  # the warning
    if not new_tx:
        raise HTTPException(status_code=400, detail="Transaction creation failed.")
    return _attach_utc_and_build_read_model(new_tx, db)


def _require_login_to_list_coins(request: Request) -> None:
    if not request.session.get("user_id"):  # never the AI key
        raise HTTPException(status_code=403, detail="Listing the coins a Transfer moves needs a login.")


@router.post("/coins-moved")
def coins_a_new_transfer_moves(tx: TransactionCreate, request: Request, db: Session = Depends(get_db)):
    """
    Which coins a new Transfer would move, as its save would move them
    (#706), given the body its save is sent: the lots it would put in its
    To account, in the order its save takes them, each with its date
    acquired, amount and cost, and the bitcoin its network fee disposes of.
    Saves nothing; one its save would refuse answers that refusal. Login
    only (never the AI key).
    """
    _require_login_to_list_coins(request)
    return transfer_coins.coins_moved(past_years.Write(past_years.ADD, tx.model_dump()), db)


@router.post("/{transaction_id}/coins-moved")
def coins_an_edited_transfer_moves(transaction_id: int, tx: TransactionUpdate, request: Request,
                                   db: Session = Depends(get_db)):
    """Which coins a Transfer would move with this edit, as its save would
    (#706); as for a new one. 404 when the transaction doesn't exist."""
    _require_login_to_list_coins(request)
    write = past_years.Write(past_years.EDIT, tx.model_dump(exclude_unset=True), transaction_id)
    return transfer_coins.coins_moved(write, db)


@router.post("/recalculate")
def recalculate_ledger(request: Request, confirm: str | None = None, db: Session = Depends(get_db)):
    """
    Rebuild every ledger line, lot and disposal from the transactions in
    chronological order (the same "scorched earth" pass edits trigger).
    Run once after upgrading so calculation fixes reach existing data.
    With the AI key, one that would change the figures of an earlier tax
    year answers 409 with the years, what changes (as pending) and a
    fingerprint, and changes nothing until sent again with
    ?confirm=<fingerprint>, after a fresh AI copy of the database; its
    first change in an hour otherwise comes after an AI copy (#336). With a
    login it's the owner's own fix, and never asks.
    """
    try:
        if _by_ai(request):
            done = past_years.save(Recalculation(), db, confirm, True, _ai_copy_first(db, True, "Not recalculated"))
            if isinstance(done, JSONResponse):
                return done  # the warning
        else:
            tx_service.recalculate_ledger(db)
    except Exception:
        db.rollback()
        raise
    count = len(tx_service.get_all_transactions(db))
    return {"detail": f"Recalculated {count} transaction(s).", "transactions": count}


@router.put("/{transaction_id}", response_model=TransactionRead)
def update_transaction(transaction_id: int, tx: TransactionUpdate, request: Request, confirm: str | None = None,
                       db: Session = Depends(get_db)):
    """
    Change the fields given, then recalculate the whole ledger. 404 when the
    transaction doesn't exist. One that changes the figures of an earlier
    tax year answers 409 with the years, what changes and a fingerprint, and
    saves nothing until sent again with ?confirm=<fingerprint>; a copy of
    the database comes first. With the AI key, its first change in an hour
    (an edit, a deletion, a recalculation, or an import that recalculates)
    comes after an AI copy of the database.
    """
    if not tx_service.get_transaction_by_id(db, transaction_id):
        raise HTTPException(status_code=404, detail="Transaction not found.")
    by_ai = _by_ai(request)
    _refuse_a_choice_from_the_ai(tx, by_ai)
    write = past_years.Write(past_years.EDIT, tx.model_dump(exclude_unset=True), transaction_id)
    try:
        updated_tx = past_years.save(write, db, confirm, by_ai, _ai_copy_first(db, by_ai, "Not changed"))
    except chosen_coins.SendAgain as e:
        raise (e.for_the_ai() if by_ai else e) from None
    if isinstance(updated_tx, JSONResponse):
        return updated_tx  # the warning
    if not updated_tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return _attach_utc_and_build_read_model(updated_tx, db)


@router.delete("/delete_all", status_code=204)
def delete_all_transactions_endpoint(
    request: Request, confirm: str | None = None, transactions: int | None = None, first_year: int | None = None,
    last_year: int | None = None, db: Session = Depends(get_db),
):
    """
    Delete every transaction with its ledger lines, lots and disposals, only
    with confirm=DELETE (typed in the dialog, #256) and, when given, while
    the ledger has the transactions and tax years the dialog showed (#377):
    otherwise 409 says what would go now, and nothing is deleted. A copy of
    the database comes first (backups/, "before-delete"). Login only (never
    the AI key).
    """
    _require_login_to_delete_all(request)
    shown = {"transactions": transactions, "first_year": first_year, "last_year": last_year}
    # The 409, or 204 No Content: what went is what the dialog showed.
    return wipe.delete_all(db, confirm, shown)


@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: int, request: Request, confirm: str | None = None,
                       db: Session = Depends(get_db)):
    """
    Delete one transaction and recalculate the ledger. 404 when it doesn't
    exist; refused, changing nothing, when later transactions need its BTC.
    One that changes the figures of an earlier tax year answers 409 with the
    years, what changes and a fingerprint, and deletes nothing until sent
    again with ?confirm=<fingerprint>; a copy of the database comes first.
    With the AI key, its first change in an hour (an edit, a deletion, a
    recalculation, or an import that recalculates) comes after an AI copy of
    the database (in the backups folder).
    """
    if not tx_service.get_transaction_by_id(db, transaction_id):
        raise HTTPException(status_code=404, detail="Transaction not found.")
    by_ai = _by_ai(request)
    write = past_years.Write(past_years.DELETE, tx_id=transaction_id)
    success = past_years.save(write, db, confirm, by_ai, _ai_copy_first(db, by_ai, "Not deleted"))
    if isinstance(success, JSONResponse):
        return success  # the warning
    if not success:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return


def _by_ai(request: Request) -> bool:
    return not request.session.get("user_id")  # else the AI key: a route on AI_KEY_ROUTES


def _refuse_a_choice_from_the_ai(tx: TransactionUpdate, by_ai: bool) -> None:
    """The AI connector can't choose coins yet (#711, Q4: it comes with the
    connector's own step), nor set a choice back to oldest first: any
    chosen_coins its edit sends, a list or null, is refused before anything
    runs. (It adds through the entry import, which refuses them too.)"""
    if by_ai and "chosen_coins" in tx.model_fields_set:
        raise HTTPException(status_code=422, detail=chosen_coins.AI_CANT_CHOOSE)


def _ai_copy_first(db: Session, by_ai: bool, refused: str):
    """What a save made as it always was runs first: with the AI key, its
    hourly copy (_copy_before_ai_changes). A confirmed save makes its own."""
    return (lambda: _copy_before_ai_changes(db, refused)) if by_ai else (lambda: None)


def _made_this_hour_today(made: float) -> bool:
    """A copy less than an hour old, made on today's UTC day: a change just
    after midnight still gets the new day's first copy (the one
    migrate._ai_copies_held keeps for the week)."""
    now = _now()
    today = datetime.fromtimestamp(now, timezone.utc).date()
    return now - made < AI_CHANGE_COPY_EVERY and datetime.fromtimestamp(made, timezone.utc).date() == today


def _copy_before_ai_changes(db: Session, refused: str) -> None:
    """
    An AI copy before the AI key's first change in an hour (an edit, a
    deletion, a recalculation, or an import that recalculates: also
    routers/entry_import), which the AI copies the key asks for next never
    push out (migrate._ai_copies_held). No copy, no change: `refused` ("Not
    changed", "Not deleted", "Not recalculated", "Not added") opens the
    message.
    """
    db_path = sqlite_file(db.get_bind())
    if db_path is None:
        return
    with _ai_change_copy:
        newest = backup_copies(db_path, "ai", label=AI_CHANGE_LABEL)
        if newest and _made_this_hour_today(newest[0].stat().st_mtime):
            return
        try:
            dest = backup_sqlite(db_path, AI_CHANGE_LABEL, kind="ai", keep=AI_COPIES_KEPT)
        except (OSError, sqlite3.Error) as e:
            logger.error("No AI copy before a change (%s): the change was refused", type(e).__name__)
            raise HTTPException(
                status_code=500, detail=f"{refused}: BitcoinTX couldn't make its copy of the database first."
            ) from e
    logger.info("AI backup copy made before a change: %s", dest.name)
