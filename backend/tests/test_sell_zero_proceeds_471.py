"""
backend/tests/test_sell_zero_proceeds_471.py

A Sell's gross of $0 is a $0 sale (#471). The save read it as "no gross
recorded", the case of rows saved before the gross was kept, and took the
stored or sent net as the gross. Edited down to $0, a sale kept its old
proceeds and gain; since #449 and #458 an edit sends the stored net on as
blank, which hid that, but a net sent beside the $0 still became the sale.
Rows saved before the gross was kept (a NULL gross) are still worked out
from their stored net.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.models.transaction import LotDisposal, Transaction

CLIENT: TestClient = None
ENGINE = None

BANK, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 3, 4, 99


@pytest.fixture(autouse=True, scope="module")
def _set_client(auth_client, test_engine):
    global CLIENT, ENGINE
    CLIENT, ENGINE = auth_client, test_engine


@pytest.fixture(autouse=True)
def _clean_ledger():
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")


def post(**tx):
    r = CLIENT.post("/api/transactions", json=tx)
    assert r.status_code == 200, r.text
    return r.json()


def put(tx_id, body):
    r = CLIENT.put(f"/api/transactions/{tx_id}", json=body)
    assert r.status_code == 200, r.text
    return CLIENT.get(f"/api/transactions/{tx_id}").json()


def sale(gross="5000", fee="0", **sent):
    """#471's ledger: $50,000 into Bank, 1 BTC bought for $20,000, 0.05 BTC
    sold (basis $1,000)."""
    post(type="Deposit", timestamp="2023-01-05T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
         amount="50000", source="N/A")
    post(type="Buy", timestamp="2023-01-10T12:00:00Z", from_account_id=BANK, to_account_id=EXCHANGE_BTC,
         amount="1", cost_basis_usd="20000", fee_amount="0", fee_currency="USD")
    return post(type="Sell", timestamp="2023-06-01T12:00:00Z", from_account_id=EXCHANGE_BTC,
                to_account_id=EXCHANGE_USD, amount="0.05", gross_proceeds_usd=gross, fee_amount=fee,
                fee_currency="USD", **sent)


def form_body(tx, gross, fee):
    """What the transaction form sends for a Sell (transactionForm.ts,
    TYPE_PAYLOAD.Sell): its proceeds as gross_proceeds_usd alone."""
    return {"type": "Sell", "timestamp": tx["timestamp"], "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD, "amount": tx["amount"], "fee_amount": fee, "fee_currency": "USD",
            "cost_basis_usd": None, "gross_proceeds_usd": gross, "broker_reporting": None, "acquired_at": None}


def figures(tx):
    return {k: None if tx[k] is None else Decimal(tx[k])
            for k in ("gross_proceeds_usd", "proceeds_usd", "cost_basis_usd", "realized_gain_usd")}


def a_zero_sale():
    return {"gross_proceeds_usd": Decimal("0"), "proceeds_usd": Decimal("0"),
            "cost_basis_usd": Decimal("1000"), "realized_gain_usd": Decimal("-1000")}


def exchange_usd():
    return Decimal(str(CLIENT.get(f"/api/calculations/account/{EXCHANGE_USD}/balance").json()["balance"]))


def disposal_proceeds(tx_id):
    """What Form 8949 reads: the sale's disposal rows' proceeds."""
    db = sessionmaker(bind=ENGINE)()
    try:
        rows = db.query(LotDisposal).filter(LotDisposal.transaction_id == tx_id).all()
        return sum((Decimal(d.proceeds_usd_for_that_portion) for d in rows), Decimal("0"))
    finally:
        db.close()


def store_gross(tx_id, gross):
    """Write the row's gross_proceeds_usd as stored, its proceeds_usd left as
    it is. None: a row saved before the gross was kept, its proceeds_usd
    already net of the USD fee."""
    db = sessionmaker(bind=ENGINE)()
    try:
        db.query(Transaction).filter(Transaction.id == tx_id).update({Transaction.gross_proceeds_usd: gross})
        db.commit()
    finally:
        db.close()


def recalculate():
    r = CLIENT.post("/api/transactions/recalculate")
    assert r.status_code == 200, r.text


class TestAZeroGross:
    """A $0 gross is the sale's, whatever net is stored or sent beside it
    (each failed before the fix: the net became the sale)."""

    def test_stored_it_is_a_zero_sale_at_every_recalculation(self):
        sold = sale()
        store_gross(sold["id"], Decimal("0"))  # proceeds_usd still the $5,000 net
        recalculate()
        assert figures(CLIENT.get(f"/api/transactions/{sold['id']}").json()) == a_zero_sale()
        assert disposal_proceeds(sold["id"]) == 0
        assert exchange_usd() == 0

    def test_an_edit_sending_a_net_beside_it(self):
        sold = sale()
        after = put(sold["id"], {"gross_proceeds_usd": "0", "proceeds_usd": "5000"})
        assert figures(after) == a_zero_sale()

    def test_a_create_sending_a_net_beside_it(self):
        """The gross is the one checked: with a $10 fee the same sale is refused."""
        assert figures(sale("0", proceeds_usd="5000")) == a_zero_sale()
        r = CLIENT.post("/api/transactions", json={
            "type": "Sell", "timestamp": "2023-07-01T12:00:00Z", "from_account_id": EXCHANGE_BTC,
            "to_account_id": EXCHANGE_USD, "amount": "0.05", "gross_proceeds_usd": "0", "proceeds_usd": "5000",
            "fee_amount": "10", "fee_currency": "USD"})
        assert r.status_code == 422
        assert r.json()["detail"] == "The sell's fee is more than its proceeds."


class TestEditedToZero:
    """#471's steps (these pass since #449 and #458 too: the edit sends the
    stored net on as blank)."""

    def test_gross_alone(self):
        sold = sale()
        assert figures(sold)["realized_gain_usd"] == Decimal("4000")
        after = put(sold["id"], {"gross_proceeds_usd": "0"})
        assert figures(after) == a_zero_sale()
        assert disposal_proceeds(sold["id"]) == 0
        assert exchange_usd() == 0  # the $5,000 credited to Exchange USD is gone

    def test_the_forms_body(self):
        sold = sale()
        after = put(sold["id"], form_body(sold, 0, 0))
        assert figures(after) == a_zero_sale()

    def test_with_its_usd_fee_cleared(self):
        """Gross $5,000 with a $10 fee, edited to $0 and no fee: the old net
        ($4,990) became the gross."""
        sold = sale("5000", "10")
        assert figures(sold)["proceeds_usd"] == Decimal("4990")
        after = put(sold["id"], form_body(sold, 0, 0))
        assert figures(after) == a_zero_sale()
        assert exchange_usd() == 0

    def test_a_fee_above_it_is_still_refused(self):
        sold = sale("5000", "10")
        r = CLIENT.put(f"/api/transactions/{sold['id']}", json={"gross_proceeds_usd": "0"})
        assert r.status_code == 422
        assert r.json()["detail"] == "The sell's fee is more than its proceeds."
        assert figures(CLIENT.get(f"/api/transactions/{sold['id']}").json())["proceeds_usd"] == Decimal("4990")

    def test_the_edit_and_a_create_agree(self):
        edited = figures(put(sale()["id"], {"gross_proceeds_usd": "0"}))
        CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")
        assert figures(sale("0")) == edited

    def test_recalculate_ledger_keeps_it(self):
        sold = sale()
        put(sold["id"], {"gross_proceeds_usd": "0"})
        recalculate()
        assert figures(CLIENT.get(f"/api/transactions/{sold['id']}").json()) == a_zero_sale()
        assert disposal_proceeds(sold["id"]) == 0

    def test_back_up_from_zero(self):
        sold = sale()
        put(sold["id"], {"gross_proceeds_usd": "0"})
        after = put(sold["id"], {"gross_proceeds_usd": "5000"})
        assert figures(after)["proceeds_usd"] == Decimal("5000")
        assert figures(after)["realized_gain_usd"] == Decimal("4000")


class TestSavedBeforeTheGrossWasKept:
    """A NULL gross is still worked out from the stored net, the fee added back once."""

    def test_recalculation_recovers_the_gross(self):
        sold = sale("5000", "10")
        store_gross(sold["id"], None)
        recalculate()
        after = CLIENT.get(f"/api/transactions/{sold['id']}").json()
        assert figures(after) == {"gross_proceeds_usd": Decimal("5000"), "proceeds_usd": Decimal("4990"),
                                  "cost_basis_usd": Decimal("1000"), "realized_gain_usd": Decimal("3990")}
        assert exchange_usd() == Decimal("4990")

    def test_an_edit_of_something_else_keeps_its_figures(self):
        sold = sale("5000", "10")
        store_gross(sold["id"], None)
        after = put(sold["id"], {"timestamp": "2023-06-02T12:00:00Z"})
        assert figures(after)["proceeds_usd"] == Decimal("4990")
        assert figures(after)["gross_proceeds_usd"] == Decimal("5000")

    def test_one_with_nothing_recorded_stays_a_zero_sale(self):
        sold = sale("0")
        store_gross(sold["id"], None)
        recalculate()
        after = CLIENT.get(f"/api/transactions/{sold['id']}").json()
        assert figures(after)["proceeds_usd"] == 0
        assert after["gross_proceeds_usd"] is None
