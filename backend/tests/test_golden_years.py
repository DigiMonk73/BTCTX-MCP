"""
Golden years: three tax years worked out by hand from the IRS rules, with
the exact Form 8949 rows, boxes and Schedule D lines BitcoinTX must produce.

Tax timezone America/New_York. Historical BTC price stubbed at $50,000
(conftest), which values the transfer fee and the income deposit.

2023
  Jan 15  Deposit $100,000 to Bank.
  Feb  1  Buy 1.0 BTC for $23,000 (lot A, $23,000/BTC).
  Mar  1  Buy 0.5 BTC for $12,000 (lot B, $24,000/BTC).
  Jun  1  Transfer 0.6 BTC Exchange -> Wallet, network fee 0.0002 BTC
          (amount includes the fee). FIFO from lot A:
          - the Wallet gets 0.5998 BTC, acquired Feb 1 2023, basis
            0.5998 x 23,000 = 13,795.40 (lot W);
          - the fee is a disposal: 0.0002 BTC, basis 0.0002 x 23,000 = 4.60,
            proceeds 0.0002 x 50,000 = 10.00, gain 5.40, short-term.
          Lot A keeps 0.4 BTC.
  Sep 10  Sell 0.5 BTC for $13,000 gross, $10 fee: net 12,990.00, split by
          BTC across the lots used (FIFO):
          - 0.4 from lot A: proceeds 10,392.00, basis 9,200.00, gain 1,192.00
          - 0.1 from lot B: proceeds  2,598.00, basis 2,400.00, gain   198.00
  Dec 31 23:30 New York (Jan 1 2024 04:30 UTC): spend 0.01 BTC from the
          Wallet for $400: basis 0.01 x 23,000 = 230.00, gain 170.00. It
          counts in 2023, the tax timezone's year.
  Through 2024 crypto uses box C (short) / F (long), Schedule D lines 3/10.
  Line 3: proceeds 10 + 10,392 + 2,598 + 400 = 13,400.00;
          cost 4.60 + 9,200 + 2,400 + 230 = 11,834.60; gain 1,565.40.

2024
  Feb  2  Sell 0.3 BTC for $15,000: lot B (acquired Mar 1 2023), basis
          7,200.00, gain 7,800.00. Held less than a year: short-term.
  Mar  2  Sell 0.1 BTC for $6,000: lot B, basis 2,400.00, gain 3,600.00.
          Sold after the one-year anniversary (Mar 1 2024): long-term.
  May  1  Income 0.02 BTC to the Wallet, basis left blank: valued at
          0.02 x 50,000 = 1,000.00 (also the income). Not a disposal.
  Jun  1  Gift 0.1 BTC from the Wallet: not on Form 8949.
  Line 3 (C): 15,000.00 / 7,200.00 / 7,800.00; line 10 (F): 6,000.00 /
  2,400.00 / 3,600.00.

2025 (digital-asset boxes)
  Jan 10  Buy 0.2 BTC for $20,000 (lot C, $100,000/BTC).
  Apr  1  Sell 0.05 BTC for $4,000: lot C, basis 5,000.00, loss -1,000.00,
          short-term. An exchange sale in 2025 is on a 1099-DA without basis:
          box H, Schedule D line 2.
  May  1  Spend 0.1 BTC from the Wallet for $9,000: lot W (acquired Feb 1
          2023), basis 2,300.00, gain 6,700.00, long-term. Self-custody:
          box L, Schedule D line 10.
"""

from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from backend.services.reports.form_8949 import build_form_8949_and_schedule_d

BANK, WALLET, EXCH_USD, EXCH_BTC, EXTERNAL = 1, 2, 3, 4, 99


def D(x: str) -> Decimal:
    return Decimal(x)


LEDGER = [
    dict(type="Deposit", timestamp="2023-01-15T17:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
         amount="100000", fee_amount="0", fee_currency="USD", source="N/A"),
    dict(type="Buy", timestamp="2023-02-01T17:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
         amount="1.0", cost_basis_usd="23000", fee_amount="0", fee_currency="USD"),
    dict(type="Buy", timestamp="2023-03-01T17:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
         amount="0.5", cost_basis_usd="12000", fee_amount="0", fee_currency="USD"),
    dict(type="Transfer", timestamp="2023-06-01T16:00:00Z", from_account_id=EXCH_BTC, to_account_id=WALLET,
         amount="0.6", fee_amount="0.0002", fee_currency="BTC"),
    dict(type="Sell", timestamp="2023-09-10T16:00:00Z", from_account_id=EXCH_BTC, to_account_id=EXCH_USD,
         amount="0.5", gross_proceeds_usd="13000", fee_amount="10", fee_currency="USD"),
    dict(type="Withdrawal", timestamp="2023-12-31T23:30:00-05:00", from_account_id=WALLET,
         to_account_id=EXTERNAL, amount="0.01", proceeds_usd="400", fee_amount="0", fee_currency="BTC",
         purpose="Spent"),
    dict(type="Sell", timestamp="2024-02-02T16:00:00Z", from_account_id=EXCH_BTC, to_account_id=EXCH_USD,
         amount="0.3", gross_proceeds_usd="15000", fee_amount="0", fee_currency="USD"),
    dict(type="Sell", timestamp="2024-03-02T16:00:00Z", from_account_id=EXCH_BTC, to_account_id=EXCH_USD,
         amount="0.1", gross_proceeds_usd="6000", fee_amount="0", fee_currency="USD"),
    dict(type="Deposit", timestamp="2024-05-01T16:00:00Z", from_account_id=EXTERNAL, to_account_id=WALLET,
         amount="0.02", fee_amount="0", fee_currency="BTC", source="Income"),
    dict(type="Withdrawal", timestamp="2024-06-01T16:00:00Z", from_account_id=WALLET, to_account_id=EXTERNAL,
         amount="0.1", fee_amount="0", fee_currency="BTC", purpose="Gift"),
    dict(type="Buy", timestamp="2025-01-10T17:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
         amount="0.2", cost_basis_usd="20000", fee_amount="0", fee_currency="USD"),
    dict(type="Sell", timestamp="2025-04-01T16:00:00Z", from_account_id=EXCH_BTC, to_account_id=EXCH_USD,
         amount="0.05", gross_proceeds_usd="4000", fee_amount="0", fee_currency="USD"),
    dict(type="Withdrawal", timestamp="2025-05-01T16:00:00Z", from_account_id=WALLET, to_account_id=EXTERNAL,
         amount="0.1", proceeds_usd="9000", fee_amount="0", fee_currency="BTC", purpose="Spent"),
]


