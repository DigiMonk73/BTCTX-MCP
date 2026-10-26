"""
Choosing which coins leave a wallet (#711, the owner's decision 29;
specific identification, Treas. Reg. §1.1012-1(j)(2)): a Transfer out of a
wallet, or a bitcoin Withdrawal from one, may name the coins that leave,
each by the Buy or Deposit that acquired them and how much from each,
together exactly what leaves. The engine then takes those coins instead of
the oldest, the network fee from the oldest of them first. The choice is
saved with the transaction, survives every recalculation, and a write that
would take chosen coins away is refused, naming the transaction that chose
them. Nothing chosen is per-wallet FIFO, as before (docs/temp/2.0-coin-choice.md,
C2a; 8.1's tests).

The figures are worked out by hand in each test: a piece of a lot costs its
running share of the lot's cost (#100), and a fee's value and a disposal's
proceeds are shared among the pieces the same way (#297).
"""

import importlib.util
import json
import shutil
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.models.transaction import BitcoinLot, LotDisposal, Transaction
from backend.schemas.transaction import TransactionCreate
from backend.services import outbound, past_years
from backend.services import transaction as tx_service
from backend.services.reports.form_8949 import build_form_8949_and_schedule_d
from backend.tests.conftest import default_login, stub_prices_at
from backend.tests.test_restore_checks import (  # noqa: F401  (live, reference_db: fixtures)
    OWNER, _at_revision, _restore, _sealed, _started_on, live, reference_db,
)

BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 2, 3, 4, 99
COLD = 100  # the first account added: a second wallet, "Cold Storage"
LEAVES = "2025-06-01T12:00:00Z"


@pytest.fixture
def owner(fresh_app, monkeypatch) -> TestClient:
    """A ledger of its own, logged in, the price $50,000 at every hour, a
    second wallet, and two acquisitions in Wallet: A1, 0.3 BTC for $300
    originally acquired 2017-03-01 (long-term), and A2, 0.5 BTC for $45,000
    deposited 2025-01-15 (short-term in mid-2025). client.ids names them."""
    stub_prices_at(monkeypatch, lambda when: Decimal("50000"))
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    r = client.post("/api/accounts/", json={"kind": "wallet", "name": "Cold Storage"})
    assert r.status_code == 201 and [a["id"] for a in r.json()] == [COLD], r.text
    client.Session = fresh_app
    client.ids = {
        "A1": deposit(client, "2023-01-10T12:00:00Z", "0.3", "300", acquired="2017-03-01"),
        "A2": deposit(client, "2025-01-15T12:00:00Z", "0.5", "45000"),
    }
    return client


def deposit(client, when: str, amount: str, basis: str, acquired: str | None = None, source: str = "MyBTC",
            to: int = WALLET) -> int:
    body = {"type": "Deposit", "timestamp": when, "from_account_id": EXTERNAL, "to_account_id": to,
            "amount": amount, "fee_amount": "0", "source": source, "cost_basis_usd": basis}
    if acquired:
        body["acquired_at"] = acquired
    return saved(client.post("/api/transactions", json=body))


def buy(client, when: str, amount: str, cost: str) -> int:
    return saved(client.post("/api/transactions", json={
        "type": "Buy", "timestamp": when, "from_account_id": BANK, "to_account_id": EXCHANGE_BTC,
        "amount": amount, "fee_amount": "0", "fee_currency": "USD", "cost_basis_usd": cost}))


def spend(when: str, amount: str, proceeds: str, fee: str = "0", chosen=None, frm: int = WALLET,
          purpose: str = "Spent") -> dict:
    body = {"type": "Withdrawal", "timestamp": when, "from_account_id": frm, "to_account_id": EXTERNAL,
            "amount": amount, "fee_amount": fee, "fee_currency": "BTC", "purpose": purpose,
            "proceeds_usd": proceeds}
    if chosen is not None:
        body["chosen_coins"] = chosen
    return body


def transfer(when: str, amount: str, fee: str = "0", to: int = COLD, frm: int = WALLET, chosen=None) -> dict:
    """A Transfer as the form sends it: amount is what left, its fee in it."""
    body = {"type": "Transfer", "timestamp": when, "from_account_id": frm, "to_account_id": to,
            "amount": amount, "fee_amount": fee, "fee_currency": "BTC"}
    if chosen is not None:
        body["chosen_coins"] = chosen
    return body


def coins(*pairs) -> list[dict]:
    """A choice: (acquisition's id, BTC) pairs."""
    return [{"acquired_txn_id": acquired, "btc": btc} for acquired, btc in pairs]


def saved(r) -> int:
    assert r.status_code == 200, r.text
    return r.json()["id"]


def pieces(client, tx_id: int) -> list[tuple]:
    """Its disposals, in order: (the lot's acquisition, date acquired, BTC,
    basis, proceeds, gain, term, a fee's)."""
    with client.Session() as db:
        rows = (db.query(LotDisposal).filter(LotDisposal.transaction_id == tx_id).order_by(LotDisposal.id).all())
        return [(row.lot.acquired_txn_id, row.lot.acquired_date.date().isoformat(), f"{row.disposed_btc:.8f}",
                 f"{row.disposal_basis_usd:.2f}", f"{row.proceeds_usd_for_that_portion:.2f}",
                 f"{row.realized_gain_usd:.2f}", row.holding_period, row.is_fee) for row in rows]


def figures_of(client, tx_id: int) -> tuple:
    with client.Session() as db:
        tx = db.get(Transaction, tx_id)
        return (f"{tx.cost_basis_usd:.2f}", f"{tx.proceeds_usd:.2f}", f"{tx.realized_gain_usd:.2f}",
                tx.holding_period)


