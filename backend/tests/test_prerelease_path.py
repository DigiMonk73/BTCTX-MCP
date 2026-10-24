"""
2.0's alphas and betas on GitHub pre-releases (2.0 plan 7.4, B10a, point 1;
#532; #251's decision 28: alphas first, then betas).

A branch prerelease/v2.0.0-alpha.N or prerelease/v2.0.0-beta.N, pushed from
2.0, publishes a GitHub pre-release: never "Latest", never Docker's :latest
or :main, never the mirror or Start9, the connector on PyPI as a
pre-release (2.0.0aN, 2.0.0bN), and a Mac app that can't be taken for the
installed one ("BitcoinTX Preview", BitcoinTX-Preview-macOS.dmg). A
release/ branch publishes a release as before.

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
import sys
import textwrap
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


def test_a_prerelease_branch_publishes_an_alpha_from_2_0(tmp_path):
    root = checkout(tmp_path, "2.0.0-alpha.2", "2.0.0-alpha.2:0", "## [v2.0.0-alpha.2] - 2026-10-30\n")
    assert outputs(run(root, "release-version.sh", "prerelease/v2.0.0-alpha.2")) == {
        "tag": "v2.0.0-alpha.2", "version": "v2.0.0-alpha.2", "revision": "0", "prerelease": "true",
        "base": "2.0", "connector": "2.0.0a2",
    }


@pytest.mark.parametrize("version, package, branch, says", [
    # a pre-release is never published as a release, nor a release as one
    ("2.0.0-alpha.1", "2.0.0-alpha.1:0", "release/v2.0.0-alpha.1", "is a pre-release"),
    ("2.0.0", "2.0.0:0", "prerelease/v2.0.0", "is not an alpha or a beta"),
    ("2.0.0-beta.1", "2.0.0-beta.1:0", "release/v2.0.0-beta.1", "is a pre-release"),
    ("1.2.11", "1.2.11:0", "prerelease/v1.2.11", "is not an alpha or a beta"),
    # a pre-release takes no package-only revision: a fix is the next one
    ("2.0.0-beta.1", "2.0.0-beta.1:1", "prerelease/v2.0.0-beta.1", "takes no package revision"),
    ("2.0.0-alpha.1", "2.0.0-alpha.1:1", "prerelease/v2.0.0-alpha.1", "takes no package revision"),
    ("2.0.0-alpha.1", "2.0.0-alpha.1:0", "prerelease/v2.0.0-beta.1", "say v2.0.0-alpha.1"),
    # the branch, VERSION and current.ts agree
    ("2.0.0-beta.1", "2.0.0-beta.1:0", "prerelease/v2.0.0-beta.2", "say v2.0.0-beta.1"),
    ("2.0.0-beta.2", "2.0.0-beta.1:0", "prerelease/v2.0.0-beta.2", "is not 2.0.0-beta.2:<n>"),
    # only alphas and betas, numbered from 1
    ("2.0.0-rc.1", "2.0.0-rc.1:0", "prerelease/v2.0.0-rc.1", "is not an alpha or a beta"),
    ("2.0.0-beta.0", "2.0.0-beta.0:0", "prerelease/v2.0.0-beta.0", "is not an alpha or a beta"),
    ("2.0.0-beta.01", "2.0.0-beta.01:0", "prerelease/v2.0.0-beta.01", "is not an alpha or a beta"),
    ("2.0.0-alpha.0", "2.0.0-alpha.0:0", "prerelease/v2.0.0-alpha.0", "is not an alpha or a beta"),
    ("2.0.0-gamma.1", "2.0.0-gamma.1:0", "prerelease/v2.0.0-gamma.1", "is not an alpha or a beta"),
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


def test_an_alpha_pushes_only_its_own_version_tag(tmp_path):
    made = image_tags(tmp_path, "2.0.0-alpha.1", "refs/heads/prerelease/v2.0.0-alpha.1")
    assert tags(made) == ["v2.0.0-alpha.1"]
    made = image_tags(tmp_path / "main", "2.0.0-alpha.1", "refs/heads/main")
    assert made.returncode == 1 and "prerelease/v2.0.0-alpha.1" in made.stderr


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


@pytest.mark.parametrize("version", ["2.0.0-rc.1", "2.0.0-beta.0", "2.0.0-alpha.0", "2.0.0-gamma.1", "2.0",
                                     "v1.2.11", "1.2.11-1"])
def test_any_other_version_publishes_nothing(tmp_path, version):
    made = image_tags(tmp_path, version, "refs/heads/main")
    assert made.returncode == 1 and "bad VERSION" in made.stderr


# What a Mac build may be called and where it may answer: scripts/mac-app.sh identity

def identity(tmp_path: Path, version: str, name: str, bundle_id: str, port: str) -> subprocess.CompletedProcess:
    return run(checkout(tmp_path, version, f"{version}:0"), "mac-app.sh", "identity", name, bundle_id, port)


def test_a_release_build_is_bitcointx_on_its_fixed_port(tmp_path):
    assert identity(tmp_path, "1.2.11", "BitcoinTX", "org.bitcointx.desktop", "8765").returncode == 0
    for n, wrong in enumerate((("BitcoinTX Preview", "org.bitcointx.desktop", "8765"),
                               ("BitcoinTX", "org.bitcointx.beta", "8765"), ("BitcoinTX", "org.bitcointx.desktop", "8767"))):
        made = identity(tmp_path / str(n), "1.2.11", *wrong)
        assert made.returncode == 1, wrong


def test_a_pre_release_build_is_never_the_installed_app(tmp_path):
    assert identity(tmp_path, "2.0.0-beta.1", "BitcoinTX Preview", "org.bitcointx.desktop.preview", "8767").returncode == 0
    assert identity(tmp_path / "a", "2.0.0-alpha.1", "BitcoinTX Preview", "org.bitcointx.desktop.preview",
                    "8767").returncode == 0
    made = identity(tmp_path / "b", "2.0.0-alpha.1", "BitcoinTX", "org.bitcointx.desktop.preview", "8767")
    assert made.returncode == 1 and "the installed app's name" in made.stderr
    for n, (wrong, says) in enumerate((
        (("BitcoinTX", "org.bitcointx.desktop.preview", "8767"), "the installed app's name"),
        # macOS folders ignore case: bitcointx.app would replace BitcoinTX.app
        (("bitcointx", "org.bitcointx.desktop.preview", "8767"), "the installed app's name"),
        (("BitcoinTX Preview", "org.bitcointx.desktop", "8767"), "the installed app's bundle id"),
        (("BitcoinTX Preview", "ORG.bitcointx.Desktop", "8767"), "the installed app's bundle id"),
        (("BitcoinTX Preview", "org.bitcointx.desktop.preview", "8765"), "the installed app's port"),
        (("BitcoinTX Preview", "org.bitcointx.desktop.preview", "8766"), "desktop/run-test-build.sh's port"),
    )):
        made = identity(tmp_path / str(n), "2.0.0-beta.1", *wrong)
        assert made.returncode == 1 and says in made.stderr, (wrong, made.stderr)


def test_the_mac_check_never_runs_off_githubs_runners(tmp_path):
    """It opens the build's own data folder: a 1.x build's is the installed
    app's, the owner's real ledger. Off GitHub's own runners (a self-hosted
    one too), a build runs only through desktop/run-test-build.sh."""
    root = checkout(tmp_path, "1.2.11", "1.2.11:0")
    for command in ("check", "package"):
        for runner in ({"GITHUB_ACTIONS": ""}, {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "self-hosted"}):
            made = run(root, "mac-app.sh", command, env={"RUNNER_ENVIRONMENT": "", **runner})
            assert made.returncode == 1 and "only on GitHub's runners" in made.stderr, (command, runner)


FAKE_APP = """#!{python}
# A stand-in for BitcoinTX Preview: its data folder, then (after a while, as the
# real app takes) an API on a port of its own
import http.server, json, os, pathlib, sys, time
home = pathlib.Path(os.environ["HOME"]) / "Library"
(home / "Application Support" / "BitcoinTX Preview").mkdir(parents=True)
for extra in filter(None, os.environ.get("FAKE_ALSO", "").split(":")):
    (home / extra).mkdir(parents=True)
