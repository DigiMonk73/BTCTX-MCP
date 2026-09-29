"""
The CSV import's response shapes: the preview (rows, errors, warnings) and
the import result.
"""

from __future__ import annotations

from pydantic import BaseModel
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
    cost_basis_usd: Decimal | None = None
    proceeds_usd: Decimal | None = None
    fee_amount: Decimal | None = None
    fee_currency: str | None = None
    source: str | None = None
    purpose: str | None = None
    notes: str | None = None


class CSVParseError(BaseModel):
    """An error or warning encountered during parsing."""
    row_number: int
    column: str | None = None
    message: str
    severity: str  # "error" or "warning"


class CSVPreviewResponse(BaseModel):
    """Response from the preview endpoint."""
    success: bool
    total_rows: int
    valid_rows: int
    transactions: list[CSVRowPreview]
    errors: list[CSVParseError]
    warnings: list[CSVParseError]
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
