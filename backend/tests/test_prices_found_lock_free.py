"""
A save that holds SQLite's write lock asks no price source (#426): the
owner's other saves wait only 5 s for that lock. A lookup that would send a
request then stops the save, which rolls back, finds the price with the
lock free, and runs again (hourly_prices.with_prices_found). Here the real
lookups ask fake sites, and every request notes whether another connection
could take the write lock at that moment; the figures come out as a save
that asked under the lock would have made them.

The paths: a recalculation pricing an old row's missing value (Recalculate
Ledger in the app and the CLI, an edit, a delete, a backdated save or
import, the tax timezone's change, Ledger Review's apply at the hour), a
Spent's proceeds priced once its row is written (a new one, or an edit
that clears them), and any price an import's warm-up (#423) didn't find.
"""

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from backend.services import csv_import, entry_import, outbound, price_history
from backend.services import hourly_prices as hp
from backend.tests.conftest import empty_price_history

# The real lookups, captured before the session fixture stubs them
from backend.services.hourly_prices import find_hours as real_find_hours
from backend.services.price_history import find_prices as real_find_prices

DAY_PRICE = Decimal("40000")
NODE = "http://umbrel.local:3006"
BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 2, 3, 4, 99
DAY = 86400


def _lock_free(engine) -> bool:
    other = sqlite3.connect(engine.url.database, timeout=0)
    try:
        other.execute("BEGIN IMMEDIATE")
        other.rollback()
        return True
    except sqlite3.OperationalError:  # database is locked
        return False
    finally:
        other.close()


def _midnight(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())


class Sites:
    """Bitstamp's daily history (every day at DAY_PRICE) and a mempool server
    (its hourly record of a few days in March 2019), faked: each request
    noted as (host, whether the write lock was free)."""

    def __init__(self, engine):
        self.engine = engine
        self.requests: list[tuple[str, bool]] = []
        self.down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.url.host, _lock_free(self.engine)))
        if self.down:
            return httpx.Response(503)
        if request.url.path == price_history.MEMPOOL_HISTORY_PATH:
            hours = range(_midnight("2019-03-01"), _midnight("2019-03-08"), 3600)
            return httpx.Response(200, json={"prices": [{"time": t, "USD": str(DAY_PRICE)} for t in hours]})
        start = int(request.url.params.get("start", _midnight("2026-01-01")))
        rows = [{"timestamp": str(t), "open": str(DAY_PRICE)} for t in range(start, start + 1000 * DAY, DAY)]
        return httpx.Response(200, json={"data": {"pair": "BTC/USD", "ohlc": rows}})

    def all_with_the_lock_free(self) -> None:
        assert self.requests, "no price was asked for"
        assert all(free for _host, free in self.requests), self.requests


@pytest.fixture
def sites(auth_client, test_engine, monkeypatch):
    fake = Sites(test_engine)
    monkeypatch.setattr(price_history, "find_prices", real_find_prices)
    monkeypatch.setattr(hp, "find_hours", real_find_hours)
    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(fake.handler))
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    yield fake
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def post(client, **fields) -> dict:
    r = client.post("/api/transactions", json=fields)
    assert r.status_code == 200, r.text
    return r.json()


def get(client, tx_id: int) -> dict:
    return client.get(f"/api/transactions/{tx_id}").json()


def _no_price_stored(test_engine) -> None:
    """No price stored and none asked for yet, as on a fresh install."""
    empty_price_history(test_engine)
    price_history.reset_state()
    hp.reset_state()


BUY = dict(type="Buy", timestamp="2019-03-01T10:00:00Z", from_account_id=BANK, to_account_id=EXCHANGE_BTC,
           amount="1", fee_amount="0", fee_currency="USD", cost_basis_usd="1000")


