"""
backend/tests/test_page_version.py

A page left open over an upgrade is refused before it can write (spec 5.13,
B6a-12): a 1.x page sends no X-BitcoinTX-Page and would save a Buy or Sell
into the first exchange, so a logged-in change a browser sent without the
page's version, or from another major version, gets 409 and "reload the
page" (backend/security_headers.PageVersionMiddleware). Scripts, the AI
connector and tests send no browser header and are unaffected; so are reads
and the routes before login.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.security_headers import PAGE_OUTDATED, PageVersionMiddleware
from backend.version import app_version

COOKIE = "btc_session_id"
LOGGED_IN = {"Cookie": f"{COOKIE}=signed-session"}
OWN_PAGE = {"Sec-Fetch-Site": "same-origin"}


def tiny_app(version="2.0.0"):
    """The server's version is stubbed: this branch's VERSION is still 1.x."""
    app = FastAPI()

    @app.post("/api/change")
    def change():
        return {"ok": True}

    @app.get("/api/read")
    def read():
        return {"ok": True}

    @app.post("/elsewhere")
    def elsewhere():
        return {"ok": True}

    app.add_middleware(PageVersionMiddleware, session_cookie=COOKIE, version=version)
    return TestClient(app, base_url="http://btctx.local:8080")


@pytest.mark.parametrize("browser", [
    {"Sec-Fetch-Site": "same-origin"},
    {"Sec-Fetch-Site": "none"},
    {"Origin": "http://btctx.local:8080"},  # Safari before 16.4: no Sec-Fetch-Site
])
def test_a_logged_in_page_without_its_version_is_refused(browser):
    r = tiny_app().post("/api/change", headers={**LOGGED_IN, **browser})
    assert r.status_code == 409 and r.json()["detail"] == PAGE_OUTDATED


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_every_changing_method_is_checked(method):
    r = getattr(tiny_app(), method)("/api/change", headers={**LOGGED_IN, **OWN_PAGE})
    assert r.status_code == 409


@pytest.mark.parametrize("page", ["1.2.9", "0.9.1", "3.0.0", ""])
def test_a_page_of_another_major_version_is_refused(page):
    r = tiny_app().post("/api/change", headers={**LOGGED_IN, **OWN_PAGE, "X-BitcoinTX-Page": page})
    assert r.status_code == 409 and r.json()["detail"] == PAGE_OUTDATED


@pytest.mark.parametrize("page", ["2.0.0", "2.4.1", " 2.0.0-rc1 "])
def test_any_page_of_the_servers_major_version_passes(page):
    r = tiny_app().post("/api/change", headers={**LOGGED_IN, **OWN_PAGE, "X-BitcoinTX-Page": page})
    assert r.status_code == 200


def test_scripts_and_the_connector_send_no_browser_header_and_pass():
    """seed_ledger.py, smoke_test.py, the equivalence snapshot, AGENT-TESTS' curl."""
    assert tiny_app().post("/api/change", headers=LOGGED_IN).status_code == 200


def test_the_routes_before_login_are_not_checked():
    """No session cookie: login, Create account, setup status. A stale page logs
    in, then its first write is refused."""
    assert tiny_app().post("/api/change", headers=OWN_PAGE).status_code == 200
    other_cookie = {"Cookie": f"btc_device=x; not_{COOKIE}=y"}
    assert tiny_app().post("/api/change", headers={**other_cookie, **OWN_PAGE}).status_code == 200


def test_reads_and_pages_outside_the_api_are_not_checked():
    client = tiny_app()
    assert client.get("/api/read", headers={**LOGGED_IN, **OWN_PAGE}).status_code == 200
    assert client.post("/elsewhere", headers={**LOGGED_IN, **OWN_PAGE}).status_code == 200


def test_the_app_refuses_a_page_from_before_the_upgrade(auth_client):
    r = auth_client.post("/api/transactions/recalculate", headers=OWN_PAGE)
    assert r.status_code == 409 and r.json()["detail"] == PAGE_OUTDATED


def test_the_app_accepts_its_own_page(auth_client):
    page = {**OWN_PAGE, "X-BitcoinTX-Page": app_version()}
    assert auth_client.post("/api/transactions/recalculate", headers=page).status_code == 200


def test_the_app_accepts_the_tests_own_client(auth_client):
    assert auth_client.post("/api/transactions/recalculate").status_code == 200
