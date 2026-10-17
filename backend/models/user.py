"""The login: BitcoinTX has one user, who owns the fixed accounts."""

from __future__ import annotations
import functools
import secrets
from typing import TYPE_CHECKING
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

    accounts: Mapped[list[Account]] = relationship(
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
        return _matches(password, self.password_hash)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username})>"


def password_matches(user: User | None, password: str) -> bool:
    """Whether there is such a user and `password` is theirs. With no user it
    checks a stand-in hash all the same, so the time a login takes doesn't
    tell whether a username exists (#204)."""
    if user is None:
        _matches(password, _stand_in_hash())
        return False
    return user.verify_password(password)


def _matches(password: str, password_hash: str) -> bool:
    try:
        encoded = password.encode('utf-8')
    except UnicodeEncodeError:  # a lone surrogate: not text, so never the password (#210)
        return False
    # bcrypt only reads 72 bytes and raises for more; a longer password never matches.
    if len(encoded) > 72:
        return False
    return bcrypt.checkpw(encoded, password_hash.encode('utf-8'))


@functools.cache
def _stand_in_hash() -> str:
    """A hash, at set_password's cost, of a random password nobody knows."""
    return bcrypt.hashpw(secrets.token_urlsafe(32).encode(), bcrypt.gensalt()).decode('utf-8')
