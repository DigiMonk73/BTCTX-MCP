"""
CI runs what a change needs (#985, scripts/ci_changes.py): docs alone skip
the heavy jobs, the click-through tests run when a change is one they can
see, a path the rules don't name runs everything, and ci.yml skips a job
only by the script's word, which "CI passed" alone counts as passed.
"""

import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import ci_changes  # noqa: E402
from ci_changes import HEAVY, docs_tests, skipped  # noqa: E402

CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
EVERYTHING_BUT = lambda *runs: [job for job in HEAVY if job not in runs]  # noqa: E731


def jobs() -> dict[str, str]:
    """ci.yml's jobs: id -> its block."""
    body = CI.split("\njobs:\n", 1)[1]
    parts = re.split(r"^  ([a-z][a-z0-9-]*):\n", body, flags=re.M)
    return dict(zip(parts[1::2], parts[2::2]))


@pytest.mark.parametrize("paths", [
    ["README.md"],
    ["docs/TESTING.md", "docs/images/dashboard.png"],
    ["AGENTS.md", ".claude/rules/tax-and-security.md", ".github/pull_request_template.md"],
    ["mcp_server/AI_SETUP.md"],
])
def test_docs_alone_skip_every_heavy_job(paths):
    assert skipped("pull_request", "develop", paths) == list(HEAVY)


@pytest.mark.parametrize("path", [
    "backend/assets/btc_prices/README.md",  # the app's own folder
    "startos/instructions.md",  # Start9 reviews the package's text
    "testdata/README.md",
    "desktop/README.md",
    "frontend/README.md",
])
def test_markdown_the_app_or_the_package_holds_is_not_docs(path):
    assert "python" not in skipped("pull_request", "develop", ["README.md", path])


@pytest.mark.parametrize("path", [
    "Dockerfile", "VERSION", "a-new-folder/anything.txt", "requirements-dev.txt", ".githooks/pre-push",
    "scripts/smoke_test.py", "backend/main.py", "frontend/src/App.tsx",
])
def test_a_path_the_rules_dont_name_runs_everything(path):
    assert skipped("pull_request", "develop", ["docs/TESTING.md", path]) == []


@pytest.mark.parametrize("path", [
    "startos/startos/manifest.ts", "mcp_server/btctx_mcp/server.py", "desktop/launcher.py",
    ".github/workflows/irs-forms-watch.yml", ".github/dependabot.yml",
])
def test_a_change_the_browsers_cant_see_skips_only_the_click_through_tests(path):
    assert skipped("pull_request", "develop", [path, "README.md"]) == ["e2e"]


@pytest.mark.parametrize("path", [
    ".github/workflows/ci.yml", "scripts/ci_changes.py", "frontend/e2e/fixtures.ts", "backend/tests/test_x.py",
])
def test_the_app_the_tests_and_ci_itself_run_the_click_through_tests(path):
    assert "e2e" not in skipped("pull_request", "develop", ["mcp_server/README.md", path])


@pytest.mark.parametrize("event", ["push", "workflow_dispatch", "schedule"])
def test_a_push_or_a_run_by_hand_skips_nothing(event):
    assert skipped(event, "", ["README.md"]) == []


def test_a_pull_request_with_no_file_changed_skips_nothing():
    assert skipped("pull_request", "develop", []) == []


def test_into_2_0_the_medium_set():
    assert skipped("pull_request", "2.0", ["backend/main.py"]) == ["e2e", "docker", "startos-pack"]
    assert skipped("pull_request", "2.0", ["README.md"]) == list(HEAVY)


def test_it_writes_the_github_output_line(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("README.md\n\nstartos/x.ts\n"))
    out = io.StringIO()
    with redirect_stdout(out):
        assert ci_changes.main(["--event", "pull_request", "--base", "develop"]) == 0
    key, value = out.getvalue().strip().split("=", 1)
    assert key == "skip" and json.loads(value) == ["e2e"]


def test_each_job_the_script_may_skip_is_skipped_by_its_own_id():
    found = jobs()
    for job in HEAVY:
        assert job in found, f"ci.yml has no job {job}"
        if job == "python-guard":  # skipped with the shards it checks
            assert "needs: python\n" in found[job]
            continue
        assert f"if: ${{{{ !contains(fromJSON(needs.changes.outputs.skip), '{job}') }}}}" in found[job], job
        assert re.search(r"needs: (changes\n|\[changes, )", found[job]), job


def test_no_other_job_is_skipped_by_the_script():
    for job, block in jobs().items():
        if job not in HEAVY:
            assert "needs.changes.outputs.skip" not in block or job == "ci-passed", job


def test_ci_passed_needs_every_job_but_the_macos_build_and_its_audit():
    block = jobs()["ci-passed"]
    needs = re.search(r"needs: \[([^\]]*)\]", block).group(1)
    listed = {job.strip() for job in needs.split(",")}
    assert listed == set(jobs()) - {"ci-passed", "macos-app", "audit-macos"}
    assert "SKIP: ${{ needs.changes.outputs.skip || '[]' }}" in block
    assert 'if: always()' in block and "name: CI passed\n" in block


def test_one_python_suite_and_the_connector_on_its_oldest():
    found = jobs()
    assert 'python: ["3.13"]' in found["python"]
    assert 'python-version: "3.11"' in found["connector"] and "pytest -q -n auto mcp_server/tests" in found["connector"]
    connector = (ROOT / "mcp_server" / "pyproject.toml").read_text()
    assert 'requires-python = ">=3.11"' in connector


def test_the_docs_job_runs_on_every_change_with_the_lint():
    block = jobs()["docs"]
    assert "needs:" not in block and "if:" not in block
    assert "ruff check ." in block and "ci_changes.py --docs-tests | xargs pytest" in block


def test_the_tests_that_read_the_docs():
    found = docs_tests()
    for test in ("backend/tests/test_disclaimer.py", "backend/tests/test_agent_rules.py",
                 "mcp_server/tests/test_connector_docs_699.py",
                 "backend/tests/test_hand_test_guide_844.py"):  # through hand_test_tables.py
        assert test in found, test
    assert all((ROOT / test).is_file() for test in found)
    assert "backend/tests/test_seed_ledger.py" not in found
