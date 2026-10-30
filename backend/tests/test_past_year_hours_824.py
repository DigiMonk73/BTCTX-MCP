"""
What #824's fix moves, and what it leaves, with the real lookups and their
limits, the sites faked at the HTTP layer: stubs skip the limits, which is
what hid all of this. The past-year question looks first for the hour of a
stored row's missing value and keeps it. Bitstamp's hours after the year
files are asked for at most every 10 minutes, and all of them are kept with
the one asked for. So from the first question on, for those 10 minutes,
values dated there take the hour's price, whichever row or report they're in.
The owner's decisions, 2026-10-30, on a plain before-and-after.

Each test says what the value was before. The ledger: a Buy of 1 BTC in 2019,
and rows dated just after the last year file, Bitstamp's hour at $41,000, the
day at $40,000, your Mempool's hour at $40,500. "This tax year" is 2009 (every
row saves at once) or 2100 (every row is in an earlier tax year).
"""

from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.main import app
from backend.models.btc_price import BtcPriceDaily, BtcPriceHourly
from backend.models.transaction import Transaction
from backend.services import hourly_prices as hp
from backend.services import outbound, price_files as pf
from backend.services import price_history
from backend.services.hourly_prices import find_hours as real_find_hours
from backend.services.price_history import find_prices as real_find_prices
from backend.services.reports.reporting_core import generate_report_data
from backend.tests.conftest import default_login

BANK, WALLET, EXCHANGE_BTC, EXTERNAL = 1, 2, 4, 99
HOUR, DAY = 3600, 86400
NODE = "http://umbrel.local:3006"
BUY = dict(type="Buy", timestamp="2019-03-01T10:00:00Z", from_account_id=BANK, to_account_id=EXCHANGE_BTC,
           amount="1", fee_amount="0", fee_currency="USD", cost_basis_usd="1000")
TIME = "%Y-%m-%dT%H:%M:%SZ"


class Sites:
    """Bitstamp and a Mempool server, faked; `down` holds which of them don't answer."""

    def __init__(self, files_end: int):
        self.files_end, self.down, self.requests = files_end, set(), []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request.url.host)
        if request.url.path == price_history.MEMPOOL_HISTORY_PATH:
            if "mempool" in self.down:
                return httpx.Response(503)
            rows = [{"time": t, "USD": "40000" if t % DAY == 0 else "40500"}
                    for t in range(self.files_end - 40 * DAY, self.files_end + 40 * DAY, HOUR)]
            return httpx.Response(200, json={"prices": rows})
        if "bitstamp" in self.down or "kraken" in request.url.host:
            return httpx.Response(503)
        step = int(request.url.params["step"])
        start = int(request.url.params.get("start", _midnight_today() - 999 * step))
        usd = "41000" if step == HOUR else "40000"
        rows = [{"timestamp": str(t), "open": usd, "volume": "1"} for t in range(start, start + 1000 * step, step)]
        return httpx.Response(200, json={"data": {"pair": "BTC/USD", "ohlc": rows}})


def _midnight_today() -> int:
    today = price_history._today()
    return int(datetime(today.year, today.month, today.day, tzinfo=timezone.utc).timestamp())


