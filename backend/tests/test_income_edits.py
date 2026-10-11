"""
Editing an income deposit (#76). An Income, Interest or Reward deposit into
a BTC account is valued at that day's price x its amount when no value is
given, and that value is both its cost basis and the income reported. An
edit used to keep the old figure: $0 after moving the deposit from Bank to a
BTC account, or the old value after changing its amount or day. The app
couldn't tell a value from the price from a typed one; now a value from the
price is marked (cost_basis_from_price) and valued again when the amount,
day or account changes, or the source comes from one not valued at receipt
(MyBTC, Gift...), while a typed one is kept.

The edits send what the transaction form sends: every field, the basis as
the form shows it.
"""

import csv
import io
import sqlite3
from datetime import date
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.migrate import alembic_config, upgrade_database
from backend.services.reports.reporting_core import generate_report_data
from backend.tests.conftest import stub_daily_prices

BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 2, 3, 4, 99
APRIL_1, APRIL_2 = date(2026, 4, 1), date(2026, 4, 2)
PRICES = {APRIL_1: 50000, APRIL_2: 60000}


@pytest.fixture(autouse=True)
def _ledger(auth_client, monkeypatch):
    """An empty ledger, and a different price each day, so a re-priced value shows."""
    stub_daily_prices(monkeypatch, lambda day: PRICES.get(day, 40000))
    auth_client.delete("/api/transactions/delete_all")
    yield
    auth_client.delete("/api/transactions/delete_all")


