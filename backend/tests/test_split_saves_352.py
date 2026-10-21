"""
The save paths split from their commit (5.8, B6b-3): apply_create,
apply_update and apply_delete do an add's, an edit's and a delete's own
work, the replay included, and leave the commit (or the rollback) to their
caller. The saves commit them; the past-year warning runs the same paths on
a scratch copy for its dry run, and under the write lock when confirmed, so
the dry run sees exactly what the save will do.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.transaction import LotDisposal, Transaction
from backend.schemas.transaction import TransactionCreate, TransactionUpdate
from backend.services.reports.form_8949 import acquired_text, disposal_box
from backend.services.tax_time import get_tax_timezone, local_date
from backend.services.transaction import apply_create, apply_delete, apply_update
from backend.tests.conftest import default_login
from backend.tests.past_years_ledger import seeded_client


@pytest.fixture
def client(fresh_app) -> TestClient:
    c = TestClient(app)
    assert c.post("/api/login", json=default_login()).status_code == 200
    return c


def deposit_row(when="2024-01-02T12:00:00Z", amount="1") -> dict:
    return {"type": "Deposit", "timestamp": when, "from_account_id": 99, "to_account_id": 2, "amount": amount,
            "source": "MyBTC", "cost_basis_usd": "40000", "fee_amount": "0", "fee_currency": "BTC"}


def add(client, row: dict) -> int:
    r = client.post("/api/transactions", json=row)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def disposals(db) -> list[tuple]:
    """Every lot disposal's proceeds, basis, gain, term, Form 8949 box and column (b)."""
    tz = get_tax_timezone(db)
    rows = []
    for d in db.query(LotDisposal).order_by(LotDisposal.transaction_id, LotDisposal.id):
        year = local_date(d.transaction.timestamp, tz).year
        rows.append((d.transaction_id, str(d.proceeds_usd_for_that_portion), str(d.disposal_basis_usd),
                     str(d.realized_gain_usd), d.holding_period, disposal_box(d, year, tz), acquired_text(d, tz)))
    return rows


def test_an_add_is_left_uncommitted(client, fresh_app):
    add(client, deposit_row())
    with fresh_app() as db:
        # Backdated: the ledger is replayed. The input as the route hands it on (its model's dump)
        new = apply_create(TransactionCreate(**deposit_row("2023-06-01T12:00:00Z", "2")).model_dump(), db)
        assert new.id is not None and db.query(Transaction).count() == 2
        db.rollback()
        assert db.query(Transaction).count() == 1


def test_an_edit_is_left_uncommitted(client, fresh_app):
    tx_id = add(client, deposit_row())
    with fresh_app() as db:
        edited = apply_update(tx_id, TransactionUpdate(amount="2").model_dump(exclude_unset=True), db)
        assert edited.amount == 2
        db.rollback()
        assert db.get(Transaction, tx_id).amount == 1


def test_a_delete_is_left_uncommitted(client, fresh_app):
    tx_id = add(client, deposit_row())
    with fresh_app() as db:
        assert apply_delete(tx_id, db) is True
        assert db.get(Transaction, tx_id) is None
        db.rollback()
        assert db.get(Transaction, tx_id) is not None


def test_a_row_that_isnt_there_is_none_and_false(client, fresh_app):
    with fresh_app() as db:
        assert apply_update(999, {"amount": "2"}, db) is None
        assert apply_delete(999, db) is False


def test_a_refused_delete_says_why_as_the_route_does(client, fresh_app):
    buy = add(client, deposit_row())
    add(client, {"type": "Withdrawal", "timestamp": "2024-02-02T12:00:00Z", "from_account_id": 2,
                 "to_account_id": 99, "amount": "1", "purpose": "Gift", "fmv_usd": "45000", "fee_amount": "0",
                 "fee_currency": "BTC"})
    with fresh_app() as db:
        with pytest.raises(HTTPException) as refused:
            apply_delete(buy, db)
        db.rollback()  # the caller's
        assert db.get(Transaction, buy) is not None
    r = client.delete(f"/api/transactions/{buy}")
    assert (refused.value.status_code, refused.value.detail) == (r.status_code, r.json()["detail"])
    assert refused.value.detail.startswith("Not deleted: later transactions depend on this one. ")


def test_every_reference_row_saved_again_unchanged_keeps_its_disposals(fresh_app):
    """5.15: proceeds, basis, gain, box and term (and column (b)) of every
    disposal, through the split edit path."""
    seeded_client()
    with fresh_app() as db:
        before = disposals(db)
        assert len(before) > 50
        for (tx_id,) in db.query(Transaction.id).order_by(Transaction.id).all():
            assert apply_update(tx_id, {}, db) is not None
            assert disposals(db) == before, f"transaction {tx_id}"
            db.rollback()
