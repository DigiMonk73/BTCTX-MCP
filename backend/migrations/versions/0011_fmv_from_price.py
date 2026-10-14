"""transactions.fmv_from_price (#255).

A Gift, Donation or Lost withdrawal's value (fmv_usd) left blank is filled
from the price when it's saved, like an income deposit's basis and a Spent's
proceeds: this marks the values filled that way, so the form shows them as
from the price and an edit of the amount or hour prices them again. A typed
value is kept.

Existing rows: every value saved so far counts as typed (false), as 0006 did
for income: nothing is priced again, and no figure changes.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-14
"""

from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Plain ADD COLUMN, as in 0004 and 0010: NOT NULL with a default needs no rebuild.
    op.add_column(
        "transactions",
        sa.Column("fmv_from_price", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("fmv_from_price")