def lots_in(client, account: int) -> list[tuple]:
    """The account's lots: (acquisition, date acquired, BTC left, BTC, cost, inherited)."""
    with client.Session() as db:
        lots = (db.query(BitcoinLot).join(Transaction, Transaction.id == BitcoinLot.created_txn_id)
                .filter(Transaction.to_account_id == account).order_by(BitcoinLot.acquired_date, BitcoinLot.id))
        return [(lot.acquired_txn_id, lot.acquired_date.date().isoformat(), f"{lot.remaining_btc:.8f}",
                 f"{lot.total_btc:.8f}", f"{lot.cost_basis_usd:.2f}", lot.inherited) for lot in lots]


def chosen_rows(client) -> list[tuple]:
    """The stored choices: (transaction, acquisition, BTC)."""
    with client.Session() as db:
        return [(tx, acquired, f"{Decimal(str(btc)):.8f}") for tx, acquired, btc in db.execute(text(
            "SELECT transaction_id, acquired_txn_id, btc FROM chosen_coins ORDER BY id"))]


def no_ids(rows: list[tuple]) -> list[tuple]:
    return [row[1:] for row in rows]


def moment(written: str) -> datetime:
    """A time the API writes, "…Z"."""
    return datetime.fromisoformat(written.replace("Z", "+00:00"))


# What leaves


def test_the_coins_chosen_leave_instead_of_the_oldest(owner):
    """Paying with 0.1 BTC (and a 0.0001 BTC fee, $5.00) chosen from A2: the
    fee and the amount come from A2's lot, short-term, at A2's cost ($90,000
    a BTC), not from A1's 2017 coins, which oldest first would take."""
    a1, a2 = owner.ids["A1"], owner.ids["A2"]
    s = saved(owner.post("/api/transactions", json=spend(LEAVES, "0.1", "10000", "0.0001", coins((a2, "0.1001")))))

    # The fee's piece: 45,000 x 0.0001 / 0.5 = $9.00 against its $5.00. The
    # amount's: the lot's running total to 0.1001 BTC, $9,009.00, less $9.00;
    # its proceeds the gross less the fee (a spend's fee is a cost of it)
    assert pieces(owner, s) == [
        (a2, "2025-01-15", "0.00010000", "9.00", "5.00", "-4.00", "SHORT", True),
        (a2, "2025-01-15", "0.10000000", "9000.00", "9995.00", "995.00", "SHORT", False),
    ]
    assert figures_of(owner, s) == ("9000.00", "9995.00", "995.00", "SHORT")
    assert lots_in(owner, WALLET) == [
        (a1, "2017-03-01", "0.30000000", "0.30000000", "300.00", False),
        (a2, "2025-01-15", "0.39990000", "0.50000000", "45000.00", False),
    ]
    with owner.Session() as db:
        rows = build_form_8949_and_schedule_d(2025, db)["short_term"]
    assert sorted((row["date_acquired"], f"{row['cost']:.2f}") for row in rows) == \
        [("01/15/2025", "9.00"), ("01/15/2025", "9000.00")]


def test_choosing_the_oldest_coins_gives_the_figures_of_no_choice(owner):
    s = saved(owner.post("/api/transactions", json=spend(LEAVES, "0.1", "10000", "0.0001")))
    oldest = (pieces(owner, s), figures_of(owner, s), lots_in(owner, WALLET))
    r = owner.put(f"/api/transactions/{s}", json=spend(LEAVES, "0.1", "10000", "0.0001",
                                                       coins((owner.ids["A1"], "0.1001"))))
    assert r.status_code == 200, r.text
    assert (pieces(owner, s), figures_of(owner, s), lots_in(owner, WALLET)) == oldest
    assert r.json()["chosen_coins"] == [{"acquired_txn_id": owner.ids["A1"], "btc": "0.10010000"}]


def test_the_fee_takes_the_oldest_of_the_coins_chosen_first_on_a_spend(owner):
    """Chosen: 0.00005 BTC of A1 and 0.10005 of A2. The fee (0.0001 BTC,
    $5.00) takes A1's coins, then A2's; the amount takes the rest of A2's.
    The fee's two pieces share its $5.00, and the amount's piece the spend's
    $9,995.00, exactly."""
    a1, a2 = owner.ids["A1"], owner.ids["A2"]
    s = saved(owner.post("/api/transactions", json=spend(
        LEAVES, "0.1", "10000", "0.0001", coins((a1, "0.00005"), (a2, "0.10005")))))
    assert pieces(owner, s) == [
        (a1, "2017-03-01", "0.00005000", "0.05", "2.50", "2.45", "LONG", True),
        (a2, "2025-01-15", "0.00005000", "4.50", "2.50", "-2.00", "SHORT", True),
        (a2, "2025-01-15", "0.10000000", "9000.00", "9995.00", "995.00", "SHORT", False),
    ]


def test_the_fee_takes_the_oldest_of_the_coins_chosen_first_on_a_transfer(owner):
    a1, a2 = owner.ids["A1"], owner.ids["A2"]
    t = saved(owner.post("/api/transactions", json=transfer(
        LEAVES, "0.2001", "0.0001", chosen=coins((a1, "0.00005"), (a2, "0.20005")))))
    assert pieces(owner, t) == [
        (a1, "2017-03-01", "0.00005000", "0.05", "2.50", "2.45", "LONG", True),
        (a2, "2025-01-15", "0.00005000", "4.50", "2.50", "-2.00", "SHORT", True),
    ]
    # What arrived: A2's 0.2 BTC, at its running share, $18,004.50 less $4.50
    assert lots_in(owner, COLD) == [(a2, "2025-01-15", "0.20000000", "0.20000000", "18000.00", False)]


