"""
The Mac beta app, "BitcoinTX Beta" (2.0 plan 7.4, B10a, point 2; #532).

A build is the beta when VERSION has a pre-release suffix (2.0.0-beta.N),
and the ordinary app otherwise, so 2.0.0 builds BitcoinTX with no edit. The
beta is installed beside BitcoinTX, never in its place: its own name and
bundle id, its own data and log folders, its own port. So a tester's real
ledger is never opened or upgraded, and like desktop/run-test-build.sh it
refuses the installed app's folder however that is spelled.

desktop/run-test-build.sh sets its own folder and port, so a run through it
can't show these defaults: these tests do (7.4's "Done when").
"""

import re
import sys
from pathlib import Path

import pytest

DESKTOP = Path(__file__).resolve().parents[2] / "desktop"
sys.path.insert(0, str(DESKTOP))
import desktop_paths  # noqa: E402
import desktop_ports  # noqa: E402

BETA, RELEASE = "2.0.0-beta.1", "2.0.0"


@pytest.fixture
def home(monkeypatch, tmp_path):
    """An empty home, no test folder or port set."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv(desktop_paths.DATA_DIR_ENV, raising=False)
    monkeypatch.delenv("BTCTX_DESKTOP_PORT", raising=False)
    return tmp_path


def version(monkeypatch, value: str) -> None:
    monkeypatch.setattr(desktop_paths, "app_version", lambda: value)


def installed(home: Path) -> Path:
    return home / "Library" / "Application Support" / "BitcoinTX"


@pytest.mark.parametrize("value, beta", [
    ("2.0.0-beta.1", True), ("2.0.0-beta.12", True),
    ("2.0.0", False), ("1.2.10", False), ("unknown", False), ("2.0.0-rc.1", False), ("2.0.0-beta.0", False),
])
def test_a_build_is_the_beta_only_when_version_is_a_beta(monkeypatch, value, beta):
    version(monkeypatch, value)
    assert desktop_paths.is_beta() is beta


def test_the_beta_has_its_own_name_and_bundle_id(monkeypatch, home):
    version(monkeypatch, BETA)
    assert (desktop_paths.own_name(), desktop_paths.bundle_id()) == ("BitcoinTX Beta", "org.bitcointx.desktop.beta")
    assert desktop_paths.app_name() == "BitcoinTX Beta"
    version(monkeypatch, RELEASE)
    assert (desktop_paths.own_name(), desktop_paths.bundle_id()) == ("BitcoinTX", "org.bitcointx.desktop")
    assert desktop_paths.app_name() == "BitcoinTX"


def test_the_beta_keeps_its_data_and_log_in_folders_of_its_own(monkeypatch, home):
    version(monkeypatch, BETA)
    assert desktop_paths.data_dir() == home / "Library" / "Application Support" / "BitcoinTX Beta"
    assert desktop_paths.log_dir() == home / "Library" / "Logs" / "BitcoinTX Beta"
    assert not installed(home).exists()
    assert not (home / "Library" / "Logs" / "BitcoinTX").exists()


def test_the_release_keeps_the_installed_apps_folders(monkeypatch, home):
    version(monkeypatch, RELEASE)
    assert desktop_paths.data_dir() == installed(home)
    assert desktop_paths.log_dir() == home / "Library" / "Logs" / "BitcoinTX"


def test_a_beta_test_run_calls_itself_bitcointx_beta_test(monkeypatch, home):
    version(monkeypatch, BETA)
    monkeypatch.setenv(desktop_paths.DATA_DIR_ENV, str(home / "test-data"))
    assert desktop_paths.app_name() == "BitcoinTX Beta Test"
    assert desktop_paths.data_dir() == home / "test-data"
    assert desktop_paths.log_dir() == home / "test-data" / "logs"


def spellings(home: Path) -> list[Path]:
    """The installed app's folder, or a folder in it, however it's written."""
    real = installed(home)
    real.mkdir(parents=True)
    (home / "link").symlink_to(real)
    support = str(real.parent)
    return [real, Path(support) / "bitcointx", Path(support) / "BITCOINTX", Path(support.upper()) / "BitcoinTX",
            real / "backups", home / "link", home / "link" / "sub", Path(f"{support}/./BitcoinTX/")]


def test_the_beta_refuses_the_installed_apps_folder_however_it_is_spelled(monkeypatch, home):
    version(monkeypatch, BETA)
    for folder in spellings(home):
        monkeypatch.setenv(desktop_paths.DATA_DIR_ENV, str(folder))
        with pytest.raises(desktop_paths.InstalledAppsFolder, match="the installed BitcoinTX's"):
            desktop_paths.data_dir()
        with pytest.raises(desktop_paths.InstalledAppsFolder):
            desktop_paths.log_dir()
    assert list(installed(home).iterdir()) == []


def test_the_beta_refuses_its_own_folder_when_it_leads_to_the_installed_apps(monkeypatch, home):
    """A ~/Library/Application Support/BitcoinTX Beta that is a link to
    BitcoinTX's folder is refused too, and so is such a log folder."""
    version(monkeypatch, BETA)
    support = home / "Library" / "Application Support"
    installed(home).mkdir(parents=True)
    (support / "BitcoinTX Beta").symlink_to(installed(home))
    with pytest.raises(desktop_paths.InstalledAppsFolder):
        desktop_paths.data_dir()
    logs = home / "Library" / "Logs"
    (logs / "BitcoinTX").mkdir(parents=True)
    (logs / "BitcoinTX Beta").symlink_to(logs / "BitcoinTX")
    with pytest.raises(desktop_paths.InstalledAppsFolder):
        desktop_paths.log_dir()


