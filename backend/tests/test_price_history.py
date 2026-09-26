"""
The local BTC price history and stored fee values (hardening F14, F42, P1;
docs/HARDENING_FINDINGS.md):

- one bulk download fills a range of days; later lookups don't touch the
  network;
- a candle for another day is never used as the asked day's price (Kraken
  only returns its latest 720 days);
- nothing falls back to today's live price: no price is a clear 422;
- a BTC fee's USD value is stored at save, kept across recalculations with
  the network down, and a typed value sticks.
"""

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

import backend.services.price_history as price_history
from backend.services import outbound

# The real functions, captured before the session fixture stubs them.
from backend.services.bitcoin import get_historical_price as real_single_day
from backend.services.price_history import fetch_range as real_fetch_range

BANK, WALLET, EXCH_BTC, EXTERNAL = 1, 2, 4, 99
D = Decimal


def candles(start: date, days: int, price=lambda d: 20000 + d.toordinal() % 1000):
    return [(start + timedelta(days=i), price(start + timedelta(days=i))) for i in range(days)]


def midnight(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


class FakeSources:
    """Bitstamp/Coinbase/Kraken/CoinGecko answering from a table of days."""

    def __init__(self, bitstamp=None, coinbase=None, kraken=None, coingecko=None):
        self.bitstamp, self.coinbase, self.kraken, self.coingecko = bitstamp, coinbase, kraken, coingecko
        self.requests = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request.url.host)
        host, params = request.url.host, request.url.params
        if "bitstamp" in host and self.bitstamp is not None:
            start = datetime.fromtimestamp(int(params["start"]), tz=timezone.utc).date()
            rows = [{"timestamp": str(midnight(d)), "open": str(p)} for d, p in self.bitstamp
                    if d >= start][: int(params["limit"])]
            return httpx.Response(200, json={"data": {"pair": "BTC/USD", "ohlc": rows}})
        if "coinbase" in host and self.coinbase is not None:
            return httpx.Response(200, json=[[midnight(d), 1, 2, p, 3, 4] for d, p in self.coinbase])
        if "kraken" in host and self.kraken is not None:
            rows = [[midnight(d), str(p), "0", "0", "0", "0", "0", 1] for d, p in self.kraken]
            return httpx.Response(200, json={"error": [], "result": {"XXBTZUSD": rows, "last": 0}})
        if "coingecko" in host and self.coingecko is not None:
            return httpx.Response(200, json={"market_data": {"current_price": {"usd": self.coingecko}}})
        return httpx.Response(503)


@pytest.fixture
def sources(monkeypatch):
    """The real download code against fake services; live price forbidden."""
    fake = FakeSources()
    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(price_history, "fetch_range", real_fetch_range)
    monkeypatch.setattr("backend.services.bitcoin.get_historical_price", real_single_day)

    async def live_price_forbidden():
        raise AssertionError("a historical value must never use the live price")

    monkeypatch.setattr("backend.services.bitcoin.get_current_price", live_price_forbidden)
    return fake


@pytest.fixture
def db(test_engine):
    with sessionmaker(bind=test_engine)() as session:
        yield session
        session.rollback()


def test_one_download_fills_the_days_around_it(sources, db):
    day = date(2021, 3, 14)
    sources.bitstamp = candles(day - timedelta(days=600), 1400)
    expected = D(dict(sources.bitstamp)[day])
    assert price_history.daily_price(db, day) == expected
    assert sources.requests == ["www.bitstamp.net"]
    # Every day of the window is now local: no more requests.
    for offset in (-500, -1, 1, 250, 499):
        d = day + timedelta(days=offset)
        assert price_history.daily_price(db, d) == D(dict(sources.bitstamp)[d])
    assert sources.requests == ["www.bitstamp.net"]


def test_timestamps_use_their_utc_day(sources, db):
    day = date(2022, 6, 30)
    sources.bitstamp = candles(day - timedelta(days=5), 10)
    late_evening_chicago = datetime(2022, 6, 30, 23, 30, tzinfo=timezone(timedelta(hours=-5)))
    assert price_history.daily_price(db, late_evening_chicago) == D(dict(sources.bitstamp)[date(2022, 7, 1)])


def test_the_next_source_is_used_when_one_fails(sources, db):
    day = date(2023, 2, 1)
    sources.coinbase = candles(day - timedelta(days=100), 200, price=lambda d: 23456)
    assert price_history.daily_price(db, day) == D("23456.00")
    assert sources.requests[:2] == ["www.bitstamp.net", "api.exchange.coinbase.com"]


