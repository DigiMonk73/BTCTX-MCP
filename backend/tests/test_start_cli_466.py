"""
CI and the release pack btctx.s9pk with the start-cli Start9 packs with
(#466). Start9's builds install the newest start-cli at each build, and from
2.4 start-cli makes the image's SquashFS itself, so a package packed by 2.3
isn't built the way the one users install is. The workflows are read as
text, as in test_pinning.py: no YAML parser is installed for the tests.
"""

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github/workflows"
# The oldest start-cli that builds the image the way Start9's builds do.
OLDEST = (2, 4, 0)


def pins(name: str) -> list[str]:
    return re.findall(r"^\s*START_CLI_VERSION:\s*(\S+)\s*$", (WORKFLOWS / name).read_text(), re.M)


def test_ci_and_the_release_pack_with_the_same_start_cli():
    assert len(pins("ci.yml")) == 1
    assert pins("release.yml") == pins("ci.yml")


def test_the_pinned_start_cli_builds_the_image_as_start9_does():
    pinned = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", pins("ci.yml")[0])
    assert pinned, "START_CLI_VERSION is an exact release, vX.Y.Z"
    assert tuple(map(int, pinned.groups())) >= OLDEST


def test_every_start_cli_download_takes_the_pinned_version():
    for workflow in sorted(WORKFLOWS.glob("*.y*ml")):
        for url in re.findall(r"releases/download/start-cli%2F(\S+?)/", workflow.read_text()):
            assert url == "${START_CLI_VERSION}", f"{workflow.name} downloads start-cli {url}"
