"""
backend/tests/test_named_rows_any_order_510.py

#510: identical rows, each named as the transaction its preview matched
(not_a_duplicate_of), were all saved in the preview's order and all left
out ("recorded again") in another: the duplicate check gave each row its
nearest copy whatever it names. Each named row now takes the transaction
it names first, so a name means the same in any order.
"""

import random

import pytest

from backend.tests.conftest import stub_daily_prices

CLIENT = None


@pytest.fixture(autouse=True, scope="module")
def _set_client(auth_client):
    global CLIENT
    CLIENT = auth_client


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 100000.0)


@pytest.fixture(autouse=True)
def _clean_ledger():
    wipe()
    yield
    wipe()


def wipe() -> None:
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")


PAYOUT = {
    "type": "Deposit", "amount": "1", "from_account": "External", "to_account": "Wallet",
    "source": "Interest", "cost_basis_usd": "100.00",
}
DAY = "2025-03-20"


def row(time: str | None = None, **changes) -> dict:
    """The payout as the AI sends it: at `time` (UTC) of DAY, or as the date alone."""
    return dict(PAYOUT, date=f"{DAY}T{time}Z" if time else DAY, **changes)


def record(time: str, amount: str = "1") -> int:
    """The payout recorded at `time` through the transactions API, which
    saves an identical copy too."""
    out = CLIENT.post("/api/transactions", json={
        "type": "Deposit", "timestamp": f"{DAY}T{time}Z", "from_account_id": 99, "to_account_id": 2,
        "amount": amount, "source": "Interest", "cost_basis_usd": "100.00", "fee_amount": "0", "fee_currency": "BTC"})
    assert out.status_code == 200, out.text
    return out.json()["id"]


def preview(rows: list[dict]) -> list[dict]:
    out = CLIENT.post("/api/import/entries/preview", json={"rows": rows})
    assert out.status_code == 200, out.text
    return out.json()["results"]


def execute(rows: list[dict]) -> int:
    out = CLIENT.post("/api/import/entries/execute", json={"rows": rows})
    assert out.status_code == 200, out.text
    return out.json()["imported_count"]


def tx_count() -> int:
    return len(CLIENT.get("/api/transactions").json())


@pytest.mark.parametrize("reverse", [False, True], ids=["preview's order", "the other order"])
def test_identical_rows_each_named_as_its_match_are_saved_in_any_order(reverse):
    """#510's steps: X at 15:00:40 and Y at noon recorded; two rows of the
    payout given as the date alone are Y's and X's duplicates. The user
    says both are other payouts: each names its match. Both are saved in
    either order, and sent again, nothing more."""
    x, y = record("15:00:40"), record("12:00:00")
    assert [(r["status"], r["matched_transaction_id"]) for r in preview([row(), row()])] == [
        ("duplicate", y), ("duplicate", x)]
    rows = [row(not_a_duplicate_of=y), row(not_a_duplicate_of=x)]
    rows = rows[::-1] if reverse else rows
    assert [r["status"] for r in preview(rows)] == ["ready", "ready"]
    assert [execute(rows) for _ in range(3)] == [2, 0, 0]
    assert tx_count() == 4


@pytest.mark.parametrize("reverse", [False, True], ids=["preview's order", "the other order"])
def test_a_timed_and_a_date_alone_row_each_named_are_saved_in_any_order(reverse):
    """The same with a timed row: copies at 15:00 and 10:00; the 15:00
    row's match is the 15:00 copy, the date-alone row's the 10:00 one, and
    the user says both are other payouts."""
    three, ten = record("15:00:00"), record("10:00:00")
    assert [(r["status"], r["matched_transaction_id"]) for r in preview([row("15:00:00"), row()])] == [
        ("duplicate", three), ("duplicate", ten)]
    rows = [row("15:00:00", not_a_duplicate_of=three), row(not_a_duplicate_of=ten)]
    rows = rows[::-1] if reverse else rows
    assert [execute(rows) for _ in range(3)] == [2, 0, 0]
    assert tx_count() == 4


TIMES = ["09:00:00", "10:00:00", "10:00:30", "13:00:00", "15:00:00"]


def saved_in_both_orders(rng: random.Random) -> tuple[list[dict], list[int], list[int]] | None:
    """A random ledger of identical copies, and rows (timed or a date
    alone, two amounts), some of the preview's duplicates named as their
    match, as the AI would send them. The request is saved three times on
    that ledger as previewed, and three times on the same ledger in the
    other order: (the rows, saved each time in the preview's order, in the
    other). None for a request the preview refuses as unclear (#497)."""
    ledger = [(rng.choice(TIMES), rng.choice(["1", "2"])) for _ in range(rng.randrange(1, 5))]
    rows = [row(rng.choice([*TIMES, None]), amount=rng.choice(["1", "2"])) for _ in range(rng.randrange(2, 5))]
    name_some = rng.random() < 0.8
    to_name = [name_some and rng.random() < 0.9 for _ in rows]  # the same rows named in both orders
    saved = []
    for reverse in (False, True):
        wipe()
        for when, amount in ledger:
            record(when, amount)
        named = [
            dict(r, not_a_duplicate_of=res["matched_transaction_id"]) if res["status"] == "duplicate" and name else r
            for r, res, name in zip(rows, preview(rows), to_name)
        ]
        if any(res["status"] == "invalid" for res in preview(named)):
            return None
        sent = named[::-1] if reverse else named
        saved.append([execute(sent) for _ in range(3)])
    return named, saved[0], saved[1]


@pytest.mark.parametrize("seed", range(3))
def test_a_request_saves_the_same_in_any_order(seed):
    """#510 on random ledgers: a request without #497's mix saves as many
    rows in the other order as in the preview's, and sent again, nothing
    more. (#510's shape is all the rows of a payout named, each as its
    own match.)"""
    rng = random.Random(seed)
    tried = 0
    while tried < 25:
        out = saved_in_both_orders(rng)
        if out is None:
            continue
        tried += 1
        rows, as_previewed, other_order = out
        assert as_previewed[1:] == [0, 0] and other_order[1:] == [0, 0], (rows, as_previewed, other_order)
        assert as_previewed[0] == other_order[0], (rows, as_previewed, other_order)
