"""
Which coins a transaction moves, shown before it's saved (#706; the owner's
decision, 2026-10-25), and what the form's coin picker chooses from (#711):
a Transfer's lots its save takes from the From account and puts in the To
account, or the coins a bitcoin Withdrawal from one of your wallets
disposes of, each with its date acquired, amount and cost, and the bitcoin
its network fee disposes of. They're the save's own: the write is made on a
scratch copy of the ledger by the path its save takes
(past_years.Write.apply), with the body the save is sent, so a backdated
transaction, which replays the ledger, an edit, and a choice of coins list
what their save will do. Without a choice, the oldest coins in the account
go first: the IRS default when the units aren't identified (Treas. Reg.
§1.1012-1(j)).

Leaving one of your wallets, the answer also gives `held`: what the wallet
holds when the transaction comes, before it takes any, one line per
acquisition, heard from the engine as the save's path posts the
transaction's lots (chosen_coins.HELD_HOOK), so the picker, the list and
the save can't disagree.
"""

import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.database import scratch_copy
from backend.models.transaction import BitcoinLot, LotDisposal, Transaction
from backend.services import chosen_coins, past_years, tax_time
from backend.services import transaction as tx_service
from backend.services.account import AccountBook, account_book

NOT_LISTED = "Only a Transfer, or a bitcoin Withdrawal from one of your wallets, lists the coins that leave."
NOT_FOUND = "Transaction not found."
TOO_SLOW = "BitcoinTX couldn't work out in time which coins move. Saving isn't affected."
# Seen only by a form whose list another window asked for after it
ASKED_AGAIN = "A newer list was asked for meanwhile, perhaps in another window: change the transfer to ask again."

# The lists asked for, numbered. BitcoinTX has one user, typing in one form
# at a time: a list asked for before the newest is one the form gave up on
# (its request cancelled in the browser, which a route like this never
# hears of), so its replay stops and leaves the time to the newest's
_asked = 0
_asked_lock = threading.Lock()


def coins_moved(write: past_years.Write, db: Session) -> dict:
    """
    {"coins", "fee_btc", "detail", "held", "dated_today"}: what `write`
    takes from its From account in the order its save takes it (a
    Transfer's lots put in its To account; a Withdrawal's coins disposed
    of, its fee's apart), each {"acquired", "btc", "cost_usd", "inherited",
    "acquired_txn_id"}; the bitcoin its fee disposes of; from a wallet,
    what the wallet held then (else None); and whether it's dated today in
    the tax timezone. Past the past-year dry run's time budget, or once a
    newer list is asked for, coins, fee_btc and held are None and detail
    says which. A choice its wallet doesn't hold then gives no coins, the
    reason, and what it holds. Any other refusal of its save is raised.
    Nothing is saved: the prices it needs are kept, as the save keeps them.
    """
    _check_listed(write, db)
    superseded = _newest_from_now()
    today = _dated_today(write, db)
    tx_service.find_prices_first(db, write.priced_rows(db))
    try:
        with scratch_copy(db) as scratch:
            scratch.info[tx_service.DEADLINE] = time.monotonic() + past_years.DRY_RUN_SECONDS
            scratch.info[tx_service.SUPERSEDED] = superseded
            heard: dict[int, list[chosen_coins.Held]] = {}
            scratch.info[chosen_coins.HELD_HOOK] = lambda tx, held: heard.__setitem__(tx.id, held)
            if chosen_coins.lots_lack_acquisition(scratch):
                tx_service.recalculate_all_transactions(scratch)  # every lot learns its acquisition (#711)
            try:
                moved = write.apply(scratch)
            except chosen_coins.NotHeldHere as e:
                tx = scratch.get(Transaction, e.tx_id)
                return {"coins": None, "fee_btc": None, "detail": e.detail,
                        "held": _held(tx, heard.get(e.tx_id, []), scratch), "dated_today": today}
            if moved is None:  # deleted meanwhile
                raise HTTPException(status_code=404, detail=NOT_FOUND)
            scratch.flush()
            return {**_what_moved(moved, scratch), "held": _held(moved, heard.get(moved.id, []), scratch),
                    "dated_today": today}
    except tx_service.OutOfTime:
        return {"coins": None, "fee_btc": None, "detail": ASKED_AGAIN if superseded() else TOO_SLOW, "held": None,
                "dated_today": today}


def _check_listed(write: past_years.Write, db: Session) -> None:
    """A Transfer, or a Withdrawal from one of your wallets, as sent or, for
    an edit that doesn't send its type or account, as saved; asked before
    the replay, which another would make for nothing. 404 for an edit of a
    row that isn't there."""
    stored = db.get(Transaction, write.tx_id) if write.kind == past_years.EDIT else None
    if write.kind == past_years.EDIT and stored is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    kind = write.data.get("type") or stored.type
    kind = getattr(kind, "value", kind)
    from_id = write.data.get("from_account_id", getattr(stored, "from_account_id", None))
    if kind == "Transfer" or (kind == "Withdrawal" and account_book(db).kind(from_id) == "wallet"):
        return
    raise HTTPException(status_code=422, detail=NOT_LISTED)


