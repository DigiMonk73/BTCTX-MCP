"""
backend/tests/test_cross_site.py

A change sent by another page with the owner's cookie is refused
(backend/security_headers.CrossSiteGuardMiddleware). SameSite=Lax already
stops other sites; this covers another app on the same host (a different
port on the StartOS server counts as the same site), whose page could post a
restore or an import. And CORS is off unless CORS_ALLOW_ORIGINS lists
origins (it used to allow six localhost dev origins with credentials).
"""

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.main as main
from backend.security_headers import CROSS_SITE_REFUSED, CrossSiteGuardMiddleware


def tiny_app(trusted=()):
    app = FastAPI()

    @app.post("/change")
    def change():
        return {"ok": True}

    @app.get("/read")
    def read():
        return {"ok": True}

    app.add_middleware(CrossSiteGuardMiddleware, trusted_origins=list(trusted))
    return TestClient(app, base_url="http://btctx.local:8080")


@pytest.mark.parametrize("site", ["same-site", "cross-site", "Cross-Site"])
def test_a_change_from_another_sites_page_is_refused(site):
    r = tiny_app().post("/change", headers={"Sec-Fetch-Site": site})
    assert r.status_code == 403 and r.json()["detail"] == CROSS_SITE_REFUSED


@pytest.mark.parametrize("site", ["same-origin", "none"])
def test_a_change_from_the_apps_own_page_passes(site):
    assert tiny_app().post("/change", headers={"Sec-Fetch-Site": site}).status_code == 200


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_every_changing_method_is_checked(method):
    r = getattr(tiny_app(), method)("/change", headers={"Sec-Fetch-Site": "same-site"})
    assert r.status_code == 403


def test_reads_are_not_checked():
    assert tiny_app().get("/read", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200


@pytest.mark.parametrize("origin", [
    "http://btctx.local:8081",        # another app, same host
    "http://btctx.local",             # another port (80)
    "http://evil.example:8080",
    "null",                           # sandboxed page
])
def test_without_fetch_metadata_a_foreign_origin_is_refused(origin):
    """Browsers without Sec-Fetch-Site (Safari before 16.4) send Origin."""
    assert tiny_app().post("/change", headers={"Origin": origin}).status_code == 403


@pytest.mark.parametrize("origin", ["http://btctx.local:8080", "http://BTCTX.local:8080"])
def test_without_fetch_metadata_the_apps_own_origin_passes(origin):
    assert tiny_app().post("/change", headers={"Origin": origin}).status_code == 200


def test_behind_the_https_proxy():
    """StartOS: TLS ends at its proxy, which says so in X-Forwarded-*."""
    proxy = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "abc.local"}
    client = tiny_app()
    assert client.post("/change", headers={**proxy, "Origin": "https://abc.local"}).status_code == 200
    assert client.post("/change", headers={**proxy, "Origin": "https://abc.local:443"}).status_code == 200
    assert client.post("/change", headers={**proxy, "Origin": "http://abc.local"}).status_code == 403
    assert client.post("/change", headers={**proxy, "Origin": "https://abc.local:8443"}).status_code == 403


def test_requests_that_are_not_from_a_page_pass():
    """The AI connector, the CLI, curl and tests send neither header."""
    assert tiny_app().post("/change").status_code == 200


def test_origins_listed_for_cors_are_trusted():
    client = tiny_app(trusted=["http://dev.example:5173"])
    headers = {"Origin": "http://dev.example:5173", "Sec-Fetch-Site": "cross-site"}
    assert client.post("/change", headers=headers).status_code == 200


def test_the_app_refuses_a_cross_site_restore(auth_client):
    r = auth_client.post(
        "/api/backup/restore", data={"password": "pw"}, files={"file": ("b.btx", b"x")},
        headers={"Sec-Fetch-Site": "same-site", "Origin": "http://testserver:9999"},
    )
    assert r.status_code == 403 and r.json()["detail"] == CROSS_SITE_REFUSED


def test_the_app_accepts_its_own_pages(auth_client):
    r = auth_client.post("/api/transactions/recalculate",
                         headers={"Sec-Fetch-Site": "same-origin", "Origin": "http://testserver"})
    assert r.status_code == 200
    r = auth_client.post("/api/transactions/recalculate", headers={"Origin": "http://testserver"})
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw, expected", [
    (None, []), ("", []), (" , ", []),
    ("http://a.example, http://b.example:5173,", ["http://a.example", "http://b.example:5173"]),
])
def test_cors_origins(raw, expected):
    assert main.cors_origins(raw) == expected


@pytest.mark.skipif(bool(os.getenv("CORS_ALLOW_ORIGINS")), reason="CORS_ALLOW_ORIGINS is set here")
def test_no_cors_by_default():
    """The dev origins (Vite on 5173 and others) used to be allowed with
    credentials on every install; Vite proxies /api, so none is needed."""
    assert main.ALLOWED_ORIGINS == []
    r = TestClient(main.app).get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert "access-control-allow-origin" not in r.headers
    r = TestClient(main.app).options("/api/login", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers
