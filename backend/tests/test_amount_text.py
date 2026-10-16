"""
The transactions API writes amounts and fees out with all eight places
(#101), as the CSV export, Form 8949 and Ledger Review do (#74). str() of a
Decimal under 0.000001 is in exponent form, "5E-8" for 5 sats and "0E-8"
for no fee, and the AI connector passes the API's answers on as they are.
"""

import re

import pytest

BANK, EXCH_BTC, EXTERNAL = 1, 4, 99
WRITTEN_OUT = re.compile(r"^\d+\.\d{8}$")


@pytest.fixture(autouse=True)
def funded(auth_client):
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    for body in (
        dict(type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
             amount="100000", fee_amount="0", fee_currency="USD", source="N/A"),
        dict(type="Buy", timestamp="2024-01-03T12:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
             amount="0.001", cost_basis_usd="40.00", fee_amount="2.50", fee_currency="USD"),
    ):
        assert auth_client.post("/api/transactions", json=body).status_code == 200
    yield
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def spend_five_sats(client) -> dict:
    r = client.post("/api/transactions", json=dict(
        type="Withdrawal", timestamp="2024-02-01T12:00:00Z", from_account_id=EXCH_BTC, to_account_id=EXTERNAL,
        amount="0.00000005", fee_amount="0.00000003", fee_currency="BTC", fee_usd="0.01",
        purpose="Spent", gross_proceeds_usd="0.01"))
    assert r.status_code == 200, r.text
    return r.json()


def test_a_few_sats_are_written_out_wherever_the_api_answers(auth_client):
    created = spend_five_sats(auth_client)
    listed = next(t for t in auth_client.get("/api/transactions").json() if t["id"] == created["id"])
    one = auth_client.get(f"/api/transactions/{created['id']}").json()
    edited = auth_client.put(f"/api/transactions/{created['id']}", json={"fee_amount": "0.00000004"}).json()
    for answer in (created, listed, one):
        assert (answer["amount"], answer["fee_amount"]) == ("0.00000005", "0.00000003")
    assert (edited["amount"], edited["fee_amount"]) == ("0.00000005", "0.00000004")


def test_every_amount_and_fee_has_eight_places(auth_client):
    """A dollar amount and a dollar fee too, as the columns hold them: only
    no fee changes, from 0E-8 to 0.00000000."""
    spend_five_sats(auth_client)
    rows = auth_client.get("/api/transactions").json()
    assert [(t["type"], t["amount"], t["fee_amount"]) for t in sorted(rows, key=lambda t: t["timestamp"])] == [
        ("Deposit", "100000.00000000", "0.00000000"),
        ("Buy", "0.00100000", "2.50000000"),
        ("Withdrawal", "0.00000005", "0.00000003"),
    ]
    assert all(WRITTEN_OUT.match(t["amount"]) and WRITTEN_OUT.match(t["fee_amount"]) for t in rows)
