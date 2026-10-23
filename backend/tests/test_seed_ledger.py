"""
scripts/seed_ledger.py loads the full test ledger (2023-2026) into a running
BitcoinTX over its API. Here against the in-process app on a fresh database:
it loads with the price source Off and asks for no price; every year has
every kind of transaction and every report something in each part (every
Form 8949 box of 2024, 2025 and 2026); and it refuses a ledger that isn't
empty and the Mac app's address.
"""

import csv
import importlib.util
import io
import json
import os
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import get_args

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.transaction import Transaction
from backend.schemas.transaction import BrokerReporting
from backend.services import first_run, outbound
from backend.services.transaction import DEPOSIT_SOURCES, TX_TYPES, WITHDRAWAL_PURPOSES
from backend.services.reports.form_8949 import build_form_8949_and_schedule_d
from backend.services.reports.reporting_core import generate_report_data


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[2] / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed_ledger = _script("seed_ledger")
reference_figures = _script("reference_figures")

USER, PASSWORD = "seed-user", "seed-password-123"

# The box of every 2026 disposal, by date sold (the "why" notes of testdata/reference_ledger.json)
BOXES_2026 = {
    "01/15/2026": {"K"}, "02/02/2026": {"J"}, "02/09/2026": {"H"}, "03/16/2026": {"I"},
    "05/04/2026": {"G"}, "06/01/2026": {"I"}, "07/01/2026": {"L"}, "08/03/2026": {"G"},
    "08/28/2026": {"I"}, "09/01/2026": {"L"}, "09/02/2026": {"K"}, "09/05/2026": {"L"}, "09/10/2026": {"L"},
    "09/13/2026": {"K"},
}
YEARS = [2023, 2024, 2025, 2026]
# Each year: every deposit source and withdrawal purpose the app has (its own
# lists, so a new one fails here until the reference ledger has it), cash
# withdrawals, transfers both ways, buys and sells
KINDS = {
    *(f"Deposit {s}" for s in DEPOSIT_SOURCES),
    *(f"Withdrawal {p}" for p in (*WITHDRAWAL_PURPOSES, "cash")),
    "Transfer to the exchange", "Transfer from the exchange", "Transfer cash", "Buy", "Sell",
}
# Every account route the app offers (type, from, to): Bank 1, Wallet 2,
# Exchange USD 3, Exchange BTC 4, External 99
ROUTES = {
    ("Buy", 1, 4), ("Buy", 3, 4), ("Sell", 4, 3),
    *(("Deposit", 99, a) for a in (1, 2, 3, 4)), *(("Withdrawal", a, 99) for a in (1, 2, 3, 4)),
    ("Transfer", 1, 3), ("Transfer", 3, 1), ("Transfer", 2, 4), ("Transfer", 4, 2),
    ("Transfer", 2, 2), ("Transfer", 4, 4),  # consolidations (#159)
}


def _kind(t: Transaction) -> str:
    if t.type == "Deposit":
        return f"Deposit {t.source}"
    if t.type == "Withdrawal":
        return f"Withdrawal {t.purpose or 'cash'}"
    if t.type == "Transfer" and t.from_account_id == t.to_account_id:
        return "Consolidation"
    if t.type == "Transfer":
        return {1: "Transfer cash", 2: "Transfer to the exchange", 4: "Transfer from the exchange"}.get(
            t.from_account_id, f"Transfer from account {t.from_account_id}")
    return t.type


@pytest.fixture
def seeded(fresh_app, monkeypatch):
    """A fresh install claimed and seeded by the script, price source Off;
    yields (client, Session, the days a price was asked for)."""
    asked = []

    async def find_prices(day, full):
        asked.append(day)
        return {}, False

    monkeypatch.setattr("backend.services.price_history.find_prices", find_prices)
    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings(price_source="off"))
    c = TestClient(app)
    seed_ledger.log_in(c, USER, PASSWORD, first_run.ensure_code())
    assert seed_ledger.seed(c) == len(seed_ledger.ledger_rows())
    yield c, fresh_app, asked


def test_the_whole_ledger_loads_with_prices_off_and_asks_for_none(seeded):
    c, Session, asked = seeded
    assert asked == []
    with Session() as db:
        assert db.query(Transaction).count() == len(seed_ledger.ledger_rows())


