"""
Each transaction says which stored price its filled-in values came from
(#145, plan 4.5): `price_used` {at, moment, source, usd_per_btc}, read from
this install's table and files at display time, never asked for. A typed
value has none.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from backend.models.btc_price import BtcPriceHourly
from backend.services import hourly_prices, price_history
from backend.services import price_files as pf
from backend.tests.conftest import STUB_HISTORICAL_USD

WALLET, EXCHANGE_BTC, EXTERNAL = 2, 4, 99
HOUR = "2026-04-01T12:00:00Z"


def deposit(client, **fields) -> dict:
    r = client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2026-04-01T12:34:56Z", "from_account_id": EXTERNAL,
        "to_account_id": WALLET, "amount": "0.1", "fee_amount": "0", "fee_currency": "BTC",
        "source": "Income", **fields})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_value_priced_at_the_hour_names_its_hour_and_source(auth_client, test_engine):
    auth_client.delete("/api/transactions/delete_all")
    with sessionmaker(bind=test_engine)() as db:
        hour = hourly_prices.hour_of(datetime(2026, 4, 1, 12, tzinfo=timezone.utc))
        db.add(BtcPriceHourly(hour=hour, usd=Decimal("68123.45"), source="mempool"))
        db.commit()
    tx = deposit(auth_client)
    assert tx["price_moment"] == "hour" and tx["cost_basis_usd"] == "6812.34"
    expected = {"at": HOUR, "moment": "hour", "source": "mempool", "usd_per_btc": "68123.45"}
    assert tx["price_used"] == expected
    assert auth_client.get(f"/api/transactions/{tx['id']}").json()["price_used"] == expected
    listed = next(t for t in auth_client.get("/api/transactions").json() if t["id"] == tx["id"])
    assert listed["price_used"] == expected
    with test_engine.begin() as conn:
        conn.execute(text("DELETE FROM btc_price_hourly WHERE hour = :h"), {"h": hour})


def test_a_value_priced_at_the_day_says_so(auth_client):
    auth_client.delete("/api/transactions/delete_all")
    tx = deposit(auth_client)  # no hourly price here: the day's (the session stub's)
    assert tx["price_moment"] == "day"
    assert tx["price_used"] == {"at": "2026-04-01T00:00:00Z", "moment": "day", "source": "stub",
                                "usd_per_btc": f"{STUB_HISTORICAL_USD:.2f}"}


def test_a_typed_value_has_none_and_reading_asks_nobody(auth_client, monkeypatch):
    auth_client.delete("/api/transactions/delete_all")
    tx = deposit(auth_client, cost_basis_usd="7000")
    assert tx["price_used"] is None
    priced = deposit(auth_client, timestamp="2026-04-02T08:00:00Z")

    def asked(*args, **kwargs):  # review of #190: any lookup here would be a request
        raise AssertionError("reading transactions looked a price up")

    for name in ("find_hours", "start_download", "hourly_price", "price_at"):
        monkeypatch.setattr(hourly_prices, name, asked)
    monkeypatch.setattr(price_history, "daily_price", asked)
    monkeypatch.setattr(price_history, "find_prices", asked)
    ids = {t["id"] for t in auth_client.get("/api/transactions").json()}
    assert ids == {tx["id"], priced["id"]}
    assert auth_client.get(f"/api/transactions/{priced['id']}").json()["price_used"]["moment"] == "day"


def test_a_value_the_stored_price_didnt_give_names_no_price(auth_client, test_engine):
    """Review of #190: an imported value marked "from the price", or one priced on
    another day (a tax timezone changed since), isn't that price times the amount."""
    auth_client.delete("/api/transactions/delete_all")
    tx = deposit(auth_client)
    with test_engine.begin() as conn:
        conn.execute(text("UPDATE transactions SET cost_basis_usd = 4321.00 WHERE id = :i"), {"i": tx["id"]})
    assert auth_client.get(f"/api/transactions/{tx['id']}").json()["price_used"] is None


def test_an_hour_from_the_year_files_names_bitstamp(auth_client, monkeypatch):
    """The year files' hours (Bitstamp's hourly opens): read once per list."""
    auth_client.delete("/api/transactions/delete_all")
    hour = hourly_prices.hour_of(datetime(2026, 4, 1, 12, tzinfo=timezone.utc))
    line = pf.YearLine(2026, pf.year_start(2026), hour + 3600, 1, "x")
    reads = []
    monkeypatch.setattr(pf, "read_manifest", lambda path=None: reads.append(1) or [line])
    monkeypatch.setattr(hourly_prices, "_year_prices", lambda y: {hour: Decimal("70000.00")})
    monkeypatch.setattr(hourly_prices, "hourly_price", lambda db, when, **k: (Decimal("70000.00"), "bitstamp"))
    tx = deposit(auth_client)
    assert tx["price_used"] == {"at": HOUR, "moment": "hour", "source": "bitstamp", "usd_per_btc": "70000.00"}
    deposit(auth_client, timestamp="2026-04-01T12:10:00Z")
    reads.clear()
    assert all(t["price_used"]["source"] == "bitstamp" for t in auth_client.get("/api/transactions").json())
    assert len(reads) == 1  # one manifest read for the whole list


def test_an_inheritance_names_its_date_of_deaths_day(auth_client):
    """#154/#177: an inheritance is valued on the date of death as entered, its day's price."""
    auth_client.delete("/api/transactions/delete_all")
    tx = deposit(auth_client, source="Inherited", acquired_at="2025-06-10T12:00:00Z")
    assert tx["price_moment"] == "day"
    assert tx["price_used"]["at"] == "2025-06-10T00:00:00Z" and tx["price_used"]["moment"] == "day"
