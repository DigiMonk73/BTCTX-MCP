"""
The Complete Tax Report's prices (#144, PR 5): holdings valued at the price
when the tax year began and ended (midnight in the tax timezone, its hour's
price), the year's values filled in from a price listed with the price each
used, the method stated, and the appraisal note beside donations.
"""

import io
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pypdf import PdfReader
from sqlalchemy.orm import sessionmaker

from backend.services import hourly_prices
from backend.services.reports.complete_tax_report import generate_comprehensive_tax_report
from backend.services.reports.reporting_core import generate_report_data
from backend.tests.conftest import stub_daily_prices, stub_prices_at

BANK, EXCHANGE_BTC, EXTERNAL = 1, 4, 99
NEW_YORK_2024_END = datetime(2025, 1, 1, 5, tzinfo=timezone.utc)  # midnight in New York


def post(client, **fields) -> dict:
    r = client.post("/api/transactions", json=fields)
    assert r.status_code == 200, r.text
    return r.json()


def buy(client, when="2024-03-01T12:00:00Z"):
    post(client, type="Buy", timestamp=when, from_account_id=BANK, to_account_id=EXCHANGE_BTC, amount="1",
         fee_amount="0", fee_currency="USD", cost_basis_usd="40000")


def report(engine, year: int) -> dict:
    db = sessionmaker(bind=engine)()
    try:
        return generate_report_data(db, year)
    finally:
        db.close()


def pdf_text(data: dict) -> str:
    reader = PdfReader(io.BytesIO(generate_comprehensive_tax_report(data)))
    return " ".join(" ".join((page.extract_text() or "").split()) for page in reader.pages)


@pytest.fixture
def clean(auth_client):
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    auth_client.put("/api/settings/tax-timezone", json={"timezone": "UTC", "chosen": True})
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def test_holdings_are_valued_when_the_tax_year_ends_and_the_next_one_starts_there(
        auth_client, test_engine, clean, monkeypatch):
    """New York: 2024 ends at 2025-01-01 05:00 UTC; that hour's price, not December 31's."""
    assert auth_client.put("/api/settings/tax-timezone", json={"timezone": "America/New_York", "chosen": True}).status_code == 200
    buy(auth_client)
    stub_prices_at(monkeypatch, lambda when: 70000 if hourly_prices.hour_of(when) ==
                   int(NEW_YORK_2024_END.timestamp()) else 10000)
    end = report(test_engine, 2024)
    held = [r for r in end["end_of_year_balances"] if r["asset"].startswith("BTC")]
    assert [r["value"] for r in held] == [70000.0]
    assert held[0]["description"] == "@ $70,000.00 per BTC, the price at the hour the tax year ended (2025-01-01 05:00 UTC)"
    start = report(test_engine, 2025)
    assert [r["value"] for r in start["start_of_year_balances"]] == [70000.0]
    assert "Market value at $70,000.00 per BTC, the price at the hour the tax year ended (2025-01-01 05:00 UTC)." \
        in pdf_text(end)


def test_where_there_is_no_hourly_price_the_days_is_said(auth_client, test_engine, clean, monkeypatch):
    buy(auth_client)
    stub_prices_at(monkeypatch, lambda when: 60000, moment="day")
    held = [r for r in report(test_engine, 2024)["end_of_year_balances"] if r["asset"].startswith("BTC")]
    assert held[0]["description"] == ("@ $60,000.00 per BTC, 2025-01-01's 00:00 UTC price (no hourly price for "
                                      "when the tax year ended)")


def test_a_year_not_over_has_no_year_end_value(auth_client, test_engine, clean, monkeypatch):
    year = datetime.now(timezone.utc).year
    buy(auth_client, f"{year}-01-02T12:00:00Z")
    stub_prices_at(monkeypatch, lambda when: 60000)
    balances = report(test_engine, year)["end_of_year_balances"]
    assert next(r for r in balances if r["asset"] == "Total")["value"] is None
    assert balances[0]["description"] == f"No BTC price for when {year} ended: not priced"


