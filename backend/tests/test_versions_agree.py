"""
backend/tests/test_versions_agree.py

VERSION is the one version for the app, the Docker image, the macOS app and
the StartOS package. The places that must repeat it as a literal are checked
here, so a release can't ship an s9pk that pulls the previous image.

A 2.0 pre-release (2.0 plan 7.4, B10a; #251's decision 28: alphas, then
betas) has VERSION X.Y.Z-alpha.N or X.Y.Z-beta.N, which each place writes in
its own form: Apple takes only numbers for a bundle's version (X.Y.Z), PyPI
the PEP 440 form (X.Y.ZaN, X.Y.ZbN), StartOS the ExVer one (X.Y.Z-alpha.N:0,
X.Y.Z-beta.N:0) and the image tag VERSION itself.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "desktop"))
import desktop_paths  # noqa: E402
import desktop_ports  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
VERSION = (REPO / "VERSION").read_text().strip()
FORM = re.compile(r"(\d+\.\d+\.\d+)(?:-(alpha|beta)\.([1-9]\d*))?")


def forms(version: str) -> dict[str, str]:
    """How each place writes `version`: a release X.Y.Z, or a pre-release
    X.Y.Z-alpha.N or X.Y.Z-beta.N."""
    found = FORM.fullmatch(version)
    assert found, f"VERSION {version} is neither X.Y.Z nor X.Y.Z-alpha.N or X.Y.Z-beta.N"
    release, stage, n = found.groups()
    return {
        "bundle": release,
        "image": f"v{version}",
        "package": version,
        "connector": f"{release}{stage[0]}{n}" if stage else release,
    }


@pytest.mark.parametrize("version, expected", [
    ("1.2.10", {"bundle": "1.2.10", "image": "v1.2.10", "package": "1.2.10", "connector": "1.2.10"}),
    ("2.0.0-beta.3", {"bundle": "2.0.0", "image": "v2.0.0-beta.3", "package": "2.0.0-beta.3",
                      "connector": "2.0.0b3"}),
    ("2.0.0-alpha.2", {"bundle": "2.0.0", "image": "v2.0.0-alpha.2", "package": "2.0.0-alpha.2",
                       "connector": "2.0.0a2"}),
])
def test_each_place_writes_a_version_in_its_own_form(version, expected):
    assert forms(version) == expected


@pytest.mark.parametrize("version", ["2.0", "2.0.0-rc.1", "2.0.0-beta.0", "2.0.0-beta.01", "2.0.0-alpha.0",
                                     "2.0.0b1", "2.0.0a1", "2.0.0-alpha", "v1.2.10"])
def test_only_a_release_or_a_pre_release_is_a_version(version):
    with pytest.raises(AssertionError, match="neither"):
        forms(version)


def read(rel: str) -> str:
    return (REPO / rel).read_text()


def test_version_file_is_a_release_or_a_pre_release():
    forms(VERSION)


def test_macos_app_version():
    spec = read("desktop/BitcoinTX.spec")
    bundle = forms(VERSION)["bundle"]
    assert re.findall(r'"CFBundle(?:Short)?Version(?:String)?": "([^"]+)"', spec) == [bundle, bundle]


def test_macos_apps_minimum_is_what_its_binary_needs():
    """The app is built on Apple silicon, arm64 only, whose binary needs
    macOS 11 (every Apple-silicon Mac has it): the bundle said 10.15, and the
    docs with it (#534)."""
    spec = read("desktop/BitcoinTX.spec")
    assert re.findall(r'"LSMinimumSystemVersion": "([^"]+)"', spec) == ["11.0"]
    assert "minimum macOS 11.0," in " ".join(read("docs/MACOS_DESKTOP_APP.md").split())


def test_startos_image_tag():
    manifest = read("startos/startos/manifest/index.ts")
    assert re.findall(r"dockerTag: '([^']+)'", manifest) == [f"ghcr.io/digimonk73/btctx-mcp:{forms(VERSION)['image']}"]


def test_startos_package_version():
    """current.ts is <VERSION>:<package revision>, a pre-release's always 0 (a
    fix is the next pre-release). When its version changes, move the old current.ts to
    vX.Y.Z_N.ts first if its migration does work (UPDATING.md)."""
    current = read("startos/startos/versions/current.ts")
    versions = re.findall(r"version: '([^']+)'", current)
    assert len(versions) == 1
    upstream, _, revision = versions[0].partition(":")
    assert upstream == forms(VERSION)["package"] and revision.isdigit()
    if upstream != forms(upstream)["bundle"]:
        assert revision == "0"


def test_mcp_connector_version():
    """The connector has the app's version, so it can tell the user when the
    one their AI app runs doesn't match their BitcoinTX (btctx_mcp/server.py)."""
    pyproject = read("mcp_server/pyproject.toml")
    assert re.findall(r'^version = "([^"]+)"', pyproject, re.M) == [forms(VERSION)["connector"]]


def test_a_release_build_is_the_installed_app_again(monkeypatch, tmp_path):
    """VERSION without a suffix makes the Mac build BitcoinTX, not BitcoinTX
    Preview: the name, bundle id, plain icon, port and data folder 1.x users
    have, so 2.0.0 replaces the app and upgrades its ledger (2.0 plan 6.3)."""
    assert forms(VERSION)["package"] == forms(VERSION)["bundle"], "VERSION is a pre-release"
    monkeypatch.delenv(desktop_paths.DATA_DIR_ENV, raising=False)
    monkeypatch.delenv("BTCTX_DESKTOP_PORT", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert not desktop_paths.is_preview()
    assert desktop_paths.own_name() == "BitcoinTX"
    assert desktop_paths.bundle_id() == "org.bitcointx.desktop"
    assert desktop_paths.icon_name() == "icon.icns"
    assert desktop_ports.preferred_port() == 8765
    assert desktop_paths.data_dir() == tmp_path / "Library" / "Application Support" / "BitcoinTX"
    made = subprocess.run(["bash", str(REPO / "scripts/mac-app.sh"), "identity", "BitcoinTX", "org.bitcointx.desktop",
                           "8765"], capture_output=True, text=True, check=False)
    assert made.returncode == 0, made.stderr
