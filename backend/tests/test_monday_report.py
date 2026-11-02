"""
The Monday report (docs/MAINTENANCE.md, "The Monday report"; the owner,
2026-10-31): a workflow writes one issue of what needs attention, so no
Claude tokens and no Mac are spent on it. GitHub runs a schedule only from the
default branch, so the workflow can't be tried before a release brings it to
`main`; these run the script against a stand-in `gh` that answers from
fixtures, and read the workflow's and Dependabot's files.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "monday-report.sh"
WORKFLOW = (ROOT / ".github" / "workflows" / "monday-report.yml").read_text()
WATCH = (ROOT / ".github" / "workflows" / "start9-watch.yml").read_text()
DEPENDABOT = (ROOT / ".github" / "dependabot.yml").read_text()

needs_jq = pytest.mark.skipif(shutil.which("jq") is None, reason="the script needs jq")

REPO = "DigiMonk73/BTCTX-MCP"
FORK = "Start9-Community/BTCTX-StartOS"
MIRROR = "DigiMonk73/BTCTX-StartOS"
ISSUES = "repos/{}/issues?state=open&per_page=100"
TITLE = "Monday report: what needs attention"

# What the stand-in gh does: answers `gh api <path>` from the fixtures (a
# {"pages": [...]} one as --paginate prints it, a page after another; a
# {"fail": true} one fails), saves the body of an issue opened or edited
# (`gh api -F body=@file`), and logs every call. A path it has no answer for
# fails, as an API call the script shouldn't make would.
STAND_IN = """#!{python}
import json, os, shutil, sys
args = sys.argv[1:]
with open(os.environ["GH_LOG"], "a") as log:
    log.write(" ".join(args) + "\\n")
body = [a for a in args if a.startswith("body=@")]
if args[0] == "api" and body:
    shutil.copy(body[0][len("body=@"):], os.environ["GH_BODY"])
    sys.exit(0)
if args[0] == "api":
    fixtures = json.load(open(os.environ["GH_FIXTURES"]))
    answer = fixtures.get(args[1])
    if isinstance(answer, dict) and answer.get("fail"):
        sys.exit(1)
    if isinstance(answer, dict) and "pages" in answer:
        for page in answer["pages"]:
            print(json.dumps(page))
        sys.exit(0)
    if args[1] in fixtures:
        print(json.dumps(answer))
        sys.exit(0)
print("unexpected: " + " ".join(args), file=sys.stderr)
sys.exit(1)
"""


def ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def issue(number, title, days, login="a-user", kind="User", labels=(), pull=False):
    found = {
        "number": number,
        "title": title,
        "html_url": f"https://github.com/x/y/issues/{number}",
        "created_at": ago(days),
        "labels": [{"name": name} for name in labels],
        "user": {"login": login, "type": kind},
    }
    return {**found, "pull_request": {}} if pull else found


def fixtures():
    return {
        f"repos/{REPO}": {"has_issues": True},
        f"repos/{FORK}": {"has_issues": True},
        f"repos/{MIRROR}": {"has_issues": False},
        ISSUES.format(REPO) + "&labels=tax-figures": [
            issue(849, "A newer figure bug", 1, "DigiMonk73", labels=["bug", "tax-figures"]),
            issue(104, "An older figure bug", 21, "DigiMonk73", labels=["tax-figures", "claude"]),
        ],
        ISSUES.format(REPO) + "&labels=start9": [issue(811, "Start9's release", 3, "DigiMonk73", labels=["start9", "owner"])],
        ISSUES.format(REPO): [
            issue(849, "A newer figure bug", 1, "DigiMonk73"),
            issue(870, "Send v2.0.0 to Start9", 2, "github-actions[bot]", "Bot"),
            issue(901, "Unanswered and old", 10, "reporter"),
            issue(902, "Answered by the owner", 9, "reporter"),
            issue(903, "Only another user replied", 2, "other-reporter"),
            issue(904, "A pull request from outside", 5, "reporter", pull=True),
            issue(950, TITLE, 7, "github-actions[bot]", "Bot"),
        ],
        ISSUES.format(FORK): [],
        f"repos/{REPO}/issues/901/comments": [],
        f"repos/{REPO}/issues/902/comments": [{"user": {"login": "DigiMonk73"}}],
        f"repos/{REPO}/issues/903/comments": [{"user": {"login": "reporter"}}],
    }


def run(tmp_path, data, *args, env=None):
    """Runs the script with the stand-in gh; returns (result, gh's calls, the body saved)."""
    stand_in = tmp_path / "bin" / "gh"
    stand_in.parent.mkdir()
    stand_in.write_text(STAND_IN.format(python=sys.executable))
    stand_in.chmod(0o755)
    (tmp_path / "fixtures.json").write_text(json.dumps(data))
    # Nothing of the CI machine's own GITHUB_* variables reaches the script
    path = f"{stand_in.parent}{os.pathsep}{os.environ['PATH']}"
    full_env = {
        "PATH": path,
        "HOME": str(tmp_path),
        "GH_FIXTURES": str(tmp_path / "fixtures.json"),
        "GH_LOG": str(tmp_path / "calls.log"),
        "GH_BODY": str(tmp_path / "body.md"),
        **(env or {}),
    }
    result = subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=full_env)
    calls = (tmp_path / "calls.log").read_text().splitlines() if (tmp_path / "calls.log").exists() else []
    body = (tmp_path / "body.md").read_text() if (tmp_path / "body.md").exists() else None
    return result, calls, body


