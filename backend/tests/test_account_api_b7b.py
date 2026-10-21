"""
The account API of spec 5.9 on the draft branch (B7b-0, never merged): adding
a bank, a wallet or an exchange, hiding and showing, deleting, the 1099-DA
switch through the past-year warning's stub (B6c, 5.8), and the gate's stub
(B7a, 5.10) that lets a transaction name an account Settings added.
"""


import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import account as account_service
from backend.tests.conftest import default_login


@pytest.fixture
def client(fresh_app) -> TestClient:
    c = TestClient(app)
    assert c.post("/api/login", json=default_login()).status_code == 200
    return c


def add(client, kind, name):
    return client.post("/api/accounts/", json={"kind": kind, "name": name})


def listed(client):
    return {a["id"]: a for a in client.get("/api/accounts/").json()}


def deposit_into(client, account_id, when="2024-01-02T12:00:00Z", amount="1"):
    r = client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": when, "from_account_id": 99, "to_account_id": account_id,
        "amount": amount, "source": "MyBTC", "cost_basis_usd": "40000", "fee_amount": "0", "fee_currency": "BTC"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_a_wallet_gets_id_100_and_the_books_shape(client):
    r = add(client, "wallet", "  Cold   Storage ")
    assert r.status_code == 201, r.text
    assert r.json() == [dict(id=100, name="Cold Storage", kind="wallet", currency="BTC", exchange_id=None,
                             exchange=None, sends_1099da=None, hidden=False, in_use=False)]
    assert add(client, "bank", "Credit Union").json()[0] == dict(
        id=101, name="Credit Union", kind="bank", currency="USD", exchange_id=None, exchange=None,
        sends_1099da=None, hidden=False, in_use=False)


def test_an_exchange_is_the_exchange_and_its_two_accounts(client):
    r = add(client, "exchange", "Kraken")
    assert r.status_code == 201, r.text
    assert [(a["id"], a["name"], a["currency"], a["exchange_id"], a["exchange"], a["sends_1099da"])
            for a in r.json()] == [(100, "Kraken USD", "USD", 2, "Kraken", True),
                                    (101, "Kraken BTC", "BTC", 2, "Kraken", True)]
    order = [a["id"] for a in client.get("/api/accounts/").json()]
    assert order == [1, 2, 3, 4, 100, 101, 5, 6]
    assert listed(client)[4]["sends_1099da"] is True


@pytest.mark.parametrize("kind, name, detail", [
    ("wallet", "", "A name is 1 to 40 characters on one line."),
    ("wallet", "x" * 41, "A name is 1 to 40 characters on one line."),
    ("exchange", "x" * 37, "A name is 1 to 36 characters on one line."),
    ("wallet", "Cold​Storage", "A name is 1 to 40 characters on one line."),
    ("wallet", "Two\nlines", "A name is 1 to 40 characters on one line."),
    ("wallet", "'=Cold", "A name is 1 to 40 characters on one line."),
    ("wallet", "wallet", "'wallet' always means your first wallet in files (CSV, River, BitcoinTX 1.x): "
                         "choose another name."),
    ("bank", "Bank", "'Bank' always means your first bank in files (CSV, River, BitcoinTX 1.x): choose another name."),
    ("exchange", "Exchange", "'Exchange' always means your first exchange in files (CSV, River, BitcoinTX 1.x): "
                             "choose another name."),
    ("wallet", "Exchange BTC", "'Exchange BTC' always means your first exchange in files (CSV, River, "
                               "BitcoinTX 1.x): choose another name."),
    ("wallet", "External", "External means everything outside BitcoinTX: choose another name."),
    ("wallet", "BTC Fees", "An account named 'BTC Fees' already exists."),
])
def test_a_name_is_refused_in_the_specs_words(client, kind, name, detail):
    r = add(client, kind, name)
    assert (r.status_code, r.json()["detail"]) == (400, detail)


