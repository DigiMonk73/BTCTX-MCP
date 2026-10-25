"""
Which coins a Transfer moves, shown before it's saved (#706; the owner's
decision, 2026-10-25): the lots its save takes from the From account and
puts in the To account, each with its date acquired, amount and cost, and
the bitcoin its network fee disposes of. They're the save's own: the write
is made on a scratch copy of the ledger by the path its save takes
(past_years.Write.apply), so a backdated transfer, which replays the
ledger, and an edit list what their save will do. The oldest coins in the
account go first: the IRS default when the units aren't identified (Treas.
Reg. §1.1012-1(j)), and the only way BitcoinTX takes them.
"""

import time
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.database import scratch_copy
from backend.models.transaction import BitcoinLot, LotDisposal, Transaction
from backend.services import past_years, tax_time
from backend.services import transaction as tx_service

ONLY_A_TRANSFER = "Only a Transfer moves coins between your accounts."
TOO_SLOW = "BitcoinTX couldn't work out quickly enough here which coins move."


def coins_moved(write: past_years.Write, db: Session) -> dict:
    """
    {"coins", "fee_btc", "detail"}: the lots `write` would put in its To
    account, in the order its save takes them ({"acquired", "btc",
    "cost_usd", "inherited"} each), and the bitcoin its fee disposes of.
    Past the past-year dry run's time budget, coins and fee_btc are None and
    detail says why. A write its save would refuse raises that refusal.
    Nothing is saved: the prices it needs are kept, as the save keeps them.
    """
    tx_service.find_prices_first(db, write.priced_rows(db))
    try:
        with scratch_copy(db) as scratch:
            scratch.info[tx_service.DEADLINE] = time.monotonic() + past_years.DRY_RUN_SECONDS
            moved = write.apply(scratch)
            scratch.flush()
            return _what_moved(moved, scratch)
    except tx_service.OutOfTime:
        return {"coins": None, "fee_btc": None, "detail": TOO_SLOW}


def _what_moved(tx: Transaction, db: Session) -> dict:
    if tx.type != "Transfer":
        raise HTTPException(status_code=422, detail=ONLY_A_TRANSFER)
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
