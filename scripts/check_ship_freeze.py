#!/usr/bin/env python3
"""
CI's guard against app code after the last beta (#848): while a branch is
named in .github/ship-freeze, a pull request into it that changes anything
that ships fails, unless it carries the label `version` (the release's
version pull request) or `approved-fix` (a fix the owner or the lead let
in). A pull request titled for CI and tests once carried app code (#842):
this looks at the files, not the title.

    python3 scripts/check_ship_freeze.py BASE LABELS_JSON [FREEZE_FILE] < changed-files.txt

LABELS_JSON is the pull request's labels as `gh pr view --json labels`
gives them; the changed files come one per line. CI hands it the base
branch's freeze file (and runs the base branch's copy of this script), so
a pull request can't lift the freeze by editing either. Exit 1 names the
files.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / ".github" / "ship-freeze"
LETS_IN = {"version", "approved-fix"}

# What ships: the app, the connector, the Mac app, the image, the package
SHIPS = ("backend/", "frontend/src/", "mcp_server/btctx_mcp/", "desktop/", "startos/",
         "Dockerfile", "docker-entrypoint.sh")
# ...except the tests beside the backend's code
NOT_SHIPPED = ("backend/tests/",)


def frozen_branches(text: str) -> set[str]:
    """The branch names the freeze file lists, one per line; # starts a comment."""
    return {line.split("#", 1)[0].strip() for line in text.splitlines()} - {""}


def ships(path: str) -> bool:
    return path.startswith(SHIPS) and not path.startswith(NOT_SHIPPED)


def refusal(base: str, labels: set[str], changed: list[str], frozen: set[str]) -> str | None:
    """Why this pull request may not merge, or None when it may."""
    if base not in frozen or labels & LETS_IN:
        return None
    shipped = [path for path in changed if ships(path)]
    if not shipped:
        return None
    return (f"{base} is past its last beta (.github/ship-freeze), and this pull request changes what ships:\n"
            + "".join(f"  {path}\n" for path in shipped)
            + "Only the version pull request (label `version`) or a fix the owner or the lead approved "
              "(label `approved-fix`) may. Add the label, then re-run this job.")


def main() -> int:
    base, labels_json = sys.argv[1], sys.argv[2]
    freeze = Path(sys.argv[3]) if len(sys.argv) > 3 else FREEZE
    labels = {label["name"] for label in json.loads(labels_json or "[]")}
    changed = [line.strip() for line in sys.stdin if line.strip()]
    frozen = frozen_branches(freeze.read_text()) if freeze.exists() else set()
    why = refusal(base, labels, changed, frozen)
    if why:
        print(why)
        return 1
    if base not in frozen:
        print(f"{base} isn't frozen (.github/ship-freeze): any change may go in")
    else:
        print(f"{base} is frozen: {', '.join(sorted(labels & LETS_IN)) or 'nothing that ships changed'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
