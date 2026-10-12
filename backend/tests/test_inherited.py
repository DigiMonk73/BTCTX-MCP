"""
backend/tests/test_inherited.py

Inherited bitcoin (#154): a Deposit with source Inherited. Its cost basis is
its value on the date of death (IRC §1014), typed or that day's price; the
date of death is its acquired_at, and required. Every disposal of these coins
is long-term however soon it comes (§1223(9)), with INHERITED in Form 8949
column (b) (Form 8949 instructions), and the rule follows the coins through
transfers. It is never income.
"""

import io
from datetime import date
from decimal import Decimal

import pytest
from pypdf import PdfReader
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from backend.services.reports.form_8949 import build_form_8949_and_schedule_d
from backend.services.reports.reporting_core import generate_report_data
from backend.services.transaction import INHERITED_NEEDS_DATE
from backend.tests.conftest import stub_daily_prices

CLIENT = None
ENGINE = None
BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 2, 3, 4, 99
# A different price each day, so the day a value was priced on shows
PRICES = {date(2025, 2, 28): 80000, date(2025, 3, 1): 81000, date(2025, 6, 1): 100000}


@pytest.fixture(autouse=True)
def _ledger(auth_client, test_engine, monkeypatch):
    global CLIENT, ENGINE
    CLIENT, ENGINE = auth_client, test_engine
    stub_daily_prices(monkeypatch, lambda day: PRICES.get(day, 90000))
    auth_client.delete("/api/transactions/delete_all")
    yield
    auth_client.delete("/api/transactions/delete_all")


def post(**data):
    return CLIENT.post("/api/transactions", json=data)


def tx(**data) -> dict:
    r = post(**data)
    assert r.status_code == 200, r.text
    return r.json()


def inherit(account=WALLET, day="2025-06-01", death="2025-02-28", amount="0.01", basis=None) -> dict:
    return tx(type="Deposit", timestamp=f"{day}T12:00:00Z", from_account_id=EXTERNAL, to_account_id=account,
              amount=amount, source="Inherited", acquired_at=death, cost_basis_usd=basis)


def sell(day, amount, gross="1000.00"):
    return tx(type="Sell", timestamp=f"{day}T12:00:00Z", from_account_id=EXCHANGE_BTC,
              to_account_id=EXCHANGE_USD, amount=amount, gross_proceeds_usd=gross)


def form_rows(year) -> list[dict]:
    with sessionmaker(bind=ENGINE)() as db:
        forms = build_form_8949_and_schedule_d(year, db)
    return forms["short_term"] + forms["long_term"]


def report(year) -> dict:
    with sessionmaker(bind=ENGINE)() as db:
        return generate_report_data(db, year)


def test_a_blank_value_is_the_price_on_the_date_of_death():
    deposit = inherit()
    # 0.01 BTC at the 2025-02-28 price ($80,000), not the deposit day's ($100,000)
    assert (deposit["cost_basis_usd"], deposit["cost_basis_from_price"]) == ("800.00", True)


def test_a_typed_value_is_kept():
    deposit = inherit(basis="950.00")
    assert (deposit["cost_basis_usd"], deposit["cost_basis_from_price"]) == ("950.00", False)


def test_the_date_of_death_is_required():
    r = post(type="Deposit", timestamp="2025-06-01T12:00:00Z", from_account_id=EXTERNAL, to_account_id=WALLET,
             amount="0.01", source="Inherited", cost_basis_usd="950.00")
    assert r.status_code == 422 and r.json()["detail"] == INHERITED_NEEDS_DATE
    # Dollars inherited are only dollars: no lot, no date needed
    assert post(type="Deposit", timestamp="2025-06-01T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
                amount="500.00", source="Inherited").status_code == 200


def test_an_edit_prices_it_again_only_when_the_date_of_death_moves():
    deposit = inherit()
    moved = CLIENT.put(f"/api/transactions/{deposit['id']}", json={"acquired_at": "2025-03-01"}).json()
    assert moved["cost_basis_usd"] == "810.00"
    # The deposit's own date isn't when it was valued
    later = CLIENT.put(f"/api/transactions/{deposit['id']}", json={"timestamp": "2025-07-01T12:00:00Z"}).json()
    assert later["cost_basis_usd"] == "810.00"
    r = CLIENT.put(f"/api/transactions/{deposit['id']}", json={"acquired_at": None})
    assert r.status_code == 422 and r.json()["detail"] == INHERITED_NEEDS_DATE


