"""
A transaction naming an account that doesn't exist (#337). Before 0.9.2
unknown account ids were saved (F28). One between the owner's account and a
missing one fails the replay's balance check, so every save that
recalculates failed with "Ledger not balanced for BTC" (or "would lack
BTC"), naming neither the row nor the account. The refusal now names both,
whatever save ran the replay, and Ledger Review lists every such row. Such a
row is written directly: the API refuses it.
"""

import pytest
from sqlalchemy import text

WALLET, EXTERNAL, MISSING = 2, 99, 999
FIX = ("Edit it into one of your accounts, or delete it. Ledger Review lists every such transaction; if it lists "
       "more than one that stops saves, each stops an edit of the others, but not a delete: delete all but one, then "
       "edit or delete the last, and enter again any you still need.")
NAMED = ("Transaction 970 (a Transfer of 2024-02-01) names account 999, which doesn't exist (a BitcoinTX before "
         "0.9.2 saved it). " + FIX)


@pytest.fixture
def ledger(auth_client, test_engine):
    """A deposit into Wallet, then an old Transfer from Wallet to a missing
    account (it stops the replay) and an old Deposit from External into one
    (it doesn't)."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    deposit = auth_client.post("/api/transactions", json=dict(
        type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=WALLET,
        amount="1", source="MyBTC", cost_basis_usd="1000"))
    assert deposit.status_code == 200, deposit.text
    with test_engine.begin() as con:
        for tx_id, typ, frm, to in ((970, "Transfer", WALLET, MISSING), (971, "Deposit", EXTERNAL, MISSING)):
            con.execute(text(
                "INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount, fee_amount,"
                " fee_currency, source) VALUES (:id, :type, '2024-02-01T12:00:00Z', :frm, :to, '0.1', '0', 'BTC',"
                " 'MyBTC')"), dict(id=tx_id, type=typ, frm=frm, to=to))
    yield deposit.json()["id"]
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def test_every_save_that_recalculates_names_the_row(auth_client, ledger):
    earlier = dict(type="Deposit", timestamp="2024-01-01T12:00:00Z", from_account_id=EXTERNAL, to_account_id=WALLET,
                   amount="0.5", source="MyBTC", cost_basis_usd="100")
    for r in (auth_client.put(f"/api/transactions/{ledger}", json={"amount": "0.9"}),
              auth_client.post("/api/transactions", json=earlier),
              auth_client.delete(f"/api/transactions/{ledger}"),
              auth_client.post("/api/transactions/recalculate")):
        assert (r.status_code, r.json()) == (400, {"detail": NAMED}), r.request.method


def test_ledger_review_lists_each_row_and_says_why_it_cant_check(auth_client, ledger):
    review = auth_client.get("/api/review").json()
    check = next(c for c in review["checks"] if c["key"] == "account_missing")
    assert [(i["id"], i["issue"]) for i in check["items"]] == [
        (970, "Names account 999, which doesn't exist (a BitcoinTX before 0.9.2 saved it). "
              "It stops every save that recalculates."),
        (971, "Names account 999, which doesn't exist (a BitcoinTX before 0.9.2 saved it). "
              "It doesn't stop saves.")]  # its other side is External
    assert review["recalc_error"] == NAMED


def test_the_row_can_be_fixed_or_deleted(auth_client, test_engine, ledger):
    fixed = auth_client.put("/api/transactions/970", json={"to_account_id": 4})
    assert fixed.status_code == 200, fixed.text
    assert auth_client.post("/api/transactions/recalculate").status_code == 200
    assert auth_client.delete("/api/transactions/971").status_code in (200, 204)
    check = next(c for c in auth_client.get("/api/review").json()["checks"] if c["key"] == "account_missing")
    assert check["items"] == []


def _old_row(test_engine, tx_id, typ, frm, to, amount="0.1", gross=None):
    with test_engine.begin() as con:
        con.execute(text(
            "INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount, fee_amount,"
            " fee_currency, gross_proceeds_usd) VALUES (:id, :type, '2024-03-01T12:00:00Z', :frm, :to, :amount, '0',"
            " 'USD', :gross)"), dict(id=tx_id, type=typ, frm=frm, to=to, amount=amount, gross=gross))


@pytest.fixture
def empty(auth_client):
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def test_a_shortage_is_still_named_as_one(auth_client, test_engine, empty):
    """#367's review: only the balance check's failure is put down to the
    missing account. An old Sell to a missing account with no BTC to sell
    is refused as a shortage, as it always was."""
    _old_row(test_engine, 980, "Sell", 4, MISSING, gross="100")
    r = auth_client.post("/api/transactions/recalculate")
    assert r.status_code == 400 and r.json()["detail"].startswith("Not enough BTC to sell"), r.text


def test_a_transaction_naming_no_account_is_named_too(auth_client, test_engine, empty):
    """The realistic way in: deleting an account (until #367) left its
    transactions naming none, and each stopped every save."""
    assert auth_client.post("/api/transactions", json=dict(
        type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=WALLET,
        amount="1", source="MyBTC", cost_basis_usd="1000")).status_code == 200
    _old_row(test_engine, 981, "Transfer", WALLET, None)
    r = auth_client.post("/api/transactions/recalculate")
    assert (r.status_code, r.json()["detail"]) == (400, (
        "Transaction 981 (a Transfer of 2024-03-01) names no account on one side (the one it named was "
        "deleted). " + FIX))
    check = next(c for c in auth_client.get("/api/review").json()["checks"] if c["key"] == "account_missing")
    assert [(i["id"], i["issue"]) for i in check["items"]] == [
        (981, "Names no account on one side (the one it named was deleted). It stops every save that recalculates.")]


def test_both_missing_accounts_are_named_and_dollars_shown_as_dollars(auth_client, test_engine, empty):
    from backend.services.review import format_text

    _old_row(test_engine, 982, "Transfer", 998, MISSING)
    _old_row(test_engine, 983, "Transfer", 1, MISSING, amount="500")  # from Bank: dollars
    review = auth_client.get("/api/review").json()
    items = {i["id"]: i for c in review["checks"] if c["key"] == "account_missing" for i in c["items"]}
    assert items[982]["issue"] == ("Names accounts 998 and 999, which don't exist (a BitcoinTX before 0.9.2 saved it). "
                                   "It doesn't stop saves.")  # neither side is one of yours: it balances
    assert (items[983]["amount"], items[983]["unit"]) == ("500.00", "USD")
    assert (items[982]["amount"], items[982]["unit"]) == ("0.10000000", "BTC")
    text_out = format_text(review)
    assert "  Transfer  $500.00  " in text_out and "(None)" not in text_out


def test_an_account_transactions_name_cant_be_deleted(auth_client, test_engine, empty):
    """#367's review: deleting it answered 204 and left its transactions
    naming no account. Refused now, in plain words; one nothing names goes."""
    made = auth_client.post("/api/accounts/", json={"user_id": 1, "name": "Old wallet", "currency": "BTC"})
    assert made.status_code in (200, 201), made.text
    account_id = made.json()["id"]
    _old_row(test_engine, 984, "Transfer", WALLET, account_id)
    r = auth_client.delete(f"/api/accounts/{account_id}")
    assert (r.status_code, r.json()["detail"]) == (
        409, "Not deleted: 1 transaction names Old wallet. Move it to another account, or delete it, first.")
    with test_engine.connect() as con:
        assert con.execute(text("SELECT to_account_id FROM transactions WHERE id = 984")).scalar() == account_id
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    assert auth_client.delete(f"/api/accounts/{account_id}").status_code == 204


@pytest.fixture
def two_blocking(auth_client, test_engine, empty):
    """#368's reproduction: a deposit into Wallet, then two old Transfers
    from Wallet, one to a missing account and one naming none (its account
    deleted before #367): each stops the replay. The deposit's id."""
    deposit = auth_client.post("/api/transactions", json=dict(
        type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=WALLET,
        amount="1", source="MyBTC", cost_basis_usd="1000"))
    assert deposit.status_code == 200, deposit.text
    _old_row(test_engine, 985, "Transfer", WALLET, MISSING)
    _old_row(test_engine, 986, "Transfer", WALLET, None)
    return deposit.json()["id"]


def _detail(r) -> str:
    return r.json()["detail"]


def test_each_row_naming_a_missing_account_can_be_deleted_one_by_one(auth_client, test_engine, two_blocking):
    """#368: each delete was refused, naming the other row, so neither could
    go. A delete of one now goes past the other; the other still stops every
    other save, by name, until it goes too. Then the ledger is whole again."""
    assert auth_client.delete("/api/transactions/985").status_code == 204
    second = ("Transaction 986 (a Transfer of 2024-03-01) names no account on one side (the one it named was "
              "deleted). " + FIX)
    r = auth_client.post("/api/transactions/recalculate")
    assert (r.status_code, _detail(r)) == (400, second)
    assert auth_client.delete("/api/transactions/986").status_code == 204
    assert auth_client.post("/api/transactions/recalculate").status_code == 200
    review = auth_client.get("/api/review").json()
    assert review["recalc_error"] is None
    assert next(c for c in review["checks"] if c["key"] == "account_missing")["items"] == []
    with test_engine.connect() as con:  # the deposit's lot, whole: nothing of the two rows is left
        assert con.execute(text("SELECT COUNT(*) FROM transactions")).scalar() == 1
        assert con.execute(text("SELECT remaining_btc, cost_basis_usd FROM bitcoin_lots")).one() == (1, 1000)


def test_the_other_order_too(auth_client, two_blocking):
    assert auth_client.delete("/api/transactions/986").status_code == 204
    assert auth_client.delete("/api/transactions/985").status_code == 204
    assert auth_client.post("/api/transactions/recalculate").status_code == 200


def test_only_a_delete_of_such_a_row_goes_past_the_others(auth_client, two_blocking):
    """An edit of one is still refused (the other stops its replay), and so
    is an edit or a delete of an ordinary transaction, each naming the first
    row that stops it; nothing changes."""
    first = ("Transaction 985 (a Transfer of 2024-03-01) names account 999, which doesn't exist (a BitcoinTX before "
             "0.9.2 saved it). " + FIX)
    second = ("Transaction 986 (a Transfer of 2024-03-01) names no account on one side (the one it named was "
              "deleted). " + FIX)
    for r, named in ((auth_client.put("/api/transactions/985", json={"to_account_id": 4}), second),
                     (auth_client.put(f"/api/transactions/{two_blocking}", json={"amount": "0.9"}), first),
                     (auth_client.delete(f"/api/transactions/{two_blocking}"), first)):
        assert (r.status_code, _detail(r)) == (400, named), r.request.method
    assert {t["id"] for t in auth_client.get("/api/transactions").json()} == {two_blocking, 985, 986}


def test_a_shortage_still_stops_such_a_delete(auth_client, test_engine, empty):
    """Going past the other row's balance check isn't going past a shortage.
    The other row, a withdrawal naming a deleted account, is replayed: its
    BTC leaves Wallet, and a later spend runs short. That delete is refused
    as any delete a later transaction needs is, and nothing changes; the
    withdrawal itself can go first."""
    assert auth_client.post("/api/transactions", json=dict(
        type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=WALLET,
        amount="1", source="MyBTC", cost_basis_usd="1000")).status_code == 200
    _old_row(test_engine, 987, "Transfer", WALLET, MISSING)
    _old_row(test_engine, 988, "Withdrawal", WALLET, None, amount="0.5")
    with test_engine.begin() as con:  # a later spend of 0.6: there with the withdrawal gone, not with it
        con.execute(text(
            "INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount, fee_amount,"
            " fee_currency, purpose, gross_proceeds_usd) VALUES (989, 'Withdrawal', '2024-04-01T12:00:00Z', 2, 99,"
            " '0.6', '0', 'USD', 'Spent', '100')"))
    r = auth_client.delete("/api/transactions/987")
    assert r.status_code == 400 and _detail(r).startswith("Not deleted: later transactions depend on this one."), r.text
    assert {t["id"] for t in auth_client.get("/api/transactions").json()} >= {987, 988, 989}
    assert auth_client.delete("/api/transactions/988").status_code == 204
    assert auth_client.delete("/api/transactions/987").status_code == 204
    assert auth_client.post("/api/transactions/recalculate").status_code == 200


def test_the_wording_for_each_missing_side():
    from backend.services.transaction import what_is_missing

    assert what_is_missing([None, None]) == "names no account on either side (the ones it named were deleted)"
    assert what_is_missing([999, None]) == ("names account 999, which doesn't exist (a BitcoinTX before 0.9.2 "
                                            "saved it), and names no account on one side (the one it named was deleted)")
