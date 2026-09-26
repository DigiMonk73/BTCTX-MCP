"""
backend/models/transaction.py

Full double-entry design with separate models:
1) Transaction (header record)
2) LedgerEntry (individual debit/credit lines)
3) BitcoinLot (tracking BTC acquired for FIFO)
4) LotDisposal (partial usage of BitcoinLots on disposal)

We keep everything in one file to maintain your 3-file approach:
(transaction.py, account.py, user.py). Extensive comments clarify each model
and its fields.

CHANGES:
- Removed 'account_id' and 'account' from LotDisposal.
- Added a 'account = relationship("Account", back_populates="ledger_entries")'
  in LedgerEntry so it matches account.py's 'ledger_entries = relationship(..., back_populates="account")'.
This resolves the "Mapper ... has no property 'account'" error and adheres to
standard double-entry design.
- NOW storing all DateTime columns as offset‐aware UTC by using UTCDateTime from database.py
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

# We import Base and UTCDateTime from database.py
from backend.database import Base, UTCDateTime


# ------------------------------------------------------------------------
# TRANSACTION (Header)
# ------------------------------------------------------------------------

class Transaction(Base):
    """
    'Transaction' is the high-level "header" record in the double-entry system.
    Each Transaction can have multiple LedgerEntries (line items) that
    record actual debits/credits. It can also create BitcoinLot(s) if acquiring BTC,
    or create LotDisposal(s) if disposing of previously acquired BTC.

    This model no longer depends on single-entry columns like amount or fee_amount
    for the final ledger amounts, since those live in LedgerEntry now. However,
    we keep optional 'from_account_id', 'to_account_id', 'amount', etc. as LEGACY
    fields for backward compatibility or user-facing convenience.

    cost_basis_usd, proceeds_usd, realized_gain_usd, and holding_period can be updated
    after the FIFO disposal logic calculates partial usage from multiple lots.
    """

    __tablename__ = "transactions"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # Transaction type: "Deposit", "Withdrawal", "Buy", "Sell", and "Transfer"
    # If you prefer an Enum, you can adapt or store as string.
    type = Column(String, nullable=False, doc="Transaction type: e.g. 'Deposit', 'Buy', 'Sell'")

    # When the user says this transaction occurred
    timestamp = Column(
        UTCDateTime,        # REPLACED DateTime(timezone=True) with UTCDateTime
        server_default=func.now(),
        nullable=False,
        doc="When the transaction actually occurred (user-facing)."
    )

    # Lock to prevent edits after finalizing a period (e.g. year-end).
    is_locked = Column(
        Boolean,
        default=False,
        nullable=False,
        doc="Once locked, no further updates or deletion allowed."
    )

    # Audit fields
    created_at = Column(
        UTCDateTime,        # REPLACED DateTime(timezone=True) with UTCDateTime
        server_default=func.now(),
        nullable=False,
        doc="Auto-set creation time."
    )
    updated_at = Column(
        UTCDateTime,        # REPLACED DateTime(timezone=True) with UTCDateTime
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        doc="Auto-set last update time."
    )

    # -------------------------------------------------------------------
    # LEGACY single-entry columns (Optional)
    # -------------------------------------------------------------------
    from_account_id = Column(
        Integer,
        ForeignKey("accounts.id"),
        nullable=True,
        doc="(LEGACY) from account, used in the old single-entry approach."
    )
    to_account_id = Column(
        Integer,
        ForeignKey("accounts.id"),
        nullable=True,
        doc="(LEGACY) to account, used in the old single-entry approach."
    )
    amount = Column(
        Numeric(18, 8),
        nullable=True,
        doc="(LEGACY) single main transaction amount."
    )
    fee_amount = Column(
        Numeric(18, 8),
        nullable=True,
        doc="(LEGACY) single fee in the old system."
    )
    fee_currency = Column(
        String,
        nullable=True,
        doc="(LEGACY) currency of the single fee, e.g. 'BTC' or 'USD'."
    )

    # -------------------------------------------------------------------
    # OPTIONAL FIELDS FOR TAX SUMMARIES
    # -------------------------------------------------------------------
    cost_basis_usd = Column(
        Numeric(18, 2),
        nullable=True,
        doc="Summarized cost basis for the entire transaction (if relevant)."
    )
    gross_proceeds_usd = Column(
        Numeric(18, 2),
        nullable=True,
        doc="User-entered gross proceeds for a Sell or Withdrawal, before fees."
    )
    proceeds_usd = Column(
        Numeric(18, 2),
        nullable=True,
        doc="Summarized proceeds for the entire transaction (if relevant)."
    )
    realized_gain_usd = Column(
        Numeric(18, 2),
        nullable=True,
        doc="Summarized realized gain for the entire transaction (if any)."
    )
    holding_period = Column(
        String,
        nullable=True,
        doc="E.g. 'SHORT' or 'LONG' for partial disposal. Optional usage."
    )
  
    # NEW FIELD: fmv_usd
    fmv_usd = Column(
        Numeric(18, 2),
        nullable=True,
        doc=(
            "Fair Market Value for non-sale disposals (Gift, Donation, Lost). "
            "If user withdrew BTC but did not receive actual proceeds, we store "
            "an informational FMV here (e.g. $450). Meanwhile, proceeds_usd=0. "
            "For normal sales or 'Spent', fmv_usd might remain null or 0."
        )
    )

    # For deposit/withdrawal scenarios
    source = Column(
        String,
        nullable=True,
        doc="(Optional) deposit source, e.g. 'Gift', 'Income'"
    )
    purpose = Column(
        String,
        nullable=True,
        doc="(Optional) withdrawal purpose, e.g. 'Spent', 'Donation'"
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

    # -------------------------------------------------------------------
    # RELATIONSHIPS
    # -------------------------------------------------------------------
    ledger_entries = relationship(
        "LedgerEntry",
        back_populates="transaction",
        cascade="all, delete-orphan",
        doc="All the line items (debits/credits) for this transaction."
    )

    bitcoin_lots_created = relationship(
        "BitcoinLot",
        back_populates="created_transaction",
        cascade="all, delete-orphan",
        doc="If this transaction acquired BTC, we store one or more lots here."
    )

    lot_disposals = relationship(
        "LotDisposal",
        back_populates="transaction",
        cascade="all, delete-orphan",
        doc="If this transaction disposed some BTC, partial usage is logged here."
    )

    def __repr__(self):
        return (
            f"<Transaction(id={self.id}, type={self.type}, "
            f"timestamp={self.timestamp}, locked={self.is_locked})>"
        )


class LedgerEntry(Base):
    """
    Represents a single line item (debit or credit) in the double-entry ledger.
    For example:
      - If user does a Transfer with a fee, you might have 3 lines:
         1) from wallet => -1.001 BTC
         2) to another wallet => +1.0 BTC
         3) fee account => +0.001 BTC

    The 'transaction_id' links to the Transaction (header).
    The 'account_id' tells which Account is debited/credited.
    'amount' can be negative or positive based on your chosen sign convention.
    """

    __tablename__ = "ledger_entries"

    id = Column(Integer, primary_key=True, index=True)

    # Link to the Transaction header
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False, index=True)
    # Which account is this line referencing
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)

    amount = Column(
        Numeric(18, 8),
        nullable=False,
        doc="Signed amount for this ledger line (e.g. -1.0 => outflow)."
    )
    currency = Column(
        String,
        nullable=False,
        default="BTC",
        doc="Currency for this line, e.g. 'BTC' or 'USD'."
    )
    entry_type = Column(
        String,
        nullable=True,
        doc="Optional label: 'FEE', 'TRANSFER_IN', 'BUY', etc."
    )

    # Relationship to the Transaction
    transaction = relationship(
        "Transaction",
        back_populates="ledger_entries",
        doc="The parent Transaction 'header' this line belongs to."
    )

    # Relationship to the Account
    # This is crucial if Account.ledger_entries uses back_populates="account"
    account = relationship(
        "Account",
        back_populates="ledger_entries",
        doc="Which account is impacted by this ledger entry."
    )

    def __repr__(self):
        return (
            f"<LedgerEntry(id={self.id}, tx={self.transaction_id}, acct={self.account_id}, "
            f"amount={self.amount}, currency={self.currency}, entry_type={self.entry_type})>"
        )

class BitcoinLot(Base):
    """
    Whenever BTC is acquired (a 'Buy' or 'Deposit'), you create a BitcoinLot to
    represent that chunk of BTC. 'remaining_btc' gets reduced as partial sells
    or withdrawals occur (see LotDisposal).
    cost_basis_usd is the total cost for the entire lot, possibly including fees.
    """

    __tablename__ = "bitcoin_lots"

    id = Column(Integer, primary_key=True, index=True)

    created_txn_id = Column(
        Integer,
        ForeignKey("transactions.id"),
        nullable=False,
        index=True,
        doc="Points to the Transaction where the user acquired this BTC."
    )

    acquired_date = Column(
        UTCDateTime,        # REPLACED DateTime(timezone=True) with UTCDateTime
        server_default=func.now(),
        nullable=False,
        doc="When the BTC was acquired. Usually equals transaction's timestamp."
    )

    total_btc = Column(
        Numeric(18, 8),
        nullable=False,
        doc="How many BTC were originally acquired in this lot."
    )
    remaining_btc = Column(
        Numeric(18, 8),
        nullable=False,
        doc="How many BTC remain un-disposed from this lot after partial sells."
    )
    cost_basis_usd = Column(
        Numeric(18, 2),
        nullable=False,
        doc="Total USD cost basis for the entire lot (including fees)."
    )

    created_transaction = relationship(
        "Transaction",
        back_populates="bitcoin_lots_created",
        doc="Transaction that introduced these BTC into the system."
    )

    lot_disposals = relationship(
        "LotDisposal",
        back_populates="lot",
        cascade="all, delete-orphan",
        doc="Tracks how this lot is consumed by future sells/withdrawals."
    )

    def __repr__(self):
        return (
            f"<BitcoinLot(id={self.id}, total_btc={self.total_btc}, "
            f"remaining_btc={self.remaining_btc}, cost_basis_usd={self.cost_basis_usd}, "
            f"acquired_date={self.acquired_date})>"
        )


class LotDisposal(Base):
    """
    Logs how a specific disposal transaction consumed part of a BitcoinLot.
    For example, if user sells 0.5 BTC but the oldest lot has 0.3 left,
    we create one LotDisposal for 0.3 from that lot, then another for 0.2
    from the next lot, etc. disposal_basis_usd, proceeds_usd_for_that_portion,
    realized_gain_usd can store partial calculations if you want to see
    exact results for each chunk.

    CHANGED: Added 'holding_period' to track short-term vs. long-term gains/losses.
    """

    __tablename__ = "lot_disposals"

    id = Column(Integer, primary_key=True)

    lot_id = Column(
        Integer,
        ForeignKey("bitcoin_lots.id"),
        nullable=False,
        index=True,
        doc="ID of the BitcoinLot from which we are removing BTC."
    )

    transaction_id = Column(
        Integer,
        ForeignKey("transactions.id"),
        nullable=False,
        index=True,
        doc="Which transaction is disposing these BTC."
    )

    disposed_btc = Column(
        Numeric(18, 8),
        nullable=False,
        doc="How many BTC from this lot were applied to this disposal."
    )

    # Optional partial gain fields
    realized_gain_usd = Column(
        Numeric(18, 2),
        nullable=True,
        doc="Realized gain for this partial chunk alone, if computed."
    )
    disposal_basis_usd = Column(
        Numeric(18, 2),
        nullable=True,
        doc="Portion of the lot's basis allocated to this disposal."
    )
    proceeds_usd_for_that_portion = Column(
        Numeric(18, 2),
        nullable=True,
        doc="Slice of total proceeds allocated to this partial disposal."
    )

    holding_period = Column(
        String(10),
        nullable=True,
        doc="Holding period of the disposed BTC, e.g., 'SHORT' or 'LONG' (1 year threshold)."
    )

    # Relationship to the lot from which BTC is disposed
    lot = relationship(
        "BitcoinLot",
        back_populates="lot_disposals",
        doc="The parent BitcoinLot from which these BTC are taken."
    )
    # Relationship to the disposing transaction
    transaction = relationship(
        "Transaction",
        back_populates="lot_disposals",
        doc="The disposal transaction (Sell/Withdraw) that uses this portion of the lot."
    )

    def __repr__(self):
        return (
            f"<LotDisposal(id={self.id}, lot_id={self.lot_id}, txn_id={self.transaction_id}, "
            f"disposed_btc={self.disposed_btc}, realized_gain_usd={self.realized_gain_usd}, "
            f"holding_period={self.holding_period})>"
        )
