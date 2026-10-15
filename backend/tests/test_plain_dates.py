"""
A date originally acquired, or a date of death, is a date (#185). Stored as
noon in the tax timezone, it read back as a date in whatever the tax
timezone became: a change of many hours moved it a day, and saving the
deposit unchanged stored the moved day. It is stored as the date given,
'YYYY-MM-DD', and migration 0012 turns each stored moment into the date the
form showed.
"""

import sqlite3
from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from backend.migrate import alembic_config, upgrade_database
from backend.services.csv_import import parse_csv_file
from backend.tests.conftest import stub_daily_prices

EXCH_BTC, EXTERNAL = 4, 99
# Noon in Kiritimati (UTC+14) is 22:00 UTC the day before
KIRITIMATI = "Pacific/Kiritimati"


@pytest.fixture(autouse=True)
def _ledger(auth_client):
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    set_timezone(auth_client, "UTC")


def set_timezone(client, name: str) -> None:
    assert client.put("/api/settings/tax-timezone", json={"timezone": name}).status_code == 200


def deposit(client, **fields) -> dict:
    r = client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2025-04-01T12:00:00Z", "from_account_id": EXTERNAL,
        "to_account_id": EXCH_BTC, "amount": "0.1", "cost_basis_usd": "2000", "fee_amount": "0",
        "fee_currency": "BTC", "source": "MyBTC", **fields})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_date_stays_the_date_given_when_the_tax_timezone_changes(auth_client):
    """The issue's case: entered in Kiritimati, then the tax timezone set to
    UTC. It read back as March 13, and the form, sending back what it
    shows with any edit, saved March 13."""
    set_timezone(auth_client, KIRITIMATI)
    tx = deposit(auth_client, acquired_at="2021-03-14")
    set_timezone(auth_client, "UTC")
    assert auth_client.get(f"/api/transactions/{tx['id']}").json()["acquired_at"] == "2021-03-14"
    r = auth_client.put(f"/api/transactions/{tx['id']}", json={"acquired_at": "2021-03-14", "amount": "0.2"})
    assert r.status_code == 200 and r.json()["acquired_at"] == "2021-03-14", r.text
    # Its lot: noon of that date in the tax timezone now
    [lot] = auth_client.get("/api/debug/lots").json()
    assert lot["acquired_date"].startswith("2021-03-14T12:00:00")


def test_a_date_of_death_keeps_its_days_price_when_the_tax_timezone_changes(auth_client, monkeypatch):
    """An inheritance is priced on its date of death: after the change, an
    edit priced it again at the day before's price."""
    prices = {date(2023, 5, 19): 20000, date(2023, 5, 20): 30000}
    stub_daily_prices(monkeypatch, lambda day: prices.get(day, 90000))
    set_timezone(auth_client, KIRITIMATI)
    tx = deposit(auth_client, source="Inherited", acquired_at="2023-05-20", cost_basis_usd=None)
    assert Decimal(tx["cost_basis_usd"]) == Decimal("3000.00")
    set_timezone(auth_client, "UTC")
    r = auth_client.put(f"/api/transactions/{tx['id']}", json={"amount": "0.2"})
    assert r.status_code == 200 and Decimal(r.json()["cost_basis_usd"]) == Decimal("6000.00"), r.text


def test_a_date_given_with_a_time_is_its_date_in_the_tax_timezone(auth_client):
    """03:00 UTC on March 15 is the evening of March 14 in Chicago: a file's
    or the API's time stands for its date there, and the export writes the
    date alone."""
    set_timezone(auth_client, "America/Chicago")
    tx = deposit(auth_client, acquired_at="2021-03-15T03:00:00Z")
    assert tx["acquired_at"] == "2021-03-14"
    csv = ("date,type,amount,from_account,to_account,cost_basis_usd,fee_amount,fee_currency,source,acquired_at\n"
           "2025-04-01T12:00:00Z,Deposit,0.1,External,Exchange BTC,2000,0,BTC,MyBTC,2021-03-15T03:00:00Z\n")
    [row] = parse_csv_file(csv.encode(), ZoneInfo("America/Chicago")).transactions
    assert row["acquired_at"] == date(2021, 3, 14)
    export = auth_client.get("/api/backup/csv").text
    assert ",2021-03-14," in export and "2021-03-15" not in export