def test_chosen_coins_arrive_with_their_date_cost_inheritance_and_acquisition(owner):
    """A Transfer choosing inherited A3 (0.01 BTC, $400) and 0.2001 of A2:
    the fee comes from A3's, the oldest chosen; both arrive in Cold Storage
    as they were, and a later spend there that chooses A2's takes those, not
    A3's older ones."""
    a2 = owner.ids["A2"]
    a3 = deposit(owner, "2022-01-10T12:00:00Z", "0.01", "400", acquired="2021-12-01", source="Inherited")
    t = saved(owner.post("/api/transactions", json=transfer(
        LEAVES, "0.2101", "0.0001", chosen=coins((a3, "0.01"), (a2, "0.2001")))))
    assert pieces(owner, t) == [(a3, "2021-12-01", "0.00010000", "4.00", "5.00", "1.00", "LONG", True)]
    assert lots_in(owner, COLD) == [
        (a3, "2021-12-01", "0.00990000", "0.00990000", "396.00", True),
        (a2, "2025-01-15", "0.20010000", "0.20010000", "18009.00", False),
    ]
    s = saved(owner.post("/api/transactions", json=spend(
        "2025-07-01T12:00:00Z", "0.05", "5000", frm=COLD, chosen=coins((a2, "0.05")))))
    # 18,009 x 0.05 / 0.2001 = $4,500.00
    assert pieces(owner, s) == [(a2, "2025-01-15", "0.05000000", "4500.00", "5000.00", "500.00", "SHORT", False)]


def test_one_acquisition_in_two_lots_is_chosen_across_both(owner):
    """A4, 1 BTC bought on the exchange for $100,000, reaches Wallet in two
    transfers, so Wallet holds it as two lots; 0.4 BTC chosen from A4 takes
    the first lot whole and 0.1 of the second."""
    a4 = buy(owner, "2025-02-01T12:00:00Z", "1", "100000")
    first = saved(owner.post("/api/transactions", json=transfer("2025-02-10T12:00:00Z", "0.3", frm=EXCHANGE_BTC,
                                                                to=WALLET)))
    second = saved(owner.post("/api/transactions", json=transfer("2025-02-20T12:00:00Z", "0.2", frm=EXCHANGE_BTC,
                                                                 to=WALLET)))
    s = saved(owner.post("/api/transactions", json=spend(LEAVES, "0.4", "40000", chosen=coins((a4, "0.4")))))
    assert pieces(owner, s) == [
        (a4, "2025-02-01", "0.30000000", "30000.00", "30000.00", "0.00", "SHORT", False),
        (a4, "2025-02-01", "0.10000000", "10000.00", "10000.00", "0.00", "SHORT", False),
    ]
    with owner.Session() as db:
        made = {lot.created_txn_id: lot.remaining_btc for lot in db.query(BitcoinLot).filter(
            BitcoinLot.acquired_txn_id == a4, BitcoinLot.created_txn_id.in_((first, second)))}
    assert made == {first: Decimal("0"), second: Decimal("0.1")}


# What the API takes and gives


def test_the_choice_and_its_day_are_given_back(owner):
    a2 = owner.ids["A2"]
    s = saved(owner.post("/api/transactions", json=spend(LEAVES, "0.1", "10000", "0.0001", coins((a2, "0.1001")))))
    one = owner.get(f"/api/transactions/{s}").json()
    assert one["chosen_coins"] == [{"acquired_txn_id": a2, "btc": "0.10010000"}]
    assert one["coins_chosen_at"].endswith("Z")
    assert moment(one["coins_chosen_at"]).date() == datetime.now(timezone.utc).date()
    listed = {tx["id"]: tx for tx in owner.get("/api/transactions").json()}
    assert listed[s]["chosen_coins"] == one["chosen_coins"]
    assert listed[a2]["chosen_coins"] is None and listed[a2]["coins_chosen_at"] is None


