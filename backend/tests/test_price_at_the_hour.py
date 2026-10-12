"""
Valuing at the hour (#144, PR 3). Every value BitcoinTX prices itself (an
income or rebate deposit's basis, a BTC fee's value, a Spent's proceeds)
takes the opening price of the transaction's UTC hour
(services/hourly_prices.price_at) and records its moment (price_moment):
"hour", or "day" where no hourly price exists. A typed value is never
priced and has none. An edit prices a value again, at the hour, when what
it depends on changes (its hour now, not its day); a recalculation never
does. A Spent's priced proceeds are marked like income's
(proceeds_from_price), its fee and proceeds share one price, and migration
0010 marks existing rows without changing a figure.
"""

import io
import sqlite3
from datetime import datetime
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import create_engine

from backend.migrate import alembic_config, upgrade_database
from backend.services import hourly_prices
from backend.tests.conftest import stub_daily_prices, stub_prices_at

BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 2, 3, 4, 99
D = Decimal
CALLS: list = []


def price_of(when) -> Decimal:
    """Each hour its own price, so a value priced at another hour shows."""
    CALLS.append(when)
    return D(50000 + (hourly_prices.hour_of(when) // 3600) % 1000)


def at(moment: str) -> datetime:
    return datetime.fromisoformat(moment.replace("Z", "+00:00"))


@pytest.fixture(autouse=True)
def _ledger(auth_client, monkeypatch):
    stub_prices_at(monkeypatch, price_of)
    CALLS.clear()
    auth_client.delete("/api/transactions/delete_all")
    yield
    auth_client.delete("/api/transactions/delete_all")


def post(client, **fields) -> dict:
    r = client.post("/api/transactions", json=fields)
    assert r.status_code == 200, r.text
    return r.json()


def get(client, tx: dict) -> dict:
    return client.get(f"/api/transactions/{tx['id']}").json()


def deposit(client, **fields) -> dict:
    return post(client, **{"type": "Deposit", "timestamp": "2026-04-01T12:34:56Z", "from_account_id": EXTERNAL,
                           "to_account_id": WALLET, "amount": "0.1", "fee_amount": "0", "fee_currency": "BTC",
                           "source": "Income", **fields})


def buy(client, when="2026-01-02T10:00:00Z", amount="1"):
    return post(client, type="Buy", timestamp=when, from_account_id=BANK, to_account_id=EXCHANGE_BTC,
                amount=amount, fee_amount="0", fee_currency="USD", cost_basis_usd="40000")


def spend(client, **fields) -> dict:
    return post(client, **{"type": "Withdrawal", "timestamp": "2026-04-01T15:20:00Z",
                           "from_account_id": EXCHANGE_BTC, "to_account_id": EXTERNAL, "amount": "0.05",
                           "fee_amount": "0.0001", "fee_currency": "BTC", "purpose": "Spent", **fields})


def edit(client, tx: dict, **changes) -> dict:
    """The form's PUT: the saved fields with the changes."""
    keys = ("type", "timestamp", "from_account_id", "to_account_id", "amount", "fee_amount", "fee_currency",
            "cost_basis_usd", "source", "purpose", "proceeds_usd")
    body = {k: tx[k] for k in keys if k in tx} | changes
    if tx["type"] == "Withdrawal" and "proceeds_usd" not in changes:
        body["proceeds_usd"] = tx["gross_proceeds_usd"]  # the form shows the gross
    r = client.put(f"/api/transactions/{tx['id']}", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_blank_income_value_is_priced_at_its_hour(auth_client):
    tx = deposit(auth_client)
    assert D(tx["cost_basis_usd"]) == (price_of(at("2026-04-01T12:00:00Z")) * D("0.1")).quantize(D("0.01"))
    assert tx["price_moment"] == "hour" and tx["cost_basis_from_price"] is True


def test_without_an_hourly_price_it_is_the_days_and_says_so(auth_client, monkeypatch):
    stub_prices_at(monkeypatch, price_of, moment="day")
    assert deposit(auth_client)["price_moment"] == "day"


def test_a_typed_value_is_never_priced(auth_client):
    tx = deposit(auth_client, cost_basis_usd="1234.56")
    assert CALLS == [] and tx["price_moment"] is None and tx["cost_basis_from_price"] is False
    tx = edit(auth_client, tx, amount="0.2")
    assert tx["cost_basis_usd"] == "1234.56" and CALLS == []


def test_a_btc_fee_is_valued_at_its_hour(auth_client):
    buy(auth_client)
    tx = post(auth_client, type="Transfer", timestamp="2026-04-01T07:45:00Z", from_account_id=EXCHANGE_BTC,
              to_account_id=WALLET, amount="0.1", fee_amount="0.0002", fee_currency="BTC")
    assert D(tx["fee_usd"]) == (price_of(at("2026-04-01T07:00:00Z")) * D("0.0002")).quantize(D("0.01"))
    assert tx["price_moment"] == "hour" and tx["fee_usd_manual"] is False


def test_a_spend_without_proceeds_is_priced_at_its_hour_once(auth_client, monkeypatch):
    buy(auth_client)
    tx = get(auth_client, spend(auth_client))
    hour_price = price_of(at("2026-04-01T15:00:00Z"))
    assert D(tx["gross_proceeds_usd"]) == (hour_price * D("0.05")).quantize(D("0.01"))
    assert tx["proceeds_from_price"] is True and tx["price_moment"] == "hour"
    stub_prices_at(monkeypatch, lambda when: D(1))  # a recalculation never prices it again
    buy(auth_client, when="2026-01-01T10:00:00Z")
    after = get(auth_client, tx)
    assert (after["gross_proceeds_usd"], after["fee_usd"]) == (tx["gross_proceeds_usd"], tx["fee_usd"])


def test_an_edit_prices_again_when_the_hour_changes_not_within_it(auth_client):
    tx = deposit(auth_client, timestamp="2026-04-01T12:10:00Z")
    same_hour = edit(auth_client, tx, timestamp="2026-04-01T12:50:00Z")
    assert same_hour["cost_basis_usd"] == tx["cost_basis_usd"]
    other_hour = edit(auth_client, same_hour, timestamp="2026-04-01T13:05:00Z")
    assert D(other_hour["cost_basis_usd"]) == (price_of(at("2026-04-01T13:00:00Z")) * D("0.1")).quantize(D("0.01"))
    assert other_hour["price_moment"] == "hour"


def test_a_value_priced_at_the_day_is_priced_at_the_hour_when_an_edit_prices_it(auth_client, monkeypatch):
    stub_prices_at(monkeypatch, price_of, moment="day")
    tx = deposit(auth_client)
    stub_prices_at(monkeypatch, price_of)
    kept = edit(auth_client, tx, cost_basis_usd=tx["cost_basis_usd"])  # the form's echo: nothing to price
    assert kept["price_moment"] == "day" and kept["cost_basis_usd"] == tx["cost_basis_usd"]
    edited = edit(auth_client, kept, amount="0.2")
    assert edited["price_moment"] == "hour"
    assert D(edited["cost_basis_usd"]) == (price_of(at("2026-04-01T12:00:00Z")) * D("0.2")).quantize(D("0.01"))


def test_a_spends_proceeds_and_fee_share_one_price_after_an_edit(auth_client, monkeypatch):
    """A Spent priced at the day: an edit of its amount prices its proceeds
    and its fee again, together, at the hour."""
    buy(auth_client)
    stub_daily_prices(monkeypatch, lambda day: 30000)
    stub_prices_at(monkeypatch, lambda when: D(30000), moment="day")
    tx = get(auth_client, spend(auth_client))
    assert (tx["price_moment"], tx["fee_usd"], tx["gross_proceeds_usd"]) == ("day", "3.00", "1500.00")
    stub_prices_at(monkeypatch, price_of)
    edited = edit(auth_client, tx, amount="0.04")
    hour_price = price_of(at("2026-04-01T15:00:00Z"))
    assert edited["price_moment"] == "hour" and edited["proceeds_from_price"] is True
    assert D(edited["gross_proceeds_usd"]) == (hour_price * D("0.04")).quantize(D("0.01"))
    assert D(edited["fee_usd"]) == (hour_price * D("0.0001")).quantize(D("0.01"))


def test_the_form_sending_back_a_priced_spends_value_isnt_typing_it(auth_client):
    buy(auth_client)
    tx = get(auth_client, spend(auth_client))
    echoed = edit(auth_client, tx)
    assert echoed["proceeds_from_price"] is True and echoed["gross_proceeds_usd"] == tx["gross_proceeds_usd"]
    typed = edit(auth_client, echoed, proceeds_usd="2222.22")
    assert typed["proceeds_from_price"] is False and typed["gross_proceeds_usd"] == "2222.22"
    later = edit(auth_client, typed, amount="0.03")
    assert later["gross_proceeds_usd"] == "2222.22"  # typed: kept


def test_a_spend_turned_gift_has_no_priced_proceeds(auth_client):
    buy(auth_client)
    tx = get(auth_client, spend(auth_client))
    gift = edit(auth_client, tx, purpose="Gift", proceeds_usd=None)
    assert gift["proceeds_from_price"] is False and gift["price_moment"] == "hour"  # its fee is still priced


def test_migration_0010_marks_priced_rows_and_changes_no_figure(tmp_path):
    db = tmp_path / "btctx.db"
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as conn:
        cfg = alembic_config()
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0009")
    con = sqlite3.connect(str(db))
    con.execute("INSERT INTO btc_price_daily (day, usd, source) VALUES ('2025-05-05', 40000, 'bitstamp')")
    columns = ("id, type, timestamp, from_account_id, to_account_id, amount, fee_amount, fee_currency, source, "
               "purpose, cost_basis_usd, gross_proceeds_usd, proceeds_usd, fee_usd, fee_usd_manual, "
               "cost_basis_from_price")
    rows = [
        (1, "Deposit", "2025-05-05T10:00:00Z", 99, 2, "0.1", "0", "BTC", "Income", None, "4000.00", None, None,
         None, 0, 1),  # an income value from the price
        (2, "Deposit", "2025-05-05T10:00:00Z", 99, 2, "0.1", "0", "BTC", "Income", None, "3999.00", None, None,
         None, 0, 0),  # typed
        (3, "Withdrawal", "2025-05-05T11:00:00Z", 4, 99, "0.05", "0", "BTC", None, "Spent", None, "2000.00",
         "2000.00", None, 0, 0),  # proceeds = the day's price x the amount
        (4, "Withdrawal", "2025-05-05T11:00:00Z", 4, 99, "0.05", "0", "BTC", None, "Spent", None, "2100.00",
         "2100.00", None, 0, 0),  # typed
        (5, "Transfer", "2025-05-05T12:00:00Z", 4, 2, "0.1", "0.0001", "BTC", None, None, None, None, None,
         "4.00", 0, 0),  # a fee from the price
        (6, "Transfer", "2025-05-05T12:00:00Z", 4, 2, "0.1", "0.0001", "BTC", None, None, None, None, None,
         "5.00", 1, 0),  # a typed fee
    ]
    con.executemany(f"INSERT INTO transactions ({columns}) VALUES ({', '.join('?' * 16)})", rows)
    con.commit()
    figures = "SELECT id, cost_basis_usd, gross_proceeds_usd, proceeds_usd, fee_usd FROM transactions ORDER BY id"
    before = con.execute(figures).fetchall()
    con.close()
    upgrade_database(engine, backup=False)
    con = sqlite3.connect(str(db))
    marks = con.execute("SELECT id, price_moment, proceeds_from_price FROM transactions ORDER BY id").fetchall()
    assert marks == [(1, "day", 0), (2, None, 0), (3, "day", 1), (4, None, 0), (5, "day", 0), (6, None, 0)]
    assert con.execute(figures).fetchall() == before
    con.close()


def test_the_csv_export_carries_the_marks_and_an_older_file_means_the_day(auth_client):
    buy(auth_client)
    deposit(auth_client)
    spend(auth_client)
    export = auth_client.get("/api/backup/csv").text
    header = export.splitlines()[0].split(",")
    assert header[-2:] == ["proceeds_typed", "price_moment"]

    def imported(text: str) -> list[dict]:
        auth_client.delete("/api/transactions/delete_all")
        r = auth_client.post("/api/import/execute", files={"file": ("x.csv", io.BytesIO(text.encode()), "text/csv")})
        assert r.status_code == 200, r.text
        return sorted(auth_client.get("/api/transactions").json(), key=lambda t: t["timestamp"])

    again = imported(export)
    assert [(t["type"], t["price_moment"], t["proceeds_from_price"]) for t in again] == [
        ("Buy", None, False), ("Deposit", "hour", False), ("Withdrawal", "hour", True)]
    older = "\n".join(",".join(line.split(",")[:-2]) for line in export.splitlines())  # before 1.3
    assert [t["price_moment"] for t in imported(older)] == [None, "day", "day"]


def test_the_ai_import_marks_what_it_fills(auth_client):
    buy(auth_client)
    rows = [
        {"date": "2026-04-01T12:30:00Z", "type": "Deposit", "amount": "0.01", "from_account": "External",
         "to_account": "Wallet", "source": "Reward"},
        {"date": "2026-04-01T16:30:00Z", "type": "Withdrawal", "amount": "0.01", "from_account": "Exchange BTC",
         "to_account": "External", "purpose": "Spent"},
    ]
    r = auth_client.post("/api/import/entries/execute", json={"rows": rows})
    assert r.status_code == 200, r.text
    saved = {t["type"]: t for t in auth_client.get("/api/transactions").json()}
    assert saved["Deposit"]["price_moment"] == "hour" and saved["Deposit"]["cost_basis_from_price"] is True
    assert saved["Withdrawal"]["price_moment"] == "hour" and saved["Withdrawal"]["proceeds_from_price"] is True
    assert D(saved["Withdrawal"]["gross_proceeds_usd"]) == (
        price_of(at("2026-04-01T16:00:00Z")) * D("0.01")).quantize(D("0.01"))
