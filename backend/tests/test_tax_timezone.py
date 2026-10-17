"""
backend/tests/test_tax_timezone.py

Tax dates follow the user's timezone, not UTC: tax-year membership, the dates
printed on Form 8949, holding-period anniversaries, and AI-entered dates
without a timezone.
"""

import zoneinfo
from datetime import datetime, timezone
from importlib import resources
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models.app_setting import AppSetting
from backend.routers.settings import RELOAD_TO_CHOOSE
from backend.services.reports.form_8949 import build_form_8949_and_schedule_d
from backend.services.tax_time import (
    MAX_ZONE_NAME, SETTING_KEY, bundled_zones, fill_tax_timezone, tax_year_bounds, validate_timezone,
)
from backend.services.transaction import holding_period

CLIENT = None
ENGINE = None
BANK, EXCHANGE_USD, EXCHANGE_BTC = 1, 3, 4
NY = "America/New_York"


@pytest.fixture(autouse=True, scope="module")
def _setup(auth_client, test_engine):
    global CLIENT, ENGINE
    CLIENT, ENGINE = auth_client, test_engine
    yield
    CLIENT.put("/api/settings/tax-timezone", json={"timezone": "UTC", "chosen": True})


@pytest.fixture(autouse=True)
def _clean():
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")
    CLIENT.put("/api/settings/tax-timezone", json={"timezone": "UTC", "chosen": True})
    yield
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")


def set_tz(name):
    r = CLIENT.put("/api/settings/tax-timezone", json={"timezone": name, "chosen": True})
    assert r.status_code == 200, r.text


def buy(ts):
    r = CLIENT.post("/api/transactions", json={
        "type": "Buy", "timestamp": ts, "from_account_id": BANK, "to_account_id": EXCHANGE_BTC,
        "amount": "1.0", "cost_basis_usd": "20000"})
    assert r.status_code == 200, r.text


def sell(ts):
    r = CLIENT.post("/api/transactions", json={
        "type": "Sell", "timestamp": ts, "from_account_id": EXCHANGE_BTC,
        "to_account_id": EXCHANGE_USD, "amount": "0.1", "gross_proceeds_usd": "5000.00"})
    assert r.status_code == 200, r.text
    return r.json()


def report(year):
    db = sessionmaker(bind=ENGINE)()
    try:
        return build_form_8949_and_schedule_d(year, db)
    finally:
        db.close()


def rows(year):
    data = report(year)
    return data["short_term"] + data["long_term"]


# A folder of zones in the tz database, a name too long for a file name,
# one of hundreds of parts (ZoneInfo ran out of recursion on it), and one
# with a part naming a module of tzdata (a TypeError on Python 3.10, 3.11)
NOT_A_ZONE = ["America", "A" * 5000, "a/" * 300 + "b", "America/__init__/x"]
NOT_A_ZONE_IDS = ["a folder", "too long", "many parts", "a module"]
# Names a machine's own zone files open and tzdata doesn't hold (#407):
# links in a Linux system's zone files (`localtime` in the Docker image),
# case variants (macOS's disk ignores case) and a module of tzdata (opens on
# Python 3.12 and later). Stored on one machine, they failed every report
# after a restore on another.
NOT_TZDATA = ["localtime", "posixrules", "america/chicago", "AMERICA/CHICAGO", "utc", "__init__/UTC"]


def test_every_zone_fits_the_name_limit():
    """A tzdata update with a longer name would be refused as unknown."""
    zones = bundled_zones()
    assert max(map(len, zones)) <= MAX_ZONE_NAME
    assert all(validate_timezone(zone) == zone for zone in zones)


def test_the_names_are_tzdatas_own_on_every_machine():
    """#407: the list is the package's, not the machine's zone files (which
    on Linux add `localtime`); it keeps old names and Factory."""
    listed = resources.files("tzdata").joinpath("zones").read_text(encoding="utf-8").split()
    assert bundled_zones() == frozenset(listed)
    assert {"UTC", "America/Chicago", "Asia/Calcutta", "Factory"} <= bundled_zones()
    assert not {"localtime", "posixrules"} & bundled_zones()


