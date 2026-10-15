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
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
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
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


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
    assert ids(review, "original_date_missing") == [901, 902, 904]  # My BTC and Gift, no original date
    assert ids(review, "income_without_value") == [903]
    assert ids(review, "gift_without_value") == [908, 909]  # lost coins saved without a value (#255)
    assert review["total"] == 7 and review["reminders"] == 3  # the original dates are a reminder (#128)
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


def test_review_amounts_have_eight_decimals(auth_client, test_engine):
    """A 5-satoshi amount reads 0.00000005, not 5E-8 (#74)."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    with test_engine.begin() as con:
        con.execute(text(
            "INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount, fee_amount,"
            " fee_currency, purpose, gross_proceeds_usd, realized_gain_usd)"
            " VALUES (950, 'Withdrawal', '2024-01-01 03:00:00', :w, :e, '0.00000005', '0', 'BTC', 'Spent', '0',"
            " '0')"), {"w": WALLET, "e": EXTERNAL})
    try:
        review = auth_client.get("/api/review").json()
        item = next(c for c in review["checks"] if c["key"] == "zero_proceeds_spend")["items"][0]
        assert item["amount"] == "0.00000005"
    finally:
        auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def test_review_fee_text_has_eight_decimals(auth_client, test_engine):
    """A transfer of 60 satoshis whose fee was valued off the day's price:
    its amount reads 0.00000060, never exponent form (#74)."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    post = lambda **b: auth_client.post("/api/transactions", json=b)  # noqa: E731
    try:
        assert post(type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=EXCH_BTC,
                    amount="0.01", fee_amount="0", fee_currency="BTC", source="MyBTC",
                    cost_basis_usd="400").status_code == 200
        fee = post(type="Transfer", timestamp="2024-05-01T12:00:00Z", from_account_id=EXCH_BTC, to_account_id=WALLET,
                   amount="0.0000006", fee_amount="0.0000005", fee_currency="BTC").json()
        with test_engine.begin() as con:  # valued at another price, as an older version could
            con.execute(text("UPDATE transactions SET fee_usd = '2.00' WHERE id = :id"), {"id": fee["id"]})
        review = auth_client.get("/api/review").json()
        item = next(c for c in review["checks"] if c["key"] == "day_priced_values")["items"][0]
        assert item["amount"] == "0.00000060" and item["change"].startswith("Fee value $2.00 -> "), item
    finally:
        auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def test_review_lists_income_deposits_with_a_zero_or_blank_value(auth_client, test_engine):
    """#77: an income deposit at $0 or blank reports no income, which the
    income rules forbid; it slipped past both basis checks."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
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
        auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def test_review_lists_zero_income_even_without_a_price(auth_client, test_engine, monkeypatch):
    """With no price for the day (prices off, a fresh install), the $0 income
    deposit is still listed, without its value, and counted in no_price_for."""
    from backend.tests.conftest import stub_daily_prices

    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
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
        auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def test_review_needs_login():
    from fastapi.testclient import TestClient

    from backend.main import app

    assert TestClient(app).get("/api/review").status_code == 401


@pytest.fixture
def priced(auth_client, test_engine):
    """A transfer whose fee value came from the live price (12.00 where the
    day's price gives 10.00), one with a typed value, and an income deposit
    valued at another day's price (F42)."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
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
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def fee_proceeds(test_engine, tx_id):
    with test_engine.connect() as con:
        return con.execute(text("SELECT SUM(proceeds_usd_for_that_portion) FROM lot_disposals"
                                " WHERE transaction_id = :id"), {"id": tx_id}).scalar()


def test_review_flags_live_priced_fees_and_off_income_values(auth_client, priced):
    live, typed, income = priced
    review = auth_client.get("/api/review").json()
    assert ids(review, "day_priced_values") == [live]  # a typed value is the owner's
    item = next(c for c in review["checks"] if c["key"] == "day_priced_values")["items"][0]
    # no hourly prices in tests: compared with the day's, as the old fee check did (F14)
    assert item["change"] == "Fee value $12.00 -> $10.00." and item["moment"] == "day"
    assert ids(review, "income_value_off") == [income]
    assert review["no_price_for"] == []


def test_applying_is_login_only_and_changes_only_values_priced_at_the_day(auth_client, test_engine, priced,
                                                                         ai_key_headers):
    live, typed, income = priced
    from fastapi.testclient import TestClient

    from backend.main import app

    anonymous = TestClient(app)
    assert anonymous.get("/api/review", headers=ai_key_headers).status_code == 200
    r = anonymous.post("/api/review/hourly-prices", json={"ids": [live]}, headers=ai_key_headers)
    assert r.status_code == 403
    assert str(fee_proceeds(test_engine, live)) == "12"

    r = auth_client.post("/api/review/hourly-prices", json={"ids": [live, typed, income]})
    assert r.status_code == 200, r.text
    assert r.json()["changed"] == [{"id": live, "moment": "day", "values": {"fee_usd": ["12.00", "10.00"]}}]
    assert r.json()["recalculated"] is True
    txs = {t["id"]: t for t in auth_client.get("/api/transactions").json()}
    assert txs[live]["fee_usd"] == "10.00" and txs[typed]["fee_usd"] == "12.00"
    assert txs[income]["cost_basis_usd"] == "620.00"
    assert str(fee_proceeds(test_engine, live)) == "10"
    assert ids(auth_client.get("/api/review").json(), "day_priced_values") == []


def test_review_shows_what_recalculation_would_change_and_changes_nothing(auth_client, test_engine):
    """After upgrading, rows computed by the old rules are listed old -> new
    (here a spend whose fee wasn't taken off its proceeds, #157, and a Lost
    withdrawal with a loss), and nothing is written."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
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
        with test_engine.begin() as con:  # the figures 0.9.2 to 1.2.7 stored, and v0.9.1's Lost
            con.execute(text("UPDATE transactions SET proceeds_usd = '1000.00', realized_gain_usd = '800.00'"
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
        # The spend: 1,000.00 received less its fee, 995.00 for 0.01 BTC, basis
        # 200, gain 795. Its fee: 0.0001 x $50,000 = 5.00, basis 2.00, gain
        # 3.00. Taxable gain 798.00. (The disposals weren't touched above, so
        # they already show the new rule.)
        assert by_id[spend["id"]]["changes"] == {"proceeds_usd": ["1000.00", "995.00"],
                                                 "realized_gain_usd": ["800.00", "795.00"]}
        assert by_id[lost["id"]]["changes"] == {"realized_gain_usd": ["-1000.00", "0.00"]}

        with test_engine.connect() as con:
            assert con.execute(text("SELECT * FROM transactions ORDER BY id")).all() == before
            assert con.execute(text("SELECT * FROM lot_disposals ORDER BY id")).all() == disposals
    finally:
        auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def test_a_deposit_without_basis_asks_for_a_gifts_basis(auth_client):
    """#115: a Gift's basis is the giver's; Ledger Review's advice once said
    only "what the BTC cost", like the form's old hint."""
    review = auth_client.get("/api/review").json()
    check = next(c for c in review["checks"] if c["key"] == "deposit_without_basis")
    assert "(for a gift, the giver's cost basis)" in check["action"]


def _sale_from_two_lots(auth_client, test_engine, second_lot_day: str) -> int:
    """0.001 BTC bought for $50.00 on 2023-01-02 and 0.001 for $60.00 on
    `second_lot_day`, both sold on 2024-06-01 for $1.01. Each row's proceeds
    are $0.505: today's rule gives the first lot $0.51 and the second $0.50.
    Its rows are then stored the other way round, as an older version could
    leave them (#296); the sale's totals stay the same."""
    post = lambda **b: auth_client.post("/api/transactions", json=b).json()  # noqa: E731
    post(type="Deposit", timestamp="2023-01-01T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
         amount="1000", fee_amount="0", fee_currency="USD", source="N/A")
    for day, cost in (("2023-01-02", "50.00"), (second_lot_day, "60.00")):
        post(type="Buy", timestamp=f"{day}T12:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
             amount="0.001", cost_basis_usd=cost, fee_amount="0", fee_currency="USD")
    sale = post(type="Sell", timestamp="2024-06-01T12:00:00Z", from_account_id=EXCH_BTC, to_account_id=3,
                amount="0.002", gross_proceeds_usd="1.01", fee_amount="0", fee_currency="USD")
    with test_engine.begin() as con:
        first, second = con.execute(text("SELECT id FROM lot_disposals WHERE transaction_id = :t ORDER BY id"),
                                    {"t": sale["id"]}).scalars().all()
        for row, proceeds, gain in ((first, "0.50", "-49.50"), (second, "0.51", "-59.49")):
            con.execute(text("UPDATE lot_disposals SET proceeds_usd_for_that_portion = :p,"
                             " realized_gain_usd = :g WHERE id = :id"), {"p": proceeds, "g": gain, "id": row})
    return sale["id"]


def _recalc_items(auth_client) -> dict:
    review = auth_client.get("/api/review").json()
    check = next(c for c in review["checks"] if c["key"] == "recalc_changes")
    return {i["id"]: i for i in check["items"]}


def _recalc_changes(auth_client) -> dict:
    return {tx_id: item["changes"] for tx_id, item in _recalc_items(auth_client).items()}


def test_review_sees_a_cent_move_between_a_sales_short_and_long_term_rows(auth_client, test_engine):
    """#296: the sale's totals don't move, but its long-term row gains a
    cent and its short-term row loses one, so Schedule D's lines would."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    try:
        sale = _sale_from_two_lots(auth_client, test_engine, "2024-03-01")
        assert _recalc_changes(auth_client) == {sale: {"long_term_gain": ["-49.50", "-49.49"],
                                                       "short_term_gain": ["-59.49", "-59.50"]}}
    finally:
        auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def test_review_sees_a_cent_move_between_two_rows_of_one_term(auth_client, test_engine):
    """#296: both lots long-term, so no term's total moves either, but two
    Form 8949 rows would."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    try:
        sale = _sale_from_two_lots(auth_client, test_engine, "2023-03-01")
        items = _recalc_items(auth_client)
        assert list(items) == [sale]
        assert items[sale]["change"] == "Its rows, lot by lot, would be split differently; its totals stay the same."
        old, new = items[sale]["changes"]["lot_rows"]
        assert [(r["term"], r["proceeds"], r["gain"]) for r in old] == [("LONG", "0.50", "-49.50"),
                                                                        ("LONG", "0.51", "-59.49")]
        assert [(r["term"], r["proceeds"], r["gain"]) for r in new] == [("LONG", "0.51", "-49.49"),
                                                                        ("LONG", "0.50", "-59.50")]
    finally:
        auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def test_review_sees_a_cent_move_in_the_cost_a_transfer_carried(auth_client, test_engine):
    """#296: 0.003 BTC bought for $1.00 and moved in two transfers of 0.001.
    Today the second carries $0.34 (the running total, #100); 1.2.8 gave each
    $0.33. A ledger saved that way lists the second transfer, though no
    transaction's own figure or disposal moves."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    post = lambda **b: auth_client.post("/api/transactions", json=b).json()  # noqa: E731
    try:
        post(type="Deposit", timestamp="2024-01-01T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
             amount="10", fee_amount="0", fee_currency="USD", source="N/A")
        post(type="Buy", timestamp="2024-01-02T12:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
             amount="0.003", cost_basis_usd="1.00", fee_amount="0", fee_currency="USD")
        moves = [post(type="Transfer", timestamp=f"2024-02-0{day}T12:00:00Z", from_account_id=EXCH_BTC,
                      to_account_id=WALLET, amount="0.001", fee_amount="0", fee_currency="BTC") for day in (1, 2)]
        with test_engine.begin() as con:
            con.execute(text("UPDATE bitcoin_lots SET cost_basis_usd = '0.33' WHERE created_txn_id = :t"),
                        {"t": moves[1]["id"]})
        assert _recalc_changes(auth_client) == {moves[1]["id"]: {"lot_cost": ["0.33", "0.34"]}}
    finally:
        auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def test_review_sees_a_row_change_term(auth_client, test_engine):
    """#296: a sale's one row stored as short-term that the rules make
    long-term: its gain moves between Schedule D's two lines."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    post = lambda **b: auth_client.post("/api/transactions", json=b).json()  # noqa: E731
    try:
        post(type="Deposit", timestamp="2023-01-01T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
             amount="100", fee_amount="0", fee_currency="USD", source="N/A")
        post(type="Buy", timestamp="2023-01-02T12:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
             amount="0.001", cost_basis_usd="50.00", fee_amount="0", fee_currency="USD")
        sale = post(type="Sell", timestamp="2024-06-01T12:00:00Z", from_account_id=EXCH_BTC, to_account_id=3,
                    amount="0.001", gross_proceeds_usd="70.00", fee_amount="0", fee_currency="USD")
        with test_engine.begin() as con:
            con.execute(text("UPDATE lot_disposals SET holding_period = 'SHORT' WHERE transaction_id = :t"),
                        {"t": sale["id"]})
        assert _recalc_changes(auth_client) == {sale["id"]: {"short_term_gain": ["20.00", "0.00"],
                                                             "long_term_gain": ["0.00", "20.00"]}}
    finally:
        auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def test_review_sees_the_lots_a_transfer_made_share_their_cost_differently(auth_client, test_engine):
    """#296: a transfer from two lots makes two lots in the Wallet. Stored
    with a cent moved between them, their total is the same, but each
    lot's cost (and so a later sale's basis) isn't."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    post = lambda **b: auth_client.post("/api/transactions", json=b).json()  # noqa: E731
    try:
        post(type="Deposit", timestamp="2024-01-01T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
             amount="10", fee_amount="0", fee_currency="USD", source="N/A")
        for day, cost in (("02", "0.50"), ("03", "0.70")):
            post(type="Buy", timestamp=f"2024-01-{day}T12:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
                 amount="0.001", cost_basis_usd=cost, fee_amount="0", fee_currency="USD")
        move = post(type="Transfer", timestamp="2024-02-01T12:00:00Z", from_account_id=EXCH_BTC,
                    to_account_id=WALLET, amount="0.002", fee_amount="0", fee_currency="BTC")
        with test_engine.begin() as con:
            for cost, was in (("0.51", "0.50"), ("0.69", "0.70")):
                con.execute(text("UPDATE bitcoin_lots SET cost_basis_usd = :c"
                                 " WHERE created_txn_id = :t AND cost_basis_usd = :w"),
                            {"c": cost, "t": move["id"], "w": was})
        items = _recalc_items(auth_client)
        assert list(items) == [move["id"]] and list(items[move["id"]]["changes"]) == ["lot_split"]
        old, new = items[move["id"]]["changes"]["lot_split"]
        assert [lot["cost"] for lot in old] == ["0.51", "0.69"] and [lot["cost"] for lot in new] == ["0.50", "0.70"]
        assert items[move["id"]]["change"] == ("The lots it made would share their cost differently;"
                                              " its totals stay the same.")
    finally:
        auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
