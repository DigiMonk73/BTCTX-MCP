"""
#824 and #849, with the real lookups and their limits, the sites faked at
the HTTP layer: stubs skip the limits, which is what hid the bug. Bitstamp's
hours after the year files are asked for at most every 10 minutes
(hourly_prices._bitstamp_after). A lookup on a scratch copy (the past-year
question's replays, the coins list, a report's holdings, Ledger Review's
check) kept the answer on the copy, which goes, and every lookup in the rest
of those 10 minutes got none and took the day's price. For those 10 minutes
a lookup is now given that last answer again, from memory: what the ledger
stores is still only what a lookup in it keeps.

Each test says what it gives on the code before the fix ("Before") when
that differs; the rest give the same on both ("Stays"). The ledger: a Buy of
1 BTC in 2019, and rows dated just after the last year file; Bitstamp's hour
$41,000, the day $40,000, your Mempool's hour $40,500. On a 0.0001 BTC fee:
$4.10, $4.00, $4.05. "This tax year" is 2009 (every row saves at once) or
2100 (every row is in an earlier tax year).
"""

from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.main import app
from backend.models.app_setting import save_setting
from backend.models.btc_price import BtcPriceDaily, BtcPriceHourly
from backend.models.transaction import Transaction
from backend.services import hourly_prices as hp
from backend.services import outbound, past_years, price_history, recalculated_by
from backend.services import price_files as pf
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
BITSTAMP = "www.bitstamp.net"


