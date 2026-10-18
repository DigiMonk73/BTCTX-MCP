"""
backend/tests/test_date_alone_match_472.py

#472: the AI import's duplicate check gave a recorded payout to a row sent
as a date alone (noon, the whole day) before a timed row of that day
after noon, so the timed row, an exact copy of it, was saved as new, at
its own time and price. A timed row's exact minute is matched before a
date alone's whole day: the date-alone row is the one saved, at noon.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.tests.conftest import stub_prices_at

CLIENT = None


@pytest.fixture(autouse=True, scope="module")
def _set_client(auth_client):
    global CLIENT
    CLIENT = auth_client


@pytest.fixture(autouse=True)
def _hour_prices(monkeypatch):
    """The hour's price: 50,000 plus 100 for each UTC hour, so a value says which hour priced it."""
    stub_prices_at(monkeypatch, lambda when: 50000 + 100 * when.astimezone(timezone.utc).hour)


@pytest.fixture(autouse=True)
def _clean_ledger():
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")


PAYOUT = {
    "type": "Deposit", "amount": "1", "from_account": "External", "to_account": "Wallet",
    "source": "Interest", "cost_basis_usd": "100.00",
}
DAY = "2025-03-20"


def row(time: str | None = None, **changes) -> dict:
    """The payout as the AI sends it: at `time` (UTC) of DAY, or as the date alone."""
    return dict(PAYOUT, date=f"{DAY}T{time}Z" if time else DAY, **changes)


def record(time: str) -> int:
    out = CLIENT.post("/api/import/entries/execute", json={"rows": [row(time)]})
    assert out.status_code == 200 and out.json()["imported_count"] == 1, out.text
    return out.json()["created"][0]["id"]


def preview(rows: list[dict]) -> list[tuple[str, int | None]]:
    out = CLIENT.post("/api/import/entries/preview", json={"rows": rows})
    assert out.status_code == 200, out.text
    return [(r["status"], r["matched_transaction_id"]) for r in out.json()["results"]]


def execute(rows: list[dict]) -> dict:
    out = CLIENT.post("/api/import/entries/execute", json={"rows": rows})
    assert out.status_code == 200, out.text
    return out.json()


def saved_after(known: set[int]) -> list[dict]:
    return [tx for tx in CLIENT.get("/api/transactions").json() if tx["id"] not in known]


def utc_time(tx: dict) -> str:
    moment = datetime.fromisoformat(tx["timestamp"].replace("Z", "+00:00"))
    return moment.astimezone(timezone.utc).strftime("%H:%M:%S")


def in_order(rows: list[dict], reverse: bool) -> list[dict]:
    return rows[::-1] if reverse else rows


ORDERS = pytest.mark.parametrize("reverse", [False, True], ids=["date alone first", "date alone last"])


@ORDERS
def test_the_afternoon_row_is_the_recorded_one_and_the_date_alone_row_is_saved_at_noon(reverse):
    """#472, step 2: recorded at 15:00; the 15:00 row is its duplicate, the
    date-alone row is new, saved at noon. Sent again, nothing more."""
    three = record("15:00:00")
    rows = in_order([row(), row("15:00:00")], reverse)
    expected = in_order([("ready", None), ("duplicate", three)], reverse)
    assert preview(rows) == expected
    assert execute(rows)["imported_count"] == 1
    [new] = saved_after({three})
    assert utc_time(new) == "12:00:00"
    assert execute(rows)["imported_count"] == 0


@ORDERS
def test_the_afternoon_row_is_the_recorded_one_in_the_tax_timezone_too(reverse):
    """In Chicago a date alone is noon there (17:00 UTC in March), and a
    payout recorded at 15:00 there (20:00 UTC) is the 15:00 row's."""
    assert CLIENT.put("/api/settings/tax-timezone", json={"timezone": "America/Chicago", "chosen": True}).status_code == 200
    try:
        three = record("20:00:00")
        rows = in_order([row(), row("20:00:00")], reverse)
        assert preview(rows) == in_order([("ready", None), ("duplicate", three)], reverse)
        assert execute(rows)["imported_count"] == 1
        [new] = saved_after({three})
        assert utc_time(new) == "17:00:00"
    finally:
        CLIENT.put("/api/settings/tax-timezone", json={"timezone": "UTC", "chosen": True})


@ORDERS
def test_the_morning_row_is_the_recorded_one_and_the_date_alone_row_is_saved_at_noon(reverse):
    """#472, step 3 (the mirror, right before the fix too): recorded at 09:00."""
    nine = record("09:00:00")
    rows = in_order([row(), row("09:00:00")], reverse)
    assert preview(rows) == in_order([("ready", None), ("duplicate", nine)], reverse)
    assert execute(rows)["imported_count"] == 1
    [new] = saved_after({nine})
    assert utc_time(new) == "12:00:00"


@pytest.mark.parametrize("order", [(0, 1, 2), (2, 1, 0), (1, 0, 2), (1, 2, 0)])
def test_with_two_copies_each_timed_row_is_its_own_and_the_date_alone_row_is_saved_at_noon(order):
    """#472, step 4: recorded at 09:00 and 15:00; a date-alone row, a 09:00
    row and a 15:00 row, in several orders. Each timed row is its own
    copy; the date-alone row is saved at noon, once."""
    nine, three = record("09:00:00"), record("15:00:00")
    sent = [(row(), ("ready", None)), (row("09:00:00"), ("duplicate", nine)), (row("15:00:00"), ("duplicate", three))]
    rows, expected = zip(*(sent[i] for i in order))
    assert preview(list(rows)) == list(expected)
    assert execute(list(rows))["imported_count"] == 1
    [new] = saved_after({nine, three})
    assert utc_time(new) == "12:00:00"
    assert execute(list(rows))["imported_count"] == 0


@pytest.mark.parametrize("recorded", ["09:00:00", "15:00:00"])
@ORDERS
def test_a_value_left_blank_is_noons_price(recorded, reverse):
    """#472, step 5: the basis left blank is filled from the hour's price.
    Whichever side of noon the recorded payout is, the new one is valued
    at noon's price ($51,200), never the timed row's hour's."""
    known = {record(recorded)}
    rows = in_order([row(cost_basis_usd=None), row(recorded, cost_basis_usd=None)], reverse)
    assert execute(rows)["imported_count"] == 1
    [new] = saved_after(known)
    assert utc_time(new) == "12:00:00"
    assert Decimal(new["cost_basis_usd"]) == Decimal("51200.00")


@ORDERS
def test_the_timed_row_named_as_another_is_saved_beside_the_date_alone_row_once(reverse):
    """The user says the 15:00 row, its preview's duplicate, is another
    payout (not_a_duplicate_of): both rows are saved, the date-alone row
    at noon and the named row at 15:00, and sent again, nothing more."""
    three = record("15:00:00")
    named = row("15:00:00", not_a_duplicate_of=three)
    rows = in_order([row(), named], reverse)
    assert preview(rows) == [("ready", None), ("ready", None)]
    assert [execute(rows)["imported_count"] for _ in range(3)] == [2, 0, 0]
    assert sorted(utc_time(tx) for tx in saved_after({three})) == ["12:00:00", "15:00:00"]
