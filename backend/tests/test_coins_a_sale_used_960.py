"""
#960: the coins a sale used, shown in the Sell form (the owner's go,
2026-11-10). The coins-moved routes answer for a Sell, and for a bitcoin
Withdrawal from an exchange as from a wallet, and each coin a disposal takes
carries its proceeds, gain and term from the save's own disposal rows: what
Form 8949 will print for it. A Transfer's coins aren't sold: none of the
three. A gift, donation or lost coins have a term but no proceeds or gain.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.transaction import LotDisposal
from backend.services import ai_key, transfer_coins
from backend.tests.conftest import default_login, stub_prices_at

BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 2, 3, 4, 99


@pytest.fixture
def owner(fresh_app, monkeypatch) -> TestClient:
    """Two lots on the exchange: 0.3 BTC bought in 2023 for $300, and 0.5
    BTC in January 2025 for $30,000."""
    stub_prices_at(monkeypatch, lambda when: Decimal("50000"))
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    for tx in (
        {"type": "Deposit", "timestamp": "2023-01-02T12:00:00Z", "from_account_id": EXTERNAL, "to_account_id": BANK,
         "amount": "50000", "fee_amount": "0", "fee_currency": "USD", "source": "N/A"},
        {"type": "Buy", "timestamp": "2023-01-10T12:00:00Z", "from_account_id": BANK, "to_account_id": EXCHANGE_BTC,
         "amount": "0.3", "cost_basis_usd": "300", "fee_amount": "0", "fee_currency": "USD"},
        {"type": "Buy", "timestamp": "2025-01-10T12:00:00Z", "from_account_id": BANK, "to_account_id": EXCHANGE_BTC,
         "amount": "0.5", "cost_basis_usd": "30000", "fee_amount": "0", "fee_currency": "USD"},
    ):
        r = client.post("/api/transactions", json=tx)
        assert r.status_code == 200, r.text
    client.Session = fresh_app
    return client


SELL = {"type": "Sell", "timestamp": "2025-06-01T12:00:00Z", "from_account_id": EXCHANGE_BTC,
        "to_account_id": EXCHANGE_USD, "amount": "0.4", "gross_proceeds_usd": "40000", "fee_amount": "0",
        "fee_currency": "USD"}


def sale_coin(acquired: str, btc: str, cost: str, proceeds: str | None, gain: str | None, term: str) -> dict:
    return {"acquired": acquired, "btc": btc, "cost_usd": cost, "proceeds_usd": proceeds, "gain_usd": gain,
            "term": term}


def shown(answer: dict) -> list[dict]:
    return [{k: c[k] for k in ("acquired", "btc", "cost_usd", "proceeds_usd", "gain_usd", "term")}
            for c in answer["coins"]]


def saved_rows(client, tx_id: int) -> list[dict]:
    """The sale's disposal rows as Form 8949 reads them."""
    with client.Session() as db:
        rows = (db.query(LotDisposal).filter(LotDisposal.transaction_id == tx_id, LotDisposal.is_fee.is_(False))
                .order_by(LotDisposal.id).all())
        return [{"btc": f"{r.disposed_btc:.8f}", "cost_usd": f"{r.disposal_basis_usd:.2f}",
                 "proceeds_usd": f"{r.proceeds_usd_for_that_portion:.2f}", "gain_usd": f"{r.realized_gain_usd:.2f}",
                 "term": r.holding_period} for r in rows]


def test_a_sale_lists_its_coins_with_proceeds_gain_and_term(owner):
    """The 2023 coins first (long-term), then part of 2025's (short-term),
    the proceeds shared by each piece's BTC."""
    r = owner.post("/api/transactions/coins-moved", json=SELL)
    assert r.status_code == 200, r.text
    assert shown(r.json()) == [
        sale_coin("2023-01-10", "0.30000000", "300.00", "30000.00", "29700.00", "LONG"),
        sale_coin("2025-01-10", "0.10000000", "6000.00", "10000.00", "4000.00", "SHORT"),
    ]
    assert r.json()["held"] is None  # an exchange's coins leave oldest first: nothing to choose
    saved = owner.post("/api/transactions", json=SELL)
    assert saved.status_code == 200, saved.text
    assert [{k: c[k] for k in ("btc", "cost_usd", "proceeds_usd", "gain_usd", "term")} for c in shown(r.json())] \
        == saved_rows(owner, saved.json()["id"])