def test_names_are_unique_ignoring_case_an_exchanges_halves_included(client):
    assert add(client, "exchange", "Kraken").status_code == 201
    for kind, name in (("exchange", "kraken"), ("wallet", "KRAKEN BTC"), ("bank", "Kraken")):
        r = add(client, kind, name)
        assert (r.status_code, r.json()["detail"]) == (400, f"An account named '{name}' already exists.")
    assert add(client, "exchange", "Kraken Pro").status_code == 201


def test_another_kind_is_a_422(client):
    assert add(client, "fee", "More Fees").status_code == 422


def test_a_deleted_accounts_id_is_never_given_again(client):
    assert add(client, "wallet", "Spare").json()[0]["id"] == 100
    assert client.delete("/api/accounts/100").status_code == 204
    assert add(client, "wallet", "Spare").json()[0]["id"] == 101


def test_hide_and_show_an_exchange_does_both_halves(client):
    add(client, "exchange", "Kraken")
    r = client.put("/api/accounts/101", json={"hidden": True})
    assert r.status_code == 200, r.text
    assert [(a["id"], a["hidden"]) for a in r.json()] == [(100, True), (101, True)]
    assert listed(client)[100]["hidden"] is True
    client.put("/api/accounts/100", json={"hidden": False})
    assert not listed(client)[101]["hidden"]


@pytest.mark.parametrize("account_id", [5, 6])
def test_a_fee_account_cant_be_hidden(client, account_id):
    r = client.put(f"/api/accounts/{account_id}", json={"hidden": True})
    assert (r.status_code, r.json()["detail"]) == (400, account_service.FEES_SHOWN)


@pytest.mark.parametrize("account_id, detail", [
    (1, account_service.FIRST_ONES_KEPT), (2, account_service.FIRST_ONES_KEPT),
    (3, account_service.FIRST_ONES_KEPT), (4, account_service.FIRST_ONES_KEPT),
    (5, account_service.FEES_KEPT), (6, account_service.FEES_KEPT),
])
def test_the_first_and_fee_accounts_cant_be_deleted(client, account_id, detail):
    r = client.delete(f"/api/accounts/{account_id}")
    assert (r.status_code, r.json()["detail"]) == (400, detail)


def test_an_account_in_use_cant_be_deleted_and_an_exchange_goes_whole(client):
    wallet = add(client, "wallet", "Cold Storage").json()[0]["id"]
    deposit_into(client, wallet)
    r = client.delete(f"/api/accounts/{wallet}")
    assert (r.status_code, r.json()["detail"]) == (409, account_service.IN_USE)
    usd, btc = (a["id"] for a in add(client, "exchange", "Kraken").json())
    deposit_into(client, btc)
    assert client.delete(f"/api/accounts/{usd}").status_code == 409  # its other half is in use
    client.delete("/api/transactions/delete_all?confirm=DELETE")
    assert client.delete(f"/api/accounts/{usd}").status_code == 204
    assert {usd, btc} & set(listed(client)) == set()
    assert add(client, "exchange", "Kraken").status_code == 201  # the exchange's name is free again


def test_deleting_an_account_that_isnt_there_is_a_404(client):
    assert client.delete("/api/accounts/999").status_code == 404


def test_the_1099da_switch_without_earlier_years_saves_at_once(client):
    add(client, "exchange", "Kraken")
    r = client.put("/api/accounts/101", json={"sends_1099da": False})
    assert r.status_code == 200, r.text
    assert [a["sends_1099da"] for a in r.json()] == [False, False]
    assert listed(client)[100]["sends_1099da"] is False


def test_the_1099da_switch_on_another_kind_is_refused(client):
    r = client.put("/api/accounts/2", json={"sends_1099da": False})
    assert (r.status_code, r.json()["detail"]) == (400, account_service.NOT_AN_EXCHANGE)


