"""The login: BitcoinTX has one user, who owns the fixed accounts."""

from __future__ import annotations
from typing import List, TYPE_CHECKING
from sqlalchemy import Integer, String
from sqlalchemy.orm import relationship, Mapped, mapped_column
import bcrypt
from backend.database import Base

if TYPE_CHECKING:
    from backend.models.account import Account


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    accounts: Mapped[List[Account]] = relationship(
        "Account",
        back_populates="user",
        doc="All accounts owned by this user."
    )

    def set_password(self, password: str) -> None:
        """Store the password's bcrypt hash."""
        password_bytes = password.encode('utf-8')
        # bcrypt reads only 72 bytes (5.0+ raises on more): refuse a longer one.
        if len(password_bytes) > 72:
            raise ValueError("Password cannot exceed 72 bytes")
        self.password_hash = bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode('utf-8')

    def verify_password(self, password: str) -> bool:
        """Whether `password` matches the stored hash."""
        return bcrypt.checkpw(
            password.encode('utf-8'),
            self.password_hash.encode('utf-8')
        )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username})>"
    