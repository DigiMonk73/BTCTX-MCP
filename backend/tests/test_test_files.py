"""
How the test files are run (#272): by pytest only. A file that also ran
on its own had a second copy of conftest.py's setup (stubbed prices, temp
folders for the setup code, the price files and the draft forms), which
drifted: run directly, every such runner failed, and some wrote
setup-code.txt into backend/. pre_commit_tests.py isn't a test file
(no test_ prefix): CI and the pre-push hook run it as a script.
"""

import ast
import shutil
import subprocess
from pathlib import Path

import pytest

TESTS = Path(__file__).parent
REPO = TESTS.parent.parent


def _runs_on_its_own(source: str) -> bool:
    """Whether the code compares __name__ with anything (`if __name__ ==
    "__main__":`, however it's spaced or turned), read from the parsed code,
    so the words in a docstring don't count."""
    return any(
        isinstance(node, ast.Compare)
        and any(isinstance(side, ast.Name) and side.id == "__name__" for side in [node.left, *node.comparators])
        for node in ast.walk(ast.parse(source))
    )


@pytest.mark.parametrize("source, runs", [
    ('if __name__ == "__main__":\n    main()\n', True),
    ("if __name__=='__main__':\n    main()\n", True),
    ('if "__main__" == __name__ :\n    main()\n', True),
    ('if (__name__ == "__main__"):\n    main()\n', True),
    ('"""Never: if __name__ == "__main__": main()"""\n', False),
])
def test_a_runner_is_found_however_it_is_written(source, runs):
    assert _runs_on_its_own(source) is runs


def test_no_test_file_runs_on_its_own():
    runners = [f.name for f in sorted(TESTS.glob("test_*.py")) if _runs_on_its_own(f.read_text())]
    assert runners == []


def _ignored_by(path: str) -> str | None:
    """The ignore rule's source ("<file>:<line>:<pattern>") that matches
    `path`, or None."""
    found = subprocess.run(["git", "check-ignore", "-v", "--no-index", path], cwd=REPO, capture_output=True, text=True)
    return found.stdout.split("\t")[0] if found.returncode == 0 else None


def _in_a_checkout() -> bool:
    return shutil.which("git") is not None and subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"], cwd=REPO, capture_output=True).returncode == 0


needs_a_checkout = pytest.mark.skipif(not _in_a_checkout(), reason="needs a git checkout")


@needs_a_checkout
@pytest.mark.parametrize("path", ["backend/setup-code.txt", "setup-code.txt", "backend/.btctx_secret_key", "a.orig"])
def test_files_a_run_from_source_leaves_are_ignored(path):
    """A server run from the checkout writes its setup code and secret key
    next to its database (backend/), and a merge may leave *.orig files:
    the repository's own .gitignore ignores them (not a developer's global
    excludes), so git never offers to commit them."""
    assert (_ignored_by(path) or "").startswith(".gitignore:"), f"{path} isn't ignored by .gitignore"


@needs_a_checkout
def test_gitignore_itself_is_not_ignored():
    assert _ignored_by(".gitignore") is None
