"""
The Mac pre-release app, "BitcoinTX Preview" (2.0 plan 7.4, B10a, point 2;
#532; #251's decision 28: one app for every alpha and beta).

A build is BitcoinTX Preview when VERSION has a pre-release suffix
(2.0.0-alpha.N or 2.0.0-beta.N), and the ordinary app otherwise, so 2.0.0
builds BitcoinTX with no edit. The Preview is installed beside BitcoinTX,
never in its place: its own name and
bundle id, its own data and log folders, its own port. So a tester's real
ledger is never opened or upgraded, and like desktop/run-test-build.sh it
refuses the installed app's folder however that is spelled.

desktop/run-test-build.sh sets its own folder and port, so a run through it
can't show these defaults: these tests do (7.4's "Done when").
"""

import os
import re
import sys
from pathlib import Path

import pytest

DESKTOP = Path(__file__).resolve().parents[2] / "desktop"
sys.path.insert(0, str(DESKTOP))
import desktop_paths  # noqa: E402
import desktop_ports  # noqa: E402

BETA, ALPHA, RELEASE = "2.0.0-beta.1", "2.0.0-alpha.1", "2.0.0"


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


@pytest.mark.parametrize("value, preview", [
    ("2.0.0-beta.1", True), ("2.0.0-beta.12", True), ("2.0.0-alpha.1", True), ("2.0.0-alpha.7", True),
    ("2.0.0", False), ("1.2.10", False), ("unknown", False), ("2.0.0-rc.1", False), ("2.0.0-beta.0", False),
    ("2.0.0-alpha.0", False), ("2.0.0b1", False),
])
def test_a_build_is_the_preview_only_when_version_is_an_alpha_or_a_beta(monkeypatch, value, preview):
    version(monkeypatch, value)
    assert desktop_paths.is_preview() is preview


@pytest.mark.parametrize("value", [ALPHA, BETA])
def test_every_alpha_and_beta_is_one_app_with_its_own_name_and_bundle_id(monkeypatch, home, value):
    version(monkeypatch, value)
    assert (desktop_paths.own_name(), desktop_paths.bundle_id()) == ("BitcoinTX Preview", "org.bitcointx.desktop.preview")
    assert desktop_paths.app_name() == "BitcoinTX Preview"
    version(monkeypatch, RELEASE)
    assert (desktop_paths.own_name(), desktop_paths.bundle_id()) == ("BitcoinTX", "org.bitcointx.desktop")
    assert desktop_paths.app_name() == "BitcoinTX"


@pytest.mark.parametrize("value", [ALPHA, BETA])
def test_the_preview_keeps_its_data_and_log_in_folders_of_its_own(monkeypatch, home, value):
    """The same folders for an alpha and a beta: a tester's test ledger carries over."""
    version(monkeypatch, value)
    assert desktop_paths.data_dir() == home / "Library" / "Application Support" / "BitcoinTX Preview"
    assert desktop_paths.log_dir() == home / "Library" / "Logs" / "BitcoinTX Preview"
    assert not installed(home).exists()
    assert not (home / "Library" / "Logs" / "BitcoinTX").exists()


def test_the_release_keeps_the_installed_apps_folders(monkeypatch, home):
    version(monkeypatch, RELEASE)
    assert desktop_paths.data_dir() == installed(home)
    assert desktop_paths.log_dir() == home / "Library" / "Logs" / "BitcoinTX"


def test_a_preview_test_run_calls_itself_bitcointx_preview_test(monkeypatch, home):
    version(monkeypatch, BETA)
    monkeypatch.setenv(desktop_paths.DATA_DIR_ENV, str(home / "test-data"))
    assert desktop_paths.app_name() == "BitcoinTX Preview Test"
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


