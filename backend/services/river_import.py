"""
Adapter + dedup engine for importing River bitcoin-activity CSV exports
into a live ledger. See docs/archive/RIVER_IMPORT_PLAN.md for the full design.

River CSV columns:
    Date, Sent Amount, Sent Currency, Received Amount, Received Currency,
    Fee Amount, Fee Currency, Tag
Dates are "YYYY-MM-DD HH:MM:SS" in UTC. Tag is one of Buy, Sell, Income
(a referral payout), Interest, Mining (a mining payout), Withdrawal (an
auto-withdrawal), or empty (on-chain sends/receives). River's help page "How
do I download my account activity?" defines the columns and tags.

Account model (spec 5.11, Q8): River is the exchange the owner chooses for
the file (its USD and BTC accounts; by default the first exchange), its
sends go to the wallet the owner chooses (by default the first wallet), a
buy is paid from the first bank unless the file's earlier sales left the
exchange's dollars to pay it (#655), and External is everything else.

Every other exchange's file (exchange_import, B5b) is read into the same
FileRows River's are, so this adapter, duplicate check and save serve them
all, with River's rules.
"""

from __future__ import annotations

import csv
import io
import logging
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from functools import partial
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.constants import ACCOUNT_EXTERNAL
from backend.models.transaction import Transaction
from backend.schemas.csv_import import CSVParseError
from backend.schemas.transaction import BTC_PLACES
from backend.services.account import FIXED_BOOK, AccountBook, account_book
from backend.services.calculation import btc_text
from backend.services.csv_import import (
    _parse_decimal,
    decimal_comma_note,
    number_limits,
    unreadable_csv,
)
from backend.services.tax_time import get_tax_timezone, local_date

logger = logging.getLogger(__name__)

RIVER_REQUIRED_COLUMNS = {
    "date", "sent amount", "sent currency", "received amount",
    "received currency", "fee amount", "fee currency", "tag",
}

RIVER_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# The amounts, as River's header names them
RIVER_NUMBER_COLUMNS = ("Sent Amount", "Received Amount", "Fee Amount")

# A buy outlay (sent + USD fee) that repeats at least this many times with no
# fee is treated as a recurring auto-buy pulled from the bank via ACH.
RECURRING_BUY_THRESHOLD = 4

# Dedup: a row within this of a transaction of the same amount is shown as similar (#253)
SIMILAR_WINDOW = timedelta(hours=48)
FUZZY_AMOUNT_TOLERANCE = Decimal("0.20")  # ±20% for transfer near-matches

STATUS_NEW = "new"
STATUS_MATCHED = "matched"
STATUS_DISCREPANCY = "discrepancy"

CHOOSE_EXCHANGE = "Choose one of your exchanges."
CHOOSE_WALLET = "Choose one of your wallets."


@dataclass(frozen=True)
class RiverAccounts:
    """Where a River file goes (5.11, Q8): the exchange's two accounts, the
    wallet its sends go to, the bank its buys are paid from by default (None
    when every bank is hidden: then the exchange's dollars), the banks a buy
    may be paid from besides the exchange's dollars, and the book naming them."""
    exchange_usd: int
    exchange_btc: int
    wallet: int
    bank: int | None
    banks: tuple[int, ...]
    book: AccountBook

    def funding_choices(self) -> list[str]:
        return [self.book.name(i) for i in (*self.banks, self.exchange_usd)]


# 1.x's: a file read without a ledger (the adapter's tests)
RIVER_1X = RiverAccounts(exchange_usd=3, exchange_btc=4, wallet=2, bank=1, banks=(1,), book=FIXED_BOOK)


def river_accounts(book: AccountBook, exchange_account_id: int | None = None,
                   wallet_account_id: int | None = None) -> RiverAccounts:
    """The accounts the owner chose for the file: an exchange's BTC account
    and a wallet, else the first of each that isn't hidden (1.x's 4 and 2),
    never a hidden one; 422 for anything else, or with none to take."""
    exchange_btc = _chosen(book, exchange_account_id, _exchanges_btc(book), CHOOSE_EXCHANGE)
    wallet = _chosen(book, wallet_account_id, [i for i in book.yours() if book.kind(i) == "wallet"], CHOOSE_WALLET)
    banks = tuple(i for i in book.yours() if book.kind(i) == "bank" and not book.is_hidden(i))
    return RiverAccounts(exchange_usd=book.usd_of(exchange_btc), exchange_btc=exchange_btc, wallet=wallet,
                         bank=banks[0] if banks else None, banks=banks, book=book)


def _exchanges_btc(book: AccountBook) -> list[int]:
    return [i for i in book.yours() if book.kind(i) == "exchange" and book.currency(i) == "BTC"]


def _chosen(book: AccountBook, chosen: int | None, allowed: list[int], refusal: str) -> int:
    """The account chosen, when it's one of `allowed`; none chosen, the first
    of them not hidden."""
    if chosen is None:
        chosen = next((i for i in allowed if not book.is_hidden(i)), None)
    if chosen not in allowed:
        raise HTTPException(status_code=422, detail=refusal)
    return chosen


@dataclass
class RiverRow:
    """One parsed row of the River bitcoin-activity CSV."""
    row_number: int
    timestamp: datetime
    sent: Decimal | None
    sent_currency: str | None
    received: Decimal | None
    received_currency: str | None
    fee: Decimal | None
    fee_currency: str | None
    tag: str | None


