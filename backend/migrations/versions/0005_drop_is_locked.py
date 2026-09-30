"""Drop transactions.is_locked, a lock nothing in the app could set.

It was half-built: no button, API or import could lock a row, yet a locked
row refused edits and deletes while recalculation still changed its figures.
Removed rather than finished (owner's decision, 2026-09-30).

SQLite 3.35+ (Docker, StartOS, the Mac app) drops the column in place, and
the table's stored definition stays word for word what a fresh install has.
An older SQLite rebuilds the table (Alembic's batch mode): the same columns,
written a little differently. Foreign keys aren't enforced, so the rows that
point at transactions are left as they are either way.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-30
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.dbapi.sqlite_version_info >= (3, 35):
        op.execute("ALTER TABLE transactions DROP COLUMN is_locked")
    else:
        with op.batch_alter_table("transactions") as batch_op:
            batch_op.drop_column("is_locked")


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()))
