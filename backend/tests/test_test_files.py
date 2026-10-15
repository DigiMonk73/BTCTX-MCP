"""
How the test files are run (#272): by pytest only. A file that also ran
on its own had a second copy of conftest.py's setup (stubbed prices, temp
folders for the setup code, the price files and the draft forms), which
drifted: run directly, every such runner failed, and some wrote
setup-code.txt into backend/. pre_commit_tests.py isn't a test file
(no test_ prefix): CI and the pre-push hook run it as a script.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

TESTS = Path(__file__).parent
REPO = TESTS.parent.parent


RUNNER = re.compile(r"^if __name__ == .__main__.:", re.MULTILINE)


def test_no_test_file_runs_on_its_own():
    runners = [f.name for f in sorted(TESTS.glob("test_*.py")) if RUNNER.search(f.read_text())]
    assert runners == []


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
@pytest.mark.parametrize("path", ["backend/setup-code.txt", "setup-code.txt", "backend/.btctx_secret_key", "a.orig"])
def test_files_a_run_from_source_leaves_are_ignored(path):
    """A server run from the checkout writes its setup code and secret key
    next to its database (backend/), and a merge may leave *.orig files:
    git never offers to commit them."""
    ignored = subprocess.run(["git", "check-ignore", "--no-index", "-q", path], cwd=REPO)
    assert ignored.returncode == 0, f"{path} isn't ignored"


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_gitignore_itself_is_not_ignored():
    assert subprocess.run(["git", "check-ignore", "--no-index", "-q", ".gitignore"], cwd=REPO).returncode == 1
