"""
A Buy needs its cost basis (#459). The transactions API saved one without
it, a lot costing $0 whose whole proceeds became gain when sold: a new Buy
sent without cost_basis_usd (or with null), and a Sell retyped as a Buy
(a type change drops the old type's figures). A typed 0 is kept, as a BTC
deposit's is. Ledger Review lists a Buy saved with a $0 or blank basis.
"""

from decimal import Decimal

import pytest
from sqlalchemy import text

BANK, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 3, 4, 99
BUY_BASIS_REQUIRED = "A buy needs its cost basis (cost_basis_usd)"


@pytest.fixture(autouse=True)
def _clean_ledger(auth_client):
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def post(client, **fields):
    return client.post("/api/transactions", json=fields)


def fund_the_bank(client):
    r = post(client, type="Deposit", timestamp="2024-01-01T12:00:00Z", from_account_id=EXTERNAL,
             to_account_id=BANK, amount="100000", fee_amount="0", fee_currency="USD", source="N/A")
    assert r.status_code == 200, r.text


def buy(client, **fields):
    body = {"type": "Buy", "timestamp": "2024-03-01T12:00:00Z", "from_account_id": BANK,
            "to_account_id": EXCHANGE_BTC, "amount": "0.5", "fee_amount": "0", "fee_currency": "USD", **fields}
    return post(client, **body)


def lot_costs(test_engine) -> list[Decimal]:
    with test_engine.connect() as con:
        rows = con.execute(text("SELECT cost_basis_usd FROM bitcoin_lots ORDER BY id")).all()
    return [Decimal(str(cost)) for (cost,) in rows]


def count(client) -> int:
    return len(client.get("/api/transactions").json())


@pytest.mark.parametrize("blank", [{}, {"cost_basis_usd": None}])
def test_a_new_buy_without_its_cost_basis_is_refused(auth_client, test_engine, blank):
    fund_the_bank(auth_client)
    r = buy(auth_client, **blank)
    assert r.status_code == 422 and BUY_BASIS_REQUIRED in r.text, r.text
    assert count(auth_client) == 1 and lot_costs(test_engine) == []


@pytest.mark.parametrize("basis", ["15000", "0"])
def test_a_buy_with_its_cost_basis_saves_and_a_typed_zero_is_kept(auth_client, test_engine, basis):
    fund_the_bank(auth_client)
    r = buy(auth_client, cost_basis_usd=basis, fee_amount="5")
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["cost_basis_usd"])) == Decimal(basis)
    assert lot_costs(test_engine) == [Decimal(basis) + 5]  # a Buy's USD fee is part of its lot's cost


def _buy_then_sell(client) -> int:
    """#459's steps: Buy 1 BTC for $30,000 (2024-03-01), Sell 0.5 BTC for
    $35,000 (2024-04-01). The Sell's id."""
    fund_the_bank(client)
    assert buy(client, amount="1", cost_basis_usd="30000").status_code == 200
    r = post(client, type="Sell", timestamp="2024-04-01T12:00:00Z", from_account_id=EXCHANGE_BTC,
             to_account_id=EXCHANGE_USD, amount="0.5", fee_amount="0", fee_currency="USD",
             gross_proceeds_usd="35000")
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_a_sell_retyped_as_a_buy_without_a_cost_basis_is_refused(auth_client, test_engine):
    sell_id = _buy_then_sell(auth_client)
    before = auth_client.get(f"/api/transactions/{sell_id}").json()
    r = auth_client.put(f"/api/transactions/{sell_id}",
                        json={"type": "Buy", "from_account_id": BANK, "to_account_id": EXCHANGE_BTC})
    assert r.status_code == 422 and BUY_BASIS_REQUIRED in r.text, r.text
    assert auth_client.get(f"/api/transactions/{sell_id}").json() == before
    assert lot_costs(test_engine) == [Decimal("30000")]

    r = auth_client.put(f"/api/transactions/{sell_id}", json={
        "type": "Buy", "from_account_id": BANK, "to_account_id": EXCHANGE_BTC, "cost_basis_usd": "17500"})
    assert r.status_code == 200, r.text
    assert r.json()["type"] == "Buy" and Decimal(str(r.json()["cost_basis_usd"])) == Decimal("17500")
    assert lot_costs(test_engine) == [Decimal("30000"), Decimal("17500")]


