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


SCRIPT = Path(__file__).resolve().parents[2] / "desktop" / "run-test-build.sh"


def _fake_app(tmp_path) -> Path:
    """An "app" whose binary writes down the folder and port it was given."""
    app = tmp_path / "Fake.app"
    binary = app / "Contents" / "MacOS" / "BitcoinTX"
    binary.parent.mkdir(parents=True)
    binary.write_text('#!/bin/sh\necho "$BTCTX_DESKTOP_DATA_DIR $BTCTX_DESKTOP_PORT" > "$RAN"\n')
    binary.chmod(0o755)
    return app


def _run_script(tmp_path, *args, data=None):
    import os
    import subprocess

    env = {**os.environ, "HOME": str(tmp_path), "TMPDIR": str(tmp_path / "tmp"), "RAN": str(tmp_path / "ran")}
    env.pop("BTCTX_TEST_DATA_DIR", None)
    if data is not None:
        env["BTCTX_TEST_DATA_DIR"] = str(data)
    return subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True)


def test_every_launch_gets_the_same_test_folder_and_port(tmp_path):
    """Run twice from fresh shells (nothing exported): both launches get the
    one test folder, never Application Support, and port 8766."""
    app = _fake_app(tmp_path)
    folder = (tmp_path / "tmp" / "btctx-test-build")
    for _ in range(2):
        r = _run_script(tmp_path, "--app", str(app))
        assert r.returncode == 0, r.stderr
        assert (tmp_path / "ran").read_text().split() == [str(folder.resolve()), "8766"]
    assert _run_script(tmp_path, "--where").stdout.strip() == str(folder.resolve())


def test_the_installed_apps_folder_is_refused(tmp_path):
    app = _fake_app(tmp_path)
    real = tmp_path / "Library" / "Application Support" / "BitcoinTX"
    r = _run_script(tmp_path, "--app", str(app), "--fresh", data=real)
    assert r.returncode == 1 and "refusing" in r.stderr
    assert not (tmp_path / "ran").exists()


def test_fresh_empties_only_what_the_app_keeps(tmp_path):
    app = _fake_app(tmp_path)
    data = tmp_path / "test-data"
    (data / "backups").mkdir(parents=True)
    (data / "btctx.db").write_text("old ledger")
    (data / "notes.txt").write_text("not the app's")
    r = _run_script(tmp_path, "--app", str(app), "--fresh", data=data)
    assert r.returncode == 0, r.stderr
    assert sorted(p.name for p in data.iterdir()) == ["notes.txt"]