if os.environ.get("FAKE_QUITS"):
    print("the fake app quit"); sys.exit(3)
time.sleep(1.5)
class Api(http.server.BaseHTTPRequestHandler):
    def answer(self, code, body=b"{{}}"):
        self.send_response(code); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        self.answer(200, json.dumps({{"status": "ok", "version": "2.0.0-beta.1"}}, separators=(",", ":")).encode())
    def do_POST(self):
        self.answer(401)
    def log_message(self, *args):
        pass
http.server.HTTPServer(("127.0.0.1", 0), Api).serve_forever()
"""
PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>BitcoinTX</string>
<key>CFBundleIdentifier</key><string>org.bitcointx.desktop.preview</string>
</dict></plist>
"""
on_a_mac = pytest.mark.skipif(sys.platform != "darwin", reason="lsof's, PlistBuddy's and hdiutil's macOS")


def fake_preview(tmp_path: Path) -> tuple[Path, dict]:
    """A beta checkout whose desktop/dist holds a fake BitcoinTX Preview.app (an
    alpha's would be the same app), and the environment of one of GitHub's
    runners with a home of its own."""
    root = checkout(tmp_path / "repo", "2.0.0-beta.1", "2.0.0-beta.1:0")
    app = root / "desktop/dist/BitcoinTX Preview.app/Contents"
    (app / "MacOS").mkdir(parents=True)
    (app / "Info.plist").write_text(PLIST)
    (app / "MacOS/BitcoinTX").write_text(FAKE_APP.format(python=sys.executable))
    (app / "MacOS/BitcoinTX").chmod(0o755)
    (tmp_path / "home").mkdir()
    return root, {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted", "HOME": str(tmp_path / "home")}


def mac_app(root: Path, command: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(root / "scripts/mac-app.sh"), command], cwd=root, capture_output=True,
                          text=True, check=False, timeout=180, env={**os.environ, **env})


