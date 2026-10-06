"""
scripts/sync-startos-mirror.sh, run against local repositories and a
stand-in `gh` (no network). Once Start9 has forked the mirror, every change
reaches their fork by pull request from the mirror's main, so the sync
commit goes on top of their fork's branch: the pull request then shows only
our changes, not theirs undone (#29, after Start9 merged their review,
Start9-Community/BTCTX-StartOS#1).
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"

FAKE_GH = """#!/bin/sh
case "$1 $2" in
  "api repos/"*/forks) printf '%s' "$FAKE_FORKS" ;;
  "api repos/"*) echo main ;;
esac
"""

FORKED = {"START9_FORK": "Start9-Community/BTCTX-StartOS", "START9_BRANCH": "main"}
CURRENT_TS = "export const current = VersionInfo.of({\n  version: '1.2.4:1',\n})\n"


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def write_package(root, main_ts):
    (root / "startos" / "versions").mkdir(parents=True, exist_ok=True)
    (root / "startos" / "versions" / "current.ts").write_text(CURRENT_TS)
    (root / "main.ts").write_text(main_ts)


@pytest.fixture
def repos(tmp_path, monkeypatch):
    """proj (BTCTX-MCP with startos/), mirror (bare, startos/ at its root), fork (a clone of the mirror)."""
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
    for var in ("START9_FORK", "START9_BRANCH", "FAKE_FORKS", "MIRROR_BRANCH"):
        monkeypatch.delenv(var, raising=False)

    proj = tmp_path / "proj"
    (proj / "scripts").mkdir(parents=True)
    for name in ("sync-startos-mirror.sh", "start9-pull.sh"):
        shutil.copy(SCRIPTS / name, proj / "scripts" / name)
    write_package(proj / "startos", "one\ntwo\n")
    git(tmp_path, "init", "-q", "-b", "develop", str(proj))
    git(proj, "add", "-A")
    git(proj, "commit", "-qm", "package")

    seed = tmp_path / "seed"
    git(tmp_path, "init", "-q", "-b", "main", str(seed))
    write_package(seed, "one\ntwo\n")
    git(seed, "add", "-A")
    git(seed, "commit", "-qm", "Sync from DigiMonk73/BTCTX-MCP@aaaaaaa (1.2.4:0)")
    mirror = tmp_path / "mirror.git"
    git(tmp_path, "clone", "-q", "--bare", str(seed), str(mirror))

    fork = tmp_path / "fork"
    git(tmp_path, "clone", "-q", str(mirror), str(fork))
    monkeypatch.setenv("MIRROR_URL", str(mirror))
    monkeypatch.setenv("FORK_URL", str(fork))
    return proj, mirror, fork, tmp_path / "out"


def run(proj, out, *args, **env):
    r = subprocess.run(
        ["bash", str(proj / "scripts" / "sync-startos-mirror.sh"), *args, str(out)],
        capture_output=True, text=True, env={**os.environ, **env},
    )
    assert r.returncode == 0, r.stderr
    return r


def start9_review(fork):
    """Start9 changes their fork, as their review did."""
    (fork / "main.ts").write_text("one\ntwo, as Start9 wants it\n")
    git(fork, "commit", "-qam", "Start9's review")
    return git(fork, "rev-parse", "HEAD")


def our_change_with_theirs(proj):
    """startos/ after scripts/start9-pull.sh --apply and a change of ours."""
    (proj / "startos" / "main.ts").write_text("one\ntwo, as Start9 wants it\nthree\n")
    git(proj, "commit", "-qam", "Take Start9's review, add three")


def test_the_sync_commit_goes_on_top_of_start9s_fork(repos):
    proj, mirror, fork, out = repos
    theirs = start9_review(fork)
    our_change_with_theirs(proj)
    r = run(proj, out, "--push", **FORKED)
    assert "Fast-forwarded" in r.stdout
    head = git(mirror, "rev-parse", "main")
    assert git(mirror, "rev-parse", "main~1") == theirs, "a fast-forward to their fork, then our one commit"
    assert git(mirror, "rev-list", "--merges", "main") == ""
    # What a pull request from the mirror's main to their fork shows: only ours.
    assert git(mirror, "diff", "--name-only", theirs, head) == "main.ts"
    assert git(mirror, "diff", "--numstat", theirs, head) == "1\t0\tmain.ts"


def test_an_open_pull_request_of_ours_leaves_the_mirror_as_it_is(repos):
    """Their branch is behind the mirror, already in it: no merge, no fast-forward."""
    proj, mirror, _, out = repos
    (proj / "startos" / "main.ts").write_text("one\ntwo\nours, not merged yet\n")
    git(proj, "commit", "-qam", "ours")
    run(proj, out, "--push", **FORKED)
    before = git(mirror, "rev-parse", "main")
    shutil.rmtree(out)

    (proj / "startos" / "main.ts").write_text("one\ntwo\nours, not merged yet\nmore\n")
    git(proj, "commit", "-qam", "more")
    r = run(proj, out, **FORKED)
    assert "already in the mirror" in r.stdout
    assert git(out, "rev-parse", "HEAD~1") == before


def test_a_diverged_fork_is_merged_keeping_startos_as_the_content(repos):
    """E.g. Start9 squash-merged a pull request of ours: their branch is no longer behind or ahead."""
    proj, mirror, fork, out = repos
    # A pull request of ours that they squash instead of merging.
    (proj / "startos" / "main.ts").write_text("one\ntwo\nours\n")
    git(proj, "commit", "-qam", "ours")
    run(proj, out, "--push")
    (fork / "main.ts").write_text("one\ntwo\nours\n")
    git(fork, "commit", "-qam", "Squashed: ours")
    theirs = git(fork, "rev-parse", "HEAD")
    shutil.rmtree(out)

    (proj / "startos" / "main.ts").write_text("one\ntwo\nours\nmore\n")
    git(proj, "commit", "-qam", "more")
    r = run(proj, out, **FORKED)
    assert "diverged" in r.stderr
    git(out, "merge-base", "--is-ancestor", theirs, "HEAD")
    assert (out / "main.ts").read_text() == "one\ntwo\nours\nmore\n"
    assert git(out, "diff", theirs, "HEAD") == git(out, "diff", "HEAD~1", "HEAD")


def test_before_start9_forks_the_sync_is_unchanged(repos):
    proj, mirror, _, out = repos
    before = git(mirror, "rev-parse", "main")
    our_change_with_theirs(proj)
    run(proj, out, "--push")
    assert git(mirror, "rev-parse", "main~1") == before
    assert (out / "main.ts").read_text() == "one\ntwo, as Start9 wants it\nthree\n"


def test_the_fork_is_found_through_github(repos):
    proj, mirror, fork, out = repos
    theirs = start9_review(fork)
    our_change_with_theirs(proj)
    run(proj, out, "--push", FAKE_FORKS="Start9-Community/BTCTX-StartOS\n")
    assert git(mirror, "rev-parse", "main~1") == theirs
