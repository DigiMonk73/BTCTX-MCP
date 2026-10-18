"""
A gift, donation or lost coins has no proceeds (#457). The form saved a
hidden $0 on one (its `?? 0`), and an edit that later made it a Spent
without proceeds kept that $0: a $0 sale, its whole basis a loss, where the
same gift never saved in the form was priced at the hour. Now an edit keeps
no proceeds sent on a withdrawal that has none, and one made a Spent with
none sent is priced at the hour when it holds $0 or none, as a new Spent
left blank is; above $0 (a former spend's) is kept, typed. A $0 isn't
carried into a Sell either: it needs its proceeds sent. Nor is anything a
dollar withdrawal held (it holds no value, #449) carried into a bitcoin
spend.
"""

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from backend.models.transaction import Transaction
from backend.services import hourly_prices
from backend.tests.conftest import stub_prices_at

BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 2, 3, 4, 99
D = Decimal
WHEN = "2024-06-10T15:20:00Z"


def price_of(when) -> Decimal:
    """Each hour its own price, so a value priced at another hour shows."""
    return D(35000 + (hourly_prices.hour_of(when) // 3600) % 1000)


def value(amount: str, when: str = WHEN) -> str:
    moment = datetime.fromisoformat(when.replace("Z", "+00:00"))
    return str((price_of(moment) * D(amount)).quantize(D("0.01")))


@pytest.fixture(autouse=True)
def _ledger(auth_client, monkeypatch):
    stub_prices_at(monkeypatch, price_of)
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    for account in (WALLET, EXCHANGE_BTC):
        post(auth_client, type="Deposit", timestamp="2024-01-10T12:00:00Z", from_account_id=EXTERNAL,
             to_account_id=account, amount="1", fee_amount="0", fee_currency="BTC", source="MyBTC",
             cost_basis_usd="40000")
    yield
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def post(client, **body) -> dict:
    r = client.post("/api/transactions", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def put(client, tx: dict, **changes) -> dict:
    r = client.put(f"/api/transactions/{tx['id']}", json=changes)
    assert r.status_code == 200, r.text
    return r.json()


def gift(client, purpose="Gift", account=WALLET, **fields) -> dict:
    return post(client, type="Withdrawal", timestamp=WHEN, from_account_id=account, to_account_id=EXTERNAL,
                amount="0.1", fee_amount="0", fee_currency="BTC", purpose=purpose, **fields)


def form_save(client, tx: dict) -> dict:
    """The edit form's save of the withdrawal unchanged, as 1.2.8's form sent it:
    every field, the proceeds as `gross ?? proceeds ?? 0`."""
    proceeds = tx["gross_proceeds_usd"] or tx["proceeds_usd"] or 0
    keys = ("type", "timestamp", "from_account_id", "to_account_id", "amount", "fee_amount", "fee_currency",
            "purpose", "fmv_usd", "cost_basis_usd")
    return put(client, tx, **{k: tx[k] for k in keys}, proceeds_usd=proceeds, broker_reporting=None,
               acquired_at=None)


def assert_priced(tx: dict, amount="0.1") -> None:
    assert tx["purpose"] == "Spent"
    assert tx["gross_proceeds_usd"] == tx["proceeds_usd"] == value(amount)
    assert tx["proceeds_from_price"] is True and tx["price_moment"] == "hour"
    assert D(tx["realized_gain_usd"]) == D(value(amount)) - D("4000.00")


@pytest.mark.parametrize("purpose", ["Gift", "Donation", "Lost"])
def test_saved_in_the_form_then_made_spent_it_is_priced(auth_client, purpose):
    """#457's steps: the gift saved unchanged in the form, then made a Spent with only its purpose sent
    (the AI connector's update_transaction)."""
    tx = form_save(auth_client, gift(auth_client, purpose))
    assert tx["gross_proceeds_usd"] is None  # the form's 0 isn't kept on a gift
    assert_priced(put(auth_client, tx, purpose="Spent"))


def test_never_saved_in_the_form_it_is_priced_too(auth_client):
    assert_priced(put(auth_client, gift(auth_client), purpose="Spent"))


def test_a_0_an_older_form_saved_is_priced_when_made_spent(auth_client):
    """A gift saved with $0 proceeds (forms before the fix sent `?? 0`; a CSV export carries it)."""
    tx = gift(auth_client, proceeds_usd="0")
    assert tx["gross_proceeds_usd"] == "0.00"
    assert_priced(put(auth_client, tx, purpose="Spent"))


def test_proceeds_sent_on_a_gift_are_not_kept(auth_client):
    tx = put(auth_client, gift(auth_client), proceeds_usd="250")
    assert tx["gross_proceeds_usd"] is None and tx["proceeds_usd"] is None
    assert_priced(put(auth_client, tx, purpose="Spent"))


def test_proceeds_sent_with_the_purpose_change_are_typed_0_included(auth_client):
    typed = put(auth_client, gift(auth_client), purpose="Spent", proceeds_usd="3500")
    assert typed["gross_proceeds_usd"] == "3500.00" and typed["proceeds_from_price"] is False
    zero = put(auth_client, gift(auth_client), purpose="Spent", proceeds_usd="0")
    assert zero["gross_proceeds_usd"] == "0.00" and zero["proceeds_from_price"] is False
    assert D(zero["realized_gain_usd"]) == D("-4000.00")


def test_a_former_spends_proceeds_come_back_typed(auth_client):
    """Above $0, a spend's proceeds made a gift are kept, as now (a sale's value made a gift is, #255)."""
    spent = post(auth_client, type="Withdrawal", timestamp=WHEN, from_account_id=WALLET, to_account_id=EXTERNAL,
                 amount="0.1", fee_amount="0", fee_currency="BTC", purpose="Spent", proceeds_usd="3600")
    made_gift = form_save(auth_client, put(auth_client, spent, purpose="Gift"))
    back = put(auth_client, made_gift, purpose="Spent")
    assert back["gross_proceeds_usd"] == "3600.00" and back["proceeds_from_price"] is False


def test_a_gifts_0_isnt_carried_into_a_sell(auth_client):
    tx = gift(auth_client, account=EXCHANGE_BTC, proceeds_usd="0")
    r = auth_client.put(f"/api/transactions/{tx['id']}",
                        json={"type": "Sell", "from_account_id": EXCHANGE_BTC, "to_account_id": EXCHANGE_USD,
                              "fee_currency": "USD"})
    assert r.status_code == 422 and "needs its proceeds" in r.text


def dollar_withdrawal_holding(client, test_engine, held: str) -> dict:
    """A dollar withdrawal as one saved before 1.2.9 could be: holding proceeds (the form's $0, or a value
    left from the bitcoin fields, #449)."""
    post(client, type="Deposit", timestamp="2024-01-10T12:00:00Z", from_account_id=EXTERNAL,
         to_account_id=BANK, amount="500", fee_amount="0", fee_currency="USD", source="N/A")
    dollars = post(client, type="Withdrawal", timestamp=WHEN, from_account_id=BANK, to_account_id=EXTERNAL,
                   amount="0.1", fee_amount="0", fee_currency="USD", purpose="N/A")
    db = sessionmaker(bind=test_engine)()
    try:
        db.query(Transaction).filter(Transaction.id == dollars["id"]).update(
            {Transaction.gross_proceeds_usd: D(held), Transaction.proceeds_usd: D(held)})
        db.commit()
    finally:
        db.close()
    return dollars


@pytest.mark.parametrize("held", ["0.00", "250.00"])
def test_what_a_dollar_withdrawal_held_is_never_carried_into_a_bitcoin_spend(auth_client, test_engine, held):
    dollars = dollar_withdrawal_holding(auth_client, test_engine, held)
    assert_priced(put(auth_client, dollars, from_account_id=WALLET, fee_currency="BTC", purpose="Spent"))


def test_nor_through_a_gift_first(auth_client, test_engine):
    """Moved to the Wallet as a gift, it holds nothing; made a Spent later, it's priced (#519's review)."""
    dollars = dollar_withdrawal_holding(auth_client, test_engine, "250.00")
    made_gift = put(auth_client, dollars, from_account_id=WALLET, fee_currency="BTC", purpose="Gift")
    assert made_gift["gross_proceeds_usd"] is None
    assert_priced(put(auth_client, made_gift, purpose="Spent"))


def test_a_recalculation_never_prices_it_again(auth_client, monkeypatch):
    tx = put(auth_client, form_save(auth_client, gift(auth_client)), purpose="Spent")
    stub_prices_at(monkeypatch, lambda when: 99999)
    assert auth_client.post("/api/transactions/recalculate").status_code == 200
    again = auth_client.get(f"/api/transactions/{tx['id']}").json()
    assert again["gross_proceeds_usd"] == tx["gross_proceeds_usd"] == value("0.1")
