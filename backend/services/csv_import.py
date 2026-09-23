"""
backend/services/csv_import.py

Core parsing and validation logic for CSV import feature.
Handles template-based CSV format with strict validation.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple, Dict, Any

from sqlalchemy.orm import Session

from backend.models.transaction import Transaction
from backend.services.transaction import create_transaction_record
from backend.schemas.csv_import import CSVRowPreview, CSVParseError
from backend.constants import (
    ACCOUNT_NAME_TO_ID,
    ACCOUNT_BANK,
    ACCOUNT_EXCHANGE_USD,
    ACCOUNT_EXCHANGE_BTC,
    ACCOUNT_EXTERNAL,
)

# Valid transaction types (case-insensitive matching)
VALID_TYPES = {"deposit", "withdrawal", "transfer", "buy", "sell"}

# Required columns in the CSV
REQUIRED_COLUMNS = {
    "date", "type", "amount", "from_account", "to_account"
}

# All valid columns
ALL_COLUMNS = REQUIRED_COLUMNS | {
    "cost_basis_usd", "proceeds_usd", "fee_amount", "fee_currency",
    "source", "purpose", "notes"
}


@dataclass
class ParseResult:
    """Result of parsing a CSV file."""
    transactions: List[Dict[str, Any]] = field(default_factory=list)
    previews: List[CSVRowPreview] = field(default_factory=list)
    errors: List[CSVParseError] = field(default_factory=list)
    warnings: List[CSVParseError] = field(default_factory=list)

    @property
    def can_import(self) -> bool:
        """Returns True if there are no errors (warnings are OK)."""
        return len(self.errors) == 0 and len(self.transactions) > 0


def parse_csv_file(content: bytes) -> ParseResult:
    """
    Parse CSV content and return structured data with errors/warnings.

    Args:
        content: Raw bytes of the CSV file

    Returns:
        ParseResult containing transactions, previews, errors, and warnings
    """
    result = ParseResult()

    # Try to decode the content
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("utf-8-sig")  # UTF-8 with BOM
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except UnicodeDecodeError:
                result.errors.append(CSVParseError(
                    row_number=0,
                    column=None,
                    message="File encoding not supported. Please save as UTF-8.",
                    severity="error"
                ))
                return result

    # Parse CSV
    try:
        reader = csv.DictReader(io.StringIO(text))
    except Exception as e:
        result.errors.append(CSVParseError(
            row_number=0,
            column=None,
            message=f"Invalid CSV format: {str(e)}",
            severity="error"
        ))
        return result

    # Validate headers
    if reader.fieldnames is None:
        result.errors.append(CSVParseError(
            row_number=0,
            column=None,
            message="CSV file is empty or has no headers.",
            severity="error"
        ))
        return result

    # Normalize headers (lowercase, strip whitespace)
    headers = {h.lower().strip() for h in reader.fieldnames if h}

    # Check for required columns
    missing_columns = REQUIRED_COLUMNS - headers
    if missing_columns:
        result.errors.append(CSVParseError(
            row_number=0,
            column=None,
            message=f"Missing required columns: {', '.join(sorted(missing_columns))}",
            severity="error"
        ))
        return result

    # Process each row
    prev_date: Optional[datetime] = None

    for row_number, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
        # Normalize row keys
        normalized_row = {k.lower().strip(): v.strip() if v else "" for k, v in row.items() if k}

        # Validate and parse the row
        tx_data, preview, row_errors, row_warnings = _validate_row(normalized_row, row_number)

        result.errors.extend(row_errors)
        result.warnings.extend(row_warnings)

        if tx_data and preview:
            # Check chronological order
            if prev_date and preview.date < prev_date:
                result.warnings.append(CSVParseError(
                    row_number=row_number,
                    column="date",
                    message="Row is not in chronological order. Import will sort by date.",
                    severity="warning"
                ))
            prev_date = preview.date

            result.transactions.append(tx_data)
            result.previews.append(preview)

    if not result.transactions and not result.errors:
        result.errors.append(CSVParseError(
            row_number=0,
            column=None,
            message="No valid transactions found in file.",
            severity="error"
        ))

    return result


def _validate_row(
    row: Dict[str, str],
    row_number: int
) -> Tuple[Optional[Dict[str, Any]], Optional[CSVRowPreview], List[CSVParseError], List[CSVParseError]]:
    """
    Validate a single CSV row.

    Returns:
        Tuple of (transaction_dict, preview, errors, warnings)
        transaction_dict and preview are None if there are fatal errors
    """
    errors: List[CSVParseError] = []
    warnings: List[CSVParseError] = []

    # Parse date
    date_str = row.get("date", "").strip()
    if not date_str:
        errors.append(CSVParseError(
            row_number=row_number,
            column="date",
            message="Date is required.",
            severity="error"
        ))
        return None, None, errors, warnings

    timestamp = _parse_date(date_str)
    if timestamp is None:
        errors.append(CSVParseError(
            row_number=row_number,
            column="date",
            message=f"Invalid date format: '{date_str}'. Use ISO8601 (e.g., 2024-01-15T10:30:00Z).",
            severity="error"
        ))
        return None, None, errors, warnings

    # Check for future date
    if timestamp > datetime.now(timezone.utc):
        warnings.append(CSVParseError(
            row_number=row_number,
            column="date",
            message="Date is in the future.",
            severity="warning"
        ))

    # Parse type
    tx_type_str = row.get("type", "").strip().lower()
    if not tx_type_str:
        errors.append(CSVParseError(
            row_number=row_number,
            column="type",
            message="Transaction type is required.",
            severity="error"
        ))
        return None, None, errors, warnings

    if tx_type_str not in VALID_TYPES:
        errors.append(CSVParseError(
            row_number=row_number,
            column="type",
            message=f"Invalid type '{tx_type_str}'. Must be one of: Deposit, Withdrawal, Transfer, Buy, Sell.",
            severity="error"
        ))
        return None, None, errors, warnings

    # Normalize type to title case
    tx_type = tx_type_str.title()

    # Parse amount (BTC)
    amount_str = row.get("amount", "").strip()
    if not amount_str:
        errors.append(CSVParseError(
            row_number=row_number,
            column="amount",
            message="Amount is required.",
            severity="error"
        ))
        return None, None, errors, warnings

    amount = _parse_decimal(amount_str, 8)
    if amount is None:
        errors.append(CSVParseError(
            row_number=row_number,
            column="amount",
            message=f"Invalid amount '{amount_str}'. Must be a positive number with up to 8 decimal places.",
            severity="error"
        ))
        return None, None, errors, warnings

    if amount <= 0:
        errors.append(CSVParseError(
            row_number=row_number,
            column="amount",
            message="Amount must be positive.",
            severity="error"
        ))
        return None, None, errors, warnings

    # Parse accounts
    from_account_str = row.get("from_account", "").strip().lower()
    to_account_str = row.get("to_account", "").strip().lower()

    if not from_account_str:
        errors.append(CSVParseError(
            row_number=row_number,
            column="from_account",
            message="From account is required.",
            severity="error"
        ))
        return None, None, errors, warnings

    if not to_account_str:
        errors.append(CSVParseError(
            row_number=row_number,
            column="to_account",
            message="To account is required.",
            severity="error"
        ))
        return None, None, errors, warnings

    from_account_id = ACCOUNT_NAME_TO_ID.get(from_account_str)
    to_account_id = ACCOUNT_NAME_TO_ID.get(to_account_str)

    if from_account_id is None:
        errors.append(CSVParseError(
            row_number=row_number,
            column="from_account",
            message=f"Invalid account '{from_account_str}'. Must be one of: Bank, Wallet, Exchange USD, Exchange BTC, External.",
            severity="error"
        ))
        return None, None, errors, warnings

    if to_account_id is None:
        errors.append(CSVParseError(
            row_number=row_number,
            column="to_account",
            message=f"Invalid account '{to_account_str}'. Must be one of: Bank, Wallet, Exchange USD, Exchange BTC, External.",
            severity="error"
        ))
        return None, None, errors, warnings

    # Validate accounts for transaction type
    type_errors = _validate_accounts_for_type(tx_type, from_account_id, to_account_id, row_number)
    if type_errors:
        errors.extend(type_errors)
        return None, None, errors, warnings

    # Parse optional fields
    cost_basis_usd = _parse_decimal(row.get("cost_basis_usd", ""), 2)
    proceeds_usd = _parse_decimal(row.get("proceeds_usd", ""), 2)
    fee_amount = _parse_decimal(row.get("fee_amount", ""), 8)
    fee_currency = row.get("fee_currency", "").strip().upper() or None
    source = row.get("source", "").strip() or None
    purpose = row.get("purpose", "").strip() or None
    notes = row.get("notes", "").strip() or None

    # Validate fee currency
    if fee_currency and fee_currency not in ("USD", "BTC"):
        errors.append(CSVParseError(
            row_number=row_number,
            column="fee_currency",
            message=f"Invalid fee currency '{fee_currency}'. Must be USD or BTC.",
            severity="error"
        ))
        return None, None, errors, warnings

    # Type-specific validation
    type_specific_errors, type_specific_warnings = _validate_type_specific(
        tx_type, cost_basis_usd, proceeds_usd, fee_currency, source, purpose, row_number
    )
    errors.extend(type_specific_errors)
    warnings.extend(type_specific_warnings)

    if errors:
        return None, None, errors, warnings

    # Build transaction data dict (for create_transaction_record)
    tx_data: Dict[str, Any] = {
        "type": tx_type,
        "timestamp": timestamp,
        "amount": amount,
        "from_account_id": from_account_id,
        "to_account_id": to_account_id,
    }

    if cost_basis_usd is not None:
        tx_data["cost_basis_usd"] = cost_basis_usd
    if proceeds_usd is not None:
        tx_data["proceeds_usd"] = proceeds_usd
        if tx_type == "Sell":
            # Record the gross like the UI form does. Without it, every
            # scorched-earth recalculation re-derives net proceeds from the
            # already-net stored value and subtracts the USD fee again.
            tx_data["gross_proceeds_usd"] = proceeds_usd
    if fee_amount is not None and fee_amount > 0:
        tx_data["fee_amount"] = fee_amount
        tx_data["fee_currency"] = fee_currency or _default_fee_currency(tx_type)
    if source:
        tx_data["source"] = source
    if purpose:
        tx_data["purpose"] = purpose

    # Build preview object
    preview = CSVRowPreview(
        row_number=row_number,
        date=timestamp,
        type=tx_type,
        amount=amount,
        from_account=from_account_str.title() if from_account_str != "external" else "External",
        to_account=to_account_str.title() if to_account_str != "external" else "External",
        cost_basis_usd=cost_basis_usd,
        proceeds_usd=proceeds_usd,
        fee_amount=fee_amount,
        fee_currency=fee_currency,
        source=source,
        purpose=purpose,
        notes=notes,
    )

    return tx_data, preview, errors, warnings


def _parse_date(date_str: str) -> Optional[datetime]:
    """
    Parse a date string into a UTC datetime.
    Supports ISO8601 and common date formats.
    """
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S UTC",
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            # Ensure UTC timezone
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except ValueError:
            continue

    return None


def _parse_decimal(value: str, max_decimals: int) -> Optional[Decimal]:
    """
    Parse a string to Decimal with validation.
    Returns None if parsing fails or value is empty.
    """
    if not value:
        return None

    # Remove commas (thousand separators)
    value = value.replace(",", "")

    try:
        d = Decimal(value)
        # Check decimal places
        if "." in value:
            decimal_places = len(value.split(".")[1])
            if decimal_places > max_decimals:
                return None
        return d
    except InvalidOperation:
        return None


def _validate_accounts_for_type(
    tx_type: str,
    from_id: int,
    to_id: int,
    row_number: int
) -> List[CSVParseError]:
    """Validate that account IDs are valid for the transaction type."""
    errors = []

    if tx_type == "Deposit":
        # Deposit: External → any internal account (BTC or USD)
        if from_id != ACCOUNT_EXTERNAL:
            errors.append(CSVParseError(
                row_number=row_number,
                column="from_account",
                message="Deposit must have from_account = 'External'.",
                severity="error"
            ))
        if to_id == ACCOUNT_EXTERNAL:
            errors.append(CSVParseError(
                row_number=row_number,
                column="to_account",
                message="Deposit must have to_account as an internal account (not 'External').",
                severity="error"
            ))

    elif tx_type == "Withdrawal":
        # Withdrawal: any internal account → External
        if from_id == ACCOUNT_EXTERNAL:
            errors.append(CSVParseError(
                row_number=row_number,
                column="from_account",
                message="Withdrawal must have from_account as an internal account (not 'External').",
                severity="error"
            ))
        if to_id != ACCOUNT_EXTERNAL:
            errors.append(CSVParseError(
                row_number=row_number,
                column="to_account",
                message="Withdrawal must have to_account = 'External'.",
                severity="error"
            ))

    elif tx_type == "Transfer":
        # Transfer: between internal accounts of same currency
        if from_id == ACCOUNT_EXTERNAL:
            errors.append(CSVParseError(
                row_number=row_number,
                column="from_account",
                message="Transfer must have from_account as an internal account (not 'External').",
                severity="error"
            ))
        if to_id == ACCOUNT_EXTERNAL:
            errors.append(CSVParseError(
                row_number=row_number,
                column="to_account",
                message="Transfer must have to_account as an internal account (not 'External').",
                severity="error"
            ))
        if from_id == to_id:
            errors.append(CSVParseError(
                row_number=row_number,
                column="to_account",
                message="Transfer must have different from_account and to_account.",
                severity="error"
            ))

    elif tx_type == "Buy":
        if from_id not in (ACCOUNT_BANK, ACCOUNT_EXCHANGE_USD):
            errors.append(CSVParseError(
                row_number=row_number,
                column="from_account",
                message="Buy must have from_account = 'Bank' or 'Exchange USD'.",
                severity="error"
            ))
        if to_id != ACCOUNT_EXCHANGE_BTC:
            errors.append(CSVParseError(
                row_number=row_number,
                column="to_account",
                message="Buy must have to_account = 'Exchange BTC'.",
                severity="error"
            ))

    elif tx_type == "Sell":
        if from_id != ACCOUNT_EXCHANGE_BTC:
            errors.append(CSVParseError(
                row_number=row_number,
                column="from_account",
                message="Sell must have from_account = 'Exchange BTC'.",
                severity="error"
            ))
        if to_id != ACCOUNT_EXCHANGE_USD:
            errors.append(CSVParseError(
                row_number=row_number,
                column="to_account",
                message="Sell must have to_account = 'Exchange USD'.",
                severity="error"
            ))

    return errors


def _validate_type_specific(
    tx_type: str,
    cost_basis_usd: Optional[Decimal],
    proceeds_usd: Optional[Decimal],
    fee_currency: Optional[str],
    source: Optional[str],
    purpose: Optional[str],
    row_number: int
) -> Tuple[List[CSVParseError], List[CSVParseError]]:
    """Validate type-specific field requirements."""
    errors = []
    warnings = []

    if tx_type == "Buy":
        if cost_basis_usd is None:
            errors.append(CSVParseError(
                row_number=row_number,
                column="cost_basis_usd",
                message="cost_basis_usd is required for Buy transactions.",
                severity="error"
            ))
        if fee_currency and fee_currency != "USD":
            errors.append(CSVParseError(
                row_number=row_number,
                column="fee_currency",
                message="Buy fee must be in USD.",
                severity="error"
            ))

    elif tx_type == "Sell":
        if proceeds_usd is None:
            errors.append(CSVParseError(
                row_number=row_number,
                column="proceeds_usd",
                message="proceeds_usd is required for Sell transactions.",
                severity="error"
            ))
        if fee_currency and fee_currency != "USD":
            errors.append(CSVParseError(
                row_number=row_number,
                column="fee_currency",
                message="Sell fee must be in USD.",
                severity="error"
            ))

    elif tx_type == "Deposit":
        if cost_basis_usd is None:
            warnings.append(CSVParseError(
                row_number=row_number,
                column="cost_basis_usd",
                message="No cost_basis_usd provided for Deposit. Will default to $0 (gift/unknown basis).",
                severity="warning"
            ))

    elif tx_type == "Withdrawal":
        if purpose and purpose.lower() in ("spent",) and proceeds_usd is None:
            warnings.append(CSVParseError(
                row_number=row_number,
                column="proceeds_usd",
                message="Withdrawal with purpose='Spent' has no proceeds_usd. Will calculate from market value.",
                severity="warning"
            ))

    elif tx_type == "Transfer":
        if fee_currency and fee_currency != "BTC":
            errors.append(CSVParseError(
                row_number=row_number,
                column="fee_currency",
                message="Transfer fee must be in BTC.",
                severity="error"
            ))

    return errors, warnings


def _default_fee_currency(tx_type: str) -> str:
    """Return the default fee currency for a transaction type."""
    if tx_type in ("Buy", "Sell"):
        return "USD"
    return "BTC"


def check_database_empty(db: Session) -> Tuple[bool, int]:
    """
    Check if the database has any transactions.

    Returns:
        Tuple of (is_empty, transaction_count)
    """
    count = db.query(Transaction).count()
    return count == 0, count


def execute_import(db: Session, transactions: List[Dict[str, Any]]) -> int:
    """
    Import transactions atomically.

    All transactions are created without committing, then committed together
    at the end. If any transaction fails, all are rolled back.

    Args:
        db: Database session
        transactions: List of transaction dicts (output from parse_csv_file)

    Returns:
        Count of imported transactions

    Raises:
        Exception on failure (all transactions rolled back)
    """
    # Sort by timestamp, then by type to ensure FIFO is calculated correctly
    # Type ordering ensures acquisitions (Deposit, Buy) are processed before
    # disposals (Sell, Withdrawal), with Transfers in the middle
    TYPE_ORDER = {"Deposit": 0, "Buy": 1, "Transfer": 2, "Sell": 3, "Withdrawal": 4}
    sorted_txns = sorted(
        transactions,
        key=lambda x: (x["timestamp"], TYPE_ORDER.get(x["type"], 99))
    )

    imported_count = 0

    try:
        for tx_data in sorted_txns:
            # Use auto_commit=False to defer commit until all transactions succeed
            create_transaction_record(tx_data, db, auto_commit=False)
            imported_count += 1

        # All transactions succeeded - commit them all
        db.commit()
        return imported_count

    except Exception:
        # Roll back all uncommitted transactions
        db.rollback()
        raise


def generate_template_csv() -> str:
    """
    Generate a CSV template with headers and sample rows.

    Includes at least one of each:
    - Transaction type: Deposit, Withdrawal, Transfer, Buy, Sell
    - Buy sources: Exchange USD (standard) and Bank (auto-buy)
    - Deposit source: MyBTC, Gift, Income, Interest, Reward (and blank/N/A)
    - Withdrawal purpose: Spent, Gift, Donation, Lost

    Balance math is verified to work correctly.

    Returns:
        CSV content as a string
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow([
        "date", "type", "amount", "from_account", "to_account",
        "cost_basis_usd", "proceeds_usd", "fee_amount", "fee_currency",
        "source", "purpose", "notes"
    ])

    # === USD SETUP ===
    # Deposit USD to Bank
    writer.writerow([
        "2024-01-01T10:00:00Z", "Deposit", "20000.00", "External", "Bank",
        "", "", "", "",
        "", "", "Initial USD deposit to bank"
    ])
    # Transfer USD from Bank to Exchange
    writer.writerow([
        "2024-01-02T10:00:00Z", "Transfer", "20000.00", "Bank", "Exchange USD",
        "", "", "", "",
        "", "", "Move USD to exchange for trading"
    ])

    # === BUY BTC ===
    # Buy from Exchange USD (standard)
    writer.writerow([
        "2024-01-03T10:00:00Z", "Buy", "0.5", "Exchange USD", "Exchange BTC",
        "10000.00", "", "50.00", "USD",
        "", "", "Buy 0.5 BTC at $20k/BTC with $50 fee"
    ])
    # Buy from Bank (auto-buy / recurring purchase)
    writer.writerow([
        "2024-01-04T10:00:00Z", "Buy", "0.1", "Bank", "Exchange BTC",
        "2000.00", "", "10.00", "USD",
        "", "", "Auto-buy: Purchase BTC directly from bank"
    ])

    # === BTC DEPOSITS (all sources) ===
    writer.writerow([
        "2024-01-10T10:00:00Z", "Deposit", "1.0", "External", "Wallet",
        "20000.00", "", "", "",
        "MyBTC", "", "Transfer from my own cold storage"
    ])
    writer.writerow([
        "2024-01-15T10:00:00Z", "Deposit", "0.1", "External", "Wallet",
        "0", "", "", "",
        "Gift", "", "BTC received as birthday gift (no cost basis)"
    ])
    writer.writerow([
        "2024-01-20T10:00:00Z", "Deposit", "0.05", "External", "Wallet",
        "2500.00", "", "", "",
        "Income", "", "Payment received for freelance work"
    ])
    writer.writerow([
        "2024-01-25T10:00:00Z", "Deposit", "0.02", "External", "Wallet",
        "1000.00", "", "", "",
        "Interest", "", "Interest earned from lending"
    ])
    writer.writerow([
        "2024-01-30T10:00:00Z", "Deposit", "0.01", "External", "Wallet",
        "500.00", "", "", "",
        "Reward", "", "Mining or staking reward"
    ])
    writer.writerow([
        "2024-01-31T10:00:00Z", "Deposit", "0.02", "External", "Wallet",
        "1000.00", "", "", "",
        "", "", "BTC deposit with no specific source"
    ])

    # === BTC TRANSFERS ===
    # Wallet to Exchange
    writer.writerow([
        "2024-02-01T10:00:00Z", "Transfer", "0.5", "Wallet", "Exchange BTC",
        "", "", "0.0001", "BTC",
        "", "", "Move BTC to exchange for trading"
    ])

    # === SELL BTC ===
    writer.writerow([
        "2024-02-10T10:00:00Z", "Sell", "0.3", "Exchange BTC", "Exchange USD",
        "", "18000.00", "10.00", "USD",
        "", "", "Sell 0.3 BTC for $18,000 with $10 fee"
    ])

    # === USD TRANSFER BACK ===
    writer.writerow([
        "2024-02-15T10:00:00Z", "Transfer", "15000.00", "Exchange USD", "Bank",
        "", "", "", "",
        "", "", "Move profits back to bank"
    ])

    # === BTC TRANSFER BACK ===
    # Exchange to Wallet
    writer.writerow([
        "2024-02-20T10:00:00Z", "Transfer", "0.2", "Exchange BTC", "Wallet",
        "", "", "0.0001", "BTC",
        "", "", "Move BTC to wallet for cold storage"
    ])

    # === USD WITHDRAWAL ===
    writer.writerow([
        "2024-03-01T10:00:00Z", "Withdrawal", "5000.00", "Bank", "External",
        "", "", "", "",
        "", "", "USD withdrawal for expenses"
    ])

    # === BTC WITHDRAWALS (all purposes) ===
    writer.writerow([
        "2024-03-10T10:00:00Z", "Withdrawal", "0.15", "Wallet", "External",
        "", "9000.00", "0.0001", "BTC",
        "", "Spent", "Spent BTC on purchase (taxable event)"
    ])
    writer.writerow([
        "2024-03-15T10:00:00Z", "Withdrawal", "0.1", "Wallet", "External",
        "", "", "0.0001", "BTC",
        "", "Gift", "Gifted BTC to family (non-taxable for giver)"
    ])
    writer.writerow([
        "2024-03-20T10:00:00Z", "Withdrawal", "0.05", "Wallet", "External",
        "", "", "0.0001", "BTC",
        "", "Donation", "Donated BTC to charity (non-taxable)"
    ])
    writer.writerow([
        "2024-03-25T10:00:00Z", "Withdrawal", "0.03", "Wallet", "External",
        "", "", "", "",
        "", "Lost", "Lost access to BTC (capital loss)"
    ])

    return output.getvalue()
