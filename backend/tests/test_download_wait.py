"""
A save of several rows prices its later rows while it holds SQLite's write
lock: the earlier rows are written. A year's price download that was running
then made it wait up to 30 s for that year, and a save of the owner's, which
waits 5 s for the lock, failed meanwhile. Once a save has written, a price
lookup doesn't wait: it takes the day's price, as when no download can run
(#421). A lookup before anything is written still waits.
"""

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from backend.services import hourly_prices as hp
from backend.services import price_files as pf
from backend.tests.conftest import stub_daily_prices

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


def test_a_later_rows_price_doesnt_wait_under_the_write_lock(auth_client, downloading):
    r = auth_client.post("/api/import/entries/execute", json={"rows": [BUY, TO_WALLET]})
    assert r.status_code == 200, r.text
    assert downloading == []  # the Buy needs no price; the transfer's fee came after the Buy was written
    [transfer] = [t for t in auth_client.get("/api/transactions").json() if t["type"] == "Transfer"]
    assert (Decimal(transfer["fee_usd"]), transfer["price_moment"]) == (Decimal("4.00"), "day")


def test_the_ai_previews_dry_run_doesnt_wait_either(auth_client, downloading):
    """The path #421 was found on: the dry run writes its rows too."""
    r = auth_client.post("/api/import/entries/preview", json={"rows": [BUY, TO_WALLET]})
    assert r.status_code == 200, r.text
    assert downloading == []
    simulated = r.json()["results"][1]["simulated"]
    assert (Decimal(simulated["fee_usd"]), simulated["from_price"]["moment"]) == (Decimal("4.00"), "day")


def test_a_lookup_waits_only_before_anything_is_written(test_engine, downloading):
    when = datetime(2019, 3, 1, 12, tzinfo=timezone.utc)
    with sessionmaker(bind=test_engine)() as db:
        assert hp.hourly_price(db, when) is None and downloading == [True]  # nothing written: it waits
        db.execute(text("INSERT INTO app_settings (key, value) VALUES ('test-421', 'x')"))
        assert hp.hourly_price(db, when) is None and downloading == [True]  # written: no wait
        db.rollback()
