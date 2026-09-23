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
    """current.ts is <VERSION>:<package revision>. When VERSION changes, move the
    old current.ts to vX_Y_Z_N.ts first if its migration does work (UPDATING.md)."""
    current = read("startos/startos/versions/current.ts")
    versions = re.findall(r"version: '([^']+)'", current)
    assert len(versions) == 1
    upstream, _, revision = versions[0].partition(":")
    assert upstream == VERSION and revision.isdigit()
