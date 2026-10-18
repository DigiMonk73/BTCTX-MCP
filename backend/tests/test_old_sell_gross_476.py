"""
backend/tests/test_old_sell_gross_476.py

#476: a Sell saved before BitcoinTX kept a sale's gross (gross_proceeds_usd
blank, proceeds_usd already net of its USD fee), edited in the form and saved
unchanged, must keep its figures. The form now opens it with the gross the
server recovers for it, the net plus the USD fee
(frontend/src/utils/transactionForm.ts, `sellGross`; its unit tests:
oldSellGross476.test.ts; the click-through: e2e/old-sell-gross-476.e2e.ts).
These tests send that body, as the form builds it, and check the server keeps
every figure: the sale's proceeds and gain, and the Exchange USD balance.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.models.transaction import Transaction
from backend.tests.conftest import stub_prices_at

CLIENT: TestClient = None
ENGINE = None

BANK, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 3, 4, 99

SELL = dict(type="Sell", timestamp="2023-06-01T12:00:00Z", from_account_id=EXCHANGE_BTC,
            to_account_id=EXCHANGE_USD, amount="0.05", fee_currency="USD")


@pytest.fixture(autouse=True, scope="session")
def _set_client(auth_client, test_engine):
    global CLIENT, ENGINE
    CLIENT, ENGINE = auth_client, test_engine


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    stub_prices_at(monkeypatch, lambda when: Decimal("30000"))


@pytest.fixture(autouse=True)
def _clean_ledger():
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")


def post(**tx):
    r = CLIENT.post("/api/transactions", json=tx)
    assert r.status_code == 200, r.text
    return r.json()


def get(tx_id):
    return CLIENT.get(f"/api/transactions/{tx_id}").json()


def exchange_usd():
    balances = CLIENT.get("/api/calculations/accounts/balances").json()
    return Decimal(str(next(b["balance"] for b in balances if b["account_id"] == EXCHANGE_USD)))


def forget_gross(tx_id):
    """What a Sell saved before the gross was kept looks like: no gross, the
    net proceeds stored (as test_disposal_proceeds.forget_gross)."""
    db = sessionmaker(bind=ENGINE)()
    try:
        db.query(Transaction).filter(Transaction.id == tx_id).update({Transaction.gross_proceeds_usd: None})
        db.commit()
    finally:
        db.close()


def old_sell(fee):
    """#476's ledger: $50,000 in the bank, 1 BTC bought for $20,000, and
    0.05 BTC sold for $5,000 gross with the fee given, its gross then blanked."""
    post(type="Deposit", timestamp="2023-01-05T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
         amount="50000", fee_amount="0", fee_currency="USD", source="N/A")
    post(type="Buy", timestamp="2023-01-10T12:00:00Z", from_account_id=BANK, to_account_id=EXCHANGE_BTC,
         amount="1", cost_basis_usd="20000.00", fee_amount="0", fee_currency="USD")
    sale = post(**SELL, fee_amount=fee, gross_proceeds_usd="5000.00")
    forget_gross(sale["id"])
    return get(sale["id"])


def form_body(stored, gross):
    """PUT /api/transactions/{id}'s body as the edit form builds a Sell's,
    saved with nothing changed (transactionForm.buildTransactionPayload)."""
    return dict(SELL, fee_amount=float(stored["fee_amount"]), cost_basis_usd=None, gross_proceeds_usd=gross,
                broker_reporting=None, acquired_at=None)


def figures(tx_id):
    tx = get(tx_id)
    return {k: tx[k] for k in ("gross_proceeds_usd", "proceeds_usd", "realized_gain_usd")}


def test_the_old_sell_is_what_476_describes():
    stored = old_sell("10.00")
    assert stored["gross_proceeds_usd"] is None
    assert Decimal(stored["proceeds_usd"]) == Decimal("4990.00")
    assert Decimal(stored["realized_gain_usd"]) == Decimal("3990.00")


def test_saved_unchanged_with_the_gross_the_form_now_shows_keeps_every_figure():
    """The form shows the net plus the USD fee ($4,990 + $10) as the gross."""
    stored = old_sell("10.00")
    before = exchange_usd()
    r = CLIENT.put(f"/api/transactions/{stored['id']}", json=form_body(stored, 5000.0))
    assert r.status_code == 200, r.text
    assert figures(stored["id"]) == {"gross_proceeds_usd": "5000.00", "proceeds_usd": "4990.00",
                                     "realized_gain_usd": "3990.00"}
    assert exchange_usd() == before


def test_with_no_fee_the_net_is_the_gross_and_nothing_moves():
    stored = old_sell("0")
    before = exchange_usd()
    r = CLIENT.put(f"/api/transactions/{stored['id']}", json=form_body(stored, 5000.0))
    assert r.status_code == 200, r.text
    assert figures(stored["id"]) == {"gross_proceeds_usd": "5000.00", "proceeds_usd": "5000.00",
                                     "realized_gain_usd": "4000.00"}
    assert exchange_usd() == before


def test_the_form_and_a_recalculation_recover_the_same_gross():
    """The form's net plus the USD fee is what the server's own recovery
    stores at the next recalculation (_sell_net_proceeds), so the edit form
    shows the same gross before and after one."""
    stored = old_sell("10.00")
    shown = Decimal(stored["proceeds_usd"]) + Decimal(stored["fee_amount"])
    assert CLIENT.post("/api/transactions/recalculate").status_code == 200
    assert Decimal(get(stored["id"])["gross_proceeds_usd"]) == shown == Decimal("5000.00")
