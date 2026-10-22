"""
The rows from before 0.9.2 (spec 5.3, 5.13; the owner's decision S7): a
transaction naming an account made through 1.x's account API (an id from 7
to 98) could be saved only before v0.9.2. 1.x's checks by number left such
rows out of income and the like; 2.0 counts them by their account's currency,
so Ledger Review lists them (account_from_before_0_9_2) until the owner has
looked at each.

The list is the ledger's own, written once (`accounts_old_rows` in
app_settings, the ids as JSON): once the gate opens (B7a) new rows can be
saved into those accounts, and they aren't from before 0.9.2. Saving a row on
it, even unchanged, or deleting it takes it off. Not by updated_at: a
recalculation moves that (#333's review).
"""

import json

from sqlalchemy.orm import Session

from backend.models.account import Account
from backend.models.app_setting import AppSetting, save_setting
from backend.models.transaction import Transaction

KEY = "accounts_old_rows"
# The ids 1.x's account API gave: after the fixed accounts, before External
OLD_IDS = range(7, 99)


def old_accounts(db: Session) -> set[int]:
    """The accounts made through 1.x's account API that exist."""
    return {account_id for (account_id,) in db.query(Account.id).filter(Account.id.in_(OLD_IDS))}


def note_once(db: Session) -> None:
    """Write the list when the ledger has none: at the first 2.0 start, and
    after a restore of a 1.x backup (a 2.0 backup brings its own, which
    the restore keeps). The caller commits."""
    if db.get(AppSetting, KEY) is not None:
        return
    old = old_accounts(db)
    # An empty set is not an IN (): a ledger with none of these accounts stores []
    ids = [
        tx_id
        for (tx_id,) in db.query(Transaction.id)
        .filter(Transaction.from_account_id.in_(old) | Transaction.to_account_id.in_(old))
        .order_by(Transaction.id)
    ] if old else []
    save_setting(db, KEY, json.dumps(ids))


def listed(db: Session) -> list[int]:
    """The ids still on the list; none without one."""
    row = db.get(AppSetting, KEY)
    if row is None:
        return []
    return json.loads(row.value)


def take_off(db: Session, tx_id: int) -> None:
    """A row saved or deleted is off the list. The caller commits."""
    ids = listed(db)
    if tx_id not in ids:
        return
    save_setting(db, KEY, json.dumps([i for i in ids if i != tx_id]))
