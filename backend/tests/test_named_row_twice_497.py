"""
backend/tests/test_named_row_twice_497.py

#497: a row the user named as another transaction (not_a_duplicate_of)
beside an identical row without a name was saved again, or not, by the
rows' order alone: the request reads the same as a first send naming a
third payout and as a send of two payouts the ledger already holds. The
owner's rule (2026-10-17): refuse to guess. The preview marks such rows
unclear, saying which and what to do, and an add refuses them until the AI
names each row or sends the named one in a request of its own.
"""

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
    """The payout recorded at `time` through the transactions API, which
    saves an identical copy too."""
    out = CLIENT.post("/api/transactions", json={
        "type": "Deposit", "timestamp": f"{DAY}T{time}Z", "from_account_id": 99, "to_account_id": 2,
        "amount": "1", "source": "Interest", "cost_basis_usd": "100.00", "fee_amount": "0", "fee_currency": "BTC"})
    assert out.status_code == 200, out.text
    return out.json()["id"]


def preview(rows: list[dict]) -> list[dict]:
    out = CLIENT.post("/api/import/entries/preview", json={"rows": rows})
    assert out.status_code == 200, out.text
    return out.json()["results"]


def execute(rows: list[dict]):
    """The add's answer: the number saved, or the refusal's words."""
    out = CLIENT.post("/api/import/entries/execute", json={"rows": rows})
    if out.status_code == 400:
        return out.json()["detail"]
    assert out.status_code == 200, out.text
    return out.json()["imported_count"]


def tx_count() -> int:
    return len(CLIENT.get("/api/transactions").json())


def in_order(rows: list[dict], reverse: bool) -> list[dict]:
    return rows[::-1] if reverse else rows


ORDERS = pytest.mark.parametrize("reverse", [False, True], ids=["named last", "named first"])


def assert_unclear(rows: list[dict], named: int, plain: list[int], tx_id: int) -> None:
    """The preview marks the named row (1-based) and its identical rows
    unclear, the named row saying what to do, and an add, sent three
    times, refuses each time and saves nothing."""
    before = tx_count()
    results = preview(rows)
    assert [r["status"] for r in results] == ["invalid"] * len(rows)
    [said] = results[named - 1]["errors"]
    assert said.startswith(f"Unclear: row {named} says it isn't tx #{tx_id} (not_a_duplicate_of)")
    assert f"send each with not_a_duplicate_of: {tx_id}" in said and f"send row {named} in a request of its own" in said
    for n in plain:
        assert results[n - 1]["errors"] == [f"Unclear: identical to row {named}, which says it isn't tx #{tx_id}: see row {named}."]
    for _ in range(3):
        refused = execute(rows)
        assert isinstance(refused, str) and "Unclear" in refused and refused.endswith("No transactions were saved.")
    assert tx_count() == before


def issue_steps_one_and_two() -> tuple[int, int]:
    """#497's steps 1 and 2: a payout recorded at 15:00:40 (X); sent as the
    date alone, it's X's duplicate, and named as another (the user says
    so) it's saved at noon (Y)."""
    x = record("15:00:40")
    [res] = preview([row()])
    assert (res["status"], res["matched_transaction_id"]) == ("duplicate", x)
    assert execute([row(not_a_duplicate_of=x)]) == 1
    [y] = [tx["id"] for tx in CLIENT.get("/api/transactions").json() if tx["id"] != x]
    return x, y


@ORDERS
def test_the_issues_steps_3_and_4_are_refused_in_either_order(reverse):
    """#497, steps 3 and 4: the two payouts the ledger now holds, sent
    again, one named as before. One order saved a third payout, the other
    nothing; now neither saves anything, and the preview says why."""
    x, _y = issue_steps_one_and_two()
    rows = in_order([row(), row(not_a_duplicate_of=x)], reverse)
    named = 1 if reverse else 2
    assert_unclear(rows, named, [3 - named], x)
    assert tx_count() == 2


@ORDERS
def test_the_same_request_as_a_first_send_naming_a_third_payout_is_refused_too(reverse):
    """The on-label first send #497 describes, which reads the same: the
    ledger holds X and Y, recorded on their own; the preview says one row
    is Y's duplicate and the other X's, and the user says the X one is a
    third payout. Saving it or not is a guess either way."""
    x, y = record("15:00:40"), record("12:00:00")
    results = preview([row(), row()])
    assert [(r["status"], r["matched_transaction_id"]) for r in results] == [("duplicate", y), ("duplicate", x)]
    rows = in_order([row(), row(not_a_duplicate_of=x)], reverse)
    assert_unclear(rows, 1 if reverse else 2, [2 if reverse else 1], x)


