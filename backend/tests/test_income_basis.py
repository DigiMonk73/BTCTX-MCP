"""
backend/tests/test_income_basis.py

A BTC deposit that is income (source Income, Interest or Reward) has a cost
basis equal to its market value at receipt, and that value is the income on
the tax report. Entered without a basis (blank, or the form's 0), it is valued
at the day's BTC price on every entry path, not saved at $0.
"""

import io
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.services.reports.reporting_core import generate_report_data

from backend.tests.conftest import STUB_HISTORICAL_USD

CLIENT: TestClient = None
WALLET, EXCHANGE_BTC, EXTERNAL = 2, 4, 99
AMOUNT = "0.00006404"
# 0.00006404 BTC at the stubbed $50,000 daily price
EXPECTED_BASIS = (Decimal(AMOUNT) * Decimal(str(STUB_HISTORICAL_USD))).quantize(Decimal("0.01"))


@pytest.fixture(autouse=True, scope="session")
def _set_client(auth_client):
    global CLIENT
    CLIENT = auth_client


@pytest.fixture(autouse=True)
def _clean_ledger():
    CLIENT.delete("/api/transactions/delete_all")
    yield
    CLIENT.delete("/api/transactions/delete_all")


def deposit(**fields):
    body = {
        "type": "Deposit", "timestamp": "2026-04-01T12:00:00Z",
        "from_account_id": EXTERNAL, "to_account_id": EXCHANGE_BTC,
        "amount": AMOUNT, "source": "Interest", **fields,
    }
    return CLIENT.post("/api/transactions", json=body)


def basis(tx) -> Decimal:
    return Decimal(str(tx["cost_basis_usd"] or 0))


@pytest.mark.parametrize("blank", [{}, {"cost_basis_usd": None}, {"cost_basis_usd": 0}])
def test_manual_income_deposit_without_basis_gets_market_value(blank):
    r = deposit(**blank)
    assert r.status_code == 200, r.text
    assert basis(r.json()) == EXPECTED_BASIS


@pytest.mark.parametrize("source", ["Income", "Interest", "Reward", "interest"])
def test_every_income_source_is_valued(source):
    assert basis(deposit(source=source).json()) == EXPECTED_BASIS


def test_entered_basis_is_kept():
    assert basis(deposit(cost_basis_usd="4.10").json()) == Decimal("4.10")


def test_non_income_deposit_keeps_zero_basis():
    # A gift or an unknown-origin deposit legitimately has no basis here.
    r = deposit(source="Gift", to_account_id=WALLET)
    assert r.status_code == 200, r.text
    assert basis(r.json()) == Decimal("0")


def test_income_is_reported_at_market_value(test_engine):
    deposit()
    db = sessionmaker(bind=test_engine)()
    try:
        report = generate_report_data(db, 2026)
    finally:
        db.close()
    assert Decimal(str(report["income_summary"]["Interest"])) == EXPECTED_BASIS


def test_price_lookup_failure_blocks_the_save(monkeypatch):
    async def unavailable(date: str):
        raise HTTPException(status_code=502, detail="price APIs down")

    monkeypatch.setattr("backend.services.bitcoin.get_historical_price", unavailable)
    r = deposit()
    assert r.status_code == 422
    assert "2026-04-01" in r.json()["detail"]
    assert CLIENT.get("/api/transactions").json() == []


def test_editing_an_income_deposit_with_zero_basis_values_it():
    # Saved at $0 by an older version; the edit form sends cost_basis_usd 0.
    tx = deposit(cost_basis_usd="0", source="Gift").json()
    r = CLIENT.put(f"/api/transactions/{tx['id']}", json={"source": "Interest", "cost_basis_usd": 0})
    assert r.status_code == 200, r.text
    assert basis(r.json()) == EXPECTED_BASIS


def test_editing_another_field_keeps_an_entered_basis():
    tx = deposit(cost_basis_usd="4.10").json()
    r = CLIENT.put(f"/api/transactions/{tx['id']}", json={"timestamp": "2026-04-02T12:00:00Z"})
    assert basis(r.json()) == Decimal("4.10")


def test_csv_import_values_income_deposit_without_basis():
    csv = (
        "date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,"
        "fee_amount,fee_currency,source,purpose,notes\n"
        f"2026-04-01T12:00:00Z,Deposit,{AMOUNT},External,Wallet,,,,,Interest,,\n"
    )
    r = CLIENT.post(
        "/api/import/execute",
        files={"file": ("import.csv", io.BytesIO(csv.encode()), "text/csv")},
    )
    assert r.status_code == 200, r.text
    [tx] = CLIENT.get("/api/transactions").json()
    assert basis(tx) == EXPECTED_BASIS


def test_csv_preview_says_income_deposit_will_be_valued():
    csv = (
        "date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,"
        "fee_amount,fee_currency,source,purpose,notes\n"
        f"2026-04-01T12:00:00Z,Deposit,{AMOUNT},External,Wallet,,,,,Interest,,\n"
    )
    r = CLIENT.post(
        "/api/import/preview",
        files={"file": ("import.csv", io.BytesIO(csv.encode()), "text/csv")},
    )
    assert r.status_code == 200, r.text
    [warning] = [w for w in r.json()["warnings"] if w["column"] == "cost_basis_usd"]
    assert "day's BTC price" in warning["message"]
    assert "$0" not in warning["message"]
