"""
The River import's shapes: the proposals the preview shows, and the rows
the user sends back to import.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from backend.schemas.csv_import import CSVParseError


class RiverProposalOut(BaseModel):
    """One proposed transaction shown in the import preview."""
    row_number: int
    date: datetime
    river_tag: str | None = None
    type: str
    from_account: str
    to_account: str
    amount: Decimal
    cost_basis_usd: Decimal | None = None
    proceeds_usd: Decimal | None = None
    fee_amount: Decimal | None = None
    fee_currency: str | None = None
    source: str | None = None
    purpose: str | None = None
    type_choices: list[str] = []
    funding_choices: list[str] = []
    basis_autofilled: bool = False
    status: str  # "new" | "matched" | "discrepancy"
    matched_tx_id: int | None = None
    discrepancy: str | None = None


class RiverPreviewResponse(BaseModel):
    success: bool
    total_rows: int
    new_count: int
    matched_count: int
    discrepancy_count: int
    proposals: list[RiverProposalOut]
    errors: list[CSVParseError]
    warnings: list[CSVParseError]


class RiverExecuteRow(BaseModel):
    """
    A final row to import — the preview proposal after any user edits
    (funding toggle, type reclassification, basis/fee edits).
    """
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


class RiverExecuteRequest(BaseModel):
    rows: list[RiverExecuteRow]


class RiverImportResponse(BaseModel):
    success: bool
    imported_count: int
    skipped_existing: int
    message: str
