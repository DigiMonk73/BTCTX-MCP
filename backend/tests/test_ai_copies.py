"""
The AI copies in <database dir>/backups/ (kind "ai"): before the AI key's
first change in an hour (an edit or a deletion) BitcoinTX makes one itself,
and the pruning keeps the newest 3 and, for the last 7 UTC days, the oldest
and the first made before a change each day. So for a week the AI copies
hold the ledger from before each day's changes, however many copies are
asked for next. The copies the AI asks for are tested in test_ai_key.py too.
"""

import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import get_db
from backend.main import app
from backend.migrate import AI_CHANGE_LABEL, backup_copies, backup_sqlite
from backend.routers import backup
from backend.routers import transaction as tx_router
from backend.services import first_run
from backend.tests.conftest import default_login, init_test_db

DEPOSITS = [
    dict(type="Deposit", timestamp=f"2024-0{month}-15T17:00:00Z", from_account_id=99, to_account_id=1,
         amount=str(1000 * month), fee_amount="0", fee_currency="USD", source="N/A")
    for month in (1, 2, 3)
]
DAY = 24 * 3600
HOUR = 3601  # a little over, so the next change makes the hour's copy


@pytest.fixture
def ledger(auth_client, tmp_path):
    """
    The app on a database of its own in tmp_path (its copies go to
    tmp_path/backups), holding three deposits: yields the database's path,
    the deposits' ids, a client logged in as the owner, and a client with
    only an AI key.
    """
    path = tmp_path / "btctx.db"
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    init_test_db(engine)
    Session = sessionmaker(bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = override
    first_run.clear_code()
    owner = TestClient(app)
    assert owner.post("/api/login", json=default_login()).status_code == 200
    ids = [owner.post("/api/transactions", json=tx).json()["id"] for tx in DEPOSITS]
    assert owner.put("/api/settings/ai-access", json={"on": True}).status_code == 200
    key = {"Authorization": f"Bearer {owner.post('/api/settings/ai-key').json()['key']}"}
    ai = TestClient(app, headers=key)
    yield path, ids, owner, ai
    first_run.clear_code()
    app.dependency_overrides[get_db] = previous
    engine.dispose()


def transaction_ids(copy) -> set[int]:
    conn = sqlite3.connect(copy)
    try:
        return {row[0] for row in conn.execute("SELECT id FROM transactions")}
    finally:
        conn.close()


def made_before_changing(path):
    """The AI copies BitcoinTX made before the key's changes, newest first."""
    return backup_copies(path, "ai", label=AI_CHANGE_LABEL)


def amounts(copy) -> dict[int, str]:
    conn = sqlite3.connect(copy)
    try:
        return {row[0]: row[1] for row in conn.execute("SELECT id, amount FROM transactions")}
    finally:
        conn.close()


def age(copy, seconds: float) -> None:
    then = time.time() - seconds
    os.utime(copy, (then, then))



def test_copies_asked_for_after_deleting_everything_leave_one_from_before(ledger, monkeypatch):
    path, ids, owner, ai = ledger
    monkeypatch.setattr(backup, "AI_COPY_EVERY", 0)
    for tx_id in ids:
        assert ai.delete(f"/api/transactions/{tx_id}").status_code == 204
    assert owner.get("/api/transactions").json() == []
    answers = [ai.post("/api/backup/ai-copy") for _ in range(3)]
    assert [r.status_code for r in answers] == [200, 200, 200]

    copies = backup_copies(path, "ai")
    assert any(transaction_ids(copy) == set(ids) for copy in copies), [c.name for c in copies]
    assert len(copies) == 4  # the 3 newest, and the one from before the deletions
    assert [r.json()["kept"] for r in answers] == [2, 3, 4]  # what is kept, said as it is


def test_after_an_earlier_copy_the_owners_newer_entries_are_kept_too(ledger, monkeypatch):
    """An AI copy from earlier in the week predates what the owner entered
    since: the copy made before the deletions is kept as well."""
    path, ids, owner, ai = ledger
    monkeypatch.setattr(backup, "AI_COPY_EVERY", 0)
    assert ai.post("/api/backup/ai-copy").status_code == 200
    age(backup_copies(path, "ai")[0], 2 * DAY)
    newer = owner.post("/api/transactions", json=dict(DEPOSITS[0], timestamp="2024-04-15T17:00:00Z")).json()["id"]
    for tx_id in [*ids, newer]:
        assert ai.delete(f"/api/transactions/{tx_id}").status_code == 204
    for _ in range(3):
        assert ai.post("/api/backup/ai-copy").status_code == 200

    copies = backup_copies(path, "ai")
    assert any(transaction_ids(copy) == {*ids, newer} for copy in copies), [c.name for c in copies]
    assert len(copies) == 5  # the 3 newest, the oldest of the week, the one before the change


def test_one_copy_before_deleting_an_hour_not_one_per_deletion(ledger):
    path, ids, owner, ai = ledger
    assert ai.delete(f"/api/transactions/{ids[0]}").status_code == 204
    assert ai.delete(f"/api/transactions/{ids[1]}").status_code == 204
    [first] = made_before_changing(path)
    assert transaction_ids(first) == set(ids)

    age(first, 3601)
    assert ai.delete(f"/api/transactions/{ids[2]}").status_code == 204
    second, older = made_before_changing(path)
    assert older == first and transaction_ids(second) == {ids[2]}


def test_the_copy_before_deleting_never_refuses_a_copy_the_ai_asks_for(ledger):
    path, ids, owner, ai = ledger
    assert ai.delete(f"/api/transactions/{ids[0]}").status_code == 204
    r = ai.post("/api/backup/ai-copy")
    assert r.status_code == 200, r.text
    assert len(backup_copies(path, "ai")) == 2


def test_the_owners_deletions_make_no_copy(ledger):
    path, ids, owner, ai = ledger
    for tx_id in ids:
        assert owner.delete(f"/api/transactions/{tx_id}").status_code == 204
    assert backup_copies(path, "ai") == []


def test_a_missing_entry_is_still_404_with_the_key_and_makes_no_copy(ledger):
    path, ids, owner, ai = ledger
    r = ai.delete("/api/transactions/999999")
    assert r.status_code == 404 and r.json()["detail"] == "Transaction not found."
    assert len(owner.get("/api/transactions").json()) == 3
    assert backup_copies(path, "ai") == []


def test_no_copy_no_deletion_and_no_edit(ledger, monkeypatch):
    path, ids, owner, ai = ledger

    def full_disk(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(tx_router, "backup_sqlite", full_disk)
    r = ai.delete(f"/api/transactions/{ids[0]}")
    assert r.status_code == 500
    assert r.json()["detail"] == "Not deleted: BitcoinTX couldn't make its copy of the database first."
    r = ai.put(f"/api/transactions/{ids[0]}", json={"amount": "1"})
    assert r.status_code == 500
    assert r.json()["detail"] == "Not changed: BitcoinTX couldn't make its copy of the database first."
    assert [tx["amount"] for tx in owner.get("/api/transactions").json()] == ["3000.00000000", "2000.00000000",
                                                                            "1000.00000000"]


# Edits
def test_an_ai_edit_comes_after_a_copy_holding_the_entry_as_it_was(ledger):
    path, ids, owner, ai = ledger
    before = amounts(path)
    r = ai.put(f"/api/transactions/{ids[0]}", json={"amount": "1"})
    assert r.status_code == 200, r.text
    [copy] = made_before_changing(path)
    assert amounts(copy) == before
    assert amounts(path)[ids[0]] != before[ids[0]]


def test_one_copy_an_hour_across_edits_and_deletions(ledger):
    path, ids, owner, ai = ledger
    assert ai.put(f"/api/transactions/{ids[0]}", json={"amount": "1"}).status_code == 200
    assert ai.delete(f"/api/transactions/{ids[1]}").status_code == 204
    assert ai.put(f"/api/transactions/{ids[2]}", json={"amount": "2"}).status_code == 200
    [first] = made_before_changing(path)

    age(first, 3601)
    assert ai.delete(f"/api/transactions/{ids[2]}").status_code == 204
    assert ai.put(f"/api/transactions/{ids[0]}", json={"amount": "3"}).status_code == 200
    second, older = made_before_changing(path)
    assert older == first and set(amounts(second)) == {ids[0], ids[2]}


def test_the_owners_edits_make_no_copy(ledger):
    path, ids, owner, ai = ledger
    for tx_id in ids:
        assert owner.put(f"/api/transactions/{tx_id}", json={"amount": "5"}).status_code == 200
    assert backup_copies(path, "ai") == []


def test_editing_a_missing_entry_is_still_404_with_the_key_and_makes_no_copy(ledger):
    path, ids, owner, ai = ledger
    r = ai.put("/api/transactions/999999", json={"amount": "1"})
    assert r.status_code == 404 and r.json()["detail"] == "Transaction not found."
    assert backup_copies(path, "ai") == []


# A copy that fails, and a change while the copy is being written
def on_each_copy(monkeypatch, then) -> None:
    """sqlite3.connect runs `then` on each copy being written (in backups/)."""
    connect = sqlite3.connect

    def connect_and_then(database, *args, **kwargs):
        connection = connect(database, *args, **kwargs)
        if Path(database).parent.name == "backups":
            then(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect_and_then)


def test_a_copy_that_fails_leaves_nothing_and_the_next_change_makes_one(ledger, monkeypatch):
    """Review of #228: a copy that failed half way ("database or disk is
    full") left a file under a copy's name, which the next change in the
    hour took for its copy."""
    path, ids, owner, ai = ledger
    before = amounts(path)
    with monkeypatch.context() as full_disk:
        on_each_copy(full_disk, lambda copy: copy.execute("PRAGMA max_page_count = 1"))
        r = ai.put(f"/api/transactions/{ids[0]}", json={"amount": "1"})
    assert r.status_code == 500
    assert r.json()["detail"] == "Not changed: BitcoinTX couldn't make its copy of the database first."
    assert list((path.parent / "backups").iterdir()) == []  # not even the unfinished file
    assert amounts(path) == before

    assert ai.put(f"/api/transactions/{ids[0]}", json={"amount": "1"}).status_code == 200
    [copy] = made_before_changing(path)
    assert amounts(copy) == before


def test_a_change_while_the_copy_is_being_written_waits_for_it(ledger, monkeypatch):
    path, ids, owner, ai = ledger
    before = amounts(path)
    on_each_copy(monkeypatch, lambda copy: time.sleep(0.5))  # a slow disk
    answers = {}

    def change(client, tx_id, amount):
        answers[tx_id] = client.put(f"/api/transactions/{tx_id}", json={"amount": amount}).status_code

    first = threading.Thread(target=change, args=(ai, ids[0], "1"))
    first.start()
    time.sleep(0.2)  # the first change's copy is being written
    change(TestClient(app, headers=ai.headers), ids[1], "2")
    first.join()

    assert answers == {ids[0]: 200, ids[1]: 200}
    [copy] = made_before_changing(path)
    assert amounts(copy) == before


# What's kept: for a week, the first copy of each day made before a change
def pass_time(path, seconds: float) -> None:
    """Time passes for the copies: each in backups/ is `seconds` older."""
    for copy in (path.parent / "backups").glob("*.db"):
        then = copy.stat().st_mtime - seconds
        os.utime(copy, (then, then))


def test_the_first_copy_of_the_day_of_a_deletion_is_kept_for_the_week(ledger):
    """Review of #228: an AI copy on day 0, an entry of the owner's on day 1;
    on day 3 the AI deletes an entry, then changes another every hour. The
    copy holding both was gone after 3 hours."""
    path, ids, owner, ai = ledger
    assert ai.post("/api/backup/ai-copy").status_code == 200
    pass_time(path, DAY)
    owners = owner.post("/api/transactions", json=dict(DEPOSITS[0], timestamp="2024-04-15T17:00:00Z")).json()["id"]
    pass_time(path, 2 * DAY)
    assert ai.delete(f"/api/transactions/{ids[0]}").status_code == 204
    for hour in range(1, 4 * 24 + 1):
        pass_time(path, HOUR)
        assert ai.put(f"/api/transactions/{ids[1]}", json={"amount": str(hour)}).status_code == 200
        copies = backup_copies(path, "ai")
        assert any({ids[0], owners} <= transaction_ids(c) for c in copies), f"after {hour} hours"
        assert len(copies) <= 11


def test_a_deletion_late_in_the_week_is_kept_however_many_copies_follow(ledger, monkeypatch):
    """Review of #228: the AI deletes an entry on day 6.8, then changes
    another every hour and asks for 3 copies an hour. Every copy holding the
    deleted entry was gone after 5 hours."""
    path, ids, owner, ai = ledger
    monkeypatch.setattr(backup, "AI_COPY_EVERY", 0)
    assert ai.post("/api/backup/ai-copy").status_code == 200
    pass_time(path, 3 * DAY)
    owners = owner.post("/api/transactions", json=dict(DEPOSITS[0], timestamp="2024-04-15T17:00:00Z")).json()["id"]
    pass_time(path, 3.8 * DAY)
    assert ai.delete(f"/api/transactions/{ids[0]}").status_code == 204
    for hour in range(1, 13):
        pass_time(path, HOUR)
        assert ai.put(f"/api/transactions/{ids[1]}", json={"amount": str(hour)}).status_code == 200
        for _ in range(3):
            assert ai.post("/api/backup/ai-copy").status_code == 200
        copies = backup_copies(path, "ai")
        assert any({ids[0], owners} <= transaction_ids(c) for c in copies), f"after {hour} hours"
        assert len(copies) <= 11


def made_at(path, when: float) -> None:
    """The copies just made were made at `when`. Unlike pass_time, which
    moves every copy across the UTC days' ends, a copy is dated once and
    keeps its day, as a real one does."""
    for copy in (path.parent / "backups").glob("*.db"):
        if copy.stat().st_mtime > time.time() - 600:  # just made
            os.utime(copy, (when, when))


def test_a_week_of_hourly_changes_keeps_the_first_copy_of_each_day(ledger):
    path, ids, owner, ai = ledger
    steps = 8 * 24
    first = time.time() - (steps + 1) * HOUR
    made = []  # (when, the amount it holds) of each copy made before a change
    for hour in range(steps):
        assert ai.put(f"/api/transactions/{ids[1]}", json={"amount": str(hour + 1)}).status_code == 200
        newest = made_before_changing(path)[0]
        made.append((first + hour * HOUR, amounts(newest)[ids[1]]))
        made_at(path, first + hour * HOUR)
        assert len(backup_copies(path, "ai")) <= 11

    today = datetime.now(timezone.utc).date()
    first_each_day = {}
    for when, amount in made:
        day = datetime.fromtimestamp(when, timezone.utc).date()
        if day > today - timedelta(days=7):
            first_each_day.setdefault(day, amount)
    assert len(first_each_day) == 7
    kept = {amounts(copy)[ids[1]] for copy in backup_copies(path, "ai")}
    assert set(first_each_day.values()) <= kept


@pytest.fixture
def db_file(tmp_path):
    path = tmp_path / "btctx.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (x)")
    conn.commit()
    conn.close()
    engine = create_engine(f"sqlite:///{path}")
    session = sessionmaker(bind=engine)()
    yield path, session
    session.close()
    engine.dispose()


def marked_copy(path, session, mark: str, days_old: float = 0):
    """An AI copy of the database holding `mark` (copies made within one
    second can reuse a pruned copy's name, so they're told apart by what
    they hold), made `days_old` days ago."""
    conn = sqlite3.connect(path)
    conn.execute("DELETE FROM t")
    conn.execute("INSERT INTO t VALUES (?)", (mark,))
    conn.commit()
    conn.close()
    copy = path.parent / "backups" / backup.ai_copy(db=session)["file"]
    if days_old:
        age(copy, days_old * DAY)


def marks(copies) -> set[str]:
    found = set()
    for copy in copies:
        conn = sqlite3.connect(copy)
        found |= {row[0] for row in conn.execute("SELECT x FROM t")}
        conn.close()
    return found


def test_the_oldest_ai_copy_of_the_last_week_is_kept_too(db_file, monkeypatch):
    path, session = db_file
    monkeypatch.setattr(backup, "AI_COPY_EVERY", 0)
    upgrade = backup_sqlite(path, "upgrade")
    review = backup_sqlite(path, "hourly-prices", kind="review")
    for mark, days in (("10 days", 10), ("6 days", 6), ("5 days", 5)):
        marked_copy(path, session, mark, days)
    for mark in ("new 1", "new 2", "new 3"):
        marked_copy(path, session, mark)

    assert marks(backup_copies(path, "ai")) == {"new 1", "new 2", "new 3", "6 days"}
    assert upgrade.exists() and review.exists()


def test_with_no_copy_from_the_last_week_only_the_newest_3_stay(db_file, monkeypatch):
    path, session = db_file
    monkeypatch.setattr(backup, "AI_COPY_EVERY", 0)
    for mark in ("old 1", "old 2"):
        marked_copy(path, session, mark, 8)
    for mark in ("new 1", "new 2", "new 3"):
        marked_copy(path, session, mark)
    assert marks(backup_copies(path, "ai")) == {"new 1", "new 2", "new 3"}


def test_other_kinds_keep_only_their_newest(db_file):
    """Pre-upgrade and review copies keep no oldest of the week: only the AI's do."""
    path, session = db_file
    made = [backup_sqlite(path, "hourly-prices", kind="review", keep=2) for _ in range(4)]
    assert set(backup_copies(path, "review")) == set(made[2:])


def test_a_copy_a_stopped_server_left_unfinished_is_removed_later(db_file):
    path, session = db_file
    backups = path.parent / "backups"
    backups.mkdir()
    stale, fresh = backups / ".partial-old.db", backups / ".partial-new.db"
    stale.write_bytes(b"x")
    fresh.write_bytes(b"x")
    age(stale, 2 * 3600)
    backup_sqlite(path, "upgrade")
    assert not stale.exists() and fresh.exists()  # another copy may be writing that one
    assert backup_copies(path) and all(not p.name.startswith(".") for p in backup_copies(path))