class Sites:
    """Bitstamp and a Mempool server, faked: `down` holds which of them don't
    answer, `mempool_lacks` the hours your Mempool has no live price for."""

    def __init__(self, files_end: int):
        self.files_end, self.down, self.mempool_lacks, self.requests = files_end, set(), set(), []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request.url.host)
        if request.url.path == price_history.MEMPOOL_HISTORY_PATH:
            if "mempool" in self.down:
                return httpx.Response(503)
            rows = [{"time": t, "USD": "40000" if t % DAY == 0 else "40500"}
                    for t in range(self.files_end - 40 * DAY, self.files_end + 40 * DAY, HOUR)
                    if t not in self.mempool_lacks]
            return httpx.Response(200, json={"prices": rows})
        if "bitstamp" in self.down or "kraken" in request.url.host:
            return httpx.Response(503)
        step = int(request.url.params["step"])
        start = int(request.url.params.get("start", _midnight_today() - 999 * step))
        usd = "41000" if step == HOUR else "40000"
        rows = [{"timestamp": str(t), "open": usd, "volume": "1"} for t in range(start, start + 1000 * step, step)]
        return httpx.Response(200, json={"data": {"pair": "BTC/USD", "ohlc": rows}})

    def bitstamp_asked(self) -> int:
        return self.requests.count(BITSTAMP)


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

    def blank_fee(self, saved_at: str = "9.99", moment: str | None = None) -> int:
        """A Transfer with a bitcoin fee and no USD value, as if it were never
        priced; its lot disposals as a save at `saved_at` left them."""
        tx_id = self.post(type="Transfer", timestamp=self.after_the_files(), from_account_id=EXCHANGE_BTC,
                          to_account_id=WALLET, amount="0.5", fee_amount="0.0001", fee_currency="BTC",
                          fee_usd=saved_at)
        self.store(tx_id, fee_usd=None, fee_usd_manual=False, price_moment=moment)
        return tx_id

    def blank_proceeds(self, fee_amount: str = "0", fee_usd: str | None = None, blank_fee: bool = False) -> int:
        """A Spent of 0.05 BTC with no proceeds; its fee typed, or blank too."""
        fee = {"fee_amount": fee_amount, "fee_currency": "BTC", **({"fee_usd": fee_usd} if fee_usd else {})}
        tx_id = self.post(type="Withdrawal", timestamp=self.after_the_files(), from_account_id=EXCHANGE_BTC,
                          to_account_id=EXTERNAL, amount="0.05", purpose="Spent", gross_proceeds_usd="1", **fee)
        blanked = dict(proceeds_usd=None, gross_proceeds_usd=None, proceeds_from_price=False, price_moment=None)
        if blank_fee:
            blanked.update(fee_usd=None, fee_usd_manual=False)
        self.store(tx_id, **blanked)
        return tx_id

    def spend_with_a_blank_fee(self) -> int:
        """A Spent of 0.05 BTC, its proceeds typed ($2,000), its 0.0001 BTC fee's value blank."""
        tx_id = self.post(type="Withdrawal", timestamp=self.after_the_files(), from_account_id=EXCHANGE_BTC,
                          to_account_id=EXTERNAL, amount="0.05", purpose="Spent", gross_proceeds_usd="2000",
                          fee_amount="0.0001", fee_currency="BTC", fee_usd="9.99")
        self.store(tx_id, fee_usd=None, fee_usd_manual=False)
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

    def nothing_pending(self) -> None:
        """This BitcoinTX last recalculated the ledger: the question's one replay is the write's."""
        with self.session() as db:
            save_setting(db, recalculated_by.KEY, recalculated_by.stamp(db))
            db.commit()

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

    def a_question(self) -> dict:
        """A past-year edit of the Buy, cancelled: the 409's body."""
        r = self.edit_the_buy()
        assert r.status_code == 409, r.text
        return r.json()

    def save_this_year(self, tx_id: int, **edit):
        return self.client.put(f"/api/transactions/{tx_id}", json=edit or {"amount": "0.4"})

    def coins_list(self):
        r = self.client.post("/api/transactions/coins-moved", json={
            "type": "Transfer", "timestamp": "2019-06-01T10:00:00Z", "from_account_id": EXCHANGE_BTC,
            "to_account_id": WALLET, "amount": "0.1", "fee_amount": "0.0001", "fee_currency": "BTC", "fee_usd": "5"})
        return r

    def income(self, hours: int = 3):
        return self.client.post("/api/transactions", json={
            "type": "Deposit", "timestamp": self.after_the_files(hours), "from_account_id": EXTERNAL,
            "to_account_id": WALLET, "amount": "0.01", "fee_amount": "0", "fee_currency": "BTC", "source": "Income"})

    def get(self, tx_id: int) -> dict:
        return self.client.get(f"/api/transactions/{tx_id}").json()

    def fee(self, tx_id: int) -> tuple:
        saved = self.get(tx_id)
        return saved["fee_usd"] and Decimal(saved["fee_usd"]), saved["price_moment"]

    def basis(self, tx_id: int) -> tuple:
        saved = self.get(tx_id)
        return Decimal(saved["cost_basis_usd"]), saved["price_moment"]

    def kept_hours(self) -> int:
        with self.session() as db:
            return db.query(BtcPriceHourly).count()

    def source(self, **settings) -> None:
        outbound._current = outbound.NetworkSettings(**settings)


MEMPOOL_ALONE = dict(price_source="mempool", mempool_url=NODE)
MEMPOOL_WITH_FALLBACK = dict(MEMPOOL_ALONE, mempool_fallback=True)


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
    saved = outbound._current
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    yield World(client, fresh_app, sites, tax_year, files_end)
    outbound._current = saved


def ai_client(world: World) -> TestClient:
    assert world.client.put("/api/settings/ai-access", json={"on": True}).status_code == 200
    key = world.client.post("/api/settings/ai-key").json()["key"]
    return TestClient(app, headers={"Authorization": f"Bearer {key}"})


# The cases the issues name: a save after the question or the list

