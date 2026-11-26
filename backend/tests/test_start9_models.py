"""
scripts/start9-models.sh, run against a local repository (no network).
Start9's publishing.md, "The Pipeline" (2026-11-26): a pull request to the
fork names, on a line of its own, each AI model that wrote any of it, by the
id its harness reports (`model: claude-opus-5-5`), comma-separated. The
mirror's commits carry no co-authors, so the script reads the Co-Authored-By
lines of our commits that changed startos/.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "start9-models.sh"


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def proj(tmp_path, monkeypatch):
    for key, value in {
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    }.items():
        monkeypatch.setenv(key, value)
    proj = tmp_path / "proj"
    (proj / "scripts").mkdir(parents=True)
    (proj / "startos").mkdir()
    shutil.copy(SCRIPT, proj / "scripts" / "start9-models.sh")
    git(tmp_path, "init", "-q", "-b", "develop", str(proj))
    commit(proj, "startos/a.ts", "the last release Start9 merged", "Claude Opus 4.6 <noreply@anthropic.com>")
    git(proj, "tag", "v1")
    return proj


def commit(proj, path, subject, *co_authors):
    file = proj / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(file.read_text() + subject + "\n" if file.exists() else subject + "\n")
    git(proj, "add", "-A")
    trailers = "".join(f"\nCo-authored-by: {who}" for who in co_authors)
    git(proj, "commit", "-qm", subject + ("\n" + trailers if trailers else ""))


def run(proj, *args):
    return subprocess.run(["bash", str(proj / "scripts" / "start9-models.sh"), *args],
                          cwd=proj, capture_output=True, text=True)


def test_each_model_once_by_its_id(proj):
    commit(proj, "startos/a.ts", "one", "Claude Opus 5.5 <noreply@anthropic.com>")
    commit(proj, "startos/b.ts", "two", "Claude Sonnet 5.5 <noreply@anthropic.com>")
    commit(proj, "startos/a.ts", "three", "Claude Opus 5.5 <noreply@anthropic.com>")
    r = run(proj, "v1")
    assert r.returncode == 0, r.stderr
    assert r.stdout == "model: claude-opus-5-5, claude-sonnet-5-5\n"


def test_only_what_changed_startos_since_the_release(proj):
    commit(proj, "backend/x.py", "app only", "Claude Sonnet 5.5 <noreply@anthropic.com>")
    commit(proj, "startos/a.ts", "package", "Claude Opus 5.5 <noreply@anthropic.com>")
    assert run(proj, "v1").stdout == "model: claude-opus-5-5\n"  # not v1's claude-opus-4-6


def test_nothing_when_no_model_wrote_it(proj):
    commit(proj, "startos/a.ts", "by hand")
    r = run(proj, "v1")
    assert (r.returncode, r.stdout) == (0, "")


def test_another_co_author_is_named_for_a_person_and_left_out(proj):
    commit(proj, "startos/a.ts", "pair", "A Person <someone@example.com>", "Claude Opus 5.5 <noreply@anthropic.com>")
    r = run(proj, "v1")
    assert r.stdout == "model: claude-opus-5-5\n"
    assert "A Person <someone@example.com>" in r.stderr


def test_until_a_commit(proj):
    commit(proj, "startos/a.ts", "sent", "Claude Opus 5.5 <noreply@anthropic.com>")
    git(proj, "tag", "v2")
    commit(proj, "startos/a.ts", "after", "Claude Sonnet 5.5 <noreply@anthropic.com>")
    assert run(proj, "v1", "v2").stdout == "model: claude-opus-5-5\n"


@pytest.mark.parametrize("args", [("v0",), ("", "v1"), ("v1", "")])
def test_a_range_that_isnt_one_is_refused(proj, args):
    # Never "no models": that would leave the line off without a word.
    r = run(proj, *args)
    assert r.returncode == 2 and r.stdout == ""
    assert "not a commit here" in r.stderr


@pytest.mark.parametrize("co_author", ["Claude <noreply@anthropic.com>"])
def test_a_claude_name_with_no_model_id_is_named_not_guessed(proj, co_author):
    commit(proj, "startos/a.ts", "bare", co_author)
    r = run(proj, "v1")
    assert (r.returncode, r.stdout) == (0, "")
    assert co_author in r.stderr


def test_a_note_after_the_name_is_not_part_of_the_id(proj):
    commit(proj, "startos/a.ts", "long", "Claude Opus 4.7 (1M context) <noreply@anthropic.com>")
    assert run(proj, "v1").stdout == "model: claude-opus-4-7\n"


def test_a_squash_carries_its_commits_lines_in_its_middle(proj):
    # GitHub's squash message: each commit's message, then its own trailer.
    (proj / "startos" / "a.ts").write_text("squashed\n")
    git(proj, "add", "-A")
    git(proj, "commit", "-qm", "Squash (#1)\n\n* one\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n\n"
        "* two\n\n---------\n\nCo-authored-by: Claude Sonnet 5.5 <noreply@anthropic.com>")
    assert run(proj, "v1").stdout == "model: claude-opus-5-5, claude-sonnet-5-5\n"


# --- what the fork holds, and the release workflow's own steps ---

def fork_holding(tmp_path, proj, *revs):
    """Start9's fork: our syncs of `revs`, oldest first, with their own
    commits between; the last inside a squash of our pull request."""
    fork = tmp_path / "fork"
    git(tmp_path, "init", "-q", "-b", "main", str(fork))
    *older, newest = [git(proj, "rev-parse", "--short", rev).strip() for rev in revs]
    for sha in older:
        git(fork, "commit", "-q", "--allow-empty", "-m", f"Sync from DigiMonk73/BTCTX-MCP@{sha} (0.1)")
    git(fork, "commit", "-q", "--allow-empty", "-m", "Their template update")
    git(fork, "commit", "-q", "--allow-empty", "-m", f"BitcoinTX v1 (#4)\n\n* Sync from DigiMonk73/BTCTX-MCP@{newest} (1)")
    return fork


def test_since_what_the_fork_holds(tmp_path, proj, monkeypatch):
    commit(proj, "startos/a.ts", "sent", "Claude Opus 5.5 <noreply@anthropic.com>")
    monkeypatch.setenv("START9_FORK", "Start9-Community/BTCTX-StartOS")
    monkeypatch.setenv("START9_BRANCH", "main")
    monkeypatch.setenv("FORK_URL", str(fork_holding(tmp_path, proj, "v1")))
    assert run(proj).stdout == "model: claude-opus-5-5\n"  # not v1's claude-opus-4-6
    assert run(proj, "--fork").stdout == "model: claude-opus-5-5\n"


def test_since_the_newest_sync_the_fork_holds_not_the_last_tag(tmp_path, proj, monkeypatch):
    # A docs-only sync after v1, by hand, which Start9 merged: its model is
    # theirs already. Counting from v1, the last tag, or from the oldest sync
    # they hold, would name it again.
    commit(proj, "startos/README.md", "docs only", "Claude Sonnet 5.5 <noreply@anthropic.com>")
    docs_sync = git(proj, "rev-parse", "HEAD").strip()
    commit(proj, "startos/a.ts", "sent", "Claude Opus 5.5 <noreply@anthropic.com>")
    monkeypatch.setenv("START9_FORK", "Start9-Community/BTCTX-StartOS")
    monkeypatch.setenv("START9_BRANCH", "main")
    monkeypatch.setenv("FORK_URL", str(fork_holding(tmp_path, proj, "v1", docs_sync)))
    assert run(proj).stdout == "model: claude-opus-5-5\n"
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv("FORK_URL", str(fork_holding(other, proj, docs_sync, "v1")))
    assert run(proj).stdout == "model: claude-opus-5-5\n"  # the newest, whatever order they hold them in


def test_the_fork_alone_is_not_enough(proj, monkeypatch):
    monkeypatch.setenv("START9_FORK", "Start9-Community/BTCTX-StartOS")
    monkeypatch.delenv("START9_BRANCH", raising=False)
    r = run(proj, "--fork")
    assert r.returncode != 0 and r.stdout == ""


def test_a_bot_is_no_model_and_no_question(proj):
    commit(proj, "startos/a.ts", "bumped", "dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>")
    r = run(proj, "v1")
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


RELEASE = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "release.yml"
FAKE_GH = """#!/bin/sh
case "$1 $2" in
  "pr list") [ -z "$FAKE_LIST_FAILS" ] || { echo "gh: HTTP 502" >&2; exit 1; }; printf '%s' "$FAKE_OPEN" ;;
  "pr view") printf '%s' "$FAKE_BODY" ;;
  "issue create") cp body.md "$ISSUES/$(ls "$ISSUES" | wc -l | tr -d ' ').md" ;;
