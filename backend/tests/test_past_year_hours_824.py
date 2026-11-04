"""
#824 and #849, with the real lookups and their limits, the sites faked at
the HTTP layer: stubs skip the limits, which is what hid the bug. Bitstamp's
hours after the year files are asked for at most every 10 minutes
(hourly_prices._bitstamp_after). A replay on a scratch copy (the past-year
question's, the coins list's, a report's, Ledger Review's) that priced a
stored row's missing value (a BTC fee with no USD value, a Spent's blank
proceeds) kept the hour on the copy, which goes, and a replay in the rest of
those 10 minutes took the day's price for it. Only such a value is now given
the hour the copy found, from memory (hourly_prices._found_for_a_stored_value):
never kept in the ledger, and with the day's prices looked for as before, so
every other row, report and price read gives what it gave.

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
from sqlalchemy.exc import OperationalError

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
def world(request, fresh_app, monkeypatch, tmp_path, tax_year) -> World:
    """The year files end with a closed year, so the hours after them are
    always past; or, `files_end_mid_year`, as this release's do."""
    lines = pf.read_manifest(pf.MANIFEST)
    lines = lines if getattr(request, "param", None) == "files_end_mid_year" else lines[:-1]
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


def test_a_question_then_its_confirm(world):
    """#824. Before: $4.00 at the day, and a second question, the
    fingerprint having changed between the two. The hour isn't kept in the
    ledger, and the day's prices are looked for as before."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    assert world.question_then_confirm() == [409, 200]
    assert world.fee(blank) == (Decimal("4.10"), "hour")
    assert world.kept_hours() == 0


def test_the_question_stores_no_price(world):
    """Stays: the question keeps nothing in the ledger, so nothing it found
    outlasts the 10 minutes (the earlier fix's lesson, #824's hand-over)."""
    world.blank_fee()
    world.nothing_stored_yet()
    world.a_question()
    assert world.kept_hours() == 0


def test_the_confirm_keeps_no_hour_in_the_ledger(world):
    """Stays: no hour kept, and the day's prices downloaded as before, so
    another row ten minutes on, Bitstamp down, takes the day's: $400."""
    _confirmed(world)
    assert world.kept_hours() == 0
    ten_minutes_later()
    world.sites.down = {"bitstamp"}
    r = world.income()
    assert world.basis(r.json()["id"]) == (Decimal("400.00"), "day")


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


def test_two_blank_rows_in_different_hours(world):
    """One ask of Bitstamp gives both hours, kept on the copy for the second
    row: both are given. Before: both at $4.00, the day's, asked twice."""
    first = world.blank_fee()
    second = world.post(type="Transfer", timestamp=world.after_the_files(5), from_account_id=EXCHANGE_BTC,
                        to_account_id=WALLET, amount="0.1", fee_amount="0.0001", fee_currency="BTC", fee_usd="9.99")
    world.store(second, fee_usd=None, fee_usd_manual=False, price_moment=None)
    world.nothing_stored_yet()
    assert world.question_then_confirm() == [409, 200]
    assert world.fee(first) == world.fee(second) == (Decimal("4.10"), "hour")


@pytest.mark.parametrize("world", ["files_end_mid_year"], indirect=True)
def test_a_save_after_the_report_of_the_blank_rows_year(world):
    """The report's year-end replay prices the blank row on its copy (the
    year's start is inside the files, so nothing else asked first). Before:
    $4.00, the day's."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    with world.session() as db:
        generate_report_data(db, datetime.fromtimestamp(world.files_end, tz=timezone.utc).year)
    assert world.save_this_year(blank).status_code == 200
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_another_row_deleted_after_a_question(world):
    """The delete's save recalculates. Before: $4.00 at the day."""
    blank = world.blank_fee()
    other = world.income(hours=40).json()["id"]
    world.nothing_stored_yet()
    world.a_question()
    assert world.client.delete(f"/api/transactions/{other}").status_code == 204
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_the_ais_add_of_a_past_year_row_after_a_question(world):
    """Before: $4.00 at the day."""
    blank = world.blank_fee()
    ai = ai_client(world)
    world.nothing_stored_yet()
    world.a_question()
    row = {"date": "2019-02-01T10:00:00Z", "type": "Buy", "amount": "0.2", "from_account": "Bank",
           "to_account": "Exchange BTC", "cost_basis_usd": "200.00", "fee_amount": "0", "fee_currency": "USD"}
    world.tax_year(2100)
    answers = world.question_then_confirm(lambda c: ai.post(
        "/api/import/entries/execute", json={"rows": [row]}, params={"confirm": c} if c else None))
    world.tax_year(2009)
    assert answers[-1] == 200, answers
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_two_coins_lists_then_a_save(world):
    """#849's table. Before: the fee at $4.00, the day's."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    assert world.coins_list().status_code == 200
    assert world.coins_list().status_code == 200
    assert world.edit_the_buy(year=2009).status_code == 200
    assert world.fee(blank) == (Decimal("4.10"), "hour")
    assert world.kept_hours() == 0


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


def test_a_spends_blank_proceeds_after_an_edit_of_its_amount(world):
    """Its proceeds stay the stored row's blank. Before: $2,400 at the day."""
    spend = world.blank_proceeds()
    world.nothing_stored_yet()
    world.a_question()
    assert world.save_this_year(spend, amount="0.06").status_code == 200
    assert _proceeds(world, spend) == (Decimal("2460.00"), "hour")