class World:
    """A ledger of its own with the real lookups and nothing stored."""

    def __init__(self, client, session, sites, tax_year, files_end):
        self.client, self.session, self.sites, self.tax_year = client, session, sites, tax_year
        self.files_end = files_end
        self.buy = self.post(**BUY)

    def post(self, **row) -> int:
        r = self.client.post("/api/transactions", json=row)
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def after_the_files(self, hours: int = 2) -> str:
        return datetime.fromtimestamp(self.files_end + hours * HOUR + 60, tz=timezone.utc).strftime(TIME)

    def blank_fee(self) -> int:
        """A Transfer with a bitcoin fee and no USD value, as if it were never priced."""
        tx_id = self.post(type="Transfer", timestamp=self.after_the_files(), from_account_id=EXCHANGE_BTC,
                          to_account_id=WALLET, amount="0.5", fee_amount="0.0001", fee_currency="BTC", fee_usd="9.99")
        self.store(tx_id, fee_usd=None, fee_usd_manual=False, price_moment=None)
        return tx_id

    def blank_proceeds(self) -> int:
        """A Spent of 0.05 BTC with no proceeds, and no fee."""
        tx_id = self.post(type="Withdrawal", timestamp=self.after_the_files(), from_account_id=EXCHANGE_BTC,
                          to_account_id=EXTERNAL, amount="0.05", fee_amount="0", fee_currency="BTC", purpose="Spent",
                          gross_proceeds_usd="1")
        self.store(tx_id, proceeds_usd=None, gross_proceeds_usd=None, proceeds_from_price=False, price_moment=None)
        return tx_id

    def store(self, tx_id: int, **values) -> None:
        with self.session() as db:
            db.query(Transaction).filter_by(id=tx_id).update(values)
            db.commit()

    def nothing_stored_yet(self, history_complete: bool = False) -> None:
        """No price kept, and every limit fresh. `history_complete`: only the latest days are asked for, once a day."""
        with self.session() as db:
            db.query(BtcPriceHourly).delete()
            db.query(BtcPriceDaily).delete()
            db.execute(text("DELETE FROM app_settings WHERE key = :key"), {"key": price_history.HISTORY_FLAG})
            if history_complete:
                db.execute(text("INSERT INTO app_settings (key, value) VALUES (:key, '1')"),
                           {"key": price_history.HISTORY_FLAG})
            db.commit()
        price_history.reset_state()
        hp.reset_state()
        self.sites.requests.clear()

    def edit_the_buy(self, year: int = 2100, confirm: str | None = None, basis: str = "1100"):
        self.tax_year(year)
        r = self.client.put(f"/api/transactions/{self.buy}", json={"cost_basis_usd": basis},
                            params={"confirm": confirm} if confirm else None)
        self.tax_year(2009)
        return r

    def question_then_confirm(self, send=None) -> list[int]:
        """The write, confirmed each time it asks: its answers."""
        send = send or (lambda confirm: self.edit_the_buy(confirm=confirm))
        answers, confirm = [], None
        for _ in range(4):
            r = send(confirm)
            answers.append(r.status_code)
            if r.status_code != 409:
                break
            confirm = r.json()["confirm"]
        return answers

    def get(self, tx_id: int) -> dict:
        return self.client.get(f"/api/transactions/{tx_id}").json()

    def fee(self, tx_id: int) -> tuple:
        saved = self.get(tx_id)
        return saved["fee_usd"] and Decimal(saved["fee_usd"]), saved["price_moment"]

    def kept_hours(self) -> int:
        with self.session() as db:
            return db.query(BtcPriceHourly).count()


def ten_minutes_later() -> None:
    hp._state.update(public_at=-1e9, failed_at=-1e9)
    price_history._state.update(mempool_at=-1e9, full_failed_at=-1e9, latest_failed_at=-1e9)


@pytest.fixture
def world(fresh_app, monkeypatch, tmp_path, tax_year) -> World:
    lines = pf.read_manifest(pf.MANIFEST)[:-1]  # a closed year last, so the hours after it are always past
    files_end = lines[-1].last_hour
    manifest = tmp_path / "MANIFEST.csv"
    manifest.write_text(pf.manifest_text(lines), encoding="utf-8")
    monkeypatch.setattr(pf, "MANIFEST", manifest)
    monkeypatch.setattr(hp, "_current_hour", lambda: files_end + 100 * HOUR)
    monkeypatch.setattr(price_history, "find_prices", real_find_prices)
    monkeypatch.setattr(hp, "find_hours", real_find_hours)
    sites = Sites(files_end)
    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(sites.handler))
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    return World(client, fresh_app, sites, tax_year, files_end)


