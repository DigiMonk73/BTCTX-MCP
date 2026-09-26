"""
GET /api/reports/years feeds the Reports page's Tax year drop-down: every
year from the first transaction (in the tax timezone) to this year, newest
first, plus the years with IRS form templates.
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.routers.reports import get_supported_years


def this_year(tz_name="UTC"):
    from zoneinfo import ZoneInfo

    return datetime.now(timezone.utc).astimezone(ZoneInfo(tz_name)).year


def test_empty_ledger_offers_this_year(auth_client):
    auth_client.delete("/api/transactions/delete_all")
    r = auth_client.get("/api/reports/years")
    assert r.status_code == 200
    assert r.json() == {"ledger_years": [this_year()], "form_years": get_supported_years()}


def test_years_run_from_the_first_transaction_in_the_tax_timezone(auth_client):
    auth_client.delete("/api/transactions/delete_all")
    auth_client.put("/api/settings/tax-timezone", json={"timezone": "America/Chicago"})
    try:
        # 2023-01-01 03:00 UTC is still Dec 31, 2022 in Chicago.
        r = auth_client.post("/api/transactions", json=dict(
            type="Deposit", timestamp="2023-01-01T03:00:00Z", from_account_id=99, to_account_id=1,
            amount="100", source="N/A", fee_amount="0", fee_currency="USD"))
        assert r.status_code in (200, 201), r.text
        years = auth_client.get("/api/reports/years").json()["ledger_years"]
        assert years[0] == this_year("America/Chicago")
        assert years[-1] == 2022
        assert years == sorted(years, reverse=True)
        assert len(years) == len(set(years))
    finally:
        auth_client.delete("/api/transactions/delete_all")
        auth_client.put("/api/settings/tax-timezone", json={"timezone": "UTC"})


def test_form_years_are_the_templates_shipped(auth_client):
    assert {2024, 2025} <= set(auth_client.get("/api/reports/years").json()["form_years"])


def test_login_required(auth_client):
    assert TestClient(auth_client.app).get("/api/reports/years").status_code == 401