def test_every_year_has_every_kind_of_transaction(seeded):
    _, Session, _ = seeded
    with Session() as db:
        kinds = {year: set() for year in YEARS}
        for t in db.query(Transaction):
            kinds[t.timestamp.year].add(_kind(t))
    assert {year: KINDS - found for year, found in kinds.items()} == {year: set() for year in YEARS}


@pytest.mark.parametrize("year, boxes", [(2023, "C"), (2024, "ABCDEF"), (2025, "GHIJKL"), (2026, "GHIJKL")])
def test_every_report_has_entries_in_every_part(seeded, year, boxes):
    """Form 8949: every box the year's form has (2023 has no forms here,
    only box C rows for the reports), short- and long-term; Schedule D:
    every line; the complete tax report: gains, income from each source,
    rebates, and a gift, a donation and a loss."""
    _, Session, _ = seeded
    with Session() as db:
        forms = build_form_8949_and_schedule_d(year, db)
        report = generate_report_data(db, year)
    assert {r["box"] for r in forms["short_term"] + forms["long_term"]} == set(boxes)
    if year >= 2024:
        assert set(forms["schedule_d"]["lines"]) == {"1b", "2", "3", "8b", "9", "10"}
        assert forms["short_term"] and forms["long_term"], year
    for part in ("capital_gains_transactions", "income_transactions", "gifts_donations_lost", "rebates"):
        assert report[part], (year, part)
    assert {"Income", "Interest", "Reward"} <= {k for k, v in report["income_summary"].items() if v}
    assert {g["type"] for g in report["gifts_donations_lost"]} == {"Gift", "Donation", "Lost"}


def test_the_ledger_has_everything_the_app_offers():
    """Every transaction type and account route, every broker-reporting
    choice, fees in USD and BTC, and a date originally acquired on a My BTC
    and a Gift deposit: so a full-ledger check exercises all of them."""
    rows = seed_ledger.ledger_rows()
    assert {r["type"] for r in rows} == set(TX_TYPES)
    assert ROUTES <= {(r["type"], r["from_account_id"], r["to_account_id"]) for r in rows}
    assert set(get_args(BrokerReporting)) <= {r.get("broker_reporting") for r in rows}
    paid = {(r["type"], r["fee_currency"]) for r in rows if Decimal(r["fee_amount"]) > 0}
    assert {("Buy", "USD"), ("Sell", "USD"), ("Transfer", "BTC"), ("Withdrawal", "BTC")} <= paid
    assert {"MyBTC", "Gift"} <= {r["source"] for r in rows if r.get("acquired_at")}


def test_every_value_a_price_would_fill_is_given():
    for row in seed_ledger.ledger_rows():
        if row.get("fee_currency") == "BTC" and Decimal(row["fee_amount"]) > 0:
            assert Decimal(row["fee_usd"]) > 0, row
        if (row.get("purpose") or "").lower() in ("gift", "donation"):
            assert Decimal(row["fmv_usd"]) > 0, row
        if (row.get("purpose") or "").lower() == "lost":  # filled from the price too since #255
            assert row.get("fmv_usd") is not None, row  # $0 typed, some of them


def test_2026_rows_land_in_their_boxes(seeded):
    _, Session, _ = seeded
    with Session() as db:
        forms = build_form_8949_and_schedule_d(2026, db)
    boxes = defaultdict(set)
    for row in forms["short_term"] + forms["long_term"]:
        boxes[row["date_sold"]].add(row["box"])
    assert dict(boxes) == BOXES_2026
    assert set(forms["schedule_d"]["lines"]) == {"1b", "2", "3", "8b", "9", "10"}


def test_dates_originally_acquired_lead_fifo(seeded):
    """The 2019 My BTC and the 2020 gift are the wallet's oldest coins by
    their date originally acquired, so they go first: long-term, and Form
    8949 column (b) shows that date (#91)."""
    _, Session, _ = seeded
    with Session() as db:
        forms = build_form_8949_and_schedule_d(2026, db)
    rows = forms["short_term"] + forms["long_term"]
    acquired = {(r["date_sold"], r["date_acquired"], r["box"]) for r in rows}
    assert ("07/01/2026", "03/01/2019", "L") in acquired
    assert ("09/01/2026", "01/15/2020", "L") in acquired


