"""
scripts/catch-up-2.0.sh: develop into the 2.0 build (AGENTS.md, "Branches").

In throwaway repositories (an origin with develop and 2.0, and a clone)
and with a fake gh that records what it was asked: nothing to do; develop's
new commits get one pull request from develop with auto-merge as a merge
commit, or the open one is named; a 1.x migration or a conflict stops for
the lead with nothing opened; a new 1.x release and changes to startos/ are
listed as to-dos beside the pull request.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "catch-up-2.0.sh"
FAKE_GH = """#!/bin/sh
echo "$*" >> "$GH_CALLS"
case "$1 $2" in
  "pr list") [ -n "$FAKE_OPEN" ] && echo "$FAKE_OPEN"; exit 0 ;;
  "pr create") echo "https://github.com/o/r/pull/700"; exit 0 ;;
esac
exit 0
"""
FIXTURE_SCRIPT = 'RELEASE = "v1.2.9"\n'

pytestmark = pytest.mark.skipif(
    not (shutil.which("git") and shutil.which("bash")), reason="needs git and bash"
)


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repos(tmp_path, monkeypatch):
    """origin (bare: develop and 2.0 at one commit) and proj, a clone with the script."""
    for key, value in {
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
        "GH_CALLS": str(tmp_path / "gh-calls.txt"),
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("FAKE_OPEN", raising=False)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text(FAKE_GH)
    (bin_dir / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    seed = tmp_path / "seed"
    (seed / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, seed / "scripts" / "catch-up-2.0.sh")
    fixtures = seed / "backend" / "tests" / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "make_reference_1x_db.py").write_text(FIXTURE_SCRIPT)
    (seed / "backend" / "migrations" / "versions").mkdir(parents=True)
    (seed / "backend" / "migrations" / "versions" / "0012_x.py").write_text("x\n")
    (seed / "app.txt").write_text("one\n")
    git(tmp_path, "init", "-q", "-b", "develop", str(seed))
    git(seed, "add", "-A")
    git(seed, "commit", "-qm", "start")
    git(seed, "branch", "2.0")
    origin = tmp_path / "origin.git"
    git(tmp_path, "clone", "-q", "--bare", str(seed), str(origin))
    git(seed, "remote", "add", "origin", str(origin))
    proj = tmp_path / "proj"
    git(tmp_path, "clone", "-q", str(origin), str(proj))
    return proj, seed


def commit_on(seed, branch, files: dict, message="change"):
    git(seed, "switch", "-q", branch)
    for name, text in files.items():
        path = seed / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(seed, "add", "-A")
    git(seed, "commit", "-qm", message)
    git(seed, "push", "-q", "origin", branch)


def run(proj, *args):
    return subprocess.run(["bash", str(proj / "scripts" / "catch-up-2.0.sh"), *args], capture_output=True, text=True)


def gh_calls(tmp_path) -> list[str]:
    path = tmp_path / "gh-calls.txt"
    return path.read_text().splitlines() if path.exists() else []


def test_nothing_to_do(repos, tmp_path):
    proj, _ = repos
    r = run(proj)
    assert r.returncode == 0 and "UP TO DATE" in r.stdout
    assert gh_calls(tmp_path) == []


def test_new_commits_get_one_pull_request_from_develop_merged_with_a_merge_commit(repos, tmp_path):
    proj, seed = repos
    commit_on(seed, "develop", {"app.txt": "two\n"}, "a 1.x fix")
    r = run(proj)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "a 1.x fix" in r.stdout
    assert "CATCH-UP OPEN https://github.com/o/r/pull/700" in r.stdout
    calls = gh_calls(tmp_path)
    assert any(c.startswith("pr create") and "--base 2.0 --head develop" in c for c in calls)
    assert any(c.startswith("pr merge") and "--auto --merge" in c for c in calls)
    assert not any("--squash" in c for c in calls)


def test_an_open_catch_up_is_named_not_opened_again(repos, tmp_path, monkeypatch):
    proj, seed = repos
    commit_on(seed, "develop", {"app.txt": "two\n"})
    monkeypatch.setenv("FAKE_OPEN", "https://github.com/o/r/pull/650")
    r = run(proj)
    assert r.returncode == 0 and "CATCH-UP OPEN https://github.com/o/r/pull/650" in r.stdout
    assert not any(c.startswith("pr create") for c in gh_calls(tmp_path))


def test_a_lead_made_merge_branch_counts_as_the_open_catch_up(repos, tmp_path):
    """The script asks gh for 2.0's open pull requests from develop or a
    2.0-merge-develop branch (the fake answers as gh's --jq would)."""
    proj, seed = repos
    commit_on(seed, "develop", {"app.txt": "two\n"})
    r = run(proj, "--dry-run")
    listed = [c for c in gh_calls(tmp_path) if c.startswith("pr list")]
    assert listed and "--base 2.0" in listed[0] and '"2.0-merge-develop"' in listed[0]
    assert r.returncode == 0


def test_a_dry_run_opens_nothing(repos, tmp_path):
    proj, seed = repos
    commit_on(seed, "develop", {"app.txt": "two\n"})
    r = run(proj, "--dry-run")
    assert r.returncode == 0 and "nothing opened" in r.stdout
    assert not any(c.startswith(("pr create", "pr merge")) for c in gh_calls(tmp_path))


def test_a_1x_migration_stops_for_the_lead(repos, tmp_path):
    proj, seed = repos
    commit_on(seed, "develop", {"backend/migrations/versions/0013_new.py": "x\n"})
    r = run(proj)
    assert r.returncode == 1
    assert "needs the lead: a 1.x migration (0013_new.py)" in r.stdout and "NEEDS THE LEAD" in r.stdout
    assert not any(c.startswith("pr create") for c in gh_calls(tmp_path))


def test_a_conflict_stops_for_the_lead(repos, tmp_path):
    proj, seed = repos
    commit_on(seed, "2.0", {"app.txt": "two point oh\n"})
    commit_on(seed, "develop", {"app.txt": "one point one\n"})
    r = run(proj)
    assert r.returncode == 1 and "needs the lead: the merge conflicts" in r.stdout
    assert not any(c.startswith("pr create") for c in gh_calls(tmp_path))


def test_a_new_release_and_startos_changes_are_to_dos_beside_the_pull_request(repos, tmp_path):
    proj, seed = repos
    commit_on(seed, "develop", {"startos/manifest.ts": "sdk 3.1.0\n"}, "start-sdk 3.1.0")
    git(seed, "tag", "v1.2.10")
    git(seed, "tag", "v1.2.10-1")  # a revision of one: not a release of its own
    git(seed, "push", "-q", "origin", "--tags")
    r = run(proj)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "to do: v1.2.10 is out: make reference_1x.db again from it" in r.stdout
    assert "to do: 1 file(s) under startos/ changed" in r.stdout
    assert "CATCH-UP OPEN" in r.stdout


def test_an_older_or_the_same_release_is_no_to_do(repos):
    proj, seed = repos
    commit_on(seed, "develop", {"app.txt": "two\n"})
    for tag in ("v1.2.8", "v1.2.9"):
        git(seed, "tag", tag)
    git(seed, "push", "-q", "origin", "--tags")
    assert "to do:" not in run(proj).stdout