def test_the_list_reads_every_choice_in_one_query(owner):
    a2 = owner.ids["A2"]
    for day in ("01", "02", "03"):
        saved(owner.post("/api/transactions", json=spend(f"2025-06-{day}T12:00:00Z", "0.01", "1000",
                                                         chosen=coins((a2, "0.01")))))
    engine = owner.Session.kw["bind"]
    statements = []

    def seen(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", seen)
    try:
        assert owner.get("/api/transactions").status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", seen)
    assert sum("FROM chosen_coins" in s for s in statements) == 1


def test_a_restores_read_check_reads_every_choice_in_one_query(chose_a2):
    """A restore reads each table as the screens do (#460), each transaction
    through TransactionRead, which reads its chosen coins: in one query,
    not one per transaction (the review's)."""
    from backend.services import backup

    for day in ("02", "03"):
        saved(chose_a2.post("/api/transactions", json=spend(f"2025-06-{day}T12:00:00Z", "0.01", "1000",
                                                            chosen=coins((chose_a2.ids["A2"], "0.01")))))
    engine = chose_a2.Session.kw["bind"]
    statements = []

    def seen(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", seen)
    try:
        backup._read_as_the_app_does(engine)
    finally:
        event.remove(engine, "before_cursor_execute", seen)
    # The transactions' choices, and the chosen_coins table's own check
    assert sum("FROM chosen_coins" in s for s in statements) == 2


@pytest.mark.parametrize("make_body, detail", [
    (lambda ids: spend(LEAVES, "0.1", "10000", frm=EXCHANGE_BTC, chosen=coins((ids["A4"], "0.1"))),
     "Coins can be chosen only when they leave one of your wallets. An exchange's coins leave oldest first, as "
     "its Form 1099-DA reports them."),
    (lambda ids: {"type": "Sell", "timestamp": LEAVES, "from_account_id": EXCHANGE_BTC,
                  "to_account_id": EXCHANGE_USD, "amount": "0.1", "fee_amount": "0", "fee_currency": "USD",
                  "proceeds_usd": "10000", "chosen_coins": coins((ids["A4"], "0.1"))},
     "Coins can be chosen only when they leave one of your wallets. An exchange's coins leave oldest first, as "
     "its Form 1099-DA reports them."),
    (lambda ids: {"type": "Deposit", "timestamp": LEAVES, "from_account_id": EXTERNAL, "to_account_id": WALLET,
                  "amount": "0.1", "fee_amount": "0", "source": "MyBTC", "cost_basis_usd": "100",
                  "chosen_coins": coins((ids["A1"], "0.1"))},
     "Coins can be chosen only when they leave one of your wallets."),
    (lambda ids: transfer(LEAVES, "0.1", "0.0001", to=WALLET, chosen=coins((ids["A1"], "0.1"))),
     "A move within the same wallet records only its network fee, from the oldest coins: no coins are chosen."),
    (lambda ids: spend(LEAVES, "0.1", "10000", chosen=coins((ids["T"], "0.1"))),
     "Transaction {T} didn't acquire bitcoin: choose coins by the Buy or Deposit that acquired them."),
    (lambda ids: spend(LEAVES, "0.1", "10000", chosen=coins((ids["USD"], "0.1"))),
     "Transaction {USD} didn't acquire bitcoin: choose coins by the Buy or Deposit that acquired them."),
    (lambda ids: spend(LEAVES, "0.1", "10000", chosen=coins((9999, "0.1"))),
     "Transaction 9999 didn't acquire bitcoin: choose coins by the Buy or Deposit that acquired them."),
    # Beyond what SQLite stores: refused as any other id, never a 500 (the review's)
    (lambda ids: spend(LEAVES, "0.1", "10000", chosen=coins((2**70, "0.1"))),
     f"Transaction {2**70} didn't acquire bitcoin: choose coins by the Buy or Deposit that acquired them."),
    (lambda ids: spend(LEAVES, "0.1", "10000", chosen=coins((0, "0.1"))),
     "Transaction 0 didn't acquire bitcoin: choose coins by the Buy or Deposit that acquired them."),
    (lambda ids: spend(LEAVES, "0.1", "10000", "0.0001", coins((ids["A2"], "0.1"))),
     "The coins chosen add up to 0.10000000 BTC, but 0.10010000 BTC leaves Wallet (0.10000000 sent and "
     "0.00010000 network fee). Choose coins for all of it, or none to send the oldest first."),
    (lambda ids: spend(LEAVES, "0.1", "10000", chosen=coins((ids["A2"], "0.05"))),
     "The coins chosen add up to 0.05000000 BTC, but 0.10000000 BTC leaves Wallet. Choose coins for all of it, "
     "or none to send the oldest first."),
    (lambda ids: transfer(LEAVES, "0.2001", "0.0001", chosen=coins((ids["A2"], "0.3"))),
     "The coins chosen add up to 0.30000000 BTC, but 0.20010000 BTC leaves Wallet (0.20000000 arriving and "
     "0.00010000 network fee). Choose coins for all of it, or none to send the oldest first."),
    (lambda ids: spend(LEAVES, "0.1", "10000", chosen=coins((ids["A1"], "0.1"), (ids["A2"], "0"))),
     "The coins chosen from transaction {A2} must be more than 0 BTC."),
    (lambda ids: spend(LEAVES, "0.1", "10000", chosen=coins((ids["A2"], "0.05"), (ids["A2"], "0.05"))),
     "Transaction {A2} is named twice: name each Buy or Deposit once, with all the coins chosen from it."),
    (lambda ids: spend(LEAVES, "0.1", "10000", chosen=coins(*[(ids["A2"], "0.0001")] * 1001)),
     "At most 1,000 Buys or Deposits can be named in one choice of coins."),
])
def test_a_choice_the_rules_dont_allow_is_refused(owner, make_body, detail):
    ids = dict(owner.ids)
    ids["A4"] = buy(owner, "2025-02-01T12:00:00Z", "1", "100000")
    ids["T"] = saved(owner.post("/api/transactions", json=transfer("2025-02-10T12:00:00Z", "0.3", frm=EXCHANGE_BTC,
                                                                   to=WALLET)))
    ids["USD"] = saved(owner.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2025-02-11T12:00:00Z", "from_account_id": EXTERNAL,
        "to_account_id": BANK, "amount": "100", "fee_amount": "0"}))
    before = owner.get("/api/transactions").json()
    r = owner.post("/api/transactions", json=make_body(ids))
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == detail.format(**ids)
    assert owner.get("/api/transactions").json() == before


@pytest.mark.parametrize("body, wallet", [
    # Dated before A2 arrived (dated before others: the ledger is replayed)
    (spend("2025-01-01T12:00:00Z", "0.1", "10000"), "Wallet"),
    # A2's coins are all in Wallet, none in Cold Storage (dated last: no replay)
    (spend(LEAVES, "0.1", "10000", frm=COLD), "Cold Storage"),
])
def test_a_choice_its_wallet_doesnt_hold_then_is_refused(owner, body, wallet):
    """The transaction being saved has no id yet: its refusal names none."""
    a2 = owner.ids["A2"]
    before = owner.get("/api/transactions").json()
    r = owner.post("/api/transactions", json={**body, "chosen_coins": coins((a2, "0.1"))})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == (f"{wallet} holds 0.00000000 BTC of the coins from transaction {a2} (a Deposit "
                                  "of 2025-01-15) on this date, not the 0.10000000 BTC chosen.")
    assert owner.get("/api/transactions").json() == before


def test_an_edit_that_moves_a_choice_before_its_coins_is_refused(chose_a2):
    ids = chose_a2.ids
    r = chose_a2.put(f"/api/transactions/{ids['S']}", json={"timestamp": "2025-01-01T12:00:00Z"})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == (f"Wallet holds 0.00000000 BTC of the coins from transaction {ids['A2']} (a "
                                  "Deposit of 2025-01-15) on this date, not the 0.10010000 BTC chosen.")