@pytest.mark.parametrize("value", [ALPHA, BETA])
def test_the_preview_refuses_the_installed_apps_folder_however_it_is_spelled(monkeypatch, home, value):
    version(monkeypatch, value)
    for folder in spellings(home):
        monkeypatch.setenv(desktop_paths.DATA_DIR_ENV, str(folder))
        with pytest.raises(desktop_paths.InstalledAppsFolder, match="the installed BitcoinTX's"):
            desktop_paths.data_dir()
        with pytest.raises(desktop_paths.InstalledAppsFolder):
            desktop_paths.log_dir()
    assert list(installed(home).iterdir()) == []


def test_the_preview_refuses_its_own_folder_when_it_leads_to_the_installed_apps(monkeypatch, home):
    """A ~/Library/Application Support/BitcoinTX Preview that is a link to
    BitcoinTX's folder is refused too, and so is such a log folder."""
    version(monkeypatch, BETA)
    support = home / "Library" / "Application Support"
    installed(home).mkdir(parents=True)
    (support / "BitcoinTX Preview").symlink_to(installed(home))
    with pytest.raises(desktop_paths.InstalledAppsFolder):
        desktop_paths.data_dir()
    logs = home / "Library" / "Logs"
    (logs / "BitcoinTX").mkdir(parents=True)
    (logs / "BitcoinTX Preview").symlink_to(logs / "BitcoinTX")
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
    for name in ("BitcoinTX Preview", "BitcoinTX2", "BitcoinTX-test"):
        monkeypatch.setenv(desktop_paths.DATA_DIR_ENV, str(installed(home).parent / name))
        assert desktop_paths.data_dir().name == name


def test_the_preview_answers_on_a_port_of_its_own(monkeypatch, home):
    for value in (ALPHA, BETA):
        version(monkeypatch, value)
        port = desktop_ports.preferred_port()
        assert port == desktop_ports.PREVIEW_PORT
        assert port not in (8765, 8766)  # the installed app's; desktop/run-test-build.sh's
    version(monkeypatch, RELEASE)
    assert desktop_ports.preferred_port() == 8765
    monkeypatch.setenv("BTCTX_DESKTOP_PORT", "8800")
    assert desktop_ports.preferred_port() == 8800


@pytest.mark.parametrize("value, app_id", [(BETA, "org.bitcointx.desktop.preview"), (ALPHA, "org.bitcointx.desktop.preview"),
                                           (RELEASE, "org.bitcointx.desktop")])
def test_a_second_launch_brings_forward_its_own_app_by_bundle_id(monkeypatch, home, value, app_id):
    """By name, "BitcoinTX" would bring forward, or start, the installed app
    on its real ledger when the Preview is opened twice."""
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
    assert 'display dialog "refusing /Users/a \\"b\\"\\\\c" with title "BitcoinTX Preview"' in scripts[0]
    assert "with icon stop" in scripts[0]


# The build: the spec, build-mac.sh, run-test-build.sh and the entry point

SPEC = (DESKTOP / "BitcoinTX.spec").read_text()


def test_the_spec_takes_the_apps_name_and_id_from_desktop_paths():
    assert "from desktop_paths import bundle_id, icon_name, own_name" in SPEC
    assert 'name=f"{APP_NAME}.app"' in SPEC
    assert "bundle_identifier=APP_ID" in SPEC
    assert '"CFBundleName": APP_NAME' in SPEC and '"CFBundleDisplayName": APP_NAME' in SPEC
    assert '"CFBundleIdentifier": APP_ID' in SPEC
    # the executable is named after the app too (#670): desktop/run-test-build.sh
    # and scripts/mac-app.sh run the one its bundle names
    assert re.search(r"exe = EXE\((?:.|\n)*?name=APP_NAME,", SPEC)
    for fixed in ('"BitcoinTX.app"', '"org.bitcointx.desktop"'):
        assert fixed not in SPEC, fixed


def test_the_build_script_finds_the_app_the_spec_made():
    build = (DESKTOP / "build-mac.sh").read_text()
    assert "dist/BitcoinTX.app" not in build
    assert 'rm -rf "$SCRIPT_DIR/dist"' in build  # one app in dist, the one just built


