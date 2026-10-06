"""
scripts/start9-pull.sh, run against local repositories and a stand-in `gh`
(no network). Once Start9 forks the mirror, the release workflow runs
`--check` and stops a release that would undo Start9's changes to their fork,
and the mirror job uses `--fork` to find the fork for the pull-request
reminder (owner's request, 2026-09-29: "a way not to forget").
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "start9-pull.sh"

FAKE_GH = """#!/bin/sh
case "$1 $2" in
  "pr list") printf '%s' "$FAKE_PR" ;;
  "api repos/"*/forks) printf '%s' "$FAKE_FORKS"; exit "${FAKE_API_EXIT:-0}" ;;
  "api repos/"*) echo "${FAKE_BRANCH:-main}" ;;
esac
"""


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repos(tmp_path, monkeypatch):
    """proj (BTCTX-MCP with startos/), mirror (startos/ at its root), fork (a clone of the mirror)."""
    for key, value in {
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    }.items():
        monkeypatch.setenv(key, value)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text(FAKE_GH)
    (bin_dir / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    for var in ("START9_FORK", "START9_BRANCH", "FAKE_PR", "FAKE_FORKS", "FAKE_API_EXIT"):
        monkeypatch.delenv(var, raising=False)

    proj = tmp_path / "proj"
    (proj / "scripts").mkdir(parents=True)
    (proj / "startos").mkdir()
    shutil.copy(SCRIPT, proj / "scripts" / "start9-pull.sh")
    (proj / "startos" / "main.ts").write_text("one\ntwo\n")
    git(tmp_path, "init", "-q", "-b", "develop", str(proj))
    git(proj, "add", "-A")
    git(proj, "commit", "-qm", "package")

    mirror = tmp_path / "mirror"
    git(tmp_path, "init", "-q", "-b", "main", str(mirror))
    (mirror / "main.ts").write_text("one\ntwo\n")
    git(mirror, "add", "-A")
    git(mirror, "commit", "-qm", "sync")

    fork = tmp_path / "fork"
    git(tmp_path, "clone", "-q", str(mirror), str(fork))
    monkeypatch.setenv("MIRROR_URL", str(mirror))
    monkeypatch.setenv("FORK_URL", str(fork))
    return proj, fork


def run(proj, *args, **env):
    return subprocess.run(
        ["bash", str(proj / "scripts" / "start9-pull.sh"), *args],
        capture_output=True, text=True, env={**os.environ, **env},
    )


def start9_changes(fork):
    (fork / "main.ts").write_text("one\ntwo, as Start9 wants it\n")
    git(fork, "commit", "-qam", "Start9's review fix")


FORKED = {"START9_FORK": "Start9-Community/BTCTX-StartOS", "START9_BRANCH": "main"}


def test_check_passes_before_start9_forks(repos):
    proj, _ = repos
    r = run(proj, "--check")
    assert r.returncode == 0 and "hasn't forked" in r.stdout


def test_check_passes_when_the_fork_matches_the_mirror(repos):
    proj, _ = repos
    r = run(proj, "--check", **FORKED)
    assert r.returncode == 0 and "nothing to take" in r.stdout


def test_check_stops_a_release_that_would_undo_start9s_changes(repos):
    proj, fork = repos
    start9_changes(fork)
    r = run(proj, "--check", **FORKED)
    assert r.returncode == 1
    assert "scripts/start9-pull.sh --apply" in r.stderr


def test_check_passes_once_their_changes_are_committed_in_startos(repos):
    proj, fork = repos
    start9_changes(fork)
    (proj / "startos" / "main.ts").write_text("one\ntwo, as Start9 wants it\n")
    assert run(proj, "--check", **FORKED).returncode == 1, "uncommitted changes don't count: the release builds HEAD"
    git(proj, "commit", "-qam", "Take Start9's changes")
    r = run(proj, "--check", **FORKED)
    assert r.returncode == 0 and "are in startos/" in r.stdout


def test_check_warns_but_passes_while_our_pull_request_is_open(repos):
    proj, fork = repos
    start9_changes(fork)
    r = run(proj, "--check", FAKE_PR="#3 BitcoinTX v1.2.3", **FORKED)
    assert r.returncode == 0 and "still open" in r.stdout


def test_check_fails_when_the_forks_cant_be_listed(repos):
    proj, _ = repos
    r = run(proj, "--check", FAKE_API_EXIT="1")
    assert r.returncode == 1, "a release must not pass the check just because GitHub didn't answer"


def test_fork_finds_start9s_fork_and_its_default_branch(repos):
    proj, _ = repos
    r = run(proj, "--fork", FAKE_FORKS="Start9-Community/btctx-startos\n", FAKE_BRANCH="master")
    assert r.returncode == 0 and r.stdout.strip() == "Start9-Community/btctx-startos master"
    assert run(proj, "--fork").stdout == "", "nothing before the fork exists"


def test_apply_brings_their_changes_into_startos(repos):
    proj, fork = repos
    start9_changes(fork)
    r = run(proj, "--apply", **FORKED)
    assert r.returncode == 0, r.stderr
    assert (proj / "startos" / "main.ts").read_text() == "one\ntwo, as Start9 wants it\n"


def test_apply_runs_on_a_branch_cut_from_develop(repos):
    """develop takes changes only by pull request, so --apply runs on a branch."""
    proj, fork = repos
    start9_changes(fork)
    git(proj, "switch", "-qc", "start9-changes")
    r = run(proj, "--apply", **FORKED)
    assert r.returncode == 0, r.stderr
    assert (proj / "startos" / "main.ts").read_text() == "one\ntwo, as Start9 wants it\n"
    assert "pull request" in r.stdout


def test_apply_is_refused_on_main(repos):
    proj, fork = repos
    start9_changes(fork)
    git(proj, "switch", "-qc", "main")
    r = run(proj, "--apply", **FORKED)
    assert r.returncode == 1 and "on main" in r.stderr
    assert (proj / "startos" / "main.ts").read_text() == "one\ntwo\n"
