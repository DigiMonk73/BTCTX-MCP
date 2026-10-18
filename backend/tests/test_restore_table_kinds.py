"""
An in-app restore takes a backup whose tables are ordinary ones: a
generated column, or an index on an expression, works out its values with
the backup's own expression as rows are read or written, and BitcoinTX's
migrations make neither. Such a backup is refused in plain words before
anything runs in it, and the live database stays as it was.

Real restores over a database of their own (test_restore_checks.py's
`live`).
"""

import pytest

from backend.services import backup
from backend.tests.test_restore_checks import _assert_refused, live  # noqa: F401  (live: fixture)

NOT_OURS = "Restore failed: " + backup.NOT_OURS


@pytest.mark.parametrize("sql", [
    ["ALTER TABLE transactions ADD COLUMN memo TEXT AS (printf('%.*c', 1000, 'x')) VIRTUAL"],
    ["CREATE TABLE notes (body TEXT, twice TEXT GENERATED ALWAYS AS (body || body) STORED)",
     "INSERT INTO notes (body) VALUES ('a note')"],
    ["CREATE INDEX ix_transactions_memo ON transactions (printf('%.*c', 1000, 'x'))"],
], ids=["virtual column", "stored column", "index on an expression"])
def test_a_backup_whose_tables_work_out_values_is_refused(live, tmp_path, sql):  # noqa: F811
    _assert_refused(live, sql, NOT_OURS, tmp_path)
