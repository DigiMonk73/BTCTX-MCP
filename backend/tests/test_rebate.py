"""
The Rebate deposit source (#98): bitcoin back for spending, such as a
rewards card's sats-back. It is generally treated like a rebate on the
purchase price, not income (by analogy with Rev. Rul. 76-96), so it is valued like income (left blank,
that day's price x the amount is its cost basis) but never counted as
income: not on the report, the dashboard or the Transaction History. The
report lists rebates on their own. Reward stays income (mining, staking,
bonuses). BitcoinTX counted card sats-back entered as Reward as income, and
the AI guide suggested Reward for it.
"""

import csv
import io
from datetime import date
from decimal import Decimal

import pytest
from pypdf import PdfReader
from sqlalchemy.orm import sessionmaker

from backend.services.reports.complete_tax_report import generate_comprehensive_tax_report
from backend.services.reports.reporting_core import generate_report_data
from backend.tests.conftest import stub_daily_prices

WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 2, 3, 4, 99
APRIL_1 = date(2026, 4, 1)


@pytest.fixture(autouse=True)
def _ledger(auth_client, monkeypatch):
    """An empty ledger; $50,000 on April 1, $40,000 any other day."""
    stub_daily_prices(monkeypatch, lambda day: 50000 if day == APRIL_1 else 40000)
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def deposit(client, **fields) -> dict:
    body = {"type": "Deposit", "timestamp": "2026-04-01T12:00:00Z", "from_account_id": EXTERNAL,
            "to_account_id": WALLET, "amount": "0.001", "fee_amount": "0", "fee_currency": "BTC",
            "source": "Rebate", **fields}
    r = client.post("/api/transactions", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def basis(tx: dict) -> Decimal:
    return Decimal(str(tx["cost_basis_usd"] or 0))


def report(test_engine, year=2026) -> dict:
    with sessionmaker(bind=test_engine)() as db:
        return generate_report_data(db, year)


def test_a_blank_rebate_is_valued_at_that_days_price(auth_client):
    tx = deposit(auth_client)
    assert tx["source"] == "Rebate"
    assert basis(tx) == Decimal("50.00") and tx["cost_basis_from_price"] is True


def test_a_rebate_is_never_income(auth_client, test_engine):
    deposit(auth_client)
    data = report(test_engine)
    assert data["income_summary"]["Total"] == 0 and data["income_transactions"] == []
    assert data["rebates"] == [{"date": "2026-04-01T12:00:00+00:00", "amount": 0.001, "value_usd": 50.0}]
    dashboard = auth_client.get("/api/calculations/gains-and-losses").json()
    assert dashboard["total_income"] == 0 and dashboard["rewards_earned"] == 0
    history = auth_client.get("/api/reports/simple_transaction_history", params={"year": 2026, "format": "csv"})
    [row] = list(csv.DictReader(io.StringIO(history.text)))
    assert row["type"] == "Rebate"


def test_the_dashboard_shows_rebates_apart_from_income(auth_client):
    """#129: the dashboard's Income & Fees card showed rebates nowhere. They
    have their own line, beside the gifts, never in Total Income."""
    deposit(auth_client)
    dashboard = auth_client.get("/api/calculations/gains-and-losses").json()
    assert dashboard["rebates_received"] == 50.0 and dashboard["rebates_btc"] == 0.001
    assert dashboard["total_income"] == 0 and dashboard["gifts_received"] == 0


def test_reward_stays_income(auth_client, test_engine):
    deposit(auth_client, source="Reward")
    assert report(test_engine)["income_summary"]["Reward"] == 50.0
    assert auth_client.get("/api/calculations/gains-and-losses").json()["total_income"] == 50.0


def test_the_report_lists_rebates_on_their_own(auth_client, test_engine):
    deposit(auth_client)
    pdf = generate_comprehensive_tax_report(report(test_engine))
    text = " ".join(" ".join(p.extract_text().split()) for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "No income in 2026." in text
    assert "Rebates (not income)" in text and "Rev. Rul. 76-96" in text
    assert "04/01/2026 0.00100000 $50.00 Total 0.00100000 $50.00" in text
    # "Using these forms" tells the preparer (#79)
    assert "Rebates (bitcoin back for spending, listed in section 3) aren't counted as income" in text


def test_a_later_sale_uses_the_rebates_value_as_its_basis(auth_client):
    deposit(auth_client, to_account_id=EXCHANGE_BTC)
    r = auth_client.post("/api/transactions", json={
        "type": "Sell", "timestamp": "2026-05-01T12:00:00Z", "from_account_id": EXCHANGE_BTC,
        "to_account_id": EXCHANGE_USD, "amount": "0.001", "proceeds_usd": "60", "fee_amount": "0",
        "fee_currency": "USD"})
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["realized_gain_usd"])) == Decimal("10.00")  # $60 - the $50 basis


def test_reward_to_rebate_keeps_the_value_and_drops_the_income(auth_client, test_engine):
    """Fixing a card reward entered as Reward: the source change prices the
    same day and amount again, so the basis stays; the income goes."""
    tx = deposit(auth_client, source="Reward")
    r = auth_client.put(f"/api/transactions/{tx['id']}", json={"source": "Rebate"})
    assert r.status_code == 200, r.text
    assert basis(r.json()) == Decimal("50.00")
    assert report(test_engine)["income_summary"]["Total"] == 0


def test_a_typed_rebate_value_is_kept(auth_client):
    tx = deposit(auth_client, cost_basis_usd="45")
    assert basis(tx) == Decimal("45.00") and tx["cost_basis_from_price"] is False


