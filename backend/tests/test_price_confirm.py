"""
Confirm once, after the update (#145, plan 2.9, the owner's addition): a
stored price choice with no record of when it was made in the price card
is asked once, with the current choice pre-selected, and nothing is asked
of anyone until the owner confirms it. That covers installs where the #134
bug saved "public" by itself (it looks like an owner's own choice) and
#155's narrow gap. The record (price_choice_at, price_choice_via) is
written only by the card's save (PUT /api/settings/network, a login), never
by the app's start, a command, the AI key or a pre-1.1.0 upgrade. One test
per case of the plan's section 5.
"""

import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from backend.services import bitcoin, hourly_prices, outbound, price_history
from backend.tests.conftest import default_login

# The real functions, captured before the session fixture stubs them.
from backend.services.bitcoin import get_current_price as real_current_price
from backend.services.hourly_prices import find_hours as real_find_hours
from backend.services.hourly_prices import download_if_public as real_download_if_public
from backend.services.hourly_prices import start_download as real_start_download
from backend.services.price_history import find_prices as real_find_prices

NODE = "http://umbrel.local:3006"
ONION = "http://mempoolabcdefghijklmnopqrstuvwxyz234567abcdefghijklmnop.onion"
TOR = "socks5h://127.0.0.1:9050"
SETTING_KEYS = ("price_source", "mempool_url", "mempool_fallback", "proxy_url", "live_data",
                "price_choice_at", "price_choice_via")


@pytest.fixture
def outside(monkeypatch):
    """Every outside request, answered as the sites and a mempool server would."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path.endswith("/api/v1/prices"):
            return httpx.Response(200, json={"time": 1, "USD": 61234})
        if request.url.host == "api.kraken.com":
            return httpx.Response(200, json={"error": [], "result": {"XXBTZUSD": {"c": ["61000.5", "1"]}}})
        return httpx.Response(503)

    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(price_history, "find_prices", real_find_prices)
    monkeypatch.setattr(bitcoin, "get_current_price", real_current_price)
    # The hourly lookups and the history download as they really are (review of #181)
    monkeypatch.setattr(hourly_prices, "find_hours", real_find_hours)
    monkeypatch.setattr(hourly_prices, "start_download", real_start_download)
    # ...but confirming Public doesn't start the download here, so no background
    # thread outlives a test (re-check of #181); asks_nothing calls the real one
    monkeypatch.setattr(hourly_prices, "download_if_public", lambda: None)
    bitcoin._price_cache.update(settings=None)
    yield seen
    outbound._current = outbound.NetworkSettings()


def stored(test_engine, **settings):
    """The app's database as an older release left it: these settings, no record."""
    with test_engine.begin() as conn:
        for key in SETTING_KEYS:
            conn.execute(text("DELETE FROM app_settings WHERE key = :k"), {"k": key})
        for key, value in settings.items():
            conn.execute(text("INSERT INTO app_settings (key, value) VALUES (:k, :v)"), {"k": key, "v": value})


def start(test_engine) -> outbound.NetworkSettings:
    """The app's start: the settings read as main.py reads them."""
    bitcoin._price_cache.update(settings=None)
    with sessionmaker(bind=test_engine)() as db:
        return outbound.load(db)


def record(test_engine) -> dict:
    with test_engine.connect() as conn:
        rows = conn.execute(text("SELECT key, value FROM app_settings WHERE key LIKE 'price_choice_%'"))
        return dict(rows.all())