class TestSetting:
    def test_get_and_put(self):
        assert CLIENT.get("/api/settings/tax-timezone").json()["timezone"] == "UTC"
        set_tz(NY)
        assert CLIENT.get("/api/settings/tax-timezone").json() == {"timezone": NY, "source": "setting"}

    def test_invalid_timezone_rejected(self):
        r = CLIENT.put("/api/settings/tax-timezone", json={"timezone": "Mars/Olympus", "chosen": True})
        assert r.status_code == 400

    @pytest.mark.parametrize("name", NOT_A_ZONE + NOT_TZDATA, ids=NOT_A_ZONE_IDS + NOT_TZDATA)
    def test_a_folder_of_zones_or_a_name_too_long_is_unknown_too(self, name):
        """#384: ZoneInfo fails on these with an OS error, which was a 500.
        #407: a name tzdata doesn't hold, which some machines open, too."""
        r = CLIENT.put("/api/settings/tax-timezone", json={"timezone": name, "chosen": True})
        assert r.status_code == 400 and r.json()["detail"].startswith("Unknown timezone"), r.text[:200]
        assert len(r.json()["detail"]) < 150  # the name cut short, not all of it
        assert CLIENT.get("/api/settings/tax-timezone").json()["timezone"] == "UTC"

    def test_requires_login(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        assert TestClient(app).get("/api/settings/tax-timezone").status_code == 401


def never_chosen():
    """No tax timezone ever chosen: the install's state before any login set one."""
    db = sessionmaker(bind=ENGINE)()
    try:
        db.query(AppSetting).filter_by(key=SETTING_KEY).delete()
        db.commit()
    finally:
        db.close()


def fill(name):
    r = CLIENT.post("/api/settings/tax-timezone/fill", json={"timezone": name})
    assert r.status_code == 200, r.text
    return r.json()


class TestLoginFill:
    """The login page's fill (#334): only while none was ever chosen and the
    ledger is empty. With transactions, another timezone would recalculate
    tax years already reported, so only Settings' own change does that."""

    @pytest.fixture(autouse=True)
    def _no_env(self, monkeypatch):
        monkeypatch.delenv("BTCTX_TIMEZONE", raising=False)

    def test_an_empty_ledger_takes_the_browsers_timezone(self):
        never_chosen()
        assert fill(NY) == {"timezone": NY, "source": "setting", "filled": True}
        assert CLIENT.get("/api/settings/tax-timezone").json() == {"timezone": NY, "source": "setting"}

    def test_a_ledger_with_transactions_keeps_utc(self):
        """Before #334 the login saved the browser's timezone here and recalculated:
        a sale near midnight or its anniversary could change tax year or term."""
        buy("2024-06-01T12:00:00Z")
        sell("2025-01-01T03:00:00Z")          # Dec 31 2024, 10 pm in New York
        never_chosen()
        assert fill(NY) == {"timezone": "UTC", "source": "default", "filled": False}
        assert len(rows(2025)) == 1 and not rows(2024)   # still UTC's tax year

    def test_never_over_a_chosen_timezone(self):
        set_tz("Asia/Tokyo")
        assert fill(NY) == {"timezone": "Asia/Tokyo", "source": "setting", "filled": False}

    def test_never_over_btctx_timezone(self, monkeypatch):
        monkeypatch.setenv("BTCTX_TIMEZONE", "Asia/Tokyo")
        never_chosen()
        assert fill(NY) == {"timezone": "Asia/Tokyo", "source": "env", "filled": False}

    @pytest.mark.parametrize("name", ["Mars/Olympus", *NOT_A_ZONE, *NOT_TZDATA],
                             ids=["unknown", *NOT_A_ZONE_IDS, *NOT_TZDATA])
    def test_unknown_timezone_refused(self, name):
        never_chosen()
        r = CLIENT.post("/api/settings/tax-timezone/fill", json={"timezone": name})
        assert r.status_code == 400 and r.json()["detail"].startswith("Unknown timezone"), r.text[:200]
        assert CLIENT.get("/api/settings/tax-timezone").json()["source"] == "default"

    def test_a_fill_after_delete_all_takes_the_browsers_timezone(self):
        buy("2024-06-01T12:00:00Z")
        CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")
        never_chosen()
        assert fill(NY)["filled"] is True

    def test_a_database_busy_past_the_wait_fills_nothing(self):
        """The check and the save hold the write lock. While another save
        holds it past the wait (5 s in the app; 0.1 s here), the login fills
        nothing, and the next login tries again."""
        never_chosen()
        holder = ENGINE.raw_connection()
        quick = create_engine(ENGINE.url, connect_args={"timeout": 0.1})
        db = sessionmaker(bind=quick)()
        try:
            holder.cursor().execute("BEGIN IMMEDIATE")
            assert fill_tax_timezone(db, NY) is False
        finally:
            db.close()
            quick.dispose()
            holder.rollback()
            holder.close()
        assert CLIENT.get("/api/settings/tax-timezone").json()["source"] == "default"


def store(name):
    """A name saved before #407, or brought by a restore, as it is."""
    with ENGINE.begin() as conn:
        conn.exec_driver_sql("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (SETTING_KEY, name))


@pytest.fixture
def own_zone_file(tmp_path):
    """A zone file only this machine holds, as `localtime` is in the Docker
    image: "localzone", Chicago's rules, which ZoneInfo opens while the
    fixture lasts."""
    (tmp_path / "localzone").write_bytes(
        resources.files("tzdata").joinpath("zoneinfo", "America", "Chicago").read_bytes())
    zoneinfo.reset_tzpath([str(tmp_path)])
    ZoneInfo.clear_cache()
    yield "localzone"
    zoneinfo.reset_tzpath()
    ZoneInfo.clear_cache()


class TestAStoredNameTzdataDoesntHold:
    """#407: an install that saved such a name before 1.2.9, or got one from
    a restore, keeps working: the figures it showed stay, and where it had
    none (every report a 500), the reports answer."""

    @pytest.fixture(autouse=True)
    def _no_env(self, monkeypatch):
        monkeypatch.delenv("BTCTX_TIMEZONE", raising=False)

    def test_a_case_variant_is_read_as_tzdatas_name(self):
        """The zone the Mac opened, also on a machine whose disk minds case."""
        buy("2024-06-01T12:00:00Z")
        sell("2025-01-01T03:00:00Z")          # Dec 31 2024, 10 pm in New York
        store("america/new_york")
        assert CLIENT.get("/api/settings/tax-timezone").json() == {"timezone": NY, "source": "setting"}
        assert len(rows(2024)) == 1 and not rows(2025)

    def test_a_name_this_machine_opens_is_read_as_it_was(self, own_zone_file):
        buy("2024-06-01T12:00:00Z")
        sell("2025-01-01T03:00:00Z")          # Dec 31 2024, 9 pm in Chicago
        store(own_zone_file)
        assert CLIENT.get("/api/settings/tax-timezone").json() == {"timezone": own_zone_file, "source": "setting"}
        assert len(rows(2024)) == 1 and not rows(2025)
        r = CLIENT.put("/api/settings/tax-timezone", json={"timezone": own_zone_file, "chosen": True})
        assert r.status_code == 400  # but never saved again

    def test_a_name_this_machine_cant_open_counts_as_none(self):
        """Stored on another machine (the restore of #407): the reports were
        a 500 every time. Settings then suggests choosing one (#334)."""
        buy("2024-06-01T12:00:00Z")
        sell("2025-01-01T03:00:00Z")
        store("localzone")
        assert CLIENT.get("/api/settings/tax-timezone").json() == {"timezone": "UTC", "source": "default"}
        assert CLIENT.get("/api/reports/irs_reports", params={"year": 2025}).status_code == 200
        assert CLIENT.get("/api/calculations/gains-and-losses").status_code == 200
        assert len(rows(2025)) == 1

    def test_btctx_timezone_is_read_the_same_way(self, monkeypatch):
        never_chosen()
        monkeypatch.setenv("BTCTX_TIMEZONE", "asia/tokyo")
        assert CLIENT.get("/api/settings/tax-timezone").json() == {"timezone": "Asia/Tokyo", "source": "env"}


class TestOldPage:
    """A page from before #334, still open after the update, set the
    timezone at its login with the plain PUT. While none was chosen and the
    ledger has transactions, the PUT now needs `chosen` (Settings' Save)."""

    @pytest.fixture(autouse=True)
    def _no_env(self, monkeypatch):
        monkeypatch.delenv("BTCTX_TIMEZONE", raising=False)

    def test_an_old_pages_login_cant_set_it(self):
        buy("2024-06-01T12:00:00Z")
        sell("2025-01-01T03:00:00Z")          # Dec 31 2024, 10 pm in New York
        never_chosen()
        r = CLIENT.put("/api/settings/tax-timezone", json={"timezone": NY})
        assert (r.status_code, r.json()["detail"]) == (409, RELOAD_TO_CHOOSE)
        assert CLIENT.get("/api/settings/tax-timezone").json() == {"timezone": "UTC", "source": "default"}
        assert len(rows(2025)) == 1 and not rows(2024)   # the sale stays in UTC's tax year

    def test_settings_save_sets_it(self):
        buy("2024-06-01T12:00:00Z")
        never_chosen()
        r = CLIENT.put("/api/settings/tax-timezone", json={"timezone": NY, "chosen": True})
        assert r.status_code == 200, r.text
        assert CLIENT.get("/api/settings/tax-timezone").json() == {"timezone": NY, "source": "setting"}

    def test_an_empty_ledger_or_a_chosen_timezone_needs_nothing(self):
        never_chosen()
        assert CLIENT.put("/api/settings/tax-timezone", json={"timezone": NY}).status_code == 200
        buy("2024-06-01T12:00:00Z")
        assert CLIENT.put("/api/settings/tax-timezone", json={"timezone": "UTC"}).status_code == 200


class TestTaxYear:
    def test_new_years_eve_sale_belongs_to_local_year(self):
        buy("2024-06-01T12:00:00Z")
        sell("2025-01-01T03:00:00Z")          # Dec 31 2024, 10 pm in New York
        assert len(rows(2025)) == 1 and not rows(2024)   # UTC: 2025
        set_tz(NY)
        assert len(rows(2024)) == 1 and not rows(2025)   # New York: 2024
        assert rows(2024)[0]["date_sold"] == "12/31/2024"

    def test_a_sale_half_a_second_into_the_year_is_in_that_year(self):
        """Bug hunt 2026-09-29: timestamps are stored and compared as text,
        and '2025-01-01T00:00:00.500000Z' sorts before '2025-01-01T00:00:00Z'
        ('.' before 'Z'): a sale half a second after midnight (a time from
        the API or the AI connector) was put in the year before. Fractions
        of a second are no longer stored, on create or on edit."""
        buy("2024-06-01T12:00:00Z")
        created = sell("2025-01-01T00:00:00.500Z")
        edited = sell("2025-03-01T12:00:00Z")
        r = CLIENT.put(f"/api/transactions/{edited['id']}", json={"timestamp": "2025-01-01T00:00:00.250Z"})
        assert r.status_code == 200, r.text
        assert len(rows(2025)) == 2 and not rows(2024)
        assert {created["timestamp"], r.json()["timestamp"]} == {"2025-01-01T00:00:00Z"}

    def test_bounds_are_local_midnights(self):
        start, end = tax_year_bounds(2025, ZoneInfo(NY))
        assert start == datetime(2025, 1, 1, 5, tzinfo=timezone.utc)
        assert end == datetime(2026, 1, 1, 5, tzinfo=timezone.utc)

    def test_complete_tax_report_includes_last_second_of_year(self):
        buy("2024-06-01T12:00:00Z")
        sell("2025-12-31T23:59:59Z")
        r = CLIENT.get("/api/reports/complete_tax_report", params={"year": 2025})
        assert r.status_code == 200 and r.content[:4] == b"%PDF"
        assert rows(2025)


class TestHoldingPeriod:
    def test_anniversary_is_decided_on_local_dates(self):
        acquired = datetime(2024, 1, 1, 12, tzinfo=timezone.utc)
        disposed = datetime(2025, 1, 2, 3, tzinfo=timezone.utc)   # Jan 1, 10 pm in New York
        assert holding_period(acquired, disposed) == "LONG"                 # UTC: Jan 2
        assert holding_period(acquired, disposed, ZoneInfo(NY)) == "SHORT"  # NY: anniversary

    def test_changing_timezone_recalculates_stored_holding_period(self):
        buy("2024-01-01T12:00:00Z")
        tx = sell("2025-01-02T03:00:00Z")
        assert CLIENT.get(f"/api/transactions/{tx['id']}").json()["holding_period"] == "LONG"
        set_tz(NY)
        assert CLIENT.get(f"/api/transactions/{tx['id']}").json()["holding_period"] == "SHORT"


class TestEntryImportDates:
    def test_bare_date_is_local_noon(self):
        set_tz(NY)
        r = CLIENT.post("/api/import/entries/preview", json={"rows": [{
            "date": "2025-03-05", "type": "Buy", "amount": "0.1", "from_account": "Bank",
            "to_account": "Exchange BTC", "cost_basis_usd": "5000"}]})
        assert r.json()["results"][0]["normalized"]["date"] == "2025-03-05T17:00:00Z"  # noon EST

    def test_local_time_without_offset_uses_tax_timezone(self):
        set_tz(NY)
        r = CLIENT.post("/api/import/entries/preview", json={"rows": [{
            "date": "2025-12-31T22:00:00", "type": "Buy", "amount": "0.1", "from_account": "Bank",
            "to_account": "Exchange BTC", "cost_basis_usd": "5000"}]})
        assert r.json()["results"][0]["normalized"]["date"] == "2026-01-01T03:00:00Z"

    def test_explicit_offset_wins(self):
        set_tz(NY)
        r = CLIENT.post("/api/import/entries/preview", json={"rows": [{
            "date": "2025-03-05T10:00:00Z", "type": "Buy", "amount": "0.1", "from_account": "Bank",
            "to_account": "Exchange BTC", "cost_basis_usd": "5000"}]})
        assert r.json()["results"][0]["normalized"]["date"] == "2025-03-05T10:00:00Z"

    def test_a_utc_suffix_is_honoured(self):
        """Bug hunt 2026-09-29: "... UTC" was read as a tax-timezone time (the
        CSV import reads it as UTC): 03:00 UTC on Jan 1, 10 pm Dec 31 in New
        York, was saved as 08:00 UTC, in the next tax year there."""
        set_tz(NY)
        r = CLIENT.post("/api/import/entries/preview", json={"rows": [{
            "date": "2025-01-01 03:00:00 UTC", "type": "Buy", "amount": "0.1", "from_account": "Bank",
            "to_account": "Exchange BTC", "cost_basis_usd": "5000"}]})
        assert r.json()["results"][0]["normalized"]["date"] == "2025-01-01T03:00:00Z"