def test_a_sale_the_next_month_is_long_term_and_inherited_on_form_8949():
    inherit(account=EXCHANGE_BTC, day="2025-03-10", basis="800.00")
    sale = sell("2025-04-10", "0.01")

    assert sale["holding_period"] == "LONG"
    rows = form_rows(2025)
    assert [(r["box"], r["date_acquired"], r["holding_period"], r["cost"]) for r in rows] == [
        ("K", "INHERITED", "LONG", Decimal("800.00"))]  # a 1099-DA sale without basis, long-term


@pytest.mark.parametrize("year, box", [(2024, "F"), (2025, "L"), (2026, "L")])
def test_a_spend_from_the_wallet_is_part_ii_every_year(year, box):
    inherit(day=f"{year}-05-01", death=f"{year}-04-01", basis="900.00")
    tx(type="Withdrawal", timestamp=f"{year}-05-02T12:00:00Z", from_account_id=WALLET, to_account_id=EXTERNAL,
       amount="0.005", purpose="Spent", proceeds_usd="460.00")
    assert [(r["box"], r["date_acquired"]) for r in form_rows(year)] == [(box, "INHERITED")]


def test_the_rule_follows_the_coins_through_a_transfer_and_its_fee():
    inherit(death="2025-01-10", day="2025-02-01", basis="1000.00")
    tx(type="Transfer", timestamp="2025-03-01T12:00:00Z", from_account_id=WALLET, to_account_id=EXCHANGE_BTC,
       amount="0.01", fee_amount="0.0001", fee_currency="BTC", fee_usd="8.00")
    sell("2025-04-01", "0.0099", gross="990.00")

    rows = form_rows(2025)
    assert {(r["box"], r["date_acquired"], r["holding_period"]) for r in rows} == {
        ("L", "INHERITED", "LONG"),  # the fee, paid with inherited coins
        ("K", "INHERITED", "LONG"),  # the sale on the exchange
    }
    assert sum(r["cost"] for r in rows) == Decimal("1000.00")


def test_other_coins_keep_their_dates_and_first_in_first_out_uses_the_date_of_death():
    tx(type="Deposit", timestamp="2025-01-05T12:00:00Z", from_account_id=EXTERNAL, to_account_id=EXCHANGE_BTC,
       amount="0.01", source="MyBTC", cost_basis_usd="700.00")
    inherit(account=EXCHANGE_BTC, death="2024-12-01", day="2025-02-01", basis="960.00")
    sell("2025-03-01", "0.015", gross="1500.00")

    rows = sorted(form_rows(2025), key=lambda r: r["date_acquired"])
    # The inherited coins, dated 2024-12-01, go first; then half the My BTC, short-term
    assert [(r["date_acquired"], r["description"], r["holding_period"], r["box"]) for r in rows] == [
        ("01/05/2025", "0.00500000 BTC", "SHORT", "H"), ("INHERITED", "0.01000000 BTC", "LONG", "K")]


def test_it_is_never_income():
    inherit()
    summary = report(2025)["income_summary"]
    assert Decimal(str(summary["Total"])) == 0


def test_a_recalculation_gives_the_same_figures():
    inherit(account=EXCHANGE_BTC, day="2025-03-10")
    sale = sell("2025-04-10", "0.006")
    assert CLIENT.post("/api/transactions/recalculate").status_code == 200
    again = CLIENT.get(f"/api/transactions/{sale['id']}").json()
    assert (again["holding_period"], again["cost_basis_usd"]) == ("LONG", sale["cost_basis_usd"])


