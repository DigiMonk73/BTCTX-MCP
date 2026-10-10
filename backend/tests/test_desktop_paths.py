"""
The Mac app's data and log folders (desktop/desktop_paths.py).

The installed app's data folder holds the owner's real ledger, so a test
build must be able to run on a throwaway folder: BTCTX_DESKTOP_DATA_DIR.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "desktop"))
import desktop_paths  # noqa: E402


def test_default_is_application_support(monkeypatch, tmp_path):
    monkeypatch.delenv(desktop_paths.DATA_DIR_ENV, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert desktop_paths.data_dir() == tmp_path / "Library" / "Application Support" / "BitcoinTX"
    assert desktop_paths.log_dir() == tmp_path / "Library" / "Logs" / "BitcoinTX"


def test_test_data_folder_keeps_data_and_log_out_of_home(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv(desktop_paths.DATA_DIR_ENV, str(tmp_path / "test-data"))

    assert desktop_paths.data_dir() == tmp_path / "test-data"
    assert (tmp_path / "test-data").is_dir()
    assert desktop_paths.log_dir() == tmp_path / "test-data" / "logs"
    assert list(home.iterdir()) == []


def test_blank_override_means_the_default(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(desktop_paths.DATA_DIR_ENV, "  ")
    assert desktop_paths.data_dir_override() is None
    assert desktop_paths.data_dir() == tmp_path / "Library" / "Application Support" / "BitcoinTX"


def test_a_relative_folder_is_made_absolute(monkeypatch, tmp_path):
    """The backend joins a relative DATABASE_FILE to the project, while
    mcp.json and the log would follow the current directory: one folder,
    absolute, keeps them together."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(desktop_paths.DATA_DIR_ENV, "rel-data")
    assert desktop_paths.data_dir() == tmp_path.resolve() / "rel-data"
    assert desktop_paths.log_dir() == tmp_path.resolve() / "rel-data" / "logs"


def test_entrypoint_takes_its_folders_from_desktop_paths():
    source = (Path(__file__).resolve().parents[2] / "desktop" / "entrypoint.py").read_text()
    assert "Path.home" not in source
    assert "Application Support" not in source
    assert "app_support = data_dir()" in source
    assert "bring_forward=data_dir_override() is None" in source
