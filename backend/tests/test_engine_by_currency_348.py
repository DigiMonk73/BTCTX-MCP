"""
The engine by currency (spec 1.4, 5.7; card B3 #348): every "is it a bitcoin
account?" the save, the edit and the recalculation ask is the book's, so a
second wallet's gifts, spends and edits follow the rules the first one's do
(5.15's "by currency": a gift from it gets its value).
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.tests.conftest import default_login, stub_prices_at

PRICE = Decimal("50000")
COLD, EXTERNAL, BANK = 100, 99, 1


@pytest.fixture
def client(fresh_app, monkeypatch) -> TestClient:
    stub_prices_at(monkeypatch, lambda when: PRICE)
    c = TestClient(app)
    assert c.post("/api/login", json=default_login()).status_code == 200
    r = c.post("/api/accounts/", json={"kind": "wallet", "name": "Cold Storage"})
    assert r.status_code == 201 and r.json()[0]["id"] == COLD, r.text
    save(c, type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=COLD,
         amount="1", source="MyBTC", cost_basis_usd="20000")
    return c


def save(client, **body) -> dict:
    r = client.post("/api/transactions", json={"fee_amount": "0", **body})
    assert r.status_code == 200, r.text
    return r.json()


def edit(client, tx_id, **body) -> dict:
    r = client.put(f"/api/transactions/{tx_id}", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def withdrawal(client, purpose, **fields) -> dict:
    return save(client, type="Withdrawal", timestamp="2024-06-15T15:00:00Z", from_account_id=COLD,
                to_account_id=EXTERNAL, amount="0.1", purpose=purpose, **fields)


def test_a_gift_from_a_second_wallet_gets_its_value(client):
    gift = withdrawal(client, "Gift")
    assert (gift["fmv_usd"], gift["fmv_from_price"]) == ("5000.00", True)
    assert gift["values_from_price"] == ["fmv_usd"]


def test_a_spend_from_a_second_wallet_is_priced_and_has_a_gain(client):
    spent = withdrawal(client, "Spent")
    assert (Decimal(spent["gross_proceeds_usd"]), spent["proceeds_from_price"]) == (Decimal("5000"), True)
    assert Decimal(spent["realized_gain_usd"]) == Decimal("3000")  # 5000 less a tenth of 20000
    assert spent["values_from_price"] == ["gross_proceeds_usd"]
    gains = client.get("/api/calculations/gains-and-losses").json()
    assert gains["withdrawals_spent"] == 5000.0


def test_the_save_prices_a_spends_blank_proceeds_from_a_second_wallet(client, fresh_app):
    from backend.services.transaction import values_the_save_prices
    found = values_the_save_prices({"type": "Withdrawal", "purpose": "Spent", "from_account_id": COLD,
                                    "to_account_id": EXTERNAL, "amount": "0.1"}, fresh_app())
    assert [field for field, _when, _at in found] == ["proceeds_usd"]


def test_a_spends_fee_is_a_cost_of_the_spend_from_a_second_wallet(client):
    """Its proceeds are the gross less its fee's value (#157); a fee worth more
    than the gross leaves $0."""
    spent = withdrawal(client, "Spent", proceeds_usd="5000", fee_amount="0.0001", fee_currency="BTC")
    assert Decimal(spent["proceeds_usd"]) == Decimal("4995")
    small = withdrawal(client, "Spent", proceeds_usd="3", fee_amount="0.0001", fee_currency="BTC")
    assert Decimal(small["proceeds_usd"]) == Decimal("0")


def test_an_edits_proceeds_are_kept_on_a_spend_from_a_second_wallet(client):
    spent = withdrawal(client, "Spent", proceeds_usd="4000")
    edited = edit(client, spent["id"], proceeds_usd="4500")
    assert Decimal(edited["gross_proceeds_usd"]) == Decimal("4500")


def test_a_gifts_value_is_priced_again_when_its_amount_changes(client):
    gift = withdrawal(client, "Gift")
    edited = edit(client, gift["id"], amount="0.2")
    assert (edited["fmv_usd"], edited["fmv_from_price"]) == ("10000.00", True)


def test_a_gifts_0_proceeds_arent_carried_into_a_spend(client):
    """A gift's $0 proceeds (forms before 1.2.9 saved one with every gift) don't
    become a Spent's when an edit makes it one sending none: they're priced (#457)."""
    gift = withdrawal(client, "Gift", fmv_usd="100", proceeds_usd="0")
    edited = edit(client, gift["id"], purpose="Spent")
    assert (Decimal(edited["gross_proceeds_usd"]), edited["proceeds_from_price"]) == (Decimal("5000"), True)


def test_a_spends_0_proceeds_stay_through_an_edit(client):
    spent = withdrawal(client, "Spent", proceeds_usd="0")
    edited = edit(client, spent["id"], amount="0.2")
    assert (Decimal(edited["gross_proceeds_usd"]), edited["proceeds_from_price"]) == (Decimal("0"), False)


def test_a_former_spends_proceeds_stay_when_its_gift_is_made_a_spend_again(client):
    """A gift from a bitcoin account keeps proceeds above $0 it holds (a former
    spend's) when an edit makes it a Spent sending none (#457)."""
    gift = withdrawal(client, "Gift", fmv_usd="100", proceeds_usd="4200")
    edited = edit(client, gift["id"], purpose="Spent")
    assert (Decimal(edited["gross_proceeds_usd"]), edited["proceeds_from_price"]) == (Decimal("4200"), False)


def test_a_dollar_withdrawals_old_proceeds_arent_carried_into_a_gift_from_a_second_wallet(client, fresh_app):
    """What an older save left on a dollar withdrawal (#449) isn't carried into
    the bitcoin withdrawal an edit makes it."""
    from backend.models.transaction import Transaction
    rent = save(client, type="Withdrawal", timestamp="2024-03-01T12:00:00Z", from_account_id=BANK,
                to_account_id=EXTERNAL, amount="100", purpose="Rent")
    db = fresh_app()
    db.get(Transaction, rent["id"]).gross_proceeds_usd = Decimal("300")
    db.commit()
    edited = edit(client, rent["id"], from_account_id=COLD, amount="0.1", purpose="Gift", fee_currency="BTC")
    assert edited["gross_proceeds_usd"] is None


def test_a_deposits_typed_basis_stays_through_an_edit_in_a_second_wallet(client):
    [deposit] = [t for t in client.get("/api/transactions").json() if t["type"] == "Deposit"]
    edited = edit(client, deposit["id"], amount="0.9")
    assert Decimal(edited["cost_basis_usd"]) == Decimal("20000")


def test_a_dollar_deposits_basis_is_dropped_when_an_edit_moves_it_into_a_second_wallet(client):
    dollars = save(client, type="Deposit", timestamp="2024-03-01T12:00:00Z", from_account_id=EXTERNAL,
                   to_account_id=BANK, amount="1", source="N/A", cost_basis_usd="100")
    edited = edit(client, dollars["id"], to_account_id=COLD, source="Income")
    assert (Decimal(edited["cost_basis_usd"]), edited["cost_basis_from_price"]) == (Decimal("50000"), True)
