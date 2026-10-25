"""
Which coins a Transfer moves, before it's saved (#706; the owner's decision,
2026-10-25): the Transfer form lists the lots its save takes from the From
account and puts in the To account, each with its date acquired, amount and
cost, oldest first (per-account FIFO, the IRS default). The list is the
save's own (its path run on a scratch copy), so it can't disagree with what
the save then does: a backdated transfer (which replays the ledger) and an
edit included. Nothing is saved, a transfer the save would refuse answers
that refusal, and it's the owner's (a login), never the AI key's.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.main import app
from backend.models.transaction import BitcoinLot, LotDisposal
from backend.services import ai_key, past_years, transfer_coins
from backend.tests.conftest import default_login, stub_prices_at

WALLET, EXCHANGE_BTC, EXTERNAL = 2, 4, 99
COLD = 100  # the first account added: "Cold Storage"


@pytest.fixture
def owner(fresh_app, monkeypatch) -> TestClient:
    """A ledger of its own, logged in, with a second wallet and two lots in
    Wallet: an old one (2017, $300 for 0.3 BTC) and a newer one (2024,
    $30,000 for 0.5 BTC)."""
    stub_prices_at(monkeypatch, lambda when: Decimal("50000"))
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    r = client.post("/api/accounts/", json={"kind": "wallet", "name": "Cold Storage"})
    assert r.status_code == 201 and [a["id"] for a in r.json()] == [COLD], r.text
    my_btc(client, "2023-01-10T12:00:00Z", "0.3", "300", acquired="2017-03-01")
    my_btc(client, "2024-05-01T12:00:00Z", "0.5", "30000", acquired="2024-05-01")
    client.Session = fresh_app
    return client


def my_btc(client, when: str, amount: str, basis: str, acquired: str) -> None:
    r = client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": when, "from_account_id": EXTERNAL, "to_account_id": WALLET,
        "amount": amount, "fee_amount": "0", "source": "MyBTC", "cost_basis_usd": basis, "acquired_at": acquired})
    assert r.status_code == 200, r.text


def transfer(when: str, amount: str, fee: str = "0", to: int = COLD) -> dict:
    """A Transfer out of Wallet as the form sends it: amount is what left, its fee in it."""
    return {"type": "Transfer", "timestamp": when, "from_account_id": WALLET, "to_account_id": to,
            "amount": amount, "fee_amount": fee, "fee_currency": "BTC"}


def coin(acquired: str, btc: str, cost: str, inherited: bool = False) -> dict:
    return {"acquired": acquired, "btc": btc, "cost_usd": cost, "inherited": inherited}


def saved_coins(client, tx_id: int) -> list[dict]:
    """The lots the saved transfer put in its To account, as the preview lists them."""
    with client.Session() as db:
        lots = db.query(BitcoinLot).filter(BitcoinLot.created_txn_id == tx_id).order_by(BitcoinLot.id).all()
        return [coin(lot.acquired_date.date().isoformat(), f"{lot.total_btc:.8f}", f"{lot.cost_basis_usd:.2f}",
                     lot.inherited) for lot in lots]


def saved_fee(client, tx_id: int) -> str:
    with client.Session() as db:
        rows = db.query(LotDisposal).filter(LotDisposal.transaction_id == tx_id, LotDisposal.is_fee).all()
        return f"{sum((Decimal(row.disposed_btc) for row in rows), Decimal(0)):.8f}"


def dump(client) -> list[str]:
    with client.Session() as db:
        return list(db.connection().connection.dbapi_connection.iterdump())


def test_the_oldest_coins_move_first_as_the_save_moves_them(owner):
    """Moving 0.4 BTC (and a 0.0001 fee) moves the 2017 coins first, then
    part of the 2024 ones: each with its date acquired, amount and cost."""
    body = transfer("2025-06-01T12:00:00Z", "0.4001", fee="0.0001")
    r = owner.post("/api/transactions/coins-moved", json=body)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "coins": [coin("2017-03-01", "0.29990000", "299.90"), coin("2024-05-01", "0.10010000", "6006.00")],
        "fee_btc": "0.00010000",
        "detail": None,
    }
    saved = owner.post("/api/transactions", json=body)
    assert saved.status_code == 200, saved.text
    assert r.json()["coins"] == saved_coins(owner, saved.json()["id"])
    assert r.json()["fee_btc"] == saved_fee(owner, saved.json()["id"])


def test_nothing_is_saved(owner):
    before = dump(owner)
    for body in (transfer("2025-06-01T12:00:00Z", "0.4001", fee="0.0001"),
                 transfer("2024-01-01T12:00:00Z", "0.1")):  # backdated: the replay is the scratch copy's
        assert owner.post("/api/transactions/coins-moved", json=body).status_code == 200
    assert dump(owner) == before


def test_a_backdated_transfer_lists_the_coins_its_replay_moves(owner):
    """Today Wallet holds only 2024 coins (a 2025 spend took the 2017 ones),
    but a transfer dated before that spend moves 2017 coins: the save
    replays the ledger in date order, and so does the list."""
    r = owner.post("/api/transactions", json={
        "type": "Withdrawal", "timestamp": "2025-03-01T12:00:00Z", "from_account_id": WALLET,
        "to_account_id": EXTERNAL, "amount": "0.3", "fee_amount": "0", "purpose": "Spent", "proceeds_usd": "15000"})
    assert r.status_code == 200, r.text
    body = transfer("2024-12-01T12:00:00Z", "0.2")
    listed = owner.post("/api/transactions/coins-moved", json=body)
    assert listed.status_code == 200, listed.text
    assert listed.json()["coins"] == [coin("2017-03-01", "0.20000000", "200.00")]
    saved = owner.post("/api/transactions", json=body)
    assert saved.status_code == 200, saved.text
    assert listed.json()["coins"] == saved_coins(owner, saved.json()["id"])


def test_an_edit_lists_the_coins_its_save_moves(owner):
    saved = owner.post("/api/transactions", json=transfer("2025-06-01T12:00:00Z", "0.1"))
    assert saved.status_code == 200, saved.text
    tx_id = saved.json()["id"]
    unchanged = owner.post(f"/api/transactions/{tx_id}/coins-moved", json=transfer("2025-06-01T12:00:00Z", "0.1"))
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["coins"] == saved_coins(owner, tx_id) == [coin("2017-03-01", "0.10000000", "100.00")]

    # More, with a fee: the edit moves the rest of the 2017 coins and some
    # 2024 ones, as its save then does
    edit = transfer("2025-06-01T12:00:00Z", "0.35", fee="0.001")
    before = dump(owner)
    listed = owner.post(f"/api/transactions/{tx_id}/coins-moved", json=edit)
    assert listed.status_code == 200, listed.text
    assert dump(owner) == before
    assert listed.json()["coins"] == [coin("2017-03-01", "0.29900000", "299.00"), coin("2024-05-01", "0.05000000", "3000.00")]
    assert owner.put(f"/api/transactions/{tx_id}", json=edit).status_code == 200
    assert listed.json()["coins"] == saved_coins(owner, tx_id)
    assert listed.json()["fee_btc"] == saved_fee(owner, tx_id) == "0.00100000"


def test_an_edit_of_a_transaction_that_isnt_there(owner):
    r = owner.post("/api/transactions/9999/coins-moved", json=transfer("2025-06-01T12:00:00Z", "0.1"))
    assert r.status_code == 404
    assert r.json()["detail"] == "Transaction not found."


def test_a_transfer_the_save_refuses_answers_its_refusal(owner):
    """More than Wallet holds: the list says what the save would."""
    body = transfer("2025-06-01T12:00:00Z", "2")
    listed = owner.post("/api/transactions/coins-moved", json=body)
    saved = owner.post("/api/transactions", json=body)
    assert listed.status_code == saved.status_code == 400
    assert listed.json()["detail"] == saved.json()["detail"]


def test_only_a_transfer_moves_coins(owner):
    r = owner.post("/api/transactions/coins-moved", json={
        "type": "Withdrawal", "timestamp": "2025-06-01T12:00:00Z", "from_account_id": WALLET,
        "to_account_id": EXTERNAL, "amount": "0.1", "fee_amount": "0", "purpose": "Gift"})
    assert r.status_code == 422
    assert r.json()["detail"] == "Only a Transfer moves coins between your accounts."


def test_another_type_is_refused_before_any_replay(owner):
    """A Buy is asked about no further: not the Buy's own refusal (no cost
    basis), and no replay of the ledger for nothing."""
    r = owner.post("/api/transactions/coins-moved", json={
        "type": "Buy", "timestamp": "2024-01-01T12:00:00Z", "from_account_id": 1, "to_account_id": EXCHANGE_BTC,
        "amount": "0.1", "fee_amount": "0", "fee_currency": "USD"})
    assert r.status_code == 422
    assert r.json()["detail"] == "Only a Transfer moves coins between your accounts."


def test_a_row_deleted_meanwhile_is_not_found(owner, monkeypatch):
    """The edited row gone between the check and the replay: 404, never an unexpected error."""
    saved = owner.post("/api/transactions", json=transfer("2025-06-01T12:00:00Z", "0.1"))
    assert saved.status_code == 200, saved.text
    monkeypatch.setattr(past_years.Write, "apply", lambda self, db: None)
    r = owner.post(f"/api/transactions/{saved.json()['id']}/coins-moved", json=transfer("2025-06-01T12:00:00Z", "0.2"))
    assert r.status_code == 404
    assert r.json()["detail"] == "Transaction not found."


def test_a_move_within_one_wallet_moves_no_coins(owner):
    """A consolidation records only its fee (#159): no coin changes account."""
    r = owner.post("/api/transactions/coins-moved", json=transfer("2025-06-01T12:00:00Z", "0.4", "0.0001", WALLET))
    assert r.status_code == 200, r.text
    assert r.json() == {"coins": [], "fee_btc": "0.00010000", "detail": None}


def test_inherited_coins_stay_inherited(owner):
    r = owner.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2022-01-10T12:00:00Z", "from_account_id": EXTERNAL,
        "to_account_id": WALLET, "amount": "0.01", "fee_amount": "0", "source": "Inherited",
        "cost_basis_usd": "400", "acquired_at": "2021-12-01"})
    assert r.status_code == 200, r.text
    listed = owner.post("/api/transactions/coins-moved", json=transfer("2025-06-01T12:00:00Z", "0.31"))
    assert listed.status_code == 200, listed.text
    assert listed.json()["coins"] == [
        coin("2017-03-01", "0.30000000", "300.00"), coin("2021-12-01", "0.01000000", "400.00", inherited=True)]


