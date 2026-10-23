"""
An exchange (2.0 spec 5.1, 5.2): one exchange account, whose dollars and
bitcoin are two rows of accounts tied to it by exchange_id, named "<its
name> USD" and "<its name> BTC". Exchange 1, "Exchange", holds 1.x's
Exchange USD (3) and Exchange BTC (4).
"""

from sqlalchemy import Boolean, Column, Integer, String
from sqlalchemy.sql.expression import true as sa_true
from backend.database import Base


class Exchange(Base):
    __tablename__ = "exchanges"

    id = Column(Integer, primary_key=True, index=True)

    # Unique ignoring ASCII case, in the database itself (a restore included):
    # the backstop of the names' own rule (2.0 spec 5.1)
    name = Column(String(collation="NOCASE"), unique=True, nullable=False)

    sends_1099da = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sa_true(),
        doc="This exchange sends the owner a Form 1099-DA: it decides Form 8949's boxes for its sales.",
    )

    def __repr__(self):
        return f"<Exchange(id={self.id}, name={self.name}, sends_1099da={self.sends_1099da})>"