@on_a_mac
def test_the_mac_check_waits_for_the_app_and_finds_its_port(tmp_path):
    """It launches the build, waits until it listens, and checks it there."""
    root, env = fake_preview(tmp_path)
    made = mac_app(root, "check", env)
    assert made.returncode == 0, made.stdout + made.stderr
    assert re.search(r"BitcoinTX Preview \(org\.bitcointx\.desktop\.preview\) answers on port \d+", made.stdout)
    assert "entries endpoint (anonymous) -> 401" in made.stdout


@on_a_mac
@pytest.mark.parametrize("folder", ["Application Support/BitcoinTX", "Logs/BitcoinTX"])
def test_a_pre_release_that_writes_in_the_installed_apps_folders_fails_the_check(tmp_path, folder):
    root, env = fake_preview(tmp_path)
    made = mac_app(root, "check", {**env, "FAKE_ALSO": folder})
    assert made.returncode == 1 and f"made ~/Library/{folder}, the installed app's" in made.stderr


@on_a_mac
def test_an_app_that_quits_shows_its_log(tmp_path):
    root, env = fake_preview(tmp_path)
    made = mac_app(root, "check", {**env, "FAKE_QUITS": "1"})
    assert made.returncode == 1 and "BitcoinTX Preview quit before it answered" in made.stderr
    assert "the fake app quit" in made.stdout


@on_a_mac
def test_the_mac_files_are_named_after_the_app(tmp_path):
    root, env = fake_preview(tmp_path)
    made = mac_app(root, "package", env)
    assert made.returncode == 0, made.stderr
    assert made.stdout.splitlines() == ["stem=BitcoinTX-Preview-macOS", "dmg=BitcoinTX-Preview-macOS.dmg",
                                        "zip=BitcoinTX-Preview-macOS.zip"]
    assert (root / "BitcoinTX-Preview-macOS.dmg").is_file() and (root / "BitcoinTX-Preview-macOS.zip").is_file()


# The workflows

def test_a_prerelease_branch_starts_the_release_workflow():
    assert re.search(r"^    branches: \['release/v\*', 'prerelease/v\*'\]$", RELEASE_YML, re.M)


def test_the_commit_is_on_main_for_a_release_and_on_2_0_for_a_pre_release():
    check = job(RELEASE_YML, "check")
    assert 'scripts/release-version.sh "$GITHUB_REF_NAME" > version.env' in check
    assert 'git merge-base --is-ancestor "$GITHUB_SHA" "origin/$base"' in check
    # the outputs are written only once every check has passed
    assert check.index("--is-ancestor") < check.index('scripts/release-notes.sh "$tag" > /dev/null') \
        < check.index('cat version.env >> "$GITHUB_OUTPUT"')
    for output in ("tag", "version", "revision", "prerelease", "connector"):
        assert f"{output}: ${{{{ steps.v.outputs.{output} }}}}" in check, output


def test_a_pre_release_never_reaches_the_mirror_or_start9():
    check = job(RELEASE_YML, "check")
    start9 = check[check.index("- name: Start9's changes"):]
    assert start9.index("if: steps.v.outputs.prerelease == 'false'") < start9.index("scripts/start9-pull.sh --check")
    assert "if: needs.check.outputs.prerelease == 'false'" in job(RELEASE_YML, "mirror").split("steps:")[0]


