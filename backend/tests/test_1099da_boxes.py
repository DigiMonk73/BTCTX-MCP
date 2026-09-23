"""
backend/tests/test_1099da_boxes.py

Form 8949 box selection under the Form 1099-DA rules, from real ledger data:
  2025: exchange (River) Sells are on a 1099-DA without basis -> H / K
  2026+: Sells of lots bought on the exchange on/after 2026-01-01 -> G / J
         (covered); lots transferred in from elsewhere stay H / K
  Self-custody spends and network-fee disposals: no 1099 -> I / L
  Through 2024: C / F
Plus: each box gets its own 8949 page and its own Schedule D line.
"""

import io
from decimal import Decimal

import pytest
from pypdf import PdfReader
from sqlalchemy.orm import sessionmaker

from backend.services.reports.form_8949 import (
    build_form_8949_and_schedule_d,
    map_schedule_d_fields,
)

CLIENT = None
ENGINE = None
BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 2, 3, 4, 99


@pytest.fixture(autouse=True, scope="module")
def _setup(auth_client, test_engine):
    global CLIENT, ENGINE
    CLIENT, ENGINE = auth_client, test_engine


@pytest.fixture(autouse=True)
def _clean():
    CLIENT.delete("/api/transactions/delete_all")
    yield
    CLIENT.delete("/api/transactions/delete_all")


def tx(**data):
    r = CLIENT.post("/api/transactions", json=data)
    assert r.status_code == 200, r.text
    return r.json()


def buy(date, amount="1.0", basis="20000"):
    return tx(type="Buy", timestamp=f"{date}T12:00:00Z", from_account_id=BANK,
              to_account_id=EXCHANGE_BTC, amount=amount, cost_basis_usd=basis)


def sell(date, amount):
    return tx(type="Sell", timestamp=f"{date}T12:00:00Z", from_account_id=EXCHANGE_BTC,
              to_account_id=EXCHANGE_USD, amount=amount, gross_proceeds_usd="1000.00")


def to_wallet(date, amount):
    return tx(type="Transfer", timestamp=f"{date}T12:00:00Z", from_account_id=EXCHANGE_BTC,
              to_account_id=WALLET, amount=amount, fee_amount="0.0001", fee_currency="BTC")


def spend(date, amount, account=WALLET):
    return tx(type="Withdrawal", timestamp=f"{date}T12:00:00Z", from_account_id=account,
              to_account_id=EXTERNAL, amount=amount, purpose="Spent", proceeds_usd="500.00")


def report(year):
    db = sessionmaker(bind=ENGINE)()
    try:
        return build_form_8949_and_schedule_d(year, db)
    finally:
        db.close()


def boxes(rows):
    return sorted({r["box"] for r in rows})


def test_2024_uses_c_and_f():
    buy("2023-01-10")
    sell("2024-02-01", "0.1")          # long
    buy("2024-03-01")
    sell("2024-04-01", "0.1")          # FIFO -> 2023 lot, long
    spend_long = spend("2024-05-01", "0.1", account=EXCHANGE_BTC)
    data = report(2024)
    assert boxes(data["short_term"] + data["long_term"]) in (["F"], ["C", "F"])
    assert spend_long


def test_2025_exchange_sale_is_h_and_self_custody_spend_is_i():
    buy("2025-01-10")
    sell("2025-02-01", "0.1")                  # River sale -> 1099-DA, no basis
    to_wallet("2025-03-01", "0.5")             # network fee disposal -> no 1099
    spend("2025-04-01", "0.1")                 # cold-storage spend -> no 1099
    data = report(2025)
    short = data["short_term"]
    assert "H" in boxes(short) and "I" in boxes(short)
    sale_rows = [r for r in short if r["box"] == "H"]
    assert len(sale_rows) == 1 and sale_rows[0]["proceeds"] == Decimal("1000.00")


def test_2025_long_term_exchange_sale_is_k():
    buy("2023-06-01")
    sell("2025-02-01", "0.1")
    assert boxes(report(2025)["long_term"]) == ["K"]


def test_2026_covered_lot_is_g_transferred_in_lot_is_h():
    # Bought on the exchange in 2026 and sold there -> covered -> G
    buy("2026-01-05", amount="0.3")
    sell("2026-02-01", "0.1")
    assert boxes(report(2026)["short_term"]) == ["G"]


def test_2026_lot_transferred_in_from_wallet_is_noncovered():
    buy("2026-01-05", amount="0.5")
    to_wallet("2026-01-06", "0.5")                              # leaves the broker
    tx(type="Transfer", timestamp="2026-01-20T12:00:00Z", from_account_id=WALLET,
       to_account_id=EXCHANGE_BTC, amount="0.4", fee_amount="0.0001", fee_currency="BTC")
    sell("2026-02-01", "0.1")                                    # transferred-in lot
    short = report(2026)["short_term"]
    assert [r["box"] for r in short if r["proceeds"] == Decimal("1000.00")] == ["H"]


def test_2026_pre_2026_lot_is_noncovered():
    buy("2025-12-20")
    sell("2026-02-01", "0.1")
    assert boxes(report(2026)["short_term"]) == ["H"]


def test_schedule_d_lines_follow_boxes():
    buy("2023-06-01", amount="0.5")                    # long-term lot
    buy("2025-01-10", amount="1.0")
    sell("2025-02-01", "0.1")                          # FIFO -> 2023 lot: K (line 9)
    to_wallet("2025-03-01", "0.5")                     # fee: long lot -> L (line 10)
    # Wallet holds 0.3999 of the 2023 lot then 0.1 of the 2025 lot (FIFO):
    spend("2025-04-01", "0.45")                        # -> L (line 10) + I (line 3)
    lines = report(2025)["schedule_d"]["lines"]
    assert set(lines) == {"9", "10", "3"}
    fields = map_schedule_d_fields(report(2025)["schedule_d"], year=2025)
    assert any(".Row9[0]." in k for k in fields)
    assert any(".Row3[0]." in k for k in fields)
    assert not any(".Row2[0]." in k for k in fields)


