"""
backend/schemas/account.py

Defines Pydantic schemas for creating, updating, and reading Account objects.
We add optional validators to ensure 'currency' is one of ["USD","BTC"].
(Though we already have the main logic in the service layer.)
"""

from pydantic import BaseModel, field_validator, ConfigDict
from typing import Optional

VALID_CURRENCIES = {"USD", "BTC"}

class AccountBase(BaseModel):
    """
    Common fields for an Account, used by create/read/update.
    - 'name': a label like "Bank", "Wallet", "BTC Fees"
    - 'currency': "USD" or "BTC"
    """
    name: str
    currency: str

    @field_validator("currency")
    @classmethod
    def currency_must_be_valid(cls, v):
        if v not in VALID_CURRENCIES:
            raise ValueError("currency must be 'USD' or 'BTC'")
        return v

class AccountCreate(AccountBase):
    """
    Schema for creating a new Account. We require user_id because
    the DB schema has user_id as NOT NULL, referencing which user owns this account.
    """
    user_id: int

class AccountUpdate(BaseModel):
    """
    Schema for updating an existing Account record.
    Currently only 'name' or 'currency' can be updated, both optional.
    We also ensure currency is "USD"/"BTC" if provided.
    """
    name: Optional[str] = None
    currency: Optional[str] = None

    @field_validator("currency")
    @classmethod
    def currency_must_be_valid(cls, v):
        if v is not None and v not in VALID_CURRENCIES:
            raise ValueError("currency must be 'USD' or 'BTC'")
        return v

class AccountRead(AccountBase):
    """
    Schema returned after fetching an Account.
    Includes the DB-generated 'id' and the 'user_id' that references
    which user owns this account.
    """
    id: int
    user_id: int

    model_config = ConfigDict(from_attributes=True)