def test_a_saved_sale_lists_the_coins_it_used(owner):
    saved = owner.post("/api/transactions", json=SELL).json()
    r = owner.post(f"/api/transactions/{saved['id']}/coins-moved", json={})
    assert r.status_code == 200, r.text
    assert [c["term"] for c in r.json()["coins"]] == ["LONG", "SHORT"]


def test_a_spend_from_an_exchange_lists_its_coins(owner):
    spend = {"type": "Withdrawal", "timestamp": "2025-06-01T12:00:00Z", "from_account_id": EXCHANGE_BTC,
             "to_account_id": EXTERNAL, "amount": "0.1", "fee_amount": "0", "fee_currency": "BTC",
             "purpose": "Spent", "proceeds_usd": "5000"}
    r = owner.post("/api/transactions/coins-moved", json=spend)
    assert r.status_code == 200, r.text
    assert shown(r.json()) == [sale_coin("2023-01-10", "0.10000000", "100.00", "5000.00", "4900.00", "LONG")]


def test_a_gift_has_a_term_but_no_proceeds_or_gain(owner):
    gift = {"type": "Withdrawal", "timestamp": "2025-06-01T12:00:00Z", "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXTERNAL, "amount": "0.1", "fee_amount": "0", "fee_currency": "BTC",
            "purpose": "Gift", "fmv_usd": "5000"}
    r = owner.post("/api/transactions/coins-moved", json=gift)
    assert r.status_code == 200, r.text
    assert shown(r.json()) == [sale_coin("2023-01-10", "0.10000000", "100.00", None, None, "LONG")]


def test_a_transfers_coins_are_not_sold(owner):
    move = {"type": "Transfer", "timestamp": "2025-06-01T12:00:00Z", "from_account_id": EXCHANGE_BTC,
            "to_account_id": WALLET, "amount": "0.1", "fee_amount": "0", "fee_currency": "BTC"}
    r = owner.post("/api/transactions/coins-moved", json=move)
    assert r.status_code == 200, r.text
    coin = r.json()["coins"][0]
    assert coin["proceeds_usd"] is None and coin["gain_usd"] is None and coin["term"] is None


@pytest.mark.parametrize("body", [
    {"type": "Withdrawal", "from_account_id": BANK, "to_account_id": EXTERNAL, "amount": "100"},
    {"type": "Buy", "from_account_id": BANK, "to_account_id": EXCHANGE_BTC, "amount": "0.1"},
    {"type": "Deposit", "from_account_id": EXTERNAL, "to_account_id": WALLET, "amount": "0.1", "source": "MyBTC"},
])
def test_what_takes_no_coins_is_still_refused(owner, body):
    r = owner.post("/api/transactions/coins-moved", json={**body, "timestamp": "2025-06-01T12:00:00Z",
                                                          "fee_amount": "0"})
    assert r.status_code == 422 and r.json()["detail"] == transfer_coins.NOT_LISTED


def test_the_ai_key_asks_about_a_saved_sale(owner):
    """The connector's get_coins_moved shows a saved sale's coins too."""
    with owner.Session() as db:
        ai_key.set_access(db, True)
        key = {"Authorization": f"Bearer {ai_key.create_key(db)}"}
    saved = owner.post("/api/transactions", json=SELL).json()
    r = TestClient(app).post(f"/api/transactions/{saved['id']}/coins-moved", json={}, headers=key)
    assert r.status_code == 200, r.text
    assert r.json()["coins"][0]["gain_usd"] == "29700.00"
