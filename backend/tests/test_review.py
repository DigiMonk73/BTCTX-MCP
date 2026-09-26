"""
The Ledger review (backend/services/review.py): read-only lists of saved
rows worth a second look (F1, F2, F15). GET /api/review, the CLI and the MCP
tool all show the same lists; nothing is changed.
"""

import pytest
from sqlalchemy import text

BANK, WALLET, EXCH_BTC, EXTERNAL = 1, 2, 4, 99


@pytest.fixture
def ledger(auth_client, test_engine):
    auth_client.delete("/api/transactions/delete_all")
    # Rows as older versions saved them: inserted directly, since today's
    # validation refuses some of them.
    rows = [
        # id, type, from, to, source, purpose, basis, gross, gain
        (901, "Deposit", EXTERNAL, WALLET, "MyBTC", None, "0", None, None),
        (902, "Deposit", EXTERNAL, EXCH_BTC, "Gift", None, None, None, None),
        (903, "Deposit", EXTERNAL, WALLET, "Income", None, None, None, None),   # income: priced, not listed
        (904, "Deposit", EXTERNAL, WALLET, "MyBTC", None, "500", None, None),   # has a basis
        (905, "Deposit", EXTERNAL, BANK, "N/A", None, None, None, None),        # USD deposit
        (906, "Withdrawal", WALLET, EXTERNAL, None, "Spent", None, "0", "-100"),
        (907, "Withdrawal", WALLET, EXTERNAL, None, "Spent", None, "900", "400"),
        (908, "Withdrawal", WALLET, EXTERNAL, None, "Lost", None, None, "-300"),
        (909, "Withdrawal", WALLET, EXTERNAL, None, "Lost", None, None, "0"),    # already recalculated
    ]
    with test_engine.begin() as con:
        for tx_id, typ, frm, to, source, purpose, basis, gross, gain in rows:
            con.execute(text(
                "INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount,"
                " fee_amount, fee_currency, source, purpose, cost_basis_usd, gross_proceeds_usd,"
                " realized_gain_usd, is_locked)"
                " VALUES (:id, :type, '2024-01-01 03:00:00', :frm, :to, '0.1', '0', 'BTC', :source, :purpose,"
                " :basis, :gross, :gain, 0)"),
                dict(id=tx_id, type=typ, frm=frm, to=to, source=source, purpose=purpose, basis=basis,
                     gross=gross, gain=gain))
    with test_engine.connect() as con:
        before = con.execute(text("SELECT * FROM transactions ORDER BY id")).all()
    yield before
    auth_client.delete("/api/transactions/delete_all")


def ids(review, key):
    return [i["id"] for i in next(c for c in review["checks"] if c["key"] == key)["items"]]


def test_review_lists_each_kind_and_changes_nothing(auth_client, test_engine, ledger):
    r = auth_client.get("/api/review")
    assert r.status_code == 200, r.text
    review = r.json()
    assert review["read_only"] is True
    assert ids(review, "zero_proceeds_spend") == [906]
    assert ids(review, "lost_with_loss") == [908]
    assert ids(review, "deposit_without_basis") == [901, 902]
    assert review["total"] == 4
    item = next(c for c in review["checks"] if c["key"] == "lost_with_loss")["items"][0]
    assert item["realized_gain_usd"] == "-300.00" and "$0.00" in item["change"]
    with test_engine.connect() as con:
        assert con.execute(text("SELECT * FROM transactions ORDER BY id")).all() == ledger


def test_review_dates_are_in_the_tax_timezone(auth_client, test_engine, ledger):
    """03:00 UTC on Jan 1 is still Dec 31 in New York. (Set directly: the
    settings route recalculates, which these legacy rows can't pass.)"""
    from sqlalchemy.orm import sessionmaker

    from backend.services.tax_time import get_tax_timezone_name, set_tax_timezone

    Session = sessionmaker(bind=test_engine)
    with Session() as db:
        before = get_tax_timezone_name(db)[0]
        set_tax_timezone(db, "America/New_York")
        db.commit()
    try:
        review = auth_client.get("/api/review").json()
    finally:
        with Session() as db:
            set_tax_timezone(db, before)
            db.commit()
    assert review["timezone"] == "America/New_York"
    assert review["checks"][0]["items"][0]["date"] == "2023-12-31 22:00"