def test_the_ai_import_keeps_a_date_alone_as_given(auth_client):
    """A date alone was turned into noon in the tax timezone, in UTC: in
    Kiritimati the preview showed the day before."""
    set_timezone(auth_client, KIRITIMATI)
    row = {"date": "2025-04-01", "type": "Deposit", "amount": "0.1", "from_account": "External",
           "to_account": "Exchange BTC", "source": "MyBTC", "cost_basis_usd": "2000", "acquired_at": "2021-03-14"}
    preview = auth_client.post("/api/import/entries/preview", json={"rows": [row]})
    assert preview.status_code == 200, preview.text
    [result] = preview.json()["results"]
    assert result["status"] == "ready" and result["normalized"]["acquired_at"] == "2021-03-14", result
    r = auth_client.post("/api/import/entries/execute", json={"rows": [row]})
    assert r.status_code == 200, r.text
    [saved] = auth_client.get("/api/transactions").json()
    assert saved["acquired_at"] == "2021-03-14"


@pytest.mark.parametrize("stored, listed", [
    ("2021-03-14T03:00:00Z", False),  # its own day: no figure moves
    ("2021-03-13T12:00:00Z", True),  # another day: the holding period can
])
def test_ledger_review_lists_a_lot_only_when_its_date_would_change(auth_client, test_engine, stored, listed):
    """A date given with a time made its lot at that time; since #185 the
    lot is at noon of the date. Ledger Review lists what a recalculation
    would change, and a lot moved within its own day changes no figure."""
    tx = deposit(auth_client, acquired_at="2021-03-14")
    with test_engine.begin() as con:
        con.execute(text("UPDATE bitcoin_lots SET acquired_date = :at WHERE created_txn_id = :t"),
                    {"at": stored, "t": tx["id"]})
    check = next(c for c in auth_client.get("/api/review").json()["checks"] if c["key"] == "recalc_changes")
    assert [item["id"] for item in check["items"]] == ([tx["id"]] if listed else [])


def _database_at_0011(tmp_path, setting: str | None):
    db = tmp_path / "btctx.db"
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as conn:
        cfg = alembic_config()
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0011")
    con = sqlite3.connect(str(db))
    if setting:
        con.execute("INSERT INTO app_settings (key, value) VALUES ('tax_timezone', ?)", (setting,))
    con.executemany(
        "INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount, fee_amount, "
        "fee_currency, source, cost_basis_usd, acquired_at) VALUES (?, 'Deposit', '2025-04-01T12:00:00Z', 99, 4, "
        "'0.1', '0', 'BTC', 'MyBTC', '2000', ?)",
        [(1, "2021-03-13T22:00:00Z"), (2, None)])  # noon on March 14 in Kiritimati
    con.commit()
    con.close()
    return db, engine


def _dates(db) -> list[tuple]:
    con = sqlite3.connect(str(db))
    try:
        return con.execute("SELECT id, acquired_at FROM transactions ORDER BY id").fetchall()
    finally:
        con.close()


@pytest.mark.parametrize("setting, server_setting, shown", [
    (KIRITIMATI, None, "2021-03-14"),  # the tax timezone in Settings
    (None, KIRITIMATI, "2021-03-14"),  # else the server's (BTCTX_TIMEZONE)
    (None, None, "2021-03-13"),  # else UTC
])
def test_migration_0012_stores_the_date_the_form_showed(tmp_path, monkeypatch, setting, server_setting, shown):
    if server_setting:
        monkeypatch.setenv("BTCTX_TIMEZONE", server_setting)
    else:
        monkeypatch.delenv("BTCTX_TIMEZONE", raising=False)
    db, engine = _database_at_0011(tmp_path, setting)
    upgrade_database(engine, backup=False)
    assert _dates(db) == [(1, shown), (2, None)]
    with engine.begin() as conn:
        cfg = alembic_config()
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "0011")
    # Back to noon of that date in the same timezone
    assert _dates(db) == [(1, "2021-03-13T22:00:00Z" if setting or server_setting else "2021-03-13T12:00:00Z"),
                          (2, None)]
