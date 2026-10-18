"""
#485: a Spent withdrawal saved before BitcoinTX kept a withdrawal's gross
(gross_proceeds_usd blank, proceeds_usd the net that version stored, its BTC
fee's offset taken off), edited in the form and saved unchanged, must keep
its proceeds. The form now opens it with the gross the server recovers for
it (frontend/src/utils/transactionForm.ts, `withdrawalProceeds`; its unit
tests: oldSpendGross485.test.ts; the click-through:
e2e/old-spend-gross-485.e2e.ts). These tests send the body the form builds
now, and the one 1.2.8's built, and check what the server keeps.
"""

from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from backend.models.transaction import Transaction
from backend.tests.conftest import stub_prices_at

BANK, EXCHANGE_BTC, EXTERNAL = 1, 4, 99
D = Decimal

SPENT = dict(type="Withdrawal", timestamp="2024-06-01T00:00:00Z", from_account_id=EXCHANGE_BTC,
             to_account_id=EXTERNAL, amount="0.01", fee_amount="0.0001", fee_currency="BTC",
             purpose="Spent", proceeds_usd="1000.00")


@pytest.fixture(autouse=True)
def _ledger(auth_client, monkeypatch):
    stub_prices_at(monkeypatch, lambda when: D("100000"))
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    post(auth_client, type="Buy", timestamp="2023-01-01T00:00:00Z", from_account_id=BANK,
         to_account_id=EXCHANGE_BTC, amount="0.1", cost_basis_usd="2000.00")
    yield
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def post(client, **body) -> dict:
    r = client.post("/api/transactions", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def as_saved_before_0_8(test_engine, tx_id: int, purpose: str = "Spent") -> None:
    """No gross, and the net that version stored: 1,000 x 0.01 / 0.0101 (its fee offset)."""
    db = sessionmaker(bind=test_engine)()
    try:
        db.query(Transaction).filter(Transaction.id == tx_id).update(
            {Transaction.gross_proceeds_usd: None, Transaction.proceeds_usd: D("990.10"),
             Transaction.purpose: purpose})
        db.commit()
    finally:
        db.close()


def form_body(tx: dict, proceeds) -> dict:
    keys = ("type", "timestamp", "from_account_id", "to_account_id", "amount", "fee_amount", "fee_currency",
            "purpose")
    return {**{k: tx[k] for k in keys}, "purpose": "Spent", "proceeds_usd": proceeds, "fmv_usd": None,
            "cost_basis_usd": None, "broker_reporting": None, "acquired_at": None}


def test_the_forms_body_keeps_the_recovered_gross(auth_client, test_engine):
    tx = post(auth_client, **SPENT)
    as_saved_before_0_8(test_engine, tx["id"])
    r = auth_client.put(f"/api/transactions/{tx['id']}", json=form_body(tx, 1000))
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["gross_proceeds_usd"] == "1000.00" and after["proceeds_from_price"] is False
    # As its own recovery at a recalculation gives (test_disposal_proceeds.py)
    assert D(after["proceeds_usd"]) == D("990.00") and D(after["realized_gain_usd"]) == D("790.00")


def test_1_2_8s_body_was_a_typed_0(auth_client, test_engine):
    """What #485 saw: the form sent $0, which the server keeps as typed (as any $0 sent is)."""
    tx = post(auth_client, **SPENT)
    as_saved_before_0_8(test_engine, tx["id"])
    after = auth_client.put(f"/api/transactions/{tx['id']}", json=form_body(tx, 0)).json()
    assert after["gross_proceeds_usd"] == "0.00" and D(after["realized_gain_usd"]) == D("-200.00")


@pytest.mark.parametrize("net, amount, fee, gross", [
    ("1.50", "0.01", "0.0001", "1.52"), ("12.50", "0.01", "0.0001", "12.62"), ("0.05", "0.02", "0.01", "0.08"),
])
def test_the_gross_recovered_rounds_a_half_cent_to_even(auth_client, test_engine, net, amount, fee, gross):
    """What the form's helper mirrors (oldSpendGross485.test.ts, "rounds ... as the server does")."""
    tx = post(auth_client, **{**SPENT, "amount": amount, "fee_amount": fee})
    db = sessionmaker(bind=test_engine)()
    try:
        db.query(Transaction).filter(Transaction.id == tx["id"]).update(
            {Transaction.gross_proceeds_usd: None, Transaction.proceeds_usd: D(net)})
        db.commit()
    finally:
        db.close()
    assert auth_client.post("/api/transactions/recalculate").status_code == 200
    assert auth_client.get(f"/api/transactions/{tx['id']}").json()["gross_proceeds_usd"] == gross


def test_an_unlisted_purposes_stored_proceeds_made_spent_are_kept(auth_client, test_engine):
    """#61: what such a row received is its stored proceeds, no offset undone; the form shows them,
    and saving it as a Spent keeps them."""
    tx = post(auth_client, **SPENT)
    as_saved_before_0_8(test_engine, tx["id"], purpose="Expenses")
    after = auth_client.put(f"/api/transactions/{tx['id']}", json=form_body(tx, 990.1)).json()
    assert after["purpose"] == "Spent" and after["gross_proceeds_usd"] == "990.10"