# Stays: another row, a report, a preview or a price read, after a question (B3, E)

def test_another_rows_income_after_a_question(world):
    """Stays: another row's value isn't a stored row's missing value: $400 at the day."""
    world.blank_fee()
    world.nothing_stored_yet()
    world.a_question()
    r = world.income()
    assert r.status_code == 200, r.text
    assert world.basis(r.json()["id"]) == (Decimal("400.00"), "day")


def test_another_rows_income_after_a_coins_list(world):
    """Stays: $400 at the day."""
    world.blank_fee()
    world.nothing_stored_yet()
    assert world.coins_list().status_code == 200
    r = world.income()
    assert r.status_code == 200, r.text
    assert world.basis(r.json()["id"]) == (Decimal("400.00"), "day")


def _year_end_values(world) -> set:
    year = datetime.fromtimestamp(world.files_end, tz=timezone.utc).year
    with world.session() as db:
        held = generate_report_data(db, year)["end_of_year_balances"]
    return {Decimal(str(row["value"])) for row in held if row.get("account") and row.get("value") is not None}


def test_a_reports_year_end_value_after_a_question(world):
    """Stays: 1 BTC at $40,000, the day's price, noted as having no hourly price."""
    world.blank_fee()
    world.nothing_stored_yet()
    world.a_question()
    assert _year_end_values(world) == {Decimal("40000.0")}


def test_an_income_after_a_report_with_no_blank_row(world):
    """Stays: a report's year-end value isn't a stored row's missing value,
    so what its copy found isn't given to anything: $400 at the day."""
    world.nothing_stored_yet()
    _year_end_values(world)
    r = world.income()
    assert r.status_code == 200, r.text
    assert world.basis(r.json()["id"]) == (Decimal("400.00"), "day")


def test_a_save_after_a_report(world):
    """Stays: this report's replay ends with 2025, before the blank row, so
    it priced no stored value; its year-end lookup asked. $4.00 at the day."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    _year_end_values(world)
    assert world.save_this_year(blank).status_code == 200
    assert world.fee(blank) == (Decimal("4.00"), "day")


def test_a_save_after_ledger_review(world):
    """Ledger Review's check replays on a scratch copy too. Before: $4.00 at the day."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    assert world.client.get("/api/review").status_code == 200
    assert world.save_this_year(blank).status_code == 200
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_the_ais_preview_of_another_row_after_a_question(world):
    """Stays: $400 at the day."""
    world.blank_fee()
    ai = ai_client(world)
    world.nothing_stored_yet()
    world.a_question()
    r = ai.post("/api/import/entries/preview", json={"rows": [{
        "date": world.after_the_files(3), "type": "Deposit", "amount": "0.01", "from_account": "External",
        "to_account": "Wallet", "source": "Income", "fee_amount": "0", "fee_currency": "BTC"}]})
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["results"][0]["normalized"]["cost_basis_usd"]) == Decimal("400.00")


def test_an_edit_pricing_a_day_priced_row_again_after_a_question(world):
    """Stays for the edited row (its own value, not a stored one missing):
    $8.00 at the day. The blank row its replay prices takes the hour.
    Before: the blank row $4.00 at the day."""
    blank = world.blank_fee()
    day_priced = world.post(type="Transfer", timestamp=world.after_the_files(4), from_account_id=EXCHANGE_BTC,
                            to_account_id=WALLET, amount="0.1", fee_amount="0.0001", fee_currency="BTC")
    world.store(day_priced, price_moment="day")
    world.nothing_stored_yet()
    world.a_question()
    assert world.save_this_year(day_priced, fee_amount="0.0002").status_code == 200
    assert world.fee(day_priced) == (Decimal("8.00"), "day")
    assert world.fee(blank) == (Decimal("4.10"), "hour")


