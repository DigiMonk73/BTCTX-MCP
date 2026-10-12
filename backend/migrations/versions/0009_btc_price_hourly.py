"""The hourly BTC price history's table (#144).

- btc_price_hourly: one BTC/USD price per UTC hour (the hour's opening
  price), for hours this install priced from its chosen source after the
  year files end (services/hourly_prices.py). A stored hour never changes.

Nothing else changes: no figure moves.

Revision ID: 0009
Revises: 0007 (0008 once #163's migration is in develop: whichever merges
second points this chain at the other)
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "btc_price_hourly",
        sa.Column("hour", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("usd", sa.Numeric(18, 2), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("btc_price_hourly")