def test_a_question_then_its_confirm(world):
    """#824. Before: $4.00 at the day, and a second question, the
    fingerprint having changed between the two. Bitstamp is asked once."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    assert world.question_then_confirm() == [409, 200]
    assert world.fee(blank) == (Decimal("4.10"), "hour")
    assert world.sites.bitstamp_asked() == 1


def test_the_question_stores_no_price(world):
    """Stays: the question keeps nothing in the ledger, so nothing it found
    outlasts the 10 minutes (the earlier fix's lesson, #824's hand-over)."""
    world.blank_fee()
    world.nothing_stored_yet()
    world.a_question()
    assert world.kept_hours() == 0


def test_the_confirm_keeps_only_the_hour_it_uses(world):
    """Before: it kept the day it used, no hour. Not the block of hours
    Bitstamp gave the question: another row ten minutes on, Bitstamp down,
    has no hour, as before (the day's history is down too: 422)."""
    world.blank_fee()
    world.nothing_stored_yet()
    assert world.question_then_confirm() == [409, 200]
    assert world.kept_hours() == 1
    ten_minutes_later()
    world.sites.down = {"bitstamp"}
    assert world.income().status_code == 422


def test_a_question_cancelled_then_the_same_row_saved_this_tax_year(world):
    """Before: $4.00 at the day."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    world.a_question()
    assert world.save_this_year(blank).status_code == 200
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_ten_minutes_after_a_cancelled_question(world):
    """Stays: Bitstamp is asked again, and gives the hour."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    world.a_question()
    ten_minutes_later()
    assert world.save_this_year(blank).status_code == 200
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_two_coins_lists_then_a_save(world):
    """#849's table. Before: the fee at $4.00, the day's, and each list asked again."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    assert world.coins_list().status_code == 200
    assert world.coins_list().status_code == 200
    assert world.edit_the_buy(year=2009).status_code == 200
    assert world.fee(blank) == (Decimal("4.10"), "hour")
    assert world.sites.bitstamp_asked() == 1


def test_the_coins_list_stores_no_price(world):
    """Stays."""
    world.blank_fee()
    world.nothing_stored_yet()
    assert world.coins_list().status_code == 200
    assert world.kept_hours() == 0


# A Spent's proceeds, and its fee (B1 of #824's hand-over)

def test_a_spends_blank_proceeds(world):
    """Before: proceeds $2,000 at the day, and a second question."""
    spend = world.blank_proceeds()
    world.nothing_stored_yet()
    assert world.question_then_confirm() == [409, 200]
    saved = world.get(spend)
    assert (Decimal(saved["gross_proceeds_usd"]), saved["price_moment"]) == (Decimal("2050.00"), "hour")


def test_a_spends_blank_proceeds_with_a_typed_fee(world):
    """Before: proceeds $2,000, net $1,990.01."""
    spend = world.blank_proceeds(fee_amount="0.0001", fee_usd="9.99")
    world.nothing_stored_yet()
    assert world.question_then_confirm() == [409, 200]
    saved = world.get(spend)
    assert (Decimal(saved["gross_proceeds_usd"]), Decimal(saved["proceeds_usd"])) == (Decimal("2050.00"),
                                                                                      Decimal("2040.01"))


def test_a_spends_blank_proceeds_and_fee(world):
    """Before: net $1,996.00, one price at the day for both."""
    spend = world.blank_proceeds(fee_amount="0.0001", fee_usd="9.99", blank_fee=True)
    world.nothing_stored_yet()
    assert world.question_then_confirm() == [409, 200]
    saved = world.get(spend)
    assert (Decimal(saved["proceeds_usd"]), Decimal(saved["fee_usd"])) == (Decimal("2045.90"), Decimal("4.10"))


def test_a_spend_whose_only_blank_is_its_fee(world):
    """Before: the fee $4.00, net $1,996.00."""
    spend = world.spend_with_a_blank_fee()
    world.nothing_stored_yet()
    assert world.question_then_confirm() == [409, 200]
    saved = world.get(spend)
    assert (Decimal(saved["proceeds_usd"]), Decimal(saved["fee_usd"])) == (Decimal("1995.90"), Decimal("4.10"))


def test_a_spends_blank_proceeds_saved_after_a_cancelled_question(world):
    """Before: proceeds $2,000 at the day."""
    spend = world.blank_proceeds()
    world.nothing_stored_yet()
    world.a_question()
    assert world.save_this_year(spend, amount="0.05").status_code == 200
    assert Decimal(world.get(spend)["gross_proceeds_usd"]) == Decimal("2050.00")


# Another row, or a report, in the 10 minutes after a question (B3, E)

def test_another_rows_income_after_a_question(world):
    """Before: basis $400 at the day."""
    world.blank_fee()
    world.nothing_stored_yet()
    world.a_question()
    r = world.income()
    assert r.status_code == 200, r.text
    assert world.basis(r.json()["id"]) == (Decimal("410.00"), "hour")


def test_another_rows_income_after_a_coins_list(world):
    """Before: basis $400 at the day."""
    world.blank_fee()
    world.nothing_stored_yet()
    assert world.coins_list().status_code == 200
    r = world.income()
    assert r.status_code == 200, r.text
    assert world.basis(r.json()["id"]) == (Decimal("410.00"), "hour")


def _year_end_values(world) -> set:
    year = datetime.fromtimestamp(world.files_end, tz=timezone.utc).year
    with world.session() as db:
        held = generate_report_data(db, year)["end_of_year_balances"]
    return {Decimal(str(row["value"])) for row in held if row.get("account") and row.get("value") is not None}


def test_a_reports_year_end_value_after_a_question(world):
    """Before: 1 BTC at $40,000, the day's price, noted as having no hourly price."""
    world.blank_fee()
    world.nothing_stored_yet()
    world.a_question()
    assert _year_end_values(world) == {Decimal("41000.00")}


def test_an_income_after_a_report_with_no_blank_row(world):
    """A report values a year's end on a scratch copy: a year ending after
    the year files asks Bitstamp there (from 1 January 2027 for 2026, with
    2.0.0's files), with no blank row in the ledger. Before: basis $400 at the day."""
    world.nothing_stored_yet()
    _year_end_values(world)
    r = world.income()
    assert r.status_code == 200, r.text
    assert world.basis(r.json()["id"]) == (Decimal("410.00"), "hour")


def test_a_save_after_a_report(world):
    """A report's holdings replay on a scratch copy too. Before: $4.00 at the day."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    _year_end_values(world)
    assert world.save_this_year(blank).status_code == 200
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_a_save_after_ledger_review(world):
    """Ledger Review's check replays on a scratch copy too. Before: $4.00 at the day."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    assert world.client.get("/api/review").status_code == 200
    assert world.save_this_year(blank).status_code == 200
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_the_ais_preview_of_another_row_after_a_question(world):
    """Before: $400 at the day."""
    world.blank_fee()
    ai = ai_client(world)
    world.nothing_stored_yet()
    world.a_question()
    r = ai.post("/api/import/entries/preview", json={"rows": [{
        "date": world.after_the_files(3), "type": "Deposit", "amount": "0.01", "from_account": "External",
        "to_account": "Wallet", "source": "Income", "fee_amount": "0", "fee_currency": "BTC"}]})
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["results"][0]["normalized"]["cost_basis_usd"]) == Decimal("410.00")