def test_past_the_time_budget_it_says_so(owner, monkeypatch):
    """A big ledger's replay can take seconds: past the dry run's time
    budget, the list isn't given, and the form says why."""
    monkeypatch.setattr(past_years, "DRY_RUN_SECONDS", 0)
    r = owner.post("/api/transactions/coins-moved", json=transfer("2024-01-01T12:00:00Z", "0.1"))  # backdated
    assert r.status_code == 200, r.text
    assert r.json() == {"coins": None, "fee_btc": None,
                        "detail": "BitcoinTX couldn't work out in time which coins move. Saving isn't affected."}


def test_a_list_asked_for_again_stops_the_one_before(owner, monkeypatch):
    """The form cancels a request once its transfer changes, but the server
    never hears of it: the older list's replay stops as soon as a newer one
    is asked for, and leaves the time to it."""
    first = transfer_coins._newest_from_now()
    assert not first()
    second = transfer_coins._newest_from_now()
    assert first() and not second()

    monkeypatch.setattr(transfer_coins, "_newest_from_now", lambda: lambda: True)  # one asked for meanwhile
    r = owner.post("/api/transactions/coins-moved", json=transfer("2024-01-01T12:00:00Z", "0.1"))  # backdated
    assert r.status_code == 200, r.text
    assert r.json()["coins"] is None


