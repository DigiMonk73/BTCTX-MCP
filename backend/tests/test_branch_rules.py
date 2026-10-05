"""
backend/tests/test_branch_rules.py

The pre-push branch rules (.githooks/branch-rules.sh, AGENTS.md "Branches"):
main only fast-forwards to commits already on develop and is never deleted,
rewound or force-pushed. Other AI assistants work in this repo too, so the
rule is enforced, not just written down.

History in a temp repo: A (main) -> B (develop); C branches off A (not on
develop). Each case feeds the script the line git gives pre-push.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / ".githooks" / "branch-rules.sh"
ZERO = "0" * 40

pytestmark = pytest.mark.skipif(
    not (shutil.which("git") and shutil.which("bash")), reason="needs git and bash"
)


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    path = tmp_path_factory.mktemp("branches")
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

    def git(*args):
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
            cwd=path, env=env, check=True, capture_output=True, text=True,
        ).stdout.strip()

    git("init", "-q", "-b", "main")
    git("commit", "-q", "--allow-empty", "-m", "A")
    a = git("rev-parse", "HEAD")
    git("checkout", "-q", "-b", "develop")
    git("commit", "-q", "--allow-empty", "-m", "B")
    b = git("rev-parse", "HEAD")
    git("checkout", "-q", "-b", "other", a)
    git("commit", "-q", "--allow-empty", "-m", "C")
    c = git("rev-parse", "HEAD")
    return path, env, {"A": a, "B": b, "C": c, "0": ZERO}


def push(repo, *lines):
    path, env, sha = repo
    stdin = "".join(
        f"{ref} {sha[local]} {ref} {sha[remote]}\n" for ref, local, remote in lines
    )
    return subprocess.run(
        ["bash", str(SCRIPT)], cwd=path, env=env, input=stdin, capture_output=True, text=True
    )


@pytest.mark.parametrize(
    "lines",
    [
        [("refs/heads/main", "B", "A")],       # fast-forward to develop
        [("refs/heads/main", "B", "0")],       # main created at a develop commit
        [("refs/heads/develop", "B", "A")],    # other branches aren't checked
        [("refs/heads/develop", "C", "B")],
        [],                                    # make check-fast: no refs
    ],
)
def test_allowed(repo, lines):
    assert push(repo, *lines).returncode == 0


@pytest.mark.parametrize(
    "lines, message",
    [
        ([("refs/heads/main", "C", "A")], "only takes commits already on develop"),
        ([("refs/heads/develop", "B", "A"), ("refs/heads/main", "C", "A")],
         "only takes commits already on develop"),
        ([("refs/heads/main", "0", "A")], "can't be deleted"),
        ([("refs/heads/main", "A", "B")], "can't be rewound or force-pushed"),
    ],
)
def test_refused(repo, lines, message):
    result = push(repo, *lines)
    assert result.returncode != 0
    assert message in result.stderr
