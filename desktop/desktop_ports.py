"""
Port handling for the Mac app, and its checks of its own address (imported
by entrypoint.py; no pywebview here, so the tests run on any OS).

The app serves on a fixed port (127.0.0.1:8765, BTCTX_DESKTOP_PORT) so the
MCP server can find it; BitcoinTX Preview, a 2.0 alpha or beta, on one of its
own (PREVIEW_PORT), so it never answers in the installed app's place. Up to v0.9.1 a probe bind without SO_REUSEADDR
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
from collections.abc import Callable

from desktop_paths import app_name, bundle_id, is_preview

logger = logging.getLogger("BitcoinTX")

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
# BitcoinTX Preview's (2.0 plan 7.4, B10a): not the installed app's, nor
# desktop/run-test-build.sh's 8766
PREVIEW_PORT = 8767
# This computer's own address never goes through a proxy set for the whole
# machine (HTTP_PROXY and co., the Mac's system proxy, #474): one elsewhere
# can't reach this Mac's 127.0.0.1, and the app would quit or misjudge
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def open_here(url: str, timeout: float):
    """urlopen for this computer's own address: no proxy at all (#474)."""
    return _NO_PROXY.open(url, timeout=timeout)


def preferred_port() -> int:
    return int(os.environ.get("BTCTX_DESKTOP_PORT", PREVIEW_PORT if is_preview() else DEFAULT_PORT))


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
) -> socket.socket | None:
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


def running_instance(port: int, timeout: float = 1.5) -> dict | None:
    """
    The /api/health answer of a BitcoinTX already serving on `port`, or None.
    Anything else on the port (or nothing) returns None.
    """
    url = f"http://{HOST}:{port}/api/health"
    try:
        with open_here(url, timeout=timeout) as resp:
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


def wait_for_backend(port: int, timeout: float = 30.0) -> bool:
    """
    Wait for the backend to become ready.
    Uses exponential backoff from 0.1s to 1s.
    """
    # Poll the SPA root: it serves index.html without auth. API routes are
    # router-level auth-protected since 2026-02 and return 401, which urllib
    # raises as HTTPError — polling one of those would spin until timeout
    # and the window would never be created.
    url = f"http://{HOST}:{port}/"
    start_time = time.time()
    delay = 0.1

    while time.time() - start_time < timeout:
        try:
            with open_here(url, timeout=2) as response:
                if response.status == 200:
                    logger.info("Backend ready on port %d", port)
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            pass

        time.sleep(delay)
        delay = min(delay * 2, 1.0)

    logger.error("Backend failed to start within %gs", timeout)
    return False


# Native dialogs (macOS: osascript; elsewhere: logged, sensible default)
RETRY, OTHER_PORT, QUIT = "Retry", "Use Another Port", "Quit"


def _quoted(text: str) -> str:
    """Text as an AppleScript string."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _osascript(script: str) -> str | None:
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
    name = app_name()
    msg = (
        f"{name} can't use port {port}: another program is using it. "
        f"AI assistants connect to {name} on this port.\\n\\n"
        "Retry after closing that program, use another port for this session "
        "(AI assistants won't connect until you restart), or quit."
    )
    answer = _osascript(
        f'display dialog "{msg}" with title "{name}" '
        f'buttons {{"{QUIT}", "{OTHER_PORT}", "{RETRY}"}} '
        f'default button "{RETRY}" cancel button "{QUIT}" with icon caution'
    )
    if not answer:
        return QUIT
    for choice in (RETRY, OTHER_PORT, QUIT):
        if answer.endswith(choice):
            return choice
    return QUIT


def tell_already_running(port: int, bring_forward: bool = True) -> None:
    """
    Say BitcoinTX is already open and bring it forward, by its own bundle
    id: by name, a second BitcoinTX Preview would bring forward, or start, the
    installed BitcoinTX on its real ledger. A test run (bring_forward=False)
    only says so: AppleScript finds the app by its id, so it could bring
    forward, or start, the installed app on its real ledger instead of the
    test copy. The message names the copy that shows it ("BitcoinTX Test"
    on a test run), so it isn't taken for the installed app's.
    """
    if sys.platform != "darwin":
        logger.error("BitcoinTX is already running on port %d", port)
        return
    if bring_forward:
        _osascript(f'tell application id "{bundle_id()}" to activate')
    name = app_name()
    _osascript(
        f'display dialog "{name} is already open." with title "{name}" '
        'buttons {"OK"} default button "OK"'
    )


def tell_refused(message: str) -> None:
    """Say why the app won't start (BitcoinTX Preview given the installed app's
    folder, desktop_paths.InstalledAppsFolder)."""
    if sys.platform != "darwin":
        logger.error("%s", message)
        return
    name = app_name()
    _osascript(
        f'display dialog {_quoted(message)} with title {_quoted(name)} '
        'buttons {"OK"} default button "OK" with icon stop'
    )


def choose_socket(
    port: int,
    ask: Callable[[int], str] = ask_port_busy,
    bind: Callable[[int], socket.socket | None] = bind_port,
) -> tuple[socket.socket | None, bool]:
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
