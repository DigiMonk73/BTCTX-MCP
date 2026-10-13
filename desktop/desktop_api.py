"""
What the Mac app's window can ask of the app: pywebview's js_api, which the
page reaches as window.pywebview.api (imported by entrypoint.py; pywebview
only inside save_file, so the tests run on any OS).

Only the app's own window has this API: a browser, or another program that
reaches 127.0.0.1 on the Mac, has no window.pywebview.
"""

from __future__ import annotations

import base64
import logging
from urllib.parse import urlsplit

logger = logging.getLogger("BitcoinTX")


class DesktopAPI:
    """
    Python API exposed to JavaScript via pywebview's js_api: the native Save
    dialog WebKit lacks, and the first-run setup code.
    """

    def __init__(self, app_url: str):
        self._app_url = app_url
        self._window = None

    def _set_window(self, window):
        """Set the pywebview window reference."""
        self._window = window

    def is_desktop(self) -> bool:
        """Check if running in desktop mode (always True for this API)."""
        return True

    def setup_code(self) -> str | None:
        """
        The first-run setup code (backend/services/first_run.py), so the login
        page can set the owner's own username and password while the account
        still has the default login; None when there is none. Only to the
        app's own pages: pywebview gives this API to whatever page the window
        shows.
        """
        if not self._shows_app_page():
            return None
        # Imported here: the backend reads DATABASE_FILE when imported, which
        # entrypoint.main() sets after importing this module.
        from backend.services import first_run

        return first_run.read_code()

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

    def _shows_app_page(self) -> bool:
        """Is the window showing one of the app's own pages (its scheme, host and port)?"""
        if self._window is None:
            return False
        shown = urlsplit(self._window.get_current_url() or "")
        app = urlsplit(self._app_url)
        return (shown.scheme, shown.netloc) == (app.scheme, app.netloc)