def test_review_needs_login():
    from fastapi.testclient import TestClient

    from backend.main import app

    assert TestClient(app).get("/api/review").status_code == 401


@pytest.fixture
def priced(auth_client, test_engine):
    """A transfer whose fee value came from the live price (12.00 where the
    day's price gives 10.00), one with a typed value, and an income deposit
    valued at another day's price (F42)."""
    auth_client.delete("/api/transactions/delete_all")
    post = lambda **b: auth_client.post("/api/transactions", json=b)  # noqa: E731
    assert post(type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
                amount="100000", fee_amount="0", fee_currency="USD", source="N/A").status_code == 200
    assert post(type="Buy", timestamp="2024-01-03T12:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
                amount="1", cost_basis_usd="40000", fee_amount="0", fee_currency="USD").status_code == 200
    live = post(type="Transfer", timestamp="2024-05-01T12:00:00Z", from_account_id=EXCH_BTC, to_account_id=WALLET,
                amount="0.1", fee_amount="0.0002", fee_currency="BTC").json()
    typed = post(type="Transfer", timestamp="2024-05-02T12:00:00Z", from_account_id=EXCH_BTC, to_account_id=WALLET,
                 amount="0.1", fee_amount="0.0002", fee_currency="BTC", fee_usd="12.00").json()
    income = post(type="Deposit", timestamp="2024-05-03T12:00:00Z", from_account_id=EXTERNAL, to_account_id=WALLET,
                  amount="0.01", fee_amount="0", fee_currency="BTC", source="Income", cost_basis_usd="620").json()
    with test_engine.begin() as con:  # as an older version saved it
        con.execute(text("UPDATE transactions SET fee_usd = '12.00' WHERE id = :id"), {"id": live["id"]})
    assert auth_client.post("/api/transactions/recalculate").status_code == 200
    yield live["id"], typed["id"], income["id"]
    auth_client.delete("/api/transactions/delete_all")


def fee_proceeds(test_engine, tx_id):
    with test_engine.connect() as con:
        return con.execute(text("SELECT SUM(proceeds_usd_for_that_portion) FROM lot_disposals"
                                " WHERE transaction_id = :id"), {"id": tx_id}).scalar()


def test_review_flags_live_priced_fees_and_off_income_values(auth_client, priced):
    live, typed, income = priced
    review = auth_client.get("/api/review").json()
    assert ids(review, "fee_value_off") == [live]  # a typed value is the owner's
    item = next(c for c in review["checks"] if c["key"] == "fee_value_off")["items"][0]
    assert "$12.00 -> $10.00" in item["change"]
    assert ids(review, "income_value_off") == [income]
    assert review["no_price_for"] == []


def test_fixing_fee_values_is_login_only_and_changes_only_flagged_rows(auth_client, test_engine, priced,
                                                                      monkeypatch):
    live, typed, income = priced
    from fastapi.testclient import TestClient

    from backend.main import app

    monkeypatch.setattr("backend.main.API_KEY", "k" * 40)
    anonymous = TestClient(app)
    r = anonymous.post("/api/review/fee-prices", json={"ids": [live]}, headers={"X-API-Key": "k" * 40})
    assert r.status_code == 401
    assert str(fee_proceeds(test_engine, live)) == "12"

    r = auth_client.post("/api/review/fee-prices", json={"ids": [live, typed, income]})
    assert r.status_code == 200, r.text
    assert r.json() == {"changed": [{"id": live, "old": "12.00", "new": "10.00"}], "recalculated": True}
    txs = {t["id"]: t for t in auth_client.get("/api/transactions").json()}
    assert txs[live]["fee_usd"] == "10.00" and txs[typed]["fee_usd"] == "12.00"
    assert txs[income]["cost_basis_usd"] == "620.00"
    assert str(fee_proceeds(test_engine, live)) == "10"
    assert ids(auth_client.get("/api/review").json(), "fee_value_off") == []
