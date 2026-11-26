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
    assert run(proj).returncode == 2