def test_more_than_eight_places_is_refused(owner):
    r = owner.post("/api/transactions", json=spend(LEAVES, "0.1", "10000",
                                                   chosen=coins((owner.ids["A2"], "0.100000001"))))
    assert r.status_code == 422, r.text


# A write that takes chosen coins away is refused (call (i), Q2)


def not_held(chose: int, what: str, acquired: int, about: str, holds: str, chosen: str = "0.10010000") -> str:
    return (f"Transaction {chose} ({what}) chose {chosen} BTC of the coins from transaction {acquired}{about}, "
            f"but Wallet holds {holds} BTC of them then. Change that transaction's chosen coins first, or set it "
            f"back to oldest first.")


@pytest.fixture
def chose_a2(owner):
    """A spend on 2025-06-01 that chose 0.1001 BTC of A2's coins."""
    owner.ids["S"] = saved(owner.post("/api/transactions", json=spend(
        LEAVES, "0.1", "10000", "0.0001", coins((owner.ids["A2"], "0.1001")))))
    return owner


def test_deleting_the_purchase_is_refused(chose_a2):
    ids = chose_a2.ids
    before = chose_a2.get("/api/transactions").json()
    r = chose_a2.delete(f"/api/transactions/{ids['A2']}")
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "Not deleted: later transactions depend on this one. " + not_held(
        ids["S"], "a Withdrawal of 2025-06-01 from Wallet", ids["A2"], "", "0.00000000")
    assert chose_a2.get("/api/transactions").json() == before


@pytest.mark.parametrize("edit, dated, holds", [({"amount": "0.05"}, "2025-01-15", "0.05000000"),
                                                ({"timestamp": "2025-07-01T12:00:00Z"}, "2025-07-01", "0.00000000")])
def test_an_edit_of_the_purchase_that_takes_the_coins_away_is_refused(chose_a2, edit, dated, holds):
    """The purchase is named as the edit would make it."""
    ids = chose_a2.ids
    before = chose_a2.get("/api/transactions").json()
    r = chose_a2.put(f"/api/transactions/{ids['A2']}", json=edit)
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == not_held(ids["S"], "a Withdrawal of 2025-06-01 from Wallet", ids["A2"],
                                          f" (a Deposit of {dated})", holds)
    assert chose_a2.get("/api/transactions").json() == before


def test_an_earlier_transfer_that_takes_the_coins_first_is_refused(chose_a2):
    """Moving 0.75 BTC out of Wallet on 2025-03-01, oldest first, takes
    A1's 0.3 and 0.45 of A2's: the spend's chosen coins wouldn't be there."""
    ids = chose_a2.ids
    before = chose_a2.get("/api/transactions").json()
    r = chose_a2.post("/api/transactions", json=transfer("2025-03-01T12:00:00Z", "0.75"))
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "Not saved: with it, the account would lack BTC on its date or later. " + \
        not_held(ids["S"], "a Withdrawal of 2025-06-01 from Wallet", ids["A2"], " (a Deposit of 2025-01-15)",
                 "0.05000000")
    assert chose_a2.get("/api/transactions").json() == before


@pytest.fixture
def chose_a4(owner):
    """A4 bought on the exchange 2025-02-01 (1 BTC, $100,000); 0.3 BTC of it
    moved to Wallet on 2025-02-10; a spend from Wallet on 2025-06-01 that
    chose 0.1 BTC of A4's coins."""
    owner.ids["A4"] = buy(owner, "2025-02-01T12:00:00Z", "1", "100000")
    saved(owner.post("/api/transactions", json=transfer("2025-02-10T12:00:00Z", "0.3", frm=EXCHANGE_BTC, to=WALLET)))
    owner.ids["S"] = saved(owner.post("/api/transactions", json=spend(LEAVES, "0.1", "10000",
                                                                      chosen=coins((owner.ids["A4"], "0.1")))))
    return owner


def a4_not_held(ids) -> str:
    return not_held(ids["S"], "a Withdrawal of 2025-06-01 from Wallet", ids["A4"], " (a Buy of 2025-02-01)",
                    "0.00000000", chosen="0.10000000")


def test_a_forgotten_earlier_buy_on_the_exchange_is_refused(chose_a4):
    """A buy dated before the transfer: the exchange's oldest coins go
    first, so the transfer would bring that buy's coins to Wallet, not A4's."""
    before = chose_a4.get("/api/transactions").json()
    r = chose_a4.post("/api/transactions", json={
        "type": "Buy", "timestamp": "2025-01-20T12:00:00Z", "from_account_id": BANK, "to_account_id": EXCHANGE_BTC,
        "amount": "0.5", "fee_amount": "0", "fee_currency": "USD", "cost_basis_usd": "40000"})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "Not saved: with it, the account would lack BTC on its date or later. " + \
        a4_not_held(chose_a4.ids)
    assert chose_a4.get("/api/transactions").json() == before


def test_an_older_river_file_that_takes_the_coins_away_is_refused_whole(chose_a4):
    before = chose_a4.get("/api/transactions").json()
    r = chose_a4.post("/api/import/river/execute", json={"rows": [
        {"date": "2025-01-20T12:00:00Z", "type": "Buy", "amount": "0.5", "from_account": "Bank",
         "to_account": "Exchange BTC", "cost_basis_usd": "40000"},
        {"date": "2025-09-01T12:00:00Z", "type": "Buy", "amount": "0.1", "from_account": "Bank",
         "to_account": "Exchange BTC", "cost_basis_usd": "9000"},
    ]})
    assert r.status_code == 400, r.text
    assert a4_not_held(chose_a4.ids) in r.json()["detail"]
    assert "No transactions were saved" in r.json()["detail"]
    assert chose_a4.get("/api/transactions").json() == before


# An edit (calls (e) and (f))


