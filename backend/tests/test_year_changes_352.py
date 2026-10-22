"""
What a write changes, tax year by tax year (5.8, B6b-4: services/
year_changes.py): Ledger Review's comparison of stored figures, plus each
disposal's Form 8949 box and column (b), compared even when every dollar
matches, and each row's tax year in the tax timezone; the rows that move in
an earlier year, listed as Ledger Review lists its items.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import year_changes
from backend.services.tax_time import get_tax_timezone
from backend.tests.conftest import default_login

BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 2, 3, 4, 99


@pytest.fixture
def client(fresh_app) -> TestClient:
    c = TestClient(app)
    assert c.post("/api/login", json=default_login()).status_code == 200
    return c


def add(client, **row) -> int:
    row.setdefault("fee_amount", "0")
    row.setdefault("fee_currency", "USD" if row["type"] in ("Buy", "Sell") else "BTC")
    r = client.post("/api/transactions", json=row)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def edit(client, tx_id: int, **fields) -> None:
    r = client.put(f"/api/transactions/{tx_id}", json=fields)
    assert r.status_code == 200, r.text


def figures(fresh_app) -> dict:
    with fresh_app() as db:
        return year_changes.figures(db, get_tax_timezone(db))


def listed(fresh_app) -> dict:
    with fresh_app() as db:
        return year_changes.listed(db, get_tax_timezone(db))


def buy_then_sell(client, sold="2025-02-03T12:00:00Z") -> tuple[int, int]:
    add(client, type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=EXTERNAL,
        to_account_id=EXCHANGE_USD, amount="50000", source="N/A")
    buy = add(client, type="Buy", timestamp="2024-01-10T12:00:00Z", from_account_id=EXCHANGE_USD,
              to_account_id=EXCHANGE_BTC, amount="1", cost_basis_usd="40000")
    sell = add(client, type="Sell", timestamp=sold, from_account_id=EXCHANGE_BTC,
               to_account_id=EXCHANGE_USD, amount="1", proceeds_usd="45000")
    return buy, sell


def test_each_rows_tax_year_and_its_disposals_boxes(client, fresh_app):
    buy, sell = buy_then_sell(client)
    found = figures(fresh_app)
    assert (found[buy]["year"], found[sell]["year"]) == (2024, 2025)
    assert found[buy]["boxes"] == []
    assert found[sell]["boxes"] == [["K", "01/10/2024"]]  # an exchange's 2025 sale, long-term
    assert found[sell]["realized_gain_usd"] == Decimal("5000")  # Ledger Review's figures are there too


def test_the_tax_year_is_the_tax_timezones(client, fresh_app):
    _, sell = buy_then_sell(client, sold="2026-01-01T03:00:00Z")
    assert figures(fresh_app)[sell]["year"] == 2026
    assert client.put("/api/settings/tax-timezone", json={"timezone": "America/Chicago", "chosen": True}).is_success
    assert figures(fresh_app)[sell]["year"] == 2025  # 9 pm on New Year's Eve in Chicago


def test_a_basis_that_moves_moves_the_sale_and_the_lot(client, fresh_app):
    buy, sell = buy_then_sell(client)
    before = figures(fresh_app)
    edit(client, buy, cost_basis_usd="41000")
    moved = year_changes.moved(before, figures(fresh_app))
    assert set(moved) == {buy, sell}
    assert moved[sell]["cost_basis_usd"] == (Decimal("40000"), Decimal("41000"))
    assert moved[sell]["realized_gain_usd"] == (Decimal("5000"), Decimal("4000"))
    assert "boxes" not in moved[sell] and "year" not in moved[sell]


def test_a_box_that_moves_with_every_dollar_the_same(client, fresh_app):
    _, sell = buy_then_sell(client)
    before = figures(fresh_app)
    edit(client, sell, broker_reporting="none")  # no 1099-DA for it: noncovered, not reported
    assert year_changes.moved(before, figures(fresh_app)) == {sell: {"boxes": ("K", "L")}}


def test_a_date_acquired_that_moves_with_every_dollar_the_same(client, fresh_app):
    deposit = add(client, type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=EXTERNAL,
                  to_account_id=WALLET, amount="1", source="MyBTC", cost_basis_usd="10000",
                  acquired_at="2020-01-01")
    gift = add(client, type="Withdrawal", timestamp="2025-03-01T12:00:00Z", from_account_id=WALLET,
               to_account_id=EXTERNAL, amount="0.5", purpose="Spent", proceeds_usd="30000")
    before = figures(fresh_app)
    edit(client, deposit, acquired_at="2020-02-01")
    moved = year_changes.moved(before, figures(fresh_app))
    assert moved[gift] == {"acquired": ("01/01/2020", "02/01/2020")}
    assert set(moved[deposit]) == {"lot_split"}  # the lot it made, dated otherwise


def test_a_row_that_moves_to_another_tax_year(client, fresh_app):
    _, sell = buy_then_sell(client, sold="2025-12-30T12:00:00Z")
    before = figures(fresh_app)
    edit(client, sell, timestamp="2026-01-02T12:00:00Z")
    assert year_changes.moved(before, figures(fresh_app))[sell] == {"year": (2025, 2026)}


def test_dollars_moved_to_another_year_move_no_figure(client, fresh_app):
    cash = add(client, type="Deposit", timestamp="2026-01-03T12:00:00Z", from_account_id=EXTERNAL,
               to_account_id=BANK, amount="100", source="N/A")
    before = figures(fresh_app)
    edit(client, cash, timestamp="2025-06-01T12:00:00Z")
    assert year_changes.moved(before, figures(fresh_app)) == {}
    assert client.delete(f"/api/transactions/{cash}").status_code == 204
    assert year_changes.moved(before, figures(fresh_app)) == {}  # nor deleted, nor (the other way) added


def test_a_row_added_or_deleted(client, fresh_app):
    _, sell = buy_then_sell(client)
    before = figures(fresh_app)
    assert client.delete(f"/api/transactions/{sell}").status_code == 204
    without = figures(fresh_app)
    assert year_changes.moved(before, without) == {sell: {"deleted": True}}
    assert year_changes.moved(without, before) == {sell: {"added": True}}


def test_nothing_moves_nothing_listed(client, fresh_app):
    buy_then_sell(client)
    assert year_changes.moved(figures(fresh_app), figures(fresh_app)) == {}


def test_the_earlier_years_rows_as_ledger_review_lists_them(client, fresh_app):
    buy, sell = buy_then_sell(client, sold="2025-12-30T12:00:00Z")
    later = add(client, type="Deposit", timestamp="2026-03-02T12:00:00Z", from_account_id=EXTERNAL,
                to_account_id=BANK, amount="100", source="N/A")
    rows, before = listed(fresh_app), figures(fresh_app)
    moved = {sell: {"year": (2025, 2026)}, buy: {"deleted": True}, later: {"added": True}}
    after = {k: v for k, v in before.items() if k != buy}
    after[sell] = {**before[sell], "year": 2026}
    items = year_changes.earlier_year_items(rows, moved, before, after, this_year=2026)
    assert [(i["id"], i["years"], i["change"]) for i in items] == [
        (buy, [2024], "Deleted."),
        (sell, [2025, 2026], "Tax year 2025 → 2026."),
    ]  # date order; the row only in 2026 isn't listed
    assert {k: items[1][k] for k in ("date", "type", "amount", "unit", "accounts", "issue")} == {
        "date": "2025-12-30 12:00", "type": "Sell", "amount": "1.00000000", "unit": "BTC",
        "accounts": ["Exchange BTC", "Exchange USD"], "issue": year_changes.ISSUE}
    assert year_changes.earlier_year_items(rows, moved, before, after, this_year=2024) == []


@pytest.mark.parametrize("diff, text", [
    ({"added": True}, "Added."),
    ({"deleted": True}, "Deleted."),
    ({"realized_gain_usd": (Decimal("10"), Decimal("12"))}, "gain 10.00 -> 12.00."),
    ({"boxes": ("G", "H")}, "Form 8949 box G → H."),
    ({"realized_gain_usd": (Decimal("10"), Decimal("12")), "boxes": ("G", "H, K"),
      "acquired": ("01/02/2025", "INHERITED"), "year": (2025, 2026)},
     "gain 10.00 -> 12.00. Form 8949 box G → H, K. Form 8949 date acquired 01/02/2025 → INHERITED. "
     "Tax year 2025 → 2026."),
    ({"lot_rows": ([], [1])}, "Its rows, lot by lot, would be split differently; its totals stay the same."),
])
def test_what_changes_in_words(diff, text):
    assert year_changes.change_text(diff) == text
