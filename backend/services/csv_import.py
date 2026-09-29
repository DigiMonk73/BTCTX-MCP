"""
The CSV import: the template, the check of every row of an uploaded file
(the errors and warnings the preview shows), and the import itself, all
rows or none, into an empty ledger.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from backend.models.transaction import Transaction
from backend.services.transaction import (
    DEPOSIT_BASIS_REQUIRED, DEPOSIT_SOURCE_UNKNOWN, DEPOSIT_SOURCES, create_transaction_record,
)
from backend.schemas.csv_import import CSVRowPreview, CSVParseError
from backend.services.tax_time import local_noon_utc
from backend.constants import (
    ACCOUNT_NAME_TO_ID,
    BROKER_REPORTING_TYPES,
    BROKER_REPORTING_VALUES,
    ACCOUNT_WALLET,
    ACCOUNT_BANK,
    ACCOUNT_EXCHANGE_USD,
    ACCOUNT_EXCHANGE_BTC,
    ACCOUNT_EXTERNAL,
    INCOME_SOURCES,
)

# Matched case-insensitively.
VALID_TYPES = {"deposit", "withdrawal", "transfer", "buy", "sell"}

REQUIRED_COLUMNS = {
    "date", "type", "amount", "from_account", "to_account"
}

# Every column, in order. The template, the import and the CSV export
# (routers/backup.py) all use this list, so an export always imports back to
# the same ledger. The last four came later and are optional (older files
# import as before): a BTC fee's USD value (blank: fee x that day's price), a
# gift's, donation's or lost BTC's fair market value, the Broker form
# override (none / proceeds / basis; blank: automatic), and whether that fee
# value was typed (yes, or blank) or priced from the day (no: kept, but
# priced again if the date or fee is edited).
CSV_COLUMNS = [
    "date", "type", "amount", "from_account", "to_account",
    "cost_basis_usd", "proceeds_usd", "fee_amount", "fee_currency",
    "source", "purpose", "notes",
    "fee_usd", "fmv_usd", "broker_reporting", "fee_usd_typed",
]

# Withdrawal purposes that aren't a sale; only these carry an FMV
GIFT_LIKE_PURPOSES = ("gift", "donation", "lost")

BTC_ACCOUNTS = (ACCOUNT_WALLET, ACCOUNT_EXCHANGE_BTC)
ACCOUNT_NAMES = "Bank, Wallet, Exchange USD, Exchange BTC, External"


@dataclass
class ParseResult:
    """Result of parsing a CSV file."""
    transactions: list[dict[str, Any]] = field(default_factory=list)
    previews: list[CSVRowPreview] = field(default_factory=list)
    errors: list[CSVParseError] = field(default_factory=list)
    warnings: list[CSVParseError] = field(default_factory=list)

    @property
    def can_import(self) -> bool:
        """True when there are rows and no errors (warnings are fine)."""
        return len(self.errors) == 0 and len(self.transactions) > 0


def parse_csv_file(content: bytes, tz=timezone.utc) -> ParseResult:
    """
    Every row of a CSV file checked, with its errors and warnings. `tz` is
    the tax timezone: a date without a timezone is local to it, and a date
    alone means noon there (as the MCP entry import reads it).
    """
    result = ParseResult()
    reader = csv.DictReader(io.StringIO(_decode(content)))
    header_error = _header_error(reader.fieldnames)
    if header_error:
        result.errors.append(header_error)
        return result

    previous_date: datetime | None = None
    for row_number, row in enumerate(reader, start=2):  # the header is row 1
        normalized = {k.lower().strip(): v.strip() if v else "" for k, v in row.items() if k}
        tx_data, preview, row_errors, row_warnings = _validate_row(normalized, row_number, tz)
        result.errors.extend(row_errors)
        result.warnings.extend(row_warnings)
        if tx_data and preview:
            if previous_date and preview.date < previous_date:
                result.warnings.append(_warning(
                    row_number, "date", "Row is not in chronological order. Import will sort by date.",
                ))
            previous_date = preview.date
            result.transactions.append(tx_data)
            result.previews.append(preview)

    if not result.transactions and not result.errors:
        result.errors.append(_file_error("No valid transactions found in file."))
    return result


def _decode(content: bytes) -> str:
    """UTF-8, with or without a byte-order mark (Excel's "CSV UTF-8" adds
    one; plain utf-8 would keep it in the first header), else Latin-1, which
    reads any bytes."""
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def _header_error(fieldnames) -> CSVParseError | None:
    if fieldnames is None:
        return _file_error("CSV file is empty or has no headers.")
    missing_columns = REQUIRED_COLUMNS - {h.lower().strip() for h in fieldnames if h}
    if missing_columns:
        return _file_error(f"Missing required columns: {', '.join(sorted(missing_columns))}")
    return None


def _file_error(message: str) -> CSVParseError:
    return CSVParseError(row_number=0, column=None, message=message, severity="error")


def _error(row_number: int, column: str, message: str) -> CSVParseError:
    return CSVParseError(row_number=row_number, column=column, message=message, severity="error")


def _warning(row_number: int, column: str, message: str) -> CSVParseError:
    return CSVParseError(row_number=row_number, column=column, message=message, severity="warning")


class _Rejected(Exception):
    """The row's errors: it isn't checked any further."""

    def __init__(self, *errors: CSVParseError):
        super().__init__()
        self.errors = list(errors)


@dataclass
class _Row:
    """A row's values once checked; account names as written, lower-cased."""
    number: int
    timestamp: datetime
    tx_type: str
    amount: Decimal
    from_name: str
    from_id: int
    to_name: str
    to_id: int
    cost_basis_usd: Decimal | None
    proceeds_usd: Decimal | None
    fee_amount: Decimal | None
    fee_usd: Decimal | None
    fmv_usd: Decimal | None
    fee_currency: str | None
    source: str | None
    purpose: str | None
    notes: str | None
    broker_reporting: str | None
    fee_usd_typed: str