def test_a_release_test_run_may_still_name_any_folder(monkeypatch, home):
    """1.x as it was: BTCTX_DESKTOP_DATA_DIR is a developer's setting, and
    desktop/run-test-build.sh refuses the installed folder itself."""
    version(monkeypatch, RELEASE)
    monkeypatch.setenv(desktop_paths.DATA_DIR_ENV, str(installed(home)))
    assert desktop_paths.data_dir() == installed(home)


def test_a_folder_beside_the_installed_one_is_fine(monkeypatch, home):
    version(monkeypatch, BETA)
    installed(home).mkdir(parents=True)
    for name in ("BitcoinTX Beta", "BitcoinTX2", "BitcoinTX-test"):
        monkeypatch.setenv(desktop_paths.DATA_DIR_ENV, str(installed(home).parent / name))
        assert desktop_paths.data_dir().name == name


def test_the_beta_answers_on_a_port_of_its_own(monkeypatch, home):
    version(monkeypatch, BETA)
    port = desktop_ports.preferred_port()
    assert port == desktop_ports.BETA_PORT
    assert port not in (8765, 8766)  # the installed app's; desktop/run-test-build.sh's
    version(monkeypatch, RELEASE)
    assert desktop_ports.preferred_port() == 8765
    monkeypatch.setenv("BTCTX_DESKTOP_PORT", "8800")
    assert desktop_ports.preferred_port() == 8800


@pytest.mark.parametrize("value, app_id", [(BETA, "org.bitcointx.desktop.beta"), (RELEASE, "org.bitcointx.desktop")])
def test_a_second_launch_brings_forward_its_own_app_by_bundle_id(monkeypatch, home, value, app_id):
    """By name, "BitcoinTX" would bring forward, or start, the installed app
    on its real ledger when the beta is opened twice."""
    version(monkeypatch, value)
    scripts = []
    monkeypatch.setattr(desktop_ports.sys, "platform", "darwin")
    monkeypatch.setattr(desktop_ports, "_osascript", lambda s: scripts.append(s) or "")
    desktop_ports.tell_already_running(desktop_ports.preferred_port())
    assert scripts[0] == f'tell application id "{app_id}" to activate'
    assert not any('application "BitcoinTX"' in s for s in scripts)


