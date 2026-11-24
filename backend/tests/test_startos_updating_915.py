"""
#915: Start9's guide has a package's UPDATING.md hold "the upstream bump
recipe and nothing else" (agent-context.md and project-structure.md,
"UPDATING.md", 2026-11-04). Ours held the release, Start9's fork, the watch,
the SDK bump, the local build and the secrets too; they moved word for word
to docs/STARTOS-PACKAGE.md, and every pointer follows them.

#898: the StartOS release notes say what a user observes, never how it was
done (Start9's versions.md, "Release Notes", 2026-11-03, and from
2026-11-19 never the minimum StartOS). startos/AGENTS.md points to it and
adds ours, where the release reads them; checked here for every version
after 2.0.2:0, whose notes were published before the last part.
"""

import re
import subprocess
from pathlib import Path

import pytest

from backend.tests.test_test_files import needs_a_checkout

ROOT = Path(__file__).resolve().parents[2]
UPDATING = ROOT / "startos" / "UPDATING.md"
PACKAGE_DOC = ROOT / "docs" / "STARTOS-PACKAGE.md"
VERSIONS = ROOT / "startos" / "startos" / "versions"

# Start9's project-structure.md, "UPDATING.md": "It has two sections".
RECIPE = ["Determining the upstream version", "Applying the bump"]
MOVED = [
    "Releasing a new version",
    "After Start9 forks the mirror",
    "The package version",
    "Watching Start9",
    "Bumping the SDK",
    "Building locally",
    "One-time setup: secrets and a variable",
]
# A pointer names a doc, then the section in quotes: `startos/UPDATING.md`,
# "Applying the bump", or UPDATING.md's "Applying the bump".
POINTER = r"{}`?(?:,|'s) \"([^\"]+)\""
# History keeps its words: archived docs, notes and the CHANGELOG.
UNPOINTED = ("docs/archive/", "docs/temp/", "docs/CHANGELOG.md")
TEXT = (".md", ".py", ".ts", ".yml", ".yaml", ".sh", ".mjs", ".gitignore")


def headings(path: Path, level: str = "#+") -> list[str]:
    return re.findall(rf"^{level} (.+?)\s*$", path.read_text(), re.M)


def test_updating_md_holds_only_the_recipe():
    assert headings(UPDATING, "##") == RECIPE
    assert headings(UPDATING, "###") == []
    text = UPDATING.read_text()
    for gone in ("Releasing", "Watching Start9", "DEV_KEY", "MIRROR_TOKEN", "REFERENCE_REGISTRY", "start-cli"):
        assert gone not in text, gone


def test_the_moved_sections_have_their_new_home():
    assert headings(PACKAGE_DOC, "##") == MOVED


@needs_a_checkout
def test_every_pointer_names_a_section_its_doc_has():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    docs = {"UPDATING.md": headings(UPDATING), "STARTOS-PACKAGE.md": headings(PACKAGE_DOC)}
    broken = []
    for path in tracked.splitlines():
        if path.startswith(UNPOINTED) or not path.endswith(TEXT) or not (ROOT / path).is_file():
            continue
        text = " ".join((ROOT / path).read_text().split())  # a pointer may wrap
        for name, sections in docs.items():
            for section in re.findall(POINTER.format(re.escape(name)), text):
                if section not in sections:
                    broken.append(f"{path}: {name}, {section!r}")
    assert not broken, broken


# --- #898: the release notes ---

# What a user can't observe, or doesn't need: an issue number or link
# (history), the SDK or start-cli (the package's internals), a StartOS version
# (the minimum, which "only a server that already meets it is shown"). Only
# the written text is read: a value put in with ${…} isn't.
UNOBSERVED = {
    "an issue number": re.compile(r"#\d|/issues/\d|/pull/\d"),
    "the SDK or start-cli": re.compile(r"start-sdk|start-cli|\bSDK\b"),
    # StartOS's versions are 0.x, BitcoinTX's 1.x on, so any 0.x.y is
    # StartOS's (or a 0.x BitcoinTX's, which is history), in any language and
    # word order; and "StartOS 0.4" or "StartOS v0.4", with any space. A
    # bitcoin amount (0.5 BTC) has one dot.
    "a StartOS version": re.compile(r"\bv?0\.\d+\.\d|StartOS\W{1,3}v?0\.\d"),
}
# The last notes published before Start9's rule against the minimum StartOS.
LAST_BEFORE_THE_RULE = (2, 0, 2, 0)


