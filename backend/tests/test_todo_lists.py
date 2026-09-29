"""
The to-do discipline (owner decision 2026-09-29; CLAUDE.md and
docs/temp/README.md): specific to-dos live in docs/temp/TODO.md, the StartOS
package's in startos/TODO.md (Start9's standard file, mirrored to the
repository Start9 forks), and what's next in docs/ROADMAP.md. Every item is
a checkbox, ticked when done and cleared at the release that ships it.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TODO_LISTS = [ROOT / "docs/temp/TODO.md", ROOT / "startos/TODO.md"]
CHECKBOX_LISTS = TODO_LISTS + [ROOT / "docs/ROADMAP.md"]


@pytest.mark.parametrize("path", TODO_LISTS, ids=lambda p: str(p.relative_to(ROOT)))
def test_the_todo_list_exists(path):
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
