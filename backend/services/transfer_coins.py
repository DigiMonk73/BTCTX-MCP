"""
Which coins a Transfer moves, shown before it's saved (#706; the owner's
decision, 2026-10-25): the lots its save takes from the From account and
puts in the To account, each with its date acquired, amount and cost, and
the bitcoin its network fee disposes of. They're the save's own: the write
is made on a scratch copy of the ledger by the path its save takes
(past_years.Write.apply), with the body the save is sent, so a backdated
transfer, which replays the ledger, and an edit list what their save will
do, and so will a transfer that names the coins it moves once the save takes
such a choice (#711). Without one, the oldest coins in the account go first:
the IRS default when the units aren't identified (Treas. Reg.
§1.1012-1(j)).
"""

import threading
import time
from collections.abc import Callable
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.database import scratch_copy
from backend.models.transaction import BitcoinLot, LotDisposal, Transaction
from backend.services import past_years, tax_time
from backend.services import transaction as tx_service

ONLY_A_TRANSFER = "Only a Transfer moves coins between your accounts."
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
    {"coins", "fee_btc", "detail"}: the lots `write` would put in its To
    account, in the order its save takes them ({"acquired", "btc",
    "cost_usd", "inherited"} each), and the bitcoin its fee disposes of.
    Past the past-year dry run's time budget, or once a newer list is asked
    for, coins and fee_btc are None and detail says which. A write its save
    would refuse raises that refusal. Nothing is saved: the prices it needs
    are kept, as the save keeps them.
    """
    _check_a_transfer(write, db)
    superseded = _newest_from_now()
    tx_service.find_prices_first(db, write.priced_rows(db))
    try:
        with scratch_copy(db) as scratch:
            scratch.info[tx_service.DEADLINE] = time.monotonic() + past_years.DRY_RUN_SECONDS
            scratch.info[tx_service.SUPERSEDED] = superseded
            moved = write.apply(scratch)
            if moved is None:  # deleted meanwhile
                raise HTTPException(status_code=404, detail=NOT_FOUND)
            scratch.flush()
            return _what_moved(moved, scratch)
    except tx_service.OutOfTime:
        return {"coins": None, "fee_btc": None, "detail": ASKED_AGAIN if superseded() else TOO_SLOW}


def _check_a_transfer(write: past_years.Write, db: Session) -> None:
    """A Transfer, as sent or, for an edit that doesn't send its type, as
    saved; asked before the replay, which another type would make for
    nothing. 404 for an edit of a row that isn't there."""
    stored = db.get(Transaction, write.tx_id) if write.kind == past_years.EDIT else None
    if write.kind == past_years.EDIT and stored is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    sent = write.data.get("type") or stored.type
    if getattr(sent, "value", sent) != "Transfer":
        raise HTTPException(status_code=422, detail=ONLY_A_TRANSFER)


def _newest_from_now() -> Callable[[], bool]:
    """This list as the newest asked for: whether another has been since."""
    global _asked
    with _asked_lock:
        _asked += 1
        mine = _asked
    return lambda: _asked != mine


def _what_moved(tx: Transaction, db: Session) -> dict:
    tz = tax_time.get_tax_timezone(db)
    lots = db.query(BitcoinLot).filter(BitcoinLot.created_txn_id == tx.id).order_by(BitcoinLot.id).all()
    fee = db.query(LotDisposal).filter(LotDisposal.transaction_id == tx.id, LotDisposal.is_fee).all()
    return {
        "coins": [_coin(lot, tz) for lot in lots],
        "fee_btc": f"{sum((Decimal(part.disposed_btc) for part in fee), Decimal(0)):.8f}",
        "detail": None,
    }


def _coin(lot: BitcoinLot, tz) -> dict:
    """A lot as the list shows it: the date acquired in the tax timezone, as Form 8949 prints it."""
    return {
        "acquired": tax_time.local_date(lot.acquired_date, tz).isoformat(),
        "btc": f"{Decimal(lot.total_btc):.8f}",
        "cost_usd": f"{Decimal(lot.cost_basis_usd):.2f}",
        "inherited": bool(lot.inherited),
    }
