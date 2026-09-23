"""
backend/tests/test_transfer_fees.py

BTC Transfer fee semantics: `amount` is what left the source, fee included;
the destination receives amount - fee. Lots (cost basis) must agree with
ledger balances, and River imports (whose amounts exclude the fee) must be
converted on the way in.
"""

import io
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.models.transaction import BitcoinLot, LotDisposal, Transaction

CLIENT: TestClient = None
ENGINE = None

EXCHANGE_BTC, WALLET, EXTERNAL = 4, 2, 99


@pytest.fixture(autouse=True, scope="session")
def _set_client(auth_client, test_engine):
    global CLIENT, ENGINE
    CLIENT, ENGINE = auth_client, test_engine


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    async def fake_historical(date: str):
        return {"USD": 100000.0}

    monkeypatch.setattr("backend.routers.river_import.get_historical_price", fake_historical)
    monkeypatch.setattr(
        "backend.services.transaction.get_btc_price", lambda timestamp, db: Decimal("100000")
    )


@pytest.fixture(autouse=True)
def _clean_ledger():
    CLIENT.delete("/api/transactions/delete_all")
    yield
    CLIENT.delete("/api/transactions/delete_all")


def create(**tx):
    r = CLIENT.post("/api/transactions", json=tx)
    return r


def deposit(amount, month=1):
    r = create(type="Deposit", timestamp=f"2024-{month:02d}-01T00:00:00Z",
               from_account_id=EXTERNAL, to_account_id=EXCHANGE_BTC,
               amount=amount, cost_basis_usd="1000.00", source="MyBTC")
    assert r.status_code == 200, r.text


def transfer(amount, fee, src=EXCHANGE_BTC, dst=WALLET, day=2):
    return create(type="Transfer", timestamp=f"2024-02-{day:02d}T00:00:00Z",
                  from_account_id=src, to_account_id=dst,
                  amount=amount, fee_amount=fee, fee_currency="BTC")


def balances():
    rows = CLIENT.get("/api/calculations/accounts/balances").json()
    return {b["account_id"]: Decimal(str(b["balance"])) for b in rows}


def lot_remaining(account_id):
    db = sessionmaker(bind=ENGINE)()
    try:
        lots = (
            db.query(BitcoinLot)
            .join(Transaction, Transaction.id == BitcoinLot.created_txn_id)
            .filter(Transaction.to_account_id == account_id)
            .all()
        )
        return sum((Decimal(l.remaining_btc) for l in lots), Decimal("0"))
    finally:
        db.close()


def fee_disposed(tx_id):
    db = sessionmaker(bind=ENGINE)()
    try:
        rows = db.query(LotDisposal).filter(LotDisposal.transaction_id == tx_id).all()
        return sum((Decimal(d.disposed_btc) for d in rows), Decimal("0"))
    finally:
        db.close()


def test_transfer_whole_balance_with_fee():
    """Sending everything (fee included) used to fail with 'Not enough BTC'."""
    deposit("0.5")
    r = transfer("0.5", "0.0001")
    assert r.status_code == 200, r.text

    b = balances()
    assert b[EXCHANGE_BTC] == Decimal("0")
    assert b[WALLET] == Decimal("0.4999")
    assert lot_remaining(EXCHANGE_BTC) == Decimal("0")
    assert lot_remaining(WALLET) == Decimal("0.4999")
    assert fee_disposed(r.json()["id"]) == Decimal("0.0001")


def test_lots_match_ledger_after_round_trips():
    deposit("1.0")
    assert transfer("0.6", "0.0002", day=2).status_code == 200
    assert transfer("0.2", "0.0001", src=WALLET, dst=EXCHANGE_BTC, day=3).status_code == 200
    assert transfer("0.3", "0.00005", day=4).status_code == 200

    b = balances()
    for account in (EXCHANGE_BTC, WALLET):
        assert lot_remaining(account) == b[account], f"account {account} lots != ledger"
    assert b[EXCHANGE_BTC] + b[WALLET] == Decimal("1.0") - Decimal("0.00035")


def test_lots_still_match_after_backdated_recalculation():
    deposit("0.5", month=3)
    assert transfer("0.1", "0.0001", day=2).status_code == 400  # before the deposit
    deposit("0.2", month=1)  # backdated: triggers full re-lot of later rows
    assert transfer("0.2", "0.0001", day=2).status_code == 200
    deposit("0.01", month=1)  # another backdated insert
    b = balances()
    for account in (EXCHANGE_BTC, WALLET):
        assert lot_remaining(account) == b[account]


def test_fee_larger_than_amount_is_rejected():
    deposit("0.5")
    r = transfer("0.0001", "0.001")
    assert r.status_code == 400
    assert "exceeds" in r.json()["detail"]


RIVER_HEADER = (
    "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,"
    "Fee Amount,Fee Currency,Tag"
)


def river_preview(rows):
    content = ("\n".join([RIVER_HEADER] + rows) + "\n").encode()
    r = CLIENT.post(
        "/api/import/river/preview",
        files={"file": ("river.csv", io.BytesIO(content), "text/csv")},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_river_send_with_fee_converts_to_fee_inclusive_amount():
    deposit("0.01")
    send = "2024-02-15 10:00:00,0.00100000,BTC,,,0.00000500,BTC,"
    p = river_preview([send])["proposals"][0]
    assert p["type"] == "Transfer" and p["status"] == "new"

    r = CLIENT.post("/api/import/river/execute", json={"rows": [{
        "date": p["date"], "type": "Transfer", "amount": p["amount"],
        "from_account": "Exchange BTC", "to_account": "Wallet",
        "fee_amount": p["fee_amount"], "fee_currency": "BTC",
    }]})
    assert r.status_code == 200, r.text

    txs = [t for t in CLIENT.get("/api/transactions").json() if t["type"] == "Transfer"]
    assert Decimal(txs[0]["amount"]) == Decimal("0.00100500")
    assert balances()[WALLET] == Decimal("0.001")  # what River says arrived
    assert lot_remaining(WALLET) == Decimal("0.001")

    # Re-importing the same file recognizes the converted row
    again = river_preview([send])["proposals"][0]
    assert again["status"] == "matched"
