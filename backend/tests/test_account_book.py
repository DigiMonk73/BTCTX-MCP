"""
The account book and the account API (2.0 spec 5.1, 5.4, 5.9; B2b, #347).

- The book answers every question about an account from the accounts and
  exchanges tables, and for a 1.x ledger exactly as 1.x's constants do.
- Ids: one more than the highest of 99, the table's ids, every id a row
  names and the last id given (`accounts_last_id`), worked out under the
  write lock, so a deleted id never comes back and two adds at once get two.
- Names: one line, 1 to 40 characters (an exchange's 36), no control or
  format character (but the joiners inside a name), runs of spaces one; no
  two alike (casefolded, joiners ignored), none reserved; an apostrophe is
  fine (the owner's decision 23, #251).
- The API: the list writes nothing; adding by kind (an exchange as its two
  accounts); hiding and showing; deleting only an unused account. No
  renames yet (B8).
"""

import shutil
import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.constants import RESERVED_NAMES
from backend.database import init_db
from backend.main import app
from backend.services import account as account_service
from backend.services.account import account_book
from backend.services.review import build_review
from backend.tests.conftest import default_login

FIXTURES = Path(__file__).parent / "fixtures"
URL = "/api/accounts/"
ONE_LINE = "A name is 1 to 40 characters on one line."
EXCHANGE_LINE = "A name is 1 to 36 characters on one line."


@pytest.fixture
def api(fresh_app):
    """A logged-in client on a database of its own, and that database's file."""
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    path = fresh_app.kw["bind"].url.database
    return SimpleNamespace(client=client, Session=fresh_app, path=path)


def _sql(path, *statements):
    con = sqlite3.connect(path)
    try:
        for statement in statements:
            con.execute(statement)
        con.commit()
    finally:
        con.close()


