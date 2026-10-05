"""
Everything that builds is pinned exactly (docs/MAINTENANCE.md, "Updating a
dependency"): GitHub Actions by commit, Docker base images by digest, Python
requirements with ==. Dependabot proposes the updates. startos/ keeps Start9's
template files as they are and is not checked here.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github/workflows").glob("*.yml"))
REQUIREMENTS = [
    ROOT / "backend/requirements.txt",
    ROOT / "desktop/requirements.txt",
    ROOT / "requirements-dev.txt",
]


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_actions_are_pinned_to_a_commit(path):
    loose = [
        f"{path.name}:{n}: {line.strip()}"
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if (used := re.search(r"uses:\s*(\S+)", line))
        and not used.group(1).startswith("./")
        and not re.search(r"@[0-9a-f]{40}\s+#\s*v\d", line)
    ]
    assert loose == [], "pin each action to a full commit with its release as a comment: owner/action@<sha> # v1.2.3"


def test_docker_base_images_are_pinned_by_digest():
    froms = [
        line.strip() for line in (ROOT / "Dockerfile").read_text().splitlines()
        if line.strip().startswith("FROM ")
    ]
    loose = [line for line in froms if not re.search(r"\S+:\S+@sha256:[0-9a-f]{64}\b", line)]
    assert froms and loose == [], "pin each base image by tag and digest: python:3.11-slim@sha256:…"


@pytest.mark.parametrize("path", REQUIREMENTS, ids=lambda p: str(p.relative_to(ROOT)))
def test_requirements_are_exact(path):
    loose = [
        line for line in path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
        and not re.match(r"[A-Za-z0-9_.-]+==[^\s#]+(\s+#.*)?$", line)
    ]
    assert loose == [], f"pin with ==: {loose}"