def asks_nothing(auth_client, outside):
    """While waiting: the live price, the block height, a newer day, a newer
    and an older hour, the history download and the status all ask nobody."""
    for path in ("/api/bitcoin/price", "/api/bitcoin/blockheight"):
        r = auth_client.get(path)
        assert r.status_code == 503 and r.json()["detail"].startswith("Confirm where BitcoinTX gets newer prices")
    for params in ({"date": "2026-01-05"}, {"at": "2026-01-05T14:20:00Z"}, {"at": "2014-03-01T09:00:00Z"}):
        r = auth_client.get("/api/bitcoin/price/history", params=params)
        assert r.status_code == 422 and "Confirm where BitcoinTX gets newer prices" in r.json()["detail"], params
    assert not hourly_prices.start_download()
    real_download_if_public()
    status = auth_client.get("/api/bitcoin/price/status").json()
    assert status["waiting"] is True and status["history"]["state"] == "not_allowed"
    assert outside == []



def asked_until_confirmed(auth_client, test_engine, outside):
    """Asked again at each restart until confirmed (the plan's section 5)."""
    for _ in range(2):
        assert start(test_engine).waiting
        assert auth_client.get("/api/settings/network").json()["confirmed"] is False
        asks_nothing(auth_client, outside)


def live_price():
    try:
        return asyncio.run(real_current_price())
    except HTTPException as exc:
        return exc.status_code