def section(text, heading):
    """The text under one `## heading`, up to the next one."""
    return re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.S | re.M).group(1)


@needs_jq
def test_it_lists_the_three_things(tmp_path):
    result, _, _ = run(tmp_path, fixtures(), "--dry-run")
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert out.startswith(f"WOULD EDIT #950: {TITLE}")

    figures = section(out, "Open `tax-figures` issues")
    assert figures.index("#104") < figures.index("#849"), "oldest first"
    assert "`An older figure bug`, 21 days, Claude has it" in figures
    assert "`A newer figure bug`, 1 day, no `claude` or `owner` label" in figures

    outside = section(out, "Outside reports with no answer")
    # The owner's own, a bot's, the answered one and the pull request aren't there
    assert "#901" in outside and "**older than a week**" in outside.split("#901")[1].split("\n")[0]
    assert "#903" in outside and "older than a week" not in outside.split("#903")[1].split("\n")[0]
    for left_out in ("#849", "#870", "#902", "#904", "#950"):
        assert left_out not in outside
    assert f"### {FORK}\n\nNone." in outside
    assert f"### {MIRROR}\n\nIssues are off, as they should be." in outside

    start9 = section(out, "Open `start9` issues")
    assert "`Start9's release`, 3 days" in start9
    # Links go through redirect.github.com, which leaves no "mentioned this" event
    assert "(https://redirect.github.com/x/y/issues/811)" in start9
    assert "(https://github.com/" not in out


