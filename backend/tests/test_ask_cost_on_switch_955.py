"""
#955: a bitcoin deposit valued from the price (income, a reward, a rebate, an inheritance)
that an edit makes My BTC, Gift or N/A asks for its cost, as a new deposit
of those sources does: the market value at receipt isn't what the user's
own coins cost them. The owner's yes, decision 1 on #972 (2026-11-14). An
edit that sends no cost is refused in the create's words; a cost sent with
the switch is the user's, so it's no longer marked as from the price.
"""

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.services.transaction import DEPOSIT_BASIS_REQUIRED
from backend.tests.conftest import stub_prices_at

CLIENT = None


@pytest.fixture(autouse=True, scope="module")
def _set_client(auth_client):
    global CLIENT
    CLIENT = auth_client


@pytest.fixture(autouse=True)
def _ledger(monkeypatch):
    stub_prices_at(monkeypatch, lambda when: 100000)
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")


def _priced(source: str = "Rebate") -> dict:
    """A deposit into the wallet left without a value, filled from the price: $500."""
    r = CLIENT.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2025-03-20T15:00:00Z", "from_account_id": 99, "to_account_id": 2,
        "amount": "0.005", "fee_amount": "0", "fee_currency": "BTC", "source": source})
    assert r.status_code == 200, r.text
    tx = r.json()
    assert tx["cost_basis_from_price"] is True and Decimal(str(tx["cost_basis_usd"])) == Decimal("500")
    return tx


@pytest.mark.parametrize("source", ["MyBTC", "Gift", "N/A"])
def test_a_priced_deposit_made_a_source_that_needs_a_cost_asks_for_it(source):
    tx = _priced()
    r = CLIENT.put(f"/api/transactions/{tx['id']}", json={"source": source})
    assert r.status_code == 422, r.text
    assert DEPOSIT_BASIS_REQUIRED in r.text
    assert CLIENT.get(f"/api/transactions/{tx['id']}").json()["source"] == "Rebate"


@pytest.mark.parametrize("from_source", ["Rebate", "Income", "Interest", "Reward"])
def test_a_cost_sent_with_the_switch_is_the_users(from_source):
    tx = _priced(from_source)
    r = CLIENT.put(f"/api/transactions/{tx['id']}", json={"source": "MyBTC", "cost_basis_usd": "120"})
    assert r.status_code == 200, r.text
    saved = CLIENT.get(f"/api/transactions/{tx['id']}").json()
    assert Decimal(str(saved["cost_basis_usd"])) == Decimal("120")
    assert saved["cost_basis_from_price"] is False


def test_the_market_value_sent_back_with_the_switch_is_the_users_too():
    """An API client that sends back the value shown: sent with the switch, it's the user's figure."""
    tx = _priced()
    r = CLIENT.put(f"/api/transactions/{tx['id']}", json={"source": "MyBTC", "cost_basis_usd": "500"})
    assert r.status_code == 200, r.text
    assert CLIENT.get(f"/api/transactions/{tx['id']}").json()["cost_basis_from_price"] is False


def test_a_zero_cost_sent_with_the_switch_is_kept():
    tx = _priced()
    r = CLIENT.put(f"/api/transactions/{tx['id']}", json={"source": "MyBTC", "cost_basis_usd": "0"})
    assert r.status_code == 200, r.text
    saved = CLIENT.get(f"/api/transactions/{tx['id']}").json()
    assert Decimal(str(saved["cost_basis_usd"])) == Decimal("0") and saved["cost_basis_from_price"] is False


def test_a_switch_between_two_priced_sources_keeps_its_value():
    """Reward to Rebate keeps it (TAX-INVARIANTS, Income deposits)."""
    tx = _priced("Reward")
    r = CLIENT.put(f"/api/transactions/{tx['id']}", json={"source": "Rebate"})
    assert r.status_code == 200, r.text
    saved = CLIENT.get(f"/api/transactions/{tx['id']}").json()
    assert Decimal(str(saved["cost_basis_usd"])) == Decimal("500") and saved["cost_basis_from_price"] is True


def test_a_later_edit_of_a_row_switched_before_isnt_refused(test_engine):
    """A row an earlier version switched (still marked from the price) edits
    as before: only the switch itself asks."""
    tx = _priced()
    with Session(test_engine) as db:
        db.execute(text("UPDATE transactions SET source = 'MyBTC' WHERE id = :id"), {"id": tx["id"]})
        db.commit()
    r = CLIENT.put(f"/api/transactions/{tx['id']}", json={"amount": "0.006"})
    assert r.status_code == 200, r.text


def test_a_move_to_the_bank_needs_no_cost():
    tx = _priced()
    r = CLIENT.put(f"/api/transactions/{tx['id']}", json={"to_account_id": 1, "amount": "500", "source": "N/A"})
    assert r.status_code == 200, r.text
