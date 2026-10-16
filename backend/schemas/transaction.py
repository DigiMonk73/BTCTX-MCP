"""
The transaction API's request and response shapes, and the precision checks
every amount goes through: BTC to 8 decimal places (a satoshi), USD to 2
(cents). The ledger line, lot and disposal shapes are for the debug views.
"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field, field_serializer, field_validator, ConfigDict
from typing import Literal
from datetime import date, datetime, timezone
from decimal import Decimal

# backend.constants.BROKER_REPORTING_VALUES
BrokerReporting = Literal["none", "proceeds", "basis"]


class TxType(str, Enum):
    DEPOSIT = "Deposit"
    WITHDRAWAL = "Withdrawal"
    TRANSFER = "Transfer"
    BUY = "Buy"
    SELL = "Sell"


# What the database's columns hold, as decimal places and digits before the
# point: BTC values and every amount (whatever its account) Numeric(18, 8),
# USD values Numeric(18, 2). The imports and the connector take the same.
BTC_PLACES, BTC_DIGITS = 8, 10
USD_PLACES, USD_DIGITS = 2, 16


def _decimal_places(value: Decimal) -> int:
    """
    Decimal places of the value itself, whatever its notation ("1E-9" has 9,
    "1.50" has 1). Read from its digits, not normalize(), which rounds to the
    decimal context: it would find no places in 1E-999999999 and fail with an
    error of its own on 1E+999999999.
    """
    if not value.is_finite():
        raise ValueError("Amount must be a finite number.")
    if not value:
        return 0
    _sign, digits, exponent = value.as_tuple()
    coefficient = "".join(map(str, digits))
    trailing_zeros = len(coefficient) - len(coefficient.rstrip("0"))
    return max(0, -(exponent + trailing_zeros))


def _integer_digits(value: Decimal) -> int:
    """Digits before the point, read from the exponent: written out, a value
    such as 1E+999998 takes seconds."""
    return max(value.adjusted() + 1, 1) if value else 1


def validate_btc_decimal(value: Decimal) -> Decimal:
    """
    At most 8 decimal places (a satoshi) and 10 integer digits (the database
    column holds 18 digits with 8 decimals; a bigger value would be saved and
    then break every listing). Checked on the number, not its text, so
    exponent notation ("1E-9") can't slip through.
    """
    if _decimal_places(value) > BTC_PLACES:
        raise ValueError(f"BTC amount cannot exceed {BTC_PLACES} decimal places.")
    if _integer_digits(value) > BTC_DIGITS:
        raise ValueError("Amount is too large.")
    return value


def validate_usd_decimal(value: Decimal) -> Decimal:
    """At most 2 decimal places (cents) and 16 integer digits."""
    if _decimal_places(value) > USD_PLACES:
        raise ValueError(f"USD amount cannot exceed {USD_PLACES} decimal places.")
    if _integer_digits(value) > USD_DIGITS:
        raise ValueError("USD amount is too large.")
    return value


def as_stored(value: Decimal, places: int) -> Decimal:
    """
    The value as the database gives it back: SQLite keeps a Numeric column
    as a 64-bit float, and SQLAlchemy reads it back as that float written
    with the column's places ("%.2f"). 9999999999999999.99 comes back as
    10000000000000000.00.
    """
    return Decimal(f"{float(value):.{places}f}")


def validate_btc_storable(value: Decimal) -> Decimal:
    """validate_btc_decimal on the value, then on the value as stored: one
    that rounds up past the rule there would be saved, then fail every
    listing."""
    validate_btc_decimal(value)
    validate_btc_decimal(as_stored(value, BTC_PLACES))
    return value


def validate_usd_storable(value: Decimal) -> Decimal:
    """validate_usd_decimal on the value, then on the value as stored."""
    validate_usd_decimal(value)
    validate_usd_decimal(as_stored(value, USD_PLACES))
    return value


def _date_alone(value):
    """A date with no time ("2021-03-14") stays a date, which the service
    keeps as it is (#185). Parsed as a datetime it would be midnight UTC,
    the day before in a US tax timezone."""
    if isinstance(value, str) and len(value.strip()) == 10:
        return date.fromisoformat(value.strip())
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
        description="Fee amount: BTC to 8 decimal places, or USD in cents."
    )
    fee_currency: str | None = None

    source: str | None = None  # a Deposit's: MyBTC, Gift, Inherited, Income, Interest, Reward, Rebate or N/A
    purpose: str | None = None  # a Withdrawal's: Spent, Gift, Donation, Lost
    acquired_at: datetime | date | None = Field(
        default=None,
        description=(
            "My BTC or Gift deposit into a BTC account only: the date the coins were "
            "originally acquired (by the giver, for a gift), YYYY-MM-DD, kept as that "
            "date whatever the tax timezone becomes; a date and time stands for its "
            "date in the tax timezone. The holding period and Form 8949 column (b) use "
            "it. Omit or null: the deposit's own date. An Inherited deposit's is the "
            "date of death, and required."
        ),
    )
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
            "fee x that hour's price; a value you give is kept."
        ),
    )
    realized_gain_usd: Decimal | None = Field(
        default=None,
        description="Realized gain/loss in USD for IRS Form 8949."
    )
    holding_period: str | None = None  # e.g., "SHORT", "LONG"

    @field_validator("acquired_at", mode="before")
    def date_alone_stays_a_date(cls, v):
        return _date_alone(v)

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
    acquired_at: datetime | date | None = None  # My BTC / Gift deposits (null: the deposit's date); Inherited: the date of death
    broker_reporting: BrokerReporting | None = None  # send null to go back to automatic

    cost_basis_usd: Decimal | None = None
    proceeds_usd: Decimal | None = None
    gross_proceeds_usd: Decimal | None = None
    fmv_usd: Decimal | None = None
    fee_usd: Decimal | None = None  # send null to go back to the hour's price
    realized_gain_usd: Decimal | None = None
    holding_period: str | None = None

    @field_validator("acquired_at", mode="before")
    def date_alone_stays_a_date(cls, v):
        return _date_alone(v)

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


class PriceUsed(BaseModel):
    """The price a transaction's filled-in values came from (#145): its UTC
    hour's (or day's) start, "hour" or "day", where it came from, and the USD
    per BTC. Read from the stored price at display time; nothing is saved."""
    at: str
    moment: str
    source: str
    usd_per_btc: Decimal


class TransactionRead(TransactionBase):
    """
    Schema for reading transactions from the database.
    Includes audit fields required for accounting software.
    """
    id: int
    fee_usd_manual: bool = False  # fee_usd was typed by the user
    cost_basis_from_price: bool = False  # an income or rebate deposit's value came from a price
    proceeds_from_price: bool = False  # a Spent's proceeds came from a price
    fmv_from_price: bool = False  # a Gift's, Donation's or Lost withdrawal's value came from a price (#255)
    price_moment: str | None = None  # those priced values': "hour" (its UTC hour's opening price) or "day"
    price_used: PriceUsed | None = None  # that price, when this install has it (never asked for)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    # A stored transaction is shown as it is. The limits above are for what
    # is entered: a figure the ledger derives from entered values (a sale's
    # basis over its lots) or one stored before they applied must never
    # stop the list. These replace TransactionBase's checks of the same name.
    @field_validator("amount")
    def validate_amount(cls, v: Decimal | None) -> Decimal | None:
        return v

    @field_validator("fee_amount")
    def validate_fee_amount(cls, v: Decimal | None) -> Decimal | None:
        return v

    @field_validator("cost_basis_usd", "proceeds_usd", "realized_gain_usd", "fmv_usd", "fee_usd")
    def validate_usd_fields(cls, v: Decimal | None) -> Decimal | None:
        return v

    @field_validator("gross_proceeds_usd")
    def validate_gross_proceeds_usd(cls, v: Decimal | None) -> Decimal | None:
        return v

    @field_serializer("amount", "fee_amount", when_used="json")
    def eight_places(self, v: Decimal | None) -> str | None:
        """
        Written out with all eight places, as the columns hold them and as
        the CSV export and calculation.btc_text() write them: str() of a
        Decimal under 0.000001 is in exponent form, "5E-8" for 5 sats and
        "0E-8" for none, which the AI connector passes on as it is (#101).
        """
        return None if v is None else f"{v:.8f}"


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
