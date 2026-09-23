"""
Complete tax report data: year-end holdings are a snapshot at the end of the
tax year (later activity excluded), valued at the Dec 31 BTC price, and the
asset summary is the year's real gains — no placeholder numbers.
"""

from sqlalchemy.orm import sessionmaker

from backend.services.reports.reporting_core import generate_report_data
from backend.tests.conftest import STUB_HISTORICAL_USD

CLIENT = None
ENGINE = None


def _setup(auth_client, test_engine):
    global CLIENT, ENGINE
    CLIENT, ENGINE = auth_client, test_engine


def tx(**data):
    r = CLIENT.post("/api/transactions", json=data)
    assert r.status_code == 200, r.text


def report(year):
    db = sessionmaker(bind=ENGINE)()
    try:
        return generate_report_data(db, year)
    finally:
        db.close()


def test_year_end_snapshot_price_and_asset_summary(auth_client, test_engine):
    _setup(auth_client, test_engine)
    CLIENT.delete("/api/transactions/delete_all")
    tx(type="Buy", timestamp="2024-03-01T12:00:00Z", from_account_id=1, to_account_id=4,
       amount="1.0", cost_basis_usd="40000")
    tx(type="Sell", timestamp="2024-09-01T12:00:00Z", from_account_id=4, to_account_id=3,
       amount="0.2", gross_proceeds_usd="12000.00")
    tx(type="Sell", timestamp="2025-02-01T12:00:00Z", from_account_id=4, to_account_id=3,
       amount="0.5", gross_proceeds_usd="30000.00")

    data = report(2024)
    btc_rows = [r for r in data["end_of_year_balances"] if r["asset"].startswith("BTC")]
    held = sum(r["quantity"] for r in btc_rows)
    assert held == 0.8, f"12/31/2024 holdings should ignore the 2025 sale, got {held}"
    assert all("2024-12-31" in r["description"] for r in btc_rows)
    assert abs(sum(r["value"] for r in btc_rows) - 0.8 * STUB_HISTORICAL_USD) < 0.01
    assert "94153" not in str(data["end_of_year_balances"])

    summary = data["asset_summary"][0]
    # 0.2 BTC: basis 8000, proceeds 12000 -> +4000 (real, not the old placeholder)
    assert summary["profit"] == 4000.0 and summary["loss"] == 0.0 and summary["net"] == 4000.0

    # Live data is intact afterwards (full recalculation restored 2025 sale)
    balances = {b["name"]: b["balance"] for b in CLIENT.get("/api/calculations/accounts/balances").json()}
    assert abs(balances["Exchange BTC"] - 0.3) < 1e-9
    CLIENT.delete("/api/transactions/delete_all")
