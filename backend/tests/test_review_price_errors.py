"""
Ledger review's fee check (review.fee_price_changes) passes over a transfer
only when there is no price for its day. Any other failure of the lookup is
an error, not a shorter list that looks like "nothing to fix".
"""

import pytest

from backend.services import price_history
from backend.tests.test_review import ids, priced  # noqa: F401  (fixture)


def test_a_day_without_a_price_is_passed_over(auth_client, priced, monkeypatch):  # noqa: F811
    def no_price(db, when):
        raise price_history.no_price(when.date())

    monkeypatch.setattr(price_history, "daily_price", no_price)
    r = auth_client.get("/api/review")
    assert r.status_code == 200, r.text
    assert ids(r.json(), "fee_value_off") == []


def test_any_other_lookup_failure_is_an_error(auth_client, priced, monkeypatch):  # noqa: F811
    def broken(db, when):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(price_history, "daily_price", broken)
    with pytest.raises(RuntimeError, match="database is locked"):
        auth_client.get("/api/review")


def test_a_lookup_failure_of_an_income_check_is_an_error(auth_client, test_engine, monkeypatch):
    """The income checks too: a broken lookup isn't "no price" (no transfers
    here, so the fee check doesn't raise first)."""
    from sqlalchemy import text

    auth_client.delete("/api/transactions/delete_all")
    with test_engine.begin() as con:
        con.execute(text(
            "INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount, fee_amount,"
            " fee_currency, source, cost_basis_usd) VALUES (980, 'Deposit', '2024-05-01T12:00:00Z', 99, 2, '0.01',"
            " '0', 'BTC', 'Income', '123')"))

    def broken(db, when):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(price_history, "daily_price", broken)
    try:
        with pytest.raises(RuntimeError, match="database is locked"):
            auth_client.get("/api/review")
    finally:
        auth_client.delete("/api/transactions/delete_all")
