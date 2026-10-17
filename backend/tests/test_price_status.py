"""
The price status line's facts (#145, GET /api/bitcoin/price/status;
services/price_status.py): where the last price came from and when, the
last problem and why, and the hourly history's download. Read from memory:
the route never asks anything. #178: an https Mempool whose certificate
isn't trusted (a private one, like StartOS's home-network address) is
named as the reason, and when the backup answers instead, the status says
the public sites answered, never your Mempool.
"""

import asyncio
import datetime as dt
import http.server
import ipaddress
import json
import ssl
import threading

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.services import bitcoin, outbound, price_status

# The real function, captured before the session fixture stubs it.
from backend.services.bitcoin import get_current_price as real_current_price

NODE = "http://umbrel.local:3006"
KRAKEN = {"error": [], "result": {"XXBTZUSD": {"c": ["61000.5", "1"]}}}


def use(**settings):
    outbound._current = outbound.NetworkSettings(**settings)
    bitcoin._price_cache.update(settings=None)


def fake_sites(monkeypatch, mempool_up=True, public_up=True):
    """A mempool server at NODE and the public sites, faked; every request recorded."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "umbrel.local" and mempool_up:
            return httpx.Response(200, json={"time": 1, "USD": 61234})
        if request.url.host == "api.kraken.com" and public_up:
            return httpx.Response(200, json=KRAKEN)
        if request.url.host == "umbrel.local" or not public_up:
            raise httpx.ConnectError("All connection attempts failed")
        return httpx.Response(503)

    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(handler))
    return seen


def live_price():
    try:
        return asyncio.run(real_current_price())
    except HTTPException as exc:
        return exc.status_code


def test_the_route_asks_nothing_and_starts_empty(auth_client, monkeypatch):
    seen = fake_sites(monkeypatch)
    use()  # not chosen yet
    status = auth_client.get("/api/bitcoin/price/status").json()
    assert status["source"] == "unset" and status["last_ok"] is None and status["last_problem"] is None
    assert set(status) == {"source", "managed", "invalid", "waiting", "host", "last_ok", "last_problem",
                           "last_mempool_problem", "bitstamp_refused", "history"}
    assert status["history"]["shipped"] is False
    assert seen == []


def test_the_ai_key_cant_read_it(auth_client, ai_key_headers):
    r = TestClient(auth_client.app).get("/api/bitcoin/price/status", headers=ai_key_headers)
    assert r.status_code == 403


def test_your_mempool_answers(auth_client, monkeypatch):
    fake_sites(monkeypatch)
    use(price_source="mempool", mempool_url=NODE)
    assert live_price()["source"] == "mempool"
    status = auth_client.get("/api/bitcoin/price/status").json()
    assert status["last_ok"]["from"] == "mempool" and status["last_ok"]["at"].endswith("Z")
    assert status["last_problem"] is None


@pytest.mark.parametrize("backup", [True, False])
def test_your_mempool_down_with_and_without_the_backup(auth_client, monkeypatch, backup):
    fake_sites(monkeypatch, mempool_up=False)
    use(price_source="mempool", mempool_url=NODE, mempool_fallback=backup)
    answer = live_price()
    status = auth_client.get("/api/bitcoin/price/status").json()
    assert status["last_problem"]["what"] == "mempool_no_answer"
    if backup:
        assert answer["source"] == "kraken" and status["last_ok"]["from"] == "kraken"
    else:
        assert answer == 502 and status["last_ok"] is None


def test_tor_down_is_named(auth_client, monkeypatch):
    fake_sites(monkeypatch, public_up=False)
    use(price_source="public", proxy_url="socks5h://127.0.0.1:9050")
    assert live_price() == 502
    assert auth_client.get("/api/bitcoin/price/status").json()["last_problem"]["what"] == "tor_no_answer"
    use(price_source="public")
    assert live_price() == 502
    assert auth_client.get("/api/bitcoin/price/status").json()["last_problem"]["what"] == "public_no_answer"


def test_mempool_chosen_on_startos_before_it_is_installed(auth_client, monkeypatch):
    seen = fake_sites(monkeypatch)
    use(price_source="mempool", managed=True)
    assert live_price() == 502 and seen == []
    assert auth_client.get("/api/bitcoin/price/status").json()["last_problem"]["what"] == "mempool_missing"


def test_a_change_of_choice_forgets_what_the_old_one_said(auth_client, monkeypatch):
    fake_sites(monkeypatch, mempool_up=False)
    use(price_source="mempool", mempool_url=NODE, mempool_fallback=True)
    live_price()
    use(price_source="public")
    status = auth_client.get("/api/bitcoin/price/status").json()
    assert status["last_ok"] is None and status["last_problem"] is None


# #178: an https Mempool with a certificate from a private authority
def _private_certificate(tmp_path):
    """A root and a server certificate for 127.0.0.1, as a home server has
    (StartOS: its own root): trusted by nothing BitcoinTX knows."""
    def name(text):
        return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, text)])

    now = dt.datetime.now(dt.timezone.utc)
    root_key, key = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    root = (x509.CertificateBuilder().subject_name(name("Home Root CA")).issuer_name(name("Home Root CA"))
            .public_key(root_key.public_key()).serial_number(1).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(root_key, hashes.SHA256()))
    leaf = (x509.CertificateBuilder().subject_name(name("127.0.0.1")).issuer_name(root.subject)
            .public_key(key.public_key()).serial_number(2).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=30))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
                           critical=False)
            .sign(root_key, hashes.SHA256()))
    cert, keyfile = tmp_path / "server.pem", tmp_path / "server.key"
    cert.write_bytes(leaf.public_bytes(serialization.Encoding.PEM) + root.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    return cert, keyfile


@pytest.fixture
def private_https_mempool(tmp_path):
    """A real local https mempool server with a private certificate."""
    class Mempool(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"time": 1, "USD": 61234}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    cert, key = _private_certificate(tmp_path)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Mempool)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"https://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.mark.parametrize("backup", [True, False])
def test_an_untrusted_mempool_certificate_is_named_and_the_backup_is_said(
        auth_client, monkeypatch, private_https_mempool, backup):
    asked_public = []

    def public_sites(request: httpx.Request) -> httpx.Response:
        asked_public.append(request.url.host)
        return httpx.Response(200, json=KRAKEN)

    # The mempool server is reached for real (over TLS); the public sites are faked.
    monkeypatch.setattr(outbound, "async_client", lambda timeout=outbound.TIMEOUT: httpx.AsyncClient(
        timeout=timeout, transport=httpx.MockTransport(public_sites)))
    use(price_source="mempool", mempool_url=private_https_mempool, mempool_fallback=backup)
    answer = live_price()
    status = auth_client.get("/api/bitcoin/price/status").json()
    assert status["last_problem"]["what"] == "mempool_untrusted_certificate"
    if backup:
        assert answer["source"] == "kraken" and status["last_ok"]["from"] == "kraken"
        assert asked_public == ["api.kraken.com"]
    else:
        assert answer == 502 and status["last_ok"] is None and asked_public == []


def test_the_reason_is_found_through_wrapped_errors():
    inner = ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate in chain")
    try:
        try:
            raise inner
        except ssl.SSLError as exc:
            raise httpx.ConnectError("connect failed") from exc
    except httpx.ConnectError as wrapped:
        assert price_status.untrusted_certificate(wrapped)
    assert not price_status.untrusted_certificate(httpx.ConnectError("All connection attempts failed"))


def test_only_the_price_says_where_prices_come_from(auth_client, monkeypatch):
    """Review of #180: a Mempool that gives the block height but no price
    was reported as the price's source while the backup gave the price."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "umbrel.local" and request.url.path.endswith("/height"):
            return httpx.Response(200, text="800000")
        if request.url.host == "umbrel.local":
            return httpx.Response(200, json={"time": 1})  # no price
        if request.url.host == "api.kraken.com":
            return httpx.Response(200, json=KRAKEN)
        return httpx.Response(503)

    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(handler))
    use(price_source="mempool", mempool_url=NODE, mempool_fallback=True)
    bitcoin._height_cache.update(settings=None)
    assert live_price()["source"] == "kraken"
    assert asyncio.run(bitcoin.get_block_height()) == {"height": 800000}  # after the price
    status = auth_client.get("/api/bitcoin/price/status").json()
    assert status["last_ok"]["from"] == "kraken" and status["last_problem"]["what"] == "mempool_no_answer"


def test_the_mempools_reason_is_kept_when_the_backup_fails_too(auth_client, monkeypatch):
    fake_sites(monkeypatch, mempool_up=False, public_up=False)
    use(price_source="mempool", mempool_url=NODE, mempool_fallback=True)
    assert live_price() == 502
    status = auth_client.get("/api/bitcoin/price/status").json()
    assert status["last_problem"]["what"] == "public_no_answer"
    assert status["last_mempool_problem"]["what"] == "mempool_no_answer"
