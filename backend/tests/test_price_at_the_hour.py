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


def day_priced_spend(auth_client, monkeypatch) -> dict:
    """A Spent saved at the day's price ($30,000): proceeds and fee from it."""
    buy(auth_client)
    stub_daily_prices(monkeypatch, lambda day: 30000)
    stub_prices_at(monkeypatch, lambda when: D(30000), moment="day")
    tx = get(auth_client, spend(auth_client))
    assert (tx["price_moment"], tx["fee_usd"], tx["gross_proceeds_usd"]) == ("day", "3.00", "1500.00")
    stub_prices_at(monkeypatch, price_of)
    return tx


def test_a_spends_value_priced_again_keeps_the_days_price_while_the_other_does(auth_client, monkeypatch):
    """Review of #173: an edit of the amount prices the proceeds again; the
    fee's value keeps the day's price, so the proceeds take it too (one
    price for a transaction's values), and the row stays "day" for Ledger
    Review to offer at the hour."""
    tx = day_priced_spend(auth_client, monkeypatch)
    edited = edit(auth_client, tx, amount="0.04")
    assert (edited["price_moment"], edited["gross_proceeds_usd"], edited["fee_usd"]) == ("day", "1200.00", "3.00")


def test_a_fee_edit_alone_leaves_the_proceeds(auth_client, monkeypatch):
    """Review of #173: adding to the fee re-priced the untouched proceeds at the hour."""
    tx = day_priced_spend(auth_client, monkeypatch)
    edited = edit(auth_client, tx, fee_amount="0.0002")
    assert (edited["price_moment"], edited["gross_proceeds_usd"], edited["fee_usd"]) == ("day", "1500.00", "6.00")


def test_a_new_hour_prices_a_spends_proceeds_and_fee_at_the_hour(auth_client, monkeypatch):
    tx = day_priced_spend(auth_client, monkeypatch)
    edited = edit(auth_client, tx, timestamp="2026-04-01T17:10:00Z")
    hour_price = price_of(at("2026-04-01T17:00:00Z"))
    assert edited["price_moment"] == "hour" and edited["proceeds_from_price"] is True
    assert D(edited["gross_proceeds_usd"]) == (hour_price * D("0.05")).quantize(D("0.01"))
    assert D(edited["fee_usd"]) == (hour_price * D("0.0001")).quantize(D("0.01"))


@pytest.mark.parametrize("cleared", [None, "0"])
def test_a_cleared_or_zero_spend_value_is_priced_again_at_the_hour(auth_client, monkeypatch, cleared):
    """Review of #173: the form's null for an emptied field wasn't read as
    blank, so a day-priced spend was priced again at the day, and $0 at the hour."""
    buy(auth_client)
    stub_daily_prices(monkeypatch, lambda day: 30000)
    stub_prices_at(monkeypatch, lambda when: D(30000), moment="day")
    tx = get(auth_client, spend(auth_client, fee_amount="0"))
    stub_prices_at(monkeypatch, price_of)
    edited = get(auth_client, edit(auth_client, tx, proceeds_usd=cleared))
    assert edited["price_moment"] == "hour" and edited["proceeds_from_price"] is True
    assert D(edited["gross_proceeds_usd"]) == (price_of(at("2026-04-01T15:00:00Z")) * D("0.05")).quantize(D("0.01"))


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


def test_the_ai_import_values_an_inheritance_at_its_date_of_deaths_day(auth_client, monkeypatch):
    """Review of #176: the connector's import priced it at the hour of noon
    on the date of death, while the form uses that day's price (#173)."""
    stub_daily_prices(monkeypatch, lambda day: 30000)
    rows = [{"date": "2026-04-01T12:30:00Z", "type": "Deposit", "amount": "0.1", "from_account": "External",
             "to_account": "Wallet", "source": "Inherited", "acquired_at": "2026-02-10"}]
    r = auth_client.post("/api/import/entries/execute", json={"rows": rows})
    assert r.status_code == 200, r.text
    tx = auth_client.get("/api/transactions").json()[0]
    assert (tx["cost_basis_usd"], tx["price_moment"], tx["cost_basis_from_price"]) == ("3000.00", "day", True)
    assert CALLS == []  # never an hour's price


def test_the_gross_sent_is_the_value_an_edit_types(auth_client):
    """Review of #173: with both sent, the gross is what's stored."""
    buy(auth_client)
    tx = get(auth_client, spend(auth_client))
    typed = edit(auth_client, tx, proceeds_usd=tx["gross_proceeds_usd"], gross_proceeds_usd="2222.22")
    assert typed["proceeds_from_price"] is False and typed["gross_proceeds_usd"] == "2222.22"


