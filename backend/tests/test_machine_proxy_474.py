"""
A proxy set for the whole machine (#474, the owner's rule of 2026-10-17):
HTTPS_PROXY, HTTP_PROXY, ALL_PROXY, or the Mac's system proxy. The public
price sites still follow it when BitcoinTX sets no proxy of its own (the
1.2.8 notes tell Docker users they may hide their address that way). Nothing
to this computer or the home network ever does: your Mempool at a home
address, the Mac app's start-up checks of 127.0.0.1, the AI connector's
requests to BitcoinTX there. Nor does the price history's download without
Tor (#241): it stays direct.

Each client is built as the app builds it (outbound._transport unset) and
httpx is asked which way it would send a request to the address (its own
transport choice, as #474's probe did): nothing is sent. The Mac's system
proxy is stood in where Python reads it (urllib.request.getproxies, which
httpx calls too, and urllib's proxy_bypass, which reads its exceptions), with
macOS's default exceptions (*.local, 169.254/16), so these run on any system.
The Mac app's checks are real requests, to a server on 127.0.0.1 with a
recording proxy beside it. Only the route changes: certificates are checked
as any client's, SSL_CERT_FILE included.
"""

import http.server
import json
import sys
import threading
import urllib.request
from dataclasses import replace
from pathlib import Path

import httpx
import httpx._utils
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from backend.services import mempool_trust, outbound
from backend.services import price_files as pf
from backend.tests.test_mempool_trust import _cert, _name, _pem
from btctx_mcp import client as connector

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "desktop"))
import desktop_ports  # noqa: E402

CORP = "http://corp-proxy.example:3128"
SOCKS = "socks5://10.9.9.9:1080"
SYSTEM = "http://system-proxy.example:8080"
TOR = "socks5h://127.0.0.1:9050"
# macOS's default "Bypass proxy settings for these Hosts & Domains"
MAC_EXCEPTIONS = ["*.local", "169.254/16"]
PROXY_VARIABLES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")

# How the machine is set: its proxy variables, or the Mac's system proxy
MACHINES = {
    "nothing set": ({}, None),
    "HTTPS_PROXY and HTTP_PROXY": ({"HTTPS_PROXY": CORP, "HTTP_PROXY": CORP}, None),
    "ALL_PROXY": ({"ALL_PROXY": SOCKS}, None),
    "the Mac's system proxy": ({}, SYSTEM),
}
# The proxy each setting gives a request it carries
MACHINE_PROXY = {"nothing set": "direct", "HTTPS_PROXY and HTTP_PROXY": CORP, "ALL_PROXY": SOCKS,
                 "the Mac's system proxy": SYSTEM}


def set_machine(monkeypatch, variables: dict, system: str | None) -> None:
    """The machine's proxy settings, as Python reads them: these variables
    alone (any already set are dropped), and with `system` the Mac's system
    proxy, read as on macOS when no variable is set."""
    for name in PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    for name, value in variables.items():
        monkeypatch.setenv(name, value)

    def getproxies():  # macOS's: the variables, else System Settings' proxy
        return urllib.request.getproxies_environment() or ({"http": system, "https": system} if system else {})

    def proxy_bypass(host):  # macOS's: NO_PROXY with the variables, else System Settings' exceptions
        if urllib.request.getproxies_environment():
            return urllib.request.proxy_bypass_environment(host)
        return urllib.request._proxy_bypass_macosx_sysconf(
            host, {"exclude_simple": False, "exceptions": MAC_EXCEPTIONS})

    monkeypatch.setattr(urllib.request, "getproxies", getproxies)
    monkeypatch.setattr(httpx._utils, "getproxies", getproxies)  # httpx imported it by name
    monkeypatch.setattr(urllib.request, "proxy_bypass", proxy_bypass)
    monkeypatch.setattr(urllib.request, "_opener", None)  # urlopen's opener reads the proxies once


@pytest.fixture(params=MACHINES)
def machine(request, monkeypatch) -> str:
    """Each way the machine may be set; the app's real clients (no fake sites)."""
    set_machine(monkeypatch, *MACHINES[request.param])
    monkeypatch.setattr(outbound, "_transport", None)
    return request.param


def route(client, url: str) -> str:
    """Which way httpx would send a request to `url`: "direct", or the
    proxy's address. Nothing is sent."""
    http = client
    while not isinstance(http, httpx.AsyncClient):  # outbound's wrappers
        http = http._client
    chosen = http._transport_for_url(httpx.URL(url))
    if chosen is http._transport:
        return "direct"
    proxy = chosen._pool._proxy_url
    return f"{proxy.scheme.decode()}://{proxy.host.decode()}:{proxy.port}"


PUBLIC = outbound.NetworkSettings(price_source="public")
PUBLIC_TOR = replace(PUBLIC, proxy_url=TOR)
ONION = "http://mempoolabcdefghijklmnopqrstuvwxyz234567abcdefghijklmnop.onion"
BITSTAMP_BLOCK = f"{pf.BITSTAMP_OHLC_URL}?step=3600&limit=1000&start=1356998400"
KRAKEN = "https://api.kraken.com/0/public/Ticker?pair=XBTUSD"


