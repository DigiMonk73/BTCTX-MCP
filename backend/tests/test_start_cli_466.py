"""
CI and the release pack btctx.s9pk with the start-cli Start9 packs with
(#466). Start9's builds install the newest start-cli at each build, and from
2.4 start-cli makes the image's SquashFS itself, so a package packed by 2.3
isn't built the way the one users install is. The release signs the package
with that binary, so it runs only once its SHA-256 matches the release notes'.
The workflows are read as text, as in test_pinning.py: no YAML parser is
installed for the tests.
"""

import re
from pathlib import Path

WORKFLOWS = sorted((Path(__file__).resolve().parents[2] / ".github/workflows").glob("*.y*ml"))
# The oldest start-cli that builds the image the way Start9's builds do.
OLDEST = (2, 4, 0)
PIN = re.compile(r"^\s*START_CLI_VERSION:\s*(\S+)\s*(?:#.*)?$", re.M)
SHA256 = re.compile(r"^\s*START_CLI_SHA256:\s*(\S+)\s*(?:#.*)?$", re.M)
# A start-cli release named in a URL or a `gh release` command, written any way
# GitHub takes it.
NAMED_RELEASE = re.compile(r"start-cli(?:%2f|/)v?\d", re.I)
# A line that downloads a start-cli build, whatever the command, or takes
# Start9's install-start-cli action (the newest, unchecked); the comments and
# the weekly check's text only name a build.
DOWNLOAD = re.compile(r"(?:https?://|curl|wget|download).*start-cli_|install-start-cli", re.I)
CHECKED = 'echo "${START_CLI_SHA256}  /usr/local/bin/start-cli" | sha256sum -c -'


def pinned(pattern: re.Pattern) -> dict[str, list[str]]:
    """Each workflow's values for a pin, for the workflows that set it."""
    found = {w.name: pattern.findall(w.read_text()) for w in WORKFLOWS}
    return {name: values for name, values in found.items() if values}


def test_ci_and_the_release_pack_with_the_same_start_cli():
    for pattern in (PIN, SHA256):
        pins = pinned(pattern)
        assert len(pins.get("ci.yml", [])) == 1 and "release.yml" in pins
        assert {value for values in pins.values() for value in values} == set(pins["ci.yml"])


def test_the_pinned_start_cli_builds_the_image_as_start9_does():
    version = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", pinned(PIN)["ci.yml"][0])
    assert version, "START_CLI_VERSION is an exact release, vX.Y.Z"
    assert tuple(map(int, version.groups())) >= OLDEST
    assert re.fullmatch(r"[0-9a-f]{64}", pinned(SHA256)["ci.yml"][0])


def test_every_start_cli_download_takes_the_pin_and_is_checked():
    for workflow in WORKFLOWS:
        lines = workflow.read_text().splitlines()
        for number, line in enumerate(lines):
            if not PIN.match(line):
                assert not NAMED_RELEASE.search(line), f"{workflow.name}:{number + 1} names a start-cli"
            if DOWNLOAD.search(line):
                assert "start-cli%2F${START_CLI_VERSION}/start-cli_x86_64-linux\"" in line
                assert lines[number + 1].strip() == CHECKED, f"{workflow.name}:{number + 2}"