def _validate_row(
    row: dict[str, str],
    row_number: int,
    tz=timezone.utc,
) -> tuple[dict[str, Any] | None, CSVRowPreview | None, list[CSVParseError], list[CSVParseError]]:
    """
    One row checked: (transaction data, preview, errors, warnings). The data
    and the preview are None when the row has errors; the checks stop at the
    first failing one.
    """
    warnings: list[CSVParseError] = []
    try:
        checked = _check_row(row, row_number, tz, warnings)
        errors, type_warnings = _validate_type_specific(checked)
        warnings.extend(type_warnings)
        if errors:
            raise _Rejected(*errors)
    except _Rejected as rejected:
        return None, None, rejected.errors, warnings
    return _transaction_data(checked, warnings), _preview(checked), [], warnings


def _check_row(row: dict[str, str], row_number: int, tz, warnings: list[CSVParseError]) -> _Row:
    """The row's values, in the order they're checked; _Rejected at the first
    that fails. A date in the future is a warning."""
    timestamp = _required_date(row, row_number, tz)
    if timestamp > datetime.now(timezone.utc):
        warnings.append(_warning(row_number, "date", "Date is in the future."))
    tx_type = _required_type(row, row_number)
    amount = _required_amount(row, row_number)
    from_name, from_id, to_name, to_id = _required_accounts(row, row_number)
    account_errors = _validate_accounts_for_type(tx_type, from_id, to_id, row_number)
    if account_errors:
        raise _Rejected(*account_errors)
    amounts = _optional_amounts(row, row_number)
    options = _options(row, row_number, tx_type)
    return _Row(row_number, timestamp, tx_type, amount, from_name, from_id, to_name, to_id, **amounts, **options)


def _required_date(row: dict[str, str], row_number: int, tz) -> datetime:
    date_str = row.get("date", "").strip()
    if not date_str:
        raise _Rejected(_error(row_number, "date", "Date is required."))
    timestamp = _parse_date(date_str, tz)
    if timestamp is None:
        raise _Rejected(_error(
            row_number, "date", f"Invalid date format: '{date_str}'. Use ISO8601 (e.g., 2024-01-15T10:30:00Z).",
        ))
    return timestamp


def _required_type(row: dict[str, str], row_number: int) -> str:
    tx_type = row.get("type", "").strip().lower()
    if not tx_type:
        raise _Rejected(_error(row_number, "type", "Transaction type is required."))
    if tx_type not in VALID_TYPES:
        raise _Rejected(_error(
            row_number, "type", f"Invalid type '{tx_type}'. Must be one of: Deposit, Withdrawal, Transfer, Buy, Sell.",
        ))
    return tx_type.title()