def test_the_reference_figures_have_not_moved(seeded):
    """#139: every figure the reference ledger gives (each year's forms and
    report, the dashboard) against testdata/reference_figures.json. A change
    meant to move figures runs `make reference-figures` and shows the
    difference in its pull request. The figures rule (AGENTS.md, "Reviews"):
    a figure moved on purpose gets the owner's OK on a plain-words
    before-and-after, never on code; one moved by mistake is fixed; no figure
    moved, Claude merges after every figures check."""
    _, Session, _ = seeded
    with Session() as db:
        now = reference_figures.figures(db)
    if os.environ.get("BTCTX_UPDATE_REFERENCE_FIGURES"):
        reference_figures.FIGURES.write_text(reference_figures.dumps(now))
    saved = json.loads(reference_figures.FIGURES.read_text())
    moved = list(reference_figures.differences(saved, now))
    assert not moved, "figures moved (make reference-figures if meant):\n" + "\n".join(moved[:20])


@pytest.mark.parametrize("tz", ["Asia/Tokyo", "Australia/Adelaide", "Pacific/Honolulu", "America/New_York"])
def test_every_box_in_any_tax_timezone(seeded, tz):
    """Review of #57: the anniversary sales stay on the lot's day, so short-
    term, wherever the owner's tax timezone is."""
    c, Session, _ = seeded
    assert c.put("/api/settings/tax-timezone", json={"timezone": tz, "chosen": True}).status_code == 200
    try:
        with Session() as db:
            forms = {year: build_form_8949_and_schedule_d(year, db) for year in (2024, 2025, 2026)}
        boxes = {year: {r["box"] for r in f["short_term"] + f["long_term"]} for year, f in forms.items()}
    finally:
        c.put("/api/settings/tax-timezone", json={"timezone": "UTC", "chosen": True})
    assert boxes == {2024: set("ABCDEF"), 2025: set("GHIJKL"), 2026: set("GHIJKL")}


def test_the_history_csv_writes_ordinary_text_as_it_is(seeded):
    """Each year's transaction history CSV of the reference ledger is the
    plain file a spreadsheet or a diff expects: a line per row and none after
    the last, every cell as it is, quoted only when it holds a comma or a
    quote."""
    c, _, _ = seeded

    def cell(value: str) -> str:
        return '"' + value.replace('"', '""') + '"' if "," in value or '"' in value else value

    for year in YEARS:
        r = c.get("/api/reports/simple_transaction_history", params={"year": year, "format": "csv"})
        assert r.status_code == 200, r.text
        rows = list(csv.reader(io.StringIO(r.text)))
        assert len(rows) > 10, year
        assert r.text == "\n".join(",".join(cell(value) for value in row) for row in rows), year


def test_a_ledger_with_transactions_is_refused(seeded):
    c, Session, _ = seeded
    with pytest.raises(seed_ledger.SeedError, match="already has"):
        seed_ledger.seed(c)
    with Session() as db:
        assert db.query(Transaction).count() == len(seed_ledger.ledger_rows())


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8765", "http://localhost:8765/", "http://[::1]:8765", "http://LOCALHOST:8765",
    # Review of #52: other spellings of this computer
    "http://127.1:8765", "http://2130706433:8765", "http://localhost.:8765", "http://foo.localhost:8765",
    "http://[::]:8765", "http://0.0.0.0:8765", "http://[::ffff:127.0.0.1]:8765",
])
def test_the_mac_app_is_refused_before_anything_is_sent(url, monkeypatch, capsys):
    def no_connection(*args, **kwargs):
        raise AssertionError("connected to the Mac app")

    monkeypatch.setattr(seed_ledger, "connect", no_connection)
    monkeypatch.setenv(seed_ledger.PASSWORD_ENV, PASSWORD)
    assert seed_ledger.main(["--url", url, "--user", USER]) == 1
    assert "Mac app" in capsys.readouterr().err


def test_other_local_ports_are_allowed():
    seed_ledger.refuse_mac_app("http://127.0.0.1:8777")  # make preview
    seed_ledger.refuse_mac_app("https://192.0.2.10:8765")  # another computer


def test_a_bad_address_is_a_message_not_a_traceback(monkeypatch, capsys):
    monkeypatch.setenv(seed_ledger.PASSWORD_ENV, PASSWORD)
    for url in ("http://host:abc", "http://a..b:8765"):
        assert seed_ledger.main(["--url", url, "--user", USER]) == 1
        assert "not a valid address" in capsys.readouterr().err
