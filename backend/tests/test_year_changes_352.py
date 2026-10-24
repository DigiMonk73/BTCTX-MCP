"""
What a write changes, tax year by tax year (2.0 spec 5.8, 5.15; card B6b
#352): Ledger Review's snapshot of each transaction's stored figures, plus
its lot disposals' Form 8949 boxes and column (b), plus its tax year.
Compared even when every dollar matches: a covered sale can turn noncovered
with the same gain (G to H), and two lots of the same cost and term can
swap. Dollars alone change no tax year's figures.

Here each change is saved for real (the tests' tax year is 2009, so nothing
asks), with the figures taken before and after it.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.main import app
from backend.services import year_changes
from backend.services.tax_time import get_tax_timezone
from backend.tests.conftest import default_login, stub_prices_at

BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 2, 3, 4, 99


@pytest.fixture
def client(fresh_app, monkeypatch):
    stub_prices_at(monkeypatch, lambda when: Decimal("50000"))
    c = TestClient(app)
    assert c.post("/api/login", json=default_login()).status_code == 200
    c.Session = fresh_app
    return c


def save(client, **body) -> int:
    r = client.post("/api/transactions", json={"fee_amount": "0", **body})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def edit(client, tx_id: int, **body) -> None:
    r = client.put(f"/api/transactions/{tx_id}", json=body)
    assert r.status_code == 200, r.text


def figures(client) -> dict:
    with client.Session() as db:
        return year_changes.figures(db, get_tax_timezone(db))


def changes_of(client, change) -> dict:
    """What `change()` moves, per transaction."""
    before = figures(client)
    change()
    return year_changes.moved(before, figures(client))


def deposit(client, when: str, amount: str = "1", basis: str = "1000", **more) -> int:
    return save(client, type="Deposit", from_account_id=EXTERNAL, to_account_id=EXCHANGE_BTC, amount=amount,
                timestamp=when, source="MyBTC", cost_basis_usd=basis, **more)


def sell(client, when: str, amount: str = "0.5", proceeds: str = "30000", **more) -> int:
    return save(client, type="Sell", from_account_id=EXCHANGE_BTC, to_account_id=EXCHANGE_USD, amount=amount,
                timestamp=when, proceeds_usd=proceeds, **more)


def test_a_box_that_moves_with_every_dollar_the_same(client):
    deposit(client, "2024-01-10T12:00:00Z")
    sale = sell(client, "2025-03-01T12:00:00Z")  # an exchange sale of 2025: H, no basis reported
    moved = changes_of(client, lambda: edit(client, sale, broker_reporting="basis"))
    assert moved == {sale: {"diff": {"boxes": (["K"], ["J"])}, "years": [2025]}}
    assert year_changes.change_text(moved[sale]["diff"]) == "Form 8949 box K -> J."


def test_a_date_acquired_that_moves(client):
    lot = deposit(client, "2024-06-01T12:00:00Z", acquired_at="2024-01-05")
    sale = sell(client, "2024-12-01T12:00:00Z")
    moved = changes_of(client, lambda: edit(client, lot, acquired_at="2024-02-05"))
    assert moved[sale]["diff"] == {"acquired": (["01/05/2024"], ["02/05/2024"])}
    assert year_changes.change_text(moved[sale]["diff"]) == "Form 8949 column (b), date acquired 01/05/2024 -> 02/05/2024."
    assert moved[lot]["diff"].keys() == {"lot_split"}  # the lot it made is dated otherwise; its cost stays
    assert set(moved) == {lot, sale}


def test_two_lots_of_the_same_cost_that_swap(client):
    first = deposit(client, "2024-01-10T12:00:00Z")
    deposit(client, "2024-02-10T12:00:00Z")
    sale = sell(client, "2024-06-01T12:00:00Z")  # FIFO: the January lot
    moved = changes_of(client, lambda: edit(client, first, timestamp="2024-03-10T12:00:00Z"))
    assert moved[sale]["diff"] == {"acquired": (["01/10/2024"], ["02/10/2024"])}  # same cost, same term


def test_a_row_moved_into_another_tax_year_lists_both(client):
    deposit(client, "2023-01-10T12:00:00Z")
    sale = sell(client, "2025-12-31T12:00:00Z")  # long-term either way, the same gain
    moved = changes_of(client, lambda: edit(client, sale, timestamp="2026-01-02T12:00:00Z"))
    assert moved[sale] == {"diff": {"year": (2025, 2026)}, "years": [2025, 2026]}
    assert year_changes.change_text(moved[sale]["diff"]) == "Tax year 2025 -> 2026."


def test_dollars_moved_to_another_year_change_nothing(client):
    cash = save(client, type="Deposit", from_account_id=EXTERNAL, to_account_id=BANK, amount="500",
                timestamp="2024-05-01T12:00:00Z", source="N/A")
    assert changes_of(client, lambda: edit(client, cash, timestamp="2025-05-01T12:00:00Z")) == {}


def test_a_row_added_or_deleted_with_figures_and_one_without(client):
    deposit(client, "2024-01-10T12:00:00Z")
    added = {}
    moved = changes_of(client, lambda: added.update(sale=sell(client, "2024-06-01T12:00:00Z", proceeds="30000")))
    assert moved == {added["sale"]: {"diff": {"added": True}, "years": [2024]}}
    assert year_changes.change_text(moved[added["sale"]]["diff"], figures(client)[added["sale"]]) == (
        "Added: proceeds 30000.00; basis 500.00; gain 29500.00; taxable gain incl. network fees 29500.00.")

    cash = {}
    assert changes_of(client, lambda: cash.update(id=save(
        client, type="Deposit", from_account_id=EXTERNAL, to_account_id=BANK, amount="500",
        timestamp="2024-05-01T12:00:00Z", source="N/A"))) == {}

    before = figures(client)
    gone = changes_of(client, lambda: client.delete(f"/api/transactions/{added['sale']}"))
    assert gone == {added["sale"]: {"diff": {"deleted": True}, "years": [2024]}}
    assert year_changes.change_text(gone[added["sale"]]["diff"], before[added["sale"]]) == (
        "Deleted: proceeds 30000.00; basis 500.00; gain 29500.00; taxable gain incl. network fees 29500.00.")


def test_figures_that_move_say_so_in_ledger_reviews_words(client):
    deposit(client, "2024-01-10T12:00:00Z")
    sale = sell(client, "2024-06-01T12:00:00Z", proceeds="30000")
    moved = changes_of(client, lambda: edit(client, sale, proceeds_usd="31000"))
    assert year_changes.change_text(moved[sale]["diff"]) == (
        "proceeds 30000.00 -> 31000.00; gain 29500.00 -> 30500.00; taxable gain incl. network fees 29500.00 -> "
        "30500.00.")


def test_only_rows_reaching_an_earlier_year_are_kept_and_their_years_are_given(client):
    lot = deposit(client, "2024-01-10T12:00:00Z", amount="2", basis="2000")
    sale_2024 = sell(client, "2024-06-01T12:00:00Z")
    sale_2026 = sell(client, "2026-03-01T12:00:00Z")
    moved = changes_of(client, lambda: edit(client, lot, cost_basis_usd="4000"))
    assert set(moved) == {lot, sale_2024, sale_2026}
    earlier = year_changes.reaching(moved, 2026)
    assert set(earlier) == {lot, sale_2024}
    assert year_changes.years(earlier) == [2024]


def test_a_gift_like_withdrawal_compares_its_purpose_and_value_a_dollar_one_doesnt(client):
    deposit(client, "2024-01-10T12:00:00Z")
    gift = save(client, type="Withdrawal", from_account_id=EXCHANGE_BTC, to_account_id=EXTERNAL, amount="0.01",
                timestamp="2024-06-01T12:00:00Z", purpose="Gift", fmv_usd="500")
    moved = changes_of(client, lambda: edit(client, gift, purpose="Lost", fmv_usd="400"))
    assert moved[gift]["diff"]["given"] == (("Gift", "500.00"), ("Lost", "400.00"))
    with client.Session() as db:
        db.execute(text("INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount,"
                        " fee_amount, fee_currency, purpose, fmv_usd) VALUES (990, 'Withdrawal',"
                        " '2024-07-01T12:00:00Z', 1, 99, '100', '0', 'USD', 'Gift', '100')"))
        db.commit()
    assert figures(client)[990]["given"] is None  # a dollar withdrawal's leftover fields (#449)
