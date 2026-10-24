"""
The "pre-change" copies (2.0 spec 5.8, 5.15; card B6b #352): the copy of the
database a confirmed past-year save makes first, with a login. A kind of its
own, so it never pushes out the pre-upgrade copies, and one that 1.x, after
going back to it (5.16), doesn't take for one of its "before" copies. The
newest 5 are kept and, for a week, the first of each UTC day, so a run of
confirmed saves keeps the copy from before the first of them. Pruned only
once the save is made (prune_backups), so a run rolled back costs no copy.
"""

import os
import sqlite3
import time
from pathlib import Path

import pytest

from backend import migrate
from backend.migrate import (
    COPY_KINDS,
    PRE_CHANGE_COPIES_KEPT,
    PRE_CHANGE_KIND,
    backup_copies,
    backup_sqlite,
    prune_backups,
)

DAY = 86400


@pytest.fixture
def db_path(tmp_path) -> Path:
    path = tmp_path / "btctx.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (x TEXT)")
    conn.commit()
    conn.close()
    return path


def copy(db_path: Path, at: float | None = None) -> Path:
    """A pre-change copy, made now or at `at` (its file time)."""
    made = backup_sqlite(db_path, "past-year", kind=PRE_CHANGE_KIND, keep=None)
    if at is not None:
        os.utime(made, (at, at))
    return made


def test_its_name_and_kind(db_path):
    made = copy(db_path)
    assert PRE_CHANGE_KIND == "pre-change" and PRE_CHANGE_KIND in COPY_KINDS
    assert made.name.startswith("btctx-pre-change-past-year-")
    assert backup_copies(db_path, PRE_CHANGE_KIND) == [made]


def test_no_other_kinds_listing_takes_it_in_1x_or_2_0(db_path):
    made = copy(db_path)
    for kind in COPY_KINDS:
        if kind != PRE_CHANGE_KIND:
            assert made not in backup_copies(db_path, kind), kind
    # 1.x's listing of its own "before" copies: every btctx-before-*.db but
    # the "before-delete" ones, the only longer kind it knows (migrate.py on develop)
    one_x_before = [p for p in (db_path.parent / "backups").glob("btctx-before-*.db")
                    if not p.name.startswith("btctx-before-delete-")]
    assert made not in one_x_before


def test_made_without_pruning_nothing_goes(db_path):
    made = [copy(db_path) for _ in range(PRE_CHANGE_COPIES_KEPT + 2)]
    assert set(backup_copies(db_path, PRE_CHANGE_KIND)) == set(made)


def test_pruned_it_keeps_the_newest_5_and_the_first_of_each_day_for_a_week(db_path):
    today = time.time() // DAY * DAY  # 00:00 UTC
    gone = copy(db_path, at=today - 9 * DAY)  # before the week: today and the 6 days before it
    first_six_days_ago = copy(db_path, at=today - 6 * DAY + 3600)
    copy(db_path, at=today - 6 * DAY + 7200)  # that day's second
    first_today = copy(db_path, at=min(today + 1, time.time()))
    newest = [copy(db_path) for _ in range(PRE_CHANGE_COPIES_KEPT)]
    prune_backups(db_path, PRE_CHANGE_COPIES_KEPT, PRE_CHANGE_KIND)
    assert set(backup_copies(db_path, PRE_CHANGE_KIND)) == {first_six_days_ago, first_today, *newest}
    assert not gone.exists()


def test_pruning_one_kind_leaves_the_others(db_path):
    upgrade = backup_sqlite(db_path, "upgrade")
    ai = backup_sqlite(db_path, migrate.AI_CHANGE_LABEL, kind="ai", keep=migrate.AI_COPIES_KEPT)
    for _ in range(PRE_CHANGE_COPIES_KEPT + 1):
        copy(db_path)
    prune_backups(db_path, PRE_CHANGE_COPIES_KEPT, PRE_CHANGE_KIND)
    assert upgrade.exists() and ai.exists()
