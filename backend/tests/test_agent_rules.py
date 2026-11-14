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


# The short AGENTS.md (#903): every session loads it, so it stays small, and
# its map leads each section it used to hold to the file that holds it now.
AGENTS_LIMIT = 12 * 1024
MOVED = {
    "docs/ARCHITECTURE.md": ("What this is", "Data model", "Key files"),
    "docs/TAX-INVARIANTS.md": ("Tax invariants",),
    "docs/SECURITY-RULES.md": ("Security rules",),
    "docs/TESTING.md": ("Testing",),
    "docs/RELEASING.md": ("Releasing",),
    "docs/START9.md": ("Start9",),
    "docs/BIG-WORK.md": ("Big work",),
    "docs/HOW-CHANGES-FLOW.md": ("Who does what", "Branches", "Pull requests", "Working through GitHub",
                                 "Bugs and security", "Starting a session", "Ending a session"),
}
FIGURES_RULE = (
    "## Reviews",
    "**The figures rule.**",
    "- **No figure moves**",
    "- **A figure moves on purpose**",
    "- **A figure moves that nobody meant to move**",
    "the owner gets a plain-words before-and-after",
)


def agents_md() -> str:
    return (ROOT / "AGENTS.md").read_text()


def test_agents_md_stays_short():
    assert len(agents_md().encode()) < AGENTS_LIMIT, "move the new part to the docs/ file its map names"


def test_the_figures_rule_and_whats_at_stake_stay_in_agents_md():
    text = agents_md()
    for words in FIGURES_RULE + ("## What's at stake", "## Before you change…"):
        assert words in text, words


def test_the_map_names_every_moved_section_and_its_file():
    text = agents_md()
    table = text.split("**Where the rest of this file went**", 1)[1].split("\n## ", 1)[0]
    for path, headings in MOVED.items():
        assert (ROOT / path).is_file(), path
        rows = [row for row in table.splitlines() if f"`{path}`" in row]
        assert rows, f"the map doesn't name {path}"
        moved = (ROOT / path).read_text()
        for heading in headings:
            assert any(f'"{heading}' in row for row in rows), f"{heading} -> {path}"
            assert f"\n## {heading}" in moved, f"{path} has no section {heading}"


def test_the_tax_paths_point_to_the_invariants_first():
    first = agents_md().split("## Before you change…\n", 1)[1].lstrip().split("\n- ", 1)[0]
    for words in ("Tax figures, login, the database", "backend/services/", "backend/migrations/",
                  "testdata/", "docs/TAX-INVARIANTS.md", "docs/SECURITY-RULES.md", '"Reviews"'):
        assert words in first, words


def test_a_path_scoped_rule_names_the_invariants_for_the_tax_paths():
    """Claude Code loads a .claude/rules/ file with `paths:` when a session
    reads or edits a matching file (code.claude.com/docs/en/memory.md)."""
    rule = (ROOT / ".claude/rules/tax-and-security.md").read_text()
    front, body = rule.split("---\n", 2)[1:]
    assert front.startswith("paths:\n")
    for glob in ("backend/services/**/*", "backend/migrations/**/*", "backend/assets/**/*", "testdata/**/*",
                 "backend/*.py", "mcp_server/btctx_mcp/**/*", "Dockerfile"):
        assert f'  - "{glob}"' in front, glob
    for words in ("docs/TAX-INVARIANTS.md", "docs/SECURITY-RULES.md", '"Reviews"'):
        assert words in body, words


# The maintenance lead (the owner, 2026-11-04, #869): a fresh lead starts from
# docs/MAINTENANCE-LEAD.md and #869's kickoff, and each release ends with the
# handoff to the next one. Since 2026-11-09 (the owner) the work runs in a
# monthly cycle of lanes, a sub-session for each kind of work, the lead on
# Fable 5.2 and a lane on Opus 5.5 unless its work needs more.
LEAD = "docs/MAINTENANCE-LEAD.md"


def test_the_maintenance_leads_job_has_its_own_doc():
    text = " ".join((ROOT / LEAD).read_text().split())
    for words in ("## Starting as lead", "## The cycle: three lanes", "| **Updates** |", "| **StartOS** |", "| **Fix** |",
                  'The owner says "start the cycle"', "### The lane brief", "### Which model",
                  "The lead runs on Fable 5.2 at high effort", "runs on Opus 5.5 (or a later Opus release) unless there is a reason",
                  "In force from 2.0.2's handoff", "Never a lane item", "Waiting is the default", "Between cycles",
                  "before anything is pushed", "Never turn on auto-merge", "never to more than two at once",
                  "nothing here loosens them",
                  "Any session may use Fable 5.2 where its own judgement says", "says why in one line",
                  "Never a Sonnet or a Haiku", "### Who talks to whom", "### The board", "## Releases",
                  "go out as soon as the IRS publishes", "I don't necessarily want to claim a freeze", "three rounds in a row",
                  "## What always needs the owner", "## The handoff at each release",
                  "Kickoff prompt for the lead session", '"ready: #N"', 'AGENTS.md`\'s "Reviews"'):
        assert words in text, words


def test_the_map_names_the_maintenance_lead():
    table = agents_md().split("**Where the rest of this file went**", 1)[1].split("\n## ", 1)[0]
    assert f"`{LEAD}`" in table


def test_releasing_ends_with_the_lead_handoff():
    steps = (ROOT / "docs/RELEASING.md").read_text().split("\n## Releasing\n", 1)[1]
    numbered = [line for line in steps.splitlines() if line[:1].isdigit() and ". " in line[:4]]
    last = steps.split(numbered[-1], 1)[1].split("\n\n", 1)[0]
    assert "Hand over to a new lead" in numbered[-1], numbered[-1]
    step = " ".join((numbered[-1] + last).split())  # the words, whatever the line breaks
    for words in ("#41", "Kickoff prompt for the lead session", "session card", f"`{LEAD}`",
                  '"The handoff at each release"'):
        assert words in step, words
