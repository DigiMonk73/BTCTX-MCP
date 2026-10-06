"""
One rules file for every AI (AGENTS.md, "Working through GitHub"): AGENTS.md at
the repository root, which other AI tools read, and CLAUDE.md only importing
it, so the two can never drift apart. startos/ has the same pair, checked by
test_startos_conformance.py.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_claude_md_only_points_to_agents_md():
    assert (ROOT / "AGENTS.md").is_file()
    assert (ROOT / "CLAUDE.md").read_text().strip() == "@AGENTS.md"