def deposit(client, **fields) -> dict:
    body = {"type": "Deposit", "timestamp": "2026-04-01T12:00:00Z", "from_account_id": EXTERNAL,
            "to_account_id": WALLET, "amount": "0.00006404", "fee_amount": "0", "fee_currency": "BTC",
            "source": "Interest", **fields}
    r = client.post("/api/transactions", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def edit(client, tx: dict, **changes) -> dict:
    """The form's PUT: the saved transaction's fields with the changes."""
    keys = ("type", "timestamp", "from_account_id", "to_account_id", "amount", "fee_amount", "fee_currency",
            "cost_basis_usd", "source")
    body = {k: tx[k] for k in keys} | changes
    r = client.put(f"/api/transactions/{tx['id']}", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def basis(tx: dict) -> Decimal:
    return Decimal(str(tx["cost_basis_usd"] or 0))


def income_reported(test_engine, year=2026) -> Decimal:
    with sessionmaker(bind=test_engine)() as db:
        report = generate_report_data(db, year)
    return Decimal(str(report["income_summary"]["Total"]))


def test_moving_income_from_bank_to_a_btc_account_values_it(auth_client, test_engine):
    """Path 1 of #76: saved into Bank (USD, no basis), then moved to Wallet
    with a BTC amount. The basis stayed blank and the income read $0."""
    tx = deposit(auth_client, to_account_id=BANK, amount="100", fee_currency="USD")
    assert tx["cost_basis_usd"] is None
    moved = edit(auth_client, tx, to_account_id=WALLET, amount="0.001", fee_currency="BTC", cost_basis_usd=None)
    assert basis(moved) == Decimal("50.00") and moved["cost_basis_from_price"] is True
    assert income_reported(test_engine) == Decimal("50.00")


def test_an_amount_edit_prices_a_value_from_the_price_again(auth_client, test_engine):
    """Path 2 of #76: 0.00006404 BTC valued at $3.20, the amount edited to
    0.001 BTC, and the form sending $3.20 back: it stayed $3.20."""
    tx = deposit(auth_client)
    assert basis(tx) == Decimal("3.20") and tx["cost_basis_from_price"] is True
    edited = edit(auth_client, tx, amount="0.001")
    assert basis(edited) == Decimal("50.00") and edited["cost_basis_from_price"] is True
    assert income_reported(test_engine) == Decimal("50.00")


def partial(client, tx: dict, **changes) -> dict:
    """An edit of a few fields only, as the AI connector's update_transaction sends it."""
    r = client.put(f"/api/transactions/{tx['id']}", json=changes)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_partial_account_edit_from_bank_values_it(auth_client, test_engine):
    """Path 1 of #76 as reproduced: the AI connector (or the API) moves a
    Bank deposit to Wallet with a BTC amount, sending no basis: it read $0."""
    tx = deposit(auth_client, to_account_id=BANK, amount="100", fee_currency="USD")
    moved = partial(auth_client, tx, to_account_id=WALLET, amount="0.001", fee_currency="BTC")
    assert basis(moved) == Decimal("50.00") and moved["cost_basis_from_price"] is True
    assert income_reported(test_engine) == Decimal("50.00")


@pytest.mark.parametrize("changes, expected", [
    ({"amount": "0.002"}, "100.00"),
    ({"timestamp": "2026-04-02T12:00:00Z"}, "60.00"),
    ({"to_account_id": EXCHANGE_BTC}, "50.00"),
])
def test_a_partial_edit_prices_a_value_from_the_price_again(auth_client, changes, expected):
    tx = deposit(auth_client, amount="0.001")
    edited = partial(auth_client, tx, **changes)
    assert basis(edited) == Decimal(expected) and edited["cost_basis_from_price"] is True


def test_a_round_trip_through_bank_keeps_the_mark(auth_client):
    """Wallet -> Bank -> Wallet by partial edits, then a new amount: priced
    again, not left at the old value as typed."""
    tx = deposit(auth_client, amount="0.001")
    partial(auth_client, tx, to_account_id=BANK, amount="100", fee_currency="USD")
    back = partial(auth_client, tx, to_account_id=WALLET, amount="0.002", fee_currency="BTC")
    assert basis(back) == Decimal("100.00") and back["cost_basis_from_price"] is True


def test_a_partial_move_to_bank_drops_the_value(auth_client, test_engine):
    """A USD deposit has no basis: the value a partial edit left on it was
    counted as income on the report."""
    tx = deposit(auth_client, amount="0.001")
    moved = partial(auth_client, tx, to_account_id=BANK, amount="100", fee_currency="USD")
    assert moved["cost_basis_usd"] is None
    assert income_reported(test_engine) == Decimal("0")


@pytest.mark.parametrize("account", [BANK, EXCHANGE_USD])
@pytest.mark.parametrize("source, earned, btc", [("Interest", "interest_earned", "interest_btc"),
                                                 ("Gift", "gifts_received", "gifts_btc"),
                                                 ("Rebate", "rebates_received", "rebates_btc")])
def test_a_usd_deposit_is_never_bitcoin_income(auth_client, test_engine, account, source, earned, btc):
    """Review of #103, #110: a USD deposit with a value (left by an older
    version, sent back by an edit, or created with one) was counted as income
    on the report and the dashboard, its dollar amount shown as BTC; a Gift's
    on the dashboard's gifts. Only deposits into Wallet or Exchange BTC count."""
    tx = deposit(auth_client, to_account_id=account, amount="100", fee_currency="USD", source=source)
    with test_engine.begin() as con:
        con.execute(text("UPDATE transactions SET cost_basis_usd = '50.00' WHERE id = :id"), {"id": tx["id"]})
    assert auth_client.post("/api/transactions/recalculate").status_code == 200  # Recalculate Ledger keeps it
    assert income_reported(test_engine) == Decimal("0")
    with sessionmaker(bind=test_engine)() as db:
        assert generate_report_data(db, 2026)["income_transactions"] == []
    dashboard = auth_client.get("/api/calculations/gains-and-losses").json()
    assert dashboard[earned] == 0 and dashboard[btc] == 0 and dashboard["total_income"] == 0
    # The Transaction History labels it a plain deposit, not income
    history = auth_client.get("/api/reports/simple_transaction_history", params={"year": 2026, "format": "csv"})
    assert ",Deposit," in history.text and f",{source}," not in history.text


@pytest.mark.parametrize("changes", [
    {"amount": "0.002"}, {"timestamp": "2026-04-02T12:00:00Z"}, {"to_account_id": EXCHANGE_BTC},
])
def test_a_partial_edit_keeps_a_my_btc_deposits_basis(auth_client, changes):
    """Review of #103: only a USD deposit loses its basis on a partial edit;
    a My BTC deposit's basis is the user's figure, and the ledger refuses one
    without it."""
    tx = deposit(auth_client, source="MyBTC", amount="0.001", cost_basis_usd="1000")
    edited = partial(auth_client, tx, **changes)
    assert basis(edited) == Decimal("1000.00") and edited["cost_basis_from_price"] is False


def test_the_river_import_passes_the_mark_through(auth_client):
    row = {"date": "2026-04-01T12:00:00Z", "type": "Deposit", "amount": "0.001", "from_account": "External",
           "to_account": "Wallet", "source": "Interest", "cost_basis_usd": "50.00", "cost_basis_typed": "no"}
    r = auth_client.post("/api/import/river/execute", json={"rows": [row]})
    assert r.status_code == 200, r.text
    [tx] = auth_client.get("/api/transactions").json()
    assert tx["cost_basis_from_price"] is True
    assert basis(partial(auth_client, tx, amount="0.002")) == Decimal("100.00")


def test_a_round_trip_through_another_source_keeps_the_mark(auth_client):
    tx = edit(auth_client, deposit(auth_client, amount="0.001"), source="Gift")
    back = edit(auth_client, tx, source="Interest", amount="0.002")
    assert basis(back) == Decimal("100.00") and back["cost_basis_from_price"] is True


@pytest.mark.parametrize("how", ["form", "partial"])
def test_back_from_a_source_not_valued_at_receipt_is_priced_again(auth_client, test_engine, how):
    """Re-check of #111: Interest -> My BTC, a new amount (a My BTC value is
    the user's, so it stays), then back to Interest on the same day: priced
    again at the new amount, or the income would read the old $50."""
    tx = deposit(auth_client, amount="0.001")
    assert basis(tx) == Decimal("50.00")
    step = (lambda t, **c: edit(auth_client, t, **c)) if how == "form" else (lambda t, **c: partial(auth_client, t, **c))
    mine = step(tx, source="MyBTC")
    mine = step(mine, amount="0.002")
    assert basis(mine) == Decimal("50.00")
    back = step(mine, source="Interest")
    assert basis(back) == Decimal("100.00") and back["cost_basis_from_price"] is True
    assert income_reported(test_engine) == Decimal("100.00")


def test_the_price_day_is_the_utc_day(auth_client):
    """23:30 in New York on April 1 is April 2 in UTC: the April 2 price."""
    tx = deposit(auth_client, amount="0.001")
    edited = partial(auth_client, tx, timestamp="2026-04-01T23:30:00-04:00")
    assert basis(edited) == Decimal("60.00")


def test_a_new_day_without_a_price_asks_for_a_value(auth_client, monkeypatch):
    tx = deposit(auth_client, amount="0.001")
    stub_daily_prices(monkeypatch, lambda day: PRICES.get(day) if day != date(2026, 4, 3) else None)
    r = auth_client.put(f"/api/transactions/{tx['id']}", json={"timestamp": "2026-04-03T12:00:00Z"})
    assert r.status_code == 422 and "cost basis" in r.text, r.text
    r = auth_client.put(f"/api/transactions/{tx['id']}", json={"timestamp": "2026-04-03T12:00:00Z",
                                                               "cost_basis_usd": "55"})
    assert r.status_code == 200 and basis(r.json()) == Decimal("55.00") and r.json()["cost_basis_from_price"] is False


def test_a_client_cant_set_the_mark(auth_client):
    tx = deposit(auth_client, amount="0.001", cost_basis_usd="40", cost_basis_from_price=True)
    assert tx["cost_basis_from_price"] is False
    assert partial(auth_client, tx, cost_basis_from_price=True, amount="0.002")["cost_basis_from_price"] is False


def test_an_unknown_cost_basis_typed_is_a_row_error(auth_client):
    body = "date,type,amount,from_account,to_account,cost_basis_usd,source,cost_basis_typed\n" \
           "2026-04-01T12:00:00Z,Deposit,0.001,External,Wallet,50,Interest,maybe\n"
    r = auth_client.post("/api/import/preview", files={"file": ("x.csv", io.BytesIO(body.encode()), "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["errors"][0]["message"] == "Invalid cost_basis_typed 'maybe'. Must be yes, no or blank."


def test_a_day_edit_prices_it_at_the_new_day(auth_client):
    tx = deposit(auth_client, amount="0.001")
    assert basis(tx) == Decimal("50.00")
    assert basis(edit(auth_client, tx, timestamp="2026-04-02T12:00:00Z")) == Decimal("60.00")


def test_a_time_edit_on_the_same_day_keeps_the_value(auth_client):
    tx = deposit(auth_client, amount="0.001")
    edited = edit(auth_client, tx, timestamp="2026-04-01T18:00:00Z")
    assert basis(edited) == Decimal("50.00") and edited["cost_basis_from_price"] is True


def test_a_typed_value_is_kept_through_amount_day_and_account_edits(auth_client):
    tx = deposit(auth_client, cost_basis_usd="4.10")
    assert tx["cost_basis_from_price"] is False
    tx = edit(auth_client, tx, amount="0.001")
    tx = edit(auth_client, tx, timestamp="2026-04-02T12:00:00Z")
    tx = edit(auth_client, tx, to_account_id=EXCHANGE_BTC)
    assert basis(tx) == Decimal("4.10") and tx["cost_basis_from_price"] is False


def test_typing_over_a_value_from_the_price_keeps_the_typed_one(auth_client):
    tx = edit(auth_client, deposit(auth_client), cost_basis_usd="7.00")
    assert basis(tx) == Decimal("7.00") and tx["cost_basis_from_price"] is False
    assert basis(edit(auth_client, tx, amount="0.001")) == Decimal("7.00")


def test_clearing_a_typed_value_prices_it(auth_client):
    tx = edit(auth_client, deposit(auth_client, amount="0.001", cost_basis_usd="4.10"), cost_basis_usd=0)
    assert basis(tx) == Decimal("50.00") and tx["cost_basis_from_price"] is True


def test_a_source_change_prices_the_same_day_and_amount(auth_client):
    tx = edit(auth_client, deposit(auth_client, amount="0.001"), source="Reward")
    assert basis(tx) == Decimal("50.00") and tx["cost_basis_from_price"] is True


def test_a_deposit_that_stops_being_income_keeps_its_value(auth_client):
    """My BTC's basis is the user's: it isn't priced, whatever the mark says."""
    tx = edit(auth_client, deposit(auth_client, amount="0.001"), source="MyBTC")
    assert basis(tx) == Decimal("50.00")
    assert basis(edit(auth_client, tx, amount="0.002")) == Decimal("50.00")


def test_a_value_typed_while_not_income_stays_typed(auth_client):
    """Interest (priced) -> My BTC with a new basis typed -> back to Interest:
    the typed basis is kept, not priced again."""
    tx = edit(auth_client, deposit(auth_client, amount="0.001"), source="MyBTC", cost_basis_usd="4000")
    assert tx["cost_basis_from_price"] is False
    back = edit(auth_client, tx, source="Interest", amount="0.002")
    assert basis(back) == Decimal("4000.00") and back["cost_basis_from_price"] is False


def test_another_type_makes_the_figure_typed(auth_client):
    tx = deposit(auth_client, amount="0.001")
    r = auth_client.put(f"/api/transactions/{tx['id']}", json={
        "type": "Buy", "from_account_id": BANK, "to_account_id": EXCHANGE_BTC, "cost_basis_usd": "50"})
    assert r.status_code == 200, r.text
    assert r.json()["cost_basis_from_price"] is False


def test_a_csv_export_and_reimport_keeps_the_mark(auth_client):
    priced = deposit(auth_client, amount="0.001")
    deposit(auth_client, amount="0.002", cost_basis_usd="90", timestamp="2026-04-02T12:00:00Z")
    export = auth_client.get("/api/backup/csv")
    assert export.status_code == 200
    rows = list(csv.DictReader(io.StringIO(export.text)))
    assert sorted(row["cost_basis_typed"] for row in rows) == ["no", "yes"]

    auth_client.delete("/api/transactions/delete_all")
    r = auth_client.post("/api/import/execute", files={"file": ("x.csv", io.BytesIO(export.content), "text/csv")})
    assert r.status_code == 200, r.text
    marks = {Decimal(str(t["amount"])): t["cost_basis_from_price"] for t in auth_client.get("/api/transactions").json()}
    assert marks == {Decimal("0.001"): True, Decimal("0.002"): False}
    reimported = next(t for t in auth_client.get("/api/transactions").json() if t["cost_basis_from_price"])
    assert basis(reimported) == basis(priced)
    assert basis(edit(auth_client, reimported, amount="0.002")) == Decimal("100.00")


def test_the_ai_connectors_autofilled_value_is_from_the_price(auth_client):
    row = {"date": "2026-04-01T12:00:00Z", "type": "Deposit", "amount": "0.001", "from_account": "External",
           "to_account": "Wallet", "source": "Interest", "fee_amount": "0", "fee_currency": "BTC"}
    r = auth_client.post("/api/import/entries/execute", json={"rows": [row]})
    assert r.status_code == 200, r.text
    [tx] = auth_client.get("/api/transactions").json()
    assert basis(tx) == Decimal("50.00") and tx["cost_basis_from_price"] is True
    assert basis(edit(auth_client, tx, amount="0.002")) == Decimal("100.00")


# Migration 0006 marks only values that are exactly the day's price x amount
def test_0006_marks_exact_day_values_and_changes_no_figure(tmp_path):
    db = tmp_path / "btctx.db"
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as conn:
        cfg = alembic_config()
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0005")
    con = sqlite3.connect(str(db))
    con.execute("INSERT INTO btc_price_daily (day, usd, source) VALUES ('2026-04-01', 50000, 'test')")
    rows = [  # id, to, source, amount, basis, timestamp as stored
        (1, WALLET, "Interest", "0.00006404", "3.20", "2026-04-01T12:00:00Z"),  # 3.202 -> 3.20: from the price
        (2, EXCHANGE_BTC, "income", "0.001", "50.00", "2026-04-01T23:59:59Z"),  # exact, any spelling
        (3, WALLET, "Reward", "0.001", "49.99", "2026-04-01T12:00:00Z"),  # a cent off: typed
        (4, WALLET, "MyBTC", "0.001", "50.00", "2026-04-01T12:00:00Z"),  # not income
        (5, BANK, "Income", "50", None, "2026-04-01T12:00:00Z"),  # USD
        (6, WALLET, "Interest", "0.001", "50.00", "2026-04-01 12:00:00.000000"),  # an older stored format
        (7, WALLET, "Interest", "0.001", "fifty", "2026-04-01T12:00:00Z"),  # not a number: typed, no failure
    ]
    for tx_id, to, source, amount, cost, when in rows:
        con.execute(
            "INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount, fee_amount,"
            " fee_currency, source, cost_basis_usd) VALUES (?, 'Deposit', ?, 99, ?, ?, '0', 'BTC', ?, ?)",
            (tx_id, when, to, amount, source, cost))
    con.commit()
    before = con.execute("SELECT id, amount, cost_basis_usd FROM transactions ORDER BY id").fetchall()
    con.close()

    upgrade_database(engine, backup=False)

    con = sqlite3.connect(str(db))
    marked = con.execute("SELECT id FROM transactions WHERE cost_basis_from_price ORDER BY id").fetchall()
    assert marked == [(1,), (2,), (6,)]
    assert con.execute("SELECT id, amount, cost_basis_usd FROM transactions ORDER BY id").fetchall() == before
    con.close()