def test_2025_pdf_has_separate_pages_per_box():
    buy("2025-01-10")
    sell("2025-02-01", "0.1")                  # H
    to_wallet("2025-03-01", "0.5")
    spend("2025-04-01", "0.1")                 # I
    r = CLIENT.get("/api/reports/irs_reports", params={"year": 2025})
    assert r.status_code == 200, r.text[:300]
    pages = PdfReader(io.BytesIO(r.content)).pages
    # two 8949 sheets (H and I, 2 pages each) + Schedule D (2 pages)
    assert len(pages) == 6


def test_covered_cutoff_uses_tax_timezone_date():
    # 03:00 UTC on Jan 1 2026 is still Dec 31 2025 in Chicago: the form prints
    # an acquisition date of 12/31/2025, so the lot is noncovered (H), not G.
    assert CLIENT.put("/api/settings/tax-timezone", json={"timezone": "America/Chicago"}).status_code == 200
    try:
        tx(type="Buy", timestamp="2026-01-01T03:00:00Z", from_account_id=BANK,
           to_account_id=EXCHANGE_BTC, amount="1.0", cost_basis_usd="20000")
        sell("2026-02-01", "0.1")
        rows = report(2026)["short_term"]
        assert [(r["box"], r["date_acquired"]) for r in rows] == [("H", "12/31/2025")]
    finally:
        CLIENT.put("/api/settings/tax-timezone", json={"timezone": "UTC"})


# ---------------------------------------------------------------------------
# Per-transaction override (transactions.broker_reporting, migration 0003)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("override, expected", [
    (None, "H"), ("basis", "G"), ("proceeds", "H"), ("none", "I"),
])
def test_2025_sale_override(override, expected):
    buy("2025-01-10")
    s = tx(type="Sell", timestamp="2025-02-01T12:00:00Z", from_account_id=EXCHANGE_BTC,
           to_account_id=EXCHANGE_USD, amount="0.1", gross_proceeds_usd="1000.00",
           broker_reporting=override)
    assert s["broker_reporting"] == override
    assert boxes(report(2025)["short_term"]) == [expected]


@pytest.mark.parametrize("override, short_box, long_box", [
    (None, "C", "F"), ("proceeds", "B", "E"), ("basis", "A", "D"), ("none", "C", "F"),
])
def test_2024_override_uses_1099b_boxes(override, short_box, long_box):
    buy("2022-06-01", amount="0.5")          # long-term lot
    buy("2024-01-10", amount="0.5")          # short-term lot
    for date in ("2024-03-01", "2024-04-01"):  # FIFO: first takes the 2022 lot, then the 2024 one
        tx(type="Sell", timestamp=f"{date}T12:00:00Z", from_account_id=EXCHANGE_BTC,
           to_account_id=EXCHANGE_USD, amount="0.5", gross_proceeds_usd="1000.00",
           broker_reporting=override)
    data = report(2024)
    assert (boxes(data["short_term"]), boxes(data["long_term"])) == ([short_box], [long_box])


def test_self_custody_spend_can_be_marked_broker_reported():
    buy("2025-01-10")
    to_wallet("2025-03-01", "0.5")
    w = spend("2025-04-01", "0.1")
    assert "I" in boxes(report(2025)["short_term"])
    r = CLIENT.put(f"/api/transactions/{w['id']}", json={"broker_reporting": "proceeds"})
    assert r.status_code == 200, r.text
    assert boxes(report(2025)["short_term"]) == ["H", "I"]      # spend -> H, fee stays I
    r = CLIENT.put(f"/api/transactions/{w['id']}", json={"broker_reporting": None})
    assert r.status_code == 200 and r.json()["broker_reporting"] is None
    assert boxes(report(2025)["short_term"]) == ["I"]          # back to automatic


def test_override_rejected_on_other_types_and_bad_values():
    r = CLIENT.post("/api/transactions", json=dict(
        type="Deposit", timestamp="2025-01-01T12:00:00Z", from_account_id=EXTERNAL,
        to_account_id=BANK, amount="100", fee_amount="0", fee_currency="USD",
        source="N/A", broker_reporting="basis"))
    assert r.status_code == 400 and "Sell or Withdrawal" in r.text
    buy("2025-01-10")
    r = CLIENT.post("/api/transactions", json=dict(
        type="Sell", timestamp="2025-02-01T12:00:00Z", from_account_id=EXCHANGE_BTC,
        to_account_id=EXCHANGE_USD, amount="0.1", gross_proceeds_usd="1000.00",
        broker_reporting="maybe"))
    assert r.status_code == 422


def test_changing_type_away_from_withdrawal_clears_the_override():
    buy("2025-01-10")
    to_wallet("2025-03-01", "0.5")
    w = spend("2025-04-01", "0.1")
    CLIENT.put(f"/api/transactions/{w['id']}", json={"broker_reporting": "none"})
    r = CLIENT.put(f"/api/transactions/{w['id']}", json={
        "type": "Transfer", "from_account_id": WALLET, "to_account_id": EXCHANGE_BTC, "fee_amount": "0", "fee_currency": "BTC",
        "purpose": None, "proceeds_usd": None})
    assert r.status_code == 200, r.text
    assert r.json()["broker_reporting"] is None