def test_ledger_review_after_a_question(world):
    """Stays: Ledger Review's hour check lists no hour change for a value
    priced at the day, the hour having none in those 10 minutes."""
    world.blank_fee()
    day_priced = world.post(type="Transfer", timestamp=world.after_the_files(4), from_account_id=EXCHANGE_BTC,
                            to_account_id=WALLET, amount="0.1", fee_amount="0.0001", fee_currency="BTC")
    world.nothing_stored_yet()
    world.store(day_priced, price_moment="day", fee_usd=Decimal("4.00"))
    world.a_question()
    applied = world.client.post("/api/review/hourly-prices", json={"ids": [day_priced]})
    assert applied.status_code == 200, applied.text
    assert applied.json()["changed"] == []
    assert world.fee(day_priced) == (Decimal("4.00"), "day")


def test_login_recalculate_after_a_question(world):
    """Before: $4.00 at the day."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    world.a_question()
    assert world.client.post("/api/transactions/recalculate").status_code == 200
    assert world.fee(blank) == (Decimal("4.10"), "hour")


# A question that goes away, and refusals that become saves (B4, B5, B8); D stays

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


def test_the_days_ask_is_used_up_as_before(world):
    """Stays: the replay without the write still looks for the day's price
    it looked for before, though the hour is given it, so the day's one ask
    for the latest days goes as it did, and an Inherited deposit (priced at
    the date of death's day) is refused as before: #905."""
    world.blank_fee()
    world.nothing_stored_yet(history_complete=True)
    world.a_question()
    r = world.client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": world.after_the_files(30), "from_account_id": EXTERNAL,
        "to_account_id": WALLET, "amount": "0.01", "fee_amount": "0", "fee_currency": "BTC", "source": "Inherited",
        "acquired_at": world.after_the_files(30)[:10]})
    assert r.status_code == 422, r.text


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


# Stays: what follows the blank row's save. The day's prices are looked for
# as before, and the hour given isn't kept, so later rows find what they did

def _confirmed(world) -> None:
    """The blank row's past-year question, confirmed until it saves (twice before the fix)."""
    world.blank_fee()
    world.nothing_stored_yet()
    assert world.question_then_confirm()[-1] == 200


def test_prices_switched_off_after_a_confirmed_question(world):
    """Stays: an income after it saves at $400, the day's price that save stored as before."""
    _confirmed(world)
    world.source(price_source="off")
    r = world.income()
    assert world.basis(r.json()["id"]) == (Decimal("400.00"), "day")


def test_your_mempool_alone_after_a_confirmed_question(world, monkeypatch):
    """Your Mempool lacks the income's hour, and its midnight price is
    $40,100. Stays: $400, Bitstamp's day that save stored as before."""
    _confirmed(world)
    world.sites.mempool_lacks = {hp.hour_of(datetime.strptime(world.after_the_files(3), TIME))}
    mempool = world.sites.handler

    def its_own_midnight(request):
        answer = mempool(request)
        if request.url.path != price_history.MEMPOOL_HISTORY_PATH:
            return answer
        rows = [{**row, "USD": "40100"} if row["time"] % DAY == 0 else row for row in answer.json()["prices"]]
        return httpx.Response(200, json={"prices": rows})

    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(its_own_midnight))
    world.source(**MEMPOOL_ALONE)
    r = world.income()
    assert world.basis(r.json()["id"]) == (Decimal("400.00"), "day")


def test_a_days_price_read_with_the_sites_down_after_a_confirmed_question(world):
    """The form's and the AI's price for a date. Stays: $40,000, stored by that save as before."""
    _confirmed(world)
    ten_minutes_later()
    world.sites.down = {"bitstamp"}
    r = world.client.get("/api/bitcoin/price/history", params={"date": world.after_the_files(4)[:10]})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("look", ["question", "coins list"])
