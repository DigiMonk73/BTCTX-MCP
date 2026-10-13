"""
Every release lets a user check a download (#203): release.yml uploads
SHA256SUMS of each file it releases, and a GitHub build provenance
attestation covers the same files. The workflow is read as text, as in
test_pinning.py: no YAML parser is installed for the tests.
"""

import re
from pathlib import Path

RELEASE_YML = (Path(__file__).resolve().parents[2] / ".github/workflows/release.yml").read_text()


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
