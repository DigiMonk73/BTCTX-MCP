#!/usr/bin/env python3
"""
BitcoinTX Desktop Application Entry Point

Starts the FastAPI backend on 127.0.0.1:8765 (BTCTX_DESKTOP_PORT; BitcoinTX
Preview, a 2.0 alpha or beta, on its own port) and opens a pywebview window.
Handles graceful shutdown and data directory management.
"""

import os
import sys
import socket
import threading
import logging
import logging.handlers
from pathlib import Path

from desktop_api import DesktopAPI
from desktop_paths import DATA_DIR_ENV, InstalledAppsFolder, app_name, data_dir, data_dir_override, log_dir
from desktop_ports import (choose_socket, preferred_port, running_instance, tell_already_running, tell_refused,
                           wait_for_backend)

LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


def setup_logging() -> None:
    """
    Log to stderr and, on macOS, to ~/Library/Logs/BitcoinTX/BitcoinTX.log
    (rotating; desktop_paths.log_dir; BitcoinTX Preview's in its own folder): a
    Finder-launched app has no terminal, so without the file nothing it logs
    (such as why it couldn't use its port) is kept. BitcoinTX Preview given
    the installed app's folder logs nothing there.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if sys.platform == "darwin":
        try:
            folder = log_dir()
            folder.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.handlers.RotatingFileHandler(
                folder / "BitcoinTX.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
            ))
        except (OSError, InstalledAppsFolder) as exc:
            print(f"BitcoinTX: no log file ({exc})", file=sys.stderr)
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, handlers=handlers)


setup_logging()
logger = logging.getLogger("BitcoinTX")


def get_resource_path(relative_path: str) -> Path:
    """
    Get absolute path to a resource, works for dev and PyInstaller bundle.
    """
    if getattr(sys, 'frozen', False):
        # Running in PyInstaller bundle
        base_path = Path(sys._MEIPASS)
    else:
        # Running in development
        base_path = Path(__file__).parent.parent
    return base_path / relative_path


def run_backend(sock: socket.socket):
    """Run the FastAPI backend with Uvicorn on an already-bound socket."""
    import uvicorn

    # No proxy stands in front: a client's address is its connection's, never
    # an X-Forwarded-For header's (the login throttle counts by address).
    config = uvicorn.Config("backend.main:app", log_level="warning", access_log=False, server_header=False,
                            proxy_headers=False)
    uvicorn.Server(config).run(sockets=[sock])


def main():
    """Main entry point for the desktop application."""
    import webview

    # Set up data directory: BitcoinTX Preview never opens the installed app's
    try:
        app_support = data_dir()
    except InstalledAppsFolder as exc:
        logger.error("%s", exc)
        tell_refused(str(exc))
        return
    if data_dir_override() is not None:
        logger.info(f"Test data folder from {DATA_DIR_ENV}: {app_support}")
    db_path = app_support / "btctx.db"

    # Set environment variables before importing backend
    os.environ["DATABASE_FILE"] = str(db_path)
    # SECRET_KEY: generated per install next to the database (backend/secret_key.py)

    # Set frontend path for bundled app
    if getattr(sys, 'frozen', False):
        frontend_dist = get_resource_path("frontend/dist")
        os.environ["BTCTX_FRONTEND_DIST"] = str(frontend_dist)
        logger.info(f"Running from bundle, frontend at: {frontend_dist}")
    else:
        logger.info("Running in development mode")

    # Fixed port, so MCP clients know where to connect. Another port only if
    # the user chooses it in the dialog, never silently.
    preferred = preferred_port()
    if running_instance(preferred):
        logger.info(f"BitcoinTX already answers on port {preferred}; not starting a second copy")
        tell_already_running(preferred, bring_forward=data_dir_override() is None)
        return
    sock, fallback = choose_socket(preferred)
    if sock is None:
        logger.info("Quit: port unavailable")
        return
    port = sock.getsockname()[1]
    os.environ["BTCTX_DESKTOP"] = "1"
    os.environ["BTCTX_DESKTOP_PREFERRED_PORT"] = str(preferred)
    os.environ["BTCTX_DESKTOP_ACTUAL_PORT"] = str(port)
    os.environ["BTCTX_DESKTOP_URL"] = f"http://127.0.0.1:{port}"
    # The AI key file (backend/services/ai_key.py): the MCP server
    # reads the URL and key from here, so its config holds no password or port.
    os.environ["BTCTX_MCP_FILE"] = str(app_support / "mcp.json")
    if fallback:
        logger.warning(f"Using port {port} for this session instead of {preferred} (user's choice)")
    logger.info(f"Starting backend on port {port}")

    # Start backend in a daemon thread
    backend_thread = threading.Thread(
        target=run_backend,
        args=(sock,),
        daemon=True,
        name="BackendThread"
    )
    backend_thread.start()

    # Wait for backend to be ready
    if not wait_for_backend(port):
        logger.error("Failed to start backend")
        sys.exit(1)

    # Create the desktop API for pywebview (desktop_api.py); it answers only
    # the app's own pages
    app_url = os.environ["BTCTX_DESKTOP_URL"]
    api = DesktopAPI(app_url)

    # Create the webview window with the API. The version in the first
    # page's address: pywebview's private mode clears WebKit's stored data
    # as the window opens, but not before it loads, and a page 1.2.8 or
    # earlier cached without Cache-Control must never be shown again
    # unchecked: it reads the API as that version did (#185)
    from backend.version import app_version

    window = webview.create_window(
        title=app_name(),
        url=f"{app_url}/?v={app_version()}",
        width=1280,
        height=800,
        min_size=(800, 600),
        resizable=True,
        confirm_close=False,
        js_api=api,
    )

    # Store window reference in the API
    api._set_window(window)  # pywebview leaves _ names out of the page's window.pywebview.api


    # Start the webview (blocks until window is closed)
    webview.start(debug=False)

    logger.info("Application closed")


if __name__ == "__main__":
    main()
