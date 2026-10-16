"""
The Mac app is built with the Python its macOS jobs set up, 3.11 as the
tests, Docker and StartOS run (#284). desktop/build-mac.sh took the newest
Python it found, and the macOS runner's 3.13 was bundled instead: 1.2.8's
Mac app ran 3.13.15, which only the build-and-launch check exercised. The
workflows are read as text, as in test_release_workflow.py.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILD_MAC = (ROOT / "desktop" / "build-mac.sh").read_text()


def job(workflow: str, name: str) -> str:
    text = (ROOT / ".github" / "workflows" / workflow).read_text()
    found = re.search(rf"^  {name}:\n(.*?)(?=^  \S|\Z)", text, re.M | re.S)
    assert found, f"{workflow} has no job {name}"
    return found.group(1)


@pytest.mark.parametrize("workflow, name", [("ci.yml", "macos-app"), ("release.yml", "macos")])
def test_the_build_takes_the_python_the_job_set_up(workflow, name):
    steps = job(workflow, name)
    setup = re.search(r"uses: actions/setup-python@[0-9a-f]{40} .*\n\s+id: (\w+)\n\s+with:\n"
                      r"\s+python-version: \"([\d.]+)\"", steps)
    assert setup, "setup-python has an id the build can name"
    build = re.search(r"run: \./desktop/build-mac\.sh\n\s+env:\n(?:\s+#.*\n)*"
                      r"\s+BTCTX_BUILD_PYTHON: \$\{\{ steps\.(\w+)\.outputs\.python-path \}\}\n", steps)
    assert build and build.group(1) == setup.group(1)
    docker = re.search(r"^FROM python:([\d.]+)-slim", (ROOT / "Dockerfile").read_text(), re.M)
    assert setup.group(2) == docker.group(1) == "3.11"


def test_build_mac_tries_btctx_build_python_alone():
    """Named, it is the only candidate: no newer Python found here replaces it."""
    assert re.search(r'if \[ -n "\$\{BTCTX_BUILD_PYTHON:-\}" \]; then\n\s+CANDIDATES=\("\$BTCTX_BUILD_PYTHON"\)\n'
                     r"else\n\s+CANDIDATES=\(python3\.13 .*\)\nfi\nfor py in \"\$\{CANDIDATES\[@\]\}\"; do",
                     BUILD_MAC)
    assert "isn't a Python 3.10+" in BUILD_MAC