def _required_amount(row: dict[str, str], row_number: int) -> Decimal:
    amount_str = row.get("amount", "").strip()
    if not amount_str:
        raise _Rejected(_error(row_number, "amount", "Amount is required."))
    amount = _parse_decimal(amount_str, 8)
    if amount is None:
        raise _Rejected(_error(
            row_number, "amount",
            f"Invalid amount '{amount_str}'. Must be a positive number with up to 8 decimal places.",
        ))
    if amount <= 0:
        raise _Rejected(_error(row_number, "amount", "Amount must be positive."))
    return amount


def _required_accounts(row: dict[str, str], row_number: int) -> tuple[str, int, str, int]:
    """(from name, from id, to name, to id): both names given before either
    is looked up."""
    from_name = row.get("from_account", "").strip().lower()
    to_name = row.get("to_account", "").strip().lower()
    if not from_name:
        raise _Rejected(_error(row_number, "from_account", "From account is required."))
    if not to_name:
        raise _Rejected(_error(row_number, "to_account", "To account is required."))
    for column, name in (("from_account", from_name), ("to_account", to_name)):
        if name not in ACCOUNT_NAME_TO_ID:
            raise _Rejected(_error(row_number, column, f"Invalid account '{name}'. Must be one of: {ACCOUNT_NAMES}."))
    return from_name, ACCOUNT_NAME_TO_ID[from_name], to_name, ACCOUNT_NAME_TO_ID[to_name]


def _optional_amounts(row: dict[str, str], row_number: int) -> dict[str, Decimal | None]:
    """The optional numbers; every one that isn't valid is an error."""
    errors: list[CSVParseError] = []
    amounts = {
        column: _optional_decimal(row, column, places, row_number, errors)
        for column, places in (("cost_basis_usd", 2), ("proceeds_usd", 2), ("fee_amount", 8), ("fee_usd", 2),
                               ("fmv_usd", 2))
    }
    if errors:
        raise _Rejected(*errors)
    return amounts


def _options(row: dict[str, str], row_number: int, tx_type: str) -> dict[str, str | None]:
    """The text columns; fee_usd_typed, broker_reporting and fee_currency
    must be one of their values."""
    options = {
        "fee_currency": row.get("fee_currency", "").strip().upper() or None,
        "source": row.get("source", "").strip() or None,
        "purpose": row.get("purpose", "").strip() or None,
        "notes": row.get("notes", "").strip() or None,
        "broker_reporting": row.get("broker_reporting", "").strip().lower() or None,
        "fee_usd_typed": (row.get("fee_usd_typed") or "").strip().lower(),
    }
    if options["fee_usd_typed"] not in ("", "yes", "no"):
        raise _Rejected(_error(
            row_number, "fee_usd_typed", f"Invalid fee_usd_typed '{options['fee_usd_typed']}'. Must be yes, no or blank.",
        ))
    broker_reporting = options["broker_reporting"]
    if broker_reporting and broker_reporting not in BROKER_REPORTING_VALUES:
        raise _Rejected(_error(
            row_number, "broker_reporting",
            f"Invalid broker_reporting '{broker_reporting}'. Must be none, proceeds or basis (blank: automatic).",
        ))
    if broker_reporting and tx_type not in BROKER_REPORTING_TYPES:
        raise _Rejected(_error(
            row_number, "broker_reporting",
            f"broker_reporting can only be set on a Sell or Withdrawal, not a {tx_type}.",
        ))
    if options["fee_currency"] and options["fee_currency"] not in ("USD", "BTC"):
        raise _Rejected(_error(
            row_number, "fee_currency", f"Invalid fee currency '{options['fee_currency']}'. Must be USD or BTC.",
        ))
    return options