@dataclass
class RiverProposal:
    """A proposed BitcoinTX transaction adapted from a River row."""
    row_number: int
    timestamp: datetime
    river_tag: str | None
    type: str
    from_account_id: int
    to_account_id: int
    amount: Decimal
    cost_basis_usd: Decimal | None = None
    proceeds_usd: Decimal | None = None
    fee_amount: Decimal | None = None
    fee_currency: str | None = None
    source: str | None = None
    purpose: str | None = None
    # Preview metadata
    type_choices: list[str] = field(default_factory=list)
    funding_choices: list[str] = field(default_factory=list)
    basis_autofilled: bool = False
    price_moment: str | None = None  # the autofilled basis's price: "hour" or "day"
    status: str = STATUS_NEW
    matched_tx_id: int | None = None
    discrepancy: str | None = None
    # A row given as a date alone (the AI connector's): its day in the tax
    # timezone, which the duplicate check matches instead of the minute
    day: date | None = None
    # Matched only by a near amount (a BTC move typed by hand): the preview
    # leaves it unticked, as it's most likely that move (owner, 2026-10-15, #253)
    near_amount: bool = False
    # The side ("from" or "to") whose account is the file's guess, not River's
    # word: a send's or receive's wallet (5.11; the owner's decision, 2026-10-16)
    guessed: str | None = None
    # The side whose bank River's file never names: a buy's funding, the
    # preview's default or the owner's edit (the build lead's call under
    # #251's decision 25, 2026-10-23): another bank there still matches
    unnamed_bank: str | None = None
    # The book naming its accounts
    book: AccountBook = field(default=FIXED_BOOK, repr=False, compare=False)

    @property
    def from_account(self) -> str:
        return self.book.name(self.from_account_id)

    @property
    def to_account(self) -> str:
        return self.book.name(self.to_account_id)

    def to_tx_data(self) -> dict[str, Any]:
        """Build the dict create_transaction_record() expects."""
        tx_data: dict[str, Any] = {
            "type": self.type,
            "timestamp": self.timestamp,
            "amount": self.amount,
            "from_account_id": self.from_account_id,
            "to_account_id": self.to_account_id,
        }
        if self.cost_basis_usd is not None:
            tx_data["cost_basis_usd"] = self.cost_basis_usd
        if self.proceeds_usd is not None:
            tx_data["proceeds_usd"] = self.proceeds_usd
        if self.fee_amount is not None and self.fee_amount > 0:
            tx_data["fee_amount"] = self.fee_amount
            tx_data["fee_currency"] = self.fee_currency or (
                "USD" if self.type in ("Buy", "Sell") else "BTC"
            )
        if self.source:
            tx_data["source"] = self.source
        if self.purpose:
            tx_data["purpose"] = self.purpose
        return tx_data


def parse_river_csv(content: bytes) -> tuple[list[RiverRow], list[CSVParseError]]:
    """Parse raw River bitcoin-activity CSV bytes into RiverRow objects."""
    try:
        return _parse_river_rows(content)
    except csv.Error as exc:
        return [], [unreadable_csv(exc)]


def rows_in_file(rows: list[RiverRow], errors: list[CSVParseError]) -> int:
    """The file's data rows, read or refused (#455): a refused row's error
    carries its row number; an error about the whole file is row 0."""
    return len({row.row_number for row in rows} | {e.row_number for e in errors if e.row_number > 0})


def _parse_river_rows(content: bytes) -> tuple[list[RiverRow], list[CSVParseError]]:
    errors: list[CSVParseError] = []
    rows: list[RiverRow] = []

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except UnicodeDecodeError:
            errors.append(CSVParseError(
                row_number=0, column=None, severity="error",
                message="File encoding not supported. Please save as UTF-8.",
            ))
            return rows, errors

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        errors.append(CSVParseError(
            row_number=0, column=None, severity="error",
            message="CSV file is empty or has no headers.",
        ))
        return rows, errors

    headers = {h.lower().strip() for h in reader.fieldnames if h}
    missing = RIVER_REQUIRED_COLUMNS - headers
    if missing:
        errors.append(CSVParseError(
            row_number=0, column=None, severity="error",
            message=(
                "This does not look like a River bitcoin-activity CSV. "
                f"Missing columns: {', '.join(sorted(missing))}"
            ),
        ))
        return rows, errors

    for row_number, raw in enumerate(reader, start=2):
        if None in raw:
            # More fields than the header (the reader lists the extras under
            # None): the columns no longer line up, so the row can't be read.
            errors.append(CSVParseError(
                row_number=row_number, column=None, severity="error",
                message=(
                    "This row has more fields than the header: a stray comma, or an amount "
                    "written with a comma (write 1000.00, not 1,000.00)?"
                ),
            ))
            continue
        r = {(k or "").lower().strip(): (v or "").strip() for k, v in raw.items()}

        date_str = r.get("date", "")
        try:
            # River exports timestamps in UTC
            ts = datetime.strptime(date_str, RIVER_DATE_FORMAT).replace(tzinfo=timezone.utc)
        except ValueError:
            errors.append(CSVParseError(
                row_number=row_number, column="date", severity="error",
                message=f"Invalid date '{date_str}'. Expected YYYY-MM-DD HH:MM:SS.",
            ))
            continue

        numbers = _river_numbers(r, row_number, errors)
        if numbers is None:
            continue
        sent, received, fee = numbers

        sent_cur = r.get("sent currency", "").upper() or None
        recv_cur = r.get("received currency", "").upper() or None
        fee_cur = r.get("fee currency", "").upper() or None

        rows.append(RiverRow(
            row_number=row_number,
            timestamp=ts,
            sent=sent,
            sent_currency=sent_cur,
            received=received,
            received_currency=recv_cur,
            fee=fee,
            fee_currency=fee_cur,
            tag=r.get("tag", "").title() or None,
        ))

    if not rows and not errors:
        errors.append(CSVParseError(
            row_number=0, column=None, severity="error",
            message="No data rows found in file.",
        ))

    return rows, errors


