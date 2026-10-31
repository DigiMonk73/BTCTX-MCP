"""
The duplicate check of the River and AI imports on a large ledger (#379).
1.2.9's rule (#253) runs up to seven passes for River and three for the AI:
each row's transactions within the window are found by time once per call,
so the check stays fast, and the answers are the ones a scan of the whole
ledger gives.
"""

import copy
import random
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.models.account import Account
from backend.models.exchange import Exchange
from backend.models.transaction import Transaction
from backend.services import river_import
from backend.services.entry_import import ENTRY_RULE
from backend.services.river_import import RIVER_RULE, RiverProposal, annotate_duplicates
from backend.tests.conftest import init_test_db, remove_temp_db, temp_db_file

START = datetime(2020, 1, 1, tzinfo=timezone.utc)
LEDGER = 5_000
BUDGET = 2.0  # seconds; about 0.15 s on a Mac, 0.5 s on CI's runners


def database(transactions: list[Transaction]):
    """A database of its own holding `transactions`, with a second exchange
    and wallet beside 1.x's accounts (the passes across accounts, #707);
    its engine and path."""
    path = temp_db_file()
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    init_test_db(engine)
    with Session(engine) as db:
        db.add(Exchange(id=2, name="Kraken"))
        db.add_all([Account(id=100, user_id=1, name="Cold Storage", kind="wallet", currency="BTC"),
                    Account(id=102, user_id=1, name="Kraken USD", kind="exchange", currency="USD", exchange_id=2),
                    Account(id=103, user_id=1, name="Kraken BTC", kind="exchange", currency="BTC", exchange_id=2)])
        db.add_all(transactions)
        db.commit()
    return engine, path


@pytest.fixture(scope="module")
def large_ledger():
    """Buys 12 hours apart."""
    engine, path = database([
        Transaction(type="Buy", timestamp=START + i * timedelta(hours=12), from_account_id=1, to_account_id=4,
                    amount=Decimal("0.001"), cost_basis_usd=Decimal(30 + i % 50), fee_amount=Decimal(0),
                    fee_currency="USD")
        for i in range(LEDGER)
    ])
    yield engine
    engine.dispose()
    remove_temp_db(path)


def buys_between(count: int) -> list[RiverProposal]:
    """Buys between the ledger's, of another amount: new rows, which every
    pass looks at."""
    return [
        RiverProposal(row_number=i + 1, timestamp=START + i * timedelta(hours=12) + timedelta(hours=6),
                      river_tag=None, type="Buy", from_account_id=1, to_account_id=4, amount=Decimal("0.002"),
                      cost_basis_usd=Decimal(30))
        for i in range(count)
    ]


@pytest.mark.parametrize("rule, rows", [(RIVER_RULE, 2_000), (ENTRY_RULE, 500)], ids=["River", "AI"])
def test_a_large_check_stays_fast(large_ledger, rule, rows):
    """River's every pass on 2,000 rows, and the AI key's 500 rows (its
    limit), against 5,000 entries."""
    proposals = buys_between(rows)
    with Session(large_ledger) as db:
        started = time.perf_counter()
        annotate_duplicates(proposals, db, rule=rule)
        elapsed = time.perf_counter() - started
    assert all(p.status == river_import.STATUS_NEW for p in proposals)
    assert elapsed < BUDGET, f"{elapsed:.2f} s"


# The same answers as looking through the whole ledger
KINDS = [  # type, from, to
    ("Buy", 1, 4), ("Buy", 3, 4), ("Sell", 4, 3), ("Deposit", 99, 2), ("Deposit", 99, 4),
    ("Withdrawal", 2, 99), ("Withdrawal", 4, 99), ("Transfer", 4, 2), ("Transfer", 2, 4),
    # A second exchange and wallet (#707)
    ("Buy", 1, 103), ("Sell", 103, 102), ("Transfer", 103, 100), ("Transfer", 4, 103), ("Deposit", 99, 100),
]
AMOUNTS = [Decimal(a) for a in ("0.001", "0.0011", "0.002", "0.0025", "0.01")]
LABELS = [None, "Interest", "Reward", "Spent", "Gift"]


def random_moment(rng: random.Random) -> datetime:
    """Within 90 days, to the second: some share a minute, an hour, a window."""
    return START + timedelta(seconds=rng.randrange(90 * 86400))