def _transaction_data(row: _Row, warnings: list[CSVParseError]) -> dict[str, Any]:
    """The row as create_transaction_record takes it. A fee_usd or fmv_usd
    the row can't carry is ignored with a warning."""
    tx_data: dict[str, Any] = {
        "type": row.tx_type,
        "timestamp": row.timestamp,
        "amount": row.amount,
        "from_account_id": row.from_id,
        "to_account_id": row.to_id,
    }
    tx_data.update(_amount_fields(row))
    if row.source:
        tx_data["source"] = row.source
    if row.purpose:
        tx_data["purpose"] = row.purpose
    tx_data.update(_fee_usd_fields(row, tx_data.get("fee_currency"), warnings))
    tx_data.update(_fmv_fields(row, warnings))
    if row.broker_reporting:
        tx_data["broker_reporting"] = row.broker_reporting
    return tx_data


def _amount_fields(row: _Row) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if row.cost_basis_usd is not None:
        fields["cost_basis_usd"] = row.cost_basis_usd
    if row.proceeds_usd is not None:
        fields["proceeds_usd"] = row.proceeds_usd
        if row.tx_type == "Sell":
            # Record the gross like the UI form does. Without it, every
            # scorched-earth recalculation re-derives net proceeds from the
            # already-net stored value and subtracts the USD fee again.
            fields["gross_proceeds_usd"] = row.proceeds_usd
    if row.fee_amount is not None and row.fee_amount > 0:
        fields["fee_amount"] = row.fee_amount
        fields["fee_currency"] = row.fee_currency or _default_fee_currency(row.tx_type, row.from_id)
    return fields


def _fee_usd_fields(row: _Row, fee_currency: str | None, warnings: list[CSVParseError]) -> dict[str, Any]:
    """A BTC fee's USD value, kept as given; "no" in fee_usd_typed marks it
    as priced from the day rather than typed."""
    if row.fee_usd is None:
        return {}
    if fee_currency != "BTC":
        warnings.append(_warning(
            row.number, "fee_usd", "fee_usd is ignored: it is the USD value of a BTC fee, and this row has none.",
        ))
        return {}
    if row.fee_usd_typed == "no":
        return {"fee_usd": row.fee_usd, "fee_usd_from_price": True}
    return {"fee_usd": row.fee_usd}


def _fmv_fields(row: _Row, warnings: list[CSVParseError]) -> dict[str, Any]:
    if row.fmv_usd is None:
        return {}
    if row.tx_type == "Withdrawal" and (row.purpose or "").lower() in GIFT_LIKE_PURPOSES:
        return {"fmv_usd": row.fmv_usd}
    warnings.append(_warning(row.number, "fmv_usd", "fmv_usd is ignored: it is for Gift, Donation and Lost withdrawals."))
    return {}


def _preview(row: _Row) -> CSVRowPreview:
    return CSVRowPreview(
        row_number=row.number,
        date=row.timestamp,
        type=row.tx_type,
        amount=row.amount,
        from_account=row.from_name.title(),
        to_account=row.to_name.title(),
        cost_basis_usd=row.cost_basis_usd,
        proceeds_usd=row.proceeds_usd,
        fee_amount=row.fee_amount,
        fee_currency=row.fee_currency,
        source=row.source,
        purpose=row.purpose,
        notes=row.notes,
    )


_DATE_FORMATS = [
    # (format, has a timezone, date only)
    ("%Y-%m-%dT%H:%M:%SZ", True, False),
    ("%Y-%m-%dT%H:%M:%S%z", True, False),
    ("%Y-%m-%d %H:%M:%S UTC", True, False),
    ("%Y-%m-%dT%H:%M:%S", False, False),
    ("%Y-%m-%d %H:%M:%S", False, False),
    ("%Y-%m-%d", False, True),
    ("%m/%d/%Y %H:%M:%S", False, False),
    ("%m/%d/%Y", False, True),
]


def _parse_date(date_str: str, tz=timezone.utc) -> datetime | None:
    """
    The date as a UTC datetime. A time without a timezone is local to `tz`
    (the tax timezone), and a date alone means noon there: read as UTC,
    "2024-01-01" would be Dec 31 2023 in a US tax timezone, another tax
    year. "Z", an offset or " UTC" is honored.
    """
    for fmt, has_tz, date_only in _DATE_FORMATS:
        try:
            dt = datetime.strptime(date_str, fmt)
        except ValueError:
            continue
        if fmt.endswith("Z") or fmt.endswith(" UTC"):
            dt = dt.replace(tzinfo=timezone.utc)
        if date_only:
            return local_noon_utc(dt.date(), tz)
        if not has_tz:
            dt = dt.replace(tzinfo=tz)
        return dt.astimezone(timezone.utc)

    return None


