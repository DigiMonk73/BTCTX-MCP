"""
The to-do discipline (AGENTS.md, "Working through GitHub"; docs/temp/README.md):
to-dos are GitHub issues, so there is no to-do file to keep in step with them.
What's next overall is in docs/ROADMAP.md, and the StartOS package's own
items in startos/TODO.md (Start9's standard file, mirrored to the repository
Start9 forks). Every item there is a checkbox: in the roadmap ticked when done
and cleared at the release that ships it; in startos/TODO.md, Start9's rule,
removed instead (test_startos_conformance.py).
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECKBOX_LISTS = [ROOT / "startos/TODO.md", ROOT / "docs/ROADMAP.md"]


@pytest.mark.parametrize("path", CHECKBOX_LISTS, ids=lambda p: str(p.relative_to(ROOT)))
def test_the_list_exists(path):
    assert path.is_file(), f"{path.relative_to(ROOT)} is missing: keep it, even with nothing pending"


@pytest.mark.parametrize("path", CHECKBOX_LISTS, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_item_is_a_checkbox(path):
    if not path.is_file():
        pytest.skip("missing (the test above says so)")
    lines = path.read_text().splitlines()
    not_boxes = [
        f"{path.name}:{n}: {line}" for n, line in enumerate(lines, 1)
        if re.match(r"[-*] ", line) and not re.match(r"[-*] \[[ x]\] \S", line)
    ]
    assert not_boxes == [], "top-level items are '- [ ] …', or '- [x] …' once done"


def test_todos_are_issues_not_a_file():
    stray = [p.relative_to(ROOT) for p in (ROOT / "docs").rglob("TODO.md")]
    assert stray == [], f"to-dos are GitHub issues (AGENTS.md); move these into issues: {stray}"