def test_the_year_end_price_is_shown_in_cents(auth_client, test_engine, clean, monkeypatch):
    """Review of #176: a Bitstamp hour after the year files comes as returned (97123.456)."""
    buy(auth_client)
    stub_prices_at(monkeypatch, lambda when: Decimal("97123.456"))
    held = [r for r in report(test_engine, 2024)["end_of_year_balances"] if r["asset"].startswith("BTC")]
    assert held[0]["description"].startswith("@ $97,123.46 per BTC") and held[0]["value"] == 97123.46


def test_the_years_values_from_a_price_are_listed_with_the_price_used(auth_client, test_engine, clean, monkeypatch):
    buy(auth_client, "2025-01-10T12:00:00Z")
    stub_prices_at(monkeypatch, lambda when: 50000)
    post(auth_client, type="Deposit", timestamp="2025-03-01T14:47:00Z", from_account_id=EXTERNAL,
         to_account_id=EXCHANGE_BTC, amount="0.1", fee_amount="0", fee_currency="BTC", source="Reward")
    post(auth_client, type="Deposit", timestamp="2025-04-01T09:00:00Z", from_account_id=EXTERNAL,
         to_account_id=EXCHANGE_BTC, amount="0.1", fee_amount="0", fee_currency="BTC", source="Income",
         cost_basis_usd="5555")
    stub_prices_at(monkeypatch, lambda when: 30000, moment="day")
    stub_daily_prices(monkeypatch, lambda day: 30000)  # the same day's price, by either path
    post(auth_client, type="Withdrawal", timestamp="2025-06-01T10:20:00Z", from_account_id=EXCHANGE_BTC,
         to_account_id=EXTERNAL, amount="0.05", fee_amount="0.0001", fee_currency="BTC", purpose="Spent")
    stub_daily_prices(monkeypatch, lambda day: 48000)
    post(auth_client, type="Deposit", timestamp="2025-07-01T09:00:00Z", from_account_id=EXTERNAL,
         to_account_id=EXCHANGE_BTC, amount="0.1", fee_amount="0", fee_currency="BTC", source="Inherited",
         acquired_at="2025-05-20")
    data = report(test_engine, 2025)
    assert [(r["transaction"], r["value"], r["usd"], r["priced_at"]) for r in data["priced_values"]] == [
        ("Deposit (Reward)", "Value (income and basis)", 5000.0, "When its hour began (2025-03-01 14:00 UTC)"),
        ("Withdrawal (Spent)", "Proceeds (before fees)", 1500.0, "That day's (2025-06-01) 00:00 UTC price"),
        ("Withdrawal (Spent)", "Network fee value", 3.0, "That day's (2025-06-01) 00:00 UTC price"),
        ("Deposit (Inherited)", "Value (cost basis)", 4800.0, "Its date of death's (2025-05-20) 00:00 UTC price"),
    ]
    text = pdf_text(data)
    assert "Values from the BTC price" in text and "When its hour began (2025-03-01 14:00 UTC)" in text
    assert "The IRS has not approved any price source or method" in text


def test_a_year_with_only_typed_values_says_so(auth_client, test_engine, clean):
    buy(auth_client)
    data = report(test_engine, 2024)
    assert data["priced_values"] == []
    assert "Values from the BTC price None of 2024's values: each was entered with its transaction." in pdf_text(data)


def test_a_donation_brings_the_appraisal_note(auth_client, test_engine, clean):
    buy(auth_client)
    appraisal = "A deduction for donated bitcoin over $5,000 needs a qualified appraisal"
    post(auth_client, type="Withdrawal", timestamp="2024-06-01T12:00:00Z", from_account_id=EXCHANGE_BTC,
         to_account_id=EXTERNAL, amount="0.01", fee_amount="0", fee_currency="BTC", purpose="Gift",
         fmv_usd="500")
    assert appraisal not in pdf_text(report(test_engine, 2024))
    post(auth_client, type="Withdrawal", timestamp="2024-07-01T12:00:00Z", from_account_id=EXCHANGE_BTC,
         to_account_id=EXTERNAL, amount="0.01", fee_amount="0", fee_currency="BTC", purpose="Donation",
         fmv_usd="600")
    assert appraisal in pdf_text(report(test_engine, 2024))


