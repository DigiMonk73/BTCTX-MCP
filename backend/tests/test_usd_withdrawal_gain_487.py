"""
#487: a bitcoin withdrawal edited into a dollar withdrawal (its account
moved from Wallet or Exchange BTC to Bank or Exchange USD) kept the cost
basis, gain and holding period it had as a bitcoin disposal, even after
Recalculate Ledger. The edit returned its lots, so no tax figure counted
it, but the Transactions list, the Transaction History report (its CSV
called it a "CapitalGainsTransaction") and the AI's list_transactions
showed a gain. A dollar withdrawal disposes of no bitcoin: it has none.
"""

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from backend.services.reports.form_8949 import build_form_8949_and_schedule_d

BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 2, 3, 4, 99
YEAR = 2025


@pytest.fixture
def ledger(auth_client):
    """#487's ledger: $5,000 in Bank, 0.1 BTC in Wallet at $2,300."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    for body in (
        dict(type="Deposit", timestamp="2025-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
             amount="5000", fee_amount="0", fee_currency="USD", source="N/A"),
        dict(type="Deposit", timestamp="2025-01-03T12:00:00Z", from_account_id=EXTERNAL, to_account_id=WALLET,
             amount="0.1", fee_amount="0", fee_currency="BTC", source="MyBTC", cost_basis_usd="2300"),
    ):
        r = auth_client.post("/api/transactions", json=body)
        assert r.status_code == 200, r.text
    yield
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def spend(client, **kw) -> dict:
    """A Spent of 0.01 BTC from the wallet for $400: basis $230, gain $170."""
    body = dict(type="Withdrawal", timestamp="2025-06-01T12:00:00Z", from_account_id=WALLET,
                to_account_id=EXTERNAL, amount="0.01", fee_amount="0", fee_currency="BTC",
                purpose="Spent", proceeds_usd="400", **kw)
    r = client.post("/api/transactions", json=body)
    assert r.status_code == 200, r.text
    tx = r.json()
    assert (tx["cost_basis_usd"], tx["realized_gain_usd"], tx["holding_period"]) == ("230.00", "170.00", "SHORT")
    return tx


def edit(client, tx_id: int, **changes) -> dict:
    r = client.put(f"/api/transactions/{tx_id}", json=changes)
    assert r.status_code == 200, r.text
    return r.json()


def listed(client, tx_id: int) -> dict:
    r = client.get("/api/transactions")
    assert r.status_code == 200, r.text
    return next(t for t in r.json() if t["id"] == tx_id)


def figures(tx: dict) -> tuple:
    return tx["cost_basis_usd"], tx["realized_gain_usd"], tx["holding_period"]


def form_8949_rows(test_engine) -> list:
    with sessionmaker(bind=test_engine)() as db:
        forms = build_form_8949_and_schedule_d(YEAR, db)
    return forms["short_term"] + forms["long_term"]


@pytest.mark.parametrize("account", [BANK, EXCHANGE_USD])
def test_moved_to_a_dollar_account_it_has_no_gain(auth_client, ledger, account):
    """#487's steps: the edit, then Recalculate Ledger."""
    tx = spend(auth_client)
    edited = edit(auth_client, tx["id"], from_account_id=account, fee_currency="USD", amount="100")
    assert figures(edited) == (None, None, None)
    assert auth_client.post("/api/transactions/recalculate").status_code == 200
    assert figures(listed(auth_client, tx["id"])) == (None, None, None)


def test_recalculate_ledger_clears_a_row_saved_so_before_the_fix(auth_client, test_engine, ledger):
    """A dollar withdrawal holding a bitcoin disposal's figures (saved by an
    edit before the fix) loses them in the next recalculation; until then
    Ledger Review lists it among what Recalculate Ledger would change."""
    tx = spend(auth_client)
    with test_engine.begin() as con:
        con.execute(text("UPDATE transactions SET from_account_id = :bank, fee_currency = 'USD', amount = 100 "
                         "WHERE id = :id"), {"bank": BANK, "id": tx["id"]})
    assert figures(listed(auth_client, tx["id"])) == ("230.00", "170.00", "SHORT")  # as such a row is stored
    review = auth_client.get("/api/review").json()
    check = next(c for c in review["checks"] if c["key"] == "recalc_changes")
    item = next(i for i in check["items"] if i["id"] == tx["id"])
    assert item["changes"]["cost_basis_usd"] == ["230.00", None]
    assert item["changes"]["realized_gain_usd"] == ["170.00", None]
    assert auth_client.post("/api/transactions/recalculate").status_code == 200
    assert figures(listed(auth_client, tx["id"])) == (None, None, None)


def test_the_transaction_history_shows_no_gain_for_it(auth_client, ledger):
    tx = spend(auth_client)
    edit(auth_client, tx["id"], from_account_id=BANK, fee_currency="USD", amount="100")
    history = auth_client.get("/api/reports/simple_transaction_history", params={"year": YEAR, "format": "csv"})
    assert history.status_code == 200, history.text
    lines = history.text.splitlines()
    header = lines[0].split(",")
    row = next(dict(zip(header, line.split(","))) for line in lines[1:] if ",Bank," in line and "Sell/Withdrawal" in line)
    assert (row["cost_basis_usd"], row["realized_gain_usd"], row["holding_period"]) == ("", "", "")
    assert "CapitalGainsTransaction" not in history.text


def test_form_8949_and_moving_it_back(auth_client, test_engine, ledger):
    """Form 8949 never counted it (it reads the lots); moved back to the
    wallet, the withdrawal is a bitcoin disposal again, with its gain."""
    tx = spend(auth_client)
    assert len(form_8949_rows(test_engine)) == 1
    edit(auth_client, tx["id"], from_account_id=BANK, fee_currency="USD", amount="100")
    assert form_8949_rows(test_engine) == []
    back = edit(auth_client, tx["id"], from_account_id=WALLET, fee_currency="BTC", amount="0.01",
                purpose="Spent", proceeds_usd="400")
    assert figures(back) == ("230.00", "170.00", "SHORT")
    assert [Decimal(str(r["gain_loss"])) for r in form_8949_rows(test_engine)] == [Decimal("170.00")]