def send_again(tx_id: int, btc: str = "0.10010000") -> str:
    return (f"Transaction {tx_id} has coins chosen for {btc} BTC leaving Wallet, and this changes what leaves: "
            "choose its coins again (chosen_coins), or set it back to oldest first (chosen_coins: null).")


@pytest.mark.parametrize("edit", [{"amount": "0.2"}, {"fee_amount": "0.0002"}, {"from_account_id": COLD},
                                  {"type": "Transfer", "to_account_id": COLD}])
def test_an_edit_that_changes_what_leaves_must_send_the_coins_again(chose_a2, edit):
    ids = chose_a2.ids
    before = chose_a2.get("/api/transactions").json()
    r = chose_a2.put(f"/api/transactions/{ids['S']}", json=edit)
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == send_again(ids["S"])
    assert chose_a2.get("/api/transactions").json() == before


def test_an_edit_sent_as_the_form_sends_it_must_send_the_coins_again(chose_a2):
    ids = chose_a2.ids
    r = chose_a2.put(f"/api/transactions/{ids['S']}", json=spend(LEAVES, "0.2", "10000", "0.0001"))
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == send_again(ids["S"])


def test_a_transfer_moved_into_its_own_wallet_must_send_the_coins_again(owner):
    t = saved(owner.post("/api/transactions", json=transfer(LEAVES, "0.2001", "0.0001",
                                                           chosen=coins((owner.ids["A2"], "0.2001")))))
    r = owner.put(f"/api/transactions/{t}", json={"to_account_id": WALLET})
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == send_again(t, "0.20010000")
    # To another account, the same coins leave: the choice is kept
    r = owner.put(f"/api/transactions/{t}", json={"to_account_id": EXCHANGE_BTC})
    assert r.status_code == 200, r.text
    assert r.json()["chosen_coins"] == [{"acquired_txn_id": owner.ids["A2"], "btc": "0.20010000"}]


def test_null_sets_it_back_to_oldest_first(chose_a2):
    ids = chose_a2.ids
    r = chose_a2.put(f"/api/transactions/{ids['S']}", json={"amount": "0.2", "chosen_coins": None})
    assert r.status_code == 200, r.text
    assert r.json()["chosen_coins"] is None and r.json()["coins_chosen_at"] is None
    assert [p[0] for p in pieces(chose_a2, ids["S"])] == [ids["A1"], ids["A1"]]
    assert chosen_rows(chose_a2) == []


def test_new_coins_are_saved_with_a_new_day_and_the_same_coins_keep_theirs(chose_a2):
    ids = chose_a2.ids
    first = chose_a2.get(f"/api/transactions/{ids['S']}").json()["coins_chosen_at"]

    # Another field, the choice sent back unchanged: its day stays (call (f))
    r = chose_a2.put(f"/api/transactions/{ids['S']}", json=spend(LEAVES, "0.1", "12000", "0.0001",
                                                                coins((ids["A2"], "0.10010000"))))
    assert r.status_code == 200, r.text
    assert r.json()["coins_chosen_at"] == first
    # Another field, the choice not sent: kept, with its day
    for edit in ({"proceeds_usd": "11000"}, {"purpose": "Gift"}, {"timestamp": "2025-06-02T12:00:00Z"}):
        r = chose_a2.put(f"/api/transactions/{ids['S']}", json=edit)
        assert r.status_code == 200, r.text
        assert r.json()["chosen_coins"] == [{"acquired_txn_id": ids["A2"], "btc": "0.10010000"}]
        assert r.json()["coins_chosen_at"] == first
    # New coins: a new day
    r = chose_a2.put(f"/api/transactions/{ids['S']}", json={
        "amount": "0.2", "chosen_coins": coins((ids["A1"], "0.0001"), (ids["A2"], "0.2"))})
    assert r.status_code == 200, r.text
    assert moment(r.json()["coins_chosen_at"]) > moment(first)
    assert no_ids(chosen_rows(chose_a2)) == [(ids["A1"], "0.00010000"), (ids["A2"], "0.20000000")]


# A choice survives


def test_a_choice_survives_recalculate_ledger_and_a_tax_timezone_change(chose_a2):
    ids = chose_a2.ids
    chosen = pieces(chose_a2, ids["S"])
    assert chose_a2.post("/api/transactions/recalculate").status_code == 200
    assert pieces(chose_a2, ids["S"]) == chosen
    r = chose_a2.put("/api/settings/tax-timezone", json={"timezone": "America/Chicago", "chosen": True})
    assert r.status_code == 200, r.text
    assert [p[:3] for p in pieces(chose_a2, ids["S"])] == [p[:3] for p in chosen]


def test_a_tax_timezone_that_reorders_the_coins_so_a_choice_runs_short_is_refused(owner):
    """In Cold Storage, D2 arrives 2025-03-02 05:00 UTC and D1 the next day,
    acquired 2025-03-02 (its lot at noon that day in the tax timezone).
    In UTC D2's coins are the older, so W1 (no choice) takes them and W2's
    choice of D1's is there. Kiritimati's noon (UTC+14) is the day before in
    UTC: D1's coins become the older, W1 would take them, and W2 would be
    short. The change is refused, naming W2, and nothing changes (Q2). Its
    dates are in the timezone the change would save, as the replay runs."""
    d2 = deposit(owner, "2025-03-02T05:00:00Z", "0.2", "2000", to=COLD)
    d1 = deposit(owner, "2025-03-03T12:00:00Z", "0.2", "4000", acquired="2025-03-02", to=COLD)
    saved(owner.post("/api/transactions", json=spend("2025-04-01T12:00:00Z", "0.2", "20000", frm=COLD)))
    w2 = saved(owner.post("/api/transactions", json=spend("2025-05-01T12:00:00Z", "0.2", "20000", frm=COLD,
                                                          chosen=coins((d1, "0.2")))))
    assert [p[0] for p in pieces(owner, w2)] == [d1] and d2
    before = owner.get("/api/transactions").json()
    r = owner.put("/api/settings/tax-timezone", json={"timezone": "Pacific/Kiritimati", "chosen": True})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == (
        f"Transaction {w2} (a Withdrawal of 2025-05-02 from Cold Storage) chose 0.20000000 BTC of the coins from "
        f"transaction {d1} (a Deposit of 2025-03-04), but Cold Storage holds 0.00000000 BTC of them then. Change "
        "that transaction's chosen coins first, or set it back to oldest first.")
    assert owner.get("/api/settings/tax-timezone").json()["timezone"] == "UTC"
    assert owner.get("/api/transactions").json() == before