def test_typing_over_the_only_priced_value_clears_the_moment(auth_client):
    tx = deposit(auth_client)
    typed = edit(auth_client, tx, cost_basis_usd="999.99")
    assert typed["cost_basis_from_price"] is False and typed["price_moment"] is None


def test_a_deposit_moved_to_the_bank_has_no_priced_value(auth_client):
    """Review of #173: the mark stays (it's unused), but no value, so no moment."""
    tx = deposit(auth_client)
    r = auth_client.put(f"/api/transactions/{tx['id']}", json={"to_account_id": BANK, "amount": "100"})
    assert r.status_code == 200, r.text
    assert r.json()["cost_basis_usd"] is None and r.json()["price_moment"] is None


# A CSV import needs an empty ledger: its rows bring their own buy.
IMPORTED_BUY = "2026-01-02T10:00:00Z,Buy,1,Bank,Exchange BTC,40000,,0,USD,,,\n"


def test_an_import_priced_at_the_day_prices_its_fee_at_the_day(auth_client, monkeypatch):
    """Review of #173: a fee priced at save took the hour and overwrote the
    import's "day", so Ledger Review would never list the day-priced proceeds."""
    stub_daily_prices(monkeypatch, lambda day: 30000)
    rows = ("date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency,"
            "purpose,proceeds_typed,price_moment\n" + IMPORTED_BUY +
            "2026-04-01T15:20:00Z,Withdrawal,0.05,Exchange BTC,External,,1500.00,0.0001,BTC,Spent,no,day\n")
    r = auth_client.post("/api/import/execute", files={"file": ("x.csv", io.BytesIO(rows.encode()), "text/csv")})
    assert r.status_code == 200, r.text
    tx = next(t for t in auth_client.get("/api/transactions").json() if t["type"] == "Withdrawal")
    assert (tx["price_moment"], tx["fee_usd"], tx["proceeds_from_price"]) == ("day", "3.00", True)


def test_a_value_priced_at_recalculation_takes_its_rows_moment(auth_client, monkeypatch, test_engine):
    """A row's other values at the day: a value priced at recalculation (an
    old fee without a stored value) takes the day too (_price_for)."""
    tx = day_priced_spend(auth_client, monkeypatch)
    from sqlalchemy import text as sql
    with test_engine.begin() as con:
        con.execute(sql("UPDATE transactions SET fee_usd = NULL WHERE id = :id"), {"id": tx["id"]})
    buy(auth_client, when="2026-01-01T10:00:00Z")  # any change recalculates
    after = get(auth_client, tx)
    assert (after["fee_usd"], after["price_moment"]) == ("3.00", "day")


@pytest.mark.parametrize("source, account", [("Rebate", WALLET), ("Interest", EXCHANGE_BTC)])
def test_rebates_and_exchange_deposits_are_priced_at_the_hour_too(auth_client, source, account):
    tx = deposit(auth_client, source=source, to_account_id=account)
    assert tx["price_moment"] == "hour"
    assert D(tx["cost_basis_usd"]) == (price_of(at("2026-04-01T12:00:00Z")) * D("0.1")).quantize(D("0.01"))


def test_an_edit_sending_one_field_like_the_ai_connector_prices_again_at_the_hour(auth_client, monkeypatch):
    stub_prices_at(monkeypatch, price_of, moment="day")
    tx = deposit(auth_client)
    stub_prices_at(monkeypatch, price_of)
    r = auth_client.put(f"/api/transactions/{tx['id']}", json={"amount": "0.3"})
    assert r.status_code == 200, r.text
    assert r.json()["price_moment"] == "hour"
    assert D(r.json()["cost_basis_usd"]) == (price_of(at("2026-04-01T12:00:00Z")) * D("0.3")).quantize(D("0.01"))


def test_a_sales_proceeds_are_never_marked_as_priced(auth_client):
    """An import's proceeds_typed "no" counts only on a Spent."""
    rows = ("date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency,"
            "purpose,proceeds_typed,price_moment\n" + IMPORTED_BUY +
            "2026-04-01T15:20:00Z,Sell,0.05,Exchange BTC,Exchange USD,,1500.00,0,USD,,no,\n")
    r = auth_client.post("/api/import/execute", files={"file": ("x.csv", io.BytesIO(rows.encode()), "text/csv")})
    assert r.status_code == 200, r.text
    sale = next(t for t in auth_client.get("/api/transactions").json() if t["type"] == "Sell")
    assert sale["proceeds_from_price"] is False and sale["price_moment"] is None