def row(desc, acquired, sold, proceeds, cost, gain, term, box):
    return {"description": desc, "date_acquired": acquired, "date_sold": sold, "proceeds": D(proceeds),
            "cost": D(cost), "gain_loss": D(gain), "holding_period": term, "box": box}


def totals(p, c, g):
    return {"proceeds": D(p), "cost": D(c), "gain_loss": D(g)}


EXPECTED = {
    2023: {
        "short_term": [
            row("0.00020000 BTC", "02/01/2023", "06/01/2023", "10.00", "4.60", "5.40", "SHORT", "C"),
            row("0.40000000 BTC", "02/01/2023", "09/10/2023", "10392.00", "9200.00", "1192.00", "SHORT", "C"),
            row("0.10000000 BTC", "03/01/2023", "09/10/2023", "2598.00", "2400.00", "198.00", "SHORT", "C"),
            row("0.01000000 BTC", "02/01/2023", "12/31/2023", "400.00", "230.00", "170.00", "SHORT", "C"),
        ],
        "long_term": [],
        "lines": {"3": totals("13400.00", "11834.60", "1565.40")},
    },
    2024: {
        "short_term": [row("0.30000000 BTC", "03/01/2023", "02/02/2024", "15000.00", "7200.00", "7800.00", "SHORT", "C")],
        "long_term": [row("0.10000000 BTC", "03/01/2023", "03/02/2024", "6000.00", "2400.00", "3600.00", "LONG", "F")],
        "lines": {"3": totals("15000.00", "7200.00", "7800.00"), "10": totals("6000.00", "2400.00", "3600.00")},
    },
    2025: {
        "short_term": [row("0.05000000 BTC", "01/10/2025", "04/01/2025", "4000.00", "5000.00", "-1000.00", "SHORT", "H")],
        "long_term": [row("0.10000000 BTC", "02/01/2023", "05/01/2025", "9000.00", "2300.00", "6700.00", "LONG", "L")],
        "lines": {"2": totals("4000.00", "5000.00", "-1000.00"), "10": totals("9000.00", "2300.00", "6700.00")},
    },
}


@pytest.fixture(scope="module")
def golden(auth_client, test_engine):
    auth_client.delete("/api/transactions/delete_all")
    before = auth_client.get("/api/settings/tax-timezone").json()["timezone"]
    assert auth_client.put("/api/settings/tax-timezone", json={"timezone": "America/New_York"}).status_code == 200
    for tx in LEDGER:
        r = auth_client.post("/api/transactions", json=tx)
        assert r.status_code == 200, (tx, r.text)
    yield sessionmaker(bind=test_engine)
    auth_client.delete("/api/transactions/delete_all")
    auth_client.put("/api/settings/tax-timezone", json={"timezone": before})


def _normalize(forms):
    out = {}
    for term in ("short_term", "long_term"):
        out[term] = sorted(
            ({**r, "proceeds": D(str(r["proceeds"])), "cost": D(str(r["cost"])), "gain_loss": D(str(r["gain_loss"]))}
             for r in forms[term]),
            key=lambda r: (r["date_sold"][-4:], r["date_sold"], r["date_acquired"][-4:], r["date_acquired"], r["description"]),
        )
    out["lines"] = {k: {f: D(str(v)) for f, v in t.items()} for k, t in forms["schedule_d"]["lines"].items()}
    return out


@pytest.mark.parametrize("year", [2023, 2024, 2025])
def test_golden_year(golden, year):
    with golden() as db:
        forms = build_form_8949_and_schedule_d(year, db)
    got = _normalize(forms)
    want = EXPECTED[year]
    assert got["short_term"] == sorted(want["short_term"], key=lambda r: (r["date_sold"][-4:], r["date_sold"], r["date_acquired"][-4:], r["date_acquired"], r["description"]))
    assert got["long_term"] == want["long_term"]
    assert got["lines"] == want["lines"]


def test_golden_income_and_balances(golden, auth_client):
    txs = auth_client.get("/api/transactions").json()
    income = next(t for t in txs if t["source"] == "Income")
    assert D(income["cost_basis_usd"]) == D("1000.00")
    balances = {b["name"]: D(str(b["balance"])) for b in auth_client.get("/api/calculations/accounts/balances").json()}
    # Wallet: 0.5998 - 0.01 + 0.02 - 0.1 - 0.1 = 0.4098; Exchange BTC: 0.2 - 0.05 = 0.15
    assert balances["Wallet"] == D("0.4098")
    assert balances["Exchange BTC"] == D("0.15")
