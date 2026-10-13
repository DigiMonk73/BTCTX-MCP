"""
The AI copies in <database dir>/backups/ (kind "ai"): before the AI key's
first deletion in an hour BitcoinTX makes one itself, and the pruning keeps
the newest 3 plus the oldest from the last week. So an AI that deletes
entries and then asks for copies of the emptied ledger can't push out every
copy from before its deletions. The copies the AI asks for are tested in
test_ai_key.py.
"""

import os
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import get_db
from backend.main import app
from backend.migrate import backup_copies, backup_sqlite
from backend.routers import backup
from backend.services import first_run
from backend.tests.conftest import default_login, init_test_db

DEPOSITS = [
    dict(type="Deposit", timestamp=f"2024-0{month}-15T17:00:00Z", from_account_id=99, to_account_id=1,
         amount=str(1000 * month), fee_amount="0", fee_currency="USD", source="N/A")
    for month in (1, 2, 3)
]
DAY = 24 * 3600
WEEK = 7 * DAY


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


def made_before_deleting(path):
    """The AI copies BitcoinTX made before the key's deletions, newest first."""
    return [p for p in backup_copies(path, "ai") if p.name.startswith("btctx-ai-before-deleting-")]


def age(copy, seconds: float) -> None:
    then = time.time() - seconds
    os.utime(copy, (then, then))


def test_copies_asked_for_after_deleting_everything_leave_one_from_before(ledger, monkeypatch):
    path, ids, owner, ai = ledger
    monkeypatch.setattr(backup, "AI_COPY_EVERY", 0)
    for tx_id in ids:
        assert ai.delete(f"/api/transactions/{tx_id}").status_code == 204
    assert owner.get("/api/transactions").json() == []
    for _ in range(3):
        assert ai.post("/api/backup/ai-copy").status_code == 200

    copies = backup_copies(path, "ai")
    assert any(transaction_ids(copy) == set(ids) for copy in copies), [c.name for c in copies]
    assert len(copies) == 4  # the 3 newest, and the one from before the deletions


def test_one_copy_before_deleting_an_hour_not_one_per_deletion(ledger):
    path, ids, owner, ai = ledger
    assert ai.delete(f"/api/transactions/{ids[0]}").status_code == 204
    assert ai.delete(f"/api/transactions/{ids[1]}").status_code == 204
    [first] = made_before_deleting(path)
    assert transaction_ids(first) == set(ids)

    age(first, 3601)
    assert ai.delete(f"/api/transactions/{ids[2]}").status_code == 204
    second, older = made_before_deleting(path)
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


def test_a_missing_entry_is_still_404_with_the_key(ledger):
    path, ids, owner, ai = ledger
    r = ai.delete("/api/transactions/999999")
    assert r.status_code == 404 and r.json()["detail"] == "Transaction not found."
    assert len(owner.get("/api/transactions").json()) == 3


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


def test_the_oldest_ai_copy_of_the_last_week_is_kept_too(db_file, monkeypatch):
    path, session = db_file
    monkeypatch.setattr(backup, "AI_COPY_EVERY", 0)
    upgrade = backup_sqlite(path, "upgrade")
    review = backup_sqlite(path, "hourly-prices", kind="review")
    ten_days, six_days, five_days = (backup.ai_copy(db=session)["file"] for _ in range(3))
    for name, days in ((ten_days, 10), (six_days, 6), (five_days, 5)):
        age(path.parent / "backups" / name, days * DAY)
    newest = [backup.ai_copy(db=session)["file"] for _ in range(3)]

    kept = {p.name for p in backup_copies(path, "ai")}
    assert kept == {*newest, six_days}
    assert upgrade.exists() and review.exists()


def test_with_no_copy_from_the_last_week_only_the_newest_3_stay(db_file, monkeypatch):
    path, session = db_file
    monkeypatch.setattr(backup, "AI_COPY_EVERY", 0)
    old = [backup.ai_copy(db=session)["file"] for _ in range(2)]
    for name in old:
        age(path.parent / "backups" / name, WEEK + DAY)
    newest = [backup.ai_copy(db=session)["file"] for _ in range(3)]
    assert {p.name for p in backup_copies(path, "ai")} == set(newest)