def test_a_gift_value_from_the_price_is_listed_and_the_notes_agree(auth_client, test_engine, clean, monkeypatch):
    """#255: a gift's value filled from the price is in the list, and no note says gift values aren't."""
    buy(auth_client, "2025-01-10T12:00:00Z")
    stub_prices_at(monkeypatch, lambda when: Decimal("50000"))
    post(auth_client, type="Withdrawal", timestamp="2025-05-01T12:34:00Z", from_account_id=EXCHANGE_BTC,
         to_account_id=EXTERNAL, amount="0.01", fee_amount="0", fee_currency="BTC", purpose="Gift")
    data = report(test_engine, 2025)
    assert [(r["value"], r["usd"]) for r in data["priced_values"]] == [("Value (fair market value)", 500.0)]
    text = pdf_text(data)
    assert "isn't tracked this way" not in text and "network fee value of the year" not in text
    assert "Every other value of the year was entered with its transaction." in text
    assert "filled in before BitcoinTX 1.2.9 isn't marked as from the price" in text


def test_the_priced_value_is_the_stored_one(auth_client, test_engine, clean, monkeypatch):
    """The table shows the value the ledger holds, rounded as stored."""
    buy(auth_client, "2025-01-10T12:00:00Z")
    stub_prices_at(monkeypatch, lambda when: Decimal("12345.67"))
    tx = post(auth_client, type="Deposit", timestamp="2025-03-01T14:47:00Z", from_account_id=EXTERNAL,
              to_account_id=EXCHANGE_BTC, amount="0.123", fee_amount="0", fee_currency="BTC", source="Rebate")
    row = report(test_engine, 2025)["priced_values"][0]
    assert (row["value"], row["usd"]) == ("Value (cost basis)", float(tx["cost_basis_usd"]))


def test_each_value_from_a_price_names_where_the_price_came_from(auth_client, test_engine, clean):
    """#145: the report's list says which source the stored price came from (Bitstamp, your Mempool)."""
    from sqlalchemy import text

    from backend.models.btc_price import BtcPriceHourly

    buy(auth_client, "2025-01-10T12:00:00Z")
    hour = hourly_prices.hour_of(datetime(2025, 3, 1, 14, tzinfo=timezone.utc))
    with sessionmaker(bind=test_engine)() as db:
        db.add(BtcPriceHourly(hour=hour, usd=Decimal("50000"), source="mempool"))
        db.commit()
    try:
        post(auth_client, type="Deposit", timestamp="2025-03-01T14:47:00Z", from_account_id=EXTERNAL,
             to_account_id=EXCHANGE_BTC, amount="0.1", fee_amount="0", fee_currency="BTC", source="Reward")
        rows = report(test_engine, 2025)["priced_values"]
        assert rows[0]["priced_at"] == "When its hour began (2025-03-01 14:00 UTC), your Mempool"
    finally:
        with test_engine.begin() as conn:
            conn.execute(text("DELETE FROM btc_price_hourly WHERE hour = :h"), {"h": hour})


def test_the_report_reads_the_year_files_once(auth_client, test_engine, clean, monkeypatch):
    """Review of #190: the year files' hours (Bitstamp) are read once for the whole report."""
    from backend.services import price_files as pf

    hour = hourly_prices.hour_of(datetime(2026, 4, 1, 12, tzinfo=timezone.utc))
    line = pf.YearLine(2026, pf.year_start(2026), hour + 3600, 1, "x")
    reads = []
    monkeypatch.setattr(pf, "read_manifest", lambda path=None: reads.append(1) or [line])
    monkeypatch.setattr(hourly_prices, "_year_prices", lambda line, remember=True: {hour: Decimal("70000.00")})
    monkeypatch.setattr(hourly_prices, "hourly_price", lambda db, when, **k: (Decimal("70000.00"), "bitstamp"))
    for minute in ("10", "20"):
        post(auth_client, type="Deposit", timestamp=f"2026-04-01T12:{minute}:00Z", from_account_id=EXTERNAL,
             to_account_id=EXCHANGE_BTC, amount="0.1", fee_amount="0", fee_currency="BTC", source="Reward")
    reads.clear()
    rows = report(test_engine, 2026)["priced_values"]
    assert [r["priced_at"].endswith(", Bitstamp") for r in rows] == [True, True]
    assert len(reads) == 1