@pytest.fixture
def unvalued_fee(auth_client, test_engine, sites):
    """A buy, a transfer whose BTC fee has no USD value (a row saved before
    values were stored, which a recalculation prices once) and a deposit
    after them; no price stored."""
    buy = post(auth_client, **BUY)
    transfer = post(auth_client, type="Transfer", timestamp="2019-03-02T12:00:00Z", from_account_id=EXCHANGE_BTC,
                    to_account_id=WALLET, amount="0.5", fee_amount="0.0001", fee_currency="BTC", fee_usd="9.99")
    deposit = post(auth_client, type="Deposit", timestamp="2019-03-03T09:00:00Z", from_account_id=EXTERNAL,
                   to_account_id=WALLET, amount="0.1", fee_amount="0", fee_currency="BTC", source="MyBTC",
                   cost_basis_usd="100")
    with test_engine.begin() as con:
        con.execute(text("UPDATE transactions SET fee_usd = NULL, fee_usd_manual = 0, price_moment = NULL "
                         "WHERE id = :id"), {"id": transfer["id"]})
    _no_price_stored(test_engine)
    sites.requests.clear()
    return {"buy": buy["id"], "transfer": transfer["id"], "deposit": deposit["id"]}


def _fee_valued(client, ids) -> None:
    transfer = get(client, ids["transfer"])
    assert (Decimal(transfer["fee_usd"]), transfer["price_moment"]) == (Decimal("4.00"), "day")
    assert "fee_usd" in transfer["values_from_price"]


# A row of an import, dated before the ledger's latest: the ledger is recalculated
EARLIER = {"date": "2019-02-01T10:00:00Z", "type": "Buy", "amount": "0.2", "from_account": "Bank",
           "to_account": "Exchange BTC", "cost_basis_usd": "200.00", "fee_amount": "0", "fee_currency": "USD"}

RECALCULATIONS = {
    "recalculate": lambda c, ids: c.post("/api/transactions/recalculate"),
    "edit": lambda c, ids: c.put(f"/api/transactions/{ids['buy']}", json={"cost_basis_usd": "1100"}),
    "delete": lambda c, ids: c.delete(f"/api/transactions/{ids['deposit']}"),
    "backdated save": lambda c, ids: c.post("/api/transactions", json={**BUY, "timestamp": "2019-02-01T10:00:00Z"}),
    "tax timezone": lambda c, ids: c.put("/api/settings/tax-timezone",
                                         json={"timezone": "America/New_York", "chosen": True}),
    "ai add": lambda c, ids: c.post("/api/import/entries/execute", json={"rows": [EARLIER]}),
    "river import": lambda c, ids: c.post("/api/import/river/execute",
                                          json={"rows": [{**EARLIER, "from_account": "Exchange USD"}]}),
}


@pytest.mark.parametrize("path", RECALCULATIONS)
def test_a_recalculation_finds_an_old_rows_missing_price_with_the_lock_free(auth_client, sites, unvalued_fee,
                                                                             path):
    r = RECALCULATIONS[path](auth_client, unvalued_fee)
    assert r.status_code in (200, 204), r.text
    sites.all_with_the_lock_free()
    _fee_valued(auth_client, unvalued_fee)
    if path == "tax timezone":
        assert auth_client.put("/api/settings/tax-timezone", json={"timezone": "UTC", "chosen": True}).status_code == 200


def test_the_ais_preview_does_too(auth_client, sites, unvalued_fee):
    """Its dry run recalculates the ledger with the row, then rolls back."""
    r = auth_client.post("/api/import/entries/preview", json={"rows": [EARLIER]})
    assert r.status_code == 200, r.text
    assert r.json()["ready_count"] == 1, r.text
    sites.all_with_the_lock_free()
    assert get(auth_client, unvalued_fee["transfer"])["fee_usd"] is None  # a dry run saves nothing