def test_delete_all_leaves_no_choice(chose_a2):
    assert chosen_rows(chose_a2)
    assert chose_a2.delete("/api/transactions/delete_all", params={"confirm": "DELETE"}).status_code == 204
    assert chosen_rows(chose_a2) == []


def test_deleting_the_transaction_that_chose_deletes_its_choice(chose_a2):
    assert chose_a2.delete(f"/api/transactions/{chose_a2.ids['S']}").status_code == 204
    assert chosen_rows(chose_a2) == []


# Lots without their acquisition (call (j))


def forget_acquisitions(client) -> None:
    """The lots as migration 0101 leaves them: none knows its acquisition."""
    with client.Session() as db:
        db.execute(text("UPDATE bitcoin_lots SET acquired_txn_id = NULL"))
        db.commit()


def lots_without_acquisition(client) -> int:
    with client.Session() as db:
        return db.query(BitcoinLot).filter(BitcoinLot.acquired_txn_id.is_(None)).count()


def test_after_the_upgrade_a_choice_replays_the_ledger_first(owner):
    forget_acquisitions(owner)
    a2 = owner.ids["A2"]
    s = saved(owner.post("/api/transactions", json=spend(LEAVES, "0.1", "10000", "0.0001", coins((a2, "0.1001")))))
    assert [p[0] for p in pieces(owner, s)] == [a2, a2]
    assert lots_without_acquisition(owner) == 0


def test_a_transfer_dated_last_that_copied_the_blank_still_lets_a_choice_through(owner):
    forget_acquisitions(owner)
    saved(owner.post("/api/transactions", json=transfer("2025-05-01T12:00:00Z", "0.4")))  # dated last: no replay
    assert lots_without_acquisition(owner) == 4  # Wallet's two, and the two it put in Cold Storage
    a2 = owner.ids["A2"]
    s = saved(owner.post("/api/transactions", json=spend(LEAVES, "0.05", "5000", frm=COLD,
                                                         chosen=coins((a2, "0.05")))))
    # Cold Storage holds A1's 0.3 and A2's 0.1 (45,000 x 0.1 / 0.5 = $9,000): A2's are chosen
    assert pieces(owner, s) == [(a2, "2025-01-15", "0.05000000", "4500.00", "5000.00", "500.00", "SHORT", False)]


def test_such_a_write_counts_as_one_that_replays(owner):
    with_a_choice = TransactionCreate(**spend(LEAVES, "0.1", "10000", chosen=coins((owner.ids["A2"], "0.1")))) \
        .model_dump()
    without = TransactionCreate(**spend(LEAVES, "0.1", "10000")).model_dump()
    with owner.Session() as db:
        assert past_years.Write(past_years.ADD, with_a_choice).appends(db)
    forget_acquisitions(owner)
    with owner.Session() as db:
        assert not past_years.Write(past_years.ADD, with_a_choice).appends(db)
        assert past_years.Write(past_years.ADD, without).appends(db)


# The engine's hook (6.1): the coins held, before any are taken


def test_the_engine_hands_over_the_coins_held_before_taking_any(owner):
    """Each path that posts a transaction's lots hands the hook (C3's
    picker, 6.1) what the account holds just before the transaction takes
    any: one line per acquisition, oldest first, with its BTC and their
    cost then."""
    from backend.services.chosen_coins import HELD_HOOK

    def heard(db, write):
        seen = {}
        db.info[HELD_HOOK] = lambda tx, held: seen.setdefault(tx.id, held)
        try:
            tx = write(db)
            return [(h.acquired_txn_id, h.btc, h.cost_usd, h.acquired.date().isoformat(), h.inherited)
                    for h in seen[tx.id]]
        finally:
            db.rollback()

    as_held = [(owner.ids["A1"], Decimal("0.3"), Decimal("300.00"), "2017-03-01", False),
               (owner.ids["A2"], Decimal("0.5"), Decimal("45000.00"), "2025-01-15", False)]
    with owner.Session() as db:
        # Dated last: it posts its own lots
        assert heard(db, lambda db: tx_service.apply_create(
            TransactionCreate(**spend(LEAVES, "0.1", "10000")).model_dump(), db)) == as_held
        # Dated before another: the ledger is replayed
        saved(owner.post("/api/transactions", json=spend("2025-09-01T12:00:00Z", "0.01", "1000")))
        assert heard(db, lambda db: tx_service.apply_create(
            TransactionCreate(**transfer(LEAVES, "0.1")).model_dump(), db)) == as_held
        # An edit: the ledger is replayed
        s = saved(owner.post("/api/transactions", json=spend(LEAVES, "0.1", "10000")))
        assert heard(db, lambda db: tx_service.apply_update(s, {"amount": Decimal("0.2")}, db)) == as_held


# The past-year question (6.2)