def mempool(url: str, proxy: str | None = None) -> outbound.NetworkSettings:
    return outbound.NetworkSettings(price_source="mempool", mempool_url=url, proxy_url=proxy)


# #474's table and more: the settings, the client, an address it asks, and the
# way it goes ("machine": the machine's proxy when one is set, else direct)
CLIENTS = [
    ("the history without Tor (Public + Tor + Yes)", replace(PUBLIC_TOR, history_direct=True),
     outbound.history_client, BITSTAMP_BLOCK, "direct"),
    ("your Mempool at a .local name", mempool("http://umbrel.local:3006"), outbound.own_node_client,
     "http://umbrel.local:3006/api/v1/prices", "direct"),
    ("your Mempool at a .local name, Tor set", mempool("http://umbrel.local:3006", TOR),
     outbound.own_node_client, "http://umbrel.local:3006/api/v1/prices", "direct"),
    ("your Mempool at 192.168.x over https", mempool("https://192.168.1.20:3006"), outbound.own_node_client,
     "https://192.168.1.20:3006/api/v1/prices", "direct"),
    ("your Mempool at a one-word name", mempool("http://umbrel:3006"), outbound.own_node_client,
     "http://umbrel:3006/api/v1/prices", "direct"),
    ("your Mempool at a .lan name", mempool("https://mempool.lan"), outbound.own_node_client,
     "https://mempool.lan/api/v1/prices", "direct"),
    ("your Mempool on this computer", mempool("http://127.0.0.1:8999"), outbound.own_node_client,
     "http://127.0.0.1:8999/api/v1/prices", "direct"),
    ("your Mempool at localhost", mempool("http://localhost:8999"), outbound.own_node_client,
     "http://localhost:8999/api/v1/prices", "direct"),
    ("your Mempool at [::1]", mempool("http://[::1]:8999"), outbound.own_node_client,
     "http://[::1]:8999/api/v1/prices", "direct"),
    ("your Mempool at an internet address", mempool("https://mempool.example.com"), outbound.own_node_client,
     "https://mempool.example.com/api/v1/prices", "machine"),
    ("public sites, no proxy in BitcoinTX", PUBLIC, outbound.async_client, KRAKEN, "machine"),
    ("the history, no proxy in BitcoinTX (a Yes changes nothing)", replace(PUBLIC, history_direct=True),
     outbound.history_client, BITSTAMP_BLOCK, "machine"),
    ("public sites through Tor", PUBLIC_TOR, outbound.async_client, KRAKEN, TOR),
    ("the history through Tor (no Yes)", PUBLIC_TOR, outbound.history_client, BITSTAMP_BLOCK, TOR),
    ("an .onion Mempool through Tor", mempool(ONION, TOR), outbound.own_node_client,
     f"{ONION}/api/v1/prices", TOR),
]


@pytest.mark.parametrize("settings, make, url, way", [c[1:] for c in CLIENTS], ids=[c[0] for c in CLIENTS])
def test_each_client_takes_a_machine_wide_proxy_only_for_public_sites(machine, monkeypatch, settings, make, url, way):
    monkeypatch.setattr(outbound, "_current", settings)
    expected = MACHINE_PROXY[machine] if way == "machine" else way
    assert route(make(), url) == expected


# The AI connector: the Mac app's key file names this computer; BTCTX_URL may
# name it, a home address, or an address beyond (BitcoinTX behind a reverse proxy)
CONNECTORS = [
    ("the Mac app's key file", {"key_file": Path("mcp.json")}, "http://127.0.0.1:8765/api/health", "direct"),
    ("the key file, BTCTX_URL on another port here", {"key_file": Path("mcp.json"),
                                                       "base_url": "http://localhost:8766"},
     "http://localhost:8766/api/health", "direct"),
    ("BTCTX_URL on this computer", {"base_url": "http://localhost:80", "ai_key": "k"},
     "http://localhost:80/api/transactions", "direct"),
    ("BTCTX_URL at a home address, plain http", {"base_url": "http://192.168.1.50:8080", "ai_key": "k"},
     "http://192.168.1.50:8080/api/transactions", "direct"),
    ("BTCTX_URL at StartOS's .local address", {"base_url": "https://adjective-noun.local/api", "ai_key": "k"},
     "https://adjective-noun.local/api/transactions", "direct"),
    ("BTCTX_URL at an internet address", {"base_url": "https://btctx.example.com", "ai_key": "k"},
     "https://btctx.example.com/api/transactions", "machine"),
]


@pytest.mark.parametrize("made, url, way", [c[1:] for c in CONNECTORS], ids=[c[0] for c in CONNECTORS])
def test_the_ai_connector_never_takes_a_machine_wide_proxy_to_this_computer_or_home(machine, made, url, way):
    expected = MACHINE_PROXY[machine] if way == "machine" else way
    assert route(connector.BtctxClient(**made)._http, url) == expected


