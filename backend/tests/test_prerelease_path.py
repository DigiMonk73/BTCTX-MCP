"""
2.0's beta on GitHub pre-releases (2.0 plan 7.4, B10a, point 1; #532).

A branch prerelease/v2.0.0-beta.N, pushed from 2.0, publishes a GitHub
pre-release: never "Latest", never Docker's :latest or :main, never the
mirror or Start9, the connector on PyPI as a pre-release (2.0.0bN), and a
Mac app that can't be taken for the installed one ("BitcoinTX Beta",
BitcoinTX-Beta-macOS.dmg). A release/ branch publishes a release as before.

The rules are scripts, so they are run here: scripts/release-version.sh
(which branch publishes which version), scripts/image-tags.sh (which Docker
tags a build pushes) and scripts/mac-app.sh identity (what a Mac build may be
called and where it may answer). The workflows are read as text, as in
test_release_workflow.py.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github/workflows"
RELEASE_YML = (WORKFLOWS / "release.yml").read_text()
IMAGE_YML = (WORKFLOWS / "image.yml").read_text()
CI_YML = (WORKFLOWS / "ci.yml").read_text()
CURRENT_TS = "startos/startos/versions/current.ts"


def job(text: str, name: str) -> str:
    """One job of a workflow, up to the next job."""
    found = re.search(rf"^  {name}:\n(.*?)(?=^  \S|\Z)", text, re.M | re.S)
    assert found, f"no job {name}"
    return found.group(1)


def checkout(tmp_path: Path, version: str, package: str, changelog: str = "") -> Path:
    """A copy of the scripts in a folder with these VERSION, current.ts
    version and CHANGELOG sections."""
    (tmp_path / "scripts").mkdir(parents=True)
    for script in ("release-version.sh", "image-tags.sh", "mac-app.sh"):
        shutil.copy(REPO / "scripts" / script, tmp_path / "scripts")
    (tmp_path / "VERSION").write_text(version + "\n")
    (tmp_path / CURRENT_TS).parent.mkdir(parents=True)
    (tmp_path / CURRENT_TS).write_text(f"export const v = VersionInfo.of({{\n  version: '{package}',\n}})\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/CHANGELOG.md").write_text(f"# Changelog\n\n{changelog}\n## [v1.0.0]\n")
    return tmp_path


def run(root: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(root / "scripts" / args[0]), *args[1:]], capture_output=True, text=True,
                          check=False, env={**os.environ, **(env or {})})


def outputs(made: subprocess.CompletedProcess) -> dict[str, str]:
    assert made.returncode == 0, made.stderr
    return dict(line.split("=", 1) for line in made.stdout.splitlines())


# Which branch publishes which version: scripts/release-version.sh

def test_a_release_branch_publishes_a_release_from_main(tmp_path):
    root = checkout(tmp_path, "1.2.11", "1.2.11:0", "## [v1.2.11] - 2026-11-01\n")
    assert outputs(run(root, "release-version.sh", "release/v1.2.11")) == {
        "tag": "v1.2.11", "version": "v1.2.11", "revision": "0", "prerelease": "false",
        "base": "main", "connector": "1.2.11",
    }


def test_a_package_only_revision_is_still_a_release(tmp_path):
    root = checkout(tmp_path, "1.2.11", "1.2.11:1", "## [v1.2.11-1]\n")
    out = outputs(run(root, "release-version.sh", "release/v1.2.11-1"))
    assert (out["tag"], out["revision"], out["prerelease"]) == ("v1.2.11-1", "1", "false")
    made = run(root, "release-version.sh", "release/v1.2.11")
    assert made.returncode == 1 and "say v1.2.11-1" in made.stderr


def test_a_prerelease_branch_publishes_a_beta_from_2_0(tmp_path):
    root = checkout(tmp_path, "2.0.0-beta.3", "2.0.0-beta.3:0", "## [v2.0.0-beta.3] - 2026-11-02\n")
    assert outputs(run(root, "release-version.sh", "prerelease/v2.0.0-beta.3")) == {
        "tag": "v2.0.0-beta.3", "version": "v2.0.0-beta.3", "revision": "0", "prerelease": "true",
        "base": "2.0", "connector": "2.0.0b3",
    }


@pytest.mark.parametrize("version, package, branch, says", [
    # a beta is never published as a release, nor a release as a beta
    ("2.0.0-beta.1", "2.0.0-beta.1:0", "release/v2.0.0-beta.1", "is a pre-release"),
    ("1.2.11", "1.2.11:0", "prerelease/v1.2.11", "is not a beta"),
    # a beta takes no package-only revision: a fix is the next beta
    ("2.0.0-beta.1", "2.0.0-beta.1:1", "prerelease/v2.0.0-beta.1", "takes no package revision"),
    # the branch, VERSION and current.ts agree
    ("2.0.0-beta.1", "2.0.0-beta.1:0", "prerelease/v2.0.0-beta.2", "say v2.0.0-beta.1"),
    ("2.0.0-beta.2", "2.0.0-beta.1:0", "prerelease/v2.0.0-beta.2", "is not 2.0.0-beta.2:<n>"),
    # only betas, numbered from 1
    ("2.0.0-rc.1", "2.0.0-rc.1:0", "prerelease/v2.0.0-rc.1", "is not a beta"),
    ("2.0.0-beta.0", "2.0.0-beta.0:0", "prerelease/v2.0.0-beta.0", "is not a beta"),
    ("2.0.0-beta.01", "2.0.0-beta.01:0", "prerelease/v2.0.0-beta.01", "is not a beta"),
    # nothing else publishes
    ("1.2.11", "1.2.11:0", "v1.2.11", "neither release/ nor prerelease/"),
    ("1.2.11", "1.2.11:0", "draft/v1.2.11", "neither release/ nor prerelease/"),
])
def test_a_branch_that_disagrees_publishes_nothing(tmp_path, version, package, branch, says):
    tag = branch.rpartition("/")[2]
    root = checkout(tmp_path, version, package, f"## [{tag}]\n")
    made = run(root, "release-version.sh", branch)
    assert made.returncode == 1 and says in made.stderr, made.stderr
    assert made.stdout == ""


def test_a_version_without_its_changelog_section_publishes_nothing(tmp_path):
    root = checkout(tmp_path, "2.0.0-beta.1", "2.0.0-beta.1:0", "## [Unreleased 2.0]\n")
    made = run(root, "release-version.sh", "prerelease/v2.0.0-beta.1")
    assert made.returncode == 1 and "no CHANGELOG section for v2.0.0-beta.1" in made.stderr


# Which Docker tags a build pushes: scripts/image-tags.sh

IMAGE = "ghcr.io/digimonk73/btctx-mcp"
SHA = "0123456789abcdef0123456789abcdef01234567"


def image_tags(tmp_path: Path, version: str, ref: str, published: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
    """image-tags.sh with a docker that knows only `published` tags."""
    root = checkout(tmp_path, version, f"{version}:0")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(
        '#!/bin/sh\n[ "$1 $2 $3" = "buildx imagetools inspect" ] || exit 2\n'
        f'for t in {" ".join(published)}; do [ "$4" = "{IMAGE}:$t" ] && exit 0; done\nexit 1\n'
    )
    (bin_dir / "docker").chmod(0o755)
    return run(root, "image-tags.sh", env={
        "PATH": f"{bin_dir}:{os.environ['PATH']}", "IMAGE": IMAGE, "GITHUB_REF": ref, "GITHUB_SHA": SHA,
    })


def tags(made: subprocess.CompletedProcess) -> list[str]:
    out = outputs(made)
    return [t.removeprefix(IMAGE + ":") for t in out["tags"].split(",") if t]


def test_mains_first_build_of_a_release_moves_latest(tmp_path):
    assert tags(image_tags(tmp_path, "1.2.11", "refs/heads/main")) == ["main", "sha-0123456", "v1.2.11", "latest"]


def test_a_published_release_is_never_overwritten(tmp_path):
    assert tags(image_tags(tmp_path, "1.2.11", "refs/heads/main", ("v1.2.11",))) == ["main", "sha-0123456"]
    made = image_tags(tmp_path / "again", "1.2.11", "refs/heads/release/v1.2.11", ("v1.2.11",))
    assert tags(made) == [] and outputs(made)["smoke"] == ""


def test_a_beta_pushes_only_its_own_version_tag(tmp_path):
    made = image_tags(tmp_path, "2.0.0-beta.1", "refs/heads/prerelease/v2.0.0-beta.1")
    assert tags(made) == ["v2.0.0-beta.1"]
    assert outputs(made)["smoke"] == f"{IMAGE}:v2.0.0-beta.1"


def test_a_published_beta_is_never_overwritten(tmp_path):
    made = image_tags(tmp_path, "2.0.0-beta.1", "refs/heads/prerelease/v2.0.0-beta.1", ("v2.0.0-beta.1",))
    assert tags(made) == [] and outputs(made)["smoke"] == ""


@pytest.mark.parametrize("ref", ["refs/heads/main", "refs/heads/2.0", "refs/heads/release/v2.0.0-beta.1",
                                 "refs/heads/prerelease/v2.0.0-beta.2"])
def test_a_beta_is_published_only_from_its_own_prerelease_branch(tmp_path, ref):
    """Never by a push to main or a run started by hand on 2.0: nothing is
    published without the owner's "release"."""
    made = image_tags(tmp_path, "2.0.0-beta.1", ref)
    assert made.returncode == 1 and "prerelease/v2.0.0-beta.1" in made.stderr
    assert made.stdout == ""


