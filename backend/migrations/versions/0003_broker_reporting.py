"""broker_reporting: per-transaction Form 1099-DA override.

NULL (every existing row) keeps the automatic box rules, so reports don't
change until a user sets it.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(sa.Column("broker_reporting", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("broker_reporting")