def test_a_candle_for_another_day_is_never_used(sources, db):
    """F42: Kraken returns only its latest 720 daily candles whatever
    `since` asks; the old lookup then used the first one, a price from about
    two years later, for any older date."""
    old_day = date(2021, 1, 5)
    sources.kraken = candles(date(2024, 10, 1), 720, price=lambda d: 64000)
    with pytest.raises(HTTPException) as exc:
        price_history.daily_price(db, old_day)
    assert exc.value.status_code == 422 and "2021-01-05" in exc.value.detail
    # The single-day lookup on its own (the old code path) also refuses it.
    with pytest.raises(HTTPException) as exc:
        asyncio.run(real_single_day(old_day.isoformat()))
    assert exc.value.status_code == 502


def test_no_price_is_a_clear_422_everywhere_never_the_live_price(sources, auth_client):
    """Income basis, Spent value, transfer fee and the form's Refresh all
    refuse to guess; before, a failed day lookup used today's price."""
    auth_client.delete("/api/transactions/delete_all")
    try:
        for body in (
            dict(type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
                 amount="100000", fee_amount="0", fee_currency="USD", source="N/A"),
            dict(type="Buy", timestamp="2024-01-03T12:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
                 amount="1", cost_basis_usd="40000", fee_amount="0", fee_currency="USD"),
        ):
            assert auth_client.post("/api/transactions", json=body).status_code == 200
        ts = "2024-05-01T12:00:00Z"
        cases = [
            dict(type="Deposit", from_account_id=EXTERNAL, to_account_id=WALLET, amount="0.01",
                 source="Income", fee_amount="0", fee_currency="BTC"),
            dict(type="Withdrawal", from_account_id=EXCH_BTC, to_account_id=EXTERNAL, amount="0.01",
                 purpose="Spent", fee_amount="0", fee_currency="BTC"),
            dict(type="Transfer", from_account_id=EXCH_BTC, to_account_id=WALLET, amount="0.1",
                 fee_amount="0.0001", fee_currency="BTC"),
        ]
        for body in cases:
            r = auth_client.post("/api/transactions", json={**body, "timestamp": ts})
            assert r.status_code == 422 and "2024-05-01" in r.text, (body["type"], r.status_code, r.text)
        r = auth_client.get("/api/bitcoin/price/history", params={"date": "2024-05-01"})
        assert r.status_code == 422
        # With the fee's value typed in, the transfer saves without any price.
        r = auth_client.post("/api/transactions", json={**cases[2], "timestamp": ts, "fee_usd": "6.10"})
        assert r.status_code == 200, r.text
        assert D(r.json()["fee_usd"]) == D("6.10") and r.json()["fee_usd_manual"] is True
    finally:
        auth_client.delete("/api/transactions/delete_all")


def test_the_refresh_button_and_the_server_use_the_same_price(auth_client):
    """F3: the form's FMV Refresh and the server's income valuation read the
    same stored price for the same UTC day."""
    auth_client.delete("/api/transactions/delete_all")
    try:
        refresh = auth_client.get("/api/bitcoin/price/history", params={"date": "2024-05-01"}).json()["USD"]
        r = auth_client.post("/api/transactions", json=dict(
            type="Deposit", timestamp="2024-05-01T12:00:00Z", from_account_id=EXTERNAL, to_account_id=WALLET,
            amount="0.5", source="Income", fee_amount="0", fee_currency="BTC"))
        assert r.status_code == 200, r.text
        assert D(r.json()["cost_basis_usd"]) == (D(str(refresh)) * D("0.5")).quantize(D("0.01"))
    finally:
        auth_client.delete("/api/transactions/delete_all")


@pytest.fixture
def funded(auth_client):
    auth_client.delete("/api/transactions/delete_all")
    for body in (
        dict(type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
             amount="100000", fee_amount="0", fee_currency="USD", source="N/A"),
        dict(type="Buy", timestamp="2024-01-03T12:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
             amount="1", cost_basis_usd="40000", fee_amount="0", fee_currency="USD"),
    ):
        assert auth_client.post("/api/transactions", json=body).status_code == 200
    yield
    auth_client.delete("/api/transactions/delete_all")


