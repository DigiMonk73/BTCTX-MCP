"""transactions.acquired_at: when the coins of a My BTC or Gift deposit were
originally acquired.

A deposit of coins the user already owned (My BTC) or received as a gift
with the giver's basis keeps their holding period from that date (IRC
§1223(2) for gifts), not from the deposit (#91). The lot the deposit creates
takes it as its acquisition date: the holding period, Form 8949 column (b)
and first-in-first-out follow it.

An empty column: nothing changes in any ledger until a date is filled in.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-10
"""

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Text, like every timestamp here (database.UTCDateTime: ISO 8601 in UTC)
    op.add_column("transactions", sa.Column("acquired_at", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("acquired_at")
