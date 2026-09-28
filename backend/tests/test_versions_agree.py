"""
backend/tests/test_versions_agree.py

VERSION is the one version for the app, the Docker image, the macOS app and
the StartOS package. The places that must repeat it as a literal are checked
here, so a release can't ship an s9pk that pulls the previous image.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VERSION = (REPO / "VERSION").read_text().strip()


def read(rel: str) -> str:
    return (REPO / rel).read_text()


def test_version_file_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", VERSION)


def test_macos_app_version():
    spec = read("desktop/BitcoinTX.spec")
    assert re.findall(r'"CFBundle(?:Short)?Version(?:String)?": "([^"]+)"', spec) == [VERSION, VERSION]


def test_startos_image_tag():
    manifest = read("startos/startos/manifest/index.ts")
    assert re.findall(r"dockerTag: '([^']+)'", manifest) == [f"ghcr.io/digimonk73/btctx-mcp:v{VERSION}"]


def test_startos_package_version():
    """current.ts is <VERSION>:<package revision>. When its version changes, move
    the old current.ts to vX.Y.Z_N.ts first if its migration does work (UPDATING.md)."""
    current = read("startos/startos/versions/current.ts")
    versions = re.findall(r"version: '([^']+)'", current)
    assert len(versions) == 1
    upstream, _, revision = versions[0].partition(":")
    assert upstream == VERSION and revision.isdigit()


def test_mcp_connector_version():
    """The connector has the app's version, so it can tell the user when the
    one their AI app runs doesn't match their BitcoinTX (btctx_mcp/server.py)."""
    pyproject = read("mcp_server/pyproject.toml")
    assert re.findall(r'^version = "([^"]+)"', pyproject, re.M) == [VERSION]