def test_the_clis_recalculate_ledger_does_too(test_engine, sites, unvalued_fee, monkeypatch, auth_client, capsys):
    """StartOS's Recalculate Ledger action runs it while the app serves."""
    import backend.database as database
    from backend import cli as backend_cli

    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=test_engine))
    monkeypatch.setattr(database, "init_db", lambda: None)
    monkeypatch.setattr(outbound, "load", lambda db, upgrade=True: None)  # the test's public sites
    assert backend_cli.main(["recalculate"]) == 0
    assert "Recalculated 3 transaction(s)." in capsys.readouterr().out
    sites.all_with_the_lock_free()
    _fee_valued(auth_client, unvalued_fee)


def test_ledger_reviews_apply_at_the_hour_does_too(auth_client, test_engine, sites, unvalued_fee):
    """It holds the lock from before its changes to the end of its recalculation."""
    reward = post(auth_client, type="Deposit", timestamp="2019-03-04T09:30:00Z", from_account_id=EXTERNAL,
                  to_account_id=WALLET, amount="0.1", fee_amount="0", fee_currency="BTC", source="Reward",
                  cost_basis_usd="4000")
    hour = _midnight("2019-03-04") + 9 * 3600
    with test_engine.begin() as con:
        con.execute(text("UPDATE transactions SET cost_basis_from_price = 1, price_moment = 'day' WHERE id = :id"),
                    {"id": reward["id"]})
        con.execute(text("INSERT INTO btc_price_hourly (hour, usd, source) VALUES (:h, '45000.00', 'bitstamp')"),
                    {"h": hour})
    r = auth_client.post("/api/review/hourly-prices", json={"ids": [reward["id"]]})
    assert r.status_code == 200, r.text
    (Path(test_engine.url.database).parent / "backups" / r.json()["backup"]).unlink()
    assert [c["id"] for c in r.json()["changed"]] == [reward["id"]]
    sites.all_with_the_lock_free()
    reward = get(auth_client, reward["id"])
    assert (reward["cost_basis_usd"], reward["price_moment"]) == ("4500.00", "hour")
    _fee_valued(auth_client, unvalued_fee)


def test_with_your_own_mempool_too(auth_client, sites, unvalued_fee):
    """The hour is asked of it first: the request it sent under the lock."""
    outbound._current = outbound.NetworkSettings(price_source="mempool", mempool_url=NODE)
    r = auth_client.post("/api/transactions/recalculate")
    assert r.status_code == 200, r.text
    assert sites.requests == [("umbrel.local", True)]  # one request: its day comes from the same answer
    _fee_valued(auth_client, unvalued_fee)


def test_without_a_price_it_answers_as_before(auth_client, sites, unvalued_fee):
    """A 422 naming the transaction, never $0; asked once, with the lock free."""
    sites.down = True
    r = auth_client.post("/api/transactions/recalculate")
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == (
        "Transfer of 0.5 BTC on 2019-03-02: its network fee has no USD value (enter it in that transaction). "
        "No BTC price is available for 2019-03-02; enter the USD value yourself.")
    assert sites.requests == [("www.bitstamp.net", True)]
    assert get(auth_client, unvalued_fee["transfer"])["fee_usd"] is None


@pytest.fixture
def bought(auth_client, test_engine, sites):
    buy = post(auth_client, **BUY)
    _no_price_stored(test_engine)
    sites.requests.clear()
    return buy["id"]


SPENT = dict(type="Withdrawal", timestamp="2019-03-05T10:00:00Z", from_account_id=EXCHANGE_BTC,
             to_account_id=EXTERNAL, amount="0.01", fee_amount="0", fee_currency="BTC", purpose="Spent")


def _proceeds_priced(spent: dict) -> None:
    assert (Decimal(spent["gross_proceeds_usd"]), spent["price_moment"]) == (Decimal("400.00"), "day")
    assert "gross_proceeds_usd" in spent["values_from_price"]


