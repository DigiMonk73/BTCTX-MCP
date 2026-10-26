"""
The coins a row chose, in BitcoinTX's CSV (#711, docs/temp/2.0-coin-choice.md
6.3): three columns after the others. `id` labels a row in its file (the
transaction's id in the ledger it was exported from; blank on a row added
by hand), `chosen_coins` names each acquisition by its row's id with the BTC
from it ("id 12: 0.01000000; id 30: 0.00500000"), and `coins_chosen_at` is
when the choice was saved (UTC). Never by a row's position: a spreadsheet's
sort, or a row put in by hand, would point a choice at another purchase,
usually one whose coins are in the wallet too, which no check could catch.
An import gives new ids, so each label is turned into the id its row got.
"""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException

from backend.models.transaction import Transaction
from backend.services import chosen_coins
from backend.services.account import AccountBook

COLUMNS = ["id", "chosen_coins", "coins_chosen_at"]
# tx_data's keys for them, which the save ignores: create_in_order turns them into its own
ROW, LABEL, CHOSEN, CHOSEN_AT = "csv_row", "csv_id", "csv_chosen", "csv_coins_chosen_at"

# An id's digits at most (SQLite's largest id has 19), and a line's BTC at most (every bitcoin there is)
LONGEST_ID, MOST_BTC, SATS = 18, Decimal(21_000_000), Decimal("0.00000001")
FIRST_DAY = datetime(2009, 1, 3, tzinfo=timezone.utc)  # bitcoin's first block, as the date column's
BAD_ID = "id must be a whole number above 0, or blank: it names this row for another row's chosen_coins."
SHARED_ID = "id {id} is row {row}'s too: each row's id is its own."
BAD_CHOSEN = ("chosen_coins must read like id 12: 0.01000000; id 30: 0.005 (the id of each Buy's or Deposit's "
              "row, and the BTC chosen from it, above 0, at most 8 places).")
NAMED_TWICE = "chosen_coins names id {id} twice: name each row once, with all the coins chosen from it."
NO_SUCH_ID = "chosen_coins names id {id}, which no row of this file without errors has."
NOT_AN_ACQUISITION = ("chosen_coins names id {id} (row {row}), which didn't acquire bitcoin: choose coins by a "
                      "Buy, or a Deposit into a bitcoin account.")
NOT_BEFORE = ("chosen_coins names id {id} (row {row}), which isn't before this row: the coins must be in the wallet "
              "when they leave (a row at the same time comes first in the file).")
BAD_CHOSEN_AT = ("coins_chosen_at must be a date and time in UTC from 2009-01-03 to now, such as "
                 "2025-03-01T12:00:00Z, or blank.")
NOT_YET = "Row {row} chooses coins of id {id}, which isn't saved before it."
_LINE = re.compile(rf"id\s+(\d{{1,{LONGEST_ID}}})\s*:\s*(\S+)", re.ASCII)


class Unreadable(Exception):
    """A column the row can't hold: (its name, why)."""

    def __init__(self, column: str, message: str):
        super().__init__(message)
        self.column, self.message = column, message


def read(row: dict[str, str], row_number: int) -> dict[str, Any]:
    """The row's three columns as tx_data's keys, checked one by one
    (Unreadable at the first that fails)."""
    return {ROW: row_number, LABEL: _label(row.get("id") or ""), CHOSEN: _chosen(row.get("chosen_coins") or ""),
            CHOSEN_AT: _moment(row.get("coins_chosen_at") or "")}


def _label(text: str) -> int | None:
    text = text.strip()
    if not text:
        return None
    if not (text.isascii() and text.isdigit()) or len(text) > LONGEST_ID or int(text) == 0:
        raise Unreadable("id", BAD_ID)
    return int(text)


def _chosen(text: str) -> list[tuple[int, Decimal]]:
    lines = [part.strip() for part in text.split(";") if part.strip()]
    chosen: list[tuple[int, Decimal]] = []
    for part in lines:
        match = _LINE.fullmatch(part)
        btc = _btc(match.group(2)) if match else None
        if btc is None:
            raise Unreadable("chosen_coins", BAD_CHOSEN)
        label = int(match.group(1))
        if label in (named for named, _ in chosen):
            raise Unreadable("chosen_coins", NAMED_TWICE.format(id=label))
        chosen.append((label, btc))
    return chosen


