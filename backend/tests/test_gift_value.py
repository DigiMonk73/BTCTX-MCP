"""
A gift's, donation's or lost coins' value left blank is filled from the price
when it's saved (#255), like an income deposit's value and a Spent's
proceeds: the BTC price when its hour began (that day's where there's no
hourly price) x the amount, marked fmv_from_price. A typed value, $0
included, is kept. With no price it stays blank (never a 422: BitcoinTX
fills no form with it). An edit prices a value from the price again when its amount
or hour changes; the form sending it back isn't typing it. Ledger Review
lists the ones with no value; its day-priced check, the tax report's list
of priced values, the CSV round trip and the AI connector know the mark.
"""

import csv
import io
from decimal import Decimal

import pytest
from fastapi import HTTPException

from backend.services import hourly_prices
from backend.tests.conftest import stub_prices_at

BANK, WALLET, EXCHANGE_BTC, EXTERNAL = 1, 2, 4, 99
D = Decimal


def price_of(when) -> Decimal:
    """Each hour its own price, so a value priced at another hour shows."""
    return D(60000 + (hourly_prices.hour_of(when) // 3600) % 1000)


def value(when: str, amount: str) -> str:
    from datetime import datetime
    moment = datetime.fromisoformat(when.replace("Z", "+00:00"))
    return str((price_of(moment) * D(amount)).quantize(D("0.01")))


@pytest.fixture(autouse=True)
def _ledger(auth_client, monkeypatch):
    stub_prices_at(monkeypatch, price_of)
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    r = auth_client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2026-01-02T10:00:00Z", "from_account_id": EXTERNAL,
        "to_account_id": WALLET, "amount": "1", "fee_amount": "0", "fee_currency": "BTC",
        "source": "MyBTC", "cost_basis_usd": "30000",
    })
    assert r.status_code == 200, r.text
    yield
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def gift(client, purpose="Gift", **fields) -> dict:
    body = {"type": "Withdrawal", "timestamp": "2026-05-01T12:34:00Z", "from_account_id": WALLET,
            "to_account_id": EXTERNAL, "amount": "0.005", "fee_amount": "0", "fee_currency": "BTC",
            "purpose": purpose, **fields}
    r = client.post("/api/transactions", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def edit(client, tx: dict, **changes) -> dict:
    """The form's PUT: the saved fields (the value as it shows it) with the changes."""
    keys = ("type", "timestamp", "from_account_id", "to_account_id", "amount", "fee_amount", "fee_currency",
            "purpose", "fmv_usd")
    r = client.put(f"/api/transactions/{tx['id']}", json={k: tx[k] for k in keys} | changes)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("purpose", ["Gift", "Donation", "Lost"])
def test_a_blank_value_is_the_price_when_its_hour_began(auth_client, purpose):
    tx = gift(auth_client, purpose)
    assert tx["fmv_usd"] == value("2026-05-01T12:00:00Z", "0.005")
    assert tx["fmv_from_price"] is True and tx["price_moment"] == "hour"
    assert tx["price_used"] is None or tx["price_used"]["moment"] == "hour"


def test_a_typed_value_is_kept_even_0(auth_client):
    typed = gift(auth_client, fmv_usd="391.05")
    assert typed["fmv_usd"] == "391.05" and typed["fmv_from_price"] is False and typed["price_moment"] is None
    zero = gift(auth_client, "Lost", fmv_usd="0")
    assert D(zero["fmv_usd"]) == 0 and zero["fmv_from_price"] is False


def test_without_a_price_it_stays_blank(auth_client, monkeypatch):
    def no_price(db, when):
        raise HTTPException(status_code=422, detail="No BTC price is stored for that day.")

    monkeypatch.setattr(hourly_prices, "price_at", no_price)
    tx = gift(auth_client, "Donation")
    assert tx["fmv_usd"] is None and tx["fmv_from_price"] is False and tx["price_moment"] is None


def test_without_an_hourly_price_it_is_the_days(auth_client, monkeypatch):
    stub_prices_at(monkeypatch, price_of, moment="day")
    assert gift(auth_client)["price_moment"] == "day"


def test_an_edit_prices_it_again_only_when_its_amount_or_hour_changes(auth_client):
    tx = gift(auth_client)
    kept = edit(auth_client, tx, purpose="Donation")  # the value sent back, a gift-like purpose
    assert kept["fmv_usd"] == tx["fmv_usd"] and kept["fmv_from_price"] is True
    moved = edit(auth_client, kept, timestamp="2026-05-01T15:10:00Z")
    assert moved["fmv_usd"] == value("2026-05-01T15:00:00Z", "0.005") and moved["fmv_from_price"] is True
    more = edit(auth_client, moved, amount="0.006")
    assert more["fmv_usd"] == value("2026-05-01T15:00:00Z", "0.006")


def test_a_typed_value_wins_and_stays(auth_client):
    tx = gift(auth_client)
    typed = edit(auth_client, tx, fmv_usd="300.00")
    assert typed["fmv_usd"] == "300.00" and typed["fmv_from_price"] is False
    later = edit(auth_client, typed, timestamp="2026-05-02T09:00:00Z")
    assert later["fmv_usd"] == "300.00" and later["fmv_from_price"] is False


def test_cleared_it_is_priced_again_and_a_sale_drops_the_mark(auth_client):
    typed = gift(auth_client, fmv_usd="300.00")
    cleared = edit(auth_client, typed, fmv_usd=None)
    assert cleared["fmv_usd"] == value("2026-05-01T12:00:00Z", "0.005") and cleared["fmv_from_price"] is True
    spent = edit(auth_client, cleared, purpose="Spent", proceeds_usd=None)
    assert spent["fmv_from_price"] is False


def test_an_old_blank_gift_is_valued_when_saved_again(auth_client, test_db):
    from backend.models.transaction import Transaction
    tx = gift(auth_client, fmv_usd="100.00")
    row = test_db.get(Transaction, tx["id"])
    row.fmv_usd = None  # as 1.2.8 saved a blank one
    test_db.commit()
    again = edit(auth_client, auth_client.get(f"/api/transactions/{tx['id']}").json(), fmv_usd=None)
    assert again["fmv_usd"] == value("2026-05-01T12:00:00Z", "0.005") and again["fmv_from_price"] is True


def blank_in_the_database(test_db, tx: dict, **fields) -> None:
    """The row as 1.2.8 left it: its value blank (or another field set), its marks unchanged."""
    from backend.models.transaction import Transaction
    row = test_db.get(Transaction, tx["id"])
    row.fmv_usd = None
    for key, stored in fields.items():
        setattr(row, key, stored)
    test_db.commit()


def test_a_value_left_blank_is_filled_by_any_edit(auth_client, test_db):
    """The AI's update_transaction sends only what changes: a blank value is filled all the same."""
    tx = gift(auth_client, fmv_usd="100.00")
    blank_in_the_database(test_db, tx)
    r = auth_client.put(f"/api/transactions/{tx['id']}", json={"amount": "0.004"})
    assert r.status_code == 200, r.text
    assert r.json()["fmv_usd"] == value("2026-05-01T12:00:00Z", "0.004") and r.json()["fmv_from_price"] is True


def test_a_spend_made_a_gift_is_valued(auth_client, test_db):
    """Its $0 or blank value (forms before #255 saved $0 for every withdrawal)
    is filled when no value is sent, or the form's blank (it shows a sale's $0
    blank: transactionForm.test.ts)."""
    for stored in (None, D(0)):
        spend = gift(auth_client, "Spent", proceeds_usd="300.00")
        blank_in_the_database(test_db, spend, fmv_usd=stored)
        r = auth_client.put(f"/api/transactions/{spend['id']}", json={"purpose": "Gift"})
        assert r.status_code == 200, r.text
        assert r.json()["fmv_usd"] == value("2026-05-01T12:00:00Z", "0.005") and r.json()["fmv_from_price"] is True
        echoed = gift(auth_client, "Spent", proceeds_usd="300.00")
        blank_in_the_database(test_db, echoed, fmv_usd=stored)
        stored_row = auth_client.get(f"/api/transactions/{echoed['id']}").json()
        again = edit(auth_client, stored_row, purpose="Donation", fmv_usd=None)
        assert again["fmv_usd"] == value("2026-05-01T12:00:00Z", "0.005") and again["fmv_from_price"] is True


def test_a_0_sent_while_making_a_spend_a_gift_is_kept(auth_client, test_db):
    """A $0 sent is the value wanted (the form and the AI's update_transaction
    send a blank one blank), whether the sale's value was blank or $0."""
    for stored in (None, D(0)):
        spend = gift(auth_client, "Spent", proceeds_usd="300.00")
        blank_in_the_database(test_db, spend, fmv_usd=stored)
        for purpose in ("Gift", "Lost"):
            r = auth_client.put(f"/api/transactions/{spend['id']}", json={"purpose": purpose, "fmv_usd": "0"})
            assert r.status_code == 200, r.text
            assert D(r.json()["fmv_usd"]) == 0 and r.json()["fmv_from_price"] is False, (stored, purpose)


def test_a_value_priced_now_beside_a_fee_at_the_days_price_takes_the_days_too(auth_client, test_db, monkeypatch):
    """One price per transaction: the fee keeps its day price, so the value
    filled takes it as well, and Ledger Review offers both at the hour."""
    stub_prices_at(monkeypatch, lambda when: D(50000), moment="day")
    typed = gift(auth_client, fee_amount="0.0001", fmv_usd="100.00")
    old_blank = gift(auth_client, "Lost", fee_amount="0.0001", fmv_usd="100.00")
    blank_in_the_database(test_db, old_blank)
    spend = gift(auth_client, "Spent", fee_amount="0.0001", proceeds_usd="300.00")
    blank_in_the_database(test_db, spend)
    assert {tx["price_moment"] for tx in (typed, old_blank, spend)} == {"day"}
    stub_prices_at(monkeypatch, price_of)  # hourly prices now
    for tx, changes in ((typed, {"fmv_usd": None}), (old_blank, {}), (spend, {"purpose": "Gift"})):
        stored = auth_client.get(f"/api/transactions/{tx['id']}").json()
        after = edit(auth_client, stored, **changes)
        assert after["fmv_usd"] == "250.00" and after["fmv_from_price"] is True, tx["purpose"]
        assert after["fee_usd"] == "5.00" and after["price_moment"] == "day", tx["purpose"]


def test_ledger_review_lists_gifts_with_no_value(auth_client, test_db):
    from backend.models.transaction import Transaction
    blank = gift(auth_client, fmv_usd="100.00")
    row = test_db.get(Transaction, blank["id"])
    row.fmv_usd = None
    test_db.commit()
    zero = gift(auth_client, "Lost", fmv_usd="0")
    gift(auth_client)  # valued: not listed
    check = next(c for c in auth_client.get("/api/review").json()["checks"] if c["key"] == "gift_without_value")
    assert [i["id"] for i in check["items"]] == [blank["id"], zero["id"]]
    assert "not given" in check["items"][0]["issue"]
    # At the stored price Ledger Review reads (the tests' day price, $50,000)
    assert check["items"][0]["change"] == "Value blank -> $250.00 if you clear it."
    assert check["items"][1]["change"] == "Value $0.00 -> $250.00 if you clear it."


def test_a_day_priced_value_is_offered_at_the_hour(auth_client, monkeypatch):
    stub_prices_at(monkeypatch, price_of, moment="day")
    tx = gift(auth_client)
    assert tx["price_moment"] == "day"
    stub_prices_at(monkeypatch, price_of)
    from backend.services.hourly_review import _priced_values
    from backend.models.transaction import Transaction
    from backend.database import get_db
    from backend.main import app
    db = next(app.dependency_overrides[get_db]())
    assert [f for f, _, _ in _priced_values(db.get(Transaction, tx["id"]))] == ["fmv_usd"]
    db.close()
    # Its tax year's totals name what moves (Settings, cli review, the AI's review_ledger)
    from backend.services.review import year_line
    found = next(c for c in auth_client.get("/api/review").json()["checks"] if c["key"] == "day_priced_values")
    [year] = found["years"]
    assert D(year["gift_values"]) != 0 and "; totals: gift values " in year_line(year)


def test_the_tax_report_lists_the_value_with_its_price(auth_client):
    gift(auth_client)
    from backend.database import get_db
    from backend.main import app
    from backend.models.transaction import Transaction
    from backend.services.reports.reporting_core import _priced_values
    from backend.services.tax_time import get_tax_timezone
    db = next(app.dependency_overrides[get_db]())
    t = db.query(Transaction).filter(Transaction.type == "Withdrawal").one()
    [(what, usd, which)] = list(_priced_values(t, get_tax_timezone(db)))
    assert what == "Value (fair market value)" and str(usd) == value("2026-05-01T12:00:00Z", "0.005")
    assert which.startswith("When its hour began")
    db.close()


def test_the_csv_round_trip_keeps_the_mark(auth_client):
    priced = gift(auth_client)
    gift(auth_client, "Donation", fmv_usd="50.00")
    text = auth_client.get("/api/backup/csv").text
    rows = [r for r in csv.DictReader(io.StringIO(text)) if r["type"] == "Withdrawal"]
    assert [(r["fmv_usd"], r["fmv_typed"]) for r in rows] == [(priced["fmv_usd"], "no"), ("50.00", "yes")]

    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    r = auth_client.post("/api/import/execute", files={"file": ("ledger.csv", text.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    back = [t for t in auth_client.get("/api/transactions").json() if t["type"] == "Withdrawal"]
    assert sorted((t["fmv_usd"], t["fmv_from_price"]) for t in back) == sorted(
        [(priced["fmv_usd"], True), ("50.00", False)])


def test_the_ai_connector_fills_and_marks_a_lost_value_too(auth_client, ai_key_headers):
    from fastapi.testclient import TestClient
    from backend.main import app
    row = {"type": "Withdrawal", "date": "2026-05-01T12:34:00Z", "from_account": "Wallet",
           "to_account": "External", "amount": "0.004", "purpose": "Lost"}
    key = TestClient(app)
    r = key.post("/api/import/entries/preview", json={"rows": [row]}, headers=ai_key_headers)
    assert r.status_code == 200, r.text
    [preview] = r.json()["results"]
    assert "fmv_usd" in preview["autofilled_fields"]
    r = key.post("/api/import/entries/execute", json={"rows": [row]}, headers=ai_key_headers)
    assert r.status_code == 200, r.text
    [lost] = [t for t in auth_client.get("/api/transactions").json() if t["type"] == "Withdrawal"]
    assert lost["fmv_usd"] == value("2026-05-01T12:00:00Z", "0.004") and lost["fmv_from_price"] is True
