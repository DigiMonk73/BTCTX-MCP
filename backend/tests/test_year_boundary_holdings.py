"""
Beginning-of-year holdings across year boundaries: buys, sells, transfers
and withdrawals with BTC fees in 2023-2025, one withdrawal an hour before
Jan 1, 2025 (UTC) and one sell half an hour after. Jan 1 must equal the
previous Dec 31 (quantity and cost) and an independent tally of every
movement, fees included, in the tax timezone.

v1.2.0 rebuilt old lots at full size after BTC had moved or been sold: it
reported 2.08945 BTC on Jan 1, 2025 for the 0.83945 held (found by Grok
Bot's StartOS test, fixed in 117837d; these figures pin it).
"""

from decimal import Decimal as D

import pytest
from sqlalchemy.orm import sessionmaker

from backend.services.reports.reporting_core import generate_report_data
from backend.tests.conftest import stub_daily_prices

BANK, WALLET, EX_USD, EX_BTC, EXT = 1, 2, 3, 4, 99

LEDGER = [
    dict(type="Deposit", timestamp="2023-01-10T17:00:00Z", from_account_id=EXT, to_account_id=BANK,
         amount="100000", fee_amount="0", fee_currency="USD", source="N/A"),
    dict(type="Buy", timestamp="2023-02-01T17:00:00Z", from_account_id=BANK, to_account_id=EX_BTC,
         amount="1.0", cost_basis_usd="23000", fee_amount="0", fee_currency="USD"),
    dict(type="Transfer", timestamp="2023-03-01T16:00:00Z", from_account_id=EX_BTC, to_account_id=WALLET,
         amount="0.5", fee_amount="0.0001", fee_currency="BTC", fee_usd="3"),
    dict(type="Sell", timestamp="2023-06-01T16:00:00Z", from_account_id=EX_BTC, to_account_id=EX_USD,
         amount="0.2", gross_proceeds_usd="6000", fee_amount="0", fee_currency="USD"),
    dict(type="Withdrawal", timestamp="2023-09-01T16:00:00Z", from_account_id=WALLET, to_account_id=EXT,
         amount="0.1", fee_amount="0.0001", fee_currency="BTC", fee_usd="4", purpose="Spent",
         proceeds_usd="3000"),
    # 2024
    dict(type="Buy", timestamp="2024-03-01T17:00:00Z", from_account_id=BANK, to_account_id=EX_BTC,
         amount="0.3", cost_basis_usd="18000", fee_amount="0", fee_currency="USD"),
    dict(type="Transfer", timestamp="2024-04-01T16:00:00Z", from_account_id=EX_BTC, to_account_id=WALLET,
         amount="0.4", fee_amount="0.0002", fee_currency="BTC", fee_usd="12"),
    dict(type="Withdrawal", timestamp="2024-08-01T16:00:00Z", from_account_id=WALLET, to_account_id=EXT,
         amount="0.05", fee_amount="0.0001", fee_currency="BTC", fee_usd="5", purpose="Gift",
         fmv_usd="3000"),
    dict(type="Sell", timestamp="2024-10-01T16:00:00Z", from_account_id=EX_BTC, to_account_id=EX_USD,
         amount="0.1", gross_proceeds_usd="6500", fee_amount="0", fee_currency="USD"),
    dict(type="Withdrawal", timestamp="2024-12-31T23:00:00Z", from_account_id=WALLET, to_account_id=EXT,
         amount="0.01", fee_amount="0.00005", fee_currency="BTC", fee_usd="4.5", purpose="Spent",
         proceeds_usd="900"),
    # 2025 (just after the boundary, and later)
    dict(type="Sell", timestamp="2025-01-01T00:30:00Z", from_account_id=EX_BTC, to_account_id=EX_USD,
         amount="0.05", gross_proceeds_usd="4700", fee_amount="0", fee_currency="USD"),
    dict(type="Transfer", timestamp="2025-03-01T16:00:00Z", from_account_id=WALLET, to_account_id=EX_BTC,
         amount="0.1", fee_amount="0.0001", fee_currency="BTC", fee_usd="8"),
]


def expected_holdings(before):
    """Independent tally: BTC acquired minus everything that left (fees included)."""
    held = D("0")
    for tx in LEDGER:
        if tx["timestamp"] >= before:
            continue
        a, fee = D(tx["amount"]), D(tx.get("fee_amount") or "0")
        btc_fee = fee if tx["fee_currency"] == "BTC" else D("0")
        if tx["type"] == "Buy":
            held += a
        elif tx["type"] == "Sell":
            held -= a
        elif tx["type"] == "Withdrawal":
            held -= a + btc_fee
        elif tx["type"] == "Transfer":
            held -= btc_fee
    return held


@pytest.fixture
def ledger(auth_client):
    auth_client.delete("/api/transactions/delete_all")
    for tx in LEDGER:
        r = auth_client.post("/api/transactions", json=tx)
        assert r.status_code == 200, (tx, r.text)
    yield
    auth_client.delete("/api/transactions/delete_all")


def report(engine, year):
    with sessionmaker(bind=engine)() as db:
        return generate_report_data(db, year)


def test_jan_1_holdings_match_the_ledger_and_the_previous_dec_31(auth_client, test_engine, ledger, monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 50000)
    out = {}
    for year in (2023, 2024, 2025, 2026):
        data = report(test_engine, year)
        boy = sum(D(str(r["quantity"])) for r in data["start_of_year_balances"])
        eoy = [r for r in data["end_of_year_balances"] if r["asset"] == "Total"][0]
        boy_cost = sum(D(str(r["quantity"])) * D(str(r["avg_cost_basis"])) for r in data["start_of_year_balances"])
        out[year] = dict(boy=boy, boy_cost=round(boy_cost, 2), eoy=D(str(eoy["quantity"])),
                         eoy_cost=D(str(eoy["cost"])),
                         exp_boy=expected_holdings(f"{year}-01-01"), exp_eoy=expected_holdings(f"{year + 1}-01-01"))
    for y, v in out.items():
        assert v["eoy"] == v["exp_eoy"], (y, v)
    for y in (2024, 2025, 2026):
        assert out[y]["boy"] == out[y - 1]["eoy"], (y, out[y], out[y - 1])
        assert out[y]["boy_cost"] == out[y - 1]["eoy_cost"], (y, out[y], out[y - 1])
    for y, v in out.items():
        assert v["boy"] == v["exp_boy"], (y, v)
    assert [out[y]["boy"] for y in (2024, 2025, 2026)] == [D("0.6998"), D("0.83945"), D("0.78935")]


@pytest.mark.parametrize("tz", ["America/Chicago", "Asia/Tokyo"])
def test_jan_1_holdings_in_the_tax_timezone(auth_client, test_engine, ledger, monkeypatch, tz):
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    stub_daily_prices(monkeypatch, lambda day: 50000)
    assert auth_client.put("/api/settings/tax-timezone", json={"timezone": tz}).status_code == 200
    try:
        out = {}
        for year in (2024, 2025):
            data = report(test_engine, year)
            boundary = datetime(year, 1, 1, tzinfo=ZoneInfo(tz)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            prev_eoy = [r for r in report(test_engine, year - 1)["end_of_year_balances"] if r["asset"] == "Total"][0]
            boy = sum(D(str(r["quantity"])) for r in data["start_of_year_balances"])
            out[year] = (boy, D(str(prev_eoy["quantity"])), expected_holdings(boundary))
        for y, (boy, prev, exp) in out.items():
            assert boy == prev == exp, (tz, y, boy, prev, exp)
    finally:
        auth_client.put("/api/settings/tax-timezone", json={"timezone": "UTC"})