def transfer(client, **kw):
    body = dict(type="Transfer", timestamp="2024-05-01T12:00:00Z", from_account_id=EXCH_BTC,
                to_account_id=WALLET, amount="0.1", fee_amount="0.0002", fee_currency="BTC", **kw)
    r = client.post("/api/transactions", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def fee_proceeds(test_engine, tx_id):
    with test_engine.connect() as con:
        return con.execute(text("SELECT SUM(proceeds_usd_for_that_portion) FROM lot_disposals"
                                " WHERE transaction_id = :id"), {"id": tx_id}).scalar()


def test_a_fee_value_is_stored_once_and_survives_recalculation_offline(auth_client, test_engine, funded,
                                                                       monkeypatch):
    tx = transfer(auth_client)
    assert D(tx["fee_usd"]) == D("10.00") and tx["fee_usd_manual"] is False  # 0.0002 x $50,000
    assert D(str(fee_proceeds(test_engine, tx["id"]))) == D("10.00")

    async def offline(*a, **k):
        raise HTTPException(status_code=502, detail="offline")

    monkeypatch.setattr("backend.services.bitcoin.get_historical_price", offline)
    monkeypatch.setattr("backend.services.bitcoin.get_current_price", offline)
    with test_engine.begin() as con:
        con.execute(text("DELETE FROM btc_price_daily"))  # not even the local price is needed
    assert auth_client.post("/api/transactions/recalculate").status_code == 200
    assert D(str(fee_proceeds(test_engine, tx["id"]))) == D("10.00")


def test_saving_works_offline_once_the_day_is_stored(auth_client, funded, monkeypatch):
    transfer(auth_client)  # stores 2024-05-01

    async def offline(*a, **k):
        raise HTTPException(status_code=502, detail="offline")

    monkeypatch.setattr("backend.services.bitcoin.get_historical_price", offline)
    r = auth_client.post("/api/transactions", json=dict(
        type="Deposit", timestamp="2024-05-01T20:00:00Z", from_account_id=EXTERNAL, to_account_id=WALLET,
        amount="0.01", source="Reward", fee_amount="0", fee_currency="BTC"))
    assert r.status_code == 200, r.text
    assert D(r.json()["cost_basis_usd"]) == D("500.00")


def test_a_typed_fee_value_sticks_and_null_goes_back_to_the_price(auth_client, test_engine, funded):
    tx = transfer(auth_client, fee_usd="7.77")
    assert D(tx["fee_usd"]) == D("7.77") and tx["fee_usd_manual"] is True
    assert D(str(fee_proceeds(test_engine, tx["id"]))) == D("7.77")

    r = auth_client.put(f"/api/transactions/{tx['id']}", json={"timestamp": "2024-06-01T12:00:00Z",
                                                                "fee_amount": "0.0003"})
    assert r.status_code == 200 and D(r.json()["fee_usd"]) == D("7.77")

    r = auth_client.put(f"/api/transactions/{tx['id']}", json={"fee_usd": None})
    assert r.status_code == 200
    assert D(r.json()["fee_usd"]) == D("15.00") and r.json()["fee_usd_manual"] is False  # 0.0003 x $50,000


def test_editing_the_fee_prices_it_again_unless_typed(auth_client, funded, monkeypatch):
    tx = transfer(auth_client)

    async def other_price(date: str):
        return {"USD": 70000.0}

    monkeypatch.setattr("backend.services.bitcoin.get_historical_price", other_price)
    r = auth_client.put(f"/api/transactions/{tx['id']}", json={"timestamp": "2024-07-01T12:00:00Z"})
    assert D(r.json()["fee_usd"]) == D("14.00")  # new day, not stored yet: 0.0002 x $70,000
    r = auth_client.put(f"/api/transactions/{tx['id']}", json={"description_only": True})
    assert D(r.json()["fee_usd"]) == D("14.00")  # nothing fee-related changed


def test_a_fee_value_is_money(auth_client, funded):
    for bad in ("-1", "1.234"):
        r = auth_client.post("/api/transactions", json=dict(
            type="Transfer", timestamp="2024-05-01T12:00:00Z", from_account_id=EXCH_BTC, to_account_id=WALLET,
            amount="0.1", fee_amount="0.0002", fee_currency="BTC", fee_usd=bad))
        assert r.status_code == 422, (bad, r.text)


def test_an_edit_that_leaves_the_fee_alone_keeps_its_stored_value(auth_client, test_engine, funded):
    """The form sends every field on each edit: a stored value (e.g. one
    kept from before v0.9.2) must not be priced again unless the fee, its
    currency, the type or the day changes."""
    tx = transfer(auth_client)
    with test_engine.begin() as con:
        con.execute(text("UPDATE transactions SET fee_usd = '11.11' WHERE id = :id"), {"id": tx["id"]})
    full = {k: tx[k] for k in ("type", "from_account_id", "to_account_id", "amount", "fee_amount", "fee_currency")}
    r = auth_client.put(f"/api/transactions/{tx['id']}",
                        json={**full, "amount": "0.11", "timestamp": "2024-05-01T18:00:00Z"})  # same UTC day
    assert r.status_code == 200 and r.json()["fee_usd"] == "11.11"
    r = auth_client.put(f"/api/transactions/{tx['id']}", json={**full, "fee_amount": "0.0004"})
    assert r.json()["fee_usd"] == "20.00"
