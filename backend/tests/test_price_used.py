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
from backend.services import hourly_prices, outbound
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
    asked = []
    monkeypatch.setattr(hourly_prices, "find_hours", lambda *a: asked.append(a))
    monkeypatch.setattr(outbound, "_transport", None)
    deposit_priced = deposit(auth_client, timestamp="2026-04-02T08:00:00Z")
    asked.clear()
    for t in auth_client.get("/api/transactions").json():  # reading never looks a price up
        assert t["id"] in (tx["id"], deposit_priced["id"])
    assert asked == []