def _river_numbers(r: dict[str, str], row_number: int,
                   errors: list[CSVParseError]) -> tuple[Decimal | None, ...] | None:
    """
    The row's sent, received and fee amounts (None when blank), or None with
    the row's error when one isn't a number within a BTC column's rule (the
    USD ones too: the import checks their cents when it saves them). Read as
    blank, such a fee would be left out and such an amount would skip its row
    as missing.
    """
    numbers = []
    for column in RIVER_NUMBER_COLUMNS:
        text = r.get(column.lower(), "")
        value = _parse_decimal(text, BTC_PLACES)
        if text and value is None:
            errors.append(CSVParseError(
                row_number=row_number, column=column, severity="error",
                message=f"{column} '{text}' isn't a number with at most {number_limits(BTC_PLACES)}."
                + decimal_comma_note(text),
            ))
            return None
        numbers.append(value)
    return tuple(numbers)


@dataclass
class FileRow:
    """
    One event of an exchange's file as every mapping reads it (B5b, 2.0
    spec 7.4): a buy, a sell, a send, a receive, or a payout, whose kind
    names its deposit source. Its amounts are River's: `btc` a send's coins
    as they arrived, its network fee on top; `usd` a buy's cost and a sell's
    proceeds, each before the fee, or a payout's value at receipt when the
    file gives one. `tag` is the file's own word for the row.
    """
    row_number: int
    timestamp: datetime
    kind: str
    btc: Decimal | None
    usd: Decimal | None = None
    fee: Decimal | None = None
    fee_currency: str | None = None
    tag: str | None = None


BUY, SELL, SEND, RECEIVE = "buy", "sell", "send", "receive"
# A payout's kind, by the deposit source it is (#399: a mining payout is a
# Reward, income like the others; #98: a Rebate is valued so, never income)
PAYOUT_SOURCES = {"income": "Income", "interest": "Interest", "reward": "Reward", "rebate": "Rebate"}
# River's payout tags, by their kind
RIVER_PAYOUTS = {"Interest": "interest", "Income": "income", "Mining": "reward"}


def _usd_fee(row: RiverRow | FileRow) -> Decimal:
    """River's USD fee on a Buy or Sell. River charges those in USD, and the
    proposal records the fee as USD even when Fee Currency is blank, so a
    blank one counts as USD here too (else a Sell's gross would leave out a
    fee the ledger still subtracts)."""
    if row.fee is not None and row.fee_currency in ("USD", None):
        return row.fee
    return Decimal("0")


def _recorded_fee(row: RiverRow | FileRow) -> Decimal:
    """The USD fee a buy's or sell's proposal records. buy() and sell() save
    every fee as fee_currency="USD", so the ledger subtracts row.fee from the
    exchange's dollars whatever currency the file wrote the fee in; covered_buys
    counts this same amount, not _usd_fee's 0 for a BTC fee currency (#655)."""
    return row.fee or Decimal("0")


def _buy_outlay(row: RiverRow) -> Decimal:
    """Total USD that left for a buy: sent + USD fee."""
    return (row.sent or Decimal("0")) + _usd_fee(row)


def _recurring_outlays(rows: list[RiverRow]) -> dict[Decimal, int]:
    """Count identical buy outlays across the file (the heuristic's signal)."""
    counts: dict[Decimal, int] = {}
    for row in rows:
        if row.tag == "Buy":
            outlay = _buy_outlay(row)
            counts[outlay] = counts.get(outlay, 0) + 1
    return counts


def river_file_rows(rows: list[RiverRow]) -> tuple[list[FileRow], list[CSVParseError]]:
    """(rows, warnings): River's rows by River's patterns, each a FileRow; a
    row that fits none is skipped with a warning, never silently dropped."""
    file_rows, warnings = [], []
    for row in rows:
        file_row = _river_file_row(row)
        if file_row is not None:
            file_rows.append(file_row)
            continue
        warnings.append(CSVParseError(
            row_number=row.row_number, column=None, severity="warning", message=(
                f"Unrecognized row pattern (tag={row.tag or 'none'}, "
                f"sent={row.sent_currency or '-'}, received={row.received_currency or '-'}) — skipped."),
        ))
    return file_rows, warnings


def _river_file_row(row: RiverRow) -> FileRow | None:
    """A River row as the event it is: a buy, a sell, a payout (tagged), a
    send (bitcoin out, whatever else its tag: an auto-withdrawal is one,
    #397), a receive (bitcoin in, untagged), or None."""
    tag = row.tag

    def event(kind: str, btc: Decimal | None, usd: Decimal | None = None) -> FileRow:
        return FileRow(row.row_number, row.timestamp, kind, btc, usd, row.fee, row.fee_currency, tag)

    if tag == "Buy" and row.sent_currency == "USD" and row.received_currency == "BTC":
        return event(BUY, row.received, row.sent)
    if tag == "Sell" and row.sent_currency == "BTC" and row.received_currency == "USD":
        # River's Received Amount is what landed after River's fee (receipt:
        # subtotal - fee = received). BitcoinTX's proceeds_usd is the gross
        # before fees, and the ledger subtracts the USD fee from it, so the
        # gross is received + fee.
        received = row.received
        return event(SELL, row.sent, received + _usd_fee(row) if received and received > 0 else received)
    if tag in RIVER_PAYOUTS and row.received_currency == "BTC" and row.received:
        return event(RIVER_PAYOUTS[tag], row.received)
    if row.sent_currency == "BTC" and row.received is None:
        return event(SEND, row.sent)
    if row.received_currency == "BTC" and row.sent is None and tag is None:
        return event(RECEIVE, row.received)
    return None


def adapt_river_rows(
    rows: list[RiverRow], accounts: RiverAccounts = RIVER_1X,
) -> tuple[list[RiverProposal], list[CSVParseError], list[CSVParseError]]:
    """
    (proposals, errors, warnings): each River row as a proposed BitcoinTX
    transaction into `accounts` (the owner's choice, river_accounts). A row
    that fits no known pattern, or lacks an amount, is skipped with a
    warning (never silently dropped). A buy is paid from a bank unless the
    file's earlier sales left the exchange's dollars to pay it (#655); a
    recurring no-fee buy from a bank always (River's rule).
    """
    file_rows, skipped = river_file_rows(rows)
    proposals, errors, warnings = adapt_rows(file_rows, accounts, _recurring_outlays(rows))
    return proposals, errors, sorted([*skipped, *warnings], key=lambda w: w.row_number)