def test_a_choice_added_in_an_earlier_year_asks_and_its_confirm_saves_it(owner, tax_year):
    s = saved(owner.post("/api/transactions", json=spend(LEAVES, "0.1", "10000", "0.0001")))
    tax_year(2026)
    edit = spend(LEAVES, "0.1", "10000", "0.0001", coins((owner.ids["A2"], "0.1001")))
    asked = owner.put(f"/api/transactions/{s}", json=edit)
    assert asked.status_code == 409, asked.text
    assert asked.json()["years"] == [2025]
    assert owner.get(f"/api/transactions/{s}").json()["chosen_coins"] is None
    r = owner.put(f"/api/transactions/{s}", json=edit, params={"confirm": asked.json()["confirm"]})
    assert r.status_code == 200, r.text
    assert r.json()["chosen_coins"] == [{"acquired_txn_id": owner.ids["A2"], "btc": "0.10010000"}]


def test_a_choice_in_this_year_saves_at_once(owner, tax_year):
    tax_year(2026)
    r = owner.post("/api/transactions", json=spend("2026-03-01T12:00:00Z", "0.1", "10000",
                                                   chosen=coins((owner.ids["A2"], "0.1"))))
    assert r.status_code == 200, r.text
    assert r.json()["chosen_coins"] == [{"acquired_txn_id": owner.ids["A2"], "btc": "0.10000000"}]


# The AI key: test_chosen_coins_ai_733.py (C5, Q4: the AI may choose coins)


# Backups and restores (8.5): the database step's extra checks

REFERENCE_1X = Path(__file__).parent / "fixtures" / "reference_1x.db"
BACKUP_PASSWORD = "backup-password"


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[2] / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # a dataclass looks its module up there
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def prices_off(monkeypatch):
    """No price asked for, as the reference figures were made (test_reference_1x.py)."""
    async def find_prices(day, full):
        return {}, False

    monkeypatch.setattr("backend.services.price_history.find_prices", find_prices)
    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings(price_source="off"))


def figures_after_a_replay(path_or_engine) -> dict:
    """A database's tax figures (scripts/reference_figures.py) once its
    whole ledger is replayed, as after Recalculate Ledger."""
    engine = path_or_engine if not isinstance(path_or_engine, Path) else \
        create_engine(f"sqlite:///{path_or_engine}", connect_args={"check_same_thread": False})
    figures = _script("reference_figures")
    try:
        with sessionmaker(bind=engine)() as db:
            tx_service.recalculate_all_transactions(db)
            db.commit()
            return json.loads(figures.dumps(figures.figures(db)))
    finally:
        if isinstance(path_or_engine, Path):
            engine.dispose()


def restored_figures(live, blob: bytes) -> dict:  # noqa: F811
    """Restore `blob` over this install, then its figures once replayed;
    every lot then knows its acquisition."""
    r = _restore(live.client, blob)
    assert r.status_code == 200, r.text
    assert live.client.post("/api/login", json=OWNER).status_code == 200  # a restore logs its browser out
    figures = figures_after_a_replay(live.engine)
    with live.engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM bitcoin_lots WHERE acquired_txn_id IS NULL")).scalar() == 0
    return figures


def test_a_1x_ledger_upgraded_through_0101_restores_with_its_figures(live, tmp_path, prices_off):  # noqa: F811
    upgraded = _started_on(REFERENCE_1X, tmp_path / "upgraded.db")  # 0001 to 0012, then 0100 and 0101
    before = figures_after_a_replay(upgraded)
    assert restored_figures(live, _sealed(upgraded.read_bytes())) == before
    # And the 1.x file as it is, which the restore upgrades
    assert restored_figures(live, _sealed(REFERENCE_1X.read_bytes())) == before


def test_an_alpha_2_backup_restores_into_this_build_with_its_figures(
        live, tmp_path, reference_db, prices_off):  # noqa: F811
    """2.0.0-alpha.2's schema is 0100: the reference ledger (2.0's multiple
    wallets, exchanges or accounts) taken back there, backed up and
    restored, gives the figures it gives here without its choices (#730's
    rows): alpha.2 holds none, so those rows take the oldest coins there."""
    alpha_2 = _at_revision(reference_db, tmp_path / "alpha2.db", "0100")
    current = tmp_path / "current.db"
    shutil.copy(reference_db, current)
    engine = create_engine(f"sqlite:///{current}")
    with engine.begin() as conn:
        assert conn.execute(text("DELETE FROM chosen_coins")).rowcount
        conn.execute(text("UPDATE transactions SET coins_chosen_at = NULL"))
    engine.dispose()
    before = figures_after_a_replay(current)
    assert restored_figures(live, _sealed(alpha_2.read_bytes())) == before
    with live.engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM chosen_coins")).scalar() == 0


def test_a_backup_holding_choices_restores_with_them(live, prices_off, monkeypatch):  # noqa: F811
    stub_prices_at(monkeypatch, lambda when: Decimal("50000"))
    client = live.client
    a5 = deposit(client, "2025-01-15T12:00:00Z", "0.5", "45000")
    saved(client.post("/api/transactions", json=transfer("2025-02-01T12:00:00Z", "0.5", frm=EXCHANGE_BTC, to=WALLET)))
    s = saved(client.post("/api/transactions", json=spend(LEAVES, "0.1", "10000", "0.0001", coins((a5, "0.1001")))))

    def stored() -> tuple:
        with live.engine.connect() as conn:
            return (conn.execute(text("SELECT * FROM chosen_coins ORDER BY id")).all(),
                    conn.execute(text("SELECT coins_chosen_at FROM transactions WHERE id = :s"), {"s": s}).scalar())

    choices = stored()
    assert choices[0] and choices[1]
    before = figures_after_a_replay(live.engine)
    blob = client.post("/api/backup/download", data={"password": BACKUP_PASSWORD})
    assert blob.status_code == 200, blob.text

    assert restored_figures(live, blob.content) == before
    assert stored() == choices
    with sessionmaker(bind=live.engine)() as db:
        disposals = db.query(LotDisposal).filter(LotDisposal.transaction_id == s).all()
        assert {d.lot.acquired_txn_id for d in disposals} == {a5}
