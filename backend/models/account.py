"""
An account: one of the fixed ones (Bank 1, Wallet 2, Exchange USD 3,
Exchange BTC 4, BTC Fees 5, USD Fees 6; External 99 is not a row), owned by
the user. Transactions name it as their from or to side; the ledger lines
built from them debit or credit it.
"""

from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, false, true
from sqlalchemy.orm import relationship
from backend.database import Base


class Exchange(Base):
    """An exchange (spec 5.2): its two accounts, "<name> USD" and "<name> BTC",
    share its id. Exchange 1 is 1.x's, "Exchange"."""
    __tablename__ = "exchanges"

    id = Column(Integer, primary_key=True)
    name = Column(String(collation="NOCASE"), nullable=False, unique=True)
    # "This exchange sends me a Form 1099-DA" (5.9): on by default
    sends_1099da = Column(Boolean, nullable=False, default=True, server_default=true())


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    name = Column(String, unique=True, nullable=False)

    # "USD" or "BTC"
    currency = Column(String, nullable=False, default="USD")

    # Spec 5.2: "bank", "wallet", "exchange" or "fee"; an exchange's two
    # accounts name their exchange; a hidden one is left out of the pickers
    kind = Column(String, nullable=True)
    exchange_id = Column(Integer, nullable=True)  # exchanges.id
    hidden = Column(Boolean, nullable=False, default=False, server_default=false())

    user = relationship(
        "User",
        back_populates="accounts",
        doc="The user that owns this account."
    )

    transactions_from = relationship(
        "Transaction",
        foreign_keys="[Transaction.from_account_id]",
        doc="Transactions with this account as their from side."
    )
    transactions_to = relationship(
        "Transaction",
        foreign_keys="[Transaction.to_account_id]",
        doc="Transactions with this account as their to side."
    )
    ledger_entries = relationship(
        "LedgerEntry",
        back_populates="account",
        cascade="all, delete-orphan",
        doc="All ledger lines (debit/credit) pointing to this account."
    )

    def __repr__(self):
        return (
            f"<Account(id={self.id}, user_id={self.user_id}, "
            f"name={self.name}, currency={self.currency})>"
        )