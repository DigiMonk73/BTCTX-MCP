"""
Pydantic models for the JSON entry import (/api/import/entries).

This is the programmatic sibling of the CSV and River imports: callers
(the MCP server, scripts) send already-structured rows using account
NAMES, get a dry-run preview with dedup + simulated FIFO results, and
then execute the same rows atomically.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_serializer

from backend.database import RowId
from backend.schemas.transaction import eight_places


class EntryRow(BaseModel):
    """One proposed transaction. Same fields as a CSV template row."""
    date: str = Field(..., description="ISO8601 date or datetime; without an offset it is in the tax timezone, and a date alone means noon there.")
    type: str
    amount: Decimal
    from_account: str
    to_account: str
    cost_basis_usd: Decimal | None = None
    proceeds_usd: Decimal | None = None
    fee_amount: Decimal | None = None
    fee_currency: str | None = None
    source: str | None = None
    purpose: str | None = None
    fmv_usd: Decimal | None = None
    fee_usd: Decimal | None = None  # a BTC fee's USD value; omitted = fee x that hour's price
    acquired_at: str | None = Field(
        default=None,
        description="My BTC or Gift deposit: when the coins were originally acquired (by the giver, for a gift), "
                    "read like date. Omitted: the deposit's date. Inherited deposit: the date of death (required).",
    )
    not_a_duplicate_of: RowId | None = Field(
        default=None,
        description="Only when the user says this row is another transaction than the one the preview matched "
                    "as a duplicate: that transaction's id (the preview's matched_transaction_id). The row is "
                    "then saved, once (sent again, it's left out) (#253, #378). Beside an identical row "
                    "without it, both are refused as unclear (#497).",
    )


class EntryRequest(BaseModel):
    rows: list[EntryRow]


class FromPrice(BaseModel):
    """
    The values BitcoinTX filled in from a price, named as the transactions
    API names them (gross_proceeds_usd: a Spent's proceeds before its fee),
    and that price (#208, #145 plan 2.5): its UTC hour's start, or the day's
    ("moment"; an inheritance's: its date of death), where it came from and
    USD per BTC, as price_used gives them. The price is left out when the
    stored one no longer gives the value (priced elsewhere: an import).
    """
    values: list[str]
    at: str | None = None
    moment: str | None = None
    source: str | None = None
    usd_per_btc: Decimal | None = None


class SimulatedResult(BaseModel):
    """What the ledger computed for this row during the dry run."""
    cost_basis_usd: Decimal | None = None
    proceeds_usd: Decimal | None = None
    realized_gain_usd: Decimal | None = None
    holding_period: str | None = None
    gross_proceeds_usd: Decimal | None = None  # a sale's or Spent's proceeds before the fee
    fmv_usd: Decimal | None = None  # a gift's, donation's or lost coins' value
    fee_usd: Decimal | None = None  # a BTC fee's USD value
    from_price: FromPrice | None = None  # which of these came from a price, and that price (#208)


class EntryResult(BaseModel):
    row: int  # 1-based position in the submitted list
    status: str  # ready | duplicate | possible_duplicate | invalid | rejected | not_simulated
    normalized: dict[str, str | None] | None = None
    errors: list[str] = []
    warnings: list[str] = []
    matched_transaction_id: int | None = None
    autofilled_fields: list[str] = []  # USD fields filled from the historical BTC price
    simulated: SimulatedResult | None = None


class AffectedTransaction(BaseModel):
    """An existing transaction whose realized gain changes because of the new rows (backdating)."""
    id: int
    type: str
    date: datetime
    realized_gain_before: Decimal | None = None
    realized_gain_after: Decimal | None = None
    holding_period_before: str | None = None
    holding_period_after: str | None = None


class AccountBalance(BaseModel):
    account: str
    currency: str
    balance: Decimal

    @field_serializer("balance", when_used="json")
    def balance_written_out(self, v: Decimal) -> str:
        return eight_places(v)


class PastYearWarning(BaseModel):
    """
    The past-year warning (2.0 spec 5.8): the rows would change the figures
    of an earlier tax year, so the execute saves them only when sent again
    with ?confirm=<confirm>. `changes` are the rows whose figures move, as
    Ledger Review lists them, each with what moves and its tax years;
    `pending`, apart, what a save that recalculates also applies (with the
    AI key); `exact` false when the server ran out of time to work out
    exactly what moves, and names every year the rows can reach instead;
    `timezone` the one the rows' dates are in.
    """
    detail: str
    years: list[int]
    changes: list[dict[str, Any]]
    pending: list[dict[str, Any]]
    recalc_error: str | None = None
    exact: bool
    why_not_exact: str | None = None
    timezone: str
    confirm: str


class EntryPreviewResponse(BaseModel):
    ok: bool  # True when every row is ready or an exact duplicate
    ready_count: int
    duplicate_count: int
    possible_duplicate_count: int
    invalid_count: int
    rejected_count: int
    results: list[EntryResult]
    affected_existing: list[AffectedTransaction] = []
    balances_after: list[AccountBalance] = []
    past_years: PastYearWarning | None = None


class CreatedTransaction(BaseModel):
    row: int
    id: int
    type: str
    date: datetime
    amount: Decimal
    realized_gain_usd: Decimal | None = None
    holding_period: str | None = None
    from_price: FromPrice | None = None
    warnings: list[str] = []  # about its accounts: one hidden in Settings (2.0 spec 5.5)

    @field_serializer("amount", when_used="json")
    def amount_written_out(self, v: Decimal) -> str:
        return eight_places(v)


class EntryExecuteResponse(BaseModel):
    success: bool
    imported_count: int
    skipped_duplicates: int
    created: list[CreatedTransaction]
    message: str
