"""
scripts/seed_ledger.py loads the full test ledger (2023-2026) into a running
BitcoinTX over its API. Here against the in-process app on a fresh database:
it loads with the price source Off and asks for no price; every year has
every kind of transaction and every report something in each part (every
Form 8949 box of 2024, 2025 and 2026); and it refuses a ledger that isn't
empty and the Mac app's address.
"""

import importlib.util
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.transaction import Transaction
from backend.services import first_run, outbound
from backend.services.reports.form_8949 import build_form_8949_and_schedule_d
from backend.services.reports.reporting_core import generate_report_data

_spec = importlib.util.spec_from_file_location(
    "seed_ledger", Path(__file__).resolve().parents[2] / "scripts" / "seed_ledger.py")
seed_ledger = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_ledger)

USER, PASSWORD = "seed-user", "seed-password-123"

# The box of every 2026 disposal, by date sold (the comments in LEDGER_2026)
BOXES_2026 = {
    "01/15/2026": {"K"}, "02/02/2026": {"J"}, "02/09/2026": {"H"}, "03/16/2026": {"I"},
    "05/04/2026": {"G"}, "06/01/2026": {"I"}, "07/01/2026": {"L"}, "08/03/2026": {"G"},
    "09/01/2026": {"L"}, "09/05/2026": {"L"}, "09/10/2026": {"L"},
}
YEARS = [2023, 2024, 2025, 2026]
# Each year: every deposit source, withdrawal purpose and transfer the app has
KINDS = {
    *(f"Deposit {s}" for s in ("MyBTC", "Gift", "Income", "Interest", "Reward", "N/A")),
    *(f"Withdrawal {p}" for p in ("Spent", "Gift", "Donation", "Lost", "cash")),
    "Transfer to the exchange", "Transfer from the exchange", "Transfer cash", "Buy", "Sell",
}


def _kind(t: Transaction) -> str:
    if t.type == "Deposit":
        return f"Deposit {t.source}"
    if t.type == "Withdrawal":
        return f"Withdrawal {t.purpose or 'cash'}"
    if t.type == "Transfer":
        return {1: "Transfer cash", 2: "Transfer to the exchange", 4: "Transfer from the exchange"}[t.from_account_id]
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
    only box C rows for the reports); Schedule D: every line; the complete
    tax report: gains, income, and gifts, donations and losses."""
    _, Session, _ = seeded
    with Session() as db:
        forms = build_form_8949_and_schedule_d(year, db)
        report = generate_report_data(db, year)
    assert {r["box"] for r in forms["short_term"] + forms["long_term"]} == set(boxes)
    if year >= 2024:
        assert set(forms["schedule_d"]["lines"]) == {"1b", "2", "3", "8b", "9", "10"}
    for part in ("capital_gains_transactions", "income_transactions", "gifts_donations_lost"):
        assert report[part], (year, part)


def test_every_value_a_price_would_fill_is_given():
    for row in seed_ledger.ledger_rows():
        if row.get("fee_currency") == "BTC" and Decimal(row["fee_amount"]) > 0:
            assert Decimal(row["fee_usd"]) > 0, row
        if (row.get("purpose") or "").lower() in ("gift", "donation"):
            assert Decimal(row["fmv_usd"]) > 0, row


def test_2026_rows_land_in_their_boxes(seeded):
    _, Session, _ = seeded
    with Session() as db:
        forms = build_form_8949_and_schedule_d(2026, db)
    boxes = defaultdict(set)
    for row in forms["short_term"] + forms["long_term"]:
        boxes[row["date_sold"]].add(row["box"])
    assert dict(boxes) == BOXES_2026
    assert set(forms["schedule_d"]["lines"]) == {"1b", "2", "3", "8b", "9", "10"}


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
