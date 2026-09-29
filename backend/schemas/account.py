"""
The account API's request and response shapes; a currency is USD or BTC.
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
    """A new account, owned by `user_id`."""
    user_id: int


class AccountUpdate(BaseModel):
    """The name or currency of an account, either optional."""
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