def test_an_edit_pricing_a_day_priced_row_again_after_a_question(world):
    """Before: $8.00 at the day."""
    world.blank_fee()
    day_priced = world.post(type="Transfer", timestamp=world.after_the_files(4), from_account_id=EXCHANGE_BTC,
                            to_account_id=WALLET, amount="0.1", fee_amount="0.0001", fee_currency="BTC")
    world.store(day_priced, price_moment="day")
    world.nothing_stored_yet()
    world.a_question()
    assert world.save_this_year(day_priced, fee_amount="0.0002").status_code == 200
    assert world.fee(day_priced) == (Decimal("8.20"), "hour")


def test_ledger_review_offers_the_hour_after_a_question(world):
    """Before: a value priced at the day wasn't listed: no hour to be had in those 10 minutes."""
    world.blank_fee()
    day_priced = world.post(type="Transfer", timestamp=world.after_the_files(4), from_account_id=EXCHANGE_BTC,
                            to_account_id=WALLET, amount="0.1", fee_amount="0.0001", fee_currency="BTC")
    world.nothing_stored_yet()
    world.store(day_priced, price_moment="day", fee_usd=Decimal("4.00"))
    world.a_question()
    applied = world.client.post("/api/review/hourly-prices", json={"ids": [day_priced]})
    assert applied.status_code == 200, applied.text
    assert [c["id"] for c in applied.json()["changed"]] == [day_priced]
    assert world.fee(day_priced) == (Decimal("4.10"), "hour")


