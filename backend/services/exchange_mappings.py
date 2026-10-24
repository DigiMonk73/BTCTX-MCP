"""
The mappings an exchange's file is read by (B5b, 2.0 spec 7.4; the owner's
decision 17 on #251, #338): ready-made ones for River, Coinbase, Kraken,
Strike, Swan and Cash App, each from its exchange's published format, and the
owner's own, kept in one app_settings row. A mapping says how to read a file,
never where its rows go: the owner chooses the exchange and the wallet for
each file (5.11), so no mapping can name a hidden account or a fee account.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.database import take_write_lock
from backend.models.app_setting import AppSetting, save_setting
from backend.schemas.exchange_import import OwnMapping
from backend.services.exchange_cells import ZONE_IN_DATES
from backend.services.river_import import BUY, PAYOUT_SOURCES, RECEIVE, SELL, SEND

# How a mapping's file is read: one row for each event, River's sent and
# received columns, or Kraken's ledger lines grouped by their reference
COLUMNS, RIVER_FILE, KRAKEN_LEDGER = "columns", "river", "kraken"

# What a file's word for a row means: an event (river_import's kinds), or
# one of these, which leave it out with their reason
DOLLARS, CONVERT, LEAVE_OUT = "dollars", "convert", "leave out"
EVENTS = (BUY, SELL, SEND, RECEIVE, *PAYOUT_SOURCES)
KINDS = (*EVENTS, DOLLARS, CONVERT, LEAVE_OUT)

SETTING_KEY = "import_mappings"
OWN_PREFIX = "own-"
MAX_OWN_MAPPINGS = 50
MAPPING_NOT_FOUND = "No such mapping."
TOO_MANY_MAPPINGS = f"You can save up to {MAX_OWN_MAPPINGS} mappings: delete one first."
NAME_TAKEN = "A mapping of yours already has that name."
BUSY = "Not saved: BitcoinTX was busy saving something else. Try again."


@dataclass(frozen=True)
class Columns:
    """
    Which of a file's columns hold what, each by the names its exchange has
    given it (any case): the first one a file's header has is read. Only the
    date, the kind (unless the mapping gives every row one) and the bitcoin
    amount are needed; a fee is read from `fee` (in `fee_currency`'s
    currency, else the kind's), or from `fee_usd` and `fee_btc` apart.
    """
    date: tuple[str, ...]
    btc: tuple[str, ...]
    kind: tuple[str, ...] = ()
    time: tuple[str, ...] = ()
    usd: tuple[str, ...] = ()
    fee: tuple[str, ...] = ()
    fee_currency: tuple[str, ...] = ()
    fee_usd: tuple[str, ...] = ()
    fee_btc: tuple[str, ...] = ()
    asset: tuple[str, ...] = ()
    status: tuple[str, ...] = ()
    row_id: tuple[str, ...] = ()

    def roles(self) -> dict[str, tuple[str, ...]]:
        """Each role a column is named for, with its names."""
        return {role: names for role, names in vars(self).items() if names}


@dataclass(frozen=True)
class LeaveOut:
    """A row left out, with `reason`, when its `column` holds `text` (in
    any case; "" for any text at all), when it's blank (`text` None), or,
    with `other_than`, when it holds anything else."""
    column: str
    text: str | None
    reason: str
    other_than: str | None = None

    def applies(self, cell: str) -> bool:
        if self.other_than is not None:
            return bool(cell) and cell.lower() != self.other_than
        return not cell if self.text is None else bool(cell) and self.text in cell.lower()


# A row priced in another currency: BitcoinTX's figures are in US dollars
NOT_DOLLARS = "are priced in another currency, not US dollars (BitcoinTX's figures are in dollars)"


@dataclass(frozen=True)
class Mapping:
    """
    How one exchange's file is read. `kinds` takes each of the file's words
    for a row (lowercase) to one of KINDS; a word it lacks leaves its rows
    out with a warning. `after_fee` names the kinds whose dollars include
    the fee (a buy's total paid, a sell's net received); `send_fee_included`
    says a send's bitcoin amount includes its network fee. Times without a
    zone are in `zone`. A row whose status is in `not_done` (in part), or
    outside `done` when it's given, is left out; `optional` names the roles
    some versions of the file lack. With `merge_same_id`, rows sharing an id
    are one event (Strike's pieces of one order). `notes` names a column
    whose text says a convert's assets, so a convert into bitcoin, its row
    another coin's, is said to involve bitcoin. `checked` is False for a
    mapping built from its exchange's published columns that no real
    export has been checked against yet.
    """
    id: str
    name: str
    reader: str = COLUMNS
    columns: Columns | None = None
    kinds: dict[str, str] = field(default_factory=dict)
    kind: str | None = None
    zone: str = "UTC"
    after_fee: frozenset[str] = frozenset()
    send_fee_included: bool = False
    decimal_comma: bool = False
    day_first: bool = False
    btc_assets: frozenset[str] = frozenset({"btc"})
    done: frozenset[str] = frozenset()
    not_done: tuple[str, ...] = ()
    optional: frozenset[str] = frozenset()
    leave_out: tuple[LeaveOut, ...] = ()
    merge_same_id: bool = False
    notes: tuple[str, ...] = ()
    signs: frozenset[str] = frozenset()
    funding: str = "exchange"
    help: str = ""
    checked: bool = True


RIVER = Mapping(
    id="river", name="River", reader=RIVER_FILE,
    help="river.com → Taxes & Documents → Bitcoin activity (CSV).",
)

# Coinbase's "Transaction history" (2021 to 2023, and from 2024 with an ID
# column first), several lines above its header. Subtotal is what the coins
# cost or brought before the fee, "Fees and/or Spread" the fee in dollars
# (Total is Subtotal plus it on a buy, less on a sell); a send's network fee
# isn't in the file in bitcoin. Built from Coinbase's published columns:
# check against a real export.
COINBASE = Mapping(
    id="coinbase", name="Coinbase",
    columns=Columns(
        date=("Timestamp",), kind=("Transaction Type",), btc=("Quantity Transacted",),
        usd=("Subtotal", "USD Subtotal"), fee_usd=("Fees and/or Spread", "USD Fees"), asset=("Asset",),
        row_id=("ID",),
    ),
    kinds={"buy": BUY, "advanced trade buy": BUY, "sell": SELL, "advanced trade sell": SELL,
           "send": SEND, "receive": RECEIVE, "rewards income": "reward", "staking income": "reward",
           "inflation reward": "reward", "coinbase earn": "income", "learning reward": "income",
           "convert": CONVERT, "deposit": DOLLARS, "withdrawal": DOLLARS,
           "pro withdrawal": LEAVE_OUT, "pro deposit": LEAVE_OUT, "exchange deposit": LEAVE_OUT,
           "exchange withdrawal": LEAVE_OUT, "retail staking transfer": LEAVE_OUT,
           "retail unstaking transfer": LEAVE_OUT},
    optional=frozenset({"row_id"}), notes=("Notes",), checked=False,
    leave_out=(LeaveOut("Spot Price Currency", "", NOT_DOLLARS, other_than="usd"),
               LeaveOut("Price Currency", "", NOT_DOLLARS, other_than="usd")),
    help="coinbase.com → Profile → Reports → Generate report → Transaction history (CSV).",
)

KRAKEN = Mapping(
    id="kraken", name="Kraken", reader=KRAKEN_LEDGER,
    checked=False,
    help="kraken.com → Documents → Export → Ledgers (CSV), unzipped: ledgers.csv.",
)

# Strike's account statements and its activity report (Strike writes UTC),
# its amounts signed by the money's way. A purchase's dollars are its total,
# fee included, a sale's what arrived after it. A target order comes in pieces sharing one id (the dollars, then
# the bitcoin), and a reversal shares the id of what it reverses.
STRIKE = Mapping(
    id="strike", name="Strike",
    columns=Columns(
        date=("Date & Time (UTC)", "Time (UTC)"), kind=("Transaction Type",), btc=("Amount BTC",),
        usd=("Amount USD",), fee_usd=("Fee USD",), fee_btc=("Fee BTC",), status=("Status",),
        row_id=("Reference", "Transaction ID"),
    ),
    kinds={"purchase": BUY, "buy": BUY, "sale": SELL, "send": SEND, "receive": RECEIVE,
           "deposit": DOLLARS, "withdrawal": DOLLARS},
    after_fee=frozenset({BUY, SELL}), done=frozenset({"completed"}), optional=frozenset({"status"}),
    merge_same_id=True, signs=frozenset({"btc", "usd"}),
    checked=False,
    help="Strike → Documents → Account statements → Export as CSV, or Activity → Generate report.",
)

# Swan's "Deposits and purchases" (Swan writes UTC): a purchase's
# Transaction USD is what bought the bitcoin, its fee apart. Swan's buys are
# pulled from the bank by ACH. A deposit of bitcoin marked a custodial
# transfer is Swan moving the coins to another custodian: they never left.
SWAN = Mapping(
    id="swan", name="Swan: deposits and purchases",
    columns=Columns(
        date=("Date",), kind=("Event",), btc=("Unit Count", "BTC"), usd=("Transaction USD", "USD"),
        fee_usd=("Fee USD",), asset=("Asset Type",), status=("Status",), row_id=("Transaction ID",),
    ),
    kinds={"purchase": BUY, "deposit": RECEIVE, "prepaid_fee": DOLLARS, "monthly_fee": DOLLARS},
    done=frozenset({"settled"}), optional=frozenset({"asset", "row_id"}),
    leave_out=(LeaveOut("Address Label", "custodial transfer",
                        "are Swan moving coins between its custodians: they never left Swan"),),
    funding="bank",
    checked=False,
    help="Swan → Profile → Documents → Export account data: Deposits and purchases (CSV).",
)

# Swan's "Withdrawals": every row a send, which Swan's custodian pays the
# network fee for, so what left is what arrived
SWAN_WITHDRAWALS = Mapping(
    id="swan-withdrawals", name="Swan: withdrawals", kind=SEND,
    columns=Columns(date=("Executed At",), btc=("Bitcoin Amount",), row_id=("Transaction ID",)),
    leave_out=(LeaveOut("Canceled At", "", "were canceled"),
               LeaveOut("Executed At", None, "haven't been sent (no Executed At)")),
    checked=False,
    help="Swan → Profile → Documents → Export account data: Withdrawals (CSV).",
)

# Cash App's bitcoin "Transactions CSV" and its activity CSV: its dates
# carry the account's US zone (PST, EDT…). A buy's Amount is what bought
# the bitcoin, negative, a sale's its gross, positive, each fee apart in
# dollars; a Boost is card cash-back paid in bitcoin, a rebate (#98).
CASH_APP = Mapping(
    id="cash-app", name="Cash App", zone=ZONE_IN_DATES,
    columns=Columns(
        date=("Date",), kind=("Transaction Type",), btc=("Asset Amount",), usd=("Amount",),
        fee_usd=("Fee",), asset=("Asset Type",), status=("Status",), row_id=("Transaction ID",),
    ),
    kinds={"bitcoin buy": BUY, "bitcoin recurring buy": BUY, "bitcoin sale": SELL, "bitcoin sell": SELL,
           "bitcoin withdrawal": SEND, "bitcoin lightning withdrawal": SEND, "bitcoin deposit": RECEIVE,
           "bitcoin lightning deposit": RECEIVE, "bitcoin boost": "rebate"},
    not_done=("fail", "revers", "cancel", "pending", "refund", "declin"), optional=frozenset({"status"}),
    leave_out=(LeaveOut("Currency", "", NOT_DOLLARS, other_than="usd"),), signs=frozenset({"usd"}),
    checked=False,
    help="Cash App → Profile → Documents → Bitcoin → Transactions CSV, or Activity → Statements → Export CSV.",
)

READY_MADE: dict[str, Mapping] = {
    m.id: m for m in (RIVER, COINBASE, KRAKEN, STRIKE, SWAN, SWAN_WITHDRAWALS, CASH_APP)}


def mapping_by_id(db: Session, mapping_id: str) -> Mapping:
    """A ready-made mapping, or one of the owner's; 404 otherwise."""
    if mapping_id in READY_MADE:
        return READY_MADE[mapping_id]
    own = saved_mappings(db).get(mapping_id)
    if own is None:
        raise HTTPException(status_code=404, detail=MAPPING_NOT_FOUND)
    return from_own(mapping_id, own)


def from_own(mapping_id: str, own: OwnMapping) -> Mapping:
    """The owner's mapping as the reader takes it: one name for each column."""
    columns = own.columns
    return Mapping(
        id=mapping_id, name=own.name,
        columns=Columns(**{role: (name,) for role, name in columns.model_dump().items() if name}),
        kinds={word.strip().lower(): kind for word, kind in own.kinds.items()},
        zone=own.zone, after_fee=frozenset(own.dollars_after_fee), send_fee_included=own.send_fee_included,
        decimal_comma=own.decimal_comma, day_first=own.day_first,
        btc_assets=frozenset(a.strip().lower() for a in own.btc_assets),
        done=frozenset(s.strip().lower() for s in own.done),
    )


def saved_mappings(db: Session) -> dict[str, OwnMapping]:
    """The owner's mappings by id, in the order saved."""
    return _stored(db)[1]


def save_mapping(db: Session, own: OwnMapping, mapping_id: str | None = None) -> str:
    """Save the owner's mapping as `mapping_id` (a new one when None), under
    the write lock so two tabs saving at once both land; its id. This
    install's saves never hand an id out twice, so a page holding a deleted
    one's id gets 404, not another mapping (a restore brings the backup's
    mappings and ids, decision 7)."""
    if not take_write_lock(db):
        raise HTTPException(status_code=503, detail=BUSY)
    try:
        last_id, mappings = _stored(db)
        if mapping_id is not None and mapping_id not in mappings:
            raise HTTPException(status_code=404, detail=MAPPING_NOT_FOUND)
        if any(m.name.casefold() == own.name.casefold() for i, m in mappings.items() if i != mapping_id):
            raise HTTPException(status_code=409, detail=NAME_TAKEN)
        if mapping_id is None:
            if len(mappings) >= MAX_OWN_MAPPINGS:
                raise HTTPException(status_code=409, detail=TOO_MANY_MAPPINGS)
            last_id += 1
            mapping_id = f"{OWN_PREFIX}{last_id}"
        mappings[mapping_id] = own
        _store(db, last_id, mappings)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return mapping_id


def delete_mapping(db: Session, mapping_id: str) -> None:
    """Delete one of the owner's mappings; 404 when there's none by that id."""
    if not take_write_lock(db):
        raise HTTPException(status_code=503, detail=BUSY)
    try:
        last_id, mappings = _stored(db)
        if mappings.pop(mapping_id, None) is None:
            raise HTTPException(status_code=404, detail=MAPPING_NOT_FOUND)
        _store(db, last_id, mappings)
        db.commit()
    except Exception:
        db.rollback()
        raise


def _stored(db: Session) -> tuple[int, dict[str, OwnMapping]]:
    """(the last id's number handed out, the mappings by id). What this
    version can't read (a restore's, from a later one) is left out, never
    an error."""
    row = db.get(AppSetting, SETTING_KEY)
    try:
        stored = json.loads(row.value) if row is not None else {}
    except ValueError:
        stored = {}
    stored = stored if isinstance(stored, dict) else {}
    mappings = {}
    for mapping_id, value in (stored.get("mappings") or {}).items():
        try:
            mappings[mapping_id] = OwnMapping.model_validate(value)
        except ValueError:
            continue
    last_id = stored.get("last_id")
    return (last_id if isinstance(last_id, int) else 0), mappings


def _store(db: Session, last_id: int, mappings: dict[str, OwnMapping]) -> None:
    save_setting(db, SETTING_KEY, json.dumps(
        {"last_id": last_id, "mappings": {i: m.model_dump(mode="json") for i, m in mappings.items()}}))
