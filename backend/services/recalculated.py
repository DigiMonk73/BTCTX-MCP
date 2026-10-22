"""
Which BitcoinTX last recalculated the live ledger. While it matches, nothing
is pending, so the dry run takes one replay, not two, and a write dated in
this tax year takes none.
"""

import functools

from sqlalchemy.orm import Session

from backend.database import SCRATCH
from backend.migrate import head_revision
from backend.models.app_setting import AppSetting, save_setting
from backend.services.tax_time import get_tax_timezone
from backend.version import app_version

KEY = "recalculated_by"


@functools.cache  # Alembic's head doesn't change while this process runs
def _head() -> str:
    return head_revision()


def stamp(db: Session) -> str:
    """This BitcoinTX: its version, migration head and tax timezone.

    The head is in the stamp because two builds can share a version. The
    timezone is in it because the BTCTX_TIMEZONE fallback can change between
    starts with no recalculation.
    """
    return f"{app_version()} {_head()} {get_tax_timezone(db).key}"


def note(db: Session) -> None:
    """Record this BitcoinTX on the live ledger. A scratch copy's session is
    skipped: what's written there is thrown away. The caller commits."""
    if db.info.get(SCRATCH):
        return
    save_setting(db, KEY, stamp(db))


def is_current(db: Session) -> bool:
    """Whether the stored row equals this BitcoinTX's stamp. False with no row."""
    row = db.get(AppSetting, KEY)
    return row is not None and row.value == stamp(db)
