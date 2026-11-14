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
@pytest.mark.parametrize("url", ELSEWHERE)
def test_the_browser_script_refuses_another_host_itself(url, tmp_path):
    # The script that types the logins takes its URL from whoever runs it:
    # it checks on its own, before it loads Playwright or writes anything
    out = tmp_path / "out"
    run = subprocess.run(["node", str(GATE / "pages.mjs"), url, str(out)],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 2
    assert f"refused: {url}" in run.stderr and "127.0.0.1" in run.stderr
    assert not out.exists()


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
        assert not re.search(r"\b(AUTH-[123]|BAK-[23]|SEC-8|END-2)\b", row), row
    assert "scripts/gate/pages.py" in by_hand
    for step in PAGE_STEPS:
        assert "scripts/gate/pages.py" in _step_text(guide, step), step


def _last_line(pages, reported, code, ports_kept, capsys):
    ok = pages.verdict(reported, code, ports_kept)
    return ok, capsys.readouterr().out.splitlines()[-1].split(" ", 1)[1]


def _reported(failing=()):
    return [{"id": step, "verdict": "FAIL" if step in failing else "PASS"} for step in PAGE_STEPS]


@pytest.mark.parametrize("reported, code, ports_kept, last", [
    (_reported(), 0, True, "PASS 7 of 7 steps passed"),
    # The browser script exits 1 on any FAIL: the run still ends on its FAIL line
    (_reported({"BAK-2"}), 1, True, "FAIL 6 of 7 steps passed"),
    ([], 1, True, "FAIL 0 of 7 steps passed"),  # it stopped before writing anything
    (_reported(), 3, True, "FAIL 7 of 7 steps passed"),  # it crashed after the last step
    (_reported()[:-1], 0, True, "FAIL 6 of 7 steps passed"),  # a step never reported
    (_reported(), 0, False, "FAIL 7 of 7 steps passed; the owner's ports changed"),
])
def test_the_run_ends_on_one_pass_or_fail_line(reported, code, ports_kept, last, capsys):
    ok, line = _last_line(_pages(), reported, code, ports_kept, capsys)
    assert line == last and ok == last.startswith("PASS")
