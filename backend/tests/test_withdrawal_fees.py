"""
F24 (owner decision 2026-09-26): a withdrawal's BTC network fee is its own
disposal at the fee's stored USD value, like a transfer's. A spend's
proceeds are what was received for the amount spent, with no fee cut; a
gift's, donation's or lost withdrawal's fee is taxable even though the gift
itself isn't; a fee is never on a broker form.
"""

from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from backend.services.reports.form_8949 import build_form_8949_and_schedule_d

BANK, WALLET, EXCH_BTC, EXTERNAL = 1, 2, 4, 99
D = Decimal


@pytest.fixture
def ledger(auth_client):
    auth_client.delete("/api/transactions/delete_all")
    for body in (
        dict(type="Deposit", timestamp="2025-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
             amount="100000", fee_amount="0", fee_currency="USD", source="N/A"),
        dict(type="Buy", timestamp="2025-01-03T12:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
             amount="1", cost_basis_usd="20000", fee_amount="0", fee_currency="USD"),
    ):
        assert auth_client.post("/api/transactions", json=body).status_code == 200
    yield
    auth_client.delete("/api/transactions/delete_all")


def withdraw(client, **kw):
    body = dict(type="Withdrawal", timestamp="2025-06-01T12:00:00Z", from_account_id=EXCH_BTC,
                to_account_id=EXTERNAL, amount="0.01", fee_amount="0.0001", fee_currency="BTC", **kw)
    r = client.post("/api/transactions", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def rows(test_engine, year=2025):
    with sessionmaker(bind=test_engine)() as db:
        forms = build_form_8949_and_schedule_d(year, db)
    return sorted(((r["description"], str(r["proceeds"]), str(r["cost"]), str(r["gain_loss"]), r["box"])
                   for r in forms["short_term"] + forms["long_term"]))


def test_a_gifts_fee_is_on_form_8949_and_the_gift_is_not(auth_client, test_engine, ledger):
    tx = withdraw(auth_client, purpose="Gift")
    # Fee: 0.0001 x $50,000 = 5.00, basis 0.0001 x 20,000 = 2.00. Gift: nothing.
    assert D(tx["realized_gain_usd"]) == D("0") and D(tx["fee_usd"]) == D("5.00")
    assert rows(test_engine) == [("0.00010000 BTC", "5.00", "2.00", "3.00", "I")]


def test_a_spends_fee_is_its_own_row_and_never_broker_reported(auth_client, test_engine, ledger):
    withdraw(auth_client, purpose="Spent", proceeds_usd="1000", broker_reporting="basis")
    assert rows(test_engine) == [
        ("0.00010000 BTC", "5.00", "2.00", "3.00", "I"),         # the fee: not on the 1099-DA
        ("0.01000000 BTC", "1000.00", "200.00", "800.00", "G"),  # the spend, as the broker reported it
    ]
