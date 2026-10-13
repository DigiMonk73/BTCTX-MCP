"""
Where the Mac app keeps its data and log (imported by entrypoint.py; no
pywebview here, so the tests run on any OS).

The installed app's data folder holds the owner's real ledger. A test build
run as is would open that ledger, so BTCTX_DESKTOP_DATA_DIR points a test run
at a throwaway folder instead, with its log kept there too.
"""

from __future__ import annotations

import os
from pathlib import Path

DATA_DIR_ENV = "BTCTX_DESKTOP_DATA_DIR"
APP_NAME = "BitcoinTX"
TEST_APP_NAME = "BitcoinTX Test"


def data_dir_override() -> Path | None:
    """The folder BTCTX_DESKTOP_DATA_DIR names, made absolute, or None when it
    isn't set. A relative path would split the data: the backend joins a
    relative DATABASE_FILE to the project (inside the bundled app), while
    mcp.json and the log would follow the current directory."""
    value = os.environ.get(DATA_DIR_ENV, "").strip()
    return Path(value).expanduser().resolve() if value else None


def app_name() -> str:
    """What the app calls itself in its window and its messages: "BitcoinTX
    Test" on a test run (a throwaway data folder, as desktop/run-test-build.sh
    sets), so its window and messages can't be taken for the installed
    app's. The menu bar and the Dock still say BitcoinTX: they come from
    the bundle."""
    return TEST_APP_NAME if data_dir_override() is not None else APP_NAME


def data_dir() -> Path:
    """The folder for btctx.db, the session key, mcp.json and backups/ (created)."""
    folder = data_dir_override() or Path.home() / "Library" / "Application Support" / "BitcoinTX"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def log_dir() -> Path:
    """The log folder: ~/Library/Logs/BitcoinTX, or logs/ in a test data folder."""
    override = data_dir_override()
    if override is not None:
        return override / "logs"
    return Path.home() / "Library" / "Logs" / "BitcoinTX"