def _parse_decimal(value: str, max_decimals: int) -> Decimal | None:
    """
    The number, or None when it's empty, isn't a finite number or has more
    decimal places. Places are counted on the number, so "1E-9" doesn't
    pass as 0 decimals.
    """
    if not value:
        return None

    value = value.replace(",", "")  # thousands separators

    try:
        d = Decimal(value)
    except InvalidOperation:
        return None
    if not d.is_finite():
        return None
    exponent = d.normalize().as_tuple().exponent
    if exponent < 0 and -exponent > max_decimals:
        return None
    return d


def _optional_decimal(
    row: dict[str, str], column: str, max_decimals: int, row_number: int, errors: list[CSVParseError]
) -> Decimal | None:
    """
    An optional number: None when blank. A value that isn't a valid number
    is an error rather than dropped (a basis of "1.123" must not become "no
    basis").
    """
    raw = (row.get(column) or "").strip()
    if not raw:
        return None
    value = _parse_decimal(raw, max_decimals)
    if value is None:
        errors.append(_error(
            row_number, column, f"Invalid {column} '{raw}': a number with at most {max_decimals} decimal places.",
        ))
    elif value < 0:
        errors.append(_error(row_number, column, f"{column} can't be negative."))
        return None
    return value


# Each type's account rules: (column, broken(from_id, to_id), message), in the
# order they're reported.
_ACCOUNT_RULES = {
    "Deposit": [
        ("from_account", lambda f, t: f != ACCOUNT_EXTERNAL, "Deposit must have from_account = 'External'."),
        ("to_account", lambda f, t: t == ACCOUNT_EXTERNAL,
         "Deposit must have to_account as an internal account (not 'External')."),
    ],
    "Withdrawal": [
        ("from_account", lambda f, t: f == ACCOUNT_EXTERNAL,
         "Withdrawal must have from_account as an internal account (not 'External')."),
        ("to_account", lambda f, t: t != ACCOUNT_EXTERNAL, "Withdrawal must have to_account = 'External'."),
    ],
    "Transfer": [
        ("from_account", lambda f, t: f == ACCOUNT_EXTERNAL,
         "Transfer must have from_account as an internal account (not 'External')."),
        ("to_account", lambda f, t: t == ACCOUNT_EXTERNAL,
         "Transfer must have to_account as an internal account (not 'External')."),
        ("to_account", lambda f, t: f == t, "Transfer must have different from_account and to_account."),
    ],
    "Buy": [
        ("from_account", lambda f, t: f not in (ACCOUNT_BANK, ACCOUNT_EXCHANGE_USD),
         "Buy must have from_account = 'Bank' or 'Exchange USD'."),
        ("to_account", lambda f, t: t != ACCOUNT_EXCHANGE_BTC, "Buy must have to_account = 'Exchange BTC'."),
    ],
    "Sell": [
        ("from_account", lambda f, t: f != ACCOUNT_EXCHANGE_BTC, "Sell must have from_account = 'Exchange BTC'."),
        ("to_account", lambda f, t: t != ACCOUNT_EXCHANGE_USD, "Sell must have to_account = 'Exchange USD'."),
    ],
}


def _validate_accounts_for_type(tx_type: str, from_id: int, to_id: int, row_number: int) -> list[CSVParseError]:
    """Every account rule of the type the row breaks."""
    return [
        _error(row_number, column, message)
        for column, broken, message in _ACCOUNT_RULES.get(tx_type, [])
        if broken(from_id, to_id)
    ]


def _validate_type_specific(row: _Row) -> tuple[list[CSVParseError], list[CSVParseError]]:
    """The type's own rules: (errors, warnings)."""
    found = list(_TYPE_RULES[row.tx_type](row))
    return [f for f in found if f.severity == "error"], [f for f in found if f.severity == "warning"]


