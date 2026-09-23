"""
backend/tests/test_tax_timezone.py

Tax dates follow the user's timezone, not UTC: tax-year membership, the dates
printed on Form 8949, holding-period anniversaries, and AI-entered dates
without a timezone.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import sessionmaker

from backend.services.reports.form_8949 import build_form_8949_and_schedule_d
from backend.services.tax_time import tax_year_bounds
from backend.services.transaction import holding_period

CLIENT = None
ENGINE = None
BANK, EXCHANGE_USD, EXCHANGE_BTC = 1, 3, 4
NY = "America/New_York"


@pytest.fixture(autouse=True, scope="module")
def _setup(auth_client, test_engine):
    global CLIENT, ENGINE
    CLIENT, ENGINE = auth_client, test_engine
    yield
    CLIENT.put("/api/settings/tax-timezone", json={"timezone": "UTC"})


@pytest.fixture(autouse=True)
def _clean():
    CLIENT.delete("/api/transactions/delete_all")
    CLIENT.put("/api/settings/tax-timezone", json={"timezone": "UTC"})
    yield
    CLIENT.delete("/api/transactions/delete_all")


def set_tz(name):
    r = CLIENT.put("/api/settings/tax-timezone", json={"timezone": name})
    assert r.status_code == 200, r.text


def buy(ts):
    r = CLIENT.post("/api/transactions", json={
        "type": "Buy", "timestamp": ts, "from_account_id": BANK, "to_account_id": EXCHANGE_BTC,
        "amount": "1.0", "cost_basis_usd": "20000"})
    assert r.status_code == 200, r.text


def sell(ts):
    r = CLIENT.post("/api/transactions", json={
        "type": "Sell", "timestamp": ts, "from_account_id": EXCHANGE_BTC,
        "to_account_id": EXCHANGE_USD, "amount": "0.1", "gross_proceeds_usd": "5000.00"})
    assert r.status_code == 200, r.text
    return r.json()


def report(year):
    db = sessionmaker(bind=ENGINE)()
    try:
        return build_form_8949_and_schedule_d(year, db)
    finally:
        db.close()


def rows(year):
    data = report(year)
    return data["short_term"] + data["long_term"]


class TestSetting:
    def test_get_and_put(self):
        assert CLIENT.get("/api/settings/tax-timezone").json()["timezone"] == "UTC"
        set_tz(NY)
        assert CLIENT.get("/api/settings/tax-timezone").json() == {"timezone": NY, "source": "setting"}

    def test_invalid_timezone_rejected(self):
        r = CLIENT.put("/api/settings/tax-timezone", json={"timezone": "Mars/Olympus"})
        assert r.status_code == 400

    def test_requires_login(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        assert TestClient(app).get("/api/settings/tax-timezone").status_code == 401


class TestTaxYear:
    def test_new_years_eve_sale_belongs_to_local_year(self):
        buy("2024-06-01T12:00:00Z")
        sell("2025-01-01T03:00:00Z")          # Dec 31 2024, 10 pm in New York
        assert len(rows(2025)) == 1 and not rows(2024)   # UTC: 2025
        set_tz(NY)
        assert len(rows(2024)) == 1 and not rows(2025)   # New York: 2024
        assert rows(2024)[0]["date_sold"] == "12/31/2024"

    def test_bounds_are_local_midnights(self):
        start, end = tax_year_bounds(2025, ZoneInfo(NY))
        assert start == datetime(2025, 1, 1, 5, tzinfo=timezone.utc)
        assert end == datetime(2026, 1, 1, 5, tzinfo=timezone.utc)

    def test_complete_tax_report_includes_last_second_of_year(self):
        buy("2024-06-01T12:00:00Z")
        sell("2025-12-31T23:59:59Z")
        r = CLIENT.get("/api/reports/complete_tax_report", params={"year": 2025})
        assert r.status_code == 200 and r.content[:4] == b"%PDF"
        assert rows(2025)


class TestHoldingPeriod:
    def test_anniversary_is_decided_on_local_dates(self):
        acquired = datetime(2024, 1, 1, 12, tzinfo=timezone.utc)
        disposed = datetime(2025, 1, 2, 3, tzinfo=timezone.utc)   # Jan 1, 10 pm in New York
        assert holding_period(acquired, disposed) == "LONG"                 # UTC: Jan 2
        assert holding_period(acquired, disposed, ZoneInfo(NY)) == "SHORT"  # NY: anniversary

    def test_changing_timezone_recalculates_stored_holding_period(self):
        buy("2024-01-01T12:00:00Z")
        tx = sell("2025-01-02T03:00:00Z")
        assert CLIENT.get(f"/api/transactions/{tx['id']}").json()["holding_period"] == "LONG"
        set_tz(NY)
        assert CLIENT.get(f"/api/transactions/{tx['id']}").json()["holding_period"] == "SHORT"


class TestEntryImportDates:
    def test_bare_date_is_local_noon(self):
        set_tz(NY)
        r = CLIENT.post("/api/import/entries/preview", json={"rows": [{
            "date": "2025-03-05", "type": "Buy", "amount": "0.1", "from_account": "Bank",
            "to_account": "Exchange BTC", "cost_basis_usd": "5000"}]})
        assert r.json()["results"][0]["normalized"]["date"] == "2025-03-05T17:00:00Z"  # noon EST

    def test_local_time_without_offset_uses_tax_timezone(self):
        set_tz(NY)
        r = CLIENT.post("/api/import/entries/preview", json={"rows": [{
            "date": "2025-12-31T22:00:00", "type": "Buy", "amount": "0.1", "from_account": "Bank",
            "to_account": "Exchange BTC", "cost_basis_usd": "5000"}]})
        assert r.json()["results"][0]["normalized"]["date"] == "2026-01-01T03:00:00Z"

    def test_explicit_offset_wins(self):
        set_tz(NY)
        r = CLIENT.post("/api/import/entries/preview", json={"rows": [{
            "date": "2025-03-05T10:00:00Z", "type": "Buy", "amount": "0.1", "from_account": "Bank",
            "to_account": "Exchange BTC", "cost_basis_usd": "5000"}]})
        assert r.json()["results"][0]["normalized"]["date"] == "2025-03-05T10:00:00Z"