def test_login_recalculate_after_a_question(world):
    """Before: $4.00 at the day."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    world.a_question()
    assert world.client.post("/api/transactions/recalculate").status_code == 200
    assert world.fee(blank) == (Decimal("4.10"), "hour")


# A question that goes away, and refusals that become saves (B4, B5, B8, D)

def test_a_past_year_write_that_asks_nothing_saves_the_hour(world):
    """B4: nothing pending, and the replay at the hour changes nothing
    stored, so it saves in the same request. Before: $4.00 at the day."""
    blank = world.blank_fee(saved_at="4.10")
    world.nothing_pending()
    world.nothing_stored_yet()
    assert world.question_then_confirm(lambda c: world.edit_the_buy(confirm=c, basis="1000")) == [200]
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_a_past_year_write_with_only_a_change_pending(world):
    """B8: a write with no change of its own, and a change pending. Before,
    its two replays priced the row differently ($4.10, $4.00), which asked,
    and it saved $4.00. Both read one price now: with a login, a
    recalculation's changes never ask."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    assert world.question_then_confirm(lambda c: world.edit_the_buy(confirm=c, basis="1000")) == [200]
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_a_refusal_for_no_price_becomes_a_save(world):
    """B5: with the history complete, the day's one ask went on a scratch
    copy too. Before: 409, then 422, "its network fee has no USD value"."""
    blank = world.blank_fee()
    world.nothing_stored_yet(history_complete=True)
    assert world.question_then_confirm() == [409, 200]
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_a_refusal_after_a_cancelled_question_becomes_a_save(world):
    """B5. Before: 422."""
    blank = world.blank_fee()
    world.nothing_stored_yet(history_complete=True)
    world.a_question()
    r = world.save_this_year(blank)
    assert r.status_code == 200, r.text
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_the_tax_timezone_after_a_question(world):
    """B5, a write of its own. Before: 422."""
    blank = world.blank_fee()
    world.nothing_stored_yet(history_complete=True)
    world.a_question()
    world.tax_year(2100)
    answers = world.question_then_confirm(lambda c: world.client.put(
        "/api/settings/tax-timezone", json={"timezone": "America/Chicago", "chosen": True},
        params={"confirm": c} if c else None))
    world.tax_year(2009)
    assert answers[-1] == 200
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_the_ais_recalculate_after_a_question(world):
    """B5, with the AI key. Before: 422."""
    blank = world.blank_fee()
    ai = ai_client(world)
    world.nothing_stored_yet(history_complete=True)
    world.a_question()
    world.tax_year(2100)
    answers = world.question_then_confirm(lambda c: ai.post(
        "/api/transactions/recalculate", params={"confirm": c} if c else None))
    world.tax_year(2009)
    assert answers[-1] == 200
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_an_ai_write_dated_this_tax_year_with_a_change_pending(world):
    """With the AI key a change pending asks even for this tax year, so it
    has the question's replays. Before: $4.00 at the day."""
    blank = world.blank_fee()
    ai = ai_client(world)
    world.nothing_stored_yet()
    r = ai.put(f"/api/transactions/{world.buy}", json={"cost_basis_usd": "1100"})
    assert r.status_code == 200, r.text
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_an_ai_write_dated_this_tax_year_with_the_history_complete(world):
    """Before: 422."""
    blank = world.blank_fee()
    ai = ai_client(world)
    world.nothing_stored_yet(history_complete=True)
    r = ai.put(f"/api/transactions/{world.buy}", json={"cost_basis_usd": "1100"})
    assert r.status_code == 200, r.text
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_the_days_ask_isnt_used_up_by_a_question(world):
    """D: the replay without the write took the day's price, and with it
    the day's one ask for the latest days, on a scratch copy. With the hour
    given again it asks for no day, so an Inherited deposit (priced at the
    date of death's day) is priced. Before: 422."""
    world.blank_fee()
    world.nothing_stored_yet(history_complete=True)
    world.a_question()
    death = world.after_the_files(30)[:10]
    r = world.client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": world.after_the_files(30), "from_account_id": EXTERNAL,
        "to_account_id": WALLET, "amount": "0.01", "fee_amount": "0", "fee_currency": "BTC", "source": "Inherited",
        "acquired_at": death})
    assert r.status_code == 200, r.text
    assert world.basis(r.json()["id"]) == (Decimal("400.00"), "day")