def _rows(path, sql):
    con = sqlite3.connect(path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _add(api, kind, name):
    return api.client.post(URL, json={"kind": kind, "name": name})


def _ledger(tmp_path, source=None):
    """A Session on a ledger at the head: a fresh one, or a copy of a fixture."""
    path = tmp_path / "btctx.db"
    if source:
        shutil.copy(source, path)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    init_db(engine)
    return sessionmaker(bind=engine)


# The book
# 1.x's names and ids (constants.ACCOUNT_ID_TO_NAME, which B5a removed), and
# its bitcoin accounts (constants.BTC_ACCOUNTS, which B3 removed)
NAMES_1X = {1: "Bank", 2: "Wallet", 3: "Exchange USD", 4: "Exchange BTC", 5: "BTC Fees", 6: "USD Fees",
            99: "External"}
BTC_1X = [2, 4]


@pytest.mark.parametrize("source", [None, FIXTURES / "v0_7_0.db"], ids=["fresh", "v0.7.0"])
def test_book_matches_1x(tmp_path, source):
    """For a 1.x ledger the book answers exactly as 1.x's constants do."""
    with _ledger(tmp_path, source)() as db:
        book = account_book(db)
    assert RESERVED_NAMES == {name: i for i, name in NAMES_1X.items()}
    for i, name in NAMES_1X.items():
        assert book.name(i) == name
        assert book.id_for(name) == book.id_for(name.upper()) == book.id_for(name.lower()) == i
    assert [i for i in [*NAMES_1X, 7, 1000] if book.is_btc(i)] == BTC_1X
    assert [book.currency(i) for i in (1, 2, 3, 4, 5, 6, 99, 7)] == ["USD", "BTC", "USD", "BTC", "BTC", "USD",
                                                                     None, None]
    assert [book.kind(i) for i in (1, 2, 3, 4, 5, 6, 99)] == ["bank", "wallet", "exchange", "exchange", "fee",
                                                              "fee", None]
    assert (book.exchange_of(3), book.exchange_of(4), book.exchange_of(2)) == (1, 1, None)
    assert (book.usd_of(4), book.btc_of(3), book.usd_of(2), book.btc_of(1)) == (3, 4, None, None)
    assert (book.sends_1099da(4), book.sends_1099da(3), book.sends_1099da(2)) == (True, True, False)
    assert book.yours() == [1, 2, 3, 4]
    assert book.name(12345) == "account 12345 (missing)"
    assert book.id_for("Nope") is None


def test_a_reserved_name_finds_its_account_after_a_rename(tmp_path):
    Session = _ledger(tmp_path)
    with Session() as db:
        db.execute(account_service.Account.__table__.update().where(account_service.Account.id == 1)
                   .values(name="Checking"))
        db.commit()
        book = account_book(db)
    assert (book.id_for("Bank"), book.id_for("checking"), book.name(1)) == (1, 1, "Checking")


def test_the_book_lists_an_old_ledgers_own_accounts_but_never_a_leftover(tmp_path):
    with _ledger(tmp_path, FIXTURES / "old_accounts_1x.db")() as db:
        book = account_book(db)
    assert book.yours() == [1, 2, 3, 4, 7, 8]  # 9, #289's leftover, is internal
    assert (book.kind(7), book.kind(8), book.kind(9)) == ("wallet", "bank", "fee")
    assert book.id_for("wallet") == 2 and book.id_for("wallet (account 8)") == 8


def test_a_row_with_externals_id_is_never_an_account(tmp_path):
    """5.3 keeps such a row (internal): External is 99 all the same."""
    Session = _ledger(tmp_path)
    with Session() as db:
        db.execute(account_service.Account.__table__.insert().values(
            id=99, user_id=1, name="Somewhere", currency="BTC", kind="fee", hidden=False))
        db.commit()
        book = account_book(db)
    assert (book.currency(99), book.kind(99), book.name(99), book.id_for("Somewhere")) == (None, None, "External",
                                                                                           None)
    assert book.id_for("External") == 99 and 99 not in book.yours()


def test_ledger_review_lists_the_row_naming_a_missing_account(tmp_path):
    with _ledger(tmp_path, FIXTURES / "old_accounts_1x.db")() as db:
        checks = {check["key"]: check["items"] for check in build_review(db)["checks"]}
        naming_999 = db.execute(account_service.Transaction.__table__.select()
                                .where(account_service.Transaction.to_account_id == 999)).one()
    assert [item["id"] for item in checks["account_missing"]] == [naming_999.id]


# The ids
def test_the_first_new_account_is_100_and_the_last_id_is_kept(api):
    r = _add(api, "wallet", "Coldcard")
    assert r.status_code == 201, r.text
    assert [(a["id"], a["name"], a["kind"], a["currency"]) for a in r.json()] == [(100, "Coldcard", "wallet", "BTC")]
    assert _rows(api.path, "SELECT value FROM app_settings WHERE key = 'accounts_last_id'") == [("100",)]


def test_an_id_a_row_names_is_never_given(api):
    _sql(api.path, "INSERT INTO transactions (type, timestamp, from_account_id, to_account_id, amount) "
                   "VALUES ('Deposit', '2024-01-01T00:00:00Z', 99, 999, 1)")
    assert [a["id"] for a in _add(api, "bank", "Credit union").json()] == [1000]


def test_a_deleted_id_never_comes_back(api):
    made = _add(api, "wallet", "Jade").json()[0]["id"]
    assert api.client.delete(f"{URL}{made}").status_code == 204
    assert [a["id"] for a in _add(api, "wallet", "Jade").json()] == [made + 1]


def test_an_exchange_is_its_two_accounts(api):
    r = _add(api, "exchange", "Kraken")
    assert r.status_code == 201, r.text
    made = r.json()
    assert [(a["id"], a["name"], a["currency"], a["kind"], a["exchange"]) for a in made] == [
        (100, "Kraken USD", "USD", "exchange", "Kraken"), (101, "Kraken BTC", "BTC", "exchange", "Kraken")]
    assert made[0]["exchange_id"] == made[1]["exchange_id"] != 1
    assert _rows(api.path, f"SELECT name, sends_1099da FROM exchanges WHERE id = {made[0]['exchange_id']}") == [
        ("Kraken", 1)]


@pytest.mark.parametrize("stored", ["'\u00b2'", "'-5'", "'x'", "'99999999999999999999'", "X'313530'", "X'FF'"])
def test_a_last_id_that_isnt_one_is_ignored(api, stored):
    _sql(api.path, f"INSERT INTO app_settings (key, value) VALUES ('accounts_last_id', {stored})")
    assert [a["id"] for a in _add(api, "wallet", "Jade").json()] == [100]


def test_an_id_only_a_ledger_line_names_is_never_given_nor_its_account_deleted(api):
    made = _add(api, "wallet", "Jade").json()[0]["id"]
    _sql(api.path, "INSERT INTO ledger_entries (transaction_id, account_id, amount, currency) "
                   f"VALUES (1, {made}, 1, 'BTC'), (1, 500, 1, 'BTC')")
    assert api.client.delete(f"{URL}{made}").status_code == 409
    assert api.client.get(f"{URL}{made}").json()["in_use"] is True
    assert [a["id"] for a in _add(api, "wallet", "Coldcard").json()] == [501]


def test_two_adds_at_once_get_two_ids(api):
    """Each works out its id under the write lock: the second waits for the
    first, then reads the id it gave."""
    barrier, made, failed = threading.Barrier(2), [], []

    def add(name):
        with api.Session() as db:
            barrier.wait()
            try:
                made.extend(a.id for a in account_service.add_account(db, "wallet", name))
            except Exception as e:  # pragma: no cover - shown below
                failed.append(e)

    threads = [threading.Thread(target=add, args=(name,)) for name in ("One", "Two")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not failed
    assert sorted(made) == [100, 101]


# The names
@pytest.mark.parametrize("kind, name, detail", [
    ("wallet", "", ONE_LINE),
    ("wallet", "   ", ONE_LINE),
    ("wallet", "x" * 41, ONE_LINE),
    ("exchange", "x" * 37, EXCHANGE_LINE),
    ("wallet", "Cold\nstorage", ONE_LINE),
    ("wallet", "Cold\u200bstorage", ONE_LINE),  # a zero-width space
    ("wallet", "\u202eevil", ONE_LINE),  # a bidirectional control
    ("wallet", "Wallet", "'Wallet' always means your first wallet in files (CSV, River, BitcoinTX 1.x): "
                         "choose another name."),
    ("bank", "bank", "'bank' always means your first bank in files (CSV, River, BitcoinTX 1.x): choose another name."),
    ("wallet", "Exchange BTC", "'Exchange BTC' always means your first exchange in files (CSV, River, BitcoinTX 1.x): "
                               "choose another name."),
    ("wallet", "external", "External means everything outside BitcoinTX: choose another name."),
    ("wallet", "BTC fees", "An account named 'BTC fees' already exists."),
    ("exchange", "Exchange", "An exchange named 'Exchange' already exists."),
    # what nothing shows makes no name of its own (2.0 spec 5.1)
    ("wallet", "Wallet\u034f", "'Wallet' always means your first wallet in files (CSV, River, BitcoinTX 1.x): "
                               "choose another name."),
    ("bank", "\u2800Bank\ufe0f", "'Bank\ufe0f' always means your first bank in files (CSV, River, BitcoinTX 1.x): "
                                 "choose another name."),
    ("wallet", "Bank\u3164", "'Bank' always means your first bank in files (CSV, River, BitcoinTX 1.x): "
                             "choose another name."),
    ("exchange", "Exchange\u034f", "An exchange named 'Exchange' already exists."),
])
def test_a_name_is_refused(api, kind, name, detail):
    r = _add(api, kind, name)
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == detail
    assert _rows(api.path, "SELECT count(*) FROM accounts WHERE id >= 100") == [(0,)]


@pytest.mark.parametrize("name", ["COLDCARD", "Cold\u200dcard", "  coldcard ", "Cold\u034fcard"])
def test_a_name_alike_another_is_refused(api, name):
    assert _add(api, "wallet", "Coldcard").status_code == 201
    r = _add(api, "bank", name)
    assert r.status_code == 400 and r.json()["detail"] == f"An account named '{name.strip()}' already exists."


def test_an_exchanges_account_names_must_be_free(api):
    assert _add(api, "wallet", "Kraken BTC").status_code == 201
    r = _add(api, "exchange", "Kraken")
    assert r.status_code == 400 and r.json()["detail"] == "An account named 'Kraken BTC' already exists."


@pytest.mark.parametrize("kind, name, saved", [
    ("wallet", "  Cold \u00a0  card ", "Cold card"),  # runs of spaces made one
    ("wallet", "x" * 40, "x" * 40),
    ("exchange", "y" * 36, "y" * 36 + " USD"),
    ("bank", "'Savings", "'Savings"),  # the owner's decision 23 (#251)
    ("wallet", "Cold \u2744\ufe0f", "Cold \u2744\ufe0f"),  # an emoji keeps its variation selector
    ("wallet", "Cafe\u0301", "Caf\u00e9"),
    ("wallet", "\U0001f469\u200d\U0001f4bb wallet", "\U0001f469\u200d\U0001f4bb wallet"),  # a joiner inside stays
])
def test_a_name_is_saved_cleaned(api, kind, name, saved):
    r = _add(api, kind, name)
    assert r.status_code == 201, r.text
    assert r.json()[0]["name"] == saved


@pytest.mark.parametrize("body", [{"kind": "fee", "name": "Fees 2"}, {"kind": "bank"}, {"name": "x"},
                                  {"kind": "bank", "name": "x", "currency": "BTC"}])
def test_a_kind_bitcointx_doesnt_add_is_422(api, body):
    assert api.client.post(URL, json=body).status_code == 422


# The list, hiding and deleting
def test_the_list_by_kind_without_a_leftover_and_writing_nothing(api):
    _add(api, "exchange", "Kraken")
    _add(api, "wallet", "Jade")
    _sql(api.path, "UPDATE accounts SET name = 'Network fees' WHERE id = 5",  # as #289 left one
         "INSERT INTO accounts (id, user_id, name, currency, kind, hidden) VALUES (9, 1, 'Old fees', 'BTC', 'fee', 0)",
         "INSERT INTO transactions (type, timestamp, from_account_id, to_account_id, amount) "
         "VALUES ('Deposit', '2024-01-01T00:00:00Z', 99, 102, 1)")
    before = _rows(api.path, "SELECT * FROM accounts ORDER BY id") + _rows(api.path, "SELECT * FROM exchanges")
    r = api.client.get(URL)
    assert r.status_code == 200
    assert [(a["id"], a["kind"], a["in_use"]) for a in r.json()] == [
        (1, "bank", False), (2, "wallet", False), (102, "wallet", True), (3, "exchange", False),
        (4, "exchange", False), (100, "exchange", False), (101, "exchange", False), (5, "fee", False),
        (6, "fee", False)]
    assert set(r.json()[0]) == {"id", "name", "kind", "currency", "exchange_id", "exchange", "hidden", "in_use"}
    assert _rows(api.path, "SELECT * FROM accounts ORDER BY id") + _rows(api.path, "SELECT * FROM exchanges") == before
    assert api.client.get(f"{URL}2").json()["name"] == "Wallet"
    assert api.client.get(f"{URL}9999").status_code == 404
    assert api.client.get(f"{URL}9").status_code == 404  # the leftover, as the list leaves it out
    assert api.client.put(f"{URL}9", json={"hidden": True}).status_code == 404
    assert api.client.delete(f"{URL}9").status_code == 404


def test_hiding_and_showing(api):
    hidden = api.client.put(f"{URL}2", json={"hidden": True})
    assert hidden.status_code == 200 and hidden.json()["hidden"] is True
    assert api.client.put(f"{URL}2", json={"hidden": False}).json()["hidden"] is False
    api.client.put(f"{URL}4", json={"hidden": True})  # an exchange's account: the exchange's two
    assert {a["id"]: a["hidden"] for a in api.client.get(URL).json()}[3] is True


@pytest.mark.parametrize("account_id, body, status, detail", [
    (5, {"hidden": True}, 400, "The fee accounts keep their names and can't be hidden."),
    (2, {"name": "Cold"}, 422, None),  # renames come with B8
    (2, {"currency": "USD"}, 422, None),
    (2, {}, 422, None),
    (9999, {"hidden": True}, 404, None),
])
def test_a_change_is_refused(api, account_id, body, status, detail):
    r = api.client.put(f"{URL}{account_id}", json=body)
    assert r.status_code == status, r.text
    if detail:
        assert r.json()["detail"] == detail


@pytest.mark.parametrize("account_id, status, detail", [
    (1, 400, "Your first bank, wallet and exchange can't be deleted. Hide one you don't use."),
    (4, 400, "Your first bank, wallet and exchange can't be deleted. Hide one you don't use."),
    (5, 400, "The fee accounts can't be deleted."),
    (99, 404, None),
])
def test_a_fixed_account_isnt_deleted(api, account_id, status, detail):
    r = api.client.delete(f"{URL}{account_id}")
    assert r.status_code == status
    if detail:
        assert r.json()["detail"] == detail


def test_an_account_in_use_isnt_deleted_and_an_exchange_goes_whole(api):
    wallet = _add(api, "wallet", "Jade").json()[0]["id"]
    usd, btc = (a["id"] for a in _add(api, "exchange", "Kraken").json())
    _sql(api.path, "INSERT INTO transactions (type, timestamp, from_account_id, to_account_id, amount) "
                   f"VALUES ('Deposit', '2024-01-01T00:00:00Z', 99, {wallet}, 1)")
    r = api.client.delete(f"{URL}{wallet}")
    assert r.status_code == 409
    assert r.json()["detail"] == "This account has transactions, so it can't be deleted. Hide it instead: its history stays."
    assert api.client.delete(f"{URL}{btc}").status_code == 204
    assert _rows(api.path, f"SELECT count(*) FROM accounts WHERE id IN ({usd}, {btc})") == [(0,)]
    assert _rows(api.path, "SELECT name FROM exchanges") == [("Exchange",)]


def test_an_exchanges_account_goes_even_if_its_exchange_row_is_gone(api):
    usd, btc = (a["id"] for a in _add(api, "exchange", "Kraken").json())
    _sql(api.path, "DELETE FROM exchanges WHERE name = 'Kraken'")  # only a hand-edited database
    assert api.client.delete(f"{URL}{usd}").status_code == 204
    assert _rows(api.path, f"SELECT count(*) FROM accounts WHERE id IN ({usd}, {btc})") == [(0,)]


def test_a_fee_goes_to_btc_fees_by_its_id(api):
    """The fee accounts are found by id (5, 6), whatever 5 is called: no
    second "BTC Fees" is made (#289)."""
    _sql(api.path, "UPDATE accounts SET name = 'Network fees' WHERE id = 5")
    for tx in (dict(type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=99, to_account_id=2,
                    amount="1", source="MyBTC", cost_basis_usd="40000"),
               dict(type="Transfer", timestamp="2024-02-01T12:00:00Z", from_account_id=2, to_account_id=4,
                    amount="0.5", fee_amount="0.0001", fee_currency="BTC", fee_usd="5.00")):
        assert api.client.post("/api/transactions", json=tx).status_code == 200
    assert _rows(api.path, "SELECT account_id FROM ledger_entries WHERE entry_type = 'FEE'") == [(5,)]
    assert _rows(api.path, "SELECT count(*) FROM accounts") == [(6,)]