def adapt_rows(
    rows: list[FileRow], accounts: RiverAccounts = RIVER_1X, outlays: dict[Decimal, int] | None = None,
    from_bank: bool = False,
) -> tuple[list[RiverProposal], list[CSVParseError], list[CSVParseError]]:
    """
    (proposals, errors, warnings): each file's row as a proposed BitcoinTX
    transaction into `accounts`; a row lacking an amount is skipped with a
    warning. A buy is paid from the exchange's dollars only when the file's
    earlier rows leave enough there (#655: a file's dollar deposits aren't
    read, so its buys would take those dollars below zero), else from the
    first bank not hidden; from the bank always with `from_bank` (Swan's,
    pulled by ACH) or when `outlays` (River's: how often each buy outlay
    repeats in its file) makes it a recurring no-fee buy. Either is the
    owner's to change in the preview.
    """
    adapter = _Adapter(accounts, outlays, from_bank, rows)
    proposals = [p for p in map(adapter.adapt, rows) if p is not None]
    return proposals, [], adapter.warnings


class _Adapter:
    """Turns a file's rows into proposals in the chosen accounts, collecting the warnings."""

    def __init__(self, accounts: RiverAccounts, outlays: dict[Decimal, int] | None, from_bank: bool,
                 rows: list[FileRow]):
        self.accounts = accounts
        self.outlays = outlays
        self.from_bank = from_bank
        self.warnings: list[CSVParseError] = []
        self.covered = self.covered_buys(rows)

    def adapt(self, row: FileRow) -> RiverProposal | None:
        if row.kind == BUY:
            return self.buy(row)
        if row.kind == SELL:
            return self.sell(row)
        if row.kind in PAYOUT_SOURCES:
            return self.payout(row)
        if row.kind == SEND:
            return self.send(row)
        return self.receive(row)

    def warn(self, row: FileRow, message: str, column: str | None = None) -> None:
        self.warnings.append(CSVParseError(
            row_number=row.row_number, column=column, severity="warning", message=message,
        ))

    def check_fee_currency(self, row: FileRow, expected: str) -> None:
        """The file's fee currency is taken as `expected` for this kind of
        row; say so when the file says otherwise instead of ignoring it."""
        if row.fee and row.fee_currency and row.fee_currency != expected:
            self.warn(row, (
                f"Fee Currency is {row.fee_currency}, but a fee on this kind of row is in {expected}; "
                f"it was read as {row.fee} {expected}. Check the fee before importing."
            ), column="Fee Currency")

    def proposal(self, row: FileRow, **fields) -> RiverProposal:
        return RiverProposal(row_number=row.row_number, timestamp=row.timestamp, river_tag=row.tag,
                             book=self.accounts.book, **fields)

    def buy(self, row: FileRow) -> RiverProposal | None:
        if not row.btc or row.btc <= 0 or not row.usd or row.usd <= 0:
            self.warn(row, "Buy row missing its bitcoin or dollar amount — skipped.")
            return None
        self.check_fee_currency(row, "USD")
        return self.proposal(
            row, type="Buy", from_account_id=self.funding(row), to_account_id=self.accounts.exchange_btc,
            amount=row.btc, cost_basis_usd=row.usd, fee_amount=row.fee, fee_currency="USD" if row.fee else None,
            funding_choices=self.accounts.funding_choices(), unnamed_bank="from",
        )

    def funding(self, row: FileRow) -> int:
        """Where a buy's dollars come from: the exchange's cash balance when
        the file's earlier rows leave enough there for it (covered_buys),
        else a bank (never a hidden one: with none, the exchange's dollars,
        as before)."""
        if id(row) in self.covered or self.accounts.bank is None:
            return self.accounts.exchange_usd
        return self.accounts.bank

    def from_a_bank(self, row: FileRow) -> bool:
        """A buy paid from a bank whatever the exchange holds: an exchange
        that pulls its buys from the bank (Swan's), or a recurring no-fee
        outlay, an auto-buy pulled by ACH (River's heuristic, by `outlays`)."""
        recurring = self.outlays is not None and not row.fee and (
            self.outlays.get((row.usd or Decimal("0")) + _usd_fee(row), 0) >= RECURRING_BUY_THRESHOLD)
        return recurring or self.from_bank

    def covered_buys(self, rows: list[FileRow]) -> set[int]:
        """The buys (by id) the exchange's own dollars pay for (#655): in
        time order, a sale's proceeds less its fee go into them, and a buy
        is paid from them when they cover its cost and fee. No file's dollar
        deposits are read (they move no bitcoin), so its buys are otherwise
        paid from the bank they came from, and the exchange's dollars, as
        the file leaves them, never fall below zero."""
        dollars, covered = Decimal(0), set()
        for row in sorted(rows, key=lambda r: r.timestamp):
            usable = row.btc and row.btc > 0 and row.usd and row.usd > 0
            if row.kind == SELL and usable:
                dollars += row.usd - _recorded_fee(row)
            elif row.kind == BUY and usable and not self.from_a_bank(row) and dollars >= row.usd + _recorded_fee(row):
                dollars -= row.usd + _recorded_fee(row)
                covered.add(id(row))
        return covered

    def sell(self, row: FileRow) -> RiverProposal | None:
        if not row.btc or row.btc <= 0 or not row.usd or row.usd <= 0:
            self.warn(row, "Sell row missing its bitcoin or dollar amount — skipped.")
            return None
        self.check_fee_currency(row, "USD")
        return self.proposal(
            row, type="Sell", from_account_id=self.accounts.exchange_btc, to_account_id=self.accounts.exchange_usd,
            amount=row.btc, proceeds_usd=row.usd, fee_amount=row.fee, fee_currency="USD" if row.fee else None,
        )

    def payout(self, row: FileRow) -> RiverProposal | None:
        # BTC the exchange paid (River's interest on the cash balance too,
        # which River pays in BTC). Its basis, the value at receipt, is the
        # file's when it gives one, else filled from the hour's price by the
        # router; editable. River's reader never gives one without its coins.
        if not row.btc:
            self.warn(row, "Payout row missing its bitcoin amount — skipped.")
            return None
        return self.proposal(
            row, type="Deposit", from_account_id=ACCOUNT_EXTERNAL, to_account_id=self.accounts.exchange_btc,
            amount=row.btc, cost_basis_usd=row.usd, source=PAYOUT_SOURCES[row.kind],
        )

    def send(self, row: FileRow) -> RiverProposal | None:
        """
        BTC left the exchange: almost always a move to the user's cold
        storage, whether a send or River's auto-withdrawal (Tag=Withdrawal:
        River sends the balance to the address the user set, #397). The user
        can make it a Withdrawal in the preview. The amount is what the
        destination receives, the network fee on top (River's Total is Sent
        plus Fee, #39); the proposal keeps it, and ledger_amount() gives a
        Transfer's BitcoinTX amount (fee included) for dedup and at execute.
        """
        if not row.btc or row.btc <= 0:
            self.warn(row, "BTC send row missing amount — skipped.")
            return None
        self.check_fee_currency(row, "BTC")
        return self.proposal(
            row, type="Transfer", from_account_id=self.accounts.exchange_btc, to_account_id=self.accounts.wallet,
            amount=row.btc, fee_amount=row.fee, fee_currency="BTC" if row.fee else None,
            type_choices=["Transfer", "Withdrawal"], guessed="to",
        )

    def receive(self, row: FileRow) -> RiverProposal | None:
        """BTC arriving at the exchange: by default back from cold storage,
        with no fee (the exchange can't see the wallet's network fee; editable)."""
        if not row.btc or row.btc <= 0:
            self.warn(row, "BTC receive row missing amount — skipped.")
            return None
        return self.proposal(
            row, type="Transfer", from_account_id=self.accounts.wallet, to_account_id=self.accounts.exchange_btc,
            amount=row.btc, type_choices=["Transfer", "Deposit"], guessed="from",
        )


