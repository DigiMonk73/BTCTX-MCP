"""
scripts/catch-up-2.0.sh: develop into the 2.0 build (AGENTS.md, "Branches";
the owner's decision 24 on #251).

In throwaway repositories (an origin with develop and 2.0, and a clone),
with a fake gh that records what it was asked (its `pr list` answers as
the script's --jq would, from FAKE_PRS):
- nothing to do; a new release listed even then;
- develop's new commits: GitHub makes the merge on a branch of its own,
  its pull request opens, and auto-merge (a merge commit) is set for that
  commit alone; nothing while a 2.0 step has auto-merge on; one already
  open is named and never changed (its auto-merge is the lead's);
- a 1.x migration (added, changed or renamed), the reference test ledger
  or its figures, or a conflict stop for the lead with nothing opened;
- a git or gh failure is "can't tell" (exit 2), never taken for a clean merge.
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
  "pr list") [ -n "$FAKE_FAIL_PR_LIST" ] && exit 1; [ -f "$FAKE_PRS" ] && cat "$FAKE_PRS"; exit 0 ;;
  "pr create") cat > "$GH_CALLS.body"; [ -n "$FAKE_FAIL_PR_CREATE" ] && exit 1
               echo "https://github.com/o/r/pull/700"; exit 0 ;;
  "pr merge") [ -n "$FAKE_FAIL_PR_MERGE" ] && exit 1; exit 0 ;;
esac
case "$*" in
  *repos/o/r/merges*) [ -n "$FAKE_FAIL_MERGES" ] && exit 1; echo "f00dfeed"; exit 0 ;;
esac
exit 0
"""
# git, but `merge-tree` fails as an old git or a bad option would
FAKE_GIT = """#!/bin/sh
for a in "$@"; do [ "$a" = merge-tree ] && exit 129; done
exec "$REAL_GIT" "$@"
"""
FIXTURE_SCRIPT = 'RELEASE = "v1.2.9"\n'

