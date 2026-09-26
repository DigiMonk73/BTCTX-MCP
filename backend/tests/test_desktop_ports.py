"""
The Mac app's port handling (desktop/desktop_ports.py).

v0.9.1 bug: after a quit and quick relaunch the app came up on a random port,
so the MCP server couldn't find it. The probe that decided "port busy" bound
without SO_REUSEADDR, which fails while the previous run's connections are in
TIME_WAIT, and a failed probe meant a random port with no retry and no trace.
"""

import http.server
import json
import socket
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "desktop"))
import desktop_ports  # noqa: E402
from desktop_ports import OTHER_PORT, QUIT, RETRY, bind_port, choose_socket, running_instance  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _leave_time_wait(port: int) -> None:
    """Serve one connection on `port` and close it server-side first, so the
    server end sits in TIME_WAIT (what a quit BitcoinTX leaves behind)."""
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # as uvicorn does
    srv.bind(("127.0.0.1", port))
    srv.listen(1)
    cli = socket.create_connection(("127.0.0.1", port))
    conn, _ = srv.accept()
    conn.close()  # active close on the server side -> TIME_WAIT on :port
    srv.close()
    cli.recv(1)
    cli.close()


def _old_probe_says_free(port: int) -> bool:
    """The v0.9.1 check (no SO_REUSEADDR)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def test_port_in_time_wait_is_still_ours():
    port = _free_port()
    _leave_time_wait(port)
    if _old_probe_says_free(port):
        pytest.skip("this OS lets a plain bind reuse a TIME_WAIT port")
    sleeps = []
    sock = bind_port(port, timeout=2, sleep=sleeps.append)
    try:
        assert sock is not None, "the old probe's false 'busy' must not stop the real bind"
        assert sock.getsockname()[1] == port
        assert sleeps == [], "bound on the first attempt"
    finally:
        sock and sock.close()


def test_busy_port_is_retried_then_reported(caplog):
    port = _free_port()
    holder = socket.socket()
    holder.bind(("127.0.0.1", port))
    holder.listen(1)
    try:
        sleeps = []
        with caplog.at_level("WARNING", logger="BitcoinTX"):
            assert bind_port(port, timeout=1.0, interval=0.25, sleep=sleeps.append) is None
        assert len(sleeps) >= 2
        assert "EADDRINUSE" in caplog.text
    finally:
        holder.close()


def test_port_freed_during_retries_is_taken():
    port = _free_port()
    holder = socket.socket()
    holder.bind(("127.0.0.1", port))
    holder.listen(1)

    def release(_seconds):
        holder.close()

    sock = bind_port(port, timeout=5, sleep=release)
    try:
        assert sock is not None and sock.getsockname()[1] == port
    finally:
        sock and sock.close()


class _FakeSock:
    def __init__(self, port):
        self.port = port

    def getsockname(self):
        return ("127.0.0.1", self.port)


def test_choose_socket_never_falls_back_silently(monkeypatch):
    asked = []
    attempts = iter([None, _FakeSock(8765)])
    sock, fallback = choose_socket(8765, ask=lambda p: asked.append(p) or RETRY, bind=lambda p: next(attempts))
    assert (sock.port, fallback, asked) == (8765, False, [8765])

    monkeypatch.setattr(desktop_ports, "bind_any_port", lambda: _FakeSock(50123))
    sock, fallback = choose_socket(8765, ask=lambda p: OTHER_PORT, bind=lambda p: None)
    assert (sock.port, fallback) == (50123, True)

    assert choose_socket(8765, ask=lambda p: QUIT, bind=lambda p: None) == (None, False)


def _serve(body: bytes, status: int = 200):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_running_instance_detects_bitcointx_only():
    bitcointx = _serve(json.dumps({"status": "ok", "version": "0.9.2", "schema": "0003"}).encode())
    degraded = _serve(json.dumps({"status": "error", "version": "0.9.2"}).encode(), status=503)
    other = _serve(b"<html>not us</html>")
    try:
        assert running_instance(bitcointx.server_address[1])["version"] == "0.9.2"
        assert running_instance(degraded.server_address[1]) is not None
        assert running_instance(other.server_address[1]) is None
        assert running_instance(_free_port()) is None
    finally:
        for s in (bitcointx, degraded, other):
            s.shutdown()


def test_desktop_info_endpoint(auth_client, monkeypatch):
    r = auth_client.get("/api/settings/desktop")
    assert r.json() == {"desktop": False, "port": None, "preferred_port": None, "port_fallback": False}

    monkeypatch.setenv("BTCTX_DESKTOP", "1")
    monkeypatch.setenv("BTCTX_DESKTOP_PREFERRED_PORT", "8765")
    monkeypatch.setenv("BTCTX_DESKTOP_ACTUAL_PORT", "8765")
    assert auth_client.get("/api/settings/desktop").json()["port_fallback"] is False
    monkeypatch.setenv("BTCTX_DESKTOP_ACTUAL_PORT", "50123")
    assert auth_client.get("/api/settings/desktop").json() == {
        "desktop": True, "port": 50123, "preferred_port": 8765, "port_fallback": True,
    }