def test_the_coins_list_after_a_question_with_the_history_complete(world):
    """E. Before: 422, the list's replay finding no price for the blank row."""
    world.blank_fee()
    world.nothing_stored_yet(history_complete=True)
    world.a_question()
    assert world.coins_list().status_code == 200


# The question's own words

def test_with_a_change_pending_the_question_reads_one_price(world):
    """Both replays price the blank fee at the hour ($4.10, a gain of $4.00
    on its $0.10 of cost). Before, the one without the write took the day's
    ($4.00): pending read "9.89 -> 3.90" and the write's change "3.90 -> 3.99"."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    body = world.a_question()
    by_id = {(item["id"], key): item["change"] for key in ("changes", "pending") for item in body[key]}
    assert by_id[(blank, "pending")] == "taxable gain incl. network fees 9.89 -> 4.00."
    assert by_id[(blank, "changes")].startswith("taxable gain incl. network fees 4.00 -> 3.99;")


def test_a_question_out_of_time_names_the_years_as_before(world, monkeypatch):
    """Stays: nothing is looked for outside the replays the budget times."""
    world.blank_fee()
    world.nothing_stored_yet()
    monkeypatch.setattr(past_years, "DRY_RUN_SECONDS", 0)
    assert world.a_question()["exact"] is False


# What stays as it was: your Mempool, a source down or switched, a refused write

def test_your_mempool_down_at_the_question_and_its_fallback_on_ten_minutes_later(world):
    """B6, after 10 minutes. Stays: your Mempool's $4.05, asked again."""
    world.source(**MEMPOOL_WITH_FALLBACK)
    blank = world.blank_fee()
    world.nothing_stored_yet()
    world.sites.down = {"mempool"}
    world.a_question()
    world.sites.down = set()
    ten_minutes_later()
    assert world.save_this_year(blank).status_code == 200
    assert world.fee(blank) == (Decimal("4.05"), "hour")