# Dedup / merge engine

# Which existing transaction types can correspond to a proposal of each type.
# BTC sends/receives are ambiguous in River's data, so they match the wider
# set the user might have recorded manually.
_COMPATIBLE_TYPES: dict[str, tuple[str, ...]] = {
    "Buy": ("Buy",),
    "Sell": ("Sell",),
    "Deposit": ("Deposit",),
    "Withdrawal": ("Withdrawal", "Transfer"),
    "Transfer": ("Transfer", "Withdrawal", "Deposit"),
}


def ledger_amount(
    tx_type: str,
    amount: Decimal,
    fee_amount: Decimal | None,
    fee_currency: str | None,
) -> Decimal:
    """
    River amounts exclude the network fee. A BitcoinTX Transfer's amount is
    what left the source, fee included (destination receives amount - fee),
    so a BTC fee is added for Transfers. Withdrawals keep the fee on top.
    """
    if tx_type == "Transfer" and fee_amount and (fee_currency or "BTC").upper() == "BTC":
        return amount + fee_amount
    return amount


def _proposal_ledger_amount(proposal: RiverProposal) -> Decimal:
    return ledger_amount(
        proposal.type, proposal.amount, proposal.fee_amount, proposal.fee_currency
    )


def _as_utc(ts: datetime) -> datetime:
    """SQLite returns naive datetimes; all app timestamps are UTC."""
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)


@dataclass(frozen=True)
class DuplicateRule:
    """What a row must share with a recorded transaction of a compatible
    kind, besides the minute, to be it (#253): an amount, and nothing that
    `differences` names (each difference as the note says it). The amount
    tests are tried in turn, each over every row, so a row of the same
    ledger amount takes its match before one that has only River's."""
    amounts: tuple[Callable[[RiverProposal, Transaction], bool], ...]
    differences: Callable[[RiverProposal, Transaction], list[str]]


def same_ledger_amount(proposal: RiverProposal, tx: Transaction) -> bool:
    """The identical BTC amount as BitcoinTX records it (a Transfer's with its fee)."""
    return Decimal(tx.amount or 0) == _proposal_ledger_amount(proposal)


def _same_river_amount(proposal: RiverProposal, tx: Transaction) -> bool:
    """River's own amount: a send the owner imported with another fee, or as
    a Withdrawal (its fee on top), is still that send (#253)."""
    return proposal.amount == _river_amount(tx)


def _river_amount(tx: Transaction) -> Decimal:
    """A recorded transaction's amount as River's file gives it: a Transfer's
    less its BTC fee (ledger_amount's inverse)."""
    amount = Decimal(tx.amount or 0)
    if tx.type == "Transfer" and tx.fee_amount and (tx.fee_currency or "BTC").upper() == "BTC":
        return amount - Decimal(tx.fee_amount)
    return amount


def _nothing_else(_proposal: RiverProposal, _tx: Transaction) -> list[str]:
    return []


# River's rule (owner, 2026-10-14, #253): the same kind, BTC amount and
# minute is the same event. A row's source, purpose, fee and values are the
# preview's defaults or the owner's own edits, so a re-import of an edited
# row isn't recorded twice.
RIVER_RULE = DuplicateRule(amounts=(same_ledger_amount, _same_river_amount), differences=_nothing_else)