def test_a_test_run_takes_the_one_app_built_and_refuses_either_installed_folder():
    script = (DESKTOP / "run-test-build.sh").read_text()
    assert 'APP="$ROOT/desktop/dist/BitcoinTX.app"' not in script
    assert '"$HOME/Library/Application Support/BitcoinTX Preview"' in script


# The entry point, run in a process of its own: a stand-in for pywebview, a
# test home, VERSION read as an alpha's, macOS's path through its logging
# (also on CI's Linux), and the refusal's dialog written down instead of
# shown. Any other dialog, a look at a port or a socket fails the run: it
# starts nothing before it refuses, and imports nothing of the backend.
# Played as macOS, urllib.request asks macOS's own _scproxy module for the
# system's proxies when it's imported; Linux has none, so a stand-in that
# knows no proxy takes its place on every machine, the Mac's too, and the
# run is the same everywhere.
ENTRY = """
import os, sys
sys.path[:0] = [{root!r}, {desktop!r}]
import backend.version
backend.version.app_version = lambda: "2.0.0-alpha.1"
sys.modules["webview"] = type(sys)("webview")
scproxy = type(sys)("_scproxy")
scproxy._get_proxies = lambda: {{}}
scproxy._get_proxy_settings = lambda: {{"exclude_simple": False, "exceptions": ()}}
sys.modules["_scproxy"] = scproxy
sys.platform = "darwin"
import desktop_ports
def never(*args, **kwargs):
    raise SystemExit("it went past the refusal")
desktop_ports._osascript = desktop_ports.running_instance = desktop_ports.choose_socket = never
import entrypoint
entrypoint.running_instance = entrypoint.choose_socket = never
told = []
entrypoint.tell_refused = told.append
entrypoint.main()
print("TOLD", told)
print("DATABASE_FILE" in os.environ, any(m.startswith("backend.main") for m in sys.modules))
"""


@pytest.mark.parametrize("given", ["Application Support/BitcoinTX", "Application Support/BitcoinTX/sub"])
def test_the_preview_given_the_installed_apps_folder_says_so_and_opens_nothing(tmp_path, given):
    """Its log too would be in that folder: the log is left out, the app
    starts no further, and the dialog says why (a crash at import said nothing)."""
    import subprocess

    home = tmp_path / "home"
    installed = home / "Library" / "Application Support" / "BitcoinTX"
    installed.mkdir(parents=True)
    script = ENTRY.format(root=str(DESKTOP.parent), desktop=str(DESKTOP))
    made = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60, env={
        **os.environ, "HOME": str(home), desktop_paths.DATA_DIR_ENV: str(home / "Library" / given)})
    assert made.returncode == 0, made.stderr
    told, opened = made.stdout.strip().splitlines()[-2:]
    assert "BitcoinTX Preview won't use" in told and "the installed BitcoinTX's" in told
    assert opened == "False False"  # no database named, no backend imported
    assert list(installed.iterdir()) == []


def test_the_desktop_modules_stay_importable_without_pywebview():
    """desktop_paths now reads VERSION through backend.version: still nothing
    from pywebview, so these tests run on any OS."""
    for module in (desktop_paths, desktop_ports):
        assert not re.search(r"^\s*(import|from) webview", Path(module.__file__).read_text(), re.M)
    assert desktop_paths.app_version.__module__ == "backend.version"


def test_the_setup_code_is_looked_for_in_the_preview_apps_folder(monkeypatch):
    """The login page's hint, when the Mac app's window can't fill the code in
    (its address in a browser): BitcoinTX Preview's folder, never BitcoinTX's."""
    from backend.services import first_run

    monkeypatch.setattr(first_run, "is_desktop", lambda: True)
    for value in (ALPHA, BETA):
        monkeypatch.setattr(first_run, "app_version", lambda value=value: value)
        assert "(~/Library/Application Support/BitcoinTX Preview)" in first_run.code_refused(None)
    monkeypatch.setattr(first_run, "app_version", lambda: RELEASE)
    assert "(~/Library/Application Support/BitcoinTX)" in first_run.code_refused(None)
