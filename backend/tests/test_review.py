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
        (903, "Deposit", EXTERNAL, WALLET, "Income", None, None, None, None),   # income left blank (#77)
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
                " realized_gain_usd)"
                " VALUES (:id, :type, '2024-01-01 03:00:00', :frm, :to, '0.1', '0', 'BTC', :source, :purpose,"
                " :basis, :gross, :gain)"),
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
    assert ids(review, "income_without_value") == [903]
    assert review["total"] == 5
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
    spend = next(c for c in review["checks"] if c["key"] == "zero_proceeds_spend")
    assert spend["items"][0]["date"] == "2023-12-31 22:00"


def test_review_lists_income_deposits_with_a_zero_or_blank_value(auth_client, test_engine):
    """#77: an income deposit at $0 or blank reports no income, which the
    income rules forbid; it slipped past both basis checks."""
    auth_client.delete("/api/transactions/delete_all")
    rows = [(960, "0"), (961, None), (962, "500")]  # $0, blank, valued
    with test_engine.begin() as con:
        for tx_id, basis in rows:
            con.execute(text(
                "INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount, fee_amount,"
                " fee_currency, source, cost_basis_usd) VALUES (:id, 'Deposit', '2024-05-01T12:00:00Z', :e, :w, '0.01',"
                " '0', 'BTC', 'Interest', :basis)"), {"id": tx_id, "e": EXTERNAL, "w": WALLET, "basis": basis})
    try:
        review = auth_client.get("/api/review").json()
        check = next(c for c in review["checks"] if c["key"] == "income_without_value")
        assert [i["id"] for i in check["items"]] == [960, 961]
        zero, blank = check["items"]
        assert zero["issue"].startswith("Basis $0.00") and blank["issue"].startswith("Basis blank")
        assert "it is $500.00" in zero["issue"] and "$500.00 if you clear it" in zero["change"]  # 0.01 at $50,000
    finally:
        auth_client.delete("/api/transactions/delete_all")


def test_review_lists_zero_income_even_without_a_price(auth_client, test_engine, monkeypatch):
    """With no price for the day (prices off, a fresh install), the $0 income
    deposit is still listed, without its value, and counted in no_price_for."""
    from backend.tests.conftest import stub_daily_prices

    auth_client.delete("/api/transactions/delete_all")
    stub_daily_prices(monkeypatch, lambda day: None)
    with test_engine.begin() as con:
        con.execute(text(
            "INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount, fee_amount,"
            " fee_currency, source, cost_basis_usd) VALUES (970, 'Deposit', '2024-05-01T12:00:00Z', :e, :w, '0.01',"
            " '0', 'BTC', 'Reward', '0')"), {"e": EXTERNAL, "w": WALLET})
    try:
        review = auth_client.get("/api/review").json()
        [item] = next(c for c in review["checks"] if c["key"] == "income_without_value")["items"]
        assert item["id"] == 970 and "(no price stored for that day)" in item["issue"]
        assert review["no_price_for"] == [970]
    finally:
        auth_client.delete("/api/transactions/delete_all")


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
                                                                      ai_key_headers):
    live, typed, income = priced
    from fastapi.testclient import TestClient

    from backend.main import app

    anonymous = TestClient(app)
    assert anonymous.get("/api/review", headers=ai_key_headers).status_code == 200
    r = anonymous.post("/api/review/fee-prices", json={"ids": [live]}, headers=ai_key_headers)
    assert r.status_code == 403
    assert str(fee_proceeds(test_engine, live)) == "12"

    r = auth_client.post("/api/review/fee-prices", json={"ids": [live, typed, income]})
    assert r.status_code == 200, r.text
    assert r.json() == {"changed": [{"id": live, "old": "12.00", "new": "10.00"}], "recalculated": True}
    txs = {t["id"]: t for t in auth_client.get("/api/transactions").json()}
    assert txs[live]["fee_usd"] == "10.00" and txs[typed]["fee_usd"] == "12.00"
    assert txs[income]["cost_basis_usd"] == "620.00"
    assert str(fee_proceeds(test_engine, live)) == "10"
    assert ids(auth_client.get("/api/review").json(), "fee_value_off") == []


def test_review_shows_what_recalculation_would_change_and_changes_nothing(auth_client, test_engine):
    """After upgrading, rows computed by the old rules are listed old -> new
    (here a spend whose fee was cut from its proceeds, and a Lost withdrawal
    with a loss), and nothing is written."""
    auth_client.delete("/api/transactions/delete_all")
    post = lambda **b: auth_client.post("/api/transactions", json=b).json()  # noqa: E731
    try:
        post(type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
             amount="100000", fee_amount="0", fee_currency="USD", source="N/A")
        post(type="Buy", timestamp="2024-01-03T12:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
             amount="1", cost_basis_usd="20000", fee_amount="0", fee_currency="USD")
        spend = post(type="Withdrawal", timestamp="2024-06-01T12:00:00Z", from_account_id=EXCH_BTC,
                     to_account_id=EXTERNAL, amount="0.01", proceeds_usd="1000", fee_amount="0.0001",
                     fee_currency="BTC", purpose="Spent")
        lost = post(type="Withdrawal", timestamp="2024-07-01T12:00:00Z", from_account_id=EXCH_BTC,
                    to_account_id=EXTERNAL, amount="0.05", fee_amount="0", fee_currency="BTC", purpose="Lost")
        with test_engine.begin() as con:  # the figures v0.9.1 stored
            con.execute(text("UPDATE transactions SET proceeds_usd = '990.10', realized_gain_usd = '788.10'"
                             " WHERE id = :id"), {"id": spend["id"]})
            con.execute(text("UPDATE transactions SET realized_gain_usd = '-1000.00' WHERE id = :id"),
                        {"id": lost["id"]})
        with test_engine.connect() as con:
            before = con.execute(text("SELECT * FROM transactions ORDER BY id")).all()
            disposals = con.execute(text("SELECT * FROM lot_disposals ORDER BY id")).all()

        review = auth_client.get("/api/review").json()
        assert review["recalc_error"] is None
        check = next(c for c in review["checks"] if c["key"] == "recalc_changes")
        by_id = {i["id"]: i for i in check["items"]}
        assert set(by_id) == {spend["id"], lost["id"]}
        # The spend: 1,000.00 for 0.01 BTC, basis 200, gain 800. Its fee: 0.0001 x
        # $50,000 = 5.00, basis 2.00, gain 3.00. Taxable gain 803.00. (The
        # disposals weren't touched above, so they already show the new rule.)
        assert by_id[spend["id"]]["changes"] == {"proceeds_usd": ["990.10", "1000.00"],
                                                 "realized_gain_usd": ["788.10", "800.00"]}
        assert by_id[lost["id"]]["changes"] == {"realized_gain_usd": ["-1000.00", "0.00"]}

        with test_engine.connect() as con:
            assert con.execute(text("SELECT * FROM transactions ORDER BY id")).all() == before
            assert con.execute(text("SELECT * FROM lot_disposals ORDER BY id")).all() == disposals
    finally:
        auth_client.delete("/api/transactions/delete_all")
