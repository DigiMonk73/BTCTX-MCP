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

from pydantic import BaseModel, Field


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
    fee_usd: Decimal | None = None  # a BTC fee's USD value; omitted = fee x that day's price


class EntryRequest(BaseModel):
    rows: list[EntryRow]


class SimulatedResult(BaseModel):
    """What the ledger computed for this row during the dry run."""
    cost_basis_usd: Decimal | None = None
    proceeds_usd: Decimal | None = None
    realized_gain_usd: Decimal | None = None
    holding_period: str | None = None


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


class CreatedTransaction(BaseModel):
    row: int
    id: int
    type: str
    date: datetime
    amount: Decimal
    realized_gain_usd: Decimal | None = None
    holding_period: str | None = None


class EntryExecuteResponse(BaseModel):
    success: bool
    imported_count: int
    skipped_duplicates: int
    created: list[CreatedTransaction]
    message: str
