"""
desktop/build-mac.sh says how to test the build it made with
desktop/run-test-build.sh, which runs it on its own data folder and port
(#679). Opening the app itself runs it on the installed app's data folder,
the owner's real ledger on their own Mac: AGENTS.md runs a Mac build only
with run-test-build.sh.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD_MAC = (ROOT / "desktop" / "build-mac.sh").read_text()


def to_test_lines() -> str:
    """The script's own "To test" lines, as it prints them for an app in desktop/dist."""
    lines = BUILD_MAC.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip().startswith('echo "To test'))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == 'echo ""')
    script = "\n".join(lines[start:end])
    env = {"SCRIPT_DIR": str(ROOT / "desktop"), "APP_PATH": str(ROOT / "desktop" / "dist" / "BitcoinTX.app"),
           "PATH": "/usr/bin:/bin"}
    return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, check=True).stdout


def test_it_says_to_test_the_build_with_run_test_build():
    printed = to_test_lines().splitlines()
    command = printed[1].split()[0]
    assert Path(command) == ROOT / "desktop" / "run-test-build.sh"
    assert Path(command).is_file()


def test_it_never_suggests_opening_the_app():
    printed = to_test_lines()
    assert "open " not in printed and "BitcoinTX.app" not in printed
