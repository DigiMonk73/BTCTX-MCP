"""
The local BTC price history and stored fee values (hardening F14, F42, P1;
docs/HARDENING_FINDINGS.md; v1.1.0 price privacy):

- no request ever names the day being looked up: the public sites are asked
  for the whole history once, in fixed blocks that are the same for every
  install, then only for "the latest days"; the own mempool server for its
  whole history (only its hourly 00:00 UTC prices are kept);
- later lookups don't touch the network; a stored day never changes;
- a candle for another day is never used as the asked day's price;
- nothing falls back to today's live price: no price is a clear 422;
- a BTC fee's USD value is stored at save, kept across recalculations with
  the network down, and a typed value sticks.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

import backend.services.price_history as price_history
from backend.services import outbound
from backend.tests.conftest import stub_daily_prices

# The real function, captured before the session fixture stubs it.
from backend.services.price_history import find_prices as real_find_prices

BANK, WALLET, EXCH_BTC, EXTERNAL = 1, 2, 4, 99
D = Decimal
TODAY = datetime.now(timezone.utc).date()
FIRST = price_history.FIRST_PRICE_DAY
NODE = "http://umbrel.local:3006"


def candles(start: date, days: int, price=lambda d: 20000 + d.toordinal() % 1000):
    return [(start + timedelta(days=i), price(start + timedelta(days=i))) for i in range(days)]


def all_days(price=lambda d: 20000 + d.toordinal() % 1000):
    return candles(FIRST, (TODAY - FIRST).days + 1, price)


def midnight(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


class FakeSources:
    """Bitstamp/Coinbase/Kraken (and a mempool server) answering from tables of days."""

    def __init__(self):
        self.bitstamp = self.coinbase = self.kraken = self.mempool = None
        self.requests = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        host, params = request.url.host, request.url.params
        if "bitstamp" in host and self.bitstamp is not None:
            limit = int(params["limit"])
            if "start" in params:
                start = datetime.fromtimestamp(int(params["start"]), tz=timezone.utc).date()
                rows = [(d, p) for d, p in self.bitstamp if d >= start][:limit]
            else:
                rows = self.bitstamp[-limit:]
            ohlc = [{"timestamp": str(midnight(d)), "open": str(p)} for d, p in rows]
            return httpx.Response(200, json={"data": {"pair": "BTC/USD", "ohlc": ohlc}})
        if "coinbase" in host and self.coinbase is not None:
            if "start" in params:
                lo, hi = (date.fromisoformat(params[k][:10]) for k in ("start", "end"))
                rows = [(d, p) for d, p in self.coinbase if lo <= d <= hi]
            else:
                rows = self.coinbase[-300:]
            return httpx.Response(200, json=[[midnight(d), 1, 2, p, 3, 4] for d, p in rows])
        if "kraken" in host and self.kraken is not None:
            rows = [[midnight(d), str(p), "0", "0", "0", "0", "0", 1] for d, p in self.kraken[-720:]]
            return httpx.Response(200, json={"error": [], "result": {"XXBTZUSD": rows, "last": 0}})
        if request.url.path == price_history.MEMPOOL_HISTORY_PATH and self.mempool is not None:
            return httpx.Response(200, json={"prices": self.mempool, "exchangeRates": {}})
        return httpx.Response(503)

    def names_a_day(self, day: date) -> bool:
        """Does any request carry `day`, as a date or as its midnight?"""
        marks = (day.isoformat(), str(midnight(day)), day.strftime("%d-%m-%Y"))
        return any(m in url for url in self.requests for m in marks)


@pytest.fixture
def sources(monkeypatch):
    """The real download code against fake services; live price forbidden."""
    fake = FakeSources()
    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(price_history, "find_prices", real_find_prices)

    async def live_price_forbidden():
        raise AssertionError("a historical value must never use the live price")

    monkeypatch.setattr("backend.services.bitcoin.get_current_price", live_price_forbidden)
    return fake


@pytest.fixture
def db(test_engine):
    with sessionmaker(bind=test_engine)() as session:
        yield session
        session.rollback()


def use(**settings):
    outbound._current = outbound.NetworkSettings(**settings)


def test_the_whole_history_comes_in_the_same_requests_whatever_the_day(sources, db):
    sources.bitstamp = all_days()
    seen = []
    for day in (date(2015, 5, 5), date(2021, 3, 14)):
        assert price_history.daily_price(db, day) == D(dict(sources.bitstamp)[day])
        assert not sources.names_a_day(day)
        seen.append(list(sources.requests))
        db.rollback()  # a fresh install again
        price_history.reset_state()
        sources.requests.clear()
    assert seen[0] == seen[1]
    starts = [datetime.fromtimestamp(int(httpx.URL(u).params["start"]), tz=timezone.utc).date() for u in seen[0]]
    assert starts[0] == FIRST and all((b - a).days == 1000 for a, b in zip(starts, starts[1:]))


def test_later_lookups_need_no_request(sources, db):
    sources.bitstamp = all_days()
    price_history.daily_price(db, date(2019, 1, 1))
    asked = len(sources.requests)
    for day in (FIRST, date(2014, 2, 2), date(2023, 7, 7), TODAY):
        assert price_history.daily_price(db, day) == D(dict(sources.bitstamp)[day])
    assert len(sources.requests) == asked
    assert price_history._history_complete(db)


def test_a_new_day_later_asks_only_for_the_latest_days(sources, db):
    sources.bitstamp = all_days()
    price_history.daily_price(db, date(2019, 1, 1))  # the whole history, flag set
    db.execute(text("DELETE FROM btc_price_daily WHERE day >= :d"), {"d": TODAY - timedelta(days=3)})
    sources.requests.clear()
    day = TODAY - timedelta(days=2)
    assert price_history.daily_price(db, day) == D(dict(sources.bitstamp)[day])
    assert len(sources.requests) == 1 and "start=" not in sources.requests[0]
    db.execute(text("DELETE FROM btc_price_daily WHERE day = :d"), {"d": day})
    # Once a UTC day is enough: another missing recent day asks nothing more.
    with pytest.raises(HTTPException):
        price_history.daily_price(db, day)
    assert len(sources.requests) == 1


def test_coinbase_blocks_when_bitstamp_is_down(sources, db):
    sources.coinbase = candles(price_history.COINBASE_FIRST_DAY,
                               (TODAY - price_history.COINBASE_FIRST_DAY).days + 1, price=lambda d: 23456)
    day = date(2023, 2, 1)
    assert price_history.daily_price(db, day) == D("23456.00")
    assert not sources.names_a_day(day)
    coinbase = [u for u in sources.requests if "coinbase" in u]
    assert len(coinbase) == len(price_history._blocks(price_history.COINBASE_FIRST_DAY, 300))
    assert not price_history._history_complete(db)  # Bitstamp is tried again later


def test_timestamps_use_their_utc_day(sources, db):
    sources.bitstamp = all_days()
    late_evening_chicago = datetime(2022, 6, 30, 23, 30, tzinfo=timezone(timedelta(hours=-5)))
    assert price_history.daily_price(db, late_evening_chicago) == D(dict(sources.bitstamp)[date(2022, 7, 1)])


def test_a_candle_for_another_day_is_never_used(sources, db):
    """F42: Kraken returns only its latest 720 daily candles; a price from
    years later must never stand in for an older day."""
    db.add(price_history.BtcPriceDaily(day=date(2020, 1, 1), usd=D("7000"), source="test"))
    price_history._mark_history_complete(db)
    sources.kraken = candles(TODAY - timedelta(days=719), 720, price=lambda d: 64000)
    with pytest.raises(HTTPException) as exc:
        price_history.daily_price(db, date(2021, 1, 5))
    assert exc.value.status_code == 422 and "2021-01-05" in exc.value.detail


@pytest.mark.parametrize("source", ["unset", "off"])
def test_nothing_is_asked_until_a_source_is_chosen_or_when_off(sources, db, source):
    use(price_source=source)
    sources.bitstamp = all_days()
    with pytest.raises(HTTPException) as exc:
        price_history.daily_price(db, date(2021, 3, 14))
    assert exc.value.status_code == 422 and "Settings" in exc.value.detail
    assert sources.requests == []


# ---------------------------------------------------------------------------
# The owner's mempool server
# ---------------------------------------------------------------------------
def hourly(day: date, price=30000, around=1):
    """mempool rows every hour from `around` days before `day` to after it."""
    t0 = midnight(day - timedelta(days=around))
    return [{"time": t0 + h * 3600, "USD": price + h % 5} for h in range((2 * around + 1) * 24)]


def test_mempool_hourly_midnights_are_used_and_nothing_public_is_asked(sources, db):
    use(price_source="mempool", mempool_url=NODE)
    day = date(2025, 4, 10)
    sources.mempool = hourly(day)
    assert price_history.daily_price(db, day) == D(str(30000 + (24 % 5)))
    assert sources.requests == [f"{NODE}/api/v1/historical-price?currency=USD"]
    assert not sources.names_a_day(day)


def test_mempool_weekly_or_lone_rows_are_not_a_days_price(sources, db):
    use(price_source="mempool", mempool_url=NODE)
    day = date(2017, 7, 13)
    sources.mempool = [{"time": midnight(day), "USD": 2400}, {"time": midnight(day) - 7 * 86400, "USD": 2500}]
    with pytest.raises(HTTPException):
        price_history.daily_price(db, day)
    assert all(NODE in u for u in sources.requests)  # fallback off: no public site


def test_midnight_prices_need_agreeing_neighbours():
    day = date(2025, 1, 1)
    t = midnight(day)
    rows = [{"time": t - 3600, "USD": 100000}, {"time": t, "USD": 101000}, {"time": t + 3600, "USD": 100500}]
    assert price_history.midnight_prices(rows) == {day: (D("101000.00"), "mempool")}
    rows[0]["USD"] = 90000  # more than 2% off: a backfilled close, not the hour
    assert price_history.midnight_prices(rows) == {}


def test_mempool_with_fallback_asks_the_public_history_for_older_days(sources, db):
    use(price_source="mempool", mempool_url=NODE, mempool_fallback=True)
    sources.mempool = hourly(date(2025, 4, 10))
    sources.bitstamp = all_days()
    day = date(2016, 6, 6)
    assert price_history.daily_price(db, day) == D(dict(sources.bitstamp)[day])
    assert sources.requests[0].startswith(NODE) and not sources.names_a_day(day)


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

    stub_daily_prices(monkeypatch, lambda day: None)
    monkeypatch.setattr("backend.services.bitcoin.get_current_price", offline)
    with test_engine.begin() as con:
        con.execute(text("DELETE FROM btc_price_daily"))  # not even the local price is needed
    assert auth_client.post("/api/transactions/recalculate").status_code == 200
    assert D(str(fee_proceeds(test_engine, tx["id"]))) == D("10.00")


def test_saving_works_offline_once_the_day_is_stored(auth_client, funded, monkeypatch):
    transfer(auth_client)  # stores 2024-05-01

    stub_daily_prices(monkeypatch, lambda day: None)  # offline
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

    stub_daily_prices(monkeypatch, lambda day: 70000.0)
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