pytestmark = pytest.mark.skipif(
    not (shutil.which("git") and shutil.which("bash")), reason="needs git and bash"
)


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repos(tmp_path, monkeypatch):
    """origin (bare: develop and 2.0 at one commit) and proj, a clone with the
    script, whose origin is named o/r for gh."""
    for key, value in {
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
        "GH_CALLS": str(tmp_path / "gh-calls.txt"), "FAKE_PRS": str(tmp_path / "prs.tsv"),
    }.items():
        monkeypatch.setenv(key, value)
    for key in ("FAKE_FAIL_MERGES", "FAKE_FAIL_PR_MERGE", "FAKE_FAIL_PR_CREATE", "FAKE_FAIL_PR_LIST"):
        monkeypatch.delenv(key, raising=False)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text(FAKE_GH)
    (bin_dir / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    seed = tmp_path / "seed"
    (seed / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, seed / "scripts" / "catch-up-2.0.sh")
    write(seed, {"backend/tests/fixtures/make_reference_1x_db.py": FIXTURE_SCRIPT,
                 "backend/migrations/versions/0012_x.py": "x\n", "testdata/reference_ledger.json": "{}\n",
                 "app.txt": "one\n"})
    git(tmp_path, "init", "-q", "-b", "develop", str(seed))
    git(seed, "add", "-A")
    git(seed, "commit", "-qm", "start")
    git(seed, "branch", "2.0")
    origin = tmp_path / "o" / "r.git"
    origin.parent.mkdir()
    git(tmp_path, "clone", "-q", "--bare", str(seed), str(origin))
    git(seed, "remote", "add", "origin", str(origin))
    proj = tmp_path / "proj"
    git(tmp_path, "clone", "-q", str(origin), str(proj))
    return proj, seed


def write(root, files: dict):
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def commit_on(seed, branch, files: dict, message="change"):
    git(seed, "switch", "-q", branch)
    write(seed, files)
    git(seed, "add", "-A")
    git(seed, "commit", "-qm", message)
    git(seed, "push", "-q", "origin", branch)


def open_prs(tmp_path, *rows):
    """2.0's open pull requests, as the script's --jq gives them."""
    (tmp_path / "prs.tsv").write_text("".join("\t".join(map(str, row)) + "\n" for row in rows))


def run(proj, *args):
    return subprocess.run(["bash", str(proj / "scripts" / "catch-up-2.0.sh"), *args], capture_output=True, text=True)


def gh_calls(tmp_path) -> list[str]:
    path = tmp_path / "gh-calls.txt"
    return path.read_text().splitlines() if path.exists() else []


def opened(tmp_path) -> bool:
    return any(c.startswith(("pr create", "api -X POST")) for c in gh_calls(tmp_path))


def test_nothing_to_do(repos, tmp_path):
    proj, _ = repos
    r = run(proj)
    assert r.returncode == 0 and "UP TO DATE" in r.stdout
    assert not opened(tmp_path)


def test_new_commits_get_a_merge_commit_of_their_own_tested_before_it_lands(repos, tmp_path):
    proj, seed = repos
    commit_on(seed, "develop", {"app.txt": "two\n"}, "a 1.x fix")
    develop = git(seed, "rev-parse", "develop")
    r = run(proj)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "a 1.x fix" in r.stdout and "CATCH-UP OPENED https://github.com/o/r/pull/700 (auto-merge on)" in r.stdout
    calls = gh_calls(tmp_path)
    branch = "2.0-merge-develop-auto-"
    made = [c for c in calls if "repos/o/r/git/refs" in c]
    assert made and f"ref=refs/heads/{branch}" in made[0] and f"sha={git(seed, 'rev-parse', '2.0')}" in made[0]
    merge = [c for c in calls if "repos/o/r/merges" in c]
    assert merge and f"head={develop}" in merge[0] and f"base={branch}" in merge[0]
    create = [c for c in calls if c.startswith("pr create")]
    assert create and f"--base 2.0 --head {branch}" in create[0]
    assert any(c.startswith("pr merge") and "--auto --merge --match-head-commit f00dfeed" in c for c in calls)
    assert not any("--squash" in c or "--head develop" in c for c in calls)
    assert "decision 24" in (tmp_path / "gh-calls.txt.body").read_text()


def test_nothing_while_a_2_0_step_has_auto_merge_on(repos, tmp_path):
    """Its pin must stay 2.0's tip, and a merge made now would land on a 2.0 its CI never saw."""
    proj, seed = repos
    commit_on(seed, "develop", {"app.txt": "two\n"})
    open_prs(tmp_path, (611, "https://github.com/o/r/pull/611", "2.0-b2b-account-book", "abc", "true", "false"))
    r = run(proj)
    assert r.returncode == 0
    assert "to do: a 2.0 step (#611) has auto-merge on: the catch-up waits" in r.stdout and "CATCH-UP WAITS" in r.stdout
    assert not opened(tmp_path) and not any(c.startswith("pr merge") for c in gh_calls(tmp_path))


@pytest.mark.parametrize("branch", ["2.0-merge-develop-auto-20261023-abc1234", "2.0-merge-develop-2026-10-23c"])
def test_an_open_catch_up_is_named_never_changed(repos, tmp_path, branch):
    """Its auto-merge off (turned off by the lead, red, or behind a step) is the lead's call."""
    proj, seed = repos
    commit_on(seed, "develop", {"app.txt": "two\n"})
    open_prs(tmp_path, (650, "https://github.com/o/r/pull/650", branch, "beef", "false", "false"))
    r = run(proj)
    assert r.returncode == 0 and "CATCH-UP OPEN https://github.com/o/r/pull/650 (auto-merge off)" in r.stdout
    assert "to do: the catch-up's auto-merge is off" in r.stdout
    assert not opened(tmp_path) and not any(c.startswith("pr merge") for c in gh_calls(tmp_path))


def test_a_step_and_a_catch_up_both_on_auto_merge_are_said(repos, tmp_path):
    proj, seed = repos
    commit_on(seed, "develop", {"app.txt": "two\n"})
    open_prs(tmp_path, (650, "https://github.com/o/r/pull/650", "2.0-merge-develop-auto-x", "beef", "true", "false"),
             (611, "https://github.com/o/r/pull/611", "2.0-b3-by-currency", "abc", "true", "false"))
    r = run(proj)
    assert "the step's pin may no longer be 2.0's tip" in r.stdout and "CATCH-UP OPEN" in r.stdout


def test_a_forks_pull_request_isnt_the_catch_up(repos, tmp_path):
    proj, seed = repos
    commit_on(seed, "develop", {"app.txt": "two\n"})
    open_prs(tmp_path, (9, "https://github.com/o/r/pull/9", "2.0-merge-develop-auto-x", "beef", "true", "true"))
    assert "CATCH-UP OPENED" in run(proj).stdout


def test_a_dry_run_opens_nothing(repos, tmp_path):
    proj, seed = repos
    commit_on(seed, "develop", {"app.txt": "two\n"})
    r = run(proj, "--dry-run")
    assert r.returncode == 0 and "DRY RUN: a catch-up would be opened now; nothing opened." in r.stdout
    assert not opened(tmp_path) and not any(c.startswith("pr merge") for c in gh_calls(tmp_path))


@pytest.mark.parametrize("change", [
    {"backend/migrations/versions/0013_new.py": "x\n"},  # added
    {"backend/migrations/versions/0012_x.py": "changed\n"},  # changed
])
def test_a_1x_migration_stops_for_the_lead(repos, tmp_path, change):
    proj, seed = repos
    commit_on(seed, "develop", change)
    r = run(proj)
    assert r.returncode == 1 and "needs the lead: a 1.x migration (" in r.stdout and "NEEDS THE LEAD" in r.stdout
    assert not opened(tmp_path)


def test_a_renamed_migration_stops_for_the_lead(repos, tmp_path):
    proj, seed = repos
    git(seed, "switch", "-q", "develop")
    git(seed, "mv", "backend/migrations/versions/0012_x.py", "backend/migrations/versions/0012_y.py")
    git(seed, "commit", "-qm", "rename")
    git(seed, "push", "-q", "origin", "develop")
    r = run(proj)
    assert r.returncode == 1 and "0012_x.py 0012_y.py" in r.stdout


def test_the_reference_ledger_stops_for_the_lead(repos, tmp_path):
    proj, seed = repos
    commit_on(seed, "develop", {"testdata/reference_ledger.json": '{"rows": 1}\n'})
    r = run(proj)
    assert r.returncode == 1 and "needs the lead: the reference test ledger or its figures changed" in r.stdout
    assert not opened(tmp_path)


def test_a_conflict_stops_for_the_lead(repos, tmp_path):
    proj, seed = repos
    commit_on(seed, "2.0", {"app.txt": "two point oh\n"})
    commit_on(seed, "develop", {"app.txt": "one point one\n"})
    open_prs(tmp_path, (616, "https://github.com/o/r/pull/616", "2.0-merge-develop-x", "beef", "false", "false"))
    r = run(proj)
    assert r.returncode == 1 and "needs the lead: the merge conflicts" in r.stdout
    assert "open catch-up: https://github.com/o/r/pull/616" in r.stdout
    assert not opened(tmp_path)


def test_a_merge_tree_failure_is_cant_tell_not_a_clean_merge(repos, tmp_path, monkeypatch):
    proj, seed = repos
    commit_on(seed, "develop", {"app.txt": "two\n"})
    fake = tmp_path / "bin" / "git"
    fake.write_text(FAKE_GIT)
    fake.chmod(0o755)
    monkeypatch.setenv("REAL_GIT", shutil.which("git", path=os.environ["PATH"].split(os.pathsep, 1)[1]))
    r = run(proj)
    assert r.returncode == 2 and "can't tell whether the merge is clean" in r.stderr
    assert not opened(tmp_path)


def test_github_refusing_the_merge_removes_its_branch(repos, tmp_path, monkeypatch):
    proj, seed = repos
    commit_on(seed, "develop", {"app.txt": "two\n"})
    monkeypatch.setenv("FAKE_FAIL_MERGES", "1")
    r = run(proj)
    assert r.returncode == 2 and "the branch is removed again" in r.stderr
    calls = gh_calls(tmp_path)
    assert any(c.startswith("api -X DELETE") for c in calls) and not any(c.startswith("pr create") for c in calls)


def test_a_pull_request_that_wont_open_removes_its_branch(repos, tmp_path, monkeypatch):
    proj, seed = repos
    commit_on(seed, "develop", {"app.txt": "two\n"})
    monkeypatch.setenv("FAKE_FAIL_PR_CREATE", "1")
    r = run(proj)
    assert r.returncode == 2 and "couldn't open the pull request" in r.stderr and "removed again" in r.stderr
    assert any(c.startswith("api -X DELETE") for c in gh_calls(tmp_path))


def test_gh_failing_to_list_is_cant_tell(repos, tmp_path, monkeypatch):
    proj, seed = repos
    commit_on(seed, "develop", {"app.txt": "two\n"})
    monkeypatch.setenv("FAKE_FAIL_PR_LIST", "1")
    r = run(proj)
    assert r.returncode == 2 and "CAN'T TELL" in r.stderr and not opened(tmp_path)


def test_auto_merge_refused_is_cant_tell(repos, tmp_path, monkeypatch):
    proj, seed = repos
    commit_on(seed, "develop", {"app.txt": "two\n"})
    monkeypatch.setenv("FAKE_FAIL_PR_MERGE", "1")
    r = run(proj)
    assert r.returncode == 2 and "couldn't turn on auto-merge" in r.stderr


def test_a_new_release_and_startos_changes_are_to_dos_beside_the_pull_request(repos, tmp_path):
    proj, seed = repos
    commit_on(seed, "develop", {"startos/manifest.ts": "sdk 3.1.0\n"}, "start-sdk 3.1.0")
    for tag in ("v1.2.10", "v1.2.10-1", "v2.0.0-alpha.1", "v2.0.0-beta.1"):  # a revision, pre-releases: none of their own
        git(seed, "tag", tag)
    git(seed, "push", "-q", "origin", "--tags")
    r = run(proj)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "to do: v1.2.10 is out: make reference_1x.db again from it" in r.stdout
    assert "to do: 1 file(s) under startos/ changed" in r.stdout
    assert "CATCH-UP OPENED" in r.stdout


def test_a_new_release_is_listed_with_2_0_up_to_date(repos):
    proj, seed = repos
    git(seed, "tag", "v1.2.10")
    git(seed, "push", "-q", "origin", "--tags")
    r = run(proj)
    assert r.returncode == 0 and "to do: v1.2.10 is out" in r.stdout and "UP TO DATE" in r.stdout


def test_an_older_or_the_same_release_is_no_to_do(repos):
    proj, seed = repos
    commit_on(seed, "develop", {"app.txt": "two\n"})
    for tag in ("v1.2.8", "v1.2.9"):
        git(seed, "tag", tag)
    git(seed, "push", "-q", "origin", "--tags")
    assert "to do:" not in run(proj).stdout
