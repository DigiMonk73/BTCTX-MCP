"""
What we name to build with is pinned exactly (docs/MAINTENANCE.md, "Updating a
dependency"): GitHub Actions by commit, Docker base images by digest, Python
requirements with ==. The AI connector, installed next to other software, takes
ranges instead, each capped below the next major version. Dependabot proposes
the updates, so each line must also stay in a form Dependabot reads. startos/ keeps Start9's template files as they
are and is not checked here.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github/workflows").glob("*.y*ml"))
REQUIREMENTS = [
    ROOT / "backend/requirements.txt",
    ROOT / "desktop/requirements.txt",
    ROOT / "requirements-dev.txt",
]

USES = re.compile(r"^\s*-?\s*uses:\s*[\"']?([^\s\"'#]+)")
# Dependabot's docker parser only reads a FROM at the start of the line.
FROM = re.compile(r"^FROM\s+(--platform=\S+\s+)?[^\s@:]+:[^\s@]+@sha256:[0-9a-f]{64}(\s|$)")
REQUIREMENT = re.compile(r"^[A-Za-z0-9_.-]+(\[[^\]]+\])?==[^\s#*;,]+(\s*;[^#]*)?(\s+#.*)?$")


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_actions_are_pinned_to_a_commit(path):
    loose = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        used = USES.match(line)
        if not used or used.group(1).startswith("./"):
            continue
        ref = used.group(1)
        pinned = re.fullmatch(r"[^@]+@[0-9a-f]{40}", ref) and re.search(r"#\s*v?\d", line)
        if ref.startswith("docker://"):
            pinned = "@sha256:" in ref
        if not pinned:
            loose.append(f"{path.name}:{n}: {line.strip()}")
    assert loose == [], "pin each action to a full commit with its release as a comment: owner/action@<sha> # v1.2.3"


def test_docker_base_images_are_pinned_by_digest():
    lines = (ROOT / "Dockerfile").read_text().splitlines()
    froms = [line for line in lines if line.lstrip().upper().startswith("FROM ")]
    loose = [line for line in froms if not FROM.match(line)]
    assert froms and loose == [], (
        "each FROM starts the line (Dependabot skips an indented one) and pins "
        f"tag and digest, python:3.11-slim@sha256:…: {loose}"
    )


@pytest.mark.parametrize("path", REQUIREMENTS, ids=lambda p: str(p.relative_to(ROOT)))
def test_requirements_are_exact(path):
    loose = [
        line for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#") and not REQUIREMENT.match(line)
    ]
    assert loose == [], f"pin with ==: {loose}"


def test_connector_ranges_are_capped():
    tomllib = pytest.importorskip("tomllib")  # Python 3.11+; CI runs it there
    project = tomllib.loads((ROOT / "mcp_server/pyproject.toml").read_text())["project"]
    # tzdata is timezone data numbered by year (2026.4): it is meant to float.
    uncapped = [
        dep for dep in project["dependencies"]
        if not dep.startswith("tzdata") and "<" not in dep and "==" not in dep
    ]
    assert uncapped == [], f"cap each connector dependency below its next major version: {uncapped}"
