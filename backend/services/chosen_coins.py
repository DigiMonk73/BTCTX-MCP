"""
The coins a transaction chose to leave one of your wallets (#711; specific
identification, Treas. Reg. §1.1012-1(j)(2)). Within a wallet the IRS's
default is the earliest acquired units first ((j)(1)); a choice names
instead the Buy or Deposit that acquired the units, and how much of them,
together exactly what leaves. Every lot remembers its acquisition through
transfers (bitcoin_lots.acquired_txn_id), so a choice survives every
recalculation. Exchanges stay first in, first out, so BitcoinTX matches
the order a broker reports on Form 1099-DA.

Here: a request's choice checked and parsed, stored with the moment it
was saved, the edit rule (an edit that changes what leaves sends the coins
again), and the lots a choice may take, with the refusals' words. The
engine (services/transaction.py) takes from those lots as first in, first
out takes from all of them: the fee's piece first, the oldest first.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.models.transaction import BitcoinLot, ChosenCoin, Transaction
from backend.schemas.transaction import validate_btc_storable
from backend.services.account import AccountBook, account_book
from backend.services.tax_time import get_tax_timezone, local_date

# A choice: each acquisition's id and the BTC chosen from it, in the order given
Choice = dict[int, Decimal]

MOST_LINES = 1000
# The largest id SQLite stores: a larger one names no transaction (and can't be asked for)
LARGEST_ID = 2**63 - 1
NOT_FROM_A_WALLET = "Coins can be chosen only when they leave one of your wallets."
EXCHANGE_OLDEST_FIRST = " An exchange's coins leave oldest first, as its Form 1099-DA reports them."
WITHIN_ONE_WALLET = ("A move within the same wallet records only its network fee, from the oldest coins: no "
                     "coins are chosen.")
TOO_MANY = f"At most {MOST_LINES:,} Buys or Deposits can be named in one choice of coins."
NOT_ABOVE_ZERO = "The coins chosen from transaction {id} must be more than 0 BTC."
NAMED_TWICE = "Transaction {id} is named twice: name each Buy or Deposit once, with all the coins chosen from it."
NOT_AN_ACQUISITION = "Transaction {id} didn't acquire bitcoin: choose coins by the Buy or Deposit that acquired them."
DOESNT_ADD_UP = ("The coins chosen add up to {chosen} BTC, but {leaves} BTC leaves {wallet}{parts}. Choose coins "
                 "for all of it, or none to send the oldest first.")
SEND_AGAIN = ("Transaction {id} has coins chosen for {btc} BTC leaving {wallet}, and this changes what leaves: "
              "choose its coins again (chosen_coins), or set it back to oldest first (chosen_coins: null).")
# SEND_AGAIN's header, naming the transaction: the AI connector answers it as
# its tool's answer (saved: false, what to send), not as an error (#733)
CHOOSE_AGAIN_HEADER = "X-BitcoinTX-Choose-Again"
NOT_HELD = ("Transaction {id} ({what}) chose {btc} BTC of the coins from transaction {acquired}{about}, but "
            "{wallet} holds {held} BTC of them then. Change that transaction's chosen coins first, or set it back "
            "to oldest first.")
# The transaction being saved: its id isn't one the owner has yet
NOT_HELD_HERE = "{wallet} holds {held} BTC of the coins from transaction {acquired}{about} on this date, not the " \
                "{btc} BTC chosen."

# Session.info key: a callable a transaction's lots are handed to before it
# takes any, as (the transaction, [Held, ...]): what its account holds then,
# for the form's list of coins to choose from. The save's own path, so
# the list and the save can't disagree
HELD_HOOK = "btctx_coins_held"


@dataclass(frozen=True)
class Held:
    """Coins of one acquisition an account holds when a transaction comes,
    before it takes any: their BTC, the cost of those BTC, when they were
    acquired (the lot's date: holding period, Form 8949 column (b)),
    whether they were inherited, and what the transaction takes of them
    without a choice (oldest first, lot by lot, as the save takes them: one
    acquisition's lots may sit apart, between another's of the same date).
    acquired_txn_id is None for lots made before migration 0101, until the
    next recalculation."""
    acquired_txn_id: int | None
    btc: Decimal
    cost_usd: Decimal
    acquired: datetime
    inherited: bool
    oldest_first: Decimal


def checked(data: dict, db: Session) -> Choice | None:
    """
    The choice `data["chosen_coins"]` (a list of {"acquired_txn_id", "btc"})
    checked against the transaction `data` is (its type, accounts, amount
    and fee, already checked), or None when nothing is chosen (left out,
    null or empty). Refused (422): a choice where coins can't be chosen, a
    line that isn't more than 0 BTC or names an acquisition twice, more
    than MOST_LINES lines, an id that isn't a Buy or Deposit into a bitcoin
    account, or a total that isn't what leaves.
    """
    lines = data.get("chosen_coins")
    if not lines:
        return None
    book = account_book(db)
    _check_where(data, book)
    choice = _parsed(lines)
    _check_acquisitions(choice, db, book)
    _check_total(choice, data, book)
    return choice


def refusal(data: dict, chosen_btc: Decimal, book: AccountBook) -> str | None:
    """Why a choice of `chosen_btc` in all can't be saved on the transaction
    `data` (where coins can be chosen, the total), in checked()'s words,
    before any acquisition or lot is read: a CSV's preview names the row
    with it (csv_choices). None when it can be."""
    try:
        _check_where(data, book)
        _check_total({0: chosen_btc}, data, book)
    except HTTPException as e:
        return str(e.detail)
    return None


def check_edit(tx: Transaction, tx_data: dict, edited: dict, db: Session) -> None:
    """
    An edit's choice. One sent is checked against the row the edit makes
    (`edited`), and tx_data holds it parsed. Without one, the row keeps the
    coins it chose while what leaves stays the same (a date, a purpose, a
    value); an edit that changes what leaves without sending them is
    refused (SendAgain): nothing chosen is dropped or guessed at.
    """
    if "chosen_coins" in tx_data:
        tx_data["chosen_coins"] = checked({**edited, "chosen_coins": tx_data["chosen_coins"]}, db)
    elif tx.chosen_coins and _what_leaves_changes(tx, edited):
        raise SendAgain(tx, account_book(db))


def store(tx: Transaction, choice: Choice | None, db: Session) -> None:
    """Save `choice` as tx's coins (None: nothing chosen). coins_chosen_at
    is when they were saved: a choice sent back unchanged keeps it, so an
    edit of another field never makes a choice look later than it was."""
    if saved_choice(tx) == (choice or {}):
        return
    tx.chosen_coins.clear()
    db.flush()  # the old lines go before new ones take their (transaction, acquisition) pairs
    tx.chosen_coins.extend(ChosenCoin(acquired_txn_id=acquired, btc=btc) for acquired, btc in (choice or {}).items())
    tx.coins_chosen_at = datetime.now(timezone.utc) if choice else None
    db.flush()


def what_leaves(tx: Transaction) -> Decimal:
    """The BTC a transaction takes from its account: a Transfer's amount
    (its fee in it), only its fee within one account (a consolidation,
    #159); a Withdrawal's or a Sell's amount and its BTC fee."""
    amount = Decimal(tx.amount or 0)
    fee = Decimal(tx.fee_amount or 0) if (tx.fee_currency or "").upper() == "BTC" else Decimal(0)
    if tx.type == "Transfer":
        return fee if tx.from_account_id == tx.to_account_id else amount
    return amount + fee


def saved_choice(tx: Transaction) -> Choice:
    return {line.acquired_txn_id: Decimal(line.btc) for line in tx.chosen_coins}


def every_choice(db: Session) -> dict[int, Choice]:
    """Every stored choice by transaction, in one query: the replay reads
    them once, so a ledger without any pays one empty query."""
    choices: dict[int, Choice] = {}
    for tx_id, acquired, btc in (db.query(ChosenCoin.transaction_id, ChosenCoin.acquired_txn_id, ChosenCoin.btc)
                                 .order_by(ChosenCoin.id)):
        choices.setdefault(tx_id, {})[acquired] = Decimal(btc)
    return choices


def replays_first(rows: Iterable[dict], db: Session) -> bool:
    """Whether writing `rows` (transactions' data) replays the whole ledger
    for a choice among them: while a lot doesn't know its acquisition
    (lots_lack_acquisition), the first row with a choice does, so the
    past-year question and the AI's copy treat the write as replaying (call
    (j))."""
    return any(row.get("chosen_coins") for row in rows) and lots_lack_acquisition(db)


def lots_lack_acquisition(db: Session) -> bool:
    """Whether a lot doesn't know its acquisition (made before migration
    0101, or moved from one by a transfer dated last since): a write with a
    choice then replays the whole ledger first, which gives every lot its
    own."""
    return db.query(BitcoinLot.id).filter(BitcoinLot.acquired_txn_id.is_(None)).first() is not None


def lots_chosen(tx: Transaction, choice: Choice, lots: list[BitcoinLot],
                db: Session) -> list[tuple[BitcoinLot, Decimal]]:
    """
    What a transaction with a choice may take from its account's open lots
    (oldest first): (lot, BTC it may give) for each lot of an acquisition
    chosen, each acquisition's lots giving at most what was chosen of it,
    the first made first. The lots must hold all of it, else NotHeld.
    """
    left = dict(choice)
    pairs = []
    for lot in lots:
        wanted = left.get(lot.acquired_txn_id)
        if wanted:
            give = min(Decimal(lot.remaining_btc), wanted)
            left[lot.acquired_txn_id] = wanted - give
            pairs.append((lot, give))
    for acquired, short in left.items():
        if short > 0:
            held = sum((Decimal(lot.remaining_btc) for lot in lots if lot.acquired_txn_id == acquired), Decimal(0))
            raise NotHeld(tx, acquired, choice[acquired], held, db)
    return pairs


class SendAgain(HTTPException):
    """An edit that changes what leaves a row whose coins were chosen,
    without sending them again: a 422 saying what to send."""

    def __init__(self, tx: Transaction, book: AccountBook):
        btc = sum(saved_choice(tx).values(), Decimal(0))
        parts = {"id": tx.id, "btc": f"{btc:.8f}", "wallet": book.name(tx.from_account_id)}
        super().__init__(status_code=422, detail=SEND_AGAIN.format(**parts), headers={CHOOSE_AGAIN_HEADER: str(tx.id)})


class NotHeld(HTTPException):
    """The replay found a choice whose coins its account doesn't hold then:
    a 400 naming the transaction that chose them, which the write's path
    passes on as any shortage of BTC (a delete's "Not deleted: …")."""

    def __init__(self, tx: Transaction, acquired: int, btc: Decimal, held: Decimal, db: Session):
        tz = get_tax_timezone(db)
        book = account_book(db)
        source = db.get(Transaction, acquired)
        self.tx_id = tx.id
        self.parts = {
            "id": tx.id, "btc": f"{btc:.8f}", "acquired": acquired, "held": f"{held:.8f}",
            "what": f"a {tx.type} of {local_date(tx.timestamp, tz).isoformat()} from {book.name(tx.from_account_id)}",
            "about": "" if source is None else f" (a {source.type} of {local_date(source.timestamp, tz).isoformat()})",
            "wallet": book.name(tx.from_account_id),
        }
        super().__init__(status_code=400, detail=NOT_HELD.format(**self.parts))

    def of_this_one(self) -> "NotHeldHere":
        """Its words for the transaction being saved, which chose them."""
        return NotHeldHere(self.tx_id, NOT_HELD_HERE.format(**self.parts))


class NotHeldHere(HTTPException):
    """The transaction being saved chose coins its wallet doesn't hold on
    its date: a 400, which the form's list of coins answers with what the
    wallet does hold, so the picker can show it."""

    def __init__(self, tx_id: int, detail: str):
        self.tx_id = tx_id
        super().__init__(status_code=400, detail=detail)


def _check_where(data: dict, book: AccountBook) -> None:
    """Coins are chosen only as they leave one of your wallets: a Transfer
    out of one to another account, or a Withdrawal from one."""
    from_id = data.get("from_account_id")
    if data.get("type") not in ("Transfer", "Withdrawal") or book.kind(from_id) != "wallet":
        on_an_exchange = book.kind(from_id) == "exchange" and book.is_btc(from_id)
        _bad(NOT_FROM_A_WALLET + (EXCHANGE_OLDEST_FIRST if on_an_exchange else ""))
    if data.get("type") == "Transfer" and data.get("to_account_id") == from_id:
        _bad(WITHIN_ONE_WALLET)


def _parsed(lines: list) -> Choice:
    if len(lines) > MOST_LINES:
        _bad(TOO_MANY)
    choice: Choice = {}
    for line in lines:
        acquired, btc = line["acquired_txn_id"], _btc(line["btc"])
        if btc <= 0:
            _bad(NOT_ABOVE_ZERO.format(id=acquired))
        if acquired in choice:
            _bad(NAMED_TWICE.format(id=acquired))
        choice[acquired] = btc
    return choice


def _btc(value) -> Decimal:
    """A line's BTC within the amounts' rule, as given and as stored."""
    try:
        return validate_btc_storable(Decimal(value))
    except InvalidOperation:
        _bad("chosen_coins: btc is not a number.")
    except ValueError as problem:
        _bad(f"chosen_coins: {problem}")


def _check_acquisitions(choice: Choice, db: Session, book: AccountBook) -> None:
    """Each id is a Buy or Deposit into a bitcoin account: the transaction
    that first acquired the coins, never a transfer that moved them."""
    ids = [acquired for acquired in choice if 0 < acquired <= LARGEST_ID]
    found = {tx.id: tx for tx in db.query(Transaction).filter(Transaction.id.in_(ids))}
    for acquired in choice:
        tx = found.get(acquired)
        if tx is None or tx.type not in ("Buy", "Deposit") or not book.is_btc(tx.to_account_id):
            _bad(NOT_AN_ACQUISITION.format(id=acquired))


def _check_total(choice: Choice, data: dict, book: AccountBook) -> None:
    """A choice covers exactly what leaves: a Transfer's amount (its fee
    in it), a Withdrawal's amount and its fee. Never half a choice, which
    would hide a rule for the rest."""
    amount = Decimal(data.get("amount") or 0)
    fee = Decimal(data.get("fee_amount") or 0) if (data.get("fee_currency") or "").upper() == "BTC" else Decimal(0)
    chosen = sum(choice.values(), Decimal(0))
    leaves = amount if data["type"] == "Transfer" else amount + fee
    if chosen == leaves:
        return
    parts = ""
    if fee > 0:
        moved = f"{amount - fee:.8f} arriving" if data["type"] == "Transfer" else f"{amount:.8f} sent"
        parts = f" ({moved} and {fee:.8f} network fee)"
    _bad(DOESNT_ADD_UP.format(chosen=f"{chosen:.8f}", leaves=f"{leaves:.8f}",
                              wallet=book.name(data["from_account_id"]), parts=parts))


def _what_leaves_changes(tx: Transaction, edited: dict) -> bool:
    """Whether the edit changes the coins that leave: the type, From, the
    amount, the fee or its currency, or To becoming From (a move within one
    wallet, which takes no choice). Another To takes the same coins."""
    if edited["type"] != tx.type or edited["from_account_id"] != tx.from_account_id:
        return True
    if edited["to_account_id"] == edited["from_account_id"]:
        return True
    return (Decimal(edited["amount"] or 0) != Decimal(tx.amount or 0)
            or Decimal(edited["fee_amount"] or 0) != Decimal(tx.fee_amount or 0)
            or (edited["fee_currency"] or "").upper() != (tx.fee_currency or "").upper())


def _bad(detail: str):
    raise HTTPException(status_code=422, detail=detail)
