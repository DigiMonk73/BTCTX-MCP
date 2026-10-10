"""
The repository's public promises about bugs and security (AGENTS.md, "Bugs
and security"): a private way to report security problems, bug reports
that ask about tax figures and keep personal data out, and a README that
says where to report. Losing one of these files or lines silently would
break a promise to users.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADVISORY_URL = "https://github.com/DigiMonk73/BTCTX-MCP/security/advisories/new"
TEMPLATES = ROOT / ".github/ISSUE_TEMPLATE"


@pytest.mark.parametrize("name", ["SECURITY.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "LICENSE"])
def test_community_file_is_there(name):
    assert (ROOT / name).is_file(), f"{name} is one of GitHub's community standards"


def test_security_problems_are_reported_privately():
    security = (ROOT / "SECURITY.md").read_text()
    assert ADVISORY_URL in security
    assert "don't open a public issue" in security
    assert ADVISORY_URL in (TEMPLATES / "config.yml").read_text()


def test_bug_form_asks_about_tax_figures_and_keeps_personal_data_out():
    form = (TEMPLATES / "bug_report.yml").read_text()
    assert "Does this change a tax figure?" in form
    assert "I removed personal data" in form
    # the checkbox can't be skipped
    after = form.split("I removed personal data", 1)[1]
    assert after.split("- label:", 1)[0].count("required: true") == 1


def test_blank_issues_go_through_the_forms():
    assert "blank_issues_enabled: false" in (TEMPLATES / "config.yml").read_text()


def test_readme_says_where_to_report():
    readme = (ROOT / "README.md").read_text()
    assert "## Reporting problems" in readme
    section = readme.split("## Reporting problems", 1)[1].split("\n## ", 1)[0]
    for needle in ("issues/new/choose", "label%3Abug", "label%3Atax-figures", "SECURITY.md"):
        assert needle in section, needle