def test_a_pre_release_keeps_the_price_historys_age_check_and_goes_to_pypi():
    """Only a package-only revision (-N) ships the history it had and skips
    PyPI, which never takes a version twice; a pre-release's tag has a '-' too."""
    prices = job(RELEASE_YML, "check").split("The hourly price history")[1]
    assert 'if [ "$REVISION" != 0 ]; then age=(--no-age-check)' in prices
    assert "*-*" not in prices
    assert "if: needs.check.outputs.exists == 'false' && needs.check.outputs.revision == '0'" in job(RELEASE_YML, "pypi")


def test_a_pre_release_is_a_github_prerelease_never_latest():
    release = job(RELEASE_YML, "release")
    assert 'if [ "$PRERELEASE" = true ]; then kind=(--prerelease --latest=false)' in release
    assert 'gh release create "$TAG" "${kind[@]}"' in release
    assert "pre-release · StartOS package" in release
    # its notes open with what an alpha or a beta is and how each platform keeps a tester's records
    pre = release[release.index("cat > pre.md"):]
    for words in ("BitcoinTX Preview", "its own ledger", "carries from one pre-release to the next",
                  "Make a StartOS backup", "a new volume", "never your real data",
                  "docs/MAINTENANCE.md#going-back-to-1x", "prerelease_report.yml"):
        assert words in pre, words