def _btc(text: str) -> Decimal | None:
    """Above 0, at most every bitcoin there is, to the satoshi (bounded
    before quantize, which can't take a value past Decimal's precision)."""
    try:
        btc = Decimal(text)
        good = btc.is_finite() and 0 < btc <= MOST_BTC and btc == btc.quantize(SATS)
    except InvalidOperation:
        return None
    return btc if good else None


def _moment(text: str) -> datetime | None:
    """A moment in UTC, from bitcoin's first day to the next one, as the
    date column takes them: a year 1 or 9999 one would stop every report in a
    tax timezone it can't be read in."""
    text = text.strip()
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        utc = moment.astimezone(timezone.utc) if moment.tzinfo else None
    except (ValueError, OverflowError):
        utc = None
    if utc is None or not FIRST_DAY <= utc <= datetime.now(timezone.utc) + timedelta(days=1):
        raise Unreadable("coins_chosen_at", BAD_CHOSEN_AT)
    return utc


def check_across(transactions: list[dict[str, Any]], book: AccountBook) -> list[tuple[int, str, str]]:
    """(row, column, why) for what the file itself shows, so the preview
    names the row: an id two rows share; a choice where coins can't be
    chosen or not adding up to what leaves (the save's own words); one
    naming an id no row has, a row that didn't acquire bitcoin, or one not
    saved before it (the import saves rows by date, a same-time pair in the
    file's order). Whether the wallet holds those coins then is the save's
    to say."""
    rows: dict[int, dict[str, Any]] = {}
    found = []
    for tx in transactions:
        label = tx.get(LABEL)
        if label is not None and label in rows:
            found.append((tx[ROW], "id", SHARED_ID.format(id=label, row=rows[label][ROW])))
        elif label is not None:
            rows[label] = tx
    for tx in transactions:
        found += [(tx[ROW], "chosen_coins", why) for why in _choice_problems(tx, rows, book)]
    return found


def _choice_problems(tx: dict[str, Any], rows: dict[int, dict[str, Any]], book: AccountBook) -> list[str]:
    chosen = tx.get(CHOSEN)
    if not chosen:
        return []
    refused = chosen_coins.refusal(tx, sum((btc for _, btc in chosen), Decimal(0)), book)
    if refused:
        return [refused]
    problems = []
    for label, _ in chosen:
        named = rows.get(label)
        if named is None:
            problems.append(NO_SUCH_ID.format(id=label))
        elif named["type"] not in ("Buy", "Deposit") or not book.is_btc(named["to_account_id"]):
            problems.append(NOT_AN_ACQUISITION.format(id=label, row=named[ROW]))
        elif (named["timestamp"], named[ROW]) >= (tx["timestamp"], tx[ROW]):
            problems.append(NOT_BEFORE.format(id=label, row=named[ROW]))
    return problems


def name_by_ids(tx_data: dict[str, Any], made: dict[int, int]) -> None:
    """The row's choice as the save takes it, each label turned into the id
    of the transaction its row became (`made`: label -> id). check_across
    made sure each is saved before it; a file changed since its preview is
    refused here."""
    chosen = tx_data.get(CHOSEN)
    if not chosen:
        return
    lines = []
    for label, btc in chosen:
        if label not in made:
            raise HTTPException(status_code=400, detail=NOT_YET.format(row=tx_data[ROW], id=label))
        lines.append({"acquired_txn_id": made[label], "btc": btc})
    tx_data["chosen_coins"] = lines


def note_saved(tx: Transaction, tx_data: dict[str, Any], made: dict[int, int]) -> None:
    """The saved row's label, and its choice's day as the file gives it (a
    blank one: the import's, which the save set), as the file's other
    columns are taken: the report's "chosen on" is as the file says (Q1)."""
    if tx_data.get(LABEL) is not None:
        made[tx_data[LABEL]] = tx.id
    if tx.chosen_coins and tx_data.get(CHOSEN_AT) is not None:
        tx.coins_chosen_at = tx_data[CHOSEN_AT]


def export_cells(tx: Transaction) -> dict[str, str]:
    """A transaction's three columns in an export: its id, its choice by the
    ids of the transactions that acquired the coins, and when it was saved."""
    lines = "; ".join(f"id {line.acquired_txn_id}: {Decimal(line.btc):.8f}" for line in tx.chosen_coins)
    when = tx.coins_chosen_at.strftime("%Y-%m-%dT%H:%M:%SZ") if tx.chosen_coins and tx.coins_chosen_at else ""
    return {"id": str(tx.id), "chosen_coins": lines, "coins_chosen_at": when}
