"""
Every Transaction column is either carried by the CSV export or listed here
with the reason it isn't, so a new column can't be left out of the export
unnoticed: the BTC fee's USD value, a gift's fair market value and the Broker
form override once were, until 1.2.1. test_csv_roundtrip.py checks that what
is exported imports back to the same ledger.
"""

from backend.models.transaction import Transaction
from backend.services.csv_import import CSV_COLUMNS

# Transaction column -> the CSV column that carries it.
EXPORTED = {
    "timestamp": "date",
    "type": "type",
    "amount": "amount",
    "from_account_id": "from_account",
    "to_account_id": "to_account",
    "cost_basis_usd": "cost_basis_usd",
    # A sale's proceeds column holds the gross figure the user typed, else
    # the stored proceeds (a Spent withdrawal's).
    "gross_proceeds_usd": "proceeds_usd",
    "proceeds_usd": "proceeds_usd",
    "fee_amount": "fee_amount",
    "fee_currency": "fee_currency",
    "source": "source",
    "purpose": "purpose",
    "fee_usd": "fee_usd",
    "fmv_usd": "fmv_usd",
    "broker_reporting": "broker_reporting",
    "fee_usd_manual": "fee_usd_typed",
}

NOT_EXPORTED = {
    "id": "the import numbers the rows anew",
    "created_at": "set when the row is saved",
    "updated_at": "set when the row is saved",
    "realized_gain_usd": "worked out from the lots on every recalculation",
    "holding_period": "worked out from the lots on every recalculation",
    "is_locked": "nothing in the app can lock a row yet (docs/temp/TODO.md)",
}

# CSV columns with no Transaction column behind them.
CSV_ONLY = {"notes"}


def test_every_transaction_column_is_exported_or_listed():
    columns = set(Transaction.__table__.columns.keys())
    unlisted = columns - EXPORTED.keys() - NOT_EXPORTED.keys()
    assert not unlisted, (
        f"New Transaction column(s) {sorted(unlisted)}: export them (CSV_COLUMNS, the export in "
        "routers/backup.py, the import in csv_import.py) or add them to NOT_EXPORTED with the reason"
    )
    assert not (EXPORTED.keys() | NOT_EXPORTED.keys()) - columns, "a listed column no longer exists"
    assert not EXPORTED.keys() & NOT_EXPORTED.keys()


def test_every_csv_column_is_accounted_for():
    assert set(CSV_COLUMNS) == set(EXPORTED.values()) | CSV_ONLY
