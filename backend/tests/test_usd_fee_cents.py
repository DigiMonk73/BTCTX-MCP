"""
A fee in dollars is in cents (#298). The API checks a fee's decimals as
bitcoin's (it can't know the currency yet), so the save checks a USD fee,
given or filled in, against the cent: a $0.005 fee was accepted and then
lost from the lot's cost. A BTC fee keeps its 8 places.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.services.csv_import import parse_csv_file

CLIENT: TestClient = None
BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 2, 3, 4, 99
HEADER = "date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency,source,purpose"


@pytest.fixture(autouse=True, scope="module")
def _client(auth_client):
    global CLIENT
    CLIENT = auth_client


@pytest.fixture(autouse=True)
def _clean_ledger():
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")
    CLIENT.post("/api/transactions", json=dict(
        type="Deposit", timestamp="2024-01-01T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
        amount="1000", fee_amount="0", fee_currency="USD", source="N/A"))
    yield
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")


def buy(fee: str, currency: str | None = "USD"):
    return CLIENT.post("/api/transactions", json=dict(
        type="Buy", timestamp="2024-01-02T12:00:00Z", from_account_id=BANK, to_account_id=EXCHANGE_BTC,
        amount="0.001", cost_basis_usd="1.00", fee_amount=fee, fee_currency=currency))


@pytest.mark.parametrize("currency", ["USD", None])
def test_a_buys_fee_past_the_cent_is_refused(currency):
    """$1.00 plus a $0.005 fee was saved as a $1.00 lot. Refused, with the
    currency given or filled in (a Buy's fee is USD)."""
    r = buy("0.005", currency)
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == "A USD fee can have at most 2 decimal places."


def test_a_buys_fee_in_cents_is_kept_whole():
    r = buy("0.50")
    assert r.status_code == 200, r.text
    lots = CLIENT.get("/api/debug/lots").json()
    assert [Decimal(str(lot["cost_basis_usd"])) for lot in lots] == [Decimal("1.50")]


def test_a_dollar_withdrawals_fee_past_the_cent_is_refused():
    """A withdrawal from the Bank pays its fee in USD (filled in when blank)."""
    r = CLIENT.post("/api/transactions", json=dict(
        type="Withdrawal", timestamp="2024-01-03T12:00:00Z", from_account_id=BANK, to_account_id=EXTERNAL,
        amount="10.00", fee_amount="0.001", fee_currency=None, purpose="N/A"))
    assert r.status_code == 422 and r.json()["detail"] == "A USD fee can have at most 2 decimal places.", r.text


def test_a_bitcoin_fee_keeps_its_eight_places():
    assert buy("0.50").status_code == 200
    r = CLIENT.post("/api/transactions", json=dict(
        type="Transfer", timestamp="2024-01-04T12:00:00Z", from_account_id=EXCHANGE_BTC, to_account_id=WALLET,
        amount="0.0005", fee_amount="0.00001234", fee_currency="BTC"))
    assert r.status_code == 200, r.text


def test_the_csv_preview_refuses_a_dollar_fee_past_the_cent():
    """The preview takes the save's rule (#266, #285): the row is refused
    there, not only at Import."""
    csv = f"{HEADER}\n2024-01-02T12:00:00Z,Buy,0.001,Bank,Exchange BTC,1.00,,0.005,,,\n"
    result = parse_csv_file(csv.encode())
    assert [(e.column, e.message) for e in result.errors] == [
        ("fee_amount", "A USD fee can have at most 2 decimal places.")]
