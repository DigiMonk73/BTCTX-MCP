"""
The transaction API's request and response shapes, and the precision checks
every amount goes through: BTC to 8 decimal places (a satoshi), USD to 2
(cents). The ledger line, lot and disposal shapes are for the debug views.
"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Literal
from datetime import datetime, timezone
from decimal import Decimal

# backend.constants.BROKER_REPORTING_VALUES
BrokerReporting = Literal["none", "proceeds", "basis"]


class TxType(str, Enum):
    DEPOSIT = "Deposit"
    WITHDRAWAL = "Withdrawal"
    TRANSFER = "Transfer"
    BUY = "Buy"
    SELL = "Sell"


def _decimal_places(value: Decimal) -> int:
    """Decimal places of the value itself, whatever its notation ("1E-9" has 9)."""
    if not value.is_finite():
        raise ValueError("Amount must be a finite number.")
    exponent = value.normalize().as_tuple().exponent
    return -exponent if exponent < 0 else 0


def _integer_digits(value: Decimal) -> int:
    whole = abs(value).to_integral_value(rounding="ROUND_DOWN")
    return len(str(int(whole))) if whole else 1


def validate_btc_decimal(value: Decimal) -> Decimal:
    """
    At most 8 decimal places (a satoshi) and 10 integer digits (the database
    column holds 18 digits with 8 decimals; a bigger value would be saved and
    then break every listing). Checked on the number, not its text, so
    exponent notation ("1E-9") can't slip through.
    """
    if _decimal_places(value) > 8:
        raise ValueError("BTC amount cannot exceed 8 decimal places.")
    if _integer_digits(value) > 10:
        raise ValueError("Amount is too large.")
    return value


def validate_usd_decimal(value: Decimal) -> Decimal:
    """At most 2 decimal places (cents) and 16 integer digits."""
    if _decimal_places(value) > 2:
        raise ValueError("USD amount cannot exceed 2 decimal places.")
    if _integer_digits(value) > 16:
        raise ValueError("USD amount is too large.")
    return value


class TransactionBase(BaseModel):
    """
    A transaction as entered: its type, accounts, amount, fee and USD
    values. The ledger lines, lots and disposals are built from it.
    """
    type: TxType
    timestamp: datetime | None = None

    from_account_id: int | None = None
    to_account_id: int | None = None

    amount: Decimal | None = Field(
        default=None,
        description="Main transaction amount, typically BTC with up to 8 decimals."
    )
    fee_amount: Decimal | None = Field(
        default=None,
        description="Fee amount, typically BTC with up to 8 decimals."
    )
    fee_currency: str | None = None

    source: str | None = None  # a Deposit's: MyBTC, Gift, Income, Interest, Reward or N/A
    purpose: str | None = None  # a Withdrawal's: Spent, Gift, Donation, Lost
    broker_reporting: BrokerReporting | None = Field(
        default=None,
        description=(
            "Sell/Withdrawal only: what your broker reported on Form 1099-DA "
            "(none / proceeds / basis). Omit or null for automatic."
        ),
    )

    cost_basis_usd: Decimal | None = Field(
        default=None,
        description="Total USD cost basis for tax reporting (e.g., Buy price)."
    )

    proceeds_usd: Decimal | None = Field(
        default=None,
        description="Total USD proceeds for tax reporting (e.g., Sell price)."

    )
    gross_proceeds_usd: Decimal | None = Field(
        default=None,
        description="Exact user input for sale/withdrawal proceeds, before fees."
    )

    fmv_usd: Decimal | None = Field(
        default=None,
        description="Fair market value for non-sale disposals (Gift, Donation, Lost)."
    
    )
    fee_usd: Decimal | None = Field(
        default=None,
        description=(
            "USD value of a transfer's or withdrawal's BTC fee. Leave out to use "
            "fee x that day's price; a value you give is kept."
        ),
    )
    realized_gain_usd: Decimal | None = Field(
        default=None,
        description="Realized gain/loss in USD for IRS Form 8949."
    )
    holding_period: str | None = None  # e.g., "SHORT", "LONG"

    @field_validator("timestamp")
    def force_utc_timestamp(cls, v: datetime | None) -> datetime | None:
        """
        Ensures timestamps are UTC for consistent audit trails.
        """
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        else:
            v = v.astimezone(timezone.utc)
        return v

    @field_validator("amount")
    def validate_amount(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            return validate_btc_decimal(v)
        return v

    @field_validator("fee_amount")
    def validate_fee_amount(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            return validate_btc_decimal(v)
        return v

    @field_validator("cost_basis_usd", "proceeds_usd", "realized_gain_usd", "fmv_usd", "fee_usd")
    def validate_usd_fields(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            return validate_usd_decimal(v)
        return v
    
    @field_validator("gross_proceeds_usd")
    def validate_gross_proceeds_usd(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            return validate_usd_decimal(v)
        return v


class TransactionCreate(TransactionBase):
    """
    Schema for creating a new transaction. Type and timestamp are required
    (a missing timestamp used to fail with a 500); the rest is validated per
    type by the service (services/transaction._validate_transaction).
    Integrates with FastAPI/SwaggerUI via TxType enum dropdown.
    """
    timestamp: datetime


class TransactionUpdate(BaseModel):
    """
    Schema for partial updates. All fields optional, with TxType for type changes.
    Added is_locked to allow toggling lock state (e.g., for admin use).
    """
    type: TxType | None = None
    timestamp: datetime | None = None

    from_account_id: int | None = None
    to_account_id: int | None = None
    amount: Decimal | None = None
    fee_amount: Decimal | None = None
    fee_currency: str | None = None

    source: str | None = None
    purpose: str | None = None
    broker_reporting: BrokerReporting | None = None  # send null to go back to automatic

    cost_basis_usd: Decimal | None = None
    proceeds_usd: Decimal | None = None
    gross_proceeds_usd: Decimal | None = None
    fmv_usd: Decimal | None = None
    fee_usd: Decimal | None = None  # send null to go back to the day's price
    realized_gain_usd: Decimal | None = None
    holding_period: str | None = None

    is_locked: bool | None = None  # accepted but not applied (docs/temp/TODO.md)

    @field_validator("timestamp")
    def force_utc_timestamp(cls, v: datetime | None) -> datetime | None:
        """
        Ensures updated timestamps remain UTC-consistent.
        """
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        else:
            v = v.astimezone(timezone.utc)
        return v

    @field_validator("amount")
    def validate_amount(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            return validate_btc_decimal(v)
        return v

    @field_validator("fee_amount")
    def validate_fee_amount(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            return validate_btc_decimal(v)
        return v

    @field_validator("cost_basis_usd", "proceeds_usd", "realized_gain_usd", "fmv_usd", "fee_usd")
    def validate_usd_fields(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            return validate_usd_decimal(v)
        return v
    
    @field_validator("gross_proceeds_usd")
    def validate_gross_proceeds_usd(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            return validate_usd_decimal(v)
        return v


class TransactionRead(TransactionBase):
    """
    Schema for reading transactions from the database.
    Includes audit fields required for accounting software.
    """
    id: int
    is_locked: bool
    fee_usd_manual: bool = False  # fee_usd was typed by the user
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LedgerEntryBase(BaseModel):
    """
    Base schema for ledger entries in double-entry accounting.
    Tracks debits/credits per account.
    """
    account_id: int
    amount: Decimal = Field(
        ...,
        description="Signed amount (e.g., -1.0 for outflow, +1.0 for inflow)."
    )
    currency: str = "BTC"
    entry_type: str | None = None  # e.g., "FEE", "TRANSFER_OUT"

    @field_validator("amount")
    def validate_ledger_amount(cls, v: Decimal) -> Decimal:
        return validate_btc_decimal(v)


class LedgerEntryCreate(LedgerEntryBase):
    """
    Schema for creating ledger entries tied to a transaction.
    """
    transaction_id: int


class LedgerEntryRead(LedgerEntryBase):
    """
    Schema for reading ledger entries, including DB-generated ID.
    """
    id: int

    model_config = ConfigDict(from_attributes=True)


class BitcoinLotBase(BaseModel):
    """
    Base schema for tracking BTC lots (FIFO tax lots for IRS compliance).
    """
    total_btc: Decimal = Field(
        ...,
        description="Total BTC acquired in this lot."
    )
    remaining_btc: Decimal = Field(
        ...,
        description="Remaining BTC not yet disposed."
    )
    cost_basis_usd: Decimal = Field(
        ...,
        description="USD cost basis for this lot (for tax reporting)."
    )

    @field_validator("total_btc", "remaining_btc")
    def validate_lot_btc(cls, v: Decimal) -> Decimal:
        return validate_btc_decimal(v)

    @field_validator("cost_basis_usd")
    def validate_lot_usd(cls, v: Decimal) -> Decimal:
        return validate_usd_decimal(v)


class BitcoinLotCreate(BitcoinLotBase):
    """
    Schema for creating a BTC lot (e.g., from Buy/Deposit).
    """
    created_txn_id: int
    acquired_date: datetime | None = None

    @field_validator("acquired_date")
    def force_utc_acquired_date(cls, v: datetime | None) -> datetime | None:
        """
        Ensures acquired_date is UTC for consistent tax holding period calculation.
        """
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        else:
            v = v.astimezone(timezone.utc)
        return v


class BitcoinLotRead(BitcoinLotBase):
    """
    Schema for reading BTC lots, including DB fields.
    """
    id: int
    created_txn_id: int
    acquired_date: datetime

    model_config = ConfigDict(from_attributes=True)


class LotDisposalBase(BaseModel):
    """
    Base schema for disposing BTC lots (e.g., Sell/Withdrawal).
    Tracks tax implications per disposal.
    """
    lot_id: int
    disposed_btc: Decimal = Field(
        ...,
        description="BTC amount disposed from this lot."
    )
    holding_period: str | None = Field(
        default=None,
        description="SHORT or LONG term for IRS capital gains."
    )

    @field_validator("disposed_btc")
    def validate_disposed_btc(cls, v: Decimal) -> Decimal:
        return validate_btc_decimal(v)


class LotDisposalCreate(LotDisposalBase):
    """
    Schema for creating a disposal record with tax details.
    """
    transaction_id: int
    realized_gain_usd: Decimal | None = None
    disposal_basis_usd: Decimal | None = None
    proceeds_usd_for_that_portion: Decimal | None = None

    @field_validator("realized_gain_usd", "disposal_basis_usd", "proceeds_usd_for_that_portion")
    def validate_disposal_usd(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            return validate_usd_decimal(v)
        return v


class LotDisposalRead(LotDisposalBase):
    """
    Schema for reading disposal records, including DB fields.
    """
    id: int
    transaction_id: int
    realized_gain_usd: Decimal | None = None
    disposal_basis_usd: Decimal | None = None
    proceeds_usd_for_that_portion: Decimal | None = None

    model_config = ConfigDict(from_attributes=True)