def test_the_price_read_for_a_moment_after_a_look(world, look):
    """The form's and the AI's price for a moment (`get_btc_price`). Stays: $40,000 at the day."""
    world.blank_fee()
    world.nothing_stored_yet()
    if look == "question":
        world.a_question()
    else:
        assert world.coins_list().status_code == 200
    r = world.client.get("/api/bitcoin/price/history", params={"at": world.after_the_files(4)})
    assert r.status_code == 200, r.text
    assert (Decimal(str(r.json()["USD"])), r.json()["moment"]) == (Decimal("40000"), "day")


def test_a_lookup_that_couldnt_keep_its_hours_for_a_busy_database(world, monkeypatch):
    """Stays: the hours found but not kept, the database being busy, aren't
    given to the next save, whose 10 minutes' ask is gone: $400, the day's."""
    world.nothing_stored_yet()
    store = hp._store
    busy = {"once": True}

    def busy_once(db, prices):
        if busy.pop("once", False) and prices:
            raise OperationalError("INSERT", {}, Exception("database is locked"))
        return store(db, prices)

    monkeypatch.setattr(hp, "_store", busy_once)
    assert world.income().status_code == 503
    r = world.income(hours=5)
    assert world.basis(r.json()["id"]) == (Decimal("400.00"), "day")


def test_a_report_then_a_save_in_the_window_then_the_sites_down(world):
    """Stays: the report's year-end value, read again later with Bitstamp
    down, is $40,000, the day the income's save stored."""
    world.nothing_stored_yet()
    _year_end_values(world)
    assert world.income().status_code == 200
    ten_minutes_later()
    world.sites.down = {"bitstamp"}
    assert _year_end_values(world) == {Decimal("40000.0")}


@pytest.mark.parametrize("later, basis", [
    (MEMPOOL_ALONE, (Decimal("405.00"), "hour")),  # your Mempool's
    (dict(price_source="off"), (Decimal("400.00"), "day")),
])
def test_a_later_row_in_the_blank_rows_hour(world, later, basis):
    """Stays: the hour given the blank row isn't kept in the ledger, so a
    later row in that hour, 10 minutes or more on, takes what it took."""
    _confirmed(world)
    ten_minutes_later()
    world.source(**later)
    r = world.income(hours=2)  # the blank row's hour
    assert world.basis(r.json()["id"]) == basis


def test_a_later_row_in_the_hour_a_price_read_looked_up(world):
    """Stays: $405, your Mempool's."""
    world.blank_fee()
    world.nothing_stored_yet()
    world.a_question()
    assert world.client.get("/api/bitcoin/price/history", params={"at": world.after_the_files(4)}).status_code == 200
    ten_minutes_later()
    world.source(**MEMPOOL_ALONE)
    r = world.income(hours=4)
    assert world.basis(r.json()["id"]) == (Decimal("405.00"), "hour")


def test_a_save_after_the_hours_went_with_a_restore(world):
    """A restore puts back a ledger without the hours a save kept a moment
    ago (deleted here as the restore leaves them). Stays: $400, the day's."""
    world.nothing_stored_yet()
    assert world.income(hours=5).status_code == 200
    with world.session() as db:
        db.query(BtcPriceHourly).delete()
        db.query(BtcPriceDaily).delete()
        db.commit()
    r = world.income(hours=6)
    assert world.basis(r.json()["id"]) == (Decimal("400.00"), "day")


# Stays: the write's own values. A new row, or the values an edit sets or
# clears, aren't a stored row's missing value (transaction.OWN_VALUES)

def _a_new_spend(world, hours: int = 2, **more):
    """A Spent of 0.05 BTC sent with no proceeds, in the blank row's hour by default."""
    return world.client.post("/api/transactions", json={
        "type": "Withdrawal", "timestamp": world.after_the_files(hours), "from_account_id": EXCHANGE_BTC,
        "to_account_id": EXTERNAL, "amount": "0.05", "purpose": "Spent", "fee_amount": "0",
        "fee_currency": "BTC", **more})


def _look(world, how: str) -> None:
    if how == "question":
        world.a_question()
    elif how == "review":
        assert world.client.get("/api/review").status_code == 200
    else:
        assert world.coins_list().status_code == 200


def _proceeds(world, tx_id: int) -> tuple:
    saved = world.get(tx_id)
    return Decimal(saved["gross_proceeds_usd"]), saved["price_moment"]