def _dated_today(write: past_years.Write, db: Session) -> bool:
    """Whether its date is today in the tax timezone: only then may the
    picker offer to fill the highest-cost coins first (the owner's Q3), so
    the form never hands out a choice made after the coins left."""
    stored = db.get(Transaction, write.tx_id) if write.kind == past_years.EDIT else None
    when = write.data.get("timestamp") or getattr(stored, "timestamp", None)
    if when is None:
        return False
    tz = tax_time.get_tax_timezone(db)
    try:
        return tax_time.local_date(when, tz) == tax_time.local_date(datetime.now(timezone.utc), tz)
    except tax_time.DateOutOfRange:
        return False


def _newest_from_now() -> Callable[[], bool]:
    """This list as the newest asked for: whether another has been since."""
    global _asked
    with _asked_lock:
        _asked += 1
        mine = _asked
    return lambda: _asked != mine


def _what_moved(tx: Transaction, db: Session) -> dict:
    tz = tax_time.get_tax_timezone(db)
    fee = db.query(LotDisposal).filter(LotDisposal.transaction_id == tx.id, LotDisposal.is_fee).all()
    if tx.type == "Transfer":
        lots = db.query(BitcoinLot).filter(BitcoinLot.created_txn_id == tx.id).order_by(BitcoinLot.id).all()
        coins = [_coin(lot, lot.total_btc, lot.cost_basis_usd, tz) for lot in lots]
    else:
        pieces = (db.query(LotDisposal).filter(LotDisposal.transaction_id == tx.id, LotDisposal.is_fee.is_(False))
                  .order_by(LotDisposal.id).all())
        coins = [_coin(piece.lot, piece.disposed_btc, piece.disposal_basis_usd, tz) for piece in pieces]
    return {
        "coins": coins,
        "fee_btc": f"{sum((Decimal(part.disposed_btc) for part in fee), Decimal(0)):.8f}",
        "detail": None,
    }


def _coin(lot: BitcoinLot, btc, cost, tz) -> dict:
    """A piece as the list shows it: the date acquired in the tax timezone, as Form 8949 prints it."""
    return {
        "acquired": tax_time.local_date(lot.acquired_date, tz).isoformat(),
        "btc": f"{Decimal(btc):.8f}",
        "cost_usd": f"{Decimal(cost):.2f}",
        "inherited": bool(lot.inherited),
        "acquired_txn_id": lot.acquired_txn_id,
    }


def _held(tx: Transaction, lines: list[chosen_coins.Held], db: Session) -> list[dict] | None:
    """What a wallet held when `tx` came, before it took any, oldest first:
    each acquisition, how and where it was acquired, its coins' date, BTC
    and cost, the term they'd have on tx's date, and what oldest first
    would take of them. None when tx doesn't leave one of your wallets (an
    exchange's coins leave oldest first, as its Form 1099-DA reports them),
    or moves within one (a consolidation records only its fee, oldest
    first)."""
    book = account_book(db)
    if book.kind(tx.from_account_id) != "wallet" or tx.from_account_id == tx.to_account_id:
        return None
    tz = tax_time.get_tax_timezone(db)
    acquisitions = {t.id: t for t in db.query(Transaction).filter(
        Transaction.id.in_([line.acquired_txn_id for line in lines if line.acquired_txn_id is not None]))}
    return [_held_line(line, acquisitions.get(line.acquired_txn_id), tx, tz, book) for line in lines]


def _held_line(line: chosen_coins.Held, acquired_by: Transaction | None, tx: Transaction, tz,
               book: AccountBook) -> dict:
    term = "LONG" if line.inherited else tx_service.holding_period(line.acquired, tx.timestamp, tz)
    return {
        "acquired_txn_id": line.acquired_txn_id,
        "kind": getattr(acquired_by, "type", None),
        "source": tx_service.listed_spelling(acquired_by.source, tx_service.DEPOSIT_SOURCES)
        if acquired_by is not None and acquired_by.type == "Deposit" else None,
        "account": book.name(acquired_by.to_account_id) if acquired_by is not None else None,
        "date": tax_time.local_date(acquired_by.timestamp, tz).isoformat() if acquired_by is not None else None,
        "acquired": tax_time.local_date(line.acquired, tz).isoformat(),
        "inherited": line.inherited,
        "btc": f"{line.btc:.8f}",
        "cost_usd": f"{line.cost_usd:.2f}",
        "term": term,
        "oldest_first": f"{line.oldest_first:.8f}",
    }