def test_your_mempool_down_at_the_question_and_its_fallback_on_within_ten_minutes(world):
    """B6, within 10 minutes: your Mempool isn't asked again yet (its answer,
    none, is kept that long), and its fallback's hour is given again.
    Before: $4.00 at the day."""
    world.source(**MEMPOOL_WITH_FALLBACK)
    blank = world.blank_fee()
    world.nothing_stored_yet()
    world.sites.down = {"mempool"}
    world.a_question()
    world.sites.down = set()
    assert world.save_this_year(blank).status_code == 200
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_your_mempool_missing_the_blank_rows_hour_with_its_fallback_on(world):
    """C4. The blank row's hour comes from the fallback; before: $4.00 at
    the day. Another row's hour your Mempool has stays its own: $405."""
    world.source(**MEMPOOL_WITH_FALLBACK)
    blank = world.blank_fee()
    world.nothing_stored_yet()
    world.sites.mempool_lacks = {hp.hour_of(datetime.strptime(world.after_the_files(), TIME))}
    assert world.question_then_confirm() == [409, 200]
    assert world.fee(blank) == (Decimal("4.10"), "hour")
    r = world.income(hours=6)  # its hour and the two beside it are your Mempool's
    assert world.basis(r.json()["id"]) == (Decimal("405.00"), "hour")


@pytest.mark.parametrize("later", [
    ("off", dict(price_source="off"), 422, None),
    ("mempool alone", MEMPOOL_ALONE, 200, Decimal("4.05")),
])
def test_a_source_switched_after_a_question(world, later):
    """C2. Stays: an hour given again only while public sites are allowed."""
    _, settings, status, fee = later
    blank = world.blank_fee()
    world.nothing_stored_yet()
    world.a_question()
    world.source(**settings)
    assert world.save_this_year(blank).status_code == status
    assert world.fee(blank)[0] == fee


def test_bitstamp_down_ten_minutes_after_a_question(world):
    """C1, after 10 minutes. Stays: Bitstamp is asked again, fails, and nothing is given again."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    world.a_question()
    ten_minutes_later()
    world.sites.down = {"bitstamp"}
    assert world.save_this_year(blank).status_code == 422
    assert world.fee(blank) == (None, None)


def test_bitstamp_down_within_ten_minutes_of_a_question(world):
    """C1, within 10 minutes: Bitstamp isn't asked; its answer is given again. Before: $4.00 at the day."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    world.a_question()
    world.sites.down = {"bitstamp"}
    assert world.save_this_year(blank).status_code == 200
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def _refused_past_year_write(world):
    """A write refused before its replay reaches the blank row: 5 BTC leave an account holding 1."""
    world.tax_year(2100)
    r = world.client.post("/api/transactions", json={
        "type": "Withdrawal", "timestamp": "2019-02-01T10:00:00Z", "from_account_id": EXCHANGE_BTC,
        "to_account_id": EXTERNAL, "amount": "5", "fee_amount": "0", "fee_currency": "BTC", "purpose": "Gift",
        "fmv_usd": "1"})
    world.tax_year(2009)
    assert r.status_code == 400, r.text


@pytest.mark.parametrize("settings, down, fee", [
    ({}, {"bitstamp"}, Decimal("4.10")),  # B7
    (MEMPOOL_ALONE, {"mempool"}, Decimal("4.05")),  # A1
    (MEMPOOL_WITH_FALLBACK, {"mempool"}, Decimal("4.05")),  # C5
    (MEMPOOL_WITH_FALLBACK, {"mempool", "bitstamp"}, Decimal("4.05")),  # C5
])
def test_a_refused_write_during_an_outage_asks_nothing(world, settings, down, fee):
    """Stays: the refused write's replay never reaches the row, so it asks
    nothing, and a save once the source is back asks for itself."""
    if settings:
        world.source(**settings)
    blank = world.blank_fee()
    world.nothing_stored_yet()
    world.sites.down = set(down)
    _refused_past_year_write(world)
    world.sites.down = set()
    assert world.save_this_year(blank).status_code == 200
    assert world.fee(blank) == (fee, "hour")


def test_your_mempool_alone_down_ten_minutes_after_a_question(world):
    """A2. Stays: your Mempool's answer goes after its 10 minutes as it did; no Bitstamp."""
    world.source(**MEMPOOL_ALONE)
    blank = world.blank_fee()
    world.nothing_stored_yet()
    world.a_question()
    ten_minutes_later()
    world.sites.down = {"mempool"}
    r = world.save_this_year(blank)
    assert (r.status_code, world.fee(blank)) in {(422, (None, None)), (200, (Decimal("4.00"), "day"))}
    assert world.sites.bitstamp_asked() == 0


