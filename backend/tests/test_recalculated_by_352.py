"""
recalculated_by (2.0 spec 5.8, 5.15; card B6b #352): which BitcoinTX last
recalculated the live ledger, its version, migration head and tax
timezone. Every full recalculation of the live ledger notes it; a scratch
copy's (Ledger Review's dry run, the past-year warning's) and a report's
partial replays never do. While it matches, nothing is pending.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.database import scratch_copy
from backend.main import app
from backend.migrate import head_revision
from backend.services import recalculated_by
from backend.services.transaction import recalculate_all_transactions
from backend.tests.conftest import default_login, stub_prices_at
from backend.version import app_version

EXTERNAL, WALLET = 99, 2


@pytest.fixture
def ledger(fresh_app, monkeypatch):
    """A ledger of its own, logged in: two deposits into Wallet, saved in
    date order (each added after the other, so nothing is recalculated)."""
    stub_prices_at(monkeypatch, lambda when: Decimal("50000"))
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    first = add(client, "2024-03-01T12:00:00Z", "0.5", "10000")
    second = add(client, "2024-06-01T12:00:00Z", "0.25", "8000")
    return client, fresh_app, first, second


def add(client, when: str, amount: str, basis: str) -> int:
    r = client.post("/api/transactions", json={
        "type": "Deposit", "from_account_id": EXTERNAL, "to_account_id": WALLET, "amount": amount,
        "fee_amount": "0", "timestamp": when, "source": "MyBTC", "cost_basis_usd": basis})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def noted(Session) -> list[str]:
    with Session() as db:
        return [v for (v,) in db.execute(text("SELECT value FROM app_settings WHERE key = 'recalculated_by'"))]


def matches(Session) -> bool:
    with Session() as db:
        return recalculated_by.matches(db)


def test_it_names_the_version_the_migration_head_and_the_tax_timezone(ledger):
    _, Session, _, _ = ledger
    with Session() as db:
        assert recalculated_by.stamp(db) == f"{app_version()} {head_revision()} UTC"


def test_a_ledger_only_added_to_has_none(ledger):
    _, Session, _, _ = ledger
    assert noted(Session) == []
    assert not matches(Session)


@pytest.mark.parametrize("save", [
    pytest.param(lambda c, first, second: add(c, "2024-01-01T12:00:00Z", "0.1", "2000"), id="backdated add"),
    pytest.param(lambda c, first, second: c.put(f"/api/transactions/{first}", json={"cost_basis_usd": "11000"}),
                 id="edit"),
    pytest.param(lambda c, first, second: c.delete(f"/api/transactions/{second}"), id="delete"),
    pytest.param(lambda c, first, second: c.post("/api/transactions/recalculate"), id="recalculate"),
])
def test_a_full_recalculation_of_the_ledger_notes_this_bitcointx(ledger, save):
    client, Session, first, second = ledger
    save(client, first, second)
    with Session() as db:
        assert noted(Session) == [recalculated_by.stamp(db)]
    assert matches(Session)


def test_saving_the_tax_timezone_notes_the_one_saved(ledger):
    client, Session, _, _ = ledger
    r = client.put("/api/settings/tax-timezone", json={"timezone": "America/Chicago", "chosen": True})
    assert r.status_code == 200, r.text
    assert noted(Session)[0].endswith(" America/Chicago")
    assert matches(Session)


def test_a_new_tax_timezone_fallback_leaves_it_unmatched(ledger, monkeypatch):
    client, Session, _, _ = ledger
    client.post("/api/transactions/recalculate")
    assert matches(Session)
    monkeypatch.setenv("BTCTX_TIMEZONE", "America/Chicago")  # between starts: nothing recalculated
    assert not matches(Session)


def test_another_version_or_head_leaves_it_unmatched(ledger):
    client, Session, _, _ = ledger
    client.post("/api/transactions/recalculate")
    with Session() as db:
        db.execute(text("UPDATE app_settings SET value = :v WHERE key = 'recalculated_by'"),
                   {"v": f"{app_version()} 0012 UTC"})
        db.commit()
    assert not matches(Session)


def test_a_partial_replay_notes_nothing(ledger):
    _, Session, _, _ = ledger
    with Session() as db:
        recalculate_all_transactions(db, until=datetime(2024, 5, 1, tzinfo=timezone.utc))
        db.commit()
    assert noted(Session) == []


def test_a_scratch_copys_recalculation_notes_nothing(ledger):
    _, Session, _, _ = ledger
    with Session() as db, scratch_copy(db) as scratch:
        recalculate_all_transactions(scratch)
        assert scratch.execute(text("SELECT value FROM app_settings WHERE key = 'recalculated_by'")).all() == []
    assert noted(Session) == []


def test_ledger_review_and_a_report_note_nothing(ledger):
    client, Session, _, _ = ledger
    assert client.get("/api/review").status_code == 200
    assert client.get("/api/reports/complete_tax_report?year=2024").status_code == 200
    assert noted(Session) == []


def test_a_replay_that_goes_past_a_row_naming_a_missing_account_notes_nothing(ledger):
    """An edit or a delete of one such row goes past the others (#368): they
    skipped their balance check, so a recalculation of the ledger as it is
    would still stop on them."""
    client, Session, _, _ = ledger
    with Session() as db:
        for tx_id, missing in ((970, 999), (972, 998)):
            db.execute(text(
                "INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount, fee_amount,"
                " fee_currency) VALUES (:id, 'Transfer', '2024-07-01T12:00:00Z', 2, :to, '0.1', '0', 'BTC')"),
                {"id": tx_id, "to": missing})
        db.commit()
    assert client.delete("/api/transactions/970").status_code == 204
    assert noted(Session) == []
    assert client.delete("/api/transactions/972").status_code == 204
    assert matches(Session)