def test_the_complete_report_says_inherited_and_explains_it():
    inherit(account=EXCHANGE_BTC, day="2025-03-10", basis="800.00")
    sell("2025-04-10", "0.01")
    pdf = CLIENT.get("/api/reports/complete_tax_report", params={"year": 2025}).content
    words = " ".join("\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages).split())
    assert "INHERITED" in words
    assert "Inherited bitcoin (deposits with source Inherited) is long-term whenever it's sold" in words
    assert "Form 8971, Schedule A" in words


def test_a_year_without_inherited_sales_has_no_such_note():
    inherit()  # held, not sold
    pdf = CLIENT.get("/api/reports/complete_tax_report", params={"year": 2025}).content
    words = " ".join("\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages).split())
    assert "Inherited bitcoin (deposits" not in words


HEADER = "date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency,source," \
         "purpose,notes,fee_usd,fmv_usd,broker_reporting,fee_usd_typed,cost_basis_typed,acquired_at"


def csv_preview(*rows) -> dict:
    body = "\n".join((HEADER, *rows)) + "\n"
    return CLIENT.post("/api/import/preview", files={"file": ("l.csv", io.BytesIO(body.encode()), "text/csv")}).json()


def test_a_csv_row_needs_the_date_of_death_and_says_how_a_blank_value_is_priced():
    missing = csv_preview("2025-06-01T12:00:00Z,Deposit,0.01,External,Wallet,800.00,,,,Inherited,,,,,,,,")
    assert [(e["column"], e["message"]) for e in missing["errors"]] == [("acquired_at", INHERITED_NEEDS_DATE)]
    blank = csv_preview("2025-06-01T12:00:00Z,Deposit,0.01,External,Wallet,,,,,Inherited,,,,,,,,2025-02-28")
    assert blank["errors"] == []
    assert "valued at the BTC price on the date of death" in blank["warnings"][0]["message"]


def test_a_csv_round_trip_keeps_it():
    inherit(account=EXCHANGE_BTC, day="2025-03-10")
    sell("2025-04-10", "0.01")
    before = form_rows(2025)
    exported = CLIENT.get("/api/backup/csv").text
    CLIENT.delete("/api/transactions/delete_all")
    r = CLIENT.post("/api/import/execute", files={"file": ("l.csv", io.BytesIO(exported.encode()), "text/csv")})
    assert r.status_code == 200, r.text
    deposit = next(t for t in CLIENT.get("/api/transactions").json() if t["type"] == "Deposit")
    assert (deposit["source"], deposit["cost_basis_usd"], deposit["cost_basis_from_price"]) == (
        "Inherited", "800.00", True)
    assert form_rows(2025) == before


def test_the_ai_import_values_it_on_the_date_of_death():
    row = {"date": "2025-06-01T12:00:00Z", "type": "Deposit", "amount": "0.01", "from_account": "External",
           "to_account": "Wallet", "source": "Inherited", "acquired_at": "2025-02-28"}
    preview = CLIENT.post("/api/import/entries/preview", json={"rows": [row]}).json()
    result = preview["results"][0]
    assert result["status"] == "ready", preview
    assert result["autofilled_fields"] == ["cost_basis_usd"]
    assert result["simulated"]["cost_basis_usd"] == "800.00"
    no_date = dict(row, acquired_at=None)
    result = CLIENT.post("/api/import/entries/preview", json={"rows": [no_date]}).json()["results"][0]
    assert result["status"] == "invalid" and INHERITED_NEEDS_DATE in result["errors"]


def test_ledger_review_doesnt_compare_an_estates_value_with_the_days_price():
    inherit(basis="2000.00")  # the estate's value, far from the day's $800
    review = CLIENT.get("/api/review").json()
    for key in ("income_value_off", "income_without_value", "deposit_without_basis"):
        assert next(c for c in review["checks"] if c["key"] == key)["items"] == [], key


def test_a_deposit_saved_before_1_1_0_as_inherited_follows_the_rules():
    """Before v1.1.0 a deposit's source was free text: one typed "inherited"
    (no date of death then) is now inherited coins: long-term when sold."""
    with ENGINE.begin() as con:
        con.execute(text(
            "INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount, fee_amount,"
            " fee_currency, source, cost_basis_usd) VALUES (970, 'Deposit', '2025-03-10T12:00:00Z', :e, :x, '0.01',"
            " '0', 'BTC', 'inherited', '800.00')"), {"e": EXTERNAL, "x": EXCHANGE_BTC})
    assert CLIENT.post("/api/transactions/recalculate").status_code == 200  # as at the first start after it
    sale = sell("2025-04-10", "0.01")
    assert sale["holding_period"] == "LONG"
    assert [(r["box"], r["date_acquired"]) for r in form_rows(2025)] == [("K", "INHERITED")]
