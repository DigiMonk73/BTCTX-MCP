"""
The CSV import's response shapes: the preview (rows, errors, warnings) and
the import result.
"""

from __future__ import annotations

from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
from datetime import datetime


class CSVRowPreview(BaseModel):
    """A single parsed row ready for preview display."""
    row_number: int
    date: datetime
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
    notes: Optional[str] = None


class CSVParseError(BaseModel):
    """An error or warning encountered during parsing."""
    row_number: int
    column: Optional[str] = None
    message: str
    severity: str  # "error" or "warning"


class CSVPreviewResponse(BaseModel):
    """Response from the preview endpoint."""
    success: bool
    total_rows: int
    valid_rows: int
    transactions: List[CSVRowPreview]
    errors: List[CSVParseError]
    warnings: List[CSVParseError]
    can_import: bool  # True only if no errors


class CSVImportResponse(BaseModel):
    """Response from the execute endpoint."""
    success: bool
    imported_count: int
    message: str


class DatabaseStatusResponse(BaseModel):
    """Response from the status endpoint."""
    is_empty: bool
    transaction_count: int
    message: str
