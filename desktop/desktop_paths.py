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


def data_dir_override() -> Path | None:
    """The folder BTCTX_DESKTOP_DATA_DIR names, made absolute, or None when it
    isn't set. A relative path would split the data: the backend joins a
    relative DATABASE_FILE to the project (inside the bundled app), while
    mcp.json and the log would follow the current directory."""
    value = os.environ.get(DATA_DIR_ENV, "").strip()
    return Path(value).expanduser().resolve() if value else None


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
