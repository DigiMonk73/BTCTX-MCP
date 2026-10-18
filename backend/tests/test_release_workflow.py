"""
Every release lets a user check a download (#203): release.yml uploads
SHA256SUMS of each file it releases, and a GitHub build provenance
attestation covers the same files. The workflow is read as text, as in
test_pinning.py: no YAML parser is installed for the tests.

And every release's notes fit GitHub (1.2.9's review, #528): a release body
over 125,000 characters is refused, after PyPI already has the version, so
scripts/release-notes.sh gives a long section's summary and a link, and the
first job checks them.
"""

import re
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RELEASE_YML = (REPO / ".github/workflows/release.yml").read_text()
NOTES_SCRIPT = REPO / "scripts/release-notes.sh"
LIMIT = 120_000


def job(name: str) -> str:
    """One job of release.yml, up to the next job."""
    found = re.search(rf"^  {name}:\n(.*?)(?=^  \S|\Z)", RELEASE_YML, re.M | re.S)
    assert found, f"release.yml has no job {name}"
    return found.group(1)


def permissions(block: str, indent: str) -> set[str]:
    found = re.search(rf"^{indent}permissions:\n((?:{indent}  .*\n)+)", block, re.M)
    return {line.split("#")[0].strip() for line in found.group(1).splitlines()} if found else set()


def released_files() -> list[str]:
    """The files `gh release create` uploads, its continuation lines included."""
    command = re.search(r"gh release create (?:.*\\\n)*.*", job("release")).group(0)
    return re.findall(r"dist/(\S+)", command)


def test_the_release_uploads_sha256sums_of_every_other_file():
    summed = re.search(r"^\s*sha256sum (.+) > SHA256SUMS$", job("release"), re.M)
    assert summed, "the release job writes SHA256SUMS with sha256sum"
    released = released_files()
    assert "SHA256SUMS" in released
    assert sorted(summed.group(1).split()) == sorted(f for f in released if f != "SHA256SUMS")


def test_the_files_are_attested_before_the_release_is_created():
    release = job("release")
    attest = re.search(
        r"uses: actions/attest-build-provenance@[0-9a-f]{40} .*\n\s+with:\n\s+subject-checksums: dist/SHA256SUMS\n",
        release,
    )
    assert attest, "attest exactly the files SHA256SUMS lists"
    assert attest.start() < release.index("gh release create"), "a release that exists can't be created again on a rerun"


def test_only_the_release_job_may_sign():
    assert {"id-token: write", "attestations: write"} <= permissions(job("release"), "    ")
    assert "contents: write" in permissions(job("release"), "    "), "gh release create needs it"
    assert not {"id-token: write", "attestations: write"} & permissions(RELEASE_YML, "")


def release_notes(tag: str, root: Path = REPO) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(root / "scripts/release-notes.sh"), tag], capture_output=True, text=True, check=False
    )


def test_every_releases_notes_fit_a_github_release():
    changelog = (REPO / "docs/CHANGELOG.md").read_text()
    tags = re.findall(r"^## \[(v[^\]]+)\]", changelog, re.M)
    assert "v1.2.9" in tags
    for tag in tags:
        made = release_notes(tag)
        assert made.returncode == 0, (tag, made.stderr)
        assert len(made.stdout.encode()) <= LIMIT, tag


def test_a_section_with_a_summary_gives_the_summary_and_a_link():
    notes = release_notes("v1.2.9").stdout
    assert "**About this release.**" in notes and "**What to do after updating**" in notes
    assert "\n### " not in notes
    assert notes.rstrip().endswith("(https://github.com/DigiMonk73/BTCTX-MCP/blob/v1.2.9/docs/CHANGELOG.md)")


def test_a_section_without_a_summary_is_given_whole():
    notes = release_notes("v1.2.8").stdout
    assert notes.lstrip().startswith("### Added") and "### Development" in notes
    assert "docs/CHANGELOG.md)" not in notes


def test_notes_too_long_for_github_are_refused(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "docs").mkdir()
    shutil.copy(NOTES_SCRIPT, tmp_path / "scripts")
    entry = "- **A fix.** " + "x" * 1_000 + "\n"
    (tmp_path / "docs/CHANGELOG.md").write_text(
        "# Changelog\n\n## [v9.9.9] - 2099-01-01 - Long\n\n### Fixed\n" + entry * 130 + "\n## [v9.9.8]\n"
    )
    made = release_notes("v9.9.9", tmp_path)
    assert made.returncode == 1 and "over 120000" in made.stderr
    assert made.stdout == ""
    assert release_notes("v9.9.7", tmp_path).returncode == 1


def test_the_notes_are_checked_before_anything_is_published():
    check = job("check")
    assert 'scripts/release-notes.sh "$TAG" > /dev/null' in check
    assert check.index("scripts/release-notes.sh") < check.index('echo "tag=$TAG"')
    for publishing in ("image", "pypi", "macos", "s9pk", "release"):
        assert re.search(r"needs: (check|\[check\b)", job(publishing)), publishing
    assert 'scripts/release-notes.sh "$TAG" > notes.md' in job("release")
    mirror = (REPO / "scripts/mirror-startos-release.sh").read_text()
    assert '"$ROOT/scripts/release-notes.sh" "$SOURCE_TAG" > "$NOTES"' in mirror
    assert "awk" not in mirror