def test_a_new_spents_proceeds_are_found_with_the_lock_free(auth_client, sites, bought):
    """Left out, they're priced once the row is written (its lots then known)."""
    _proceeds_priced(post(auth_client, **SPENT))
    sites.all_with_the_lock_free()


def test_so_are_those_an_edit_clears(auth_client, test_engine, sites, bought):
    spent = post(auth_client, **SPENT, proceeds_usd="500")
    assert sites.requests == []  # typed: nothing priced
    r = auth_client.put(f"/api/transactions/{spent['id']}", json={"proceeds_usd": None})
    assert r.status_code == 200, r.text
    _proceeds_priced(r.json())
    sites.all_with_the_lock_free()


# Whatever price an import's warm-up (transaction.find_prices_first) misses:
# without it, a later row's price is looked for once earlier rows are written
FIRST, SECOND, THIRD = (
    {"date": "2019-03-01T10:00:00Z", "type": "Buy", "amount": "0.5", "from_account": "Bank",
     "to_account": "Exchange BTC", "cost_basis_usd": "1000.00", "fee_amount": "0", "fee_currency": "USD"},
    {"date": "2019-03-02T12:00:00Z", "type": "Transfer", "amount": "0.1", "from_account": "Exchange BTC",
     "to_account": "Wallet", "fee_amount": "0.0001", "fee_currency": "BTC"},
    {"date": "2019-03-06T12:00:00Z", "type": "Transfer", "amount": "0.1", "from_account": "Exchange BTC",
     "to_account": "Wallet", "fee_amount": "0.0002", "fee_currency": "BTC"},
)


def _csv(rows: list[dict]) -> str:
    columns = csv_import.CSV_COLUMNS
    return "\n".join([",".join(columns)] + [",".join(str(r.get(c, "")) for c in columns) for r in rows]) + "\n"


IMPORTS = {
    "ai add": lambda c, rows: c.post("/api/import/entries/execute", json={"rows": rows}),
    "ai preview": lambda c, rows: c.post("/api/import/entries/preview", json={"rows": rows}),
    "csv import": lambda c, rows: c.post("/api/import/execute", files={"file": ("x.csv", _csv(rows), "text/csv")}),
    "river import": lambda c, rows: c.post("/api/import/river/execute",
                                           json={"rows": [{**rows[0], "from_account": "Exchange USD"}, *rows[1:]]}),
}


@pytest.mark.parametrize("path", IMPORTS)
def test_an_imports_rows_find_a_price_its_warm_up_missed_with_the_lock_free(auth_client, test_engine, sites,
                                                                          monkeypatch, path):
    """The first transfer's day is stored, the second's isn't: found once the
    first is written, the import starts again from the rows as given, so
    the first fee's value is still one from the price, not a typed one."""
    monkeypatch.setattr(csv_import, "find_prices_first", lambda db, rows: None)
    monkeypatch.setattr(entry_import, "find_prices_first", lambda db, rows: None)
    _no_price_stored(test_engine)
    with test_engine.begin() as con:
        con.execute(text("INSERT INTO btc_price_daily (day, usd, source) VALUES ('2019-03-02', '30000.00', 'bitstamp')"))
    r = IMPORTS[path](auth_client, [FIRST, SECOND, THIRD])
    assert r.status_code == 200, r.text
    sites.all_with_the_lock_free()
    if path == "ai preview":
        simulated = [row["simulated"] for row in r.json()["results"][1:]]
        assert [Decimal(s["fee_usd"]) for s in simulated] == [Decimal("3.00"), Decimal("8.00")]
        assert all(s["from_price"]["values"] == ["fee_usd"] for s in simulated)
        return
    transfers = sorted((t for t in auth_client.get("/api/transactions").json() if t["type"] == "Transfer"),
                       key=lambda t: t["timestamp"])
    assert [Decimal(t["fee_usd"]) for t in transfers] == [Decimal("3.00"), Decimal("8.00")]
    assert all(t["values_from_price"] == ["fee_usd"] for t in transfers)
