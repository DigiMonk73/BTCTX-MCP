"""
The "pre-change" copies (5.8, B6b-2): before a confirmed save that changes
an earlier tax year, with a login, BitcoinTX copies the database into
backups/ as btctx-pre-change-earlier-year-<second>.db. The pruning keeps
the newest 5 and, for the last 7 UTC days, the first of each day, so a run
of confirmed saves can't push out the copy from before the first of them.
Not a "before-" kind: 1.x takes every btctx-before-*.db but its own kinds
for a pre-upgrade copy, so after going back to 1.x (5.16) these would push
out its older ones.
"""

import os
import sqlite3
import time
from pathlib import Path

import pytest

from backend import migrate
from backend.migrate import (PRE_CHANGE_COPIES_KEPT, PRE_CHANGE_KIND, PRE_CHANGE_LABEL, backup_copies,
                             backup_sqlite)

DAY = 86400


@pytest.fixture
def db_file(tmp_path) -> Path:
    path = tmp_path / "btctx.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (x TEXT)")
    conn.commit()
    conn.close()
    return path


def marked(path: Path, mark: str, days_old: int = 0, hour: int = 12) -> Path:
    """A pre-change copy holding `mark`, made `days_old` UTC days ago at `hour`."""
    conn = sqlite3.connect(path)
    conn.execute("DELETE FROM t")
    conn.execute("INSERT INTO t VALUES (?)", (mark,))
    conn.commit()
    conn.close()
    copy = backup_sqlite(path, PRE_CHANGE_LABEL, kind=PRE_CHANGE_KIND, keep=PRE_CHANGE_COPIES_KEPT)
    if days_old:
        midnight = time.time() // DAY * DAY
        then = midnight - days_old * DAY + hour * 3600
        os.utime(copy, (then, then))
    return copy


def marks(copies) -> set[str]:
    found = set()
    for copy in copies:
        conn = sqlite3.connect(copy)
        found |= {row[0] for row in conn.execute("SELECT x FROM t")}
        conn.close()
    return found


def test_the_kind_its_label_and_how_many_are_kept():
    assert (PRE_CHANGE_KIND, PRE_CHANGE_LABEL, PRE_CHANGE_COPIES_KEPT) == ("pre-change", "earlier-year", 5)
    assert PRE_CHANGE_KIND in migrate.COPY_KINDS


def test_its_name_is_one_1x_never_takes_for_a_pre_upgrade_copy(db_file):
    copy = marked(db_file, "one")
    assert copy.name.startswith("btctx-pre-change-earlier-year-")
    assert not copy.name.startswith("btctx-before-")  # 1.x's "before" copies: btctx-before-*.db
    assert backup_copies(db_file, "before") == []
    assert backup_copies(db_file, PRE_CHANGE_KIND) == [copy]


def test_the_newest_five_and_the_first_of_today_stay(db_file):
    for n in range(1, 9):
        marked(db_file, f"save {n}")
    assert marks(backup_copies(db_file, PRE_CHANGE_KIND)) == {"save 1", "save 4", "save 5", "save 6", "save 7",
                                                               "save 8"}


def test_for_a_week_the_first_copy_of_each_day_stays(db_file):
    for mark, days, hour in (("10 days a", 10, 9), ("6 days a", 6, 9), ("6 days b", 6, 15), ("3 days a", 3, 9),
                             ("3 days b", 3, 15)):
        marked(db_file, mark, days, hour)
    for n in range(1, 6):
        marked(db_file, f"today {n}")
    assert marks(backup_copies(db_file, PRE_CHANGE_KIND)) == {"6 days a", "3 days a", "today 1", "today 2",
                                                               "today 3", "today 4", "today 5"}


def test_other_kinds_are_left_alone(db_file):
    upgrade = backup_sqlite(db_file, "upgrade")
    review = [backup_sqlite(db_file, "hourly-prices", kind="review", keep=2) for _ in range(4)]
    for n in range(1, 8):
        marked(db_file, f"save {n}")
    assert upgrade.exists()
    assert set(backup_copies(db_file, "review")) == set(review[2:])  # no first of the day for them
    assert len(backup_copies(db_file, PRE_CHANGE_KIND)) == 6
