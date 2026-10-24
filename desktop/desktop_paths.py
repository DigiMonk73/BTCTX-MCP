"""
Where the Mac app keeps its data and log, and what it is called (imported
by entrypoint.py and BitcoinTX.spec; no pywebview here, so the tests run on
any OS).

The installed app's data folder holds the owner's real ledger. A test build
run as is would open that ledger, so BTCTX_DESKTOP_DATA_DIR points a test run
at a throwaway folder instead, with its log kept there too.

A 2.0 pre-release (VERSION 2.0.0-beta.N, 2.0 plan 7.4, B10a) is another app,
"BitcoinTX Beta", installed beside BitcoinTX, never in its place: its own
bundle id and its own folders, so a tester's real ledger is never opened or
upgraded. It refuses the installed app's folder however that is spelled, as
desktop/run-test-build.sh does.
"""

from __future__ import annotations

import os
from pathlib import Path

from backend.version import app_version, is_beta_version

DATA_DIR_ENV = "BTCTX_DESKTOP_DATA_DIR"
APP_NAME = "BitcoinTX"
APP_ID = "org.bitcointx.desktop"
BETA_APP_NAME = "BitcoinTX Beta"
BETA_APP_ID = "org.bitcointx.desktop.beta"


class InstalledAppsFolder(RuntimeError):
    """The beta was given the installed app's folder: it won't open it."""


def is_beta() -> bool:
    """Whether this build is a 2.0 pre-release, BitcoinTX Beta."""
    return is_beta_version(app_version())


def own_name() -> str:
    """The app's own name: its bundle's, its folders' and its window's."""
    return BETA_APP_NAME if is_beta() else APP_NAME


def bundle_id() -> str:
    return BETA_APP_ID if is_beta() else APP_ID


def data_dir_override() -> Path | None:
    """The folder BTCTX_DESKTOP_DATA_DIR names, made absolute, or None when it
    isn't set. A relative path would split the data: the backend joins a
    relative DATABASE_FILE to the project (inside the bundled app), while
    mcp.json and the log would follow the current directory."""
    value = os.environ.get(DATA_DIR_ENV, "").strip()
    return Path(value).expanduser().resolve() if value else None


def app_name() -> str:
    """What the app calls itself in its window and its messages: its own
    name, and "Test" after it on a test run (a throwaway data folder, as
    desktop/run-test-build.sh sets), so its window and messages can't be
    taken for the installed app's. The menu bar and the Dock come from the
    bundle."""
    return f"{own_name()} Test" if data_dir_override() is not None else own_name()


def data_dir() -> Path:
    """The folder for btctx.db, the session key, mcp.json and backups/ (created)."""
    folder = data_dir_override() or Path.home() / "Library" / "Application Support" / own_name()
    _refuse_installed_folder(folder, Path.home() / "Library" / "Application Support" / APP_NAME)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def log_dir() -> Path:
    """The log folder: ~/Library/Logs/<own name>, or logs/ in a test data folder."""
    override = data_dir_override()
    if override is not None:
        _refuse_installed_folder(override, Path.home() / "Library" / "Application Support" / APP_NAME)
        return override / "logs"
    folder = Path.home() / "Library" / "Logs" / own_name()
    _refuse_installed_folder(folder, Path.home() / "Library" / "Logs" / APP_NAME)
    return folder


def _refuse_installed_folder(folder: Path, installed: Path) -> None:
    """The beta never uses the installed app's folder, nor one inside it."""
    if is_beta() and _is_or_inside(folder, installed):
        raise InstalledAppsFolder(
            f"{BETA_APP_NAME} won't use {folder}: it is the installed BitcoinTX's folder, "
            "with its own ledger. Give BitcoinTX Beta a folder of its own."
        )


def _is_or_inside(folder: Path, installed: Path) -> bool:
    """By name, ignoring case (macOS file systems do), and by identity for
    each existing folder on the way up, so a link or another spelling is
    caught too."""
    path = str(folder).casefold().rstrip("/") + "/"
    for name in {installed, installed.resolve()}:
        if path.startswith(str(name).casefold().rstrip("/") + "/"):
            return True
    if not installed.exists():
        return False
    return any(d.exists() and os.path.samefile(d, installed) for d in (folder, *folder.parents))
