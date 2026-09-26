"""
Port handling for the Mac app (imported by entrypoint.py; no pywebview here,
so the tests run on any OS).

The app serves on a fixed port (127.0.0.1:8765, BTCTX_DESKTOP_PORT) so the
MCP server can find it. Up to v0.9.1 a probe bind without SO_REUSEADDR
decided whether the port was free: connections from the previous run still
in TIME_WAIT made it fail, and the app silently moved to a random port for the
whole session. Now the listening socket itself is bound, with SO_REUSEADDR
(as uvicorn does), retried for a while, and handed to uvicorn, so nothing can
take the port between the check and the start.
"""

from __future__ import annotations

import errno
import json
import logging
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

logger = logging.getLogger("BitcoinTX")

HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def preferred_port() -> int:
    return int(os.environ.get("BTCTX_DESKTOP_PORT", DEFAULT_PORT))


def _listening_socket(port: int) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform != "win32":
        # Lets the bind succeed while old connections sit in TIME_WAIT; a port
        # another program is listening on still fails with EADDRINUSE.
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((HOST, port))
        s.listen(2048)
    except OSError:
        s.close()
        raise
    return s


def bind_port(
    port: int,
    timeout: float = 10.0,
    interval: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
) -> Optional[socket.socket]:
    """
    A listening socket on HOST:port, retrying every `interval` seconds for up
    to `timeout` seconds. None if the port stays unavailable. Every failure is
    logged with its errno so a later "why the other port?" has an answer.
    """
    deadline = time.monotonic() + timeout
    attempt = 0
    while True:
        attempt += 1
        try:
            sock = _listening_socket(port)
        except OSError as exc:
            name = errno.errorcode.get(exc.errno or 0, str(exc.errno))
            logger.warning("Port %d unavailable (attempt %d): %s %s", port, attempt, name, exc.strerror)
            if time.monotonic() + interval > deadline:
                logger.error("Port %d still unavailable after %.0fs", port, timeout)
                return None
            sleep(interval)
            continue
        logger.info("Bound %s:%d (attempt %d)", HOST, port, attempt)
        return sock


def bind_any_port() -> socket.socket:
    """A listening socket on a free port chosen by the OS (only on request)."""
    return _listening_socket(0)


def running_instance(port: int, timeout: float = 1.5) -> Optional[dict]:
    """
    The /api/health answer of a BitcoinTX already serving on `port`, or None.
    Anything else on the port (or nothing) returns None.
    """
    url = f"http://{HOST}:{port}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:  # 503: BitcoinTX with a schema problem
        body = exc.read()
    except (OSError, ValueError):
        return None
    try:
        data = json.loads(body)
    except ValueError:
        return None
    if isinstance(data, dict) and {"status", "version"} <= data.keys():
        return data
    return None


# ---------------------------------------------------------------------------
# Native dialogs (macOS: osascript; elsewhere: logged, sensible default)
# ---------------------------------------------------------------------------
RETRY, OTHER_PORT, QUIT = "Retry", "Use Another Port", "Quit"


def _osascript(script: str) -> Optional[str]:
    try:
        out = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True, timeout=600
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Dialog unavailable: %s", exc)
        return None
    if out.returncode != 0:  # user pressed Cancel/Escape
        return None
    return out.stdout.strip()


def ask_port_busy(port: int) -> str:
    """Ask what to do when the port stays taken: RETRY, OTHER_PORT or QUIT."""
    if sys.platform != "darwin":
        logger.error("Port %d is taken; using another port for this session", port)
        return OTHER_PORT
    msg = (
        f"BitcoinTX can't use port {port}: another program is using it. "
        "AI assistants connect to BitcoinTX on this port.\\n\\n"
        "Retry after closing that program, use another port for this session "
        "(AI assistants won't connect until you restart), or quit."
    )
    answer = _osascript(
        f'display dialog "{msg}" with title "BitcoinTX" '
        f'buttons {{"{QUIT}", "{OTHER_PORT}", "{RETRY}"}} '
        f'default button "{RETRY}" cancel button "{QUIT}" with icon caution'
    )
    if not answer:
        return QUIT
    for choice in (RETRY, OTHER_PORT, QUIT):
        if answer.endswith(choice):
            return choice
    return QUIT


def tell_already_running(port: int) -> None:
    """Bring the running BitcoinTX forward and say so."""
    if sys.platform != "darwin":
        logger.error("BitcoinTX is already running on port %d", port)
        return
    _osascript('tell application "BitcoinTX" to activate')
    _osascript(
        'display dialog "BitcoinTX is already open." with title "BitcoinTX" '
        'buttons {"OK"} default button "OK"'
    )


def choose_socket(
    port: int,
    ask: Callable[[int], str] = ask_port_busy,
    bind: Callable[[int], Optional[socket.socket]] = bind_port,
) -> tuple[Optional[socket.socket], bool]:
    """
    (listening socket, fallback) for this session: the preferred port, or,
    only if the user chooses it, another port (fallback=True). (None, False)
    means quit.
    """
    while True:
        sock = bind(port)
        if sock is not None:
            return sock, False
        choice = ask(port)
        logger.info("Port %d busy; user chose %s", port, choice)
        if choice == RETRY:
            continue
        if choice == OTHER_PORT:
            return bind_any_port(), True
        return None, False
