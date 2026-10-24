"""
The account API's request and response shapes (2.0 spec 5.9). An account's
kind and currency never change: none is taken after it's added, and the
currency comes from the kind. Renames come later (B8).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class AccountCreate(BaseModel):
    """A bank, a wallet, or an exchange (its two accounts), with a name."""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["bank", "wallet", "exchange"]
    name: str


class AccountUpdate(BaseModel):
    """Hide an account from the pickers, or show it again."""
    model_config = ConfigDict(extra="forbid")

    hidden: bool | None = None
    sends_1099da: bool | None = None  # TEMP: a stand-in for B6c's switch (#353), reverted before B6c merges in

    @model_validator(mode="after")
    def _one_change(self):  # TEMP, with the stand-in above
        if self.hidden is None and self.sends_1099da is None:
            raise ValueError("Nothing to change.")
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