@pytest.mark.parametrize("version", ["2.0.0-rc.1", "2.0.0-beta.0", "2.0", "v1.2.11", "1.2.11-1"])
def test_any_other_version_publishes_nothing(tmp_path, version):
    made = image_tags(tmp_path, version, "refs/heads/main")
    assert made.returncode == 1 and "bad VERSION" in made.stderr


# What a Mac build may be called and where it may answer: scripts/mac-app.sh identity

def identity(tmp_path: Path, version: str, name: str, bundle_id: str, port: str) -> subprocess.CompletedProcess:
    return run(checkout(tmp_path, version, f"{version}:0"), "mac-app.sh", "identity", name, bundle_id, port)


def test_a_release_build_is_bitcointx_on_its_fixed_port(tmp_path):
    assert identity(tmp_path, "1.2.11", "BitcoinTX", "org.bitcointx.desktop", "8765").returncode == 0
    for n, wrong in enumerate((("BitcoinTX Beta", "org.bitcointx.desktop", "8765"),
                               ("BitcoinTX", "org.bitcointx.beta", "8765"), ("BitcoinTX", "org.bitcointx.desktop", "8767"))):
        made = identity(tmp_path / str(n), "1.2.11", *wrong)
        assert made.returncode == 1, wrong


def test_a_beta_build_is_never_the_installed_app(tmp_path):
    assert identity(tmp_path, "2.0.0-beta.1", "BitcoinTX Beta", "org.bitcointx.desktop.beta", "8767").returncode == 0
    for n, (wrong, says) in enumerate((
        (("BitcoinTX", "org.bitcointx.desktop.beta", "8767"), "the installed app's name"),
        # macOS folders ignore case: bitcointx.app would replace BitcoinTX.app
        (("bitcointx", "org.bitcointx.desktop.beta", "8767"), "the installed app's name"),
        (("BitcoinTX Beta", "org.bitcointx.desktop", "8767"), "the installed app's bundle id"),
        (("BitcoinTX Beta", "ORG.bitcointx.Desktop", "8767"), "the installed app's bundle id"),
        (("BitcoinTX Beta", "org.bitcointx.desktop.beta", "8765"), "the installed app's port"),
        (("BitcoinTX Beta", "org.bitcointx.desktop.beta", "8766"), "desktop/run-test-build.sh's port"),
    )):
        made = identity(tmp_path / str(n), "2.0.0-beta.1", *wrong)
        assert made.returncode == 1 and says in made.stderr, (wrong, made.stderr)


