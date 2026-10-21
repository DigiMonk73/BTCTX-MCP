"""
The account API's request and response shapes; a currency is USD or BTC.
"""

from typing import Literal

from pydantic import BaseModel, field_validator, ConfigDict

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


class AccountCreate(BaseModel):
    """A new account (spec 5.9): its kind and name; the currency comes from the kind."""
    kind: Literal["bank", "wallet", "exchange"]
    name: str


class AccountUpdate(BaseModel):
    """Hide or show an account, an exchange's 1099-DA switch; `name` only unchanged
    on this draft branch (renames are B8's)."""
    name: str | None = None
    hidden: bool | None = None
    sends_1099da: bool | None = None


class AccountRead(AccountBase):
    """
    Schema returned after fetching an Account.
    Includes the DB-generated 'id' and the 'user_id' that references
    which user owns this account.
    """
    id: int
    user_id: int

    model_config = ConfigDict(from_attributes=True)

class LedgerAccountRead(BaseModel):
    """An account as 2.0's list gives it (spec 5.9): `name` is the owner's
    nickname; an exchange's two accounts share `exchange_id`, and `exchange`
    is that exchange's name; `in_use` when a transaction names it."""
    id: int
    name: str
    kind: str
    currency: str
    exchange_id: int | None
    exchange: str | None
    sends_1099da: bool | None  # the exchange's switch (5.9); None on any other account
    hidden: bool
    in_use: bool
