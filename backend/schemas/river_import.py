"""
The River import's shapes: the proposals the preview shows, and the rows
the user sends back to import.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel

from backend.schemas.csv_import import CSVParseError


class RiverProposalOut(BaseModel):
    """One proposed transaction shown in the import preview."""
    row_number: int
    date: datetime
    river_tag: Optional[str] = None
    type: str
    from_account: str
    to_account: str
    amount: Decimal
    cost_basis_usd: Optional[Decimal] = None
    proceeds_usd: Optional[Decimal] = None
    fee_amount: Optional[Decimal] = None
    fee_currency: Optional[str] = None
    source: Optional[str] = None
    purpose: Optional[str] = None
    type_choices: List[str] = []
    funding_choices: List[str] = []
    basis_autofilled: bool = False
    status: str  # "new" | "matched" | "discrepancy"
    matched_tx_id: Optional[int] = None
    discrepancy: Optional[str] = None


class RiverPreviewResponse(BaseModel):
    success: bool
    total_rows: int
    new_count: int
    matched_count: int
    discrepancy_count: int
    proposals: List[RiverProposalOut]
    errors: List[CSVParseError]
    warnings: List[CSVParseError]


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
    cost_basis_usd: Optional[Decimal] = None
    proceeds_usd: Optional[Decimal] = None
    fee_amount: Optional[Decimal] = None
    fee_currency: Optional[str] = None
    source: Optional[str] = None
    purpose: Optional[str] = None


class RiverExecuteRequest(BaseModel):
    rows: List[RiverExecuteRow]


class RiverImportResponse(BaseModel):
    success: bool
    imported_count: int
    skipped_existing: int
    message: str
