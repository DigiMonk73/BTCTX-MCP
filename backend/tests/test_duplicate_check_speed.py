"""
The duplicate check of the River and AI imports on a large ledger (#379).
1.2.9's rule (#253) runs up to seven passes for River and three for the AI,
and each pass looked through the whole ledger for every row: 2,000 rows
against 2,000 entries took about 13 s. Each row's transactions within the
window are now found once, by time, and the answers are the same.
"""

import copy
import random
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.models.transaction import Transaction
from backend.services import river_import
from backend.services.entry_import import ENTRY_RULE
from backend.services.river_import import RIVER_RULE, RiverProposal, annotate_duplicates
from backend.tests.conftest import init_test_db, remove_temp_db, temp_db_file

START = datetime(2020, 1, 1, tzinfo=timezone.utc)
LEDGER = 5_000
BUDGET = 2.0  # seconds; about 0.1 s here, 13 s before


def database(transactions: list[Transaction]):
    """A database of its own holding `transactions`; its engine and path."""
    path = temp_db_file()
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    init_test_db(engine)
    with Session(engine) as db:
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
]
AMOUNTS = [Decimal(a) for a in ("0.001", "0.0011", "0.002", "0.0025", "0.01")]
LABELS = [None, "Interest", "Reward", "Spent", "Gift"]


def random_moment(rng: random.Random) -> datetime:
    """Within 90 days, to the second: some share a minute, an hour, a window."""
    return START + timedelta(seconds=rng.randrange(90 * 86400))


def random_ledger(rng: random.Random, count: int) -> list[Transaction]:
    """Transactions of every kind, a quarter of them recorded twice (the
    same everything), so that equally close matches tie."""
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
    txs += rng.sample(txs, count // 4)
    rng.shuffle(txs)
    return [Transaction(**tx) for tx in txs]


def like(rng: random.Random, value, others):
    """Mostly `value`, sometimes another."""
    return value if rng.random() < 0.7 else rng.choice(others)


def random_rows(rng: random.Random, ledger: list[Transaction], count: int) -> list[RiverProposal]:
    """Mostly copies of recorded transactions (some moved by seconds, hours
    or days, some given as a date alone, some with a field changed), and
    others."""
    rows = []
    for i in range(count):
        tx = rng.choice(ledger)
        kind, from_id, to_id = like(rng, (tx.type, tx.from_account_id, tx.to_account_id), KINDS)
        moment = tx.timestamp.replace(tzinfo=timezone.utc) + rng.choice(
            [timedelta(0), timedelta(0), timedelta(seconds=20), timedelta(hours=3), timedelta(hours=-30),
             timedelta(days=3)])
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