@pytest.mark.parametrize("how", ["question", "review", "coins list"])
def test_a_new_spend_with_no_proceeds_after_a_look(world, how):
    """Stays: $2,000 at the day (#824's third review: it took the copy's hour)."""
    world.blank_fee()
    world.nothing_stored_yet()
    _look(world, how)
    r = _a_new_spend(world)
    assert r.status_code == 200, r.text
    assert _proceeds(world, r.json()["id"]) == (Decimal("2000.00"), "day")


def test_a_new_spend_with_no_proceeds_after_a_question_with_the_history_complete(world):
    """Stays: refused, no price."""
    world.blank_fee()
    world.nothing_stored_yet(history_complete=True)
    world.a_question()
    assert _a_new_spend(world).status_code == 422


def test_an_edit_clearing_a_spends_typed_proceeds_after_a_question(world):
    """Stays: $2,000 at the day."""
    world.blank_fee()
    spend = _a_new_spend(world, gross_proceeds_usd="1234").json()["id"]
    world.nothing_stored_yet()
    world.a_question()
    r = world.save_this_year(spend, proceeds_usd=None, gross_proceeds_usd=None)
    assert r.status_code == 200, r.text
    assert _proceeds(world, spend) == (Decimal("2000.00"), "day")


def test_a_gift_edited_into_a_spend_after_a_question(world):
    """Stays: $2,000 at the day."""
    world.blank_fee()
    gift = _a_new_spend(world, purpose="Gift", fmv_usd="1")
    assert gift.status_code == 200, gift.text
    world.nothing_stored_yet()
    world.a_question()
    assert world.save_this_year(gift.json()["id"], purpose="Spent").status_code == 200
    assert _proceeds(world, gift.json()["id"]) == (Decimal("2000.00"), "day")


def test_a_restore_after_a_copy_found_the_blank_rows_hour_stored(world):
    """A save asked and kept the hours; the question's copy found the blank
    row's hour stored; a restore then put back a ledger without them
    (deleted here). Stays: Recalculate prices the blank fee at $4.00, the
    day's: a copy remembers only an hour its own lookup asked for."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    assert world.income(hours=5).status_code == 200
    world.a_question()
    with world.session() as db:
        db.query(BtcPriceHourly).delete()
        db.commit()
    assert world.client.post("/api/transactions/recalculate").status_code == 200
    assert world.fee(blank) == (Decimal("4.00"), "day")


# Refused today for the blank row's price, worked out with the fix

def test_ledger_review_after_a_question_with_the_history_complete(world):
    """Before: its check of Recalculate Ledger stopped, "its network fee has
    no USD value". It lists the blank row's change at the hour's price."""
    blank = world.blank_fee()
    world.nothing_stored_yet(history_complete=True)
    world.a_question()
    review = world.client.get("/api/review").json()
    assert review["recalc_error"] is None
    listed = [item for check in review["checks"] for item in check.get("items", []) if item.get("id") == blank]
    assert any("9.89 -> 4.00" in str(item.get("change")) for item in listed), listed


def test_the_report_after_a_question_with_the_history_complete(world):
    """The blank row's year. Before: 422, "its network fee has no USD value"."""
    world.blank_fee()
    world.nothing_stored_yet(history_complete=True)
    world.a_question()
    with world.session() as db:
        assert generate_report_data(db, datetime.fromtimestamp(world.files_end + 2 * HOUR, tz=timezone.utc).year)


def test_the_ais_preview_of_a_past_year_row_after_a_question_with_the_history_complete(world):
    """Before: rejected, the blank row's fee having no USD value."""
    world.blank_fee()
    ai = ai_client(world)
    world.nothing_stored_yet(history_complete=True)
    world.a_question()
    world.tax_year(2100)
    r = ai.post("/api/import/entries/preview", json={"rows": [{
        "date": "2019-02-01T10:00:00Z", "type": "Buy", "amount": "0.2", "from_account": "Bank",
        "to_account": "Exchange BTC", "cost_basis_usd": "200.00", "fee_amount": "0", "fee_currency": "USD"}]})
    world.tax_year(2009)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


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
    """C4. The blank row's hour comes from the fallback. Before: $4.00 at
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
    """Stays."""
    blank = world.blank_fee()
    world.nothing_stored_yet()
    assert world.edit_the_buy(year=2009).status_code == 200
    assert world.fee(blank) == (Decimal("4.10"), "hour")
    assert world.sites.bitstamp_asked() == 1


def test_an_add_dated_last_leaves_the_blank_row_alone(world):
    """Stays."""
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
    """Stays: its own dry run keeps the hours it asks for."""
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
    """Stays."""
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