# What counts as this computer or the home network: the app's rule and the
# connector's own copy of it (a package of its own) say the same
HOME = {
    "http://127.0.0.1:8765": True, "http://127.8.9.10": True, "http://localhost:80": True,
    "http://app.localhost": True, "http://[::1]:8765": True,
    "https://umbrel.local": True, "http://mempool.lan:3006": True, "http://umbrel:3006": True,
    "http://10.0.0.5": True, "http://172.16.0.1": True, "http://172.31.255.255": True,
    "http://192.168.1.50:8080": True,
    "https://btctx.example.com": False, "http://8.8.8.8": False, "http://172.32.0.1": False,
    # As the resolver reads them: 8.8.8.8, 127.0.0.1, 8.0.0.8, 0.0.0.0, and the
    # short forms of 127.0.0.1, 10.0.0.1 and 192.168.0.1
    "http://134744072": False, "http://2130706433": True, "http://8.8": False, "http://0": False,
    "http://127.1": True, "http://0x7f.1": True, "http://10.1": True, "http://192.168.1": True,
    "http://0.0.0.0": False,
    # A dot at the end names the same host
    "http://umbrel.local.:3006": True, "http://localhost.:8765": True, "https://btctx.example.com.": False,
    "https://example.local.com": False, "http://[2001:db8::1]": False, "": False, "not a url": False,
}


@pytest.mark.parametrize("url", HOME)
def test_this_computer_and_the_home_network(url):
    assert outbound.this_computer_or_home(url) is HOME[url]
    assert connector.this_computer_or_home(url) is HOME[url]


def test_the_connector_keeps_the_apps_list_of_home_addresses():
    assert connector.HOME_SUFFIXES == mempool_trust.PRIVATE_SUFFIXES
    assert connector.HOME_NETWORKS == mempool_trust.PRIVATE_NETWORKS


def test_a_direct_client_checks_certificates_as_any_client(machine, monkeypatch, tmp_path):
    """Its own connection changes the route only: the certificates a machine
    names in SSL_CERT_FILE are the ones trusted, as for any client
    (trust_env=False would have dropped them)."""
    key = ec.generate_private_key(ec.SECP256R1())
    (tmp_path / "roots.pem").write_bytes(_pem(_cert(_name("BTCTX test root 474"), _name("BTCTX test root 474"),
                                                     key, key, ca=True)))
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "roots.pem"))
    monkeypatch.setattr(outbound, "_current", replace(PUBLIC_TOR, history_direct=True))
    history = outbound.history_client()
    monkeypatch.setattr(outbound, "_current", mempool("https://umbrel.local"))
    home = outbound.own_node_client()
    at_home = connector.BtctxClient(base_url="https://adjective-noun.local", ai_key="k")._http
    for client, url in ((history, BITSTAMP_BLOCK), (home, "https://umbrel.local/api/v1/prices"),
                        (at_home, "https://adjective-noun.local/api/health")):
        while not isinstance(client, httpx.AsyncClient):
            client = client._client
        roots = client._transport_for_url(httpx.URL(url))._pool._ssl_context.get_ca_certs()
        assert [dict(r["subject"][0])["commonName"] for r in roots] == ["BTCTX test root 474"]


# The Mac app's start-up checks of 127.0.0.1: real requests, with a recording
# proxy beside them standing for the machine's
def _serve(handler) -> http.server.HTTPServer:
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class _BitcoinTX(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"status": "ok", "version": "1.2.9", "schema": "0011"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class _RecordingProxy(http.server.BaseHTTPRequestHandler):
    seen: list = []

    def do_GET(self):
        self.seen.append(self.path)
        self.send_error(502)

    def log_message(self, *args):
        pass


@pytest.fixture
def mac_app():
    """A BitcoinTX answering on 127.0.0.1, and a proxy that records what reaches it."""
    _RecordingProxy.seen = []
    app, proxy = _serve(_BitcoinTX), _serve(_RecordingProxy)
    yield app.server_address[1], f"http://127.0.0.1:{proxy.server_address[1]}"
    for server in (app, proxy):
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("set_as", ["HTTP_PROXY", "the Mac's system proxy"])
def test_the_mac_apps_checks_of_this_computer_use_no_proxy(mac_app, monkeypatch, set_as):
    """Before, a proxy set for the whole machine got them, unless it named
    127.0.0.1 as an exception: the app then quit after 30 seconds ("Failed to
    start backend"), or took a running BitcoinTX for none."""
    port, proxy = mac_app
    if set_as == "HTTP_PROXY":
        set_machine(monkeypatch, {"HTTP_PROXY": proxy}, None)
    else:
        set_machine(monkeypatch, {}, proxy)
    assert desktop_ports.running_instance(port)["version"] == "1.2.9"
    assert desktop_ports.wait_for_backend(port, timeout=3.0)
    assert _RecordingProxy.seen == []
