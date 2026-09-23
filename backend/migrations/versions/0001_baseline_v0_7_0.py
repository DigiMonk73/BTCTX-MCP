"""Baseline: the schema every install had at v0.7.0.

Frozen DDL (never import models here: they keep changing, this must not).
Databases created before migrations existed are checked against this
revision, repaired where safe, and stamped (see runner.adopt_unversioned).

Revision ID: 0001
Revises:
Create Date: 2026-09-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_users_id", "users", ["id"])

    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_accounts_id", "accounts", ["id"])

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("timestamp", sa.String(), server_default=sa.func.now(), nullable=False),
        sa.Column("is_locked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.String(), server_default=sa.func.now(), nullable=False),
        sa.Column("from_account_id", sa.Integer(), nullable=True),
        sa.Column("to_account_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(18, 8), nullable=True),
        sa.Column("fee_amount", sa.Numeric(18, 8), nullable=True),
        sa.Column("fee_currency", sa.String(), nullable=True),
        sa.Column("cost_basis_usd", sa.Numeric(18, 2), nullable=True),
        sa.Column("gross_proceeds_usd", sa.Numeric(18, 2), nullable=True),
        sa.Column("proceeds_usd", sa.Numeric(18, 2), nullable=True),
        sa.Column("realized_gain_usd", sa.Numeric(18, 2), nullable=True),
        sa.Column("holding_period", sa.String(), nullable=True),
        sa.Column("fmv_usd", sa.Numeric(18, 2), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("purpose", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["from_account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["to_account_id"], ["accounts.id"]),
    )
    op.create_index("ix_transactions_id", "transactions", ["id"])

    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 8), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("entry_type", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
    )
    op.create_index("ix_ledger_entries_id", "ledger_entries", ["id"])
    op.create_index("ix_ledger_entries_transaction_id", "ledger_entries", ["transaction_id"])
    op.create_index("ix_ledger_entries_account_id", "ledger_entries", ["account_id"])

    op.create_table(
        "bitcoin_lots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_txn_id", sa.Integer(), nullable=False),
        sa.Column("acquired_date", sa.String(), server_default=sa.func.now(), nullable=False),
        sa.Column("total_btc", sa.Numeric(18, 8), nullable=False),
        sa.Column("remaining_btc", sa.Numeric(18, 8), nullable=False),
        sa.Column("cost_basis_usd", sa.Numeric(18, 2), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["created_txn_id"], ["transactions.id"]),
    )
    op.create_index("ix_bitcoin_lots_id", "bitcoin_lots", ["id"])
    op.create_index("ix_bitcoin_lots_created_txn_id", "bitcoin_lots", ["created_txn_id"])

    op.create_table(
        "lot_disposals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lot_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column("disposed_btc", sa.Numeric(18, 8), nullable=False),
        sa.Column("realized_gain_usd", sa.Numeric(18, 2), nullable=True),
        sa.Column("disposal_basis_usd", sa.Numeric(18, 2), nullable=True),
        sa.Column("proceeds_usd_for_that_portion", sa.Numeric(18, 2), nullable=True),
        sa.Column("holding_period", sa.String(10), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["lot_id"], ["bitcoin_lots.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
    )
    op.create_index("ix_lot_disposals_lot_id", "lot_disposals", ["lot_id"])
    op.create_index("ix_lot_disposals_transaction_id", "lot_disposals", ["transaction_id"])


def downgrade() -> None:
    for table in ("lot_disposals", "bitcoin_lots", "ledger_entries", "transactions", "accounts", "users"):
        op.drop_table(table)