def test_a_deposit_retyped_as_a_buy_keeps_its_basis(auth_client, test_engine):
    """Both types take a cost basis, so a type change keeps it: the edit
    needs no new one."""
    fund_the_bank(auth_client)
    r = post(auth_client, type="Deposit", timestamp="2024-03-01T12:00:00Z", from_account_id=EXTERNAL,
             to_account_id=EXCHANGE_BTC, amount="0.5", fee_amount="0", fee_currency="BTC", source="MyBTC",
             cost_basis_usd="12000")
    assert r.status_code == 200, r.text
    r = auth_client.put(f"/api/transactions/{r.json()['id']}",
                        json={"type": "Buy", "from_account_id": BANK, "to_account_id": EXCHANGE_BTC})
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["cost_basis_usd"])) == Decimal("12000")
    assert lot_costs(test_engine) == [Decimal("12000")]


@pytest.mark.parametrize("stored", ["0", "250"])
def test_a_dollar_deposit_retyped_as_a_buy_needs_its_cost_basis(auth_client, test_engine, stored):
    """A dollar deposit's cost basis is no bitcoin's cost: the forms before
    0.9.2 saved 0 on every one, and the API keeps a figure sent with one.
    Kept by the type change, it was the Buy's lot's cost: $0, or made up."""
    fund_the_bank(auth_client)
    r = post(auth_client, type="Deposit", timestamp="2024-03-01T12:00:00Z", from_account_id=EXTERNAL,
             to_account_id=BANK, amount="500", fee_amount="0", fee_currency="USD", source="N/A",
             cost_basis_usd=stored)
    assert r.status_code == 200 and Decimal(str(r.json()["cost_basis_usd"])) == Decimal(stored), r.text
    deposit_id = r.json()["id"]
    retype = {"type": "Buy", "from_account_id": BANK, "to_account_id": EXCHANGE_BTC, "amount": "0.5"}
    r = auth_client.put(f"/api/transactions/{deposit_id}", json=retype)
    assert r.status_code == 422 and BUY_BASIS_REQUIRED in r.text, r.text
    assert lot_costs(test_engine) == []

    r = auth_client.put(f"/api/transactions/{deposit_id}", json={**retype, "cost_basis_usd": "17500"})
    assert r.status_code == 200, r.text
    assert lot_costs(test_engine) == [Decimal("17500")]


def _insert_old_buys(test_engine):
    """Buys as the API saved them before this fix: inserted directly, since
    the save now refuses a blank one."""
    with test_engine.begin() as con:
        for tx_id, basis in ((951, None), (952, "0"), (953, "100")):
            con.execute(text(
                "INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount,"
                " fee_amount, fee_currency, cost_basis_usd)"
                " VALUES (:id, 'Buy', '2024-03-01 12:00:00', :frm, :to, '0.01', '0', 'USD', :basis)"),
                dict(id=tx_id, frm=BANK, to=EXCHANGE_BTC, basis=basis))


def _buy_check(review) -> dict:
    return next(c for c in review["checks"] if c["key"] == "buy_without_basis")


def test_ledger_review_lists_a_buy_saved_with_a_zero_or_blank_basis(auth_client, test_engine):
    fund_the_bank(auth_client)
    _insert_old_buys(test_engine)
    review = auth_client.get("/api/review").json()
    check = _buy_check(review)
    assert check["kind"] == "check" and check["count"] == 2
    assert [(i["id"], i["issue"]) for i in check["items"]] == [
        (951, "Cost basis blank."), (952, "Cost basis $0.00.")]
    assert "before the fee" in check["action"]
    assert review["total"] >= 2


def test_an_old_blank_buy_is_fixed_by_an_edit_that_gives_its_basis(auth_client, test_engine):
    """Editing an old Buy saved without a basis asks for it, as editing a
    BTC deposit saved without one does; with it, the review lists it no more."""
    fund_the_bank(auth_client)
    _insert_old_buys(test_engine)
    r = auth_client.put("/api/transactions/951", json={"amount": "0.02"})
    assert r.status_code == 422 and BUY_BASIS_REQUIRED in r.text, r.text
    r = auth_client.put("/api/transactions/951", json={"amount": "0.02", "cost_basis_usd": "600"})
    assert r.status_code == 200, r.text
    assert [i["id"] for i in _buy_check(auth_client.get("/api/review").json())["items"]] == [952]