def test_ledger_review_leaves_fees_priced_at_the_hour(auth_client, monkeypatch):
    """Review of #173: the old fee check compared them with the day's price
    and offered to set them to it; the check of day-priced values passes them."""
    buy(auth_client)
    stub_daily_prices(monkeypatch, lambda day: 10000)  # far from the hour's
    post(auth_client, type="Transfer", timestamp="2026-04-01T07:45:00Z", from_account_id=EXCHANGE_BTC,
         to_account_id=WALLET, amount="0.1", fee_amount="0.0002", fee_currency="BTC")
    review = auth_client.get("/api/review").json()
    assert next(c for c in review["checks"] if c["key"] == "day_priced_values")["count"] == 0
def test_the_price_route_gives_the_price_a_moment_is_valued_at(auth_client):
    r = auth_client.get("/api/bitcoin/price/history", params={"at": "2026-04-01T09:47:00-05:00"})
    assert r.status_code == 200, r.text
    assert r.json() == {"USD": float(price_of(at("2026-04-01T14:00:00Z"))), "moment": "hour",
                        "at": "2026-04-01T14:00:00Z", "source": ""}  # the stub names no source
    for bad in ("tomorrow", "2999-01-01T00:00:00Z", "0001-01-01T00:00:00+14:00"):
        assert auth_client.get("/api/bitcoin/price/history", params={"at": bad}).status_code == 400
    # an offset's "+" sent unencoded (a space), and a lowercase z
    for sent in ("2026-04-01T16:47:00 02:00", "2026-04-01T14:47:00z"):
        assert auth_client.get("/api/bitcoin/price/history", params={"at": sent}).json()["at"] == "2026-04-01T14:00:00Z"
    assert auth_client.get("/api/bitcoin/price/history").status_code == 400



@pytest.mark.parametrize("change", [{"fee_amount": "0.0001"}, {"fee_usd": None}])
def test_a_fee_priced_by_an_edit_of_a_day_spend_takes_the_day(auth_client, monkeypatch, change):
    """Re-check of #173: a fee added (or a typed one cleared) on a spend whose
    proceeds keep the day's price was priced at the hour, the row marked "hour"."""
    buy(auth_client)
    stub_daily_prices(monkeypatch, lambda day: 30000)
    stub_prices_at(monkeypatch, lambda when: D(30000), moment="day")
    fields = {"fee_amount": "0"} if "fee_amount" in change else {"fee_usd": "7.77"}
    tx = get(auth_client, spend(auth_client, **fields))
    stub_prices_at(monkeypatch, price_of)
    edited = edit(auth_client, tx, **change)
    assert (edited["price_moment"], edited["gross_proceeds_usd"], edited["fee_usd"]) == ("day", "1500.00", "3.00")


def test_a_transfer_fee_priced_again_is_at_the_hour(auth_client, monkeypatch):
    buy(auth_client)
    stub_prices_at(monkeypatch, price_of, moment="day")
    tx = post(auth_client, type="Transfer", timestamp="2026-04-01T07:45:00Z", from_account_id=EXCHANGE_BTC,
              to_account_id=WALLET, amount="0.1", fee_amount="0.0002", fee_currency="BTC")
    assert tx["price_moment"] == "day"
    stub_prices_at(monkeypatch, price_of)
    edited = edit(auth_client, tx, fee_amount="0.0003")
    assert edited["price_moment"] == "hour"
    assert D(edited["fee_usd"]) == (price_of(at("2026-04-01T07:00:00Z")) * D("0.0003")).quantize(D("0.01"))


def test_a_file_without_the_moment_means_the_day(auth_client, monkeypatch):
    """Re-check of #173: the CSV instructions say a blank moment is the day."""
    stub_daily_prices(monkeypatch, lambda day: 30000)
    rows = ("date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency,"
            "purpose,proceeds_typed,price_moment\n" + IMPORTED_BUY +
            "2026-04-01T15:20:00Z,Withdrawal,0.05,Exchange BTC,External,,1500.00,0.0001,BTC,Spent,no,\n")
    r = auth_client.post("/api/import/execute", files={"file": ("x.csv", io.BytesIO(rows.encode()), "text/csv")})
    assert r.status_code == 200, r.text
    tx = next(t for t in auth_client.get("/api/transactions").json() if t["type"] == "Withdrawal")
    assert (tx["price_moment"], tx["fee_usd"]) == ("day", "3.00")


def test_a_file_row_priced_at_the_day_fills_a_blank_income_value_at_the_day(auth_client, monkeypatch):
    """Re-check of #173: an income value's own pricing (as an inheritance's,
    at the day) mustn't end the file row's day pricing: the hour's price
    marked "day" would be wrong."""
    stub_daily_prices(monkeypatch, lambda day: 30000)
    rows = ("date,type,amount,from_account,to_account,cost_basis_usd,source,fee_amount,fee_currency,"
            "price_moment\n2026-04-01T15:20:00Z,Deposit,0.1,External,Wallet,,Reward,0,BTC,day\n")
    r = auth_client.post("/api/import/execute", files={"file": ("x.csv", io.BytesIO(rows.encode()), "text/csv")})
    assert r.status_code == 200, r.text
    tx = auth_client.get("/api/transactions").json()[0]
    assert (tx["cost_basis_usd"], tx["price_moment"]) == ("3000.00", "day")
    assert CALLS == []


