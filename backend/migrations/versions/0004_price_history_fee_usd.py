"""Local BTC price history and stored fee values.

- btc_price_daily: one BTC/USD price per UTC day (the 00:00 UTC daily
  price the sources publish). Every historical valuation reads it first, so
  the same day always gets the same price and recalculation never needs the
  network.
- transactions.fee_usd / fee_usd_manual: a BTC fee's USD value, stored once
  when the transaction is saved (typed by the user when fee_usd_manual).
  Recalculation reads it instead of pricing the fee again.

Existing figures don't move: fee_usd is filled from the proceeds the fee
disposals already carry (a transfer's disposals are all fee disposals).

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-26
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "btc_price_daily",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("usd", sa.Numeric(18, 2), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
    )
    # Plain ADD COLUMN (SQLite allows NOT NULL with a default): a batch
    # operation would rebuild the whole table for no reason.
    op.add_column("transactions", sa.Column("fee_usd", sa.Numeric(18, 2), nullable=True))
    op.add_column(
        "transactions",
        sa.Column("fee_usd_manual", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        """
        UPDATE transactions
        SET fee_usd = (
            SELECT ROUND(SUM(d.proceeds_usd_for_that_portion), 2)
            FROM lot_disposals d WHERE d.transaction_id = transactions.id
        )
        WHERE type = 'Transfer' AND UPPER(COALESCE(fee_currency, '')) = 'BTC'
          AND CAST(COALESCE(fee_amount, 0) AS REAL) > 0
          AND EXISTS (SELECT 1 FROM lot_disposals d WHERE d.transaction_id = transactions.id)
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("fee_usd_manual")
        batch_op.drop_column("fee_usd")
    op.drop_table("btc_price_daily")