def test_the_csv_import_and_export_take_rebate(auth_client):
    body = ("date,type,amount,from_account,to_account,source,fee_amount,fee_currency\n"
            "2026-04-01T12:00:00Z,Deposit,0.001,External,Wallet,Rebate,0,BTC\n")
    preview = auth_client.post("/api/import/preview", files={"file": ("x.csv", io.BytesIO(body.encode()), "text/csv")})
    assert preview.status_code == 200, preview.text
    assert "a rebate, not income" in preview.text
    r = auth_client.post("/api/import/execute", files={"file": ("x.csv", io.BytesIO(body.encode()), "text/csv")})
    assert r.status_code == 200, r.text
    [tx] = auth_client.get("/api/transactions").json()
    assert tx["source"] == "Rebate" and basis(tx) == Decimal("50.00") and tx["cost_basis_from_price"] is True
    [row] = list(csv.DictReader(io.StringIO(auth_client.get("/api/backup/csv").text)))
    assert row["source"] == "Rebate" and row["cost_basis_typed"] == "no"


def test_the_ai_connectors_import_takes_rebate(auth_client):
    row = {"date": "2026-04-01T12:00:00Z", "type": "Deposit", "amount": "0.001", "from_account": "External",
           "to_account": "Wallet", "source": "Rebate", "fee_amount": "0", "fee_currency": "BTC"}
    r = auth_client.post("/api/import/entries/execute", json={"rows": [row]})
    assert r.status_code == 200, r.text
    [tx] = auth_client.get("/api/transactions").json()
    assert tx["source"] == "Rebate" and basis(tx) == Decimal("50.00") and tx["cost_basis_from_price"] is True


def test_ledger_review_checks_a_rebates_value_not_its_income(auth_client, test_engine):
    """A $0 rebate is listed like a $0 income deposit, worded for a rebate,
    and not also as a deposit without basis."""
    from sqlalchemy import text

    tx = deposit(auth_client)
    with test_engine.begin() as con:
        con.execute(text("UPDATE transactions SET cost_basis_usd = '0' WHERE id = :id"), {"id": tx["id"]})
    review = auth_client.get("/api/review").json()
    by_key = {c["key"]: c for c in review["checks"]}
    [item] = by_key["income_without_value"]["items"]
    assert "its whole value becomes gain when it's sold" in item["issue"] and "income" not in item["issue"]
    assert item["change"] == "Basis $0.00 -> $50.00 if you clear it."
    assert by_key["deposit_without_basis"]["items"] == []


def test_reward_to_rebate_needs_no_price(auth_client, test_engine, monkeypatch):
    """Review of #111: a switch between two sources valued at receipt can't
    change the value, so it isn't priced again; the fix users are told to
    make works with no price stored or reachable (a CSV re-import into an
    install whose price source is Off)."""
    from sqlalchemy import text

    tx = deposit(auth_client, source="Reward")
    with test_engine.begin() as con:
        con.execute(text("DELETE FROM btc_price_daily"))
    stub_daily_prices(monkeypatch, lambda day: None)
    r = auth_client.put(f"/api/transactions/{tx['id']}", json={"source": "Rebate"})
    assert r.status_code == 200, r.text
    assert basis(r.json()) == Decimal("50.00") and r.json()["cost_basis_from_price"] is True
    full = {k: r.json()[k] for k in ("type", "timestamp", "from_account_id", "to_account_id", "amount",
                                     "fee_amount", "fee_currency", "cost_basis_usd")} | {"source": "Reward"}
    back = auth_client.put(f"/api/transactions/{tx['id']}", json=full)  # the form's PUT
    assert back.status_code == 200, back.text
    assert basis(back.json()) == Decimal("50.00")


def test_the_rebates_table_dates_are_in_the_tax_timezone(auth_client, test_engine):
    """03:00 UTC on January 1 is still December 31 in Chicago: the rebate is
    in that tax year, and its date prints so."""
    assert auth_client.put("/api/settings/tax-timezone", json={"timezone": "America/Chicago"}).status_code == 200
    try:
        deposit(auth_client, timestamp="2026-01-01T03:00:00Z")
        data = report(test_engine, 2025)
        assert [r["value_usd"] for r in data["rebates"]] == [40.0]
        pdf = generate_comprehensive_tax_report(data)
        text = " ".join(" ".join(p.extract_text().split()) for p in PdfReader(io.BytesIO(pdf)).pages)
        assert "12/31/2025 0.00100000 $40.00" in text
        assert report(test_engine, 2026)["rebates"] == []
    finally:
        auth_client.put("/api/settings/tax-timezone", json={"timezone": "UTC"})


def test_a_rebate_moved_to_bank_is_not_listed(auth_client, test_engine):
    tx = deposit(auth_client)
    r = auth_client.put(f"/api/transactions/{tx['id']}", json={
        "to_account_id": 1, "amount": "100", "fee_currency": "USD"})
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "Rebate" and report(test_engine)["rebates"] == []


def test_the_ai_connectors_preview_values_a_rebate(auth_client):
    row = {"date": "2026-04-01T12:00:00Z", "type": "Deposit", "amount": "0.001", "from_account": "External",
           "to_account": "Wallet", "source": "Rebate"}
    r = auth_client.post("/api/import/entries/preview", json={"rows": [row]})
    assert r.status_code == 200, r.text
    [res] = r.json()["results"]
    assert res["autofilled_fields"] == ["cost_basis_usd"]
    assert Decimal(res["normalized"]["cost_basis_usd"]) == Decimal("50.00")