def test_the_day_wins_when_a_transactions_values_differ():
    from backend.services.transaction import _note_moment

    data = {"price_moment": "day"}
    _note_moment(data, "hour")
    assert data["price_moment"] == "day"
    data = {}
    _note_moment(data, "hour")
    assert data["price_moment"] == "hour"


def test_pricing_at_the_day_ends_with_its_block_even_on_an_error(test_engine):
    from sqlalchemy.orm import sessionmaker
    from backend.services.transaction import DAY_PRICES, _priced_at_the_day

    with sessionmaker(bind=test_engine)() as db:
        with pytest.raises(RuntimeError):
            with _priced_at_the_day(db, True):
                assert db.info[DAY_PRICES] is True
                raise RuntimeError
        assert not db.info.get(DAY_PRICES)



def test_an_inheritance_is_valued_at_its_date_of_deaths_day_and_a_save_changing_nothing_keeps_it(
        auth_client, monkeypatch):
    """Final re-check of #173: a date of death has no hour. It was priced at
    the hour of noon in the tax timezone, so the form's unchanged save (the
    date sent again, read as noon in a new tax timezone) moved the basis."""
    stub_daily_prices(monkeypatch, lambda day: 30000)
    tx = deposit(auth_client, source="Inherited", acquired_at="2026-02-10")
    assert (tx["cost_basis_usd"], tx["price_moment"]) == ("3000.00", "day")
    assert CALLS == []  # never the hour's price
    try:
        auth_client.put("/api/settings/tax-timezone", json={"timezone": "America/Chicago"})
        saved = edit(auth_client, tx, acquired_at="2026-02-10", cost_basis_usd=tx["cost_basis_usd"])
        assert saved["cost_basis_usd"] == "3000.00"
    finally:
        auth_client.put("/api/settings/tax-timezone", json={"timezone": "UTC"})


def test_a_day_spend_with_a_typed_fee_goes_to_the_hour_when_its_proceeds_are_priced_again(auth_client, monkeypatch):
    """A typed fee isn't a value kept at the day: the proceeds are the only priced value."""
    buy(auth_client)
    stub_daily_prices(monkeypatch, lambda day: 30000)
    stub_prices_at(monkeypatch, lambda when: D(30000), moment="day")
    tx = get(auth_client, spend(auth_client, fee_usd="7.77"))
    stub_prices_at(monkeypatch, price_of)
    edited = edit(auth_client, tx, amount="0.04")
    assert edited["price_moment"] == "hour" and edited["fee_usd"] == "7.77"


def test_an_hour_spend_edited_stays_at_the_hour(auth_client):
    buy(auth_client)
    tx = get(auth_client, spend(auth_client))
    edited = edit(auth_client, tx, amount="0.04")
    assert edited["price_moment"] == "hour"
    assert D(edited["gross_proceeds_usd"]) == (price_of(at("2026-04-01T15:00:00Z")) * D("0.04")).quantize(D("0.01"))


def test_a_day_fee_beside_typed_proceeds_goes_to_the_hour_when_priced_again(auth_client, monkeypatch):
    buy(auth_client)
    stub_daily_prices(monkeypatch, lambda day: 30000)
    stub_prices_at(monkeypatch, lambda when: D(30000), moment="day")
    tx = get(auth_client, spend(auth_client, proceeds_usd="1600.00"))
    assert (tx["price_moment"], tx["proceeds_from_price"]) == ("day", False)
    stub_prices_at(monkeypatch, price_of)
    edited = edit(auth_client, tx, fee_amount="0.0002")
    assert edited["price_moment"] == "hour"
    assert D(edited["fee_usd"]) == (price_of(at("2026-04-01T15:00:00Z")) * D("0.0002")).quantize(D("0.01"))


def test_typing_the_proceeds_while_the_fee_changes_puts_the_fee_at_the_hour(auth_client, monkeypatch):
    tx = day_priced_spend(auth_client, monkeypatch)
    edited = edit(auth_client, tx, proceeds_usd="2222.22", fee_amount="0.0002")
    assert (edited["price_moment"], edited["proceeds_from_price"], edited["gross_proceeds_usd"]) == (
        "hour", False, "2222.22")
    assert D(edited["fee_usd"]) == (price_of(at("2026-04-01T15:00:00Z")) * D("0.0002")).quantize(D("0.01"))
