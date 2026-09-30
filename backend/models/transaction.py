"""
The ledger's models. A Transaction is what the user enters (type, accounts,
amount, fee, USD values); from it every recalculation rebuilds its
LedgerEntry lines (debits and credits), the BitcoinLots it acquires and the
LotDisposals that consume lots first in, first out
(services/transaction.py). All timestamps are stored in UTC (UTCDateTime).
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Numeric,
    ForeignKey,
    false as sa_false,
    func
)
from sqlalchemy.orm import relationship

from backend.database import Base, UTCDateTime


class Transaction(Base):
    """
    One entered transaction. The user's fields (type, accounts, amount, fee,
    typed USD values) are the source of truth; a Sell's or Withdrawal's
    cost basis, net proceeds, gain and holding period are worked out from its
    lot disposals on every recalculation.
    """

    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)

    type = Column(String, nullable=False, doc="Deposit, Withdrawal, Transfer, Buy or Sell.")
    timestamp = Column(
        UTCDateTime,
        server_default=func.now(),
        nullable=False,
        doc="When the transaction happened, as the user entered it."
    )

    created_at = Column(
        UTCDateTime,
        server_default=func.now(),
        nullable=False,
        doc="Auto-set creation time."
    )
    updated_at = Column(
        UTCDateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        doc="Auto-set last update time."
    )

    # External (99) is an id with no account row.
    from_account_id = Column(
        Integer,
        ForeignKey("accounts.id"),
        nullable=True,
        doc="The account the amount leaves."
    )
    to_account_id = Column(
        Integer,
        ForeignKey("accounts.id"),
        nullable=True,
        doc="The account the amount goes to."
    )
    amount = Column(
        Numeric(18, 8),
        nullable=True,
        doc="The amount, in the from account's currency (a Transfer's includes its BTC fee)."
    )
    fee_amount = Column(
        Numeric(18, 8),
        nullable=True,
        doc="The fee, in fee_currency."
    )
    fee_currency = Column(
        String,
        nullable=True,
        doc="'BTC' or 'USD'."
    )

    cost_basis_usd = Column(
        Numeric(18, 2),
        nullable=True,
        doc="A Buy's or Deposit's basis as entered; a Sell's or Withdrawal's from its lots."
    )
    gross_proceeds_usd = Column(
        Numeric(18, 2),
        nullable=True,
        doc="User-entered gross proceeds for a Sell or Withdrawal, before fees."
    )
    proceeds_usd = Column(
        Numeric(18, 2),
        nullable=True,
        doc="Proceeds net of fees, worked out from gross_proceeds_usd on every recalculation."
    )
    realized_gain_usd = Column(
        Numeric(18, 2),
        nullable=True,
        doc="The disposal's gain or loss, from its lots."
    )
    holding_period = Column(
        String,
        nullable=True,
        doc="'SHORT' or 'LONG', from its lots."
    )

    fmv_usd = Column(
        Numeric(18, 2),
        nullable=True,
        doc=(
            "Fair market value of a Gift, Donation or Lost withdrawal, as entered: "
            "shown on the reports, while its proceeds stay $0."
        )
    )
    source = Column(
        String,
        nullable=True,
        doc="A Deposit's source, e.g. 'Gift', 'Income'."
    )
    purpose = Column(
        String,
        nullable=True,
        doc="A Withdrawal's purpose, e.g. 'Spent', 'Donation'."
    )
    broker_reporting = Column(
        String,
        nullable=True,
        doc=(
            "What the broker actually reported on Form 1099-DA/1099-B for this "
            "Sell or Withdrawal: 'none', 'proceeds' or 'basis'. NULL = decide "
            "automatically (form_8949._broker_reporting)."
        ),
    )
    fee_usd = Column(
        Numeric(18, 2),
        nullable=True,
        doc=(
            "USD value of a BTC fee, stored when the transaction is saved "
            "(fee x that day's price, or typed by the user) so recalculation "
            "never prices it again. NULL for USD fees and no fee."
        ),
    )
    fee_usd_manual = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sa_false(),
        doc="True when the user typed fee_usd: it is kept when the fee or date changes.",
    )

    ledger_entries = relationship(
        "LedgerEntry",
        back_populates="transaction",
        cascade="all, delete-orphan",
        doc="Its debit and credit lines."
    )

    bitcoin_lots_created = relationship(
        "BitcoinLot",
        back_populates="created_transaction",
        cascade="all, delete-orphan",
        doc="The lots it acquired."
    )

    lot_disposals = relationship(
        "LotDisposal",
        back_populates="transaction",
        cascade="all, delete-orphan",
        doc="The lot slices it disposed of."
    )

    def __repr__(self):
        return (
            f"<Transaction(id={self.id}, type={self.type}, "
            f"timestamp={self.timestamp})>"
        )


class LedgerEntry(Base):
    """
    One debit or credit line of a transaction, signed: a Transfer of 1.001
    BTC with a 0.001 fee is -1.001 from the source, +1.0 to the destination
    and +0.001 to BTC Fees.
    """

    __tablename__ = "ledger_entries"

    id = Column(Integer, primary_key=True, index=True)

    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)

    amount = Column(
        Numeric(18, 8),
        nullable=False,
        doc="Signed: negative leaves the account."
    )
    currency = Column(
        String,
        nullable=False,
        default="BTC",
        doc="'BTC' or 'USD'."
    )
    entry_type = Column(
        String,
        nullable=True,
        doc="A label such as 'FEE', 'TRANSFER_IN', 'BUY'."
    )

    transaction = relationship(
        "Transaction",
        back_populates="ledger_entries",
        doc="The transaction this line belongs to."
    )
    account = relationship(
        "Account",
        back_populates="ledger_entries",
        doc="The account debited or credited."
    )

    def __repr__(self):
        return (
            f"<LedgerEntry(id={self.id}, tx={self.transaction_id}, acct={self.account_id}, "
            f"amount={self.amount}, currency={self.currency}, entry_type={self.entry_type})>"
        )


class BitcoinLot(Base):
    """
    BTC acquired by a Buy or Deposit, or moved by a Transfer (which keeps the
    source lot's acquisition date and a pro-rated share of its basis).
    Disposals and transfers take from remaining_btc, oldest lot first.
    """

    __tablename__ = "bitcoin_lots"

    id = Column(Integer, primary_key=True, index=True)

    created_txn_id = Column(
        Integer,
        ForeignKey("transactions.id"),
        nullable=False,
        index=True,
        doc="The transaction that acquired (or moved) this BTC."
    )

    acquired_date = Column(
        UTCDateTime,
        server_default=func.now(),
        nullable=False,
        doc="When the BTC was acquired: a moved lot keeps its source's date."
    )

    total_btc = Column(
        Numeric(18, 8),
        nullable=False,
        doc="BTC in the lot when it was created."
    )
    remaining_btc = Column(
        Numeric(18, 8),
        nullable=False,
        doc="BTC not yet disposed of."
    )
    cost_basis_usd = Column(
        Numeric(18, 2),
        nullable=False,
        doc="The whole lot's cost basis in USD."
    )

    created_transaction = relationship(
        "Transaction",
        back_populates="bitcoin_lots_created",
        doc="The transaction that created the lot."
    )

    lot_disposals = relationship(
        "LotDisposal",
        back_populates="lot",
        cascade="all, delete-orphan",
        doc="The disposals that consumed it."
    )

    def __repr__(self):
        return (
            f"<BitcoinLot(id={self.id}, total_btc={self.total_btc}, "
            f"remaining_btc={self.remaining_btc}, cost_basis_usd={self.cost_basis_usd}, "
            f"acquired_date={self.acquired_date})>"
        )


class LotDisposal(Base):
    """
    The slice of one lot that a disposal consumed: selling 0.5 BTC when the
    oldest lot has 0.3 left gives a disposal of 0.3 from it and one of 0.2
    from the next. Each slice has its own basis, proceeds, gain and holding
    period; the taxable ones are the Form 8949 rows.
    """

    __tablename__ = "lot_disposals"

    id = Column(Integer, primary_key=True)

    lot_id = Column(
        Integer,
        ForeignKey("bitcoin_lots.id"),
        nullable=False,
        index=True,
        doc="The lot the BTC came from."
    )

    transaction_id = Column(
        Integer,
        ForeignKey("transactions.id"),
        nullable=False,
        index=True,
        doc="The disposing transaction."
    )

    disposed_btc = Column(
        Numeric(18, 8),
        nullable=False,
        doc="BTC taken from the lot."
    )

    realized_gain_usd = Column(
        Numeric(18, 2),
        nullable=True,
        doc="This slice's gain or loss."
    )
    disposal_basis_usd = Column(
        Numeric(18, 2),
        nullable=True,
        doc="This slice's share of the lot's basis."
    )
    proceeds_usd_for_that_portion = Column(
        Numeric(18, 2),
        nullable=True,
        doc="This slice's share of the proceeds."
    )

    holding_period = Column(
        String(10),
        nullable=True,
        doc="'LONG' when disposed of more than a year after acquisition (tax timezone), else 'SHORT'."
    )
    is_fee = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sa_false(),
        doc=(
            "A BTC network fee's disposal (a transfer's or a withdrawal's): taxable "
            "at the fee's value even when the withdrawal itself is a gift, and "
            "never on a broker form."
        ),
    )

    lot = relationship(
        "BitcoinLot",
        back_populates="lot_disposals",
        doc="The lot the BTC came from."
    )
    transaction = relationship(
        "Transaction",
        back_populates="lot_disposals",
        doc="The Sell, Withdrawal or Transfer (its fee) that disposed of the slice."
    )

    def __repr__(self):
        return (
            f"<LotDisposal(id={self.id}, lot_id={self.lot_id}, txn_id={self.transaction_id}, "
            f"disposed_btc={self.disposed_btc}, realized_gain_usd={self.realized_gain_usd}, "
            f"holding_period={self.holding_period})>"
        )