def annotate_duplicates(
    proposals: list[RiverProposal],
    db: Session,
    exact_only: bool = False,
    rule: DuplicateRule = RIVER_RULE,
    reserved_tx_ids: Collection[int] = (),
) -> None:
    """
    Mark proposals that are already in the ledger, or look like it (#253).
    No proposal is matched to a transaction in `reserved_tx_ids` (at a River
    import: the preview's matches of the rows it found in the ledger). Every
    pass compares a row with transactions of its own currency only, bitcoin
    with bitcoin, dollars with dollars (_compatible, #581).

    Pass 1 (a duplicate, STATUS_MATCHED): a compatible type, the same amount
    and minute (a row given as a date alone: the same day in the tax
    timezone), and no difference, as `rule` says; greedy nearest-timestamp,
    one existing tx matches at most one proposal, the timed rows before the
    rows given as a date alone (_timed_first). Within each amount test, a
    transaction of the row's own type is tried before one of another
    compatible type.

    Pass 2 (similar, STATUS_DISCREPANCY): the same amount within ±48 h,
    anything else different; its note says what. Never left out by itself.
    The one pass offered a transaction in another wallet than the one a
    River row's wallet side guessed (_compatible's `guess`).

    Pass 3 (BTC moves only, never a dollar row, #581): within ±48 h and an
    amount within ±20 %: the user's manual transfer entries are known to be
    approximate.

    Passes 2 and 3 are skipped when exact_only=True: the execute
    endpoints' double-submit guard leaves out only duplicates.
    """
    if not proposals:
        return  # nothing to look up the ledger for
    existing: list[Transaction] = db.query(Transaction).order_by(Transaction.id).all()  # ties: the oldest first
    tz = get_tax_timezone(db) if any(p.day for p in proposals) else timezone.utc
    book = account_book(db)
    used_tx_ids: set = set(reserved_tx_ids)
    by_time = sorted(proposals, key=lambda p: p.timestamp)
    nearby = _nearby(proposals, existing)

    def each_new(match, types=None, order=by_time, guess=False) -> None:
        """One pass: `match` for every row still new (of `types`), in `order` (time, unless given)."""
        for proposal in order:
            if proposal.status == STATUS_NEW and (types is None or proposal.type in types):
                match(proposal, _candidates(proposal, nearby[id(proposal)], used_tx_ids, book, guess), used_tx_ids)

    timed_first = sorted(proposals, key=_timed_first)
    for same_amount in rule.amounts:
        for same_type in (True, False):
            each_new(partial(_match_exactly, same_amount=same_amount, differences=rule.differences, tz=tz,
                             same_type=same_type), order=timed_first)
    if exact_only:
        return
    for same_amount in rule.amounts:
        each_new(partial(_match_similar, same_amount=same_amount, differences=rule.differences, tz=tz, book=book),
                 guess=True)
    each_new(partial(_match_roughly, book=book), types=("Transfer", "Withdrawal"))


def _timed_first(proposal: RiverProposal) -> tuple[bool, datetime]:
    """The order rows take their duplicates in: the timed rows, then the rows
    given as a date alone, each in time order. A timed row's minute is a
    surer match than a date alone's whole day (its noon is no time at all),
    so a date-alone row takes a copy only after the timed rows have theirs,
    and is the row saved when one of them is that copy (#472). River's rows
    are all timed: in time order."""
    return proposal.day is not None, proposal.timestamp


def _nearby(proposals: list[RiverProposal], existing: list[Transaction]) -> dict[int, list[Transaction]]:
    """Each proposal's transactions within the window (by id(proposal)),
    found by time once per call, so no pass scans the whole ledger for
    every row (#379). Kept in the ledger's order: _nearest gives a tie to
    the first of them, as over the whole ledger."""
    by_time = sorted((_as_utc(tx.timestamp), i) for i, tx in enumerate(existing))
    times = [moment for moment, _ in by_time]
    nearby = {}
    for proposal in proposals:
        low, high = _window(proposal.timestamp)
        start, end = bisect_left(times, low), bisect_right(times, high)
        nearby[id(proposal)] = [existing[i] for i in sorted(i for _, i in by_time[start:end])]
    return nearby


def _window(moment: datetime) -> tuple[datetime, datetime]:
    """From SIMILAR_WINDOW before `moment` to SIMILAR_WINDOW after, in UTC
    (an aware time elsewhere would move by its wall clock), stopping at
    Python's first and last years: a River file's row can be dated anywhere
    until its import refuses it (#211)."""
    moment = _as_utc(moment)
    first, last = datetime.min.replace(tzinfo=timezone.utc), datetime.max.replace(tzinfo=timezone.utc)
    low = moment - SIMILAR_WINDOW if moment - first > SIMILAR_WINDOW else first
    high = moment + SIMILAR_WINDOW if last - moment > SIMILAR_WINDOW else last
    return low, high


def _candidates(proposal: RiverProposal, existing: list[Transaction], used_tx_ids: set,
                book: AccountBook, guess: bool = False) -> list[Transaction]:
    """The unmatched transactions of a compatible type within the window,
    going the same way (_compatible). The window is checked here too, so
    that over the whole ledger (the speed test's reference) it's exact."""
    return [
        tx for tx in existing
        if tx.id not in used_tx_ids
        and _compatible(proposal, tx, book, guess)
        and abs(_as_utc(tx.timestamp) - proposal.timestamp) <= SIMILAR_WINDOW
    ]


def _compatible(proposal: RiverProposal, tx: Transaction, book: AccountBook, guess: bool = False) -> bool:
    """A compatible type going the same way: from the row's account or to
    it, so a send never matches a deposit, nor a receive a withdrawal (#253);
    in the row's currency, so a bitcoin amount is never a dollar one of the
    same number, nor the other way round (#581); and naming on neither side
    another account of the same kind and currency as the row's (two
    wallets, two exchanges' BTC or USD accounts, two banks: the owner's
    rule, 2026-10-15), so exchange B's send to a wallet is never exchange
    A's; but River never names a buy's funding bank, so another bank there
    still matches (`_unnamed_bank`, the build lead's call under #251's
    decision 25). With `guess` (the similar pass), a River row's guessed
    side may name another wallet, and then counts as going the same way
    when the other side is the row's own account or External: the file
    chose its wallet, River didn't (the owner's decision, 2026-10-16), so a
    deposit typed into the other wallet is offered too, never a move
    between two of the owner's wallets."""
    alike = [side for side in _other_accounts_alike(proposal, tx, book) if not _unnamed_bank(proposal, side, book)]
    guessed = guess and proposal.guessed in alike and _beside_its_own(proposal, tx)
    return (
        tx.type in _COMPATIBLE_TYPES.get(proposal.type, (proposal.type,))
        and (tx.from_account_id == proposal.from_account_id or tx.to_account_id == proposal.to_account_id
             or guessed)
        and _in_dollars(tx, book) == _in_dollars(proposal, book)
        and all(guessed and side == proposal.guessed for side in alike)
    )


