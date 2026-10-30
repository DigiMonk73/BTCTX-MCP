"""
River's sample file (#844): testdata/exchange_files/river_bitcoin_activity.csv,
made-up rows in River's published format, one of each kind of row River's
reader reads, with its figures worked out here by hand, as
test_exchange_import_567_mappings.py does for the other exchanges' files:

- the $198 buy with a $2 fee is paid from the bank, since no earlier sale left
  dollars at the exchange; four $25 buys with no fee are an auto-buy, paid from
  the bank though the sale left enough there; the $49.50 buy with a $0.50 fee
  is paid from the $104.50 the sale left;
- the Sell's Received Amount is net of River's fee: 104.50 + 1.50 = 106.00 gross;
- a send, tagged Withdrawal or not, is a Transfer to the wallet: the Sent
  Amount arrived, so the Transfer's amount is it plus the network fee;
- an untagged receive is a Transfer from the wallet;
- each payout is a Deposit, valued at the hour's price (here $100,000 a bitcoin);
- the row of dollars alone is no pattern River's reader knows: named, and left out.

Every coin costs $100,000 a bitcoin, so the only gain is the sale's: its half
of the first buy cost $100.00, and it brought in $104.50 after its fee, a gain
of $4.50. Each network fee is a disposal at no gain: $0.50 and $0.20.

Bitcoin, by account:
  the exchange: 0.001 + 0.002 - 0.001 + 0.0005 + 0.00006 - 0.001005 - 0.000502 + 0.0002 = 0.001253
  the wallet:   0.001 + 0.0005 - 0.0002 = 0.0013
Together 0.002553: the 0.0035 bought, less the 0.001 sold, plus the 0.00006
paid out, less the 0.000007 of fees.
Dollars: the bank paid 4 x 25 + 198 + 2 = 300; the exchange holds 104.50 - 49.50 - 0.50 = 54.50.
"""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from backend.services.reports.form_8949 import build_form_8949_and_schedule_d
from backend.services.reports.reporting_core import generate_report_data
from backend.tests.conftest import stub_daily_prices
from backend.tests.hand_test_tables import rows_to_send

FILE = Path(__file__).resolve().parents[2] / "testdata" / "exchange_files" / "river_bitcoin_activity.csv"
PRICE = 100000.0
BANK, EX_USD, EX_BTC, WALLET, EXTERNAL = "Bank", "Exchange USD", "Exchange BTC", "Wallet", "External"


# The docstring's balances, with the fee accounts': 2.00 + 1.50 + 0.50 and the two network fees
BY_HAND = {BANK: Decimal("-300"), EX_USD: Decimal("54.5"), EX_BTC: Decimal("0.001253"), WALLET: Decimal("0.0013"),
           "USD Fees": Decimal("4"), "BTC Fees": Decimal("0.000007")}


@pytest.fixture(autouse=True)
def _prices(monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: PRICE)


