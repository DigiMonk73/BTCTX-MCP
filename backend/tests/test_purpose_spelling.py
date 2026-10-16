"""
A purpose or source saved with spaces around it (#342). Before 0.9.2 a
purpose, and before 1.1.0 a source, was saved as typed, so an old ledger can
hold " gift " or " Income ". The screens read those as Gift and Income
(frontend/src/utils/purposes.ts trims); the server compared them lowercase
but untrimmed, so " gift " was a sale on Form 8949 and " Income " no income.
Every comparison now trims too (constants.normalized): each such row counts
exactly as its listed spelling does.
"""

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from backend.services.reports.form_8949 import build_form_8949_and_schedule_d
from backend.services.reports.reporting_core import generate_report_data

WALLET, EXTERNAL = 2, 99
# (spelled with spaces, listed spelling): each pair is the same withdrawal or deposit
TWINS = [(912, 911), (914, 913), (916, 915), (922, 921)]
ROWS = [
    # id, type, day, from, to, amount, source, purpose, basis, gross
    (901, "Deposit", "2024-01-02", EXTERNAL, WALLET, "1", "MyBTC", None, "1000", None),
    (921, "Deposit", "2024-01-03", EXTERNAL, WALLET, "0.1", "Income", None, "500", None),
    (922, "Deposit", "2024-01-04", EXTERNAL, WALLET, "0.1", " Income ", None, "500", None),
    (911, "Withdrawal", "2024-02-01", WALLET, EXTERNAL, "0.1", None, "Gift", None, None),
    (912, "Withdrawal", "2024-02-02", WALLET, EXTERNAL, "0.1", None, " gift ", None, None),
    (913, "Withdrawal", "2024-02-03", WALLET, EXTERNAL, "0.1", None, "Donation", None, None),
    (914, "Withdrawal", "2024-02-04", WALLET, EXTERNAL, "0.1", None, " Donation", None, None),
    (915, "Withdrawal", "2024-02-05", WALLET, EXTERNAL, "0.1", None, "Spent", None, "450"),
    (916, "Withdrawal", "2024-02-06", WALLET, EXTERNAL, "0.1", None, " spent ", None, "450"),
]


@pytest.fixture
def ledger(auth_client, test_engine):
    """Rows as older versions saved them, written directly (the API saves the
    listed spelling), then recalculated."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    with test_engine.begin() as con:
        for tx_id, typ, day, frm, to, amount, source, purpose, basis, gross in ROWS:
            con.execute(text(
                "INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount,"
                " fee_amount, fee_currency, source, purpose, cost_basis_usd, gross_proceeds_usd)"
                " VALUES (:id, :type, :day, :frm, :to, :amount, '0', 'BTC', :source, :purpose, :basis, :gross)"),
                dict(id=tx_id, type=typ, day=f"{day}T12:00:00Z", frm=frm, to=to, amount=amount, source=source,
                     purpose=purpose, basis=basis, gross=gross))
    assert auth_client.post("/api/transactions/recalculate").status_code == 200
    yield sessionmaker(bind=test_engine)
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def _figures(test_engine, tx_id):
    with test_engine.connect() as con:
        return con.execute(text(
            "SELECT cost_basis_usd, proceeds_usd, realized_gain_usd, holding_period FROM transactions WHERE id = :id"
        ), {"id": tx_id}).one()


def test_a_spaced_spelling_counts_as_its_listed_one(auth_client, test_engine, ledger):
    for spaced, listed in TWINS:
        assert _figures(test_engine, spaced) == _figures(test_engine, listed), (spaced, listed)


def test_form_8949_leaves_out_spaced_gifts_and_donations(test_engine, ledger):
    with ledger() as db:
        data = build_form_8949_and_schedule_d(2024, db)
    rows = data["short_term"] + data["long_term"]
    assert len(rows) == 2  # the two spends; " gift " and " Donation" are not sales
    assert sum(Decimal(str(r["proceeds"])) for r in rows) == Decimal("900.00")


def test_the_tax_report_and_the_dashboard_agree_with_the_screens(auth_client, test_engine, ledger):
    with ledger() as db:
        report = generate_report_data(db, 2024)
    assert report["income_summary"]["Income"] == 1000.0  # " Income " is income
    assert sorted(g["type"] for g in report["gifts_donations_lost"]) == [" Donation", " gift ", "Donation", "Gift"]
    dashboard = auth_client.get("/api/calculations/gains-and-losses").json()
    assert dashboard["income_earned"] == 1000.0


def test_ledger_review_knows_the_spaced_purposes(auth_client, ledger):
    check = next((c for c in auth_client.get("/api/review").json()["checks"]
                  if c["key"] == "withdrawal_purpose_unknown"), None)
    assert check is None or not {i["id"] for i in check["items"]} & {912, 914, 916}
