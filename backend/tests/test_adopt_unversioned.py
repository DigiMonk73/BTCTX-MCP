"""
Adopting a pre-migration database whose missing columns can't simply be
added: a required one without a default, and one whose default SQLite
won't take in ALTER TABLE. Both refuse the upgrade and change nothing.
"""

import shutil
import sqlite3

import pytest

from backend.migrate import MigrationError, upgrade_database
from backend.tests.test_migrations import FIXTURE, engine_for


def without_column(tmp_path, column: str):
    db = tmp_path / "btctx.db"
    shutil.copy(FIXTURE, db)
    con = sqlite3.connect(str(db))
    con.execute(f"ALTER TABLE transactions DROP COLUMN {column}")
    con.commit()
    con.close()
    return db


def columns(db) -> list[str]:
    con = sqlite3.connect(str(db))
    try:
        return [row[1] for row in con.execute("PRAGMA table_info(transactions)")]
    finally:
        con.close()


def test_a_missing_required_column_is_refused(tmp_path):
    db = without_column(tmp_path, "type")
    before = columns(db)
    with pytest.raises(MigrationError) as refused:
        upgrade_database(engine_for(db), backup=False)
    assert str(refused.value) == (
        "Column transactions.type is missing and required; this database can't be upgraded automatically."
    )
    assert columns(db) == before


def test_a_column_sqlite_cant_add_is_refused(tmp_path):
    db = without_column(tmp_path, "created_at")
    before = columns(db)
    with pytest.raises(MigrationError) as refused:
        upgrade_database(engine_for(db), backup=False)
    assert str(refused.value).startswith("Couldn't add missing column transactions.created_at: ")
    assert "non-constant default" in str(refused.value)
    assert columns(db) == before