def random_ledger(rng: random.Random, count: int) -> list[Transaction]:
    """Transactions of every kind, a quarter of them recorded twice (the
    same everything, or 6 hours later), so that equally close matches tie:
    at the same time, or on either side of a row."""
    txs = []
    for _ in range(count):
        kind, from_id, to_id = rng.choice(KINDS)
        fee = rng.choice([Decimal(0), Decimal("0.0001")])
        txs.append(dict(
            type=kind, timestamp=random_moment(rng), from_account_id=from_id, to_account_id=to_id,
            amount=rng.choice(AMOUNTS), cost_basis_usd=rng.choice([Decimal(30), Decimal(31)]),
            fee_amount=fee, fee_currency="BTC" if fee else "USD", source=rng.choice(LABELS),
            purpose=rng.choice(LABELS),
        ))
    txs += [dict(tx, timestamp=tx["timestamp"] + rng.choice([timedelta(0), timedelta(hours=6)]))
            for tx in rng.sample(txs, count // 4)]
    rng.shuffle(txs)
    return [Transaction(**tx) for tx in txs]


def like(rng: random.Random, value, others):
    """Mostly `value`, sometimes another."""
    return value if rng.random() < 0.7 else rng.choice(others)


def random_rows(rng: random.Random, ledger: list[Transaction], count: int) -> list[RiverProposal]:
    """Mostly copies of recorded transactions (some moved by seconds, hours,
    days or exactly the window, some given as a date alone, some with a
    field changed), and others."""
    rows = []
    for i in range(count):
        tx = rng.choice(ledger)
        kind, from_id, to_id = like(rng, (tx.type, tx.from_account_id, tx.to_account_id), KINDS)
        moment = tx.timestamp.replace(tzinfo=timezone.utc) + rng.choice(
            [timedelta(0), timedelta(0), timedelta(seconds=20), timedelta(hours=3), timedelta(hours=-30),
             timedelta(days=3), river_import.SIMILAR_WINDOW, -river_import.SIMILAR_WINDOW])
        day = moment.date() if rng.random() < 0.15 else None
        rows.append(RiverProposal(
            row_number=i + 1, timestamp=datetime(moment.year, moment.month, moment.day, 12, tzinfo=timezone.utc)
            if day else moment, river_tag=None, type=kind, from_account_id=from_id, to_account_id=to_id,
            amount=like(rng, tx.amount, AMOUNTS), cost_basis_usd=like(rng, tx.cost_basis_usd, [Decimal(30), Decimal(31)]),
            fee_amount=tx.fee_amount, fee_currency=tx.fee_currency, source=like(rng, tx.source, LABELS),
            purpose=like(rng, tx.purpose, LABELS), day=day,
        ))
    return rows


def answers(proposals: list[RiverProposal]) -> list[tuple]:
    return [(p.status, p.matched_tx_id, p.discrepancy, getattr(p, "near_amount", False)) for p in proposals]


@pytest.mark.parametrize("seed", range(4))
def test_the_answers_are_the_ones_the_whole_ledger_gives(seed, monkeypatch):
    """Random ledgers and rows, each rule, with and without the similar
    passes and with some transactions reserved: the same status, match and
    note for every row as when every pass looked through the whole ledger."""
    rng = random.Random(seed)
    ledger = random_ledger(rng, 320)
    engine, path = database(ledger)
    try:
        with Session(engine) as db:
            recorded = db.query(Transaction).all()
            rows = random_rows(rng, recorded, 300)
            reserved = {tx.id for tx in rng.sample(recorded, 20)}
            for rule in (RIVER_RULE, ENTRY_RULE):
                for exact_only in (False, True):
                    found_by_time = copy.deepcopy(rows)
                    annotate_duplicates(found_by_time, db, exact_only, rule, reserved)
                    with monkeypatch.context() as m:
                        m.setattr(river_import, "_nearby", lambda ps, existing: {id(p): existing for p in ps})
                        whole_ledger = copy.deepcopy(rows)
                        annotate_duplicates(whole_ledger, db, exact_only, rule, reserved)
                    assert answers(found_by_time) == answers(whole_ledger)
                    assert any(p.status != river_import.STATUS_NEW for p in whole_ledger)
    finally:
        engine.dispose()
        remove_temp_db(path)


def test_the_window_is_measured_in_utc_across_a_clock_change():
    """#391's review: a row given in a zone with daylight saving measured
    its 48 hours by that zone's clock, an hour off across the change. A
    Buy 47.5 hours before a row at noon in Chicago the day after the
    spring change is within it."""
    from zoneinfo import ZoneInfo

    row = datetime(2024, 3, 11, 12, tzinfo=ZoneInfo("America/Chicago"))
    buy = row.astimezone(timezone.utc) - timedelta(hours=47.5)
    low, high = river_import._window(row)
    assert low.tzinfo is high.tzinfo is timezone.utc
    assert low <= buy and high - low == 2 * river_import.SIMILAR_WINDOW


@pytest.mark.parametrize("date", ["0001-01-01 00:00:00", "9999-12-31 23:59:59"])
def test_a_river_row_at_the_ends_of_the_calendar_is_previewed(auth_client, date):
    """#391's review: the window around a row dated in year 1 or 9999 ran
    past Python's dates, and the whole preview failed (500). Such a row is
    previewed as new; the import refuses it by name."""
    river = ("Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag\n"
             f"{date},25.00,USD,0.00030000,BTC,,,Buy\n")
    r = auth_client.post("/api/import/river/preview", files={"file": ("river.csv", river.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    assert [p["status"] for p in r.json()["proposals"]] == [river_import.STATUS_NEW]
