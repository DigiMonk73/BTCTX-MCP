"""
backend/models/user.py

Represents a user of the BitcoinTX application. Even if this is mostly single-user,
the design supports multiple users. Each user can own multiple Accounts,
and each Account can participate in many LedgerEntry lines or single-row Transactions.
No further changes needed for double-entry, but we confirm the layout is correct.
"""

from __future__ import annotations
from typing import List, TYPE_CHECKING
from sqlalchemy import Integer, String
from sqlalchemy.orm import relationship, Mapped, mapped_column
import bcrypt
from backend.database import Base

if TYPE_CHECKING:
    from backend.models.account import Account

class User(Base):
    """
    The main user table. Each user has:
      - An ID (PK)
      - A unique username
      - A hashed password
      - A list of accounts (bank, wallet, fees, etc.)
    """

    __tablename__ = 'users'

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Unique username for login
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Bcrypt-hashed password storage
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Relationship: a user can have many accounts
    accounts: Mapped[List[Account]] = relationship(
        "Account",
        back_populates="user",
        doc="All accounts owned by this user."
    )

    def set_password(self, password: str) -> None:
        """
        Hash and store the user's password using bcrypt.
        The field 'password_hash' holds the result.
        """
        password_bytes = password.encode('utf-8')
        # bcrypt 5.0+ requires explicit check (was silently truncated before)
        if len(password_bytes) > 72:
            raise ValueError("Password cannot exceed 72 bytes")
        self.password_hash = bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode('utf-8')

    def verify_password(self, password: str) -> bool:
        """
        Verify a plain-text password against the stored hash.
        """
        return bcrypt.checkpw(
            password.encode('utf-8'),
            self.password_hash.encode('utf-8')
        )

    def __repr__(self) -> str:
        """
        String representation for debugging, showing user ID and username.
        """
        return f"<User(id={self.id}, username={self.username})>"
    