"""The account book's columns (spec 5.2), a draft stub for B7b (never merged).

A new table `exchanges` (exchange 1, today's "Exchange", is made by
database.seed_defaults at every start and after a restore, as 5.2 has it, so
a restore's copy of the backup's rows never meets a row made here), and three
columns in `accounts`: `kind`, `exchange_id` and `hidden`. Existing rows:
1 is a bank, 2 a wallet, 3 and 4 exchange 1's, 5 and 6 fee accounts; any
other account (made through the 1.x API) a wallet when it holds BTC, else a
bank (5.3). No figure changes: nothing reads these columns but the account
book and Settings.

The real B2a writes this migration with 5.3's repairs; this one is the
Grok trial's, on draft/2.0-grok only.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exchanges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(collation="NOCASE"), nullable=False, unique=True),
        sa.Column("sends_1099da", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    # Plain ADD COLUMN, as in 0011 (no rebuild); no foreign key: the app doesn't turn them on
    op.add_column("accounts", sa.Column("kind", sa.String(), nullable=True))
    op.add_column("accounts", sa.Column("exchange_id", sa.Integer(), nullable=True))
    op.add_column("accounts", sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE accounts SET kind = 'bank' WHERE id = 1")
    op.execute("UPDATE accounts SET kind = 'wallet' WHERE id = 2")
    op.execute("UPDATE accounts SET kind = 'exchange', exchange_id = 1 WHERE id IN (3, 4)")
    op.execute("UPDATE accounts SET kind = 'fee' WHERE id IN (5, 6)")
    op.execute("UPDATE accounts SET kind = CASE currency WHEN 'BTC' THEN 'wallet' ELSE 'bank' END "
               "WHERE kind IS NULL AND id NOT IN (99) AND name NOT IN ('BTC Fees', 'USD Fees')")


def downgrade() -> None:
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.drop_column("hidden")
        batch_op.drop_column("exchange_id")
        batch_op.drop_column("kind")
    op.drop_table("exchanges")
