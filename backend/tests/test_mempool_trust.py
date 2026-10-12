"""
#188: trusting a home server's own certificate for your own Mempool. A
local https server with a private certificate authority stands in for a
StartOS server's home-network address: not trusted, then trusted after the
owner's click (for that address only, never for public sites), then
forgotten.
"""

import asyncio
import datetime as dt
import http.server
import json
import ssl
import threading

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from backend.services import mempool_trust, outbound, price_status

NETWORK = "/api/settings/network"
CERTIFICATE = "/api/settings/network/mempool-certificate"


def _name(cn: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _cert(subject, issuer, key, signer, ca: bool, sans=()):
    now = dt.datetime.now(dt.timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(key.public_key())
               .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
               .not_valid_after(now + dt.timedelta(days=30))
               .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    if sans:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in sans]), critical=False)
    return builder.sign(signer, hashes.SHA256())


def _pem(cert) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


class _Mempool(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server's name)
        body = json.dumps({"USD": 70000, "time": 1760000000}).encode() if self.path == "/api/v1/prices" else b"{}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _serve(tmp_path, name: str, send_root: bool = True):
    """A home server's Mempool on https://localhost:<port>: its leaf
    certificate from its own "<name> Local Root CA", sent with that root."""
    root_key, leaf_key = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    root = _cert(_name(f"{name} Local Root CA"), _name(f"{name} Local Root CA"), root_key, root_key, ca=True)
    leaf = _cert(_name("localhost"), root.subject, leaf_key, root_key, ca=False, sans=("localhost",))
    chain, key = tmp_path / f"{name}-chain.pem", tmp_path / f"{name}-key.pem"
    chain.write_bytes(_pem(leaf) + (_pem(root) if send_root else b""))
    key.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(chain, key)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Mempool)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fingerprint = root.fingerprint(hashes.SHA256()).hex(":").upper()
    return server, f"https://localhost:{server.server_address[1]}", fingerprint


@pytest.fixture
def home_server(tmp_path, auth_client, test_engine, monkeypatch):
    """The owner's Mempool at a home server's https address, chosen in Settings."""
    monkeypatch.setattr(outbound, "_transport", None)  # the real network, to localhost only
    server, url, fingerprint = _serve(tmp_path, "home-server")
    r = auth_client.put(NETWORK, json={"price_source": "mempool", "mempool_url": url})
    assert r.status_code == 200, r.text
    yield url, fingerprint
    server.shutdown()
    auth_client.put(NETWORK, json={"price_source": "public"})
    with test_engine.begin() as conn:
        conn.execute(text("DELETE FROM app_settings WHERE key = :k"), {"k": outbound.TRUSTED_ROOT_KEY})


async def _price(client_for) -> int:
    async with client_for() as client:
        return (await client.get(f"{outbound.current().mempool_url}/api/v1/prices")).json()["USD"]


def test_a_home_servers_mempool_untrusted_then_trusted_then_forgotten(auth_client, home_server):
    url, fingerprint = home_server
    with pytest.raises(httpx.ConnectError) as untrusted:
        asyncio.run(_price(outbound.own_node_client))
    assert price_status.untrusted_certificate(untrusted.value)
    assert auth_client.get(NETWORK).json()["mempool_trustable"] is True

    shown = auth_client.get(CERTIFICATE).json()  # what the owner sees before trusting
    assert shown == {"server": "localhost", "name": "home-server Local Root CA", "sha256": fingerprint}
    r = auth_client.put(CERTIFICATE, json={"sha256": fingerprint})
    assert r.status_code == 200, r.text
    assert r.json()["mempool_certificate"] == {"name": "home-server Local Root CA", "sha256": fingerprint}
    assert asyncio.run(_price(outbound.own_node_client)) == 70000  # BitcoinTX can use it now

    r = auth_client.delete(CERTIFICATE)
    assert r.status_code == 200 and r.json()["mempool_certificate"] is None
    with pytest.raises(httpx.ConnectError):
        asyncio.run(_price(outbound.own_node_client))


def test_the_trusted_root_is_never_used_for_public_sites(auth_client, home_server):
    url, fingerprint = home_server
    assert auth_client.put(CERTIFICATE, json={"sha256": fingerprint}).status_code == 200
    with pytest.raises(httpx.ConnectError) as refused:  # the public sites' client: the usual trust store only
        asyncio.run(_price(outbound.async_client))
    assert price_status.untrusted_certificate(refused.value)


def test_another_servers_certificate_isnt_trusted_by_a_trusted_root(auth_client, home_server, tmp_path):
    """The root is trusted for its address only: another server (another
    authority) at another address isn't, nor is the same one after the
    address changes."""
    url, fingerprint = home_server
    assert auth_client.put(CERTIFICATE, json={"sha256": fingerprint}).status_code == 200
    other, other_url, _ = _serve(tmp_path, "other-server")
    try:
        r = auth_client.put(NETWORK, json={"price_source": "mempool", "mempool_url": other_url})
        assert r.json()["mempool_certificate"] is None  # a new address forgets it
        with pytest.raises(httpx.ConnectError):
            asyncio.run(_price(outbound.own_node_client))
        r = auth_client.put(NETWORK, json={"price_source": "mempool", "mempool_url": url})
        assert r.json()["mempool_certificate"] is None  # and stays forgotten
    finally:
        other.shutdown()