esac
"""


def mirror_step():
    """release.yml's mirror step, from finding the fork to the issue."""
    text = RELEASE.read_text()
    start = text.index('          FORK_INFO="$(scripts/start9-pull.sh --fork)"')
    end = text.index("\n", text.index('echo "::warning::Open the pull request to $FORK'))
    return "\n".join(line[10:] for line in text[start:end].split("\n"))


@pytest.fixture
def release(tmp_path, proj, monkeypatch):
    """Run the step on proj's tag v2, Start9's fork holding v1."""
    commit(proj, "startos/a.ts", "in v2", "Claude Opus 5.5 <noreply@anthropic.com>")
    git(proj, "tag", "v2")
    (proj / "scripts" / "start9-pull.sh").write_text('#!/bin/sh\necho "Start9-Community/BTCTX-StartOS main"\n')
    (proj / "scripts" / "start9-pull.sh").chmod(0o755)
    (proj / "step.sh").write_text(mirror_step())
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text(FAKE_GH)
    (bin_dir / "gh").chmod(0o755)
    issues = tmp_path / "issues"
    issues.mkdir()
    for var in ("START9_FORK", "START9_BRANCH", "FAKE_OPEN", "FAKE_BODY", "FAKE_LIST_FAILS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("ISSUES", str(issues))
    monkeypatch.setenv("FORK_URL", str(fork_holding(tmp_path, proj, "v1")))
    monkeypatch.setenv("TAG", "v2")
    monkeypatch.setenv("GITHUB_REPOSITORY", "DigiMonk73/BTCTX-MCP")

    def step():
        r = subprocess.run(["bash", "-e", "step.sh"], cwd=proj, capture_output=True, text=True)
        return r, [path.read_text() for path in sorted(issues.iterdir())]
    return step


def test_the_send_issue_gives_the_model_line(release):
    r, issues = release()
    assert r.returncode == 0, r.stderr
    assert len(issues) == 1 and "Click **Create pull request**" in issues[0]
    assert "`model: claude-opus-5-5`" in issues[0]
    assert "by hand" not in issues[0]


def test_an_open_pull_request_gets_the_whole_line(release, monkeypatch):
    monkeypatch.setenv("FAKE_OPEN", "12")
    monkeypatch.setenv("FAKE_BODY", "Notes\r\n\r\nmodel:claude-opus-4-6\r\n")
    r, issues = release()
    assert r.returncode == 0, r.stderr
    assert len(issues) == 1
    assert "`model: claude-opus-4-6, claude-opus-5-5`" in issues[0]
    assert "pull/12" in issues[0]


def test_the_whole_line_keeps_only_ids(release, monkeypatch):
    monkeypatch.setenv("FAKE_OPEN", "12")
    monkeypatch.setenv("FAKE_BODY", "Notes\n\nmodel: claude-opus-4-6 (the first) *\n")
    r, issues = release()
    assert r.returncode == 0, r.stderr
    assert "`model: claude-opus-4-6, claude-opus-5-5`" in issues[0]


@pytest.mark.parametrize("line", ["model: claude-opus-5-5", "  `model: claude-opus-4-6,claude-opus-5-5`"])
def test_an_open_pull_request_that_names_them_gets_no_issue(release, monkeypatch, line):
    monkeypatch.setenv("FAKE_OPEN", "12")
    monkeypatch.setenv("FAKE_BODY", f"Notes\n\n{line}\n")
    r, issues = release()
    assert r.returncode == 0, r.stderr
    assert issues == []


def test_a_failed_lookup_stops_rather_than_send_a_second_pull_request(release, monkeypatch):
    monkeypatch.setenv("FAKE_LIST_FAILS", "1")
    r, issues = release()
    assert r.returncode != 0
    assert issues == []


def test_a_co_author_left_out_reaches_the_owner(release, proj):
    commit(proj, "startos/a.ts", "paired", "Cursor <cursoragent@cursor.com>")
    git(proj, "tag", "-f", "v2")
    r, issues = release()
    assert r.returncode == 0, r.stderr
    assert "by hand" in issues[0] and "Cursor <cursoragent@cursor.com>" in issues[0]
    assert "::warning::" in r.stdout
