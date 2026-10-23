"""
The account API's request and response shapes (2.0 spec 5.9). An account's
kind and currency never change: none is taken after it's added, and the
currency comes from the kind.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class AccountCreate(BaseModel):
    """A bank, a wallet, or an exchange (its two accounts), with a name."""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["bank", "wallet", "exchange"]
    name: str


class AccountUpdate(BaseModel):
    """Rename an account (an exchange's: its exchange and both of its
    accounts), hide it from the pickers or show it again; at least one."""
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    hidden: bool | None = None

    @model_validator(mode="after")
    def _something_to_change(self) -> "AccountUpdate":
        if self.name is None and self.hidden is None:
            raise ValueError("Send a name, hidden, or both.")
        return self


class AccountRead(BaseModel):
    """An account as the API lists it: `exchange` is its exchange's name,
    `in_use` whether a transaction or a ledger line names it."""
    id: int
    name: str
    kind: str
    currency: str
    exchange_id: int | None
    exchange: str | None
    hidden: bool
    in_use: bool
