"""
The Start9 watch (startos/UPDATING.md, "Watching Start9"; the owner,
2026-10-23): daily, and looking at everything the StartOS package must
follow, not only the SDK and start-cli as the weekly check it replaces did.
These read the files; the script itself talks to GitHub and npm, so it's run
by hand with --dry-run, never here.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github" / "workflows" / "start9-watch.yml").read_text()
SCRIPT = ROOT / "scripts" / "start9-watch.sh"


def test_it_runs_daily_and_runs_the_script():
    assert "cron: '23 8 * * *'" in WORKFLOW
    assert "run: scripts/start9-watch.sh" in WORKFLOW
    assert not (ROOT / ".github" / "workflows" / "startos-sdk-check.yml").exists()


def test_it_watches_each_thing_start9_changes():
    calls = [line for line in SCRIPT.read_text().splitlines() if line and not line.startswith((" ", "#", "\t"))]
    for check in ("check_sdk", "check_start_cli", "check_startos", "check_registry", "check_fork"):
        assert check in calls, f"{check} isn't run"
    assert any(c.startswith("check_commits live-docs") for c in calls), "Start9's packaging guide"
    assert any(c.startswith("check_commits master") for c in calls), "Start9's shared package workflows"
    assert 'check_builds "$MIRROR"' in calls


def test_it_reads_develops_pins_and_never_switches_a_checkout():
    text = SCRIPT.read_text()
    assert 'REF="${WATCH_REF:-origin/develop}"' in text
    assert "git checkout" not in text and "git switch" not in text


def test_the_script_parses():
    # /bin/bash is 3.2 on a Mac, where a here-document inside $( ) with an
    # apostrophe in it doesn't parse; CI's bash is 5
    bashes = {"bash"} | ({"/bin/bash"} if Path("/bin/bash").exists() else set())
    for bash in sorted(bashes):
        subprocess.run([bash, "-n", str(SCRIPT)], check=True)


def test_it_refuses_an_argument_it_doesnt_know():
    # A typo such as --dryrun must not open public issues
    run = subprocess.run(["bash", str(SCRIPT), "--dryrun"], capture_output=True, text=True)
    assert run.returncode == 2 and "usage" in run.stderr