@needs_jq
def test_nothing_needs_attention_when_nothing_is_open(tmp_path):
    data = {key: ([] if isinstance(value, list) else value) for key, value in fixtures().items()}
    result, _, _ = run(tmp_path, data, "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "WOULD OPEN: " + TITLE in result.stdout
    assert "**Nothing needs attention this week.**" in result.stdout


@needs_jq
def test_an_issue_title_cant_link_mention_or_refer(tmp_path):
    # Text direction marks, zero-width and line separator characters, built here
    # so that no invisible character sits in this file
    invisible = "".join(chr(code) for code in (0x202E, 0x200B, 0x200F, 0x2028, 0x2029, 0xFEFF))
    hostile = f"`x` [click](https://evil.example) @someone #12 <img src=x> {invisible} www.evil.example\nfake: **bold**"
    data = fixtures()
    data[ISSUES.format(FORK)] = [issue(7, hostile, 8)]
    data[f"repos/{FORK}/issues/7/comments"] = []
    result, _, _ = run(tmp_path, data, "--dry-run")
    assert result.returncode == 0, result.stderr
    line = next(line for line in result.stdout.splitlines() if line.startswith("- [#7]"))
    # Inside one code span nothing is a link, a mention or a reference
    assert re.fullmatch(r"- \[#7\]\(https://redirect\.github\.com/x/y/issues/7\) `[^`\n]*`, 8 days, \*\*older than a week\*\*", line)
    assert not any(char in line for char in invisible)


@needs_jq
def test_it_edits_its_open_report_by_rest_and_otherwise_opens_one(tmp_path):
    result, calls, body = run(tmp_path, fixtures())
    assert result.returncode == 0, result.stderr
    published = [call for call in calls if "-F body=@" in call]
    assert len(published) == 1 and published[0].startswith(f"api -X PATCH repos/{REPO}/issues/950 -F body=@")
    assert body.startswith("Updated ") and body.rstrip().endswith("— Claude (scripts/monday-report.sh)")

    # Someone else's issue with the same title is never edited
    data = fixtures()
    data[ISSUES.format(REPO)][-1] = issue(950, TITLE, 7, "a-stranger")
    data[f"repos/{REPO}/issues/950/comments"] = []
    second = tmp_path / "second"
    second.mkdir()
    result, calls, _ = run(second, data)
    assert result.returncode == 0, result.stderr
    assert not any("PATCH" in call for call in calls)
    assert f"api -X POST repos/{REPO}/issues -f title={TITLE} -F body=@" in "\n".join(calls)

    # A report the owner published (the script run by hand) is edited too
    data[ISSUES.format(REPO)][-1] = issue(950, TITLE, 7, "DigiMonk73")
    third = tmp_path / "third"
    third.mkdir()
    result, calls, _ = run(third, data)
    assert any(call.startswith(f"api -X PATCH repos/{REPO}/issues/950 ") for call in calls)


@needs_jq
def test_in_actions_it_links_the_run_and_signs_as_the_workflow(tmp_path):
    env = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_RUN_ID": "123",
    }
    result, _, body = run(tmp_path, fixtures(), env=env)
    assert result.returncode == 0, result.stderr
    assert f"(https://github.com/{REPO}/actions/runs/123)" in body
    assert body.rstrip().endswith("— the Monday report (GitHub Actions)")


@needs_jq
def test_a_repository_it_cant_read_fails_the_run_after_publishing(tmp_path):
    data = fixtures()
    del data[f"repos/{FORK}"]
    result, calls, body = run(tmp_path, data)
    assert result.returncode == 1
    assert f"Couldn't read {FORK} this week" in body
    assert any("PATCH" in call for call in calls), "the rest is still reported"
    assert "#903" in body


@needs_jq
def test_an_issue_whose_comments_cant_be_read_is_listed_as_unanswered(tmp_path):
    data = fixtures()
    data[f"repos/{REPO}/issues/902/comments"] = {"fail": True}   # the owner did answer it
    result, _, body = run(tmp_path, data)
    assert result.returncode == 1
    assert f"Couldn't read {REPO}#902's comments" in body
    assert "#902" in section(body, "Outside reports with no answer")


@needs_jq
def test_without_the_open_reports_it_cant_be_found_nothing_is_published(tmp_path):
    data = fixtures()
    data[ISSUES.format(REPO)] = {"fail": True}
    result, calls, _ = run(tmp_path, data)
    assert result.returncode == 1
    assert not any("-F body=@" in call for call in calls), "a second report would follow"


@needs_jq
def test_it_reads_every_page(tmp_path):
    data = fixtures()
    page_one = [issue(number, f"Report {number}", 3, "reporter") for number in range(1, 101)]
    page_two = [issue(number, f"Report {number}", 5, "reporter") for number in range(101, 151)]   # older: listed first
    data[ISSUES.format(REPO)] = {"pages": [page_one, page_two]}
    for number in range(1, 151):
        data[f"repos/{REPO}/issues/{number}/comments"] = [{"user": {"login": "DigiMonk73" if number == 120 else "x"}}]
    result, _, _ = run(tmp_path, data, "--dry-run")
    assert result.returncode == 0, result.stderr
    outside = section(result.stdout, "Outside reports with no answer")
    assert "`Report 130`" in outside, "from the second page"
    assert "`Report 120`" not in outside, "answered, on the second page"
    assert "… and 99 more" in outside, "50 are listed, then how many are not"