def ai_client(world: World) -> TestClient:
    assert world.client.put("/api/settings/ai-access", json={"on": True}).status_code == 200
    key = world.client.post("/api/settings/ai-key").json()["key"]
    return TestClient(app, headers={"Authorization": f"Bearer {key}"})


# What the owner approved: each was $4.00 at the day's price, or its like

def test_a_question_then_its_confirm(world):
    """Before: $4.00 at the day, and a second question, the fingerprint having changed."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    assert world.question_then_confirm() == [409, 200]
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_a_question_cancelled_then_the_same_row_saved_this_tax_year(world):
    """Before: $4.00 at the day."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    assert world.edit_the_buy().status_code == 409
    assert world.client.put(f"/api/transactions/{blank}", json={"amount": "0.4"}).status_code == 200
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_a_spends_blank_proceeds(world):
    """Before: proceeds $2,000 at the day, and a second question."""
    spend = world.blank_proceeds()
    world.nothing_stored_yet()
    assert world.question_then_confirm() == [409, 200]
    saved = world.get(spend)
    assert (Decimal(saved["gross_proceeds_usd"]), saved["price_moment"]) == (Decimal("2050.00"), "hour")


def test_another_rows_income_after_a_question(world):
    """Before: basis $400 at the day. It's the only row the question didn't look for."""
    world.blank_fee()
    world.nothing_stored_yet()
    assert world.edit_the_buy().status_code == 409
    income = world.post(type="Deposit", timestamp=world.after_the_files(3), from_account_id=EXTERNAL,
                        to_account_id=WALLET, amount="0.01", fee_amount="0", fee_currency="BTC", source="Income")
    saved = world.get(income)
    assert (Decimal(saved["cost_basis_usd"]), saved["price_moment"]) == (Decimal("410.00"), "hour")


def test_a_reports_year_end_value_after_a_question(world):
    """Before: 1 BTC at $40,000, the day's price, noted as having no hourly price."""
    world.blank_fee()
    world.nothing_stored_yet()
    assert world.edit_the_buy().status_code == 409
    year = datetime.fromtimestamp(world.files_end, tz=timezone.utc).year
    with world.session() as db:
        held = generate_report_data(db, year)["end_of_year_balances"]
    values = {Decimal(str(row["value"])) for row in held if row.get("account") and row.get("value") is not None}
    assert values == {Decimal("41000.00")}


def test_a_past_year_write_that_asks_nothing(world):
    """A write with no change of its own, and a change pending: before, its
    two passes priced the row differently ($4.10, $4.00), which asked, and it
    saved $4.00, or 422 with the history complete. Both passes now read one
    price: with a login, a recalculation's changes never ask."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    assert world.question_then_confirm(lambda c: world.edit_the_buy(confirm=c, basis="1000")) == [200]
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_a_refusal_for_no_price_becomes_a_save(world):
    """With the history complete the day's one ask went on a scratch copy, so
    before: 409, then 422, "its network fee has no USD value". With no hour
    to be had it stays that: test_prices_found_lock_free.py."""
    blank = world.blank_fee()
    world.nothing_stored_yet(history_complete=True)
    assert world.question_then_confirm() == [409, 200]
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_your_mempool_down_at_the_question_and_its_fallback_on(world):
    """Before: your Mempool's $4.05, found once it answered again. Bitstamp's is kept for good from the question."""
    outbound._current = outbound.NetworkSettings(price_source="mempool", mempool_url=NODE, mempool_fallback=True)
    blank = world.blank_fee()
    world.nothing_stored_yet()
    world.sites.down = {"mempool"}
    question = world.edit_the_buy()
    assert question.status_code == 409, question.text
    world.sites.down = set()
    ten_minutes_later()
    assert world.question_then_confirm() == [409, 200]
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_a_refused_write_during_an_outage_uses_up_the_ask(world):
    """The one that goes the other way. Before: a write refused before its
    replay reached the row asked nothing, so a save just after got $4.10.
    Now the look first asked, in the outage, and it's 10 minutes till the next."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    world.sites.down = {"bitstamp"}
    world.tax_year(2100)
    refused = world.client.post("/api/transactions", json={
        "type": "Withdrawal", "timestamp": "2019-02-01T10:00:00Z", "from_account_id": EXCHANGE_BTC,
        "to_account_id": EXTERNAL, "amount": "5", "fee_amount": "0", "fee_currency": "BTC", "purpose": "Gift",
        "fmv_usd": "1"})
    world.tax_year(2009)
    assert refused.status_code == 400, refused.text
    world.sites.down = set()
    price_history._state.update(full_failed_at=-1e9, latest_failed_at=-1e9)
    assert world.client.put(f"/api/transactions/{blank}", json={"amount": "0.4"}).status_code == 200
    assert world.fee(blank) == (Decimal("4.00"), "day")