def test_a_past_year_in_another_tax_timezone_lists_what_its_confirmed_save_moves(owner, tax_year):
    """In Chicago, a lot whose deposit is 03:00 UTC on May 2 was acquired on
    May 1, as Form 8949 prints it; and a transfer dated in an earlier tax
    year lists what its save makes once confirmed."""
    assert owner.put("/api/settings/tax-timezone", json={"timezone": "America/Chicago", "chosen": True}) \
        .status_code == 200
    r = owner.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2024-05-02T03:00:00Z", "from_account_id": EXTERNAL, "to_account_id": WALLET,
        "amount": "0.2", "fee_amount": "0", "source": "MyBTC", "cost_basis_usd": "12000"})
    assert r.status_code == 200, r.text
    tax_year(2026)
    body = transfer("2025-06-01T12:00:00Z", "0.9001", fee="0.0001")
    listed = owner.post("/api/transactions/coins-moved", json=body)
    assert listed.status_code == 200, listed.text
    assert listed.json()["coins"] == [coin("2017-03-01", "0.29990000", "299.90"),
                                      coin("2024-05-01", "0.50000000", "30000.00"),
                                      coin("2024-05-01", "0.10010000", "6006.00")]
    asked = owner.post("/api/transactions", json=body)
    assert asked.status_code == 409, asked.text
    saved = owner.post("/api/transactions", json=body, params={"confirm": asked.json()["confirm"]})
    assert saved.status_code == 200, saved.text
    with owner.Session() as db:
        lots = db.query(BitcoinLot).filter(BitcoinLot.created_txn_id == saved.json()["id"]).order_by(BitcoinLot.id)
        assert [(f"{lot.total_btc:.8f}", f"{lot.cost_basis_usd:.2f}") for lot in lots] == [
            (c["btc"], c["cost_usd"]) for c in listed.json()["coins"]]


def test_the_ai_key_cant_ask(owner):
    with owner.Session() as db:
        ai_key.set_access(db, True)
        key = {"Authorization": f"Bearer {ai_key.create_key(db)}"}
    anyone = TestClient(app)
    body = transfer("2025-06-01T12:00:00Z", "0.1")
    saved = owner.post("/api/transactions", json=body)
    assert saved.status_code == 200, saved.text
    for route in ("/api/transactions/coins-moved", f"/api/transactions/{saved.json()['id']}/coins-moved"):
        assert anyone.post(route, json=body, headers=key).status_code == 403
        assert anyone.post(route, json=body).status_code == 401
    with owner.Session() as db:
        assert db.execute(text("SELECT count(*) FROM transactions")).scalar() == 3