def version_of(text: str) -> tuple[int, ...]:
    """`version: '2.0.3:0'` as (2, 0, 3, 0); a pre-release's tag is left out."""
    version = re.search(r"^\s*version: '([^']+)'", text, re.M).group(1)
    upstream, revision = version.split(":")
    return (*(int(part) for part in upstream.split("-")[0].split(".")), int(revision))


def release_notes(text: str) -> str:
    """Every language's notes: from releaseNotes to the migrations."""
    return text.split("releaseNotes:", 1)[1].split("\n  migrations:", 1)[0]


def unobserved(text: str) -> list[str]:
    notes = release_notes(text)
    return [what for what, pattern in UNOBSERVED.items() if pattern.search(notes)]


def test_the_notes_say_only_what_a_user_observes():
    checked = [path for path in VERSIONS.glob("*.ts") if "releaseNotes:" in path.read_text()]
    assert checked
    found = {path.name: unobserved(path.read_text()) for path in checked
             if version_of(path.read_text()) > LAST_BEFORE_THE_RULE}
    assert not any(found.values()), found


NOTES = "export const current = VersionInfo.of({{\n  version: '2.0.3:0',\n  releaseNotes: {{\n    en_US: `{}`,\n  }},\n  migrations: {{}},\n}})\n"


@pytest.mark.parametrize("notes, what", [
    ("It fixes the wrong date on Form 8949 (#950).", "an issue number"),
    ("Details: https://github.com/DigiMonk73/BTCTX-MCP/issues/950", "an issue number"),
    ("Built with start-sdk 4.1.0.", "the SDK or start-cli"),
    ("**Update StartOS to 0.4.2 or later first.**", "a StartOS version"),
    ("Needs StartOS v0.4.2.", "a StartOS version"),
    ("Needs StartOS 0.4.", "a StartOS version"),
    ("Necesita la versión 0.4.2 de StartOS.", "a StartOS version"),
    ("Requires 0.4.2 or later.", "a StartOS version"),
])
def test_the_check_finds_what_a_user_does_not_observe(notes, what):
    assert unobserved(NOTES.format(notes)) == [what]


def test_the_check_would_refuse_2_0_2s_notes_today():
    # 2.0.2's notes named the minimum StartOS, as the rule then allowed.
    text = (VERSIONS / "current.ts").read_text()
    if version_of(text) != LAST_BEFORE_THE_RULE:
        pytest.skip("current.ts has moved on from 2.0.2:0")
    assert unobserved(text.replace("version: '2.0.2:0'", "version: '2.0.3:0'")) == ["a StartOS version"]


@pytest.mark.parametrize("notes", [
    "Form 8949 for 2025 now shows the right date sold.",
    "A sale of 0.5 BTC now takes the coins listed first.",
    "Update StartOS first, then BitcoinTX 2.0.3.",
])
def test_the_check_passes_notes_that_say_what_a_user_sees(notes):
    assert unobserved(NOTES.format(notes)) == []


def test_the_rule_is_written_where_the_release_reads_it():
    # Start9's rule by its page, never restated (project-structure.md,
    # "AGENTS.md and CLAUDE.md"); ours beside it.
    rules = " ".join((ROOT / "startos" / "AGENTS.md").read_text().split())
    assert "[Versions](https://docs.start9.com/packaging/versions.html), \"Release Notes\"" in rules
    assert "never the minimum StartOS" not in rules
    assert "`tax-figures` fix" in rules
    assert "never which BitcoinTX versions had it" in rules
    releasing = " ".join((ROOT / "docs" / "RELEASING.md").read_text().split())
    assert "ours in `startos/AGENTS.md`" in releasing
