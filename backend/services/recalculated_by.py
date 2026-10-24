"""
Which BitcoinTX last recalculated the live ledger (2.0 spec 5.8): its
version, its migration head and the tax timezone, in app_settings. While it
names this BitcoinTX, the stored figures are what a recalculation gives
now, so nothing is pending (Ledger Review's recalc_changes): the past-year
warning's dry run takes one replay, not two, and an AI write dated in this
tax year takes none. A restore brings the backup's along with its figures
(5.11).
"""

from functools import cache

from sqlalchemy.orm import Session

from backend.database import SCRATCH
from backend.migrate import head_revision
from backend.models.app_setting import AppSetting, save_setting
from backend.services.tax_time import get_tax_timezone
from backend.version import app_version

KEY = "recalculated_by"


@cache  # the code's migration head doesn't change while it runs
def _head() -> str:
    return head_revision()


def stamp(db: Session) -> str:
    """
    This BitcoinTX, as recalculated_by names it. Two builds can share a
    version string, so the head is in it; the tax timezone too, since the
    BTCTX_TIMEZONE fallback can change between starts with nothing
    recalculated.
    """
    return f"{app_version()} {_head()} {get_tax_timezone(db).key}"


def note(db: Session) -> None:
    """After a full recalculation of the ledger, uncommitted: its caller
    commits or rolls back. A scratch copy's is thrown away with it, and so
    never noted on the copy either."""
    if not db.info.get(SCRATCH):
        save_setting(db, KEY, stamp(db))


def matches(db: Session) -> bool:
    """Whether this BitcoinTX last recalculated the ledger: never, with no
    row (a 1.x ledger, or one only ever added to)."""
    row = db.get(AppSetting, KEY)
    return row is not None and row.value == stamp(db)