def _other_accounts_alike(proposal: RiverProposal, tx: Transaction, book: AccountBook) -> list[str]:
    """The sides ("from", "to") on which the transaction names another
    account than the row, of the same kind and currency. External, an
    account of another kind, or one the book doesn't have, is never alike."""
    sides = (("from", proposal.from_account_id, tx.from_account_id), ("to", proposal.to_account_id, tx.to_account_id))
    return [side for side, ours, theirs in sides
            if ours != theirs and book.kind(ours) is not None
            and (book.kind(ours), book.currency(ours)) == (book.kind(theirs), book.currency(theirs))]


def _beside_its_own(proposal: RiverProposal, tx: Transaction) -> bool:
    """The transaction's side opposite the guessed one is the row's own
    account or External: a deposit or a send typed into the other wallet, a
    withdrawal or a receive typed from it."""
    if proposal.guessed == "to":
        return tx.from_account_id in (proposal.from_account_id, ACCOUNT_EXTERNAL)
    return tx.to_account_id in (proposal.to_account_id, ACCOUNT_EXTERNAL)


def _unnamed_bank(proposal: RiverProposal, side: str, book: AccountBook) -> bool:
    """A bank River's file never names (a buy's funding): another bank on
    that side doesn't stop a match, as an edit of the funding never did."""
    account = proposal.from_account_id if side == "from" else proposal.to_account_id
    return side == proposal.unnamed_bank and book.kind(account) == "bank"


def account_differences(proposal: RiverProposal, tx: Transaction, book: AccountBook,
                        sides: tuple[str, ...] = ("from", "to")) -> list[str]:
    """The accounts the transaction left or went into that aren't the row's,
    on `sides`, as a note says them: "recorded into Cold Storage, not Wallet"."""
    found = {"from": ("from", tx.from_account_id, proposal.from_account_id),
             "to": ("into", tx.to_account_id, proposal.to_account_id)}
    return [f"recorded {way} {_named(recorded, book)}, not {_named(sent, book)}"
            for way, recorded, sent in (found[side] for side in sides) if recorded != sent]


def _named(account_id: int | None, book: AccountBook) -> str:
    return book.name(account_id) if account_id is not None else "no account"


def is_duplicate(proposal: RiverProposal, tx: Transaction, rule: DuplicateRule, tz, book: AccountBook) -> bool:
    """Whether pass 1 could take `tx` for `proposal`: a compatible type going
    the same way, the same moment, an amount `rule` accepts and nothing
    else different (#253)."""
    return (
        _compatible(proposal, tx, book) and _same_moment(proposal, tx, tz)
        and any(same(proposal, tx) for same in rule.amounts) and not rule.differences(proposal, tx)
    )


def match_by_moving(
    stuck: list[RiverProposal], holders: list[RiverProposal], db: Session, rule: DuplicateRule,
    kept_tx_ids: Collection[int],
) -> None:
    """
    Each proposal in `stuck` (still new) matched after all when a duplicate
    of it can be freed: one a proposal in `holders` matched, when that one
    can take another duplicate of its own instead, and so on down (an
    augmenting path: the most proposals matched). Never a transaction in
    `kept_tx_ids`. For the AI's rows: a looser row (one matching more
    copies) can have taken the one copy another row has (#411), and sent
    again, a copy the first send saved for a row the user says is another
    transaction (#388's review). The timed rows go first (_timed_first).
    """
    if not stuck:
        return
    existing = db.query(Transaction).order_by(Transaction.id).all()
    holder = {p.matched_tx_id: p for p in holders}
    if all(tx.id in holder or tx.id in kept_tx_ids for tx in existing):
        return  # every transaction taken: none can be freed
    proposals = [*stuck, *holders]
    tz = get_tax_timezone(db) if any(p.day for p in proposals) else timezone.utc
    book = account_book(db)
    nearby = _nearby(proposals, existing)
    duplicates: dict[int, list[Transaction]] = {}

    def duplicates_of(proposal: RiverProposal) -> list[Transaction]:
        """Its duplicates it may take, nearest first, found once."""
        if id(proposal) not in duplicates:
            duplicates[id(proposal)] = sorted(
                (tx for tx in nearby[id(proposal)] if tx.id not in kept_tx_ids and is_duplicate(proposal, tx, rule, tz, book)),
                key=lambda tx: abs(_as_utc(tx.timestamp) - proposal.timestamp),
            )
        return duplicates[id(proposal)]

    seen: set = set()  # no path through these until a row is placed (then the matches change)
    for proposal in sorted(stuck, key=_timed_first):
        if _place(proposal, duplicates_of, holder, seen):
            seen = set()


def _place(start: RiverProposal, duplicates_of, holder: dict, seen: set) -> bool:
    """`start` matched to a free duplicate, or to one its holder gives up for
    another of its own, and so on down: a search kept on a list, not in
    Python's recursion (a long chain of identical rows ran past its limit).
    Every row on the path found takes the transaction it reached."""
    path = [(start, iter(duplicates_of(start)), None)]  # (row, its duplicates left, the one it would take)
    while path:
        proposal, options, _ = path[-1]
        tx = next((tx for tx in options if tx.id not in seen), None)
        if tx is None:
            path.pop()
            continue
        seen.add(tx.id)
        path[-1] = (proposal, options, tx)
        if tx.id in holder:
            path.append((holder[tx.id], iter(duplicates_of(holder[tx.id])), None))
            continue
        for row, _, taken in path:
            holder[taken.id] = row
            row.matched_tx_id, row.status = taken.id, STATUS_MATCHED
        return True
    return False