def run_release_step(tmp_path: Path, tag: str, changelog: str, **env: str) -> subprocess.CompletedProcess:
    """release.yml's "Create the release" step, run with a gh that writes
    down what it was asked (in tmp_path/asked)."""
    release = job(RELEASE_YML, "release")
    block = release[release.index("- name: Create the release"):]
    script = textwrap.dedent(block[block.index("run: |\n") + len("run: |\n"):])
    root = tmp_path / "root"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(REPO / "scripts/release-notes.sh", root / "scripts")
    (root / "docs").mkdir()
    (root / "docs/CHANGELOG.md").write_text(f"# Changelog\n\n{changelog}\n## [v1.0.0]\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text('#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a"; done > "$ASKED"\n')
    (bin_dir / "gh").chmod(0o755)
    return subprocess.run(["bash", "-e", "-c", script], cwd=root, capture_output=True, text=True, check=False, env={
        **os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "ASKED": str(tmp_path / "asked"),
        "GITHUB_REPOSITORY": "DigiMonk73/BTCTX-MCP", "GITHUB_SHA": SHA, "TAG": tag, **env})


def release_step(tmp_path: Path, tag: str, changelog: str, **env: str) -> tuple[str, str]:
    """(the notes, the gh command) of the step run as run_release_step does."""
    made = run_release_step(tmp_path, tag, changelog, **env)
    assert made.returncode == 0, made.stderr
    return (tmp_path / "root/notes.md").read_text(), (tmp_path / "asked").read_text()


def test_a_release_is_created_as_before(tmp_path):
    notes, asked = release_step(
        tmp_path, "v1.2.11", "## [v1.2.11]\n\n### Fixed\n- A fix.\n", VERSION="v1.2.11", CONNECTOR="1.2.11",
        PRERELEASE="false", MAC_DMG="BitcoinTX-macOS.dmg", MAC_ZIP="BitcoinTX-macOS.zip", PACKAGE="1.2.11:0")
    assert asked.splitlines() == [
        "release", "create", "v1.2.11", "--target", SHA, "--title", "v1.2.11 · StartOS package 1.2.11:0",
        "--notes-file", "notes.md", "dist/btctx.s9pk", "dist/BitcoinTX-macOS.dmg", "dist/BitcoinTX-macOS.zip",
        "dist/SHA256SUMS"]
    assert notes.startswith("\n### Fixed\n- A fix.\n\n## Downloads\n")
    for line in ("installs of earlier versions update in place", "`BitcoinTX-macOS.dmg`",
                 "`ghcr.io/digimonk73/btctx-mcp:v1.2.11` (amd64 and arm64).", "`uvx btctx-mcp==1.2.11` (PyPI)",
                 "**Checking a download:**"):
        assert line in notes, line
    assert "pre-release" not in notes and "Preview" not in notes


def test_a_beta_is_created_as_a_prerelease_with_its_own_notes(tmp_path):
    notes, asked = release_step(
        tmp_path, "v2.0.0-beta.1", "## [v2.0.0-beta.1]\n\n**About this beta.** Words.\n\n### Added\n- x\n",
        VERSION="v2.0.0-beta.1", CONNECTOR="2.0.0b1", PRERELEASE="true", MAC_DMG="BitcoinTX-Preview-macOS.dmg",
        MAC_ZIP="BitcoinTX-Preview-macOS.zip", PACKAGE="2.0.0-beta.1:0")
    assert asked.splitlines() == [
        "release", "create", "v2.0.0-beta.1", "--prerelease", "--latest=false", "--target", SHA, "--title",
        "v2.0.0-beta.1 · pre-release · StartOS package 2.0.0-beta.1:0", "--notes-file", "notes.md",
        "dist/btctx.s9pk", "dist/BitcoinTX-Preview-macOS.dmg", "dist/BitcoinTX-Preview-macOS.zip", "dist/SHA256SUMS"]
    assert notes.startswith("**This is a beta of BitcoinTX 2.0: a pre-release, for testing.**")
    assert notes.index("**About this beta.** Words.") < notes.index("## Downloads")
    for line in ("`uvx btctx-mcp==2.0.0b1` (a pre-release on PyPI)", "`BitcoinTX-Preview-macOS.dmg`",
                 "`ghcr.io/digimonk73/btctx-mcp:v2.0.0-beta.1` (amd64 and arm64), on a new volume",
                 "/blob/v2.0.0-beta.1/docs/MAINTENANCE.md#going-back-to-1x", "**Checking a download:**"):
        assert line in notes, line


def test_an_alpha_is_created_as_a_prerelease_and_called_an_alpha(tmp_path):
    notes, asked = release_step(
        tmp_path, "v2.0.0-alpha.1", "## [v2.0.0-alpha.1]\n\n**About this alpha.** Words.\n\n### Added\n- x\n",
        VERSION="v2.0.0-alpha.1", CONNECTOR="2.0.0a1", PRERELEASE="true", MAC_DMG="BitcoinTX-Preview-macOS.dmg",
        MAC_ZIP="BitcoinTX-Preview-macOS.zip", PACKAGE="2.0.0-alpha.1:0")
    assert asked.splitlines()[:7] == ["release", "create", "v2.0.0-alpha.1", "--prerelease", "--latest=false",
                                      "--target", SHA]
    assert notes.startswith("**This is an alpha of BitcoinTX 2.0, its earliest test stage: a pre-release, for testing.**")
    assert "`uvx btctx-mcp==2.0.0a1` (a pre-release on PyPI)" in notes
    assert "a beta of" not in notes


@pytest.mark.parametrize("tag, prerelease, says", [
    ("v2.0.0-beta.1", "", "prerelease is '', not true or false"),
    ("v1.2.11", "yes", "prerelease is 'yes', not true or false"),
    ("v2.0.0-beta.1", "false", "v2.0.0-beta.1 is a pre-release, not marked one"),
    ("v2.0.0-alpha.1", "false", "v2.0.0-alpha.1 is a pre-release, not marked one"),
    # and the other way: only an alpha or a beta is a pre-release
    ("v2.0.0-rc.1", "true", "v2.0.0-rc.1 is marked a pre-release but is neither an alpha nor a beta"),
    ("v1.2.11", "true", "v1.2.11 is marked a pre-release but is neither an alpha nor a beta"),
])
def test_a_release_whose_kind_is_unclear_is_never_created(tmp_path, tag, prerelease, says):
    """Made a normal release, a beta would be "Latest" (gh's default), and
    releases/latest and the landing page would offer it: fail closed."""
    made = run_release_step(tmp_path, tag, f"## [{tag}]\n\n### Added\n- x\n", VERSION=tag, CONNECTOR="2.0.0b1",
                            PRERELEASE=prerelease, MAC_DMG="a.dmg", MAC_ZIP="a.zip", PACKAGE="2.0.0-beta.1:0")
    assert made.returncode == 1 and says in made.stdout + made.stderr
    assert not (tmp_path / "asked").exists()


def test_the_release_notes_name_the_pre_releases_own_downloads():
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


def test_the_pre_release_report_form_keeps_real_data_and_security_problems_out():
    form = (REPO / ".github/ISSUE_TEMPLATE/prerelease_report.yml").read_text()
    assert 'labels: ["pre-release", "unconfirmed"]' in form
    for words in ("Which alpha or beta", "StartOS", "macOS app (BitcoinTX Preview)", "Docker", "test ledger",
                  "never post personal data", "SECURITY.md"):
        assert words in form, words
    after = form.split("I removed personal data", 1)[1]
    assert after.split("- label:", 1)[0].count("required: true") == 1