def test_a_refusal_is_told_in_a_dialog_with_its_words_quoted(monkeypatch, home):
    version(monkeypatch, BETA)
    scripts = []
    monkeypatch.setattr(desktop_ports.sys, "platform", "darwin")
    monkeypatch.setattr(desktop_ports, "_osascript", lambda s: scripts.append(s) or "")
    desktop_ports.tell_refused('refusing /Users/a "b"\\c')
    assert 'display dialog "refusing /Users/a \\"b\\"\\\\c" with title "BitcoinTX Beta"' in scripts[0]
    assert "with icon stop" in scripts[0]


# The build: the spec, build-mac.sh, run-test-build.sh and the entry point

SPEC = (DESKTOP / "BitcoinTX.spec").read_text()


def test_the_spec_takes_the_apps_name_and_id_from_desktop_paths():
    assert "from desktop_paths import bundle_id, own_name" in SPEC
    assert 'name=f"{APP_NAME}.app"' in SPEC
    assert "bundle_identifier=APP_ID" in SPEC
    assert '"CFBundleName": APP_NAME' in SPEC and '"CFBundleDisplayName": APP_NAME' in SPEC
    assert '"CFBundleIdentifier": APP_ID' in SPEC
    # the executable keeps its name: desktop/run-test-build.sh runs Contents/MacOS/BitcoinTX
    assert re.search(r'exe = EXE\((?:.|\n)*?name="BitcoinTX",', SPEC)
    for fixed in ('"BitcoinTX.app"', '"org.bitcointx.desktop"'):
        assert fixed not in SPEC, fixed


def test_the_build_script_finds_the_app_the_spec_made():
    build = (DESKTOP / "build-mac.sh").read_text()
    assert "dist/BitcoinTX.app" not in build
    assert 'rm -rf "$SCRIPT_DIR/dist"' in build  # one app in dist, the one just built


def test_a_test_run_takes_the_one_app_built_and_refuses_either_installed_folder():
    script = (DESKTOP / "run-test-build.sh").read_text()
    assert 'APP="$ROOT/desktop/dist/BitcoinTX.app"' not in script
    assert '"$HOME/Library/Application Support/BitcoinTX Beta"' in script


def test_the_entry_point_refuses_before_it_opens_anything():
    entry = (DESKTOP / "entrypoint.py").read_text()
    main = entry[entry.index("def main():"):]
    refused = main.index("except InstalledAppsFolder as exc:")
    assert main.index("app_support = data_dir()") < refused < main.index('os.environ["DATABASE_FILE"]')
    assert "tell_refused(str(exc))" in main[refused:refused + 200]
    logging = entry[entry.index("def setup_logging"):entry.index("def get_resource_path")]
    assert "except (OSError, InstalledAppsFolder)" in logging


def test_the_desktop_modules_stay_importable_without_pywebview():
    """desktop_paths now reads VERSION through backend.version: still nothing
    from pywebview, so these tests run on any OS."""
    for module in (desktop_paths, desktop_ports):
        assert not re.search(r"^\s*(import|from) webview", Path(module.__file__).read_text(), re.M)
    assert desktop_paths.app_version.__module__ == "backend.version"


def test_the_setup_code_is_looked_for_in_the_beta_apps_folder(monkeypatch):
    """The login page's hint, when the Mac app's window can't fill the code in
    (its address in a browser): BitcoinTX Beta's folder, never BitcoinTX's."""
    from backend.services import first_run

    monkeypatch.setattr(first_run, "is_desktop", lambda: True)
    monkeypatch.setattr(first_run, "app_version", lambda: BETA)
    assert "(~/Library/Application Support/BitcoinTX Beta)" in first_run.code_refused(None)
    monkeypatch.setattr(first_run, "app_version", lambda: RELEASE)
    assert "(~/Library/Application Support/BitcoinTX)" in first_run.code_refused(None)