@pytest.mark.parametrize("later, fee", [
    (dict(price_source="off"), None),
    (dict(price_source="public"), Decimal("4.10")),
])
def test_your_mempool_alone_then_a_source_switched(world, later, fee):
    """A3. Stays: to off, no price; to public sites, Bitstamp is asked for itself."""
    world.source(**MEMPOOL_ALONE)
    blank = world.blank_fee()
    world.nothing_stored_yet()
    world.a_question()
    world.source(**later)
    world.save_this_year(blank)
    assert world.fee(blank)[0] == fee


def test_your_mempool_up_at_the_question_with_its_fallback_on(world):
    """C3. Stays: your Mempool has the hour, so Bitstamp isn't asked, and nothing is given again."""
    world.source(**MEMPOOL_WITH_FALLBACK)
    blank = world.blank_fee()
    world.nothing_stored_yet()
    assert world.question_then_confirm() == [409, 200]
    assert world.fee(blank) == (Decimal("4.05"), "hour")
    assert world.sites.bitstamp_asked() == 0


def test_a_row_inside_the_files_years_with_your_mempool(world):
    """B. Stays: an hour inside the year files' years never comes from Bitstamp's later hours."""
    world.source(**MEMPOOL_ALONE)
    inside = world.post(type="Transfer", timestamp=datetime.fromtimestamp(
        world.files_end - 10 * HOUR + 60, tz=timezone.utc).strftime(TIME), from_account_id=EXCHANGE_BTC,
        to_account_id=WALLET, amount="0.5", fee_amount="0.0001", fee_currency="BTC", fee_usd="9.99")
    world.store(inside, fee_usd=None, fee_usd_manual=False)
    world.nothing_stored_yet()
    assert world.question_then_confirm() == [409, 200]
    assert world.fee(inside) == (Decimal("4.05"), "hour")


# What stays as it was: no question first, or a write that replays nothing

def test_a_login_write_dated_this_tax_year(world):
    blank = world.blank_fee()
    world.nothing_stored_yet()
    assert world.edit_the_buy(year=2009).status_code == 200
    assert world.fee(blank) == (Decimal("4.10"), "hour")
    assert world.sites.bitstamp_asked() == 1


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


def test_the_ais_preview_keeps_what_it_did(world):
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
    assert world.kept_hours() == 100 and world.sites.requests == [BITSTAMP]
    assert world.fee(blank) == (None, None)


def test_an_income_with_no_question_first(world):
    r_blank = world.blank_fee()
    world.nothing_stored_yet()
    r = world.income()
    assert world.basis(r.json()["id"]) == (Decimal("410.00"), "hour")
    assert world.fee(r_blank) == (None, None)


# The race #824's re-check reported

def test_a_row_deleted_while_its_question_is_worked_out(world, monkeypatch):
    """Deleted by another save between the check that it's a past-year
    write and the look for its prices. Before: 500 (an AttributeError)."""
    spend = world.blank_proceeds()
    world.nothing_stored_yet()
    saves_at_once = past_years._saves_at_once

    def deleted_meanwhile(write, db, *rest):
        answer = saves_at_once(write, db, *rest)
        with world.session() as other:
            for table, key in (("lot_disposals", "transaction_id"), ("ledger_entries", "transaction_id"),
                               ("transactions", "id")):
                other.execute(text(f"DELETE FROM {table} WHERE {key} = :id"), {"id": spend})
            other.commit()
        return answer

    monkeypatch.setattr(past_years, "_saves_at_once", deleted_meanwhile)
    world.tax_year(2100)
    r = world.save_this_year(spend, amount="0.04")
    world.tax_year(2009)
    assert r.status_code == 404, r.text
