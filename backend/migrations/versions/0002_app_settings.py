"""app_settings key/value table (tax timezone).

Development builds between v0.7.0 and the introduction of migrations created
this table with create_all(), so it may already exist.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("app_settings"):
        return
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