@ORDERS
def test_a_timed_row_named_beside_a_date_alone_row_of_its_day_is_refused(reverse):
    """The shape #472's fix left (#472's comment): two 15:00 copies, the
    second saved for a row named as another than the first, then sent
    beside the payout given as a date alone."""
    first = record("15:00:00")
    record("15:00:00")
    rows = in_order([row(), row("15:00:00", not_a_duplicate_of=first)], reverse)
    assert_unclear(rows, 1 if reverse else 2, [2 if reverse else 1], first)


def test_every_row_identical_to_the_named_one_is_said():
    """Two plain rows beside the named one, and a row of another amount,
    which isn't identical: it's checked as usual, but nothing is saved."""
    x = record("15:00:00")
    other = row(amount="2")
    rows = [row(), row(not_a_duplicate_of=x), row("15:00:30"), other]
    results = preview(rows)
    assert [r["status"] for r in results] == ["invalid", "invalid", "invalid", "ready"]
    assert results[1]["errors"][0].startswith(f"Unclear: row 2 says it isn't tx #{x} (not_a_duplicate_of), but rows 1 and 3")
    assert isinstance(execute(rows), str) and tx_count() == 1


def test_any_id_counts_as_a_name():
    """The check reads the request alone: a row naming a transaction that
    isn't its duplicate beside an identical row is refused too."""
    buy = CLIENT.post("/api/transactions", json={
        "type": "Buy", "timestamp": "2025-03-01T10:00:00Z", "from_account_id": 1, "to_account_id": 4,
        "amount": "0.5", "cost_basis_usd": "10000", "fee_amount": "0", "fee_currency": "USD"}).json()["id"]
    record("15:00:00")
    assert_unclear([row(), row(not_a_duplicate_of=buy)], 2, [1], buy)


@ORDERS
def test_rows_each_named_save_those_the_ledger_doesnt_hold_once(reverse):
    """A way out (#277's case): X recorded, the preview says one of two
    identical rows is X's duplicate, and the user says neither is X. Each
    named, both are saved, and sent again, nothing more."""
    x = record("15:00:00")
    assert [r["status"] for r in preview([row(), row()])] == ["duplicate", "ready"]
    rows = in_order([row(not_a_duplicate_of=x), row(not_a_duplicate_of=x)], reverse)
    assert [r["status"] for r in preview(rows)] == ["ready", "ready"]
    assert [execute(rows) for _ in range(3)] == [2, 0, 0]
    assert tx_count() == 3


@ORDERS
def test_after_the_issues_steps_each_row_named_saves_one_and_the_named_row_alone_none(reverse):
    """The two ways out after #497's steps 1 and 2 (X, and Y saved for the
    named row). If neither row is X, one is Y and the other a third payout:
    each named, one is saved, once. If one of them is X, the named row
    sent alone is found again (Y), and the plain row alone is X or Y."""
    x, y = issue_steps_one_and_two()
    each = in_order([row(not_a_duplicate_of=x), row(not_a_duplicate_of=x)], reverse)
    assert [execute(each) for _ in range(3)] == [1, 0, 0]
    assert tx_count() == 3
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")
    x, y = issue_steps_one_and_two()
    [alone] = preview([row(not_a_duplicate_of=x)])
    assert (alone["status"], alone["matched_transaction_id"]) == ("duplicate", y)
    assert any("Recorded again" in w for w in alone["warnings"])
    assert [execute([row(not_a_duplicate_of=x)]), execute([row()])] == [0, 0]
    assert tx_count() == 2


@pytest.mark.parametrize("other", [
    row("10:00:00"), row(amount="2"), row(source="Reward"), row(to_account="Exchange BTC", source="Reward"),
    dict(row(), date="2025-03-21"),
], ids=["another minute", "another amount", "another source", "another source and account", "another day"])
def test_a_named_row_beside_rows_not_identical_to_it_goes_as_before(other):
    """A request without the mix is checked as before: the named 15:00 row
    is saved, the other row as its own duplicate check says."""
    x = record("15:00:00")
    rows = [row("15:00:00", not_a_duplicate_of=x), other]
    results = preview(rows)
    assert results[0]["status"] == "ready" and results[1]["status"] in ("ready", "possible_duplicate")
    assert execute(rows) == 2 and execute(rows) == 0