def test_the_1099da_switch_with_earlier_years_asks_first(client, tax_year):
    """B6c's stub of 5.8's warning: a 409 with the years and a fingerprint; the
    same request with ?confirm=<it> saves."""
    year = 2026
    deposit_into(client, 4, when=f"{year - 2}-03-01T12:00:00Z")
    deposit_into(client, 4, when=f"{year - 1}-03-01T12:00:00Z")
    tax_year(year)  # after the deposits: the clock is the one 5.8's warning reads
    r = client.put("/api/accounts/4", json={"sends_1099da": False})
    assert r.status_code == 409
    body = r.json()
    assert body["detail"] == (f"This changes the figures of tax years {year - 2} and {year - 1}, which you may "
                              "already have filed. Confirm to save it: a copy of your ledger is made first.")
    assert (body["years"], body["changes"], body["pending"]) == ([year - 2, year - 1], [], [])
    assert listed(client)[4]["sends_1099da"] is True  # nothing saved
    assert client.put("/api/accounts/4?confirm=wrong", json={"sends_1099da": False}).status_code == 409
    r = client.put(f"/api/accounts/4?confirm={body['confirm']}", json={"sends_1099da": False})
    assert r.status_code == 200, r.text
    assert listed(client)[3]["sends_1099da"] is False


def test_the_gate_stub_lets_a_transaction_name_an_added_account(client):
    wallet = add(client, "wallet", "Cold Storage").json()[0]["id"]
    deposit_into(client, wallet)
    assert listed(client)[wallet]["in_use"] is True
    r = client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2024-01-03T12:00:00Z", "from_account_id": 99, "to_account_id": 5,
        "amount": "1", "source": "MyBTC", "cost_basis_usd": "1", "fee_amount": "0", "fee_currency": "BTC"})
    assert (r.status_code, r.json()["detail"]) == (422, "Unknown account id 5.")  # a fee account is never yours


def tx(client, kind, from_id, to_id, **fields):
    return client.post("/api/transactions", json={
        "type": kind, "timestamp": "2024-06-15T15:00:00Z", "from_account_id": from_id, "to_account_id": to_id,
        "amount": "0.1", "fee_amount": "0", "fee_currency": "USD", **fields})


def test_the_gate_stub_lets_a_buy_and_a_sell_use_an_added_exchange(client):
    usd, btc = (a["id"] for a in add(client, "exchange", "Kraken").json())
    bank = add(client, "bank", "Credit Union").json()[0]["id"]
    funded = client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2024-01-02T12:00:00Z", "from_account_id": 99, "to_account_id": usd,
        "amount": "20000", "source": "N/A", "fee_amount": "0", "fee_currency": "USD"})
    assert funded.status_code == 200, funded.text
    assert tx(client, "Buy", usd, btc, cost_basis_usd="6000").status_code == 200
    assert tx(client, "Buy", bank, btc, cost_basis_usd="6000").status_code == 200
    assert tx(client, "Sell", btc, usd, gross_proceeds_usd="3200").status_code == 200


@pytest.mark.parametrize("kind, from_side, to_side, detail", [
    ("Buy", "1.x USD", "added BTC", "Buy => from and to must be the same exchange."),
    ("Buy", "added USD", "1.x BTC", "Buy => from and to must be the same exchange."),
    ("Sell", "added BTC", "1.x USD", "Sell => from and to must be the same exchange."),
    ("Buy", "wallet", "added BTC", "Buy => from must be Bank or Exchange USD."),
    ("Sell", "added BTC", "bank", "Sell => to must be Exchange USD."),
])
def test_a_buy_or_sell_across_two_exchanges_or_kinds_is_refused(client, kind, from_side, to_side, detail):
    usd, btc = (a["id"] for a in add(client, "exchange", "Kraken").json())
    sides = {"1.x USD": 3, "1.x BTC": 4, "added USD": usd, "added BTC": btc,
             "wallet": add(client, "wallet", "Cold").json()[0]["id"], "bank": 1}
    r = tx(client, kind, sides[from_side], sides[to_side], cost_basis_usd="6000", gross_proceeds_usd="3200")
    assert r.status_code == 400
    assert r.json()["detail"] == detail
