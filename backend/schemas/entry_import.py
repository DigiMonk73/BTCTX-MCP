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
from typing import Any

from pydantic import BaseModel, Field, field_serializer

from backend.database import RowId
from backend.schemas.transaction import ChosenCoin, eight_places


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
    fee_usd: Decimal | None = None  # a BTC fee's USD value; omitted = fee x that hour's price
    acquired_at: str | None = Field(
        default=None,
        description="My BTC or Gift deposit: when the coins were originally acquired (by the giver, for a gift), "
                    "read like date. Omitted: the deposit's date. Inherited deposit: the date of death (required).",
    )
    not_a_duplicate_of: RowId | None = Field(
        default=None,
        description="Only when the user says this row is another transaction than the one the preview matched "
                    "as a duplicate: that transaction's id (the preview's matched_transaction_id). The row is "
                    "then saved, once (sent again, it's left out) (#253, #378). Beside an identical row "
                    "without it, both are refused as unclear (#497).",
    )
    chosen_coins: list[ChosenCoin] | None = Field(
        default=None,
        description="A Transfer to another account, or a BTC Withdrawal, from one of the user's wallets: the "
                    "coins the user says they chose by the time they left, each the Buy or Deposit that acquired "
                    "them (its transaction id) and the BTC from it, together exactly what leaves (a Transfer's "
                    "amount, its fee in it; a Withdrawal's amount and its BTC fee). Omitted: the oldest coins "
                    "(#711).",
    )


class EntryRequest(BaseModel):
    rows: list[EntryRow]


class FromPrice(BaseModel):
    """
    The values BitcoinTX filled in from a price, named as the transactions
    API names them (gross_proceeds_usd: a Spent's proceeds before its fee),
    and that price (#208, #145 plan 2.5): its UTC hour's start, or the day's
    ("moment"; an inheritance's: its date of death), where it came from and
    USD per BTC, as price_used gives them. The price is left out when the
    stored one no longer gives the value (priced elsewhere: an import).
    """
    values: list[str]
    at: str | None = None
    moment: str | None = None
    source: str | None = None
    usd_per_btc: Decimal | None = None


class CoinLine(BaseModel):
    """Coins of one acquisition (#711): the Buy or Deposit that acquired them
    by its transaction id, or, when it's a row of this request (no id yet),
    by that row's number."""
    acquired_txn_id: int | None = None
    row: int | None = None
    btc: Decimal

    @field_serializer("btc", when_used="json")
    def btc_written_out(self, v: Decimal) -> str:
        return eight_places(v)


class HeldCoins(CoinLine):
    """What a wallet holds of one acquisition when a row comes, before it
    takes any: how they were acquired and where, their date acquired
    (INHERITED for inherited coins), their cost, and the term they'd have
    leaving on the row's date."""
    how: str | None = None
    acquired: str
    cost_usd: Decimal
    term: str

    @field_serializer("cost_usd", when_used="json")
    def cost_in_cents(self, v: Decimal) -> str:
        return f"{v:.2f}"


class CoinsSeen(BaseModel):
    """For a row leaving one of the user's wallets (#711, 6.5): the coins it
    takes, by acquisition, and those the wallet holds then, oldest first, at
    most entry_import.MOST_HELD of them (held_not_listed: how many more)."""
    takes: list[CoinLine]
    held: list[HeldCoins]
    held_not_listed: int = 0


class SimulatedResult(BaseModel):
    """What the ledger computed for this row during the dry run."""
    cost_basis_usd: Decimal | None = None
    proceeds_usd: Decimal | None = None
    realized_gain_usd: Decimal | None = None
    holding_period: str | None = None
    gross_proceeds_usd: Decimal | None = None  # a sale's or Spent's proceeds before the fee
    fmv_usd: Decimal | None = None  # a gift's, donation's or lost coins' value
    fee_usd: Decimal | None = None  # a BTC fee's USD value
    from_price: FromPrice | None = None  # which of these came from a price, and that price (#208)
    coins: CoinsSeen | None = None  # a row leaving a wallet: the coins it takes and those held (#711)


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

    @field_serializer("balance", when_used="json")
    def balance_written_out(self, v: Decimal) -> str:
        return eight_places(v)


class PastYearWarning(BaseModel):
    """
    The past-year warning (2.0 spec 5.8): the rows would change the figures
    of an earlier tax year, so the execute saves them only when sent again
    with ?confirm=<confirm>. `changes` are the rows whose figures move, as
    Ledger Review lists them, each with what moves and its tax years;
    `pending`, apart, what a save that recalculates also applies (with the
    AI key); `exact` false when the server ran out of time to work out
    exactly what moves, and names every year the rows can reach instead;
    `timezone` the one the rows' dates are in.
    """
    detail: str
    years: list[int]
    changes: list[dict[str, Any]]
    pending: list[dict[str, Any]]
    recalc_error: str | None = None
    exact: bool
    why_not_exact: str | None = None
    timezone: str
    confirm: str


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
    past_years: PastYearWarning | None = None


class CreatedTransaction(BaseModel):
    row: int
    id: int
    type: str
    date: datetime
    amount: Decimal
    realized_gain_usd: Decimal | None = None
    holding_period: str | None = None
    from_price: FromPrice | None = None
    warnings: list[str] = []  # about its accounts: one hidden in Settings (2.0 spec 5.5)

    @field_serializer("amount", when_used="json")
    def amount_written_out(self, v: Decimal) -> str:
        return eight_places(v)


class EntryExecuteResponse(BaseModel):
    success: bool
    imported_count: int
    skipped_duplicates: int
    created: list[CreatedTransaction]
    message: str