def _trade_rules(row: _Row):
    """A Buy needs its cost basis, a Sell its proceeds; both pay a USD fee."""
    column = "cost_basis_usd" if row.tx_type == "Buy" else "proceeds_usd"
    if getattr(row, column) is None:
        yield _error(row.number, column, f"{column} is required for {row.tx_type} transactions.")
    if row.fee_currency and row.fee_currency != "USD":
        yield _error(row.number, "fee_currency", f"{row.tx_type} fee must be in USD.")


def _deposit_rules(row: _Row):
    source = row.source
    into_btc = row.to_id in BTC_ACCOUNTS
    if source and source.lower() not in {c.lower() for c in DEPOSIT_SOURCES}:
        yield _error(row.number, "source", DEPOSIT_SOURCE_UNKNOWN)
    elif not row.cost_basis_usd and source and source.lower() in INCOME_SOURCES and into_btc:
        yield _warning(
            row.number, "cost_basis_usd",
            f"No cost_basis_usd for this {source} deposit. It will be valued at "
            "that day's BTC price (its market value at receipt, which is also the income).",
        )
    elif row.cost_basis_usd is None and into_btc:
        # A blank basis would make the whole value gain when it's sold.
        yield _error(row.number, "cost_basis_usd", DEPOSIT_BASIS_REQUIRED)


def _withdrawal_rules(row: _Row):
    if row.from_id not in BTC_ACCOUNTS:
        return
    purpose = (row.purpose or "").lower()
    if purpose not in ("spent", "gift", "donation", "lost"):
        yield _error(row.number, "purpose", "A BTC withdrawal needs a purpose: Spent, Gift, Donation or Lost.")
    if purpose == "spent" and row.proceeds_usd is None:
        yield _warning(
            row.number, "proceeds_usd",
            "Withdrawal with purpose='Spent' has no proceeds_usd. Will calculate from market value.",
        )


def _transfer_rules(row: _Row):
    # The fee is paid from the account sending: BTC between BTC accounts,
    # USD between Bank and Exchange USD.
    expected = "BTC" if row.from_id in BTC_ACCOUNTS else "USD"
    if row.fee_currency and row.fee_currency != expected:
        yield _error(row.number, "fee_currency", f"A transfer from this account pays its fee in {expected}.")


_TYPE_RULES = {
    "Buy": _trade_rules,
    "Sell": _trade_rules,
    "Deposit": _deposit_rules,
    "Withdrawal": _withdrawal_rules,
    "Transfer": _transfer_rules,
}


def _default_fee_currency(tx_type: str, from_account_id: int | None = None) -> str:
    """The fee currency when the row leaves it blank: USD for Buy/Sell and
    for moves out of a USD account, else BTC."""
    if tx_type in ("Buy", "Sell"):
        return "USD"
    if from_account_id in (ACCOUNT_BANK, ACCOUNT_EXCHANGE_USD):
        return "USD"
    return "BTC"


def check_database_empty(db: Session) -> tuple[bool, int]:
    """(whether the ledger is empty, how many transactions it has)."""
    count = db.query(Transaction).count()
    return count == 0, count


def execute_import(db: Session, transactions: list[dict[str, Any]]) -> int:
    """
    Save every transaction (parse_csv_file's) and commit once: if one is
    refused, none is saved. Returns how many were saved.
    """
    # By timestamp only; rows at the same time keep the file's order (a
    # stable sort). The ledger replays same-time transactions in the order
    # they were saved, and an export lists them in that order, so a round
    # trip gives back the same FIFO results. (A fixed type order here, e.g.
    # Transfer before Sell, changed which lots a same-time sale used.)
    sorted_txns = sorted(transactions, key=lambda x: x["timestamp"])

    imported_count = 0
    try:
        for tx_data in sorted_txns:
            create_transaction_record(tx_data, db, auto_commit=False)
            imported_count += 1
        db.commit()
        return imported_count
    except Exception:
        db.rollback()
        raise


