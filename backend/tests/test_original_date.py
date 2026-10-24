"""
A My BTC or Gift deposit's date originally acquired (#91). Coins the user
already owned, or a gift received with the giver's basis, keep their holding
period from when they were first acquired (IRC §1223(2) for gifts), not from
the deposit. The deposit's lot takes that date: the holding period, Form 8949
column (b) and first-in-first-out follow it, and a transfer keeps it. Left
blank, the deposit's date, as before.
"""

import io
import sqlite3
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.migrate import alembic_config, upgrade_database
from backend.services.reports.form_8949 import build_form_8949_and_schedule_d
from backend.services.review import REMINDERS, format_text

BANK, WALLET, EXCH_USD, EXCH_BTC, EXTERNAL = 1, 2, 3, 4, 99
TWO_YEARS_BEFORE = "2023-03-14T12:00:00Z"


@pytest.fixture(autouse=True)
def _ledger(auth_client):
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def post(client, **body) -> dict:
    r = client.post("/api/transactions", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def deposit(client, source="MyBTC", **fields) -> dict:
    return post(client, **{"type": "Deposit", "timestamp": "2025-04-01T12:00:00Z", "from_account_id": EXTERNAL,
                           "to_account_id": EXCH_BTC, "amount": "0.1", "cost_basis_usd": "2000",
                           "fee_amount": "0", "fee_currency": "BTC", "source": source, **fields})


def sell(client, when="2025-07-01T12:00:00Z", amount="0.1") -> dict:
    return post(client, type="Sell", timestamp=when, from_account_id=EXCH_BTC, to_account_id=EXCH_USD,
                amount=amount, gross_proceeds_usd="9000", fee_amount="0", fee_currency="USD")


def rows_2025(test_engine) -> list[dict]:
    with sessionmaker(bind=test_engine)() as db:
        forms = build_form_8949_and_schedule_d(2025, db)
    return forms["short_term"] + forms["long_term"]


@pytest.mark.parametrize("source", ["MyBTC", "Gift"])
def test_coins_held_before_the_deposit_are_long_term(auth_client, test_engine, source):
    """Deposited April 1, sold three months later, first acquired two years
    before: long-term, and column (b) is the date originally acquired."""
    tx = deposit(auth_client, source, acquired_at=TWO_YEARS_BEFORE)
    assert tx["acquired_at"].startswith("2023-03-14")
    sell(auth_client)
    [row] = rows_2025(test_engine)
    assert (row["holding_period"], row["date_acquired"]) == ("LONG", "03/14/2023")


def test_without_a_date_the_holding_period_starts_at_the_deposit(auth_client, test_engine):
    deposit(auth_client)
    sell(auth_client)
    [row] = rows_2025(test_engine)
    assert (row["holding_period"], row["date_acquired"]) == ("SHORT", "04/01/2025")


def test_first_in_first_out_takes_the_coins_acquired_first(auth_client, test_engine):
    """A Buy in January, then a My BTC deposit in April of coins bought two
    years earlier: a sale in July uses the older coins first (Treas. Reg.
    §1.1012-1(j): the units acquired earliest)."""
    post(auth_client, type="Deposit", timestamp="2025-01-02T12:00:00Z", from_account_id=EXTERNAL,
         to_account_id=EXCH_USD, amount="50000", fee_amount="0", fee_currency="USD", source="N/A")
    post(auth_client, type="Buy", timestamp="2025-01-10T12:00:00Z", from_account_id=EXCH_USD,
         to_account_id=EXCH_BTC, amount="0.1", cost_basis_usd="9500", fee_amount="0", fee_currency="USD")
    deposit(auth_client, acquired_at=TWO_YEARS_BEFORE)
    sell(auth_client, amount="0.1")
    [row] = rows_2025(test_engine)
    assert (row["date_acquired"], Decimal(str(row["cost"]))) == ("03/14/2023", Decimal("2000.00"))


def test_a_transfer_keeps_the_date(auth_client, test_engine):
    deposit(auth_client, acquired_at=TWO_YEARS_BEFORE)
    post(auth_client, type="Transfer", timestamp="2025-05-01T12:00:00Z", from_account_id=EXCH_BTC,
         to_account_id=WALLET, amount="0.1", fee_amount="0", fee_currency="BTC")
    post(auth_client, type="Withdrawal", timestamp="2025-07-01T12:00:00Z", from_account_id=WALLET,
         to_account_id=EXTERNAL, amount="0.05", fee_amount="0", fee_currency="BTC", purpose="Spent",
         proceeds_usd="4500")
    [row] = rows_2025(test_engine)
    assert (row["holding_period"], row["date_acquired"]) == ("LONG", "03/14/2023")


@pytest.mark.parametrize("fields, message", [
    ({"acquired_at": "2025-04-02T12:00:00Z"}, "can't be after the deposit's date"),
    ({"acquired_at": "2008-12-31T12:00:00Z"}, "before Bitcoin existed"),
    ({"acquired_at": TWO_YEARS_BEFORE, "source": "Income"}, "only for a My BTC or Gift deposit"),
    ({"acquired_at": TWO_YEARS_BEFORE, "to_account_id": BANK, "amount": "100", "fee_currency": "USD",
      "cost_basis_usd": None}, "only for a My BTC or Gift deposit"),
])
def test_a_date_that_cant_apply_is_refused(auth_client, fields, message):
    body = {"type": "Deposit", "timestamp": "2025-04-01T12:00:00Z", "from_account_id": EXTERNAL,
            "to_account_id": EXCH_BTC, "amount": "0.1", "cost_basis_usd": "2000", "fee_amount": "0",
            "fee_currency": "BTC", "source": "MyBTC", **fields}
    r = auth_client.post("/api/transactions", json=body)
    assert r.status_code == 422 and message in r.text, r.text


def test_an_edit_to_another_source_drops_the_date(auth_client):
    tx = deposit(auth_client, acquired_at=TWO_YEARS_BEFORE)
    r = auth_client.put(f"/api/transactions/{tx['id']}", json={"source": "Income"})
    assert r.status_code == 200, r.text
    assert r.json()["acquired_at"] is None


def test_an_edit_sets_and_clears_the_date(auth_client, test_engine):
    tx = deposit(auth_client)
    sell(auth_client)
    r = auth_client.put(f"/api/transactions/{tx['id']}", json={"acquired_at": TWO_YEARS_BEFORE})
    assert r.status_code == 200, r.text
    assert rows_2025(test_engine)[0]["holding_period"] == "LONG"  # the whole ledger recalculated
    r = auth_client.put(f"/api/transactions/{tx['id']}", json={"acquired_at": None})
    assert r.status_code == 200 and r.json()["acquired_at"] is None
    assert rows_2025(test_engine)[0]["holding_period"] == "SHORT"


def test_the_csv_export_and_import_carry_the_date(auth_client, test_engine):
    deposit(auth_client, acquired_at=TWO_YEARS_BEFORE)
    export = auth_client.get("/api/backup/csv")
    header, row = export.text.splitlines()[:2]
    column = header.split(",").index("acquired_at")
    assert row.split(",")[column] == "2023-03-14"  # a date (#185)
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    r = auth_client.post("/api/import/execute", files={"file": ("x.csv", io.BytesIO(export.content), "text/csv")})
    assert r.status_code == 200, r.text
    [tx] = auth_client.get("/api/transactions").json()
    assert tx["acquired_at"] == "2023-03-14"


def test_the_ai_connectors_import_takes_the_date(auth_client):
    row = {"date": "2025-04-01", "type": "Deposit", "amount": "0.1", "from_account": "External",
           "to_account": "Exchange BTC", "source": "Gift", "cost_basis_usd": "2000", "acquired_at": "2023-03-14"}
    preview = auth_client.post("/api/import/entries/preview", json={"rows": [row]}).json()
    assert preview["results"][0]["normalized"]["acquired_at"].startswith("2023-03-14")
    r = auth_client.post("/api/import/entries/execute", json={"rows": [row]})
    assert r.status_code == 200, r.text
    [tx] = auth_client.get("/api/transactions").json()
    assert tx["acquired_at"].startswith("2023-03-14")


def test_ledger_review_lists_my_btc_and_gift_deposits_without_a_date(auth_client):
    undated = deposit(auth_client)
    deposit(auth_client, "Gift", acquired_at=TWO_YEARS_BEFORE)
    deposit(auth_client, "Income", cost_basis_usd="5000")
    review = auth_client.get("/api/review").json()
    check = next(c for c in review["checks"] if c["key"] == "original_date_missing")
    assert [i["id"] for i in check["items"]] == [undated["id"]]


def test_ledger_review_lists_them_as_a_reminder_after_the_checks(auth_client):
    """#128: a blank date isn't an error, and after the 1.2.6 upgrade
    every older My BTC and Gift deposit has one: a reminder with one
    explanation for the group, after the checks and not in the total."""
    undated = deposit(auth_client)
    review = auth_client.get("/api/review").json()
    kinds = [c["kind"] for c in review["checks"]]
    assert kinds == sorted(kinds)  # every "check", then the reminders
    reminder = next(c for c in review["checks"] if c["key"] == "original_date_missing")
    assert reminder["kind"] == "reminder" and reminder["title"].startswith("Reminder:")
    assert [i["id"] for i in reminder["items"]] == [undated["id"]]
    assert reminder["explanation"][0].startswith("If these are really income, interest, rewards or rebates")
    checks = [c for c in review["checks"] if c["kind"] == "check"]
    # Only the hourly check (#144) explains itself, like a reminder
    assert [c["key"] for c in checks if c["explanation"]] == ["day_priced_values"]
    assert review["total"] == 0 and review["reminders"] == 1


def test_cli_review_prints_the_reminder_explanation_once_after_its_rows(auth_client):
    undated = deposit(auth_client)
    deposit(auth_client, "Gift")
    text = format_text(auth_client.get("/api/review").json())
    first = REMINDERS["original_date_missing"][0]
    assert text.count(first) == 1
    assert text.index(f"#{undated['id']} ") < text.index(first)


def test_0007_adds_an_empty_column_and_changes_nothing(tmp_path):
    db = tmp_path / "btctx.db"
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as conn:
        cfg = alembic_config()
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0006")
    con = sqlite3.connect(str(db))
    con.execute("INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount, fee_amount,"
                " fee_currency, source, cost_basis_usd) VALUES (1, 'Deposit', '2025-04-01T12:00:00Z', 99, 4, '0.1',"
                " '0', 'BTC', 'MyBTC', '2000')")
    con.commit()
    before = con.execute("SELECT * FROM transactions").fetchall()
    con.close()
    upgrade_database(engine, backup=False)
    con = sqlite3.connect(str(db))
    after = con.execute("SELECT * FROM transactions").fetchall()
    con.close()
    n = len(before[0])  # 0007's column comes next; later migrations add theirs after it
    assert [row[:n] for row in after] == before and after[0][n] is None


def test_coins_acquired_the_morning_of_the_deposit_are_allowed(auth_client):
    """Days compare in the tax timezone: a date alone on the day of a 10:00
    deposit is fine, and its lot (noon of that date) is no later than the
    deposit itself."""
    tx = deposit(auth_client, timestamp="2025-04-01T10:00:00Z", acquired_at="2025-04-01")
    assert tx["acquired_at"] == "2025-04-01"
    [lot] = auth_client.get("/api/debug/lots").json()
    assert lot["acquired_date"].startswith("2025-04-01T10:00:00")


def test_a_date_alone_is_kept_and_its_lot_is_at_noon_in_the_tax_timezone(auth_client, test_engine):
    """Column (b) shows the date given, in a New York tax timezone too: read as
    midnight UTC it would be the day before there."""
    before = auth_client.get("/api/settings/tax-timezone").json()["timezone"]
    assert auth_client.put("/api/settings/tax-timezone", json={"timezone": "America/New_York", "chosen": True}).status_code == 200
    try:
        tx = deposit(auth_client, acquired_at="2023-03-14")
        assert tx["acquired_at"] == "2023-03-14"
        [lot] = auth_client.get("/api/debug/lots").json()
        assert lot["acquired_date"].startswith("2023-03-14T16:00:00")  # noon in New York
        sell(auth_client)
        assert rows_2025(test_engine)[0]["date_acquired"] == "03/14/2023"
    finally:
        auth_client.put("/api/settings/tax-timezone", json={"timezone": before, "chosen": True})


@pytest.mark.parametrize("cells, message", [
    ("Deposit,0.1,External,Exchange BTC,5000,Income,2023-03-14", "only for a My BTC or Gift deposit"),
    ("Deposit,0.1,External,Exchange BTC,2000,MyBTC,2025-04-02", "can't be after the deposit's date"),
    ("Buy,0.1,Bank,Exchange BTC,2000,,2023-03-14", "only for a My BTC or Gift deposit"),
])
def test_the_csv_preview_names_a_row_whose_date_cant_apply(auth_client, cells, message):
    body = ("date,type,amount,from_account,to_account,cost_basis_usd,source,acquired_at\n"
            f"2025-04-01T09:00:00Z,{cells}\n")
    r = auth_client.post("/api/import/preview", files={"file": ("x.csv", io.BytesIO(body.encode()), "text/csv")})
    assert r.status_code == 200, r.text
    [error] = r.json()["errors"]
    assert (error["row_number"], error["column"]) == (2, "acquired_at") and message in error["message"]


@pytest.mark.parametrize("changes", [
    {"type": "Buy", "from_account_id": BANK, "to_account_id": EXCH_BTC},
    {"to_account_id": BANK, "amount": "100", "fee_currency": "USD", "cost_basis_usd": None},
])
def test_an_edit_to_another_type_or_account_drops_the_date(auth_client, changes):
    tx = deposit(auth_client, acquired_at=TWO_YEARS_BEFORE)
    r = auth_client.put(f"/api/transactions/{tx['id']}", json=changes)
    assert r.status_code == 200, r.text
    assert r.json()["acquired_at"] is None


def test_an_edit_that_moves_the_deposit_before_its_date_is_refused(auth_client):
    tx = deposit(auth_client, acquired_at="2025-03-01T12:00:00Z")
    r = auth_client.put(f"/api/transactions/{tx['id']}", json={"timestamp": "2025-02-01T12:00:00Z"})
    assert r.status_code == 422 and "can't be after the deposit's date" in r.text


def test_a_sale_before_the_deposit_never_uses_its_coins(auth_client, test_engine):
    """The lot exists only from the deposit on: a February sale uses the
    January Buy, though the April deposit's coins were acquired earlier."""
    post(auth_client, type="Deposit", timestamp="2025-01-02T12:00:00Z", from_account_id=EXTERNAL,
         to_account_id=EXCH_USD, amount="50000", fee_amount="0", fee_currency="USD", source="N/A")
    post(auth_client, type="Buy", timestamp="2025-01-10T12:00:00Z", from_account_id=EXCH_USD,
         to_account_id=EXCH_BTC, amount="0.1", cost_basis_usd="9500", fee_amount="0", fee_currency="USD")
    sell(auth_client, when="2025-02-01T12:00:00Z", amount="0.05")
    deposit(auth_client, acquired_at=TWO_YEARS_BEFORE)
    sell(auth_client, when="2025-07-01T12:00:00Z", amount="0.1")
    rows = sorted(rows_2025(test_engine), key=lambda r: r["date_sold"])
    assert [(r["date_sold"], r["date_acquired"]) for r in rows] == [
        ("02/01/2025", "01/10/2025"), ("07/01/2025", "03/14/2023")]


def test_a_misspelt_source_says_so_before_the_date(auth_client):
    body = ("date,type,amount,from_account,to_account,cost_basis_usd,source,acquired_at\n"
            "2025-04-01T09:00:00Z,Deposit,0.1,External,Exchange BTC,2000,Gfit,2023-03-14\n")
    r = auth_client.post("/api/import/preview", files={"file": ("x.csv", io.BytesIO(body.encode()), "text/csv")})
    [error] = r.json()["errors"]
    assert error["column"] == "source"
