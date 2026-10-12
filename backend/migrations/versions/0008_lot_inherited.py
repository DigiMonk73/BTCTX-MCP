"""bitcoin_lots.inherited: the lot's coins were inherited (#154).

Inherited bitcoin is always long-term, however soon it's sold (IRC
§1223(9)), and Form 8949 column (b) says "INHERITED" instead of a date
(Form 8949 instructions). The rule follows the coins: a lot moved by a
Transfer keeps it, as it keeps its acquisition date and basis, so it is a
mark on the lot, not only on the deposit.

Lots are rebuilt from the transactions at every recalculation, so nothing
the user typed is stored here. Existing lots are not inherited: the source
Inherited didn't exist before this version.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Plain ADD COLUMN, as in 0006: NOT NULL with a default needs no rebuild.
    op.add_column(
        "bitcoin_lots",
        sa.Column("inherited", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    with op.batch_alter_table("bitcoin_lots") as batch_op:
        batch_op.drop_column("inherited")
