"""transactions.price_moment and transactions.proceeds_from_price (#144).

- price_moment: the moment of the price a transaction's priced values came
  from: "hour" (the opening price of its UTC hour) or "day" (its UTC day's
  00:00 price); NULL when it has none (every value typed). Its priced
  values are an income or rebate deposit's basis (cost_basis_from_price), a
  Spent withdrawal's proceeds (proceeds_from_price) and a BTC fee's value
  (fee_usd_manual false). Ledger Review lists the "day" ones the hour would
  change, and the tax report says which moment each value has.
- proceeds_from_price: a Spent withdrawal's proceeds came from the price
  (left blank when entered), like cost_basis_from_price for income. An edit
  of what they depend on prices them again; a typed value is kept.

Existing rows: every priced value so far came from the day's price, so a
transaction with one is marked "day". A Spent's proceeds are marked only
where the stored gross is exactly that day's stored price x the amount, to
the cent, as the app priced it; every other row counts as typed (as 0006
did for income). No figure changes here.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-12
"""

from decimal import Decimal, InvalidOperation

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

CENT = Decimal("0.01")
SATS = Decimal("0.00000001")


def upgrade() -> None:
    # Plain ADD COLUMN, as in 0004: NOT NULL with a default needs no rebuild.
    op.add_column("transactions", sa.Column("price_moment", sa.String(), nullable=True))
    op.add_column(
        "transactions",
        sa.Column("proceeds_from_price", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    bind = op.get_bind()
    # The day of a price is the timestamp's UTC day (price_history.daily_price)
    rows = bind.execute(sa.text(
        """
        SELECT t.id, t.amount, t.gross_proceeds_usd, p.usd
        FROM transactions t JOIN btc_price_daily p ON p.day = date(t.timestamp)
        WHERE t.type = 'Withdrawal' AND LOWER(COALESCE(t.purpose, '')) = 'spent'
          AND t.gross_proceeds_usd IS NOT NULL AND t.amount IS NOT NULL
        """
    )).all()
    for row in rows:
        if _is_day_value(row.amount, row.gross_proceeds_usd, row.usd):
            bind.execute(sa.text("UPDATE transactions SET proceeds_from_price = 1 WHERE id = :id"),
                         {"id": row.id})
    bind.execute(sa.text(
        """
        UPDATE transactions SET price_moment = 'day'
        WHERE cost_basis_from_price = 1 OR proceeds_from_price = 1
           OR (fee_usd IS NOT NULL AND fee_usd_manual = 0)
        """
    ))


def _is_day_value(amount, value, price) -> bool:
    """Whether the value is the price x the amount, rounded as the app rounds
    it. A value that isn't a number (an old row) counts as typed."""
    try:
        priced = (Decimal(str(price)) * Decimal(str(amount)).quantize(SATS)).quantize(CENT)
        return priced > 0 and Decimal(str(value)).quantize(CENT) == priced
    except InvalidOperation:
        return False


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("proceeds_from_price")
        batch_op.drop_column("price_moment")
