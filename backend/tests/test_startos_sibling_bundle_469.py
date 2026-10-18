"""
#469: the StartOS package imports four constants from its sibling packages
(Start9's service-to-service.md), but Mempool's utils imports Bitcoin Core's
and LND's packages, so their code is in BitcoinTX's bundle: a lockfile change
that moves a sibling can change what ships. Start9's maintaining-a-package.md
("Read the lockfile diff as code review") says to check what landed, and
UPDATING.md's "Bumping the SDK" has each refresh do it.
"""

import json
import re
from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "startos"

# The check UPDATING.md gives: every sibling module the bundler concatenated.
SIBLING_MODULES = "CONCATENATED MODULE: ./node_modules/[a-z-]*-startos"


def refresh_step() -> str:
    """The numbered step of "Bumping the SDK" that refreshes the siblings."""
    text = (PKG / "UPDATING.md").read_text()
    section = text.split("\n## Bumping the SDK\n", 1)[1].split("\n## ", 1)[0]
    steps = re.split(r"\n(?=\d+\. )", section)
    step = next((step for step in steps if "git-resolved" in step), "")
    return " ".join(step.split())  # a re-wrap moves no words


def test_refreshing_the_siblings_checks_what_the_bundle_took():
    step = refresh_step()
    assert "Read the lockfile diff as code review" in step
    assert f"grep '{SIBLING_MODULES}' javascript/index.js" in step
    assert "make javascript/index.js" in step
    assert "before the refresh and after it" in step


def test_the_check_finds_every_sibling_in_the_lockfile():
    # The grep names a sibling by its "-startos" ending: a git-resolved
    # package named otherwise would be in the bundle without being listed.
    lock = json.loads((PKG / "package-lock.json").read_text())["packages"]
    siblings = {
        path.rsplit("node_modules/", 1)[1]
        for path, entry in lock.items()
        if entry.get("resolved", "").startswith("git+")
    }
    assert siblings, "the package imports its constants from sibling packages"
    pattern = SIBLING_MODULES.rsplit("/", 1)[1]
    assert {s for s in siblings if not re.fullmatch(pattern, s)} == set()
