"""transactions.cost_basis_from_price: an income deposit's value came from
that day's BTC price, not typed by the user.

An income deposit (Income, Interest or Reward into Wallet or Exchange BTC)
left without a value is valued at the day's price x its amount. Without a
mark, an edit of its amount, day or account kept the old figure (#76): the
app couldn't tell it from a typed one, which an edit must keep.

Existing rows: the mark is set only where the stored value is exactly that
day's stored price x the amount, to the cent, as the app would have priced
it; every other row counts as typed. No figure changes here: the mark only
decides what the next edit of the deposit does.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-10
"""

from decimal import Decimal

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

CENT = Decimal("0.01")
SATS = Decimal("0.00000001")


def upgrade() -> None:
    # Plain ADD COLUMN, as in 0004: NOT NULL with a default needs no rebuild.
    op.add_column(
        "transactions",
        sa.Column("cost_basis_from_price", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    bind = op.get_bind()
    # The day of a price is the timestamp's UTC day (price_history.daily_price);
    # the sources and BTC accounts are those of this version, written out so a
    # later change to the app's lists can't change what this migration did.
    rows = bind.execute(sa.text(
        """
        SELECT t.id, t.amount, t.cost_basis_usd, p.usd
        FROM transactions t JOIN btc_price_daily p ON p.day = date(t.timestamp)
        WHERE t.type = 'Deposit' AND t.to_account_id IN (2, 4)
          AND LOWER(COALESCE(t.source, '')) IN ('income', 'interest', 'reward')
          AND t.cost_basis_usd IS NOT NULL AND t.amount IS NOT NULL
        """
    )).all()
    priced = [row.id for row in rows if _is_day_value(row.amount, row.cost_basis_usd, row.usd)]
    for tx_id in priced:
        bind.execute(sa.text("UPDATE transactions SET cost_basis_from_price = 1 WHERE id = :id"), {"id": tx_id})


def _is_day_value(amount, basis, price) -> bool:
    """Whether the basis is the price x the amount, rounded as the app rounds it."""
    value = (Decimal(str(price)) * Decimal(str(amount)).quantize(SATS)).quantize(CENT)
    return value > 0 and Decimal(str(basis)).quantize(CENT) == value


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("cost_basis_from_price")