# What stays exactly as it was: each of these passes on the code before the fix too

def test_a_login_write_dated_this_tax_year(world):
    blank = world.blank_fee()
    world.nothing_stored_yet()
    assert world.edit_the_buy(year=2009).status_code == 200
    assert world.fee(blank) == (Decimal("4.10"), "hour")
    assert len(world.sites.requests) == 1


def test_an_ai_write_dated_this_tax_year_with_a_change_pending(world):
    """It asks the question with a change pending, but it isn't a past-year
    write: nothing is looked for first, so the question's copy uses the ask
    and the save takes the day's price."""
    blank = world.blank_fee()
    ai = ai_client(world)
    world.nothing_stored_yet()
    r = ai.put(f"/api/transactions/{world.buy}", json={"cost_basis_usd": "1100"})
    assert r.status_code == 200, r.text
    assert world.fee(blank) == (Decimal("4.00"), "day")


def test_an_add_dated_last_leaves_the_blank_row_alone(world):
    blank = world.blank_fee()
    world.nothing_stored_yet()
    world.tax_year(2100)
    r = world.client.post("/api/transactions", json={
        "type": "Buy", "timestamp": world.after_the_files(5), "from_account_id": BANK, "to_account_id": EXCHANGE_BTC,
        "amount": "0.01", "fee_amount": "0", "fee_currency": "USD", "cost_basis_usd": "10"})
    world.tax_year(2009)
    assert r.status_code == 409, r.text
    assert world.fee(blank) == (None, None)
    assert world.sites.requests == [] and world.kept_hours() == 0


def test_the_coins_list_keeps_no_hour(world):
    world.blank_fee()
    world.nothing_stored_yet()
    r = world.client.post("/api/transactions/coins-moved", json={
        "type": "Transfer", "timestamp": "2019-06-01T10:00:00Z", "from_account_id": EXCHANGE_BTC,
        "to_account_id": WALLET, "amount": "0.1", "fee_amount": "0.0001", "fee_currency": "BTC", "fee_usd": "5"})
    assert r.status_code == 200, r.text
    assert world.kept_hours() == 0


def test_the_ais_preview_asks_and_keeps_what_it_did(world):
    """Its own dry run keeps the hours it asks for, as it always has."""
    blank = world.blank_fee()
    ai = ai_client(world)
    world.nothing_stored_yet()
    world.tax_year(2100)
    r = ai.post("/api/import/entries/preview", json={"rows": [{
        "date": "2019-02-01T10:00:00Z", "type": "Buy", "amount": "0.2", "from_account": "Bank",
        "to_account": "Exchange BTC", "cost_basis_usd": "200.00", "fee_amount": "0", "fee_currency": "USD"}]})
    world.tax_year(2009)
    assert r.status_code == 200, r.text
    assert world.kept_hours() == 100 and world.sites.requests == ["www.bitstamp.net"]
    assert world.fee(blank) == (None, None)
