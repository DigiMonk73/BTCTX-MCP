"""
A save of several rows prices its later rows while it holds SQLite's write
lock: the earlier rows are written. A year's price download that was running
then made it wait up to 30 s for that year (#421), and a price not stored
yet was asked for from the price sites or the owner's Mempool (#426); a save
of the owner's, which waits 5 s for the lock, failed meanwhile. Once a save
has written, a lookup doesn't wait (#421); and an import, the AI's preview
or add, finds its rows' prices before its first write
(transaction.find_prices_first). A request waits for a year once.
"""

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from backend.services import hourly_prices as hp
from backend.services import price_files as pf
from backend.services import price_history
from backend.services.csv_import import CSV_COLUMNS
from backend.tests.conftest import price_finder, stub_daily_prices

DAY_PRICE = 40000
BUY = {"date": "2019-03-01T10:00:00Z", "type": "Buy", "amount": "0.5", "from_account": "Bank",
       "to_account": "Exchange BTC", "cost_basis_usd": "1000.00", "fee_amount": "0", "fee_currency": "USD"}
TO_WALLET = {"date": "2019-03-01T12:00:00Z", "type": "Transfer", "amount": "0.1", "from_account": "Exchange BTC",
             "to_account": "Wallet", "fee_amount": "0.0001", "fee_currency": "BTC"}


@pytest.fixture
def downloading(auth_client, test_engine, monkeypatch):
    """2019's year file still downloading, no hourly price elsewhere; each
    wait for it records whether SQLite's write lock was free (another
    connection could take it)."""
    stub_daily_prices(monkeypatch, lambda day: DAY_PRICE)
    line = pf.YearLine(2019, pf.year_start(2019), pf.year_end(2019), 1, "sha2019")
    monkeypatch.setattr(pf, "read_manifest", lambda path=None: [line])
    monkeypatch.setattr(hp, "_year_prices", lambda *args, **kwargs: None)
    monkeypatch.setattr(hp, "_from_sources", lambda db, hour, files_end: (None, {}))
    monkeypatch.setattr(hp, "start_download", lambda: True)
    waits = []

    def wait(line):
        other = sqlite3.connect(test_engine.url.database, timeout=0)
        try:
            other.execute("BEGIN IMMEDIATE")
            other.rollback()
            waits.append(True)
        except sqlite3.OperationalError:  # database is locked
            waits.append(False)
        finally:
            other.close()
        return None

    monkeypatch.setattr(hp, "_wait_for_year", wait)
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    yield waits
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def test_a_later_rows_price_never_waits_under_the_write_lock(auth_client, downloading):
    r = auth_client.post("/api/import/entries/execute", json={"rows": [BUY, TO_WALLET]})
    assert r.status_code == 200, r.text
    assert downloading == [True]  # once, finding the transfer's fee first: the lock free
    [transfer] = [t for t in auth_client.get("/api/transactions").json() if t["type"] == "Transfer"]
    assert (Decimal(transfer["fee_usd"]), transfer["price_moment"]) == (Decimal("4.00"), "day")


def test_the_ai_previews_dry_run_never_waits_under_it_either(auth_client, downloading):
    """The path #421 was found on: the dry run writes its rows too."""
    r = auth_client.post("/api/import/entries/preview", json={"rows": [BUY, TO_WALLET]})
    assert r.status_code == 200, r.text
    assert downloading == [True]
    simulated = r.json()["results"][1]["simulated"]
    assert (Decimal(simulated["fee_usd"]), simulated["from_price"]["moment"]) == (Decimal("4.00"), "day")


def test_a_lookup_outside_an_import_waits_as_before_but_not_once_written(test_engine, downloading):
    """Each lookup waits for the year, as on develop (the AI's autofill, the
    River preview, Ledger Review's CLI apply), except once its save holds
    the write lock (#421)."""
    with sessionmaker(bind=test_engine)() as db:
        for hour in (11, 12):
            assert hp.hourly_price(db, datetime(2019, 3, 1, hour, tzinfo=timezone.utc)) is None
        assert downloading == [True, True]
    with sessionmaker(bind=test_engine)() as db:
        db.execute(text("INSERT INTO app_settings (key, value) VALUES ('test-421', 'x')"))
        assert hp.hourly_price(db, datetime(2019, 3, 1, 13, tzinfo=timezone.utc)) is None
        assert downloading == [True, True]  # written: no wait
        db.rollback()


def test_an_import_waits_for_a_year_once(auth_client, downloading):
    """#423's reviews: an import's rows in a year still downloading waited
    for it again and again (under the lock on develop)."""
    fee = {**TO_WALLET, "amount": "0.01"}
    rows = [BUY, {**fee, "date": "2019-03-01T11:00:00Z"}, {**fee, "date": "2019-03-01T12:00:00Z"}]
    r = auth_client.post("/api/import/execute", files={"file": ("x.csv", _csv(rows), "text/csv")})
    assert r.status_code == 200, r.text
    assert downloading == [True]  # finding the first fee's price, the lock free


