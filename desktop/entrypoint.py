#!/usr/bin/env python3
"""
BitcoinTX Desktop Application Entry Point

Starts the FastAPI backend on a free port and opens a pywebview window.
Handles graceful shutdown and data directory management.
"""

import os
import sys
import socket
import threading
import time
import logging
import base64
from pathlib import Path

# Setup logging before any other imports
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("BitcoinTX")


def extend_path_for_homebrew():
    """
    Extend PATH to include common Homebrew installation directories.

    PyInstaller bundles don't inherit the full system PATH, so pdftk
    (installed via Homebrew) won't be found. This must be called BEFORE
    importing any backend modules that use pdftk.
    """
    homebrew_paths = [
        "/opt/homebrew/bin",  # Apple Silicon
        "/usr/local/bin",      # Intel Mac
    ]

    current_path = os.environ.get("PATH", "")
    path_parts = current_path.split(os.pathsep) if current_path else []

    # Prepend Homebrew paths if not already present
    for hp in reversed(homebrew_paths):
        if hp not in path_parts:
            path_parts.insert(0, hp)

    os.environ["PATH"] = os.pathsep.join(path_parts)
    logger.info(f"Extended PATH for Homebrew: {os.environ['PATH']}")


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


# Fixed local port so external clients (the BitcoinTX MCP server) can find
# the app at http://127.0.0.1:8765. Override with BTCTX_DESKTOP_PORT.
DEFAULT_PORT = 8765


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
        except OSError:
            return False
    return True


def find_free_port() -> int:
    """
    Use the fixed port when available; otherwise fall back to a random free
    port (the app still works, but MCP clients won't find it at the usual URL).
    """
    preferred = int(os.environ.get("BTCTX_DESKTOP_PORT", DEFAULT_PORT))
    if _port_is_free(preferred):
        return preferred
    logger.warning(f"Port {preferred} is in use; using a random port (MCP clients won't connect)")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


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


def check_pdftk_available() -> bool:
    """Check if pdftk is installed and available."""
    from backend.services.reports.pdftk_path import is_pdftk_available
    return is_pdftk_available()


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


def run_backend(port: int):
    """Run the FastAPI backend with Uvicorn."""
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )


def main():
    """Main entry point for the desktop application."""
    # IMPORTANT: Extend PATH for Homebrew FIRST, before any backend imports
    # This ensures pdftk can be found in PyInstaller bundles
    extend_path_for_homebrew()

    import webview

    # Set up data directory
    app_support = get_application_support_dir()
    db_path = app_support / "btctx.db"

    # Set environment variables before importing backend
    os.environ["DATABASE_FILE"] = str(db_path)
    os.environ["SECRET_KEY"] = "desktop-app-secret-key-change-in-production"

    # Set frontend path for bundled app
    if getattr(sys, 'frozen', False):
        frontend_dist = get_resource_path("frontend/dist")
        os.environ["BTCTX_FRONTEND_DIST"] = str(frontend_dist)
        logger.info(f"Running from bundle, frontend at: {frontend_dist}")
    else:
        logger.info("Running in development mode")

    # Check pdftk availability
    pdftk_available = check_pdftk_available()
    if not pdftk_available:
        logger.warning("pdftk not found - IRS form generation will be unavailable")

    # Find a free port
    port = find_free_port()
    logger.info(f"Starting backend on port {port}")

    # Start backend in a daemon thread
    backend_thread = threading.Thread(
        target=run_backend,
        args=(port,),
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

    # Show pdftk warning after window loads (if needed)
    def on_loaded():
        if not pdftk_available:
            webview.windows[0].evaluate_js('''
                setTimeout(function() {
                    if (confirm("pdftk is not installed.\\n\\nIRS form generation requires pdftk.\\nInstall with: brew install pdftk-java\\n\\nAll other features will work normally.\\n\\nClick OK to continue.")) {}
                }, 2000);
            ''')

    window.events.loaded += on_loaded

    # Start the webview (blocks until window is closed)
    webview.start(debug=False)

    logger.info("Application closed")


if __name__ == "__main__":
    main()