def confirm(auth_client, via="first-run", **choice):
    body = {"mempool_url": None, "mempool_fallback": False, "proxy_url": None, "via": via, **choice}
    r = auth_client.put("/api/settings/network", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_1_public_saved_by_the_134_bug_is_asked_with_public_preselected(auth_client, test_engine, outside):
    """The #134 state: the server set the source, prices were stored, then the
    old code saved Public by itself on a switch to Decide in BitcoinTX instead."""
    stored(test_engine, price_source="public")
    for _ in range(2):  # asked again after a restart, until confirmed
        s = start(test_engine)
        assert s.waiting and not s.public_allowed and s.own_node is None
        shown = auth_client.get("/api/settings/network").json()
        assert shown["price_source"] == "public" and shown["confirmed"] is False  # pre-selected
        asks_nothing(auth_client, outside)


def test_2_your_own_public_choice_is_asked_once_then_never_again(auth_client, test_engine, outside):
    stored(test_engine, price_source="public", mempool_fallback="off")
    asked_until_confirmed(auth_client, test_engine, outside)
    shown = confirm(auth_client, price_source="public", via="first-run")
    assert shown["confirmed"] is True and shown["chosen_via"] == "first-run" and shown["chosen_at"].endswith("Z")
    assert live_price()["source"] == "kraken"  # asked now
    for _ in range(2):  # never asked again, on any later start
        assert not start(test_engine).waiting
    assert record(test_engine)["price_choice_via"] == "first-run"


def test_3_nobody_is_asked_too_and_nothing_is_sent_before_or_after(auth_client, test_engine, outside):
    stored(test_engine, price_source="off", proxy_url=TOR)
    asked_until_confirmed(auth_client, test_engine, outside)
    shown = confirm(auth_client, price_source="off", proxy_url=TOR, via="settings")
    assert shown["confirmed"] and shown["proxy_url"] == TOR  # kept as it was
    assert live_price() == 503 and outside == []


@pytest.mark.parametrize("settings", [
    {"price_source": "mempool", "mempool_url": NODE, "mempool_fallback": "off"},
    {"price_source": "mempool", "mempool_url": NODE, "mempool_fallback": "on"},
    {"price_source": "mempool", "mempool_url": ONION, "mempool_fallback": "off", "proxy_url": TOR},
], ids=["mempool", "with its backup", "onion"])
def test_4_your_mempool_is_paused_until_confirmed(auth_client, test_engine, outside, settings):
    stored(test_engine, **settings)
    asked_until_confirmed(auth_client, test_engine, outside)
    confirm(auth_client, price_source="mempool", mempool_url=settings["mempool_url"],
            mempool_fallback=settings["mempool_fallback"] == "on", proxy_url=settings.get("proxy_url"))
    assert live_price()["source"] == "mempool"
    assert [u for u in outside if not u.startswith(settings["mempool_url"])] == []


def test_5_set_by_startos_is_never_asked_until_the_switch_to_choose_in_bitcointx(
        auth_client, test_engine, outside, monkeypatch):
    """And #155's narrow gap: after the switch to Decide in BitcoinTX instead, an
    unrecorded choice made in the app (or one saved while stopped) is asked."""
    stored(test_engine, price_source="public")
    monkeypatch.setenv("BTCTX_PRICE_SOURCE", "mempool")
    monkeypatch.setenv("BTCTX_MEMPOOL_URL", NODE)
    s = start(test_engine)
    assert s.managed and not s.waiting
    assert auth_client.get("/api/settings/network").json()["confirmed"] is True
    assert live_price()["source"] == "mempool"
    outside.clear()
    monkeypatch.delenv("BTCTX_PRICE_SOURCE")
    monkeypatch.delenv("BTCTX_MEMPOOL_URL")
    asked_until_confirmed(auth_client, test_engine, outside)  # Decide in BitcoinTX instead


@pytest.mark.parametrize("settings", [{}, {"price_source": "unset"}], ids=["no row", "unset"])
def test_6_not_chosen_gets_the_first_run_question_not_the_confirm_one(auth_client, test_engine, outside, settings):
    stored(test_engine, **settings)
    s = start(test_engine)
    assert s.price_source == "unset" and not s.waiting
    shown = auth_client.get("/api/settings/network").json()
    assert shown["price_source"] == "unset" and shown["confirmed"] is True
    assert auth_client.get("/api/bitcoin/price").json()["detail"].startswith("Prices: not chosen yet")
    assert outside == []


def test_7_a_pre_1_1_0_install_is_upgraded_as_before_then_asked(auth_client, test_engine, outside):
    stored(test_engine, live_data="on")
    assert start(test_engine).price_source == "public"
    asked_until_confirmed(auth_client, test_engine, outside)


def test_8_changing_the_choice_while_confirming_saves_the_new_one(auth_client, test_engine, outside):
    stored(test_engine, price_source="public")
    start(test_engine)
    shown = confirm(auth_client, price_source="mempool", mempool_url=NODE, via="first-run")
    assert (shown["price_source"], shown["confirmed"], shown["chosen_via"]) == ("mempool", True, "first-run")
    assert not start(test_engine).waiting


def test_9_an_in_app_restore_keeps_the_current_record(auth_client, test_engine, outside, monkeypatch):
    from backend.routers import backup

    confirm(auth_client, price_source="public", via="settings")
    before = record(test_engine)

    def restore_old_backup(password, path):  # an older backup: public, no record
        stored(test_engine, price_source="public")

    monkeypatch.setattr(backup, "restore_backup", restore_old_backup)
    r = auth_client.post("/api/backup/restore", data={"password": "pw"}, files={"file": ("b.btx", b"x")})
    assert r.status_code == 200, r.text
    assert auth_client.post("/api/login", json=default_login()).status_code == 200
    assert record(test_engine) == before
    assert not start(test_engine).waiting


def test_10_a_command_and_the_ai_key_never_write_the_record(auth_client, test_engine, outside, ai_key_headers):
    stored(test_engine, price_source="public")
    with sessionmaker(bind=test_engine)() as db:
        outbound.load(db, upgrade=False)  # what every backend.cli command does
    r = TestClient(auth_client.app).put("/api/settings/network", headers=ai_key_headers,
                                        json={"price_source": "public", "via": "settings"})
    assert r.status_code == 403
    assert record(test_engine) == {}
    assert start(test_engine).waiting
    # Nothing else in the backend writes it: only save() names the keys
    backend = Path(__file__).resolve().parents[1]
    writers = [p.relative_to(backend).as_posix() for p in backend.rglob("*.py")
               if "tests" not in p.parts and ("CHOSEN_AT_KEY" in p.read_text() or "price_choice_at" in p.read_text())]
    assert writers == ["services/outbound.py"]
