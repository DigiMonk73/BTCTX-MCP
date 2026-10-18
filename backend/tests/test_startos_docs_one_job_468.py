"""
The StartOS package's documents, one job each (#468). Start9's guide gives
README.md, instructions.md and AGENTS.md one reader each and says the README
repeats neither what StartOS shows nor what instructions.md says
(writing-readmes.md, "Guiding principles"; project-structure.md, "AGENTS.md
and CLAUDE.md"; writing-instructions.md, "What does not belong"). Most of that
is read by hand; these are the parts a script can check, two of them from the
sweep's list of rules a script could check (#436, S5's 10 and 11).
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "startos"
MODELS = PKG / "startos" / "fileModels"


def read(name):
    return (PKG / name).read_text()


def section(heading):
    """A README section's text, from its H2 to the next."""
    return read("README.md").split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]


def model_files():
    """The file each file model maps to (its `subpath`, a literal or a constant)."""
    files = []
    for source in sorted(MODELS.glob("*.ts")):
        text = source.read_text()
        subpath = re.search(r"subpath:\s*(?:'([^']+)'|(\w+))", text)
        assert subpath, f"{source.name} has no subpath"
        name = subpath[1] or re.search(rf"const {subpath[2]} = '([^']+)'", text)[1]
        files.append(name)
    return files


def test_there_are_file_models_to_document():
    assert "store.json" in model_files()


def test_file_models_documents_every_model():
    # writing-readmes.md, "File Models": "For each model: the file it maps
    # to ..., how it is seeded ..., and whether a hand edit survives." The
    # section said "One model" while fileModels/ held two.
    text = section("File Models")
    for name in model_files():
        assert f"`{name}`" in text, f"File Models doesn't name {name}"
    assert "seedStore" in text  # how store.json is seeded
    assert "hand edit" in text


def test_the_quick_reference_lists_every_model():
    yaml = section("Quick Reference for AI Consumers")
    listed = re.search(r"^file_models:\n((?:  - .+\n)+)", yaml, re.M)[1]
    names = [line.split("#")[0].strip().removeprefix("- ") for line in listed.splitlines()]
    assert sorted(names) == sorted(model_files())


def test_actions_leave_their_statuses_to_startos():
    # writing-readmes.md, "Actions": StartOS supplies each action's
    # allowedStatuses (and the rest of its metadata); "Do not restate them."
    statuses = r"(?i)\b(?:only )?while (?:the service is )?stopped\b|\brunning or stopped\b|allowedStatuses"
    assert re.findall(statuses, section("Actions")) == []


def test_the_recalculate_task_claims_no_update_just_happened():
    # The task is raised again after a restore, where no update happened
    # (README, Tasks), so its reason can't say "this update".
    # Prettier writes the text in double quotes when it holds an apostrophe.
    found = re.search(r"reason: i18n\(\s*(['\"])(.+?)\1", (PKG / "startos/init/recalculateTask.ts").read_text(), re.S)
    assert found, "recalculateTask.ts raises no task with a reason"
    assert not re.search(r"(?i)\bthis update\b", found[2])


def test_readme_links_no_upstream_docs():
    # writing-readmes.md: upstream documentation links "belong only in
    # instructions.md's ## Documentation section" (S5's 10).
    allowed = {"https://github.com/DigiMonk73/BTCTX-MCP", "https://github.com/Start9-Community/BTCTX-StartOS"}
    # Markdown links and autolinks; an address quoted as code isn't a link.
    links = set(re.findall(r"\]\((https?://[^)\s]+)\)|<(https?://[^>\s]+)>", read("README.md")))
    links = {inline or auto for inline, auto in links}
    assert links <= allowed, links - allowed


def test_instructions_use_no_startos_internal_words():
    # writing-instructions.md, "What does not belong": "Internal terminology
    # from the StartOS codebase ("ABI", "task", "manifest", "subcontainer").
    # Use the words a user sees in the UI." Tasks is the UI's own word for a
    # task, so it stays (S5's 11).
    text = read("instructions.md")
    assert re.findall(r"(?i)\bsubcontainers?\b|\bmanifest\b|\bABI\b", text) == []
