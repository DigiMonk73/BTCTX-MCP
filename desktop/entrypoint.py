#!/usr/bin/env python3
"""
BitcoinTX Desktop Application Entry Point

Starts the FastAPI backend on 127.0.0.1:8765 (BTCTX_DESKTOP_PORT) and opens a pywebview window.
Handles graceful shutdown and data directory management.
"""

import os
import sys
import socket
import threading
import time
import logging
import logging.handlers
import base64
from pathlib import Path

from desktop_ports import choose_socket, preferred_port, running_instance, tell_already_running

LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


def setup_logging() -> None:
    """
    Log to stderr and, on macOS, to ~/Library/Logs/BitcoinTX/BitcoinTX.log
    (rotating): a Finder-launched app has no terminal, so without the file
    nothing it logs (such as why it couldn't use its port) is kept.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if sys.platform == "darwin":
        log_dir = Path.home() / "Library" / "Logs" / "BitcoinTX"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.handlers.RotatingFileHandler(
                log_dir / "BitcoinTX.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
            ))
        except OSError as exc:
            print(f"BitcoinTX: no log file ({exc})", file=sys.stderr)
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, handlers=handlers)


setup_logging()
logger = logging.getLogger("BitcoinTX")


def get_application_support_dir() -> Path:
    """
    Returns the macOS Application Support directory for BitcoinTX.
    Creates it if it doesn't exist.
    """
    app_support = Path.home() / "Library" / "Application Support" / "BitcoinTX"
    app_support.mkdir(parents=True, exist_ok=True)
    return app_support


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


def wait_for_backend(port: int, timeout: float = 30.0) -> bool:
    """
    Wait for the backend to become ready.
    Uses exponential backoff from 0.1s to 1s.
    """
    import urllib.request
    import urllib.error

    # Poll the SPA root: it serves index.html without auth. API routes are
    # router-level auth-protected since 2026-02 and return 401, which urllib
    # raises as HTTPError — polling one of those would spin until timeout
    # and the window would never be created.
    url = f"http://127.0.0.1:{port}/"
    start_time = time.time()
    delay = 0.1

    while time.time() - start_time < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    logger.info(f"Backend ready on port {port}")
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            pass

        time.sleep(delay)
        delay = min(delay * 2, 1.0)

    logger.error(f"Backend failed to start within {timeout}s")
    return False


class DesktopAPI:
    """
    Python API exposed to JavaScript via pywebview's js_api.

    Provides native desktop functionality like file save dialogs
    that aren't available in the WebKit renderer.
    """

    def __init__(self):
        self._window = None

    def set_window(self, window):
        """Set the pywebview window reference."""
        self._window = window

    def is_desktop(self) -> bool:
        """Check if running in desktop mode (always True for this API)."""
        return True

    def save_file(self, filename: str, data_base64: str, file_type: str = "pdf") -> dict:
        """
        Save a file using native macOS save dialog.

        Args:
            filename: Suggested filename for the save dialog
            data_base64: Base64-encoded file content
            file_type: File type for the filter (pdf, csv)

        Returns:
            dict with keys:
                - success: bool
                - path: str (if success)
                - error: str (if not success)
        """
        import webview

        try:
            # Decode base64 data
            file_data = base64.b64decode(data_base64)

            # Configure file type filters
            if file_type.lower() == "csv":
                file_types = ("CSV Files (*.csv)", "All files (*.*)")
            elif file_type.lower() == "btx":
                file_types = ("BitcoinTX Backup (*.btx)", "All files (*.*)")
            else:
                file_types = ("PDF Files (*.pdf)", "All files (*.*)")

            # Show native save dialog
            save_path = webview.windows[0].create_file_dialog(
                webview.SAVE_DIALOG,
                save_filename=filename,
                file_types=file_types,
            )

            if save_path:
                # save_path is a tuple for SAVE_DIALOG, get the first element
                if isinstance(save_path, (list, tuple)):
                    save_path = save_path[0]

                # Write the file
                with open(save_path, "wb") as f:
                    f.write(file_data)

                logger.info(f"File saved to: {save_path}")
                return {"success": True, "path": save_path}
            else:
                # User cancelled the dialog
                return {"success": False, "error": "Save cancelled"}

        except Exception as e:
            logger.error(f"Failed to save file: {e}")
            return {"success": False, "error": str(e)}



def run_backend(sock: socket.socket):
    """Run the FastAPI backend with Uvicorn on an already-bound socket."""
    import uvicorn

    config = uvicorn.Config("backend.main:app", log_level="warning", access_log=False)
    uvicorn.Server(config).run(sockets=[sock])


def main():
    """Main entry point for the desktop application."""
    import webview

    # Set up data directory
    app_support = get_application_support_dir()
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
        tell_already_running(preferred)
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
    # The AI assistant key file (backend/services/mcp_key.py): the MCP server
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

    # Create the desktop API for pywebview
    api = DesktopAPI()

    # Create the webview window with the API
    window = webview.create_window(
        title="BitcoinTX",
        url=f"http://127.0.0.1:{port}/",
        width=1280,
        height=800,
        min_size=(800, 600),
        resizable=True,
        confirm_close=False,
        js_api=api,
    )

    # Store window reference in the API
    api.set_window(window)


    # Start the webview (blocks until window is closed)
    webview.start(debug=False)

    logger.info("Application closed")


if __name__ == "__main__":
    main()
