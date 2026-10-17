"""
A save of several rows prices its later rows while it holds SQLite's write
lock: the earlier rows are written. A year's price download that was running
then made it wait up to 30 s for that year (#421), and a price not stored
yet sent a request to the price sites or the owner's Mempool (#426); a save
of the owner's, which waits 5 s for the lock, failed meanwhile. Every save
that writes now finds the prices it needs first
(transaction.prices_found_ahead); under the lock it reads stored prices
only. A lookup before anything is written still waits for a download.
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
    assert downloading == [True]  # the transfer's fee, found before the Buy was written: the lock free
    [transfer] = [t for t in auth_client.get("/api/transactions").json() if t["type"] == "Transfer"]
    assert (Decimal(transfer["fee_usd"]), transfer["price_moment"]) == (Decimal("4.00"), "day")


def test_the_ai_previews_dry_run_never_waits_under_it_either(auth_client, downloading):
    """The path #421 was found on: the dry run writes its rows too."""
    r = auth_client.post("/api/import/entries/preview", json={"rows": [BUY, TO_WALLET]})
    assert r.status_code == 200, r.text
    assert downloading == [True]
    simulated = r.json()["results"][1]["simulated"]
    assert (Decimal(simulated["fee_usd"]), simulated["from_price"]["moment"]) == (Decimal("4.00"), "day")


def test_a_lookup_waits_only_before_anything_is_written(test_engine, downloading):
    when = datetime(2019, 3, 1, 12, tzinfo=timezone.utc)
    with sessionmaker(bind=test_engine)() as db:
        assert hp.hourly_price(db, when) is None and downloading == [True]  # nothing written: it waits
        db.execute(text("INSERT INTO app_settings (key, value) VALUES ('test-421', 'x')"))
        assert hp.hourly_price(db, when) is None and downloading == [True]  # written: no wait
        db.rollback()


# #426: every request for a price comes before the save's first write
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


def _rows(day: str) -> list[dict]:
    return [{**BUY, "date": f"{day}T10:00:00Z"}, {**TO_WALLET, "date": f"{day}T12:00:00Z"}]


def _asked_only_before_writing(asked: list) -> None:
    assert ("day", True) in asked  # the transfer's fee: its day wasn't stored
    assert all(free for _what, free in asked), asked


@pytest.mark.parametrize("route", ["preview", "execute"])
def test_the_ais_rows_are_priced_before_the_first_write(auth_client, test_engine, asked, route):
    _not_stored(test_engine, "2017-05-10")
    r = auth_client.post(f"/api/import/entries/{route}", json={"rows": _rows("2017-05-10")})
    assert r.status_code == 200, r.text
    _asked_only_before_writing(asked)


def test_a_csv_files_rows_are_priced_before_the_first_write(auth_client, test_engine, asked):
    _not_stored(test_engine, "2017-05-11")
    lines = [",".join(CSV_COLUMNS)]
    for row in _rows("2017-05-11"):
        cells = {**row, "fee_amount": row["fee_amount"], "fee_currency": row["fee_currency"]}
        lines.append(",".join(str(cells.get(c, "")) for c in CSV_COLUMNS))
    r = auth_client.post("/api/import/execute", files={"file": ("x.csv", "\n".join(lines) + "\n", "text/csv")})
    assert r.status_code == 200, r.text
    _asked_only_before_writing(asked)


def test_a_river_files_rows_are_priced_before_the_first_write(auth_client, test_engine, asked):
    _not_stored(test_engine, "2017-05-12")
    buy, transfer = _rows("2017-05-12")
    rows = [{**buy, "from_account": "Exchange USD"}, transfer]
    r = auth_client.post("/api/import/river/execute", json={"rows": rows})
    assert r.status_code == 200, r.text
    _asked_only_before_writing(asked)


def test_a_recalculation_prices_a_missing_value_before_it_writes(auth_client, test_engine, asked):
    """A row saved before values were stored, its BTC fee's USD value
    missing: the replay prices it once (transaction._stored_fee_usd)."""
    _not_stored(test_engine, "2017-05-13")
    buy, _ = _rows("2017-05-13")
    assert auth_client.post("/api/import/entries/execute", json={"rows": [buy]}).status_code == 200
    with test_engine.begin() as con:
        con.execute(text(
            "INSERT INTO transactions (type, timestamp, from_account_id, to_account_id, amount, fee_amount,"
            " fee_currency) VALUES ('Transfer', '2017-05-13T12:00:00Z', 4, 2, '0.1', '0.0001', 'BTC')"))
    asked.clear()
    assert auth_client.post("/api/transactions/recalculate").status_code == 200
    _asked_only_before_writing(asked)