def test_a_single_save_waits_once(auth_client, downloading):
    """#423's review: finding prices first made a save wait two or three times."""
    r = auth_client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2019-03-01T09:00:00Z", "from_account_id": 99, "to_account_id": 4,
        "amount": "1", "fee_amount": "0", "fee_currency": "USD", "source": "MyBTC", "cost_basis_usd": "1000"})
    assert r.status_code == 200, r.text
    r = auth_client.post("/api/transactions", json={
        "type": "Transfer", "timestamp": "2019-03-01T12:00:00Z", "from_account_id": 4, "to_account_id": 2,
        "amount": "0.1", "fee_amount": "0.0001", "fee_currency": "BTC"})
    assert r.status_code == 200, r.text
    assert downloading == [True]


# #426: an import's rows are priced before its first write
def _lock_free(test_engine) -> bool:
    other = sqlite3.connect(test_engine.url.database, timeout=0)
    try:
        other.execute("BEGIN IMMEDIATE")
        other.rollback()
        return True
    except sqlite3.OperationalError:  # database is locked
        return False
    finally:
        other.close()


@pytest.fixture
def asked(auth_client, test_engine, monkeypatch):
    """Each request for a price (a day's from the sites, an hour's from a
    source), as whether SQLite's write lock was free when it was made."""
    calls = []
    days = price_finder(lambda day: DAY_PRICE)

    async def find_prices(day, full):
        calls.append(("day", _lock_free(test_engine)))
        return await days(day, full)

    async def find_hours(hour, files_end, stored):
        calls.append(("hour", _lock_free(test_engine)))
        return {}

    monkeypatch.setattr(price_history, "find_prices", find_prices)
    monkeypatch.setattr(hp, "find_hours", find_hours)
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    yield calls
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def _not_stored(test_engine, day: str) -> None:
    with test_engine.begin() as con:
        con.execute(text("DELETE FROM btc_price_daily WHERE day = :d"), {"d": day})


GIFT = {"type": "Withdrawal", "amount": "0.01", "from_account": "Exchange BTC", "to_account": "External",
        "fee_amount": "0", "fee_currency": "BTC", "purpose": "Gift"}


def _rows(day: str, second: dict) -> list[dict]:
    return [{**BUY, "date": f"{day}T10:00:00Z"}, {**second, "date": f"{day}T12:00:00Z"}]


def _csv(rows: list[dict]) -> str:
    return "\n".join([",".join(CSV_COLUMNS)] + [",".join(str(r.get(c, "")) for c in CSV_COLUMNS) for r in rows]) + "\n"


def _asked_only_before_writing(asked: list) -> None:
    assert ("day", True) in asked  # the later row's day wasn't stored
    assert all(free for _what, free in asked), asked


@pytest.mark.parametrize("route", ["preview", "execute"])
def test_the_ais_rows_are_priced_before_the_first_write(auth_client, test_engine, asked, route):
    _not_stored(test_engine, "2017-05-10")
    r = auth_client.post(f"/api/import/entries/{route}", json={"rows": _rows("2017-05-10", TO_WALLET)})
    assert r.status_code == 200, r.text
    _asked_only_before_writing(asked)


@pytest.mark.parametrize("second, day", [(TO_WALLET, "2017-05-11"), (GIFT, "2017-05-14")], ids=["fee", "gift"])
def test_a_csv_files_rows_are_priced_before_the_first_write(auth_client, test_engine, asked, second, day):
    _not_stored(test_engine, day)
    r = auth_client.post("/api/import/execute", files={"file": ("x.csv", _csv(_rows(day, second)), "text/csv")})
    assert r.status_code == 200, r.text
    _asked_only_before_writing(asked)
    if second is GIFT:  # #423's review: a gift's blank value is priced, at the price found first
        [gift] = [t for t in auth_client.get("/api/transactions").json() if t["type"] == "Withdrawal"]
        assert (Decimal(gift["fmv_usd"]), gift["fmv_from_price"]) == (Decimal("400.00"), True)


@pytest.mark.parametrize("second, day", [(TO_WALLET, "2017-05-12"), (GIFT, "2017-05-15")], ids=["fee", "gift"])
def test_a_river_files_rows_are_priced_before_the_first_write(auth_client, test_engine, asked, second, day):
    _not_stored(test_engine, day)
    buy, later = _rows(day, second)
    r = auth_client.post("/api/import/river/execute", json={"rows": [{**buy, "from_account": "Exchange USD"}, later]})
    assert r.status_code == 200, r.text
    _asked_only_before_writing(asked)
