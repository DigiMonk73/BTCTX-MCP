"""
desktop/build-mac.sh says how to test the build it made with
desktop/run-test-build.sh, which runs it on its own data folder and port
(#679). Opening the app itself runs it on the installed app's data folder,
the owner's real ledger on their own Mac: AGENTS.md runs a Mac build only
with run-test-build.sh.
"""

import re
import shlex
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILD_MAC = (ROOT / "desktop" / "build-mac.sh").read_text()


def to_test_lines(script: str = BUILD_MAC) -> str:
    """The script's "To test" lines as it prints them for an app in
    desktop/dist, run with the shell's builtins only (a restricted bash, no
    PATH): a command written there instead of a line printed, an "open" of
    the build say, is refused, never run on a machine that has a build."""
    lines = script.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip().startswith('echo "To test'))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == 'echo ""')
    block = "set -e\n" + "\n".join(lines[start:end])
    env = {"SCRIPT_DIR": str(ROOT / "desktop"), "APP_PATH": str(ROOT / "desktop" / "dist" / "BitcoinTX.app"),
           "PATH": "/nonexistent"}
    return subprocess.run(["/bin/bash", "-r", "-c", block], env=env, capture_output=True, text=True,
                          check=True).stdout


def test_it_says_to_test_the_build_with_run_test_build():
    command = shlex.split(to_test_lines().splitlines()[1])[0]
    assert Path(command) == ROOT / "desktop" / "run-test-build.sh"
    assert Path(command).is_file()


def test_it_never_suggests_opening_the_app():
    printed = to_test_lines()
    assert ".app" not in printed and not re.search(r"\bopen\b", printed)


def test_a_command_in_those_lines_is_refused_never_run():
    opened = re.sub(r'(echo "To test[^\n]*\n)', r'\1    open "$APP_PATH"\n', BUILD_MAC, count=1)
    assert opened != BUILD_MAC
    with pytest.raises(subprocess.CalledProcessError, match="returned non-zero"):
        to_test_lines(opened)