@pytest.fixture
def client(auth_client):
    r = auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    assert r.status_code in (200, 204)
    yield auth_client
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def preview(client, route: str = "/api/import/exchange/preview", form: dict | None = None) -> dict:
    r = client.post(route, data=form if form is not None else {"mapping_id": "river"},
                    files={"file": (FILE.name, FILE.read_bytes(), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


def at(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


def row(number, kind, from_, to, amount, when, cost=None, proceeds=None, fee=None, source=None):
    currency = None if fee is None else "USD" if kind in ("Buy", "Sell") else "BTC"
    figures = (Decimal(amount), *(Decimal(v) if v is not None else None for v in (cost, proceeds, fee)))
    return (number, kind, from_, to, *figures, currency, source, when)


def rows(answer: dict) -> list:
    def number(v):
        return Decimal(v) if v is not None else None
    return [(p["row_number"], p["type"], p["from_account"], p["to_account"], number(p["amount"]),
             number(p["cost_basis_usd"]), number(p["proceeds_usd"]), number(p["fee_amount"]),
             p["fee_currency"], p["source"], datetime.fromisoformat(p["date"]).astimezone(timezone.utc))
            for p in answer["proposals"]]


def held(client) -> dict[str, Decimal]:
    balances = client.get("/api/calculations/accounts/balances").json()
    return {b["name"]: Decimal(str(b["balance"])) for b in balances if Decimal(str(b["balance"]))}


def import_the_file(client) -> None:
    r = client.post("/api/import/exchange/execute", json={"rows": rows_to_send(preview(client))})
    assert r.status_code == 200, r.text
    assert r.json()["imported_count"] == 13


def test_the_preview_reads_each_kind_of_row(client):
    answer = preview(client)
    assert rows(answer) == [
        row(2, "Buy", BANK, EX_BTC, "0.002", at(2025, 1, 6, 15, 30), cost="198.00", fee="2.00"),
        row(3, "Sell", EX_BTC, EX_USD, "0.001", at(2025, 2, 3, 16), proceeds="106.00", fee="1.50"),
        row(4, "Buy", BANK, EX_BTC, "0.00025", at(2025, 2, 10, 12), cost="25.00"),
        row(5, "Buy", BANK, EX_BTC, "0.00025", at(2025, 2, 17, 12), cost="25.00"),
        row(6, "Buy", BANK, EX_BTC, "0.00025", at(2025, 2, 24, 12), cost="25.00"),
        row(7, "Buy", BANK, EX_BTC, "0.00025", at(2025, 3, 3, 12), cost="25.00"),
        row(8, "Buy", EX_USD, EX_BTC, "0.0005", at(2025, 3, 10, 12), cost="49.50", fee="0.50"),
        row(9, "Deposit", EXTERNAL, EX_BTC, "0.00001", at(2025, 3, 31, 9), cost="1.00", source="Interest"),
        row(10, "Deposit", EXTERNAL, EX_BTC, "0.00002", at(2025, 4, 1, 9), cost="2.00", source="Income"),
        row(11, "Deposit", EXTERNAL, EX_BTC, "0.00003", at(2025, 4, 15, 12), cost="3.00", source="Reward"),
        row(12, "Transfer", EX_BTC, WALLET, "0.001", at(2025, 5, 1, 10), fee="0.000005"),
        row(13, "Transfer", EX_BTC, WALLET, "0.0005", at(2025, 5, 15, 10), fee="0.000002"),
        row(14, "Transfer", WALLET, EX_BTC, "0.0002", at(2025, 6, 2, 10)),
    ]
    assert (answer["total_rows"], answer["new_count"], answer["errors"]) == (14, 13, [])
    assert [(w["row_number"], w["message"]) for w in answer["warnings"]] == [
        (14, "From your wallet, oldest coins first: you can choose the coins after the import."),
        (15, "Unrecognized row pattern (tag=none, sent=USD, received=-) — skipped."),
    ]


def test_rivers_own_route_reads_it_the_same(client):
    assert preview(client, "/api/import/river/preview", {}) == preview(client)


def test_the_balances_are_the_ones_worked_out_by_hand(client):
    import_the_file(client)
    assert held(client) == BY_HAND


def test_in_a_later_tax_year_the_import_asks_first_then_saves_the_same(client, tax_year):
    """The guide's "Save anyway": the tests' pinned year never asks, a real clock does."""
    tax_year(2026)
    answer = preview(client)
    assert answer["past_years_dated"] == [2025]
    sent = {"rows": rows_to_send(answer)}
    asked = client.post("/api/import/exchange/execute", json=sent)
    assert asked.status_code == 409, asked.text
    assert client.get("/api/transactions").json() == []
    r = client.post("/api/import/exchange/execute", json=sent, params={"confirm": asked.json()["confirm"]})
    assert r.status_code == 200, r.text
    assert r.json()["imported_count"] == 13
    assert held(client) == BY_HAND


def test_the_forms_and_the_report_are_the_ones_worked_out_by_hand(client, test_engine):
    import_the_file(client)
    with sessionmaker(bind=test_engine)() as db:
        forms = build_form_8949_and_schedule_d(2025, db)
        report = generate_report_data(db, 2025)
    assert forms["long_term"] == []
    by_box = {}
    for form_row in forms["short_term"]:
        by_box.setdefault(form_row["box"], []).append(
            (Decimal(str(form_row["proceeds"])), Decimal(str(form_row["cost"])), Decimal(str(form_row["gain_loss"]))))
    assert {box: sorted(found) for box, found in by_box.items()} == {
        "H": [(Decimal("104.50"), Decimal("100.00"), Decimal("4.50"))],  # the sale: a 1099-DA without basis
        "I": [(Decimal("0.20"), Decimal("0.20"), Decimal("0.00")),  # the network fees: self-custody
              (Decimal("0.50"), Decimal("0.50"), Decimal("0.00"))],
    }
    assert {k: v for k, v in report["income_summary"].items() if v and k != "Total"} == {
        "Income": 2.0, "Interest": 1.0, "Reward": 3.0}
