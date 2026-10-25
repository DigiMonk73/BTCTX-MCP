"""The coins a transaction chose (#711, specific identification).

A Transfer out of a wallet, or a bitcoin Withdrawal from one, may name the
coins that leave: each by the Buy or Deposit that acquired them, and how
much from each (Treas. Reg. §1.1012-1(j)(2)). So:

- chosen_coins: one row per acquisition a transaction chose (its
  transaction_id, the acquisition's acquired_txn_id, the BTC), unique on
  the pair. What the user entered, like the transactions row: a
  recalculation reads it and never rebuilds it.
- bitcoin_lots.acquired_txn_id: the Buy or Deposit that first acquired a
  lot's coins, kept through every transfer, so a choice finds them. A
  plain integer with no foreign key: a key on an existing table would need
  it rebuilt, the app enforces none, and the lot is rebuilt from the
  transactions at every recalculation. Lots made before this are NULL
  until the next one.
- transactions.coins_chosen_at: when the choice was saved (the books' own
  date); NULL when nothing is chosen.

Plain ADD COLUMN, as in 0008 and 0011: no table is rebuilt. No row is
written and nothing is recalculated: nothing is chosen in any ledger, so
no figure moves. The way back drops them, and a ledger that has choices
loses them that way: going back is a copy, never a downgrade.

Revision ID: 0101
Revises: 0100
Create Date: 2026-10-25
"""

from alembic import op
import sqlalchemy as sa

revision = "0101"
down_revision = "0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chosen_coins",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column("acquired_txn_id", sa.Integer(), nullable=False),
        sa.Column("btc", sa.Numeric(18, 8), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transaction_id", "acquired_txn_id"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["acquired_txn_id"], ["transactions.id"]),
    )
    op.create_index("ix_chosen_coins_id", "chosen_coins", ["id"])
    op.create_index("ix_chosen_coins_transaction_id", "chosen_coins", ["transaction_id"])
    op.create_index("ix_chosen_coins_acquired_txn_id", "chosen_coins", ["acquired_txn_id"])
    op.add_column("bitcoin_lots", sa.Column("acquired_txn_id", sa.Integer(), nullable=True))
    op.create_index("ix_bitcoin_lots_acquired_txn_id", "bitcoin_lots", ["acquired_txn_id"])
    op.add_column("transactions", sa.Column("coins_chosen_at", sa.String(), nullable=True))


def downgrade() -> None:
    # SQLite's own DROP COLUMN (3.35 and later), not a batch rebuild: each
    # table's stored definition stays as 0100 made it
    op.drop_column("transactions", "coins_chosen_at")
    op.drop_index("ix_bitcoin_lots_acquired_txn_id", table_name="bitcoin_lots")
    op.drop_column("bitcoin_lots", "acquired_txn_id")
    op.drop_index("ix_chosen_coins_acquired_txn_id", table_name="chosen_coins")
    op.drop_index("ix_chosen_coins_transaction_id", table_name="chosen_coins")
    op.drop_index("ix_chosen_coins_id", table_name="chosen_coins")
    op.drop_table("chosen_coins")