def _nearest(proposal: RiverProposal, txs: list[Transaction]) -> Transaction | None:
    """The transaction closest in time; the first of equally close ones."""
    return min(txs, key=lambda tx: abs(_as_utc(tx.timestamp) - proposal.timestamp), default=None)


def _same_moment(proposal: RiverProposal, tx: Transaction, tz) -> bool:
    """The same minute; for a row given as a date alone, the same day in the tax timezone."""
    if proposal.day is not None:
        return local_date(_as_utc(tx.timestamp), tz) == proposal.day
    return _as_utc(tx.timestamp).replace(second=0, microsecond=0) == proposal.timestamp.replace(second=0, microsecond=0)


def _match_exactly(proposal: RiverProposal, candidates: list[Transaction], used_tx_ids: set,
                   same_amount, differences, tz, same_type: bool = False) -> None:
    same = [
        tx for tx in candidates
        if (tx.type == proposal.type or not same_type)
        and same_amount(proposal, tx) and _same_moment(proposal, tx, tz) and not differences(proposal, tx)
    ]
    best = _nearest(proposal, same)
    if best is None:
        return
    used_tx_ids.add(best.id)
    proposal.matched_tx_id = best.id
    proposal.status = STATUS_MATCHED


def _match_similar(proposal: RiverProposal, candidates: list[Transaction], used_tx_ids: set,
                   same_amount, differences, tz, book: AccountBook) -> None:
    best = _nearest(proposal, [tx for tx in candidates if same_amount(proposal, tx)])
    if best is None:
        return
    used_tx_ids.add(best.id)
    proposal.matched_tx_id = best.id
    proposal.status = STATUS_DISCREPANCY
    # The other wallet the guessed side names (never External or another kind: a 1.x note stays as it was)
    guessed = proposal.guessed in _other_accounts_alike(proposal, best, book)
    what = [_when_recorded(proposal, best, tz), *(account_differences(proposal, best, book, (proposal.guessed,))
                                                   if guessed else []), *differences(proposal, best)]
    proposal.discrepancy = (
        f"Same {'dollar' if _in_dollars(best, book) else 'BTC'} amount as tx #{best.id} "
        f"({_type_and_amount(best, book)}), "
        f"{'; '.join(what)}: it may be the same transaction"
    )


def _in_dollars(tx: Transaction | RiverProposal, book: AccountBook) -> bool:
    """Whether its amount is dollars: the AI's rows can be dollar deposits,
    withdrawals and transfers, beside River's bitcoin ones (#525). The
    amount's account (transaction._check_amount's) is neither External nor
    a bitcoin account: a missing one's, which only a ledger from before
    0.9.2 holds, counts as dollars, as in 1.x, so no bitcoin row is ever
    taken for a row whose coins went to no account BitcoinTX knows."""
    account = tx.to_account_id if tx.type in ("Deposit", "Buy") else tx.from_account_id
    return account != ACCOUNT_EXTERNAL and not book.is_btc(account)


def _type_and_amount(tx: Transaction, book: AccountBook) -> str:
    """A transaction as a note names it: "Deposit $500.00", "Buy 0.00030000 BTC"."""
    if _in_dollars(tx, book):
        return f"{tx.type} ${Decimal(tx.amount or 0):,.2f}"
    return f"{tx.type} {btc_text(tx.amount or 0)} BTC"


def _when_recorded(proposal: RiverProposal, tx: Transaction, tz) -> str:
    """When the similar transaction is, from this row: "recorded 3 hours earlier", "recorded on 2026-02-01"."""
    if _same_moment(proposal, tx, tz):
        return "the same day" if proposal.day is not None else "the same minute"
    if proposal.day is not None:
        return f"recorded on {local_date(_as_utc(tx.timestamp), tz).isoformat()}"
    gap = _as_utc(tx.timestamp) - proposal.timestamp
    return f"recorded {_gap_text(gap)} {'earlier' if gap < timedelta(0) else 'later'}"


def _gap_text(gap: timedelta) -> str:
    """A gap as the note says it, in whole units below it: "less than a
    minute", "3 minutes", "1 hour", "47 hours"."""
    seconds = abs(gap).total_seconds()
    if seconds < 60:
        return "less than a minute"
    count, unit = (int(seconds // 60), "minute") if seconds < 3600 else (int(seconds // 3600), "hour")
    return f"{count} {unit}{'' if count == 1 else 's'}"


def _match_roughly(proposal: RiverProposal, candidates: list[Transaction], used_tx_ids: set,
                   book: AccountBook) -> None:
    """A bitcoin move within ±20 % of a recorded one (pass 3): a move typed
    by hand, its network fee guessed, is approximate. Never a dollar row:
    dollars are typed to the cent, and $1,250 beside $1,500 is another
    payment (#581)."""
    if _in_dollars(proposal, book):
        return
    amount = _proposal_ledger_amount(proposal)
    close = [
        tx for tx in candidates
        if Decimal(tx.amount or 0) > 0
        and abs(Decimal(tx.amount or 0) - amount) / Decimal(tx.amount or 0) <= FUZZY_AMOUNT_TOLERANCE
    ]
    best = _nearest(proposal, close)
    if best is None:
        return
    used_tx_ids.add(best.id)
    proposal.matched_tx_id = best.id
    proposal.status = STATUS_DISCREPANCY
    proposal.near_amount = True
    proposal.discrepancy = (
        f"Likely the same event as tx #{best.id} ({_type_and_amount(best, book)}) recorded with a "
        f"different amount"
    )
