"""
The release gate's sign-in and password page checks by script (#935, for
#924): scripts/gate/pages.py runs AUTH-1 to AUTH-3, BAK-2, BAK-3, SEC-8 and
END-2 against the candidate's own image on 127.0.0.1, with test logins, so
they no longer wait for a person. It types those logins only into a page on
127.0.0.1 or localhost; every step it reports is one of docs/AGENT-TESTS.md's;
and the guide gives those steps to the script, not to a person.
"""

import importlib.util
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "gate"
GUIDE = ROOT / "docs" / "AGENT-TESTS.md"
PAGE_STEPS = ("AUTH-1", "AUTH-2", "AUTH-3", "BAK-2", "BAK-3", "SEC-8", "END-2")


def _pages():
    spec = importlib.util.spec_from_file_location("pages", GATE / "pages.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Hosts a test login must never be typed into: the test VM's own name, another
# machine, and names or URLs that only look local
ELSEWHERE = [
    "https://adjective-noun.local",
    "http://192.168.1.20:8080",
    "http://127.0.0.1.example.com",
    "http://localhost.example.com",
    "http://127.0.0.1@example.com",
    "http://example.com/127.0.0.1",
    "http://[::1]:9553",
    "file:///tmp/index.html",
]
HERE = ["http://127.0.0.1:9553", "http://localhost:9553", "https://127.0.0.1:9553/"]


@pytest.mark.parametrize("url", ELSEWHERE)
def test_a_host_other_than_this_computer_is_refused(url):
    with pytest.raises(SystemExit):
        _pages().local_url(url)


@pytest.mark.parametrize("url", HERE)
def test_this_computer_is_taken(url):
    assert _pages().local_url(url) == url.rstrip("/")


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_the_browser_script_refuses_another_host_itself():
    # The script that types the logins checks on its own, before it loads
    # Playwright, for whoever runs it without pages.py
    run = subprocess.run(["node", str(GATE / "pages.mjs"), "https://adjective-noun.local"],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 2
    assert "127.0.0.1" in run.stderr and "adjective-noun.local" in run.stderr


def test_every_step_reported_is_the_guides_and_both_scripts_agree():
    steps = _pages().STEPS
    assert tuple(steps) == PAGE_STEPS
    in_browser = re.findall(r"""\bstep\(\s*["']([A-Z]+-\d+[a-z]?)["']""", (GATE / "pages.mjs").read_text())
    assert in_browser == list(steps)
    guide = GUIDE.read_text()
    for step in steps:
        assert f"- **{step}**" in guide, step


def _step_text(guide, step):
    begin = guide.index(f"- **{step}**")
    end = guide.find("\n- **", begin + 1)
    return guide[begin:end]


def test_the_page_steps_are_the_scripts_not_a_persons():
    guide = GUIDE.read_text()
    by_hand = guide[guide.index("## What stays by hand"):guide.index("## What CI already proves")]
    rows = [line for line in by_hand.splitlines() if line.startswith("|")]
    for row in rows:
        assert not re.search(r"\b(AUTH-\d|BAK-[23]|SEC-8|END-2)\b", row), row
    assert "scripts/gate/pages.py" in by_hand
    for step in PAGE_STEPS:
        assert "scripts/gate/pages.py" in _step_text(guide, step), step