def test_the_mac_check_never_runs_off_githubs_runners(tmp_path):
    """It opens the build's own data folder: a 1.x build's is the installed
    app's, the owner's real ledger. Off CI, a build runs only through
    desktop/run-test-build.sh."""
    root = checkout(tmp_path, "1.2.11", "1.2.11:0")
    for command in ("check", "package"):
        made = run(root, "mac-app.sh", command, env={"CI": "", "GITHUB_ACTIONS": ""})
        assert made.returncode == 1 and "only on GitHub's runners" in made.stderr, command


# The workflows

def test_a_prerelease_branch_starts_the_release_workflow():
    assert re.search(r"^    branches: \['release/v\*', 'prerelease/v\*'\]$", RELEASE_YML, re.M)


def test_the_commit_is_on_main_for_a_release_and_on_2_0_for_a_beta():
    check = job(RELEASE_YML, "check")
    assert 'scripts/release-version.sh "$GITHUB_REF_NAME" > version.env' in check
    assert 'git merge-base --is-ancestor "$GITHUB_SHA" "origin/$base"' in check
    # the outputs are written only once every check has passed
    assert check.index("--is-ancestor") < check.index('scripts/release-notes.sh "$tag" > /dev/null') \
        < check.index('cat version.env >> "$GITHUB_OUTPUT"')
    for output in ("tag", "version", "revision", "prerelease", "connector"):
        assert f"{output}: ${{{{ steps.v.outputs.{output} }}}}" in check, output


