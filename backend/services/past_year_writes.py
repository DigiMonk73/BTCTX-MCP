"""
The past-year warning's other writes (2.0 spec 5.8; card B6c, #353): an
import's rows (the AI's batch, River's file: one confirm for them all),
saving the tax timezone, an exchange's 1099-DA switch and, with the AI key,
Recalculate Ledger. Each goes through past_years.save as an add, an edit or
a delete does: a 409 when it would change an earlier tax year's figures,
saved once confirmed, after a copy of the database.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.transaction import Transaction
from backend.services import account as account_service
from backend.services import hourly_prices, recalculated_by, tax_time
from backend.services import transaction as tx_service
from backend.services.account import account_book
from backend.services.past_years import PastYearWrite, moves_only_dollars

ROWS_BY_DATE = ("These rows start in {year}, so they can change {year}'s figures and later years you may have "
                "filed. Save them? A copy of your ledger is made first.")
ROWS_BY_DATE_WITH_FIXES = ("These rows can change the figures of tax year {year} and later years you may have "
                           "filed: saving them also applies the rules fixed since your transactions were saved. Save "
                           "them? A copy of your ledger is made first.")
TIMEZONE_BY_DATE = ("Saving this tax timezone recalculates your ledger from {year} on, so it can change {year}'s "
                    "figures and later years you may have filed. Save it? A copy of your ledger is made first.")
RECALCULATES = ("Recalculating applies the rules fixed since your transactions were saved, and changes the figures "
                "of {years}, which you may already have filed. Confirm to recalculate: a copy of your ledger is made "
                "first.")
RECALCULATES_BY_DATE = ("Recalculating applies the rules fixed since your transactions were saved, so it can change "
                        "the figures of tax year {year} and later years you may have filed. Recalculate? A copy of "
                        "your ledger is made first.")


@dataclass(frozen=True, eq=False)
class Rows(PastYearWrite):
    """
    An import's rows, one confirm for them all. `rows`: each row's data as
    checked, which the fingerprint takes. `kept`: those of them the
    import's duplicate check keeps on a session's ledger, whose dates
    decide what the rows can reach (a duplicate, left out, reaches nothing:
    a batch sent again, or one keeping its duplicates beside a row dated
    last, replays nothing). `write_them`: the duplicate check and its rows
    in time order, uncommitted, so in the confirmed save the check runs
    inside the write lock the rows are written under (#454, #504).
    `save_them`: the import as it always saved. `named`: the transactions
    the rows are told apart from or matched to, which the fingerprint takes
    too.
    """
    rows: tuple[dict, ...]
    kept: Callable[[Session], list[dict]]
    write_them: Callable[[Session], Any]
    save_them: Callable[[Session], Any]
    named: Any = None
    kind = "import"
    by_date_text, by_date_with_fixes_text = ROWS_BY_DATE, ROWS_BY_DATE_WITH_FIXES

    def apply(self, db: Session) -> Any:
        return self.write_them(db)

    def save(self, db: Session) -> Any:
        return self.save_them(db)

    def earliest_year(self, db: Session, tz) -> int | None:
        try:
            return min((tax_time.local_date(row["timestamp"], tz).year for row in self.kept(db)), default=None)
        except tax_time.DateOutOfRange:  # the save refuses it
            return None

    def appends(self, db: Session) -> bool:
        latest = db.query(func.max(Transaction.timestamp)).scalar()
        return latest is None or all(tax_time.as_utc(row["timestamp"]) >= tax_time.as_utc(latest)
                                     for row in self.kept(db))

    def moves_no_figure(self, db: Session) -> bool:
        book = account_book(db)
        return all(moves_only_dollars(row.get("type"), (row.get("from_account_id"), row.get("to_account_id")), book)
                   for row in self.kept(db))

    def priced_rows(self, db: Session) -> list[dict]:
        return [dict(row) for row in self.rows]

    def parts(self) -> list:
        return [self.kind, list(self.rows), self.named]


@dataclass(frozen=True)
class TaxTimezone(PastYearWrite):
    """Settings' Save of the tax timezone, and the recalculation it makes:
    holding periods, tax years and 2026's covered date all go by dates in
    it (each pass reads them in its own: past_years._compare)."""
    name: str
    kind = "tax timezone"
    by_date_text = by_date_with_fixes_text = TIMEZONE_BY_DATE

    def apply(self, db: Session) -> None:
        tax_time.set_tax_timezone(db, self.name)
        tx_service.recalculate_all_transactions(db)

    def save(self, db: Session) -> None:
        def save() -> None:
            self.apply(db)
            db.commit()

        # A price the recalculation needs is looked for with the lock free (#426)
        hourly_prices.with_prices_found(db, save)

    def earliest_year(self, db: Session, tz) -> int | None:
        """The first transaction's tax year, in whichever timezone puts it earlier."""
        first = db.query(func.min(Transaction.timestamp)).scalar()
        if first is None:
            return None
        return min(tax_time.local_date(first, zone).year for zone in (tz, ZoneInfo(self.name)))

    def this_year(self, tz) -> int:
        # Around 1 January the two timezones can be in different tax years: a
        # year still earlier in either counts as earlier, so the warning asks
        return max(tax_time.current_tax_year(tz), tax_time.current_tax_year(ZoneInfo(self.name)))

    def moves_no_figure(self, db: Session) -> bool:
        """The timezone in use saved again: every date reads as before."""
        return tax_time.get_tax_timezone(db).key == self.name

    def parts(self) -> list:
        return [self.kind, self.name]


@dataclass(frozen=True)
class AccountChange(PastYearWrite):
    """
    PUT /api/accounts/{id}: hiding or showing an account, and an exchange's
    "This exchange sends me a Form 1099-DA" (5.9). It replays nothing: a
    box is worked out when a report is built (form_8949.disposal_box), never
    stored, so the dry run compares the boxes of the exchange's Sells under
    each setting, and asks only when the switch changes and the exchange
    has a Sell before this tax year.
    """
    account_id: int
    hidden: bool | None = None
    sends_1099da: bool | None = None
    kind = "account"

    def apply(self, db: Session) -> None:
        account_service.apply_change(db, self.account_id, hidden=self.hidden, sends_1099da=self.sends_1099da)

    def save(self, db: Session) -> None:
        account_service.change_account(db, self.account_id, hidden=self.hidden, sends_1099da=self.sends_1099da)

    def earliest_year(self, db: Session, tz) -> int | None:
        now = account_service.sends_1099da(db, self.account_id)  # None: not an exchange's account
        if self.sends_1099da is None or now is None or now == self.sends_1099da:
            return None
        first = (db.query(func.min(Transaction.timestamp))
                 .filter(Transaction.type == "Sell",
                         Transaction.from_account_id.in_(account_service.exchange_accounts(db, self.account_id)))
                 .scalar())
        return None if first is None else tax_time.local_date(first, tz).year

    def recalculates(self, db: Session) -> bool:
        return False

    def parts(self) -> list:
        return [self.kind, self.account_id, self.hidden, self.sends_1099da]


@dataclass(frozen=True)
class Recalculation(PastYearWrite):
    """
    Recalculate Ledger with the AI key: what it changes is what the rules
    fixed since rows were saved give, so it's all pending (2.0 spec 5.8).
    With a login it's the owner's own fix, and never asks. While this
    BitcoinTX last recalculated the ledger (recalculated_by), nothing is
    pending, and it moves no figure.
    """
    kind = "recalculate"
    pending_only = True
    changes_text = RECALCULATES
    by_date_text = by_date_with_fixes_text = RECALCULATES_BY_DATE

    def apply(self, db: Session) -> None:
        tx_service.recalculate_all_transactions(db)

    def save(self, db: Session) -> None:
        tx_service.recalculate_ledger(db)

    def earliest_year(self, db: Session, tz) -> int | None:
        first = db.query(func.min(Transaction.timestamp)).scalar()
        return None if first is None else tax_time.local_date(first, tz).year

    def moves_no_figure(self, db: Session) -> bool:
        return recalculated_by.matches(db)

    def parts(self) -> list:
        return [self.kind]