def test_a_changed_certificate_isnt_trusted(auth_client, home_server):
    url, fingerprint = home_server
    r = auth_client.put(CERTIFICATE, json={"sha256": "AB:" + fingerprint[3:]})
    assert r.status_code == 409 and "changed since it was shown" in r.json()["detail"]
    assert auth_client.get(NETWORK).json()["mempool_certificate"] is None


def test_a_server_that_doesnt_show_its_root_cant_be_trusted(auth_client, tmp_path, monkeypatch):
    monkeypatch.setattr(outbound, "_transport", None)
    server, url, _ = _serve(tmp_path, "no-root", send_root=False)
    try:
        assert auth_client.put(NETWORK, json={"price_source": "mempool", "mempool_url": url}).status_code == 200
        r = auth_client.get(CERTIFICATE)
        assert r.status_code == 422 and "doesn't show its root certificate" in r.json()["detail"]
    finally:
        server.shutdown()
        auth_client.put(NETWORK, json={"price_source": "public"})


@pytest.mark.parametrize("url", [
    "https://mempool.example.com", "https://8.8.8.8", "https://172.32.0.1", "https://11.0.0.1",
    "http://umbrel.local", "https://abc.onion",
    # review of #193: the resolver's reading, not a name's look
    "https://134744072", "https://0x08080808", "https://0", "https://evil。com", "https://evil．com",
    "https://xn--zz", "https://10.0.0.1.", "https://box.local:４４３", "https://box.local:99999",
])
def test_a_public_address_is_never_offered(auth_client, monkeypatch, url):
    """Never for a public internet name, so it can't get around a real certificate problem."""
    async def no_connection(*args):
        raise AssertionError("nothing may be asked")

    monkeypatch.setattr(outbound, "own_node_certificates", no_connection)
    assert mempool_trust.private_address(url) is False
    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings(price_source="mempool", mempool_url=url))
    for r in (auth_client.get(CERTIFICATE), auth_client.put(CERTIFICATE, json={"sha256": "AB"})):
        assert r.status_code == 422 and "home-network" in r.json()["detail"]
    assert auth_client.get(NETWORK).json()["mempool_trustable"] is False


@pytest.mark.parametrize("url", [
    "https://start9.local", "https://umbrel.lan:8443", "https://10.0.0.5", "https://172.16.1.1",
    "https://172.31.255.1", "https://192.168.1.20:4080", "https://myserver", "https://3232235777",
])
def test_home_network_addresses_are_offered(url):
    assert mempool_trust.private_address(url) is True


def test_only_for_your_own_mempool_in_use(auth_client):
    """Public sites chosen (the tests' default): nothing to trust, nothing asked."""
    r = auth_client.get(CERTIFICATE)
    assert r.status_code == 409 and "your own Mempool" in r.json()["detail"]


def test_never_with_the_ai_key(auth_client, ai_key_headers):
    from fastapi.testclient import TestClient

    from backend.main import app

    key_only = TestClient(app)
    for method in ("get", "put", "delete"):
        r = key_only.request(method.upper(), CERTIFICATE, headers=ai_key_headers, json={"sha256": "AB"})
        assert r.status_code == 403, (method, r.text)


def test_a_restore_keeps_this_installs_trusted_root(auth_client, home_server, test_engine):
    """Like the price choice: an in-app restore never brings back a backup's."""
    url, fingerprint = home_server
    assert auth_client.put(CERTIFICATE, json={"sha256": fingerprint}).status_code == 200
    db = sessionmaker(bind=test_engine)()
    try:
        before = outbound.snapshot(db)
        assert json.loads(before[outbound.TRUSTED_ROOT_KEY])["url"] == url
        db.execute(text("DELETE FROM app_settings WHERE key = :k"), {"k": outbound.TRUSTED_ROOT_KEY})
        db.commit()  # what restoring a backup without it does
        assert outbound.carry_over(db, before).mempool_root is not None
    finally:
        db.close()


def test_an_address_httpx_cant_read_never_breaks_the_settings(auth_client, monkeypatch):
    """Re-check of #193: "xn--zz" is accepted as an address but idna refuses it."""
    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings(
        price_source="mempool", mempool_url="https://xn--zz"))
    r = auth_client.get(NETWORK)
    assert r.status_code == 200 and r.json()["mempool_trustable"] is False


def test_a_damaged_row_trusts_nothing(test_engine):
    """A row that isn't exactly one certificate (two, or a key before one) trusts nothing."""
    root_key = ec.generate_private_key(ec.SECP256R1())
    root = _cert(_name("x Local Root CA"), _name("x Local Root CA"), root_key, root_key, ca=True)
    one = _pem(root).decode()
    key = root_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption()).decode()
    db = sessionmaker(bind=test_engine)()
    try:
        for pem, kept in ((one, True), (one + one, False), (key + one, False), ("junk", False), (None, False)):
            outbound._set(db, outbound.TRUSTED_ROOT_KEY, json.dumps({"url": "https://box.local", "pem": pem}))
            assert (outbound._trusted_root(db, "https://box.local") is not None) is kept, pem
        outbound._set(db, outbound.TRUSTED_ROOT_KEY, None)
        db.commit()
    finally:
        db.close()
