"""
backend/schemas/entry_import.py

Pydantic models for the JSON entry import (/api/import/entries).

This is the programmatic sibling of the CSV and River imports: callers
(the MCP server, scripts) send already-structured rows using account
NAMES, get a dry-run preview with dedup + simulated FIFO results, and
then execute the same rows atomically.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class EntryRow(BaseModel):
    """One proposed transaction. Same fields as a CSV template row."""
    date: str = Field(..., description="ISO8601 date or datetime; UTC when no offset is given.")
    type: str
    amount: Decimal
    from_account: str
    to_account: str
    cost_basis_usd: Optional[Decimal] = None
    proceeds_usd: Optional[Decimal] = None
    fee_amount: Optional[Decimal] = None
    fee_currency: Optional[str] = None
    source: Optional[str] = None
    purpose: Optional[str] = None
    fmv_usd: Optional[Decimal] = None


class EntryRequest(BaseModel):
    rows: List[EntryRow]


class SimulatedResult(BaseModel):
    """What the ledger computed for this row during the dry run."""
    cost_basis_usd: Optional[Decimal] = None
    proceeds_usd: Optional[Decimal] = None
    realized_gain_usd: Optional[Decimal] = None
    holding_period: Optional[str] = None


class EntryResult(BaseModel):
    row: int  # 1-based position in the submitted list
    status: str  # ready | duplicate | possible_duplicate | invalid | rejected | not_simulated
    normalized: Optional[Dict[str, Optional[str]]] = None
    errors: List[str] = []
    warnings: List[str] = []
    matched_transaction_id: Optional[int] = None
    autofilled_fields: List[str] = []  # USD fields filled from the historical BTC price
    simulated: Optional[SimulatedResult] = None


class AffectedTransaction(BaseModel):
    """An existing transaction whose realized gain changes because of the new rows (backdating)."""
    id: int
    type: str
    date: datetime
    realized_gain_before: Optional[Decimal] = None
    realized_gain_after: Optional[Decimal] = None
    holding_period_before: Optional[str] = None
    holding_period_after: Optional[str] = None


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
    results: List[EntryResult]
    affected_existing: List[AffectedTransaction] = []
    balances_after: List[AccountBalance] = []


class CreatedTransaction(BaseModel):
    row: int
    id: int
    type: str
    date: datetime
    amount: Decimal
    realized_gain_usd: Optional[Decimal] = None
    holding_period: Optional[str] = None


class EntryExecuteResponse(BaseModel):
    success: bool
    imported_count: int
    skipped_duplicates: int
    created: List[CreatedTransaction]
    message: str
