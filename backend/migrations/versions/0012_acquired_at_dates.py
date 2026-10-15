"""transactions.acquired_at holds a date (#185).

A My BTC or Gift deposit's date originally acquired, or an Inherited one's
date of death, was stored as a moment: the typed date at noon in the tax
timezone, capped at the deposit's own moment. Read back as a date in
whatever the tax timezone was later, a change of many hours moved it a day,
and saving the deposit unchanged stored the moved day (#185). The column now
holds the date itself, 'YYYY-MM-DD' (database.PlainDate); a lot takes noon
of that date in the tax timezone of the recalculation that makes it.

Existing rows: each moment becomes its date in this database's tax timezone
(the app_settings row, else BTCTX_TIMEZONE, else UTC, as
tax_time.get_tax_timezone_name), which is the date the form shows today. A
date an earlier timezone change already moved can't be told apart: it keeps
the date shown. A restored backup is converted with its own setting. No
figure changes: the next recalculation makes the same lots, at the same
moments, from these dates.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-15
"""

import os
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _rewrite(_as_date)


def downgrade() -> None:
    _rewrite(_as_moment)


def _rewrite(convert) -> None:
    bind = op.get_bind()
    tz = _tax_timezone(bind)
    rows = bind.execute(sa.text("SELECT id, acquired_at FROM transactions WHERE acquired_at IS NOT NULL")).all()
    for row in rows:
        bind.execute(sa.text("UPDATE transactions SET acquired_at = :value WHERE id = :id"),
                     {"value": convert(str(row.acquired_at).strip(), tz), "id": row.id})


def _tax_timezone(bind) -> ZoneInfo:
    """The tax timezone the app reads (tax_time.get_tax_timezone_name)."""
    name = bind.execute(sa.text("SELECT value FROM app_settings WHERE key = 'tax_timezone'")).scalar()
    return ZoneInfo(name or os.getenv("BTCTX_TIMEZONE") or "UTC")


def _as_date(text: str, tz: ZoneInfo) -> str:
    """A stored moment ('...Z', or naive as UTC) as its date in `tz`; a date stays."""
    if len(text) == 10:
        return text
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(tz).date().isoformat()


def _as_moment(text: str, tz: ZoneInfo) -> str:
    """A date back to noon in `tz`, in UTC, as stored before 0012."""
    if len(text) != 10:
        return text
    noon = datetime.combine(date.fromisoformat(text), time(12), tzinfo=tz).astimezone(timezone.utc)
    return noon.isoformat().replace("+00:00", "Z")
