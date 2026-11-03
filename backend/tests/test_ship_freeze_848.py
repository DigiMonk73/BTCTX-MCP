"""
CI's guard against app code after the last beta (#848,
scripts/check_ship_freeze.py): a pull request into a branch named in
.github/ship-freeze that changes what ships fails unless it's labelled as
the version or an approved fix; and ci.yml runs it, required by "CI passed".
"""

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("check_ship_freeze", ROOT / "scripts" / "check_ship_freeze.py")
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

FROZEN = {"2.1"}


@pytest.mark.parametrize("path", [
    "backend/services/transaction.py", "backend/requirements.txt", "frontend/src/App.tsx",
    "mcp_server/btctx_mcp/server.py", "desktop/entrypoint.py", "startos/startos/manifest/index.ts",
    "Dockerfile", "docker-entrypoint.sh",
])
def test_a_shipped_file_into_a_frozen_branch_fails_naming_it(path):
    why = guard.refusal("2.1", set(), ["docs/USING.md", path], FROZEN)
    assert why and f"  {path}\n" in why and "docs/USING.md" not in why


@pytest.mark.parametrize("path", [
    "backend/tests/test_seed_ledger.py", "frontend/e2e/flows.spec.ts", "frontend/package.json",
    "mcp_server/tests/test_server.py", "scripts/seed_ledger.py", ".github/workflows/ci.yml", "docs/CHANGELOG.md",
])
def test_tests_docs_and_tooling_pass(path):
    assert guard.refusal("2.1", set(), [path], FROZEN) is None


@pytest.mark.parametrize("label", ["version", "approved-fix"])
def test_the_version_or_an_approved_fix_passes(label):
    assert guard.refusal("2.1", {label, "claude"}, ["backend/main.py"], FROZEN) is None


def test_another_label_lets_nothing_in():
    assert guard.refusal("2.1", {"claude", "tax-figures"}, ["backend/main.py"], FROZEN)


def test_a_branch_not_frozen_takes_anything():
    assert guard.refusal("staging", set(), ["backend/main.py"], FROZEN) is None


def test_the_freeze_file_lists_branches_with_comments():
    text = "# the branches past their last beta\n\n2.1   # from beta.3\n  staging\n"
    assert guard.frozen_branches(text) == {"2.1", "staging"}
    assert guard.frozen_branches(guard.FREEZE.read_text()) <= {"staging", "develop", "2.0", "2.1", "main"}


def test_ci_runs_it_on_pull_requests_and_requires_it():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    job = re.search(r"\n  ship-freeze:\n(.*?)\n  [a-z-]+:\n", ci, re.S).group(1)
    assert "scripts/check_ship_freeze.py" in job and "pull_request" in job
    needs = re.search(r"\n  ci-passed:\n.*?needs: \[([^\]]*)\]", ci, re.S).group(1)
    assert "ship-freeze" in [n.strip() for n in needs.split(",")]
