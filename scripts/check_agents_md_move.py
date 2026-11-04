#!/usr/bin/env python3
"""
The proof that M2 (#903) moved AGENTS.md's sections without changing a
byte: every section of the old AGENTS.md (at a git revision) is found,
word for word, in the file the short AGENTS.md's map names for it.

    python scripts/check_agents_md_move.py e7908fc1

Prints each section and where it was found, and exits 1 on the first
section that isn't there unchanged, with the diff.
"""

import difflib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOW = "docs/HOW-CHANGES-FLOW.md"
ARCH = "docs/ARCHITECTURE.md"

# Each old section -> (the file it is in now, its heading there)
MOVES = {
    "What this is": (ARCH, "What this is"),
    "What's at stake": ("AGENTS.md", "What's at stake"),
    "Who does what": (FLOW, "Who does what"),
    "Branches": (FLOW, "Branches"),
    "Before you change…": ("AGENTS.md", "Before you change…"),
    "Data model": (ARCH, "Data model"),
    "Tax invariants (each has regression tests; don't break them)":
        ("docs/TAX-INVARIANTS.md", "Tax invariants (each has regression tests; don't break them)"),
    "Key files": (ARCH, "Key files"),
    "Security rules": ("docs/SECURITY-RULES.md", "Security rules"),
    "Testing (see `docs/TESTING.md`)": ("docs/TESTING.md", "Testing: the rules every session keeps"),
    "Releasing": ("docs/RELEASING.md", "Releasing"),
    "Start9": ("docs/START9.md", "Start9"),
    "Working through GitHub": (FLOW, "Working through GitHub"),
    "Bugs and security": (FLOW, "Bugs and security"),
    "Reviews": ("AGENTS.md", "Reviews"),
    "Pull requests": (FLOW, "Pull requests"),
    "Big work: a main session and numbered sessions": ("docs/BIG-WORK.md", "Big work: a main session and numbered sessions"),
    "Starting a session": (FLOW, "Starting a session"),
    "Ending a session": (FLOW, "Ending a session"),
}


def split(text: str) -> tuple[str, dict[str, str]]:
    """The text before the first `## ` heading, and each section's body
    (the lines after its heading, without the blank lines that end it)."""
    starts = [m.start() for m in re.finditer(r"^## ", text, re.M)]
    found = {}
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        heading, body = text[start + 3:end].split("\n", 1)
        found[heading] = body.strip("\n") + "\n"
    return text[:starts[0]], found


def body_in(path: str, heading: str) -> str:
    """The section under `## heading` in a file now, to the next heading."""
    text = (ROOT / path).read_text()
    marker = f"\n## {heading}\n"
    assert marker in text, f"{path} has no heading '## {heading}'"
    return text.split(marker, 1)[1].split("\n## ", 1)[0] + "\n"


def main(rev: str) -> int:
    old = subprocess.run(["git", "show", f"{rev}:AGENTS.md"], cwd=ROOT, check=True,
                         capture_output=True, text=True).stdout
    preamble, sections = split(old)
    assert sorted(sections) == sorted(MOVES), set(sections) ^ set(MOVES)
    assert (ROOT / "AGENTS.md").read_text().startswith(preamble), "the preamble changed"
    print(f"preamble: AGENTS.md, unchanged ({len(preamble.encode())} bytes)")
    for heading, body in sections.items():
        path, now = MOVES[heading]
        after = body_in(path, now)
        if body not in after:
            sys.stdout.writelines(difflib.unified_diff(
                body.splitlines(True), after[:len(body) + 2000].splitlines(True),
                f"{rev}:AGENTS.md ## {heading}", f"{path} ## {now}"))
            print(f"\nNOT THE SAME: '{heading}'")
            return 1
        print(f"'{heading}': {path}, '## {now}', word for word ({len(body.encode())} bytes)")
    print(f"\nEvery section of {rev}:AGENTS.md is in its new place, byte for byte.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "e7908fc1"))