def test_a_beta_never_reaches_the_mirror_or_start9():
    check = job(RELEASE_YML, "check")
    start9 = check[check.index("- name: Start9's changes"):]
    assert start9.index("if: steps.v.outputs.prerelease == 'false'") < start9.index("scripts/start9-pull.sh --check")
    assert "if: needs.check.outputs.prerelease == 'false'" in job(RELEASE_YML, "mirror").split("steps:")[0]


def test_a_beta_keeps_the_price_historys_age_check_and_goes_to_pypi():
    """Only a package-only revision (-N) ships the history it had and skips
    PyPI, which never takes a version twice; a beta's tag has a '-' too."""
    prices = job(RELEASE_YML, "check").split("The hourly price history")[1]
    assert 'if [ "$REVISION" != 0 ]; then age=(--no-age-check)' in prices
    assert "*-*" not in prices
    assert "if: needs.check.outputs.exists == 'false' && needs.check.outputs.revision == '0'" in job(RELEASE_YML, "pypi")


def test_a_beta_is_a_github_prerelease_never_latest():
    release = job(RELEASE_YML, "release")
    assert 'if [ "$PRERELEASE" = true ]; then kind=(--prerelease --latest=false)' in release
    assert 'gh release create "$TAG" "${kind[@]}"' in release
    assert "pre-release · StartOS package" in release
    # its notes open with what a beta is and how each platform keeps a tester's records
    beta = release[release.index("cat > beta.md"):]
    for words in ("BitcoinTX Beta", "its own empty ledger", "Make a StartOS backup", "a new volume",
                  "never your real data", "docs/MAINTENANCE.md#going-back-to-1x", "beta_report.yml"):
        assert words in beta, words


def test_the_release_notes_name_the_betas_own_downloads():
    release = job(RELEASE_YML, "release")
    assert "uvx btctx-mcp==$CONNECTOR" in release
    assert "\\`$MAC_DMG\\`" in release and "ghcr.io/digimonk73/btctx-mcp:$VERSION" in release


def test_the_image_takes_its_tags_from_the_script():
    tags_step = job(IMAGE_YML, "publish").split("- name: Tags")[1].split("- uses:")[0]
    assert 'scripts/image-tags.sh >> "$GITHUB_OUTPUT"' in tags_step
    assert ":latest" not in tags_step.replace("never :latest", "")


@pytest.mark.parametrize("workflow, name", [("ci.yml", "macos-app"), ("release.yml", "macos")])
def test_both_mac_jobs_take_the_apps_name_port_and_files_from_the_build(workflow, name):
    mac = job((WORKFLOWS / workflow).read_text(), name)
    assert "scripts/mac-app.sh check" in mac
    assert re.search(r'scripts/mac-app\.sh package >> "\$GITHUB_OUTPUT"', mac)
    for fixed in ("BitcoinTX.app", ":8765", "8765/", "BitcoinTX-macOS", "pkill"):
        assert fixed not in mac, fixed
    assert "${{ steps.package.outputs.dmg }}" in mac and "${{ steps.package.outputs.zip }}" in mac


def test_the_release_job_uploads_the_mac_files_the_build_named():
    release = job(RELEASE_YML, "release")
    assert "MAC_DMG: ${{ needs.macos.outputs.dmg }}" in release
    assert "MAC_ZIP: ${{ needs.macos.outputs.zip }}" in release
    assert "dmg: ${{ steps.package.outputs.dmg }}" in job(RELEASE_YML, "macos")


def test_the_beta_report_form_keeps_real_data_and_security_problems_out():
    form = (REPO / ".github/ISSUE_TEMPLATE/beta_report.yml").read_text()
    assert 'labels: ["beta", "unconfirmed"]' in form
    for words in ("Which beta", "StartOS", "macOS app (BitcoinTX Beta)", "Docker", "test ledger",
                  "never post personal data", "SECURITY.md"):
        assert words in form, words
    after = form.split("I removed personal data", 1)[1]
    assert after.split("- label:", 1)[0].count("required: true") == 1
