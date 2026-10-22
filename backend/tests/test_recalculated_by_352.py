"""
`recalculated_by` (5.8, B6b-1): which BitcoinTX last recalculated the live
ledger, its version, migration head and tax timezone, in `app_settings`.
Only a full recalculation of the live ledger writes it: never a partial
replay, a scratch copy's replay (Ledger Review's dry run) or an add dated
after the rest (it replays nothing). While it matches, nothing is pending,
so the past-year warning's dry run takes one replay, not two. A restore
takes the backup's.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.database import SCRATCH, scratch_copy
from backend.main import app
from backend.migrate import head_revision
from backend.models.app_setting import AppSetting, save_setting
from backend.services import recalculated, tax_time
from backend.services.transaction import recalculate_all_transactions
from backend.tests.conftest import default_login, keep_in_use
from backend.version import app_version


@pytest.fixture
def client(fresh_app) -> TestClient:
    c = TestClient(app)
    assert c.post("/api/login", json=default_login()).status_code == 200
    return c


def deposit(client, when: str, amount: str = "1") -> int:
    r = client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": when, "from_account_id": 99, "to_account_id": 2,
        "amount": amount, "source": "MyBTC", "cost_basis_usd": "40000", "fee_amount": "0", "fee_currency": "BTC"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def stored(fresh_app) -> str | None:
    with fresh_app() as db:
        row = db.get(AppSetting, recalculated.KEY)
        return row.value if row else None


def test_the_stamp_is_the_version_the_migration_head_and_the_tax_timezone(fresh_app):
    with fresh_app() as db:
        assert recalculated.KEY == "recalculated_by"
        assert recalculated.stamp(db) == f"{app_version()} {head_revision()} UTC"
        tax_time.set_tax_timezone(db, "America/Chicago")
        db.commit()
        assert recalculated.stamp(db) == f"{app_version()} {head_revision()} America/Chicago"


def test_a_fresh_ledger_has_none_and_isnt_current(fresh_app):
    assert stored(fresh_app) is None
    with fresh_app() as db:
        assert recalculated.is_current(db) is False


def test_recalculate_ledger_notes_it(client, fresh_app):
    deposit(client, "2024-01-02T12:00:00Z")
    assert client.post("/api/transactions/recalculate").status_code == 200
    with fresh_app() as db:
        assert stored(fresh_app) == recalculated.stamp(db)
        assert recalculated.is_current(db) is True


def test_adds_dated_after_the_rest_replay_nothing_and_note_nothing(client, fresh_app):
    deposit(client, "2024-01-02T12:00:00Z")
    deposit(client, "2024-02-02T12:00:00Z")
    assert stored(fresh_app) is None


@pytest.mark.parametrize("write", ["backdated add", "edit", "delete"])
def test_each_save_that_replays_the_whole_ledger_notes_it(client, fresh_app, write):
    first = deposit(client, "2024-01-02T12:00:00Z")
    deposit(client, "2024-03-02T12:00:00Z")
    if write == "backdated add":
        deposit(client, "2024-02-02T12:00:00Z")
    elif write == "edit":
        assert client.put(f"/api/transactions/{first}", json={"amount": "2"}).status_code == 200
    else:
        assert client.delete(f"/api/transactions/{first}").status_code == 204
    with fresh_app() as db:
        assert recalculated.is_current(db) is True


def test_a_partial_replay_notes_nothing(client, fresh_app):
    deposit(client, "2024-01-02T12:00:00Z")
    with fresh_app() as db:
        recalculate_all_transactions(db, until=tax_time.tax_year_bounds(2025, tax_time.get_tax_timezone(db))[0])
        db.commit()
    assert stored(fresh_app) is None


def test_a_scratch_copy_is_marked_and_its_replay_notes_nothing(client, fresh_app):
    deposit(client, "2024-01-02T12:00:00Z")
    with fresh_app() as db:
        assert not db.info.get(SCRATCH)
        with scratch_copy(db) as scratch:
            assert scratch.info[SCRATCH] is True
            recalculate_all_transactions(scratch)
            scratch.commit()
            assert scratch.get(AppSetting, recalculated.KEY) is None
    assert client.get("/api/review").status_code == 200  # Ledger Review's dry run, on a scratch copy too
    assert stored(fresh_app) is None


def test_another_tax_timezone_or_version_leaves_it_unmatched(client, fresh_app):
    deposit(client, "2024-01-02T12:00:00Z")
    assert client.post("/api/transactions/recalculate").status_code == 200
    with fresh_app() as db:
        tax_time.set_tax_timezone(db, "Asia/Tokyo")  # saved by hand: no recalculation
        db.commit()
        assert recalculated.is_current(db) is False
        save_setting(db, recalculated.KEY, f"1.2.9 0012 {tax_time.get_tax_timezone(db).key}")
        db.commit()
        assert recalculated.is_current(db) is False


def test_a_restore_takes_the_backups(client, fresh_app, monkeypatch):
    from backend.routers import backup

    engine = fresh_app.kw["bind"]
    deposit(client, "2024-01-02T12:00:00Z")
    assert client.post("/api/transactions/recalculate").status_code == 200

    def restore_backup(password, path, carry_over):  # the backup's database: another BitcoinTX recalculated it
        with keep_in_use(engine, carry_over), engine.begin() as conn:
            conn.execute(text("UPDATE app_settings SET value = '1.2.9 0012 UTC' WHERE key = 'recalculated_by'"))

    monkeypatch.setattr(backup, "restore_backup", restore_backup)
    r = client.post("/api/backup/restore", data={"password": "pw"}, files={"file": ("b.btx", b"x")})
    assert r.status_code == 200, r.text
    assert stored(fresh_app) == "1.2.9 0012 UTC"
