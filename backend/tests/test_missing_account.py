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
NAMED = ("Transaction 970 (a Transfer) names account 999, which doesn't exist: a BitcoinTX before 0.9.2 saved it. "
         "Edit it into one of your accounts, or delete it. Ledger Review lists every such transaction.")


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
        (970, "Names account 999, which doesn't exist."), (971, "Names account 999, which doesn't exist.")]
    assert review["recalc_error"] == NAMED


def test_the_row_can_be_fixed_or_deleted(auth_client, test_engine, ledger):
    fixed = auth_client.put("/api/transactions/970", json={"to_account_id": 4})
    assert fixed.status_code == 200, fixed.text
    assert auth_client.post("/api/transactions/recalculate").status_code == 200
    assert auth_client.delete("/api/transactions/971").status_code in (200, 204)
    check = next(c for c in auth_client.get("/api/review").json()["checks"] if c["key"] == "account_missing")
    assert check["items"] == []
