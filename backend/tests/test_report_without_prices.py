"""
The complete tax report works with price lookups off. It only needs a BTC
price to value the holdings on Jan 1 and Dec 31; without one those values
read "not priced" (never $0) and everything else is the same.

Before, the Jan 1 lookup ran even when nothing was held and a missing price
failed the whole report with a 422; a missing Dec 31 price valued the
holdings at $0.
"""

import io
import logging

import pytest
from pypdf import PdfReader
from sqlalchemy.orm import sessionmaker

from backend.services import outbound
from backend.services.reports.reporting_core import generate_report_data
from backend.tests.conftest import stub_daily_prices

# Every USD value typed, so the ledger saves without prices
LEDGER = [
    dict(type="Deposit", timestamp="2023-01-15T17:00:00Z", from_account_id=99, to_account_id=1,
         amount="100000", fee_amount="0", fee_currency="USD", source="N/A"),
    dict(type="Buy", timestamp="2023-02-01T17:00:00Z", from_account_id=1, to_account_id=4,
         amount="1.0", cost_basis_usd="23000", fee_amount="0", fee_currency="USD"),
    dict(type="Transfer", timestamp="2023-06-01T16:00:00Z", from_account_id=4, to_account_id=2,
         amount="0.6", fee_amount="0.0002", fee_currency="BTC", fee_usd="10"),
    dict(type="Sell", timestamp="2023-09-10T16:00:00Z", from_account_id=4, to_account_id=3,
         amount="0.3", gross_proceeds_usd="9000", fee_amount="0", fee_currency="USD"),
    dict(type="Deposit", timestamp="2024-05-01T16:00:00Z", from_account_id=99, to_account_id=2,
         amount="0.02", cost_basis_usd="1000", fee_amount="0", fee_currency="BTC", source="Income"),
    dict(type="Sell", timestamp="2024-07-01T16:00:00Z", from_account_id=4, to_account_id=3,
         amount="0.1", gross_proceeds_usd="6000", fee_amount="0", fee_currency="USD"),
]


@pytest.fixture
def ledger(auth_client, monkeypatch):
    """The ledger saved with prices off and nothing stored."""
    stub_daily_prices(monkeypatch, lambda day: None)
    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings(price_source="off"))
    auth_client.delete("/api/transactions/delete_all")
    for tx in LEDGER:
        r = auth_client.post("/api/transactions", json=tx)
        assert r.status_code == 200, (tx, r.text)
    yield
    auth_client.delete("/api/transactions/delete_all")


def report(engine, year):
    with sessionmaker(bind=engine)() as db:
        return generate_report_data(db, year)


def pdf_text(client, year):
    r = client.get(f"/api/reports/complete_tax_report?year={year}&format=pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    text = " ".join(page.extract_text() for page in PdfReader(io.BytesIO(r.content)).pages)
    return " ".join(text.split())  # table cells wrap: compare words, not lines


@pytest.mark.parametrize("year", [2023, 2024])
def test_the_report_generates_with_price_lookups_off(auth_client, ledger, year):
    text = pdf_text(auth_client, year)
    assert "not priced" in text
    assert f"No BTC price for {year}-12-31" in text


def test_unpriced_holdings_are_not_priced_never_zero(auth_client, test_engine, ledger):
    data = report(test_engine, 2024)
    start = data["start_of_year_balances"]
    end = data["end_of_year_balances"]
    # Jan 1, 2024: 0.5998 BTC in the Wallet and 0.1 on the exchange
    assert sum(r["quantity"] for r in start) == pytest.approx(0.6998)
    assert all(r["value"] is None for r in start)
    assert all(r["value"] is None for r in end)  # the Total row too
    assert "No BTC price is stored for 2024-01-01" in pdf_text(auth_client, 2024)
    # The gains don't need a price: 0.1 BTC bought 2023-02-01 at 23,000/BTC, sold for 6,000
    assert data["capital_gains_summary"]["long_term"]["gain"] == pytest.approx(3700.0)


def test_nothing_held_on_jan_1_needs_no_price(auth_client, test_engine, ledger, monkeypatch):
    asked = []
    stub_daily_prices(monkeypatch, lambda day: asked.append(day))  # records, answers "no price"
    data = report(test_engine, 2023)
    assert data["start_of_year_balances"] == []
    assert [d.isoformat() for d in asked] == ["2023-12-31"]  # only the year-end value was looked up


def test_with_a_price_the_holdings_are_valued(auth_client, test_engine, ledger, monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 50000)
    data = report(test_engine, 2024)
    assert sum(r["value"] for r in data["start_of_year_balances"]) == pytest.approx(0.6998 * 50000)
    total = next(r for r in data["end_of_year_balances"] if r["asset"] == "Total")
    assert total["value"] == pytest.approx(total["quantity"] * 50000)
    assert "not priced" not in pdf_text(auth_client, 2024)


def test_jan_1_holdings_equal_the_previous_dec_31(auth_client, test_engine, ledger, monkeypatch):
    """They used to count lots twice: Jan 1, 2024 showed 1.5998 BTC here, not 0.6998."""
    stub_daily_prices(monkeypatch, lambda day: 50000)
    for year in (2024, 2025):
        start = report(test_engine, year)["start_of_year_balances"]
        before = [r for r in report(test_engine, year - 1)["end_of_year_balances"] if r["asset"] != "Total"]
        assert sum(r["quantity"] for r in start) == pytest.approx(sum(r["quantity"] for r in before))
        assert sum(r["quantity"] * r["avg_cost_basis"] for r in start) == \
            pytest.approx(sum(r["cost"] for r in before), abs=0.01)


def test_an_unvalued_old_fee_names_its_transaction(auth_client, test_engine, ledger):
    """A withdrawal's BTC fee saved before fee values were stored (migration
    0004 filled only transfers) still needs a price; with lookups off the
    report's 422 said only "No BTC price is stored for 2024-06-01"."""
    from sqlalchemy import text

    r = auth_client.post("/api/transactions", json=dict(
        type="Withdrawal", timestamp="2024-06-01T16:00:00Z", from_account_id=2, to_account_id=99,
        amount="0.01", fee_amount="0.0001", fee_currency="BTC", fee_usd="5", purpose="Gift"))
    assert r.status_code == 200, r.text
    with test_engine.begin() as con:  # as an old row: no stored fee value
        con.execute(text("UPDATE transactions SET fee_usd = NULL, fee_usd_manual = 0 WHERE id = :i"),
                    {"i": r.json()["id"]})
    r = auth_client.get("/api/reports/complete_tax_report?year=2024&format=pdf")
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail.startswith("Withdrawal of 0.01 BTC on 2024-06-01: its network fee has no USD value")
    assert "No BTC price is stored for 2024-06-01" in detail
