"""
What we name to build with is pinned exactly (docs/MAINTENANCE.md, "Pinning"):
GitHub Actions by commit, Docker base images by digest, Python requirements
with ==. What ships (the Docker image, the Mac app, the connector's release
build) installs from locks that hold every indirect package too, with hashes.
The AI connector, installed next to other software, takes ranges instead,
each capped below the next major version. Dependabot proposes the updates, so
each line must also stay in a form Dependabot reads. startos/ keeps Start9's
template files as they are and is not checked here.
"""

import re
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github/workflows").glob("*.y*ml"))
# Each requirements.in and the lock compiled from it (`make lock`).
LOCKED = ["backend", "desktop", ".github/release-tools"]
REQUIREMENTS = [ROOT / d / "requirements.in" for d in LOCKED] + [ROOT / "requirements-dev.txt"]
# The command `make lock` runs, as the lock's header records it: Dependabot
# re-runs it from there, so every platform (--universal) and Python >= 3.10
# stays covered when it updates a lock.
LOCK_COMMAND = (
    "uv pip compile --universal --python-version 3.10 --generate-hashes "
    "requirements.in --output-file requirements.txt"
)
INSTALLERS = [ROOT / "Dockerfile", ROOT / "desktop/build-mac.sh", *WORKFLOWS]
# What may be installed without hashes: the dev tools (pinned, not shipped)
# and the connector under test.
UNHASHED = {"-r", "requirements-dev.txt", "./mcp_server"}

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
        if line.strip() and not line.lstrip().startswith(("#", "-c "))
        and not REQUIREMENT.match(line)
    ]
    assert loose == [], f"pin with ==: {loose}"


def locked_entries(directory: str) -> list[tuple[str, str, str]]:
    """(name, version, the entry's text) for each package in a lock."""
    text = (ROOT / directory / "requirements.txt").read_text()
    entries = re.split(r"\n(?=[A-Za-z0-9])", text.split("\n", 2)[2])
    return [(*re.match(r"([^=\s]+)==([^\s;]+)", e).groups(), e) for e in entries]


def locked_versions(directory: str) -> dict[str, set[str]]:
    versions: dict[str, set[str]] = {}
    for name, version, _ in locked_entries(directory):
        versions.setdefault(canonicalize_name(name), set()).add(version)
    return versions


@pytest.mark.parametrize("directory", LOCKED)
def test_locks_hold_hashes_for_every_platform(directory):
    header = (ROOT / directory / "requirements.txt").read_text().splitlines()[1]
    assert header == f"#    {LOCK_COMMAND}", f"recompile {directory}/requirements.txt with `make lock`"
    unhashed = [name for name, _, entry in locked_entries(directory) if "--hash=sha256:" not in entry]
    assert unhashed == [], f"every package in the lock needs its hashes: {unhashed}"


@pytest.mark.parametrize("directory", LOCKED)
def test_locks_match_their_pins(directory):
    locked = locked_versions(directory)
    stale = []
    for line in (ROOT / directory / "requirements.in").read_text().splitlines():
        line = line.split("#")[0].strip()
        if not line or line.startswith("-c "):
            continue
        req = Requirement(line)
        if {spec.version for spec in req.specifier} != locked.get(canonicalize_name(req.name), set()):
            stale.append(str(req))
    assert stale == [], f"{directory}/requirements.txt is older than its pins: run `make lock` ({stale})"


def test_mac_lock_agrees_with_the_backend_lock():
    """The Mac build installs both locks together, so a package in both is one version."""
    backend, desktop = locked_versions("backend"), locked_versions("desktop")
    differ = {name: (backend[name], desktop[name]) for name in backend.keys() & desktop.keys()
              if backend[name] != desktop[name]}
    assert differ == {}, f"run `make lock`: desktop/ is held to backend/'s versions ({differ})"


@pytest.mark.parametrize("path", INSTALLERS, ids=lambda p: p.name)
def test_installs_check_hashes(path):
    unchecked = [
        line.strip() for line in path.read_text().splitlines()
        if re.search(r"\bpip install\b", line) and "--require-hashes" not in line
        and not set(line.split("pip install", 1)[1].split("#")[0].split()) <= UNHASHED
    ]
    assert unchecked == [], f"install from a lock with --require-hashes: {unchecked}"


def test_docker_image_installs_the_lock_without_building():
    install = next(line for line in (ROOT / "Dockerfile").read_text().splitlines() if "pip install" in line)
    assert "--require-hashes" in install and "--only-binary :all:" in install
    assert install.endswith("-r requirements.txt")


def test_connector_release_builds_inside_its_setuptools_range():
    tomllib = pytest.importorskip("tomllib")
    build_system = tomllib.loads((ROOT / "mcp_server/pyproject.toml").read_text())["build-system"]
    (setuptools,) = map(Requirement, build_system["requires"])
    assert any(spec.operator == "<" for spec in setuptools.specifier), "cap setuptools below its next major"
    (locked,) = locked_versions(".github/release-tools")["setuptools"]
    assert locked in setuptools.specifier, (
        f"release.yml builds with setuptools {locked}, outside mcp_server/pyproject.toml's {setuptools.specifier}"
    )


def test_connector_ranges_are_capped():
    tomllib = pytest.importorskip("tomllib")  # Python 3.11+; CI runs it there
    project = tomllib.loads((ROOT / "mcp_server/pyproject.toml").read_text())["project"]
    # tzdata is timezone data numbered by year (2026.4): it is meant to float.
    uncapped = [
        dep for dep in map(Requirement, project["dependencies"])
        if dep.name != "tzdata"
        and not any(spec.operator in ("<", "<=", "==", "~=") for spec in dep.specifier)
    ]
    assert uncapped == [], f"cap each connector dependency below its next major version: {uncapped}"
