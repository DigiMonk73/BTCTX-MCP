"""
The developer documents for 2.0 (#807, docs step D6 and D7a of
docs/temp/2.0-docs.md): no count that goes out of date as tests are added,
the records in docs/archive/ with nothing pointing at their old places, and
the owner's rules for pull requests from outside (2026-10-29, #799) in both
places a contributor or a session reads them.
"""

import re

from backend.tests.test_test_files import needs_a_checkout
from backend.tests.test_texts_2_0_357 import ROOT, flat, tracked

# "~3,200 tests" stayed in three documents long after the fast suite passed
# 4,500: a count of tests is only true the day it's written
TEST_COUNT = re.compile(r"~?\d(?:[\d,]*\d)?\s+(?:hermetic |unit and integration |unit |integration )?tests\b", re.I)
# History says how many tests a change had then, and that stays true
HISTORY = ("docs/CHANGELOG.md", "docs/temp/", "docs/archive/")
# Session 54's version pull request rewrites the rest of this file; its
# line 44 follows once that has merged (#807's guardrail)
COUNT_NOT_YET = {"docs/AGENT-TESTS.md"}

# Records, not guides: their old place -> where they are now
ARCHIVED = {
    "docs/HARDENING_FINDINGS.md": "docs/archive/HARDENING_FINDINGS.md",
    "docs/startos-research/": "docs/archive/startos-research/",
}
PRIVACY_AUDIT_1_2_1 = "docs/archive/PRIVACY_AUDIT_1.2.1.md"


def section(text: str, heading: str) -> str:
    """One `## heading` section of a Markdown file, as words."""
    assert f"\n## {heading}\n" in text, heading
    return flat(text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0])


@needs_a_checkout
def test_no_document_counts_the_tests():
    found = [f"{path}: {hit.group(0)}"
             for path in tracked()
             if path.endswith(".md") and not path.startswith(HISTORY) and path not in COUNT_NOT_YET
             for hit in TEST_COUNT.finditer((ROOT / path).read_text())]
    assert not found, found


def test_a_file_waiting_for_its_turn_still_counts_them():
    """Once its count is gone, it comes off the list, so the check above
    covers it from then on."""
    for path in COUNT_NOT_YET:
        assert TEST_COUNT.search((ROOT / path).read_text()), f"{path}: take it off COUNT_NOT_YET"


@needs_a_checkout
def test_the_records_are_in_the_archive():
    files = tracked()
    for old, new in ARCHIVED.items():
        assert not any(path.startswith(old) for path in files), old
        assert any(path.startswith(new) for path in files), new
    assert PRIVACY_AUDIT_1_2_1 in files
    assert "\n## The 1.2.1 audit" not in (ROOT / "docs/PRIVACY_AUDIT.md").read_text()


@needs_a_checkout
def test_nothing_points_at_an_archived_records_old_place():
    """Its old path, outside history and this test."""
    this_test = "backend/tests/test_dev_docs_807.py"
    found = [f"{path}: {old}"
             for path in tracked()
             if not path.startswith(HISTORY) and path != this_test and (ROOT / path).is_file()
             for old in ARCHIVED
             if old in _text(path)]
    assert not found, found


def _text(path: str) -> str:
    try:
        return (ROOT / path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def test_contributing_says_which_pull_requests_from_outside_are_taken():
    """The owner, 2026-10-29: tests or docs only, read line by line, CI
    only after the owner approves it; anything else is redone by us."""
    rules = section((ROOT / "CONTRIBUTING.md").read_text(), "Pull requests from outside")
    for words in ("only tests or documentation", "every line", "approves", "we write it ourselves"):
        assert words in rules, words


def test_start9s_contributions_are_looked_at_first_never_accepted_automatically():
    """The owner, 2026-10-29: verified on GitHub, never by a name; read
    the same day; its CI approved only after that first read."""
    for path, heading in (("CONTRIBUTING.md", "Pull requests from outside"), ("AGENTS.md", "Start9")):
        rules = section((ROOT / path).read_text(), heading)
        for words in ("Start9Labs", "Start9-Community", "never accepted automatically", "the same day", "never by"):
            assert words in rules, f"{path}: {words}"


def test_agents_md_keeps_the_outside_pull_request_rule():
    rules = section((ROOT / "AGENTS.md").read_text(), "Pull requests")
    for words in ("only tests or documentation", "every line", "approves", "CONTRIBUTING.md"):
        assert words in rules, words
