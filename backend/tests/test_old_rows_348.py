"""
The rows from before 0.9.2 (spec 5.3, 5.13, 5.15; the owner's decision S7;
card B3 #348): a ledger's first 2.0 start keeps the ids of the transactions
naming an account made through 1.x's account API (7 to 98), Ledger Review
lists them as account_from_before_0_9_2 until each is saved or deleted,
and they count by their account's currency: the deposit into 7 is income now.
"""

import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.database import init_db, seed_defaults
from backend.main import app
from backend.models.account import Account
from backend.models.transaction import BitcoinLot, Transaction
from backend.services.reports.reporting_core import generate_report_data
from backend.services.review import build_review
from backend.tests.conftest import default_login, stub_prices_at

ISSUE = ("Saved before 0.9.2 into an account made through the old account API; 2.0 counts it by that "
         "account's currency.")
CHANGE = "Saving it, even unchanged, takes it off this list."


def save(client, **body) -> int:
    r = client.post("/api/transactions", json={"fee_amount": "0", "timestamp": "2024-06-15T15:00:00Z", **body})
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture
def ledger(gate_open, fresh_app, monkeypatch):
    """A 1.x ledger as 2.0 first finds it: accounts made through 1.x's API (a
    BTC "cold2" as 7, a USD "old bank" as 8, and a 99 that 1.x's API could
    make, internal since External is 99, 5.3), rows saved into them back
    then, and its first 2.0 start (seed_defaults) still to come."""
    stub_prices_at(monkeypatch, lambda when: Decimal("50000"))
    db = fresh_app()
    db.add_all([Account(id=7, user_id=1, name="cold2", kind="wallet", currency="BTC"),
                Account(id=8, user_id=1, name="old bank", kind="bank", currency="USD"),
                Account(id=99, user_id=1, name="account 99", kind="fee", currency="USD")])
    db.commit()
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    rows = {
        "income into 7": save(client, type="Deposit", from_account_id=99, to_account_id=7, amount="0.01",
                              source="Income", cost_basis_usd="500"),
        "into 8": save(client, type="Deposit", from_account_id=99, to_account_id=8, amount="300", source="N/A"),
        "into 2": save(client, type="Deposit", from_account_id=99, to_account_id=2, amount="0.02",
                       source="MyBTC", cost_basis_usd="900"),
    }
    db.execute(text("DELETE FROM app_settings WHERE key = 'accounts_old_rows'"))
    db.commit()
    seed_defaults(fresh_app.kw["bind"])
    return client, db, rows


def kept(db) -> list[int]:
    db.expire_all()
    (value,) = db.execute(text("SELECT value FROM app_settings WHERE key = 'accounts_old_rows'")).one()
    return json.loads(value)


def listed(client) -> list[dict]:
    return next(c for c in client.get("/api/review").json()["checks"] if c["key"] == "account_from_before_0_9_2")


def test_the_first_start_keeps_the_rows_naming_an_old_account(ledger):
    client, db, rows = ledger
    assert kept(db) == [rows["income into 7"], rows["into 8"]]


def test_ledger_review_lists_them_in_date_order_with_its_words(ledger):
    client, db, rows = ledger
    check = listed(client)
    assert (check["kind"], check["count"]) == ("check", 2)
    assert check["title"] == "Transactions in an account made through BitcoinTX's old account API"
    assert [(i["id"], i["issue"], i["change"]) for i in check["items"]] == [
        (rows["income into 7"], ISSUE, CHANGE), (rows["into 8"], ISSUE, CHANGE)]


def test_they_count_by_their_accounts_currency(ledger):
    client, db, rows = ledger
    gains = client.get("/api/calculations/gains-and-losses").json()
    assert (gains["income_earned"], gains["income_btc"]) == (500.0, 0.01)


def test_a_row_saved_into_an_old_account_later_isnt_listed(ledger):
    client, db, rows = ledger
    later = save(client, type="Deposit", from_account_id=99, to_account_id=7, amount="0.03", source="MyBTC",
                 cost_basis_usd="1000")
    assert later not in kept(db)
    assert [i["id"] for i in listed(client)["items"]] == [rows["income into 7"], rows["into 8"]]


def test_saving_one_even_unchanged_or_deleting_one_takes_it_off(ledger):
    client, db, rows = ledger
    assert client.put(f"/api/transactions/{rows['income into 7']}", json={}).status_code == 200
    assert kept(db) == [rows["into 8"]]
    assert client.delete(f"/api/transactions/{rows['into 8']}").status_code == 204
    assert kept(db) == []
    assert listed(client)["count"] == 0


def test_a_row_also_naming_a_missing_account_is_account_missings_alone(ledger):
    client, db, rows = ledger
    db.add(Transaction(type="Deposit", timestamp=db.get(Transaction, rows["into 8"]).timestamp,
                       from_account_id=999, to_account_id=7, amount=Decimal("0.001"), fee_amount=Decimal("0"),
                       source="MyBTC", cost_basis_usd=Decimal("50")))
    db.commit()
    db.execute(text("DELETE FROM app_settings WHERE key = 'accounts_old_rows'"))
    db.commit()
    seed_defaults(db.get_bind())
    both = max(kept(db))
    review = client.get("/api/review").json()
    by_key = {c["key"]: [i["id"] for i in c["items"]] for c in review["checks"]}
    assert both in by_key["account_missing"]
    assert both not in by_key["account_from_before_0_9_2"]


