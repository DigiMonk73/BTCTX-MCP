"""
scripts/sync-check.sh, run against throwaway repositories and a stand-in
`gh` (no network). The owner asked (2026-10-06) for a way to know that
nothing exists only on this computer: every session runs it at its start
and end (AGENTS.md).
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "sync-check.sh"

# Merged pull requests: lines "<branch> <number> <head sha>" in $FAKE_PRS.
FAKE_GH = """#!/bin/sh
head=""
while [ $# -gt 0 ]; do [ "$1" = --head ] && head="$2"; shift; done
[ -f "$FAKE_PRS" ] && awk -v b="$head" '$1 == b {print $2 " " $3}' "$FAKE_PRS"
exit 0
"""

pytestmark = pytest.mark.skipif(
    not (shutil.which("git") and shutil.which("bash")), reason="needs git and bash"
)


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repos(tmp_path, monkeypatch):
    """origin (bare, main and develop) and proj, a clone with the script committed."""
    for key, value in {
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
        "FAKE_PRS": str(tmp_path / "prs.txt"),
    }.items():
        monkeypatch.setenv(key, value)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text(FAKE_GH)
    (bin_dir / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    seed = tmp_path / "seed"
    (seed / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, seed / "scripts" / "sync-check.sh")
    (seed / "app.txt").write_text("one\n")
    git(tmp_path, "init", "-q", "-b", "main", str(seed))
    git(seed, "add", "-A")
    git(seed, "commit", "-qm", "start")
    git(seed, "branch", "develop")
    origin = tmp_path / "origin.git"
    git(tmp_path, "clone", "-q", "--bare", str(seed), str(origin))

    proj = tmp_path / "proj"
    git(tmp_path, "clone", "-q", str(origin), str(proj))
    git(proj, "branch", "-q", "develop", "origin/develop")
    return proj, seed


def run(proj, *args):
    return subprocess.run(
        ["bash", str(proj / "scripts" / "sync-check.sh"), *args], capture_output=True, text=True
    )


def push_from_seed(seed, branch, text):
    git(seed, "switch", "-q", branch)
    (seed / "app.txt").write_text(text)
    git(seed, "commit", "-qam", text)
    git(seed, "push", "-q", str(seed.parent / "origin.git"), branch)


def test_a_fresh_clone_is_in_sync(repos):
    proj, _ = repos
    r = run(proj)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "IN SYNC" in r.stdout and "NOT IN SYNC" not in r.stdout


def test_work_not_committed_is_reported(repos):
    proj, _ = repos
    (proj / "app.txt").write_text("changed\n")
    r = run(proj)
    assert r.returncode == 1
    assert "NOT IN SYNC" in r.stdout and str(proj) in r.stdout


def test_work_not_committed_in_a_worktree_is_reported(repos, tmp_path):
    proj, _ = repos
    wt = tmp_path / "wt"
    git(proj, "worktree", "add", "-q", "-b", "side", str(wt), "origin/main")
    (wt / "notes.txt").write_text("only here\n")
    r = run(proj)
    assert r.returncode == 1 and f"{wt} has work not committed" in r.stdout


def test_a_symlink_is_not_work(repos):
    """A worktree's node_modules link to the main checkout's."""
    proj, _ = repos
    (proj / "node_modules").symlink_to(proj.parent)
    assert run(proj).returncode == 0


def test_commits_not_pushed_are_reported(repos):
    proj, _ = repos
    git(proj, "switch", "-qc", "feature")
    (proj / "app.txt").write_text("feature\n")
    git(proj, "commit", "-qam", "feature")
    git(proj, "switch", "-q", "main")
    r = run(proj)
    assert r.returncode == 1 and "branch feature has commits GitHub doesn't" in r.stdout


def test_a_merged_pull_request_counts_as_on_github_and_tidy_deletes_it(repos, tmp_path):
    """GitHub deletes a branch after its squash merge: its commits are in the pull request."""
    proj, _ = repos
    git(proj, "switch", "-qc", "done")
    (proj / "app.txt").write_text("done\n")
    git(proj, "commit", "-qam", "done")
    git(proj, "switch", "-q", "main")
    (tmp_path / "prs.txt").write_text(f"done 7 {git(proj, 'rev-parse', 'done')}\n")
    r = run(proj)
    assert r.returncode == 0, r.stdout
    assert "1 are on GitHub already and could go" in r.stdout
    r = run(proj, "--tidy")
    assert r.returncode == 0 and "Deleted 1" in r.stdout
    assert git(proj, "branch", "--list", "done") == ""


def test_tidy_keeps_a_branch_a_working_folder_has_checked_out(repos):
    proj, _ = repos
    git(proj, "push", "-q", "origin", "main:pushed")
    git(proj, "switch", "-qc", "pushed", "origin/pushed")
    run(proj, "--tidy")
    assert git(proj, "branch", "--list", "pushed") != ""


def test_develop_behind_github_is_brought_down(repos):
    proj, seed = repos
    push_from_seed(seed, "develop", "newer\n")
    r = run(proj)
    assert "develop: brought 1 commit(s) down" in r.stdout
    assert git(proj, "rev-parse", "develop") == git(proj, "rev-parse", "origin/develop")


def test_main_with_local_commits_is_reported(repos):
    proj, _ = repos
    (proj / "app.txt").write_text("on main\n")
    git(proj, "commit", "-qam", "on main")
    r = run(proj)
    assert r.returncode == 1 and "local main has 1 commit(s) GitHub doesn't" in r.stdout


def test_a_stash_is_reported(repos):
    proj, _ = repos
    (proj / "app.txt").write_text("stashed\n")
    git(proj, "stash", "-q")
    r = run(proj)
    assert r.returncode == 1 and "1 stash(es)" in r.stdout