# The template's sample rows, in date order: at least one of each type, both
# ways to buy (Exchange USD, and Bank for an auto-buy), every deposit source
# and withdrawal purpose. Their balances add up, so the file imports as it
# is. The columns a row doesn't give are left blank.
TEMPLATE_ROWS = [
    # USD in, and to the exchange
    ["2024-01-01T10:00:00Z", "Deposit", "20000.00", "External", "Bank",
     "", "", "", "", "", "", "Initial USD deposit to bank"],
    ["2024-01-02T10:00:00Z", "Transfer", "20000.00", "Bank", "Exchange USD",
     "", "", "", "", "", "", "Move USD to exchange for trading"],
    # Buys
    ["2024-01-03T10:00:00Z", "Buy", "0.5", "Exchange USD", "Exchange BTC",
     "10000.00", "", "50.00", "USD", "", "", "Buy 0.5 BTC at $20k/BTC with $50 fee"],
    ["2024-01-04T10:00:00Z", "Buy", "0.1", "Bank", "Exchange BTC",
     "2000.00", "", "10.00", "USD", "", "", "Auto-buy: Purchase BTC directly from bank"],
    # BTC deposits, every source
    ["2024-01-10T10:00:00Z", "Deposit", "1.0", "External", "Wallet",
     "20000.00", "", "", "", "MyBTC", "", "Transfer from my own cold storage"],
    ["2024-01-15T10:00:00Z", "Deposit", "0.1", "External", "Wallet",
     "0", "", "", "", "Gift", "", "BTC received as birthday gift (no cost basis)"],
    ["2024-01-20T10:00:00Z", "Deposit", "0.05", "External", "Wallet",
     "2500.00", "", "", "", "Income", "", "Payment received for freelance work"],
    ["2024-01-25T10:00:00Z", "Deposit", "0.02", "External", "Wallet",
     "1000.00", "", "", "", "Interest", "", "Interest earned from lending"],
    ["2024-01-30T10:00:00Z", "Deposit", "0.01", "External", "Wallet",
     "500.00", "", "", "", "Reward", "", "Mining or staking reward"],
    ["2024-01-31T10:00:00Z", "Deposit", "0.02", "External", "Wallet",
     "1000.00", "", "", "", "", "", "BTC deposit with no specific source"],
    # To the exchange, a sale, and the proceeds back to the bank
    ["2024-02-01T10:00:00Z", "Transfer", "0.5", "Wallet", "Exchange BTC",
     "", "", "0.0001", "BTC", "", "", "Move BTC to exchange for trading"],
    ["2024-02-10T10:00:00Z", "Sell", "0.3", "Exchange BTC", "Exchange USD",
     "", "18000.00", "10.00", "USD", "", "", "Sell 0.3 BTC for $18,000 with $10 fee"],
    ["2024-02-15T10:00:00Z", "Transfer", "15000.00", "Exchange USD", "Bank",
     "", "", "", "", "", "", "Move profits back to bank"],
    ["2024-02-20T10:00:00Z", "Transfer", "0.2", "Exchange BTC", "Wallet",
     "", "", "0.0001", "BTC", "", "", "Move BTC to wallet; fee_usd is what the fee was worth (blank: that day's price)",
     "5.20"],
    # Withdrawals: USD, then BTC for every purpose
    ["2024-03-01T10:00:00Z", "Withdrawal", "5000.00", "Bank", "External",
     "", "", "", "", "", "", "USD withdrawal for expenses"],
    ["2024-03-10T10:00:00Z", "Withdrawal", "0.15", "Wallet", "External",
     "", "9000.00", "0.0001", "BTC", "", "Spent", "Spent BTC on purchase (taxable event)"],
    ["2024-03-15T10:00:00Z", "Withdrawal", "0.1", "Wallet", "External",
     "", "", "0.0001", "BTC", "", "Gift", "Gifted BTC to family (non-taxable for giver); fmv_usd is its value that day",
     "", "6800.00"],
    ["2024-03-20T10:00:00Z", "Withdrawal", "0.05", "Wallet", "External",
     "", "", "0.0001", "BTC", "", "Donation", "Donated BTC to charity (non-taxable)"],
    ["2024-03-25T10:00:00Z", "Withdrawal", "0.03", "Wallet", "External",
     "", "", "", "", "", "Lost", "Lost access to BTC (no gain or loss; not on Form 8949)"],
]


def generate_template_csv() -> str:
    """The CSV template: the header and TEMPLATE_ROWS."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_COLUMNS)
    for cells in TEMPLATE_ROWS:
        writer.writerow(cells + [""] * (len(CSV_COLUMNS) - len(cells)))
    return output.getvalue()