def test_a_restore_keeps_a_2_0_backups_list_and_writes_a_1x_backups(ledger):
    """A restore copies the backup's tables in, then runs seed_defaults
    (services/backup.restore_backup): a 2.0 backup's list stays as it is, a
    1.x backup has none and gets one."""
    client, db, rows = ledger
    db.execute(text("UPDATE app_settings SET value = '[42]' WHERE key = 'accounts_old_rows'"))
    db.commit()
    seed_defaults(db.get_bind())
    assert kept(db) == [42]
    db.execute(text("DELETE FROM app_settings WHERE key = 'accounts_old_rows'"))
    db.commit()
    seed_defaults(db.get_bind())
    assert kept(db) == [rows["income into 7"], rows["into 8"]]


OLD_ACCOUNTS = Path(__file__).parent / "fixtures" / "old_accounts_1x.db"


def test_the_old_databases_deposit_into_7_is_listed_and_moves_no_figure(tmp_path):
    """5.15's old database (1.x wrote it): its first 2.0 start keeps the
    deposit into 7 (cold2, a wallet), and by currency it is a My BTC deposit
    into a bitcoin account like any other. Its figures were already 7's
    currency's in 1.x (lines and a lot), so none moves; what moves is that
    Ledger Review lists it: as from before 0.9.2, and, having no date
    originally acquired, as such (1.x asked that only of 2 and 4). The row
    naming 999 is account_missing's alone."""
    path = tmp_path / "btctx.db"
    shutil.copy(OLD_ACCOUNTS, path)
    engine = create_engine(f"sqlite:///{path}")
    init_db(engine)
    with sessionmaker(bind=engine)() as db:
        into_7 = db.query(Transaction).filter_by(to_account_id=7).one()
        naming_999 = db.query(Transaction).filter_by(to_account_id=999).one()
        assert kept(db) == [into_7.id]
        checks = {c["key"]: [i["id"] for i in c["items"]] for c in build_review(db)["checks"] if c["items"]}
        lot = db.query(BitcoinLot).filter_by(created_txn_id=into_7.id).one()
        report = generate_report_data(db, 2024)
    by_hand = [t.id for t in sorted(_deposits_without_a_date(path), key=lambda t: t[1])]
    assert checks == {"account_from_before_0_9_2": [into_7.id], "account_missing": [naming_999.id],
                      "original_date_missing": [*by_hand]}
    assert into_7.id in by_hand
    assert (lot.total_btc, lot.cost_basis_usd) == (Decimal("0.5"), Decimal("15000"))
    assert report["income_summary"]["Total"] == 0.0
    assert ("cold2", 0.5, 15000.0) in [(b.get("account"), b["quantity"], b["cost"])
                                        for b in report["end_of_year_balances"]]


def _deposits_without_a_date(path):
    """The My BTC and Gift deposits into a bitcoin account (2, 4 and 7) with
    no date originally acquired, read straight from the file."""
    import sqlite3
    from collections import namedtuple
    Row = namedtuple("Row", "id timestamp")
    with sqlite3.connect(path) as con:
        return [Row(*r) for r in con.execute(
            "SELECT id, timestamp FROM transactions WHERE type = 'Deposit' AND to_account_id IN (2, 4, 7) "
            "AND source IN ('MyBTC', 'Gift') AND acquired_at IS NULL")]


def test_delete_all_empties_the_list_so_an_id_given_again_isnt_listed(ledger):
    """SQLite gives a transaction's id again once the highest are gone: after
    Delete All, a new row saved into 7 takes an id the list held."""
    client, db, rows = ledger
    r = client.delete("/api/transactions/delete_all?confirm=DELETE")
    assert r.status_code == 204, r.text
    assert kept(db) == []
    again = save(client, type="Deposit", from_account_id=99, to_account_id=7, amount="0.01", source="Income",
                 cost_basis_usd="500")
    assert again in rows.values()  # the same id as a row the list held
    assert listed(client)["count"] == 0
    seed_defaults(db.get_bind())  # a later start doesn't list it either
    assert kept(db) == []


def test_a_listed_id_whose_row_no_longer_names_an_old_account_isnt_listed(ledger):
    """5.13: the check lists a row on the list that names an account 7 to 98
    (a row the list names can only have left one by a save, which takes it
    off; or be another row, its id given again)."""
    client, db, rows = ledger
    db.execute(text("UPDATE app_settings SET value = :v WHERE key = 'accounts_old_rows'"),
               {"v": json.dumps([rows["income into 7"], rows["into 2"]])})
    db.commit()
    assert [i["id"] for i in listed(client)["items"]] == [rows["income into 7"]]


@pytest.mark.parametrize("value", ["not json", "{}", '"7"', '[1, "2", true, null, 2.5]'])
def test_a_value_that_isnt_a_list_of_ids_stops_nothing(ledger, value):
    client, db, rows = ledger
    db.execute(text("UPDATE app_settings SET value = :v WHERE key = 'accounts_old_rows'"), {"v": value})
    db.commit()
    assert client.get("/api/review").status_code == 200
    assert client.put(f"/api/transactions/{rows['income into 7']}", json={}).status_code == 200
    assert client.delete(f"/api/transactions/{rows['into 8']}").status_code == 204
    assert listed(client)["count"] == 0
