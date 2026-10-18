"""
#520: a bitcoin withdrawal saved before 0.8.0 (no gross_proceeds_usd
recorded, its proceeds in proceeds_usd), changed into a Sell with a USD
fee before any recalculation had filled its gross in, was saved with
proceeds too high by the fee. The edit's check read the stored proceeds as
the sale's gross; the save read them as the net of an old Sell, and added
the fee on top.
"""

from decimal import Decimal

import pytest
from sqlalchemy import text

BANK, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 3, 4, 99


@pytest.fixture
def ledger(auth_client):
    """#520's ledger: $50,000 in Bank, 1 BTC bought on the exchange for $20,000."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    for body in (
        dict(type="Deposit", timestamp="2023-01-05T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
             amount="50000", fee_amount="0", fee_currency="USD", source="N/A"),
        dict(type="Buy", timestamp="2023-01-10T12:00:00Z", from_account_id=BANK, to_account_id=EXCHANGE_BTC,
             amount="1", cost_basis_usd="20000", fee_amount="0", fee_currency="USD"),
    ):
        r = auth_client.post("/api/transactions", json=body)
        assert r.status_code == 200, r.text
    yield
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def old_withdrawal(client, engine, purpose: str, fee: dict | None = None) -> dict:
    """A withdrawal of 0.05 BTC for $700 as a ledger from before 0.8.0 holds
    it: no gross recorded, its purpose as written then."""
    body = dict(type="Withdrawal", timestamp="2023-06-01T12:00:00Z", from_account_id=EXCHANGE_BTC,
                to_account_id=EXTERNAL, amount="0.05", purpose="Spent", proceeds_usd="700",
                **(fee or dict(fee_amount="0", fee_currency="BTC")))
    r = client.post("/api/transactions", json=body)
    assert r.status_code == 200, r.text
    tx = r.json()
    with engine.begin() as con:
        con.execute(text("UPDATE transactions SET gross_proceeds_usd = NULL, proceeds_usd = '700.00', "
                         "purpose = :purpose WHERE id = :id"), {"purpose": purpose, "id": tx["id"]})
    return tx


def made_a_sell(client, tx_id: int, **changes) -> dict:
    r = client.put(f"/api/transactions/{tx_id}", json={"type": "Sell", "to_account_id": EXCHANGE_USD, **changes})
    assert r.status_code == 200, r.text
    return r.json()


def sale(tx: dict) -> tuple:
    return Decimal(tx["gross_proceeds_usd"]), Decimal(tx["proceeds_usd"]), Decimal(tx["realized_gain_usd"])


@pytest.mark.parametrize("purpose", ["Expenses", "Spent"])
def test_changed_into_a_sell_with_a_usd_fee_its_proceeds_are_the_gross(auth_client, test_engine, ledger, purpose):
    """#520's steps: $700 is the sale's gross, the $10 fee comes off it.
    Basis 0.05 x $20,000 = $1,000."""
    tx = old_withdrawal(auth_client, test_engine, purpose)
    sell = made_a_sell(auth_client, tx["id"], fee_currency="USD", fee_amount="10")
    assert sale(sell) == (Decimal("700.00"), Decimal("690.00"), Decimal("-310.00"))
    assert auth_client.post("/api/transactions/recalculate").status_code == 200
    again = next(t for t in auth_client.get("/api/transactions").json() if t["id"] == tx["id"])
    assert sale(again) == sale(sell)


def test_an_old_spents_fee_offset_is_undone_as_the_form_shows_it(auth_client, test_engine, ledger):
    """A Spent with a BTC fee, saved before 0.9.2, stored its proceeds less
    the fee's offset: $700 for 0.05 BTC with a 0.001 BTC fee was $714
    received, which the edit form shows (#485) and a recalculation recovers.
    Made a Sell, that's its gross."""
    tx = old_withdrawal(auth_client, test_engine, "Spent", fee=dict(fee_amount="0.001", fee_currency="BTC"))
    sell = made_a_sell(auth_client, tx["id"], fee_currency="USD", fee_amount="10")
    assert sale(sell) == (Decimal("714.00"), Decimal("704.00"), Decimal("-296.00"))


def test_the_exchange_gets_the_gross_less_the_fee(auth_client, test_engine, ledger):
    tx = old_withdrawal(auth_client, test_engine, "Expenses")
    made_a_sell(auth_client, tx["id"], fee_currency="USD", fee_amount="10")
    rows = auth_client.get("/api/calculations/accounts/balances").json()
    balances = {b["account_id"]: Decimal(str(b["balance"])) for b in rows}
    assert balances[EXCHANGE_USD] == Decimal("690")


def test_proceeds_sent_with_the_change_are_the_gross(auth_client, test_engine, ledger):
    """What an edit sends stays the sale's gross, as before (#458)."""
    tx = old_withdrawal(auth_client, test_engine, "Expenses")
    sell = made_a_sell(auth_client, tx["id"], fee_currency="USD", fee_amount="10", proceeds_usd="800")
    assert sale(sell) == (Decimal("800.00"), Decimal("790.00"), Decimal("-210.00"))