@needs_jq
def test_a_report_too_long_for_an_issue_is_cut(tmp_path):
    result, _, body = run(tmp_path, fixtures(), env={"REPORT_MAX_BYTES": "900"})
    assert result.returncode == 0, result.stderr
    assert len(body.encode()) < 1100
    assert "The rest is cut" in body and body.rstrip().endswith("— Claude (scripts/monday-report.sh)")


@needs_jq
def test_the_mirror_getting_issues_is_said(tmp_path):
    data = fixtures()
    data[f"repos/{MIRROR}"] = {"has_issues": True}
    data[ISSUES.format(MIRROR)] = [issue(3, "A report on the mirror", 1)]
    data[f"repos/{MIRROR}/issues/3/comments"] = []
    result, _, _ = run(tmp_path, data, "--dry-run")
    assert "**Issues are on now**" in result.stdout
    assert "`A report on the mirror`" in result.stdout

    # Even with nothing else open, the banner doesn't say all is well
    empty = {key: ([] if isinstance(value, list) else value) for key, value in data.items()}
    empty[ISSUES.format(MIRROR)] = []
    (tmp_path / "empty").mkdir()
    result, _, _ = run(tmp_path / "empty", empty, "--dry-run")
    assert "**Issues are on now**" in result.stdout
    assert "Nothing needs attention" not in result.stdout


@needs_jq
def test_it_says_nothing_about_security_advisories_or_a_grok_pass(tmp_path):
    # A public count of waiting advisories would hint at a problem not yet fixed
    result, calls, _ = run(tmp_path, fixtures(), "--dry-run")
    for text in [result.stdout, *calls]:
        assert not re.search(r"advisor|grok|dependabot/alerts", text, re.I)
    code = "\n".join(line for line in SCRIPT.read_text().splitlines() if not line.lstrip().startswith("#"))
    assert not re.search(r"advisor|grok|dependabot/alerts", code, re.I)


def test_the_script_parses_and_refuses_what_it_doesnt_know():
    # /bin/bash is 3.2 on a Mac; CI's bash is 5
    for bash in sorted({"bash"} | ({"/bin/bash"} if Path("/bin/bash").exists() else set())):
        subprocess.run([bash, "-n", str(SCRIPT)], check=True)
    # A typo such as --dryrun must not open a public issue
    run_ = subprocess.run(["bash", str(SCRIPT), "--dryrun"], capture_output=True, text=True)
    assert run_.returncode == 2 and "usage" in run_.stderr


def test_the_workflow_is_weekly_narrow_and_runs_the_script():
    assert "cron: '7 13 * * 1'" in WORKFLOW
    assert "run: scripts/monday-report.sh" in WORKFLOW
    # Only what it needs: read the code, write the one issue, set once for the whole file
    assert WORKFLOW.count("permissions:") == 1
    permissions = re.search(r"^permissions:\n((?:  .*\n)+)", WORKFLOW, re.M).group(1)
    assert permissions.split() == ["contents:", "read", "issues:", "write"]
    assert "persist-credentials: false" in WORKFLOW
    # No secret of its own, and none of the triggers that hand a secret to outside code
    assert "secrets." not in WORKFLOW
    for trigger in ("pull_request_target", "workflow_run", "pull_request:"):
        assert trigger not in WORKFLOW


def test_the_start9_watch_runs_hours_before_the_report_on_the_same_monday():
    minutes = []
    for text in (WATCH, WORKFLOW):
        cron = re.search(r"cron: '(\d+) (\d+) \* \* 1'", text)
        assert cron, "both run on Mondays"
        minutes.append(int(cron.group(2)) * 60 + int(cron.group(1)))
    # Hours, for a late start: the issues it opens are in that week's report
    assert minutes[1] - minutes[0] >= 120


def test_the_watch_looks_back_a_week_and_a_day_when_it_has_no_earlier_issue():
    assert "timedelta(days=8)" in (ROOT / "scripts" / "start9-watch.sh").read_text()


def test_dependabot_is_monthly_grouped_and_targets_staging():
    entries = DEPENDABOT.split("\n  - package-ecosystem:")[1:]
    assert len(entries) == 9
    for entry in entries:
        assert "interval: monthly" in entry
        assert "target-branch: staging" in entry
        assert "groups:" in entry
    assert "interval: weekly" not in DEPENDABOT and "interval: daily" not in DEPENDABOT
