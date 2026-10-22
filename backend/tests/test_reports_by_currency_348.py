"""
The reports by currency (spec 1.4, 5.7, 5.15's "by currency"; card B3 #348):
income, a rebate and an inherited deposit into a second wallet show in the
tax report and on the dashboard, a gift from it is listed, the transaction
history calls its income income, and the CSV export marks its priced basis.
A deposit into a second bank stays dollars.
"""

import csv
import io
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.reports.reporting_core import generate_report_data
from backend.services.reports.transaction_history import generate_transaction_history_report
from backend.tests.conftest import default_login, stub_prices_at

PRICE = Decimal("50000")
COLD, CREDIT_UNION, EXTERNAL = 100, 101, 99


def save(client, **body) -> dict:
    r = client.post("/api/transactions", json={"fee_amount": "0", "timestamp": "2024-06-15T15:00:00Z", **body})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def client(fresh_app, monkeypatch) -> TestClient:
    stub_prices_at(monkeypatch, lambda when: PRICE)
    c = TestClient(app)
    assert c.post("/api/login", json=default_login()).status_code == 200
    for kind, name in (("wallet", "Cold Storage"), ("bank", "Credit Union")):
        assert c.post("/api/accounts/", json={"kind": kind, "name": name}).status_code == 201
    into = {"type": "Deposit", "from_account_id": EXTERNAL, "to_account_id": COLD}
    save(c, **into, amount="0.01", source="Income")                         # priced: $500
    save(c, **into, amount="0.02", source="Interest", cost_basis_usd="900")
    save(c, **into, amount="0.004", source="Rebate")                        # priced: $200
    save(c, **into, amount="0.1", source="Inherited", acquired_at="2024-05-01", cost_basis_usd="6000")
    save(c, type="Deposit", from_account_id=EXTERNAL, to_account_id=CREDIT_UNION, amount="700", source="N/A")
    save(c, type="Withdrawal", from_account_id=COLD, to_account_id=EXTERNAL, amount="0.002", purpose="Gift",
         timestamp="2024-07-01T12:00:00Z")                                   # priced: $100
    return c


def test_the_tax_reports_income_rebates_gifts_and_priced_values(client, fresh_app):
    report = generate_report_data(fresh_app(), 2024)
    assert (report["income_summary"]["Income"], report["income_summary"]["Interest"]) == (500.0, 900.0)
    assert [(t["type"], t["value_usd"]) for t in report["income_transactions"]] == [("Income", 500.0), ("Interest", 900.0)]
    assert [r["value_usd"] for r in report["rebates"]] == [200.0]
    assert [(g["type"], g["fmv_usd"]) for g in report["gifts_donations_lost"]] == [("Gift", 100.0)]
    assert [(v["value"], v["usd"]) for v in report["priced_values"]] == [
        ("Value (income and basis)", 500.0), ("Value (cost basis)", 200.0), ("Value (fair market value)", 100.0)]


def test_the_dashboards_income_and_rebates(client):
    gains = client.get("/api/calculations/gains-and-losses").json()
    assert (gains["income_earned"], gains["interest_earned"], gains["total_income"]) == (500.0, 900.0, 1400.0)
    assert (gains["income_btc"], gains["rebates_received"], gains["rebates_btc"]) == (0.01, 200.0, 0.004)


def test_the_transaction_historys_income(client, fresh_app):
    rows = list(csv.DictReader(io.StringIO(generate_transaction_history_report(fresh_app(), 2024, "csv").decode())))
    assert [r["type"] for r in rows if r["type"] != "Sell/Withdrawal"] == [
        "Income", "Interest", "Rebate", "Inherited", "Deposit"]


def test_the_csv_export_marks_a_priced_basis(client):
    rows = list(csv.DictReader(io.StringIO(client.get("/api/backup/csv").text)))
    assert [(r["source"], r["cost_basis_typed"]) for r in rows if r["type"] == "Deposit"] == [
        ("Income", "no"), ("Interest", "yes"), ("Rebate", "no"), ("Inherited", "yes"), ("N/A", "")]
