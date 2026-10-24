"""
The StartOS package keeps Start9's packaging rules (owner's rule, 2026-09-29):
Start9 forks startos/ (through the DigiMonk73/BTCTX-StartOS mirror) into its
community registry and reviews it against its packaging guide,
https://docs.start9.com/packaging (project-structure.md, writing-readmes.md,
writing-instructions.md, versions.md, maintaining-a-package.md). These are the
rules a script can check; what the README and instructions say is still read
against the guide by hand.
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "startos"

# project-structure.md: the root layout every package has.
LAYOUT = [
    ".github/workflows/build.yml",
    ".github/workflows/pr-retarget.yml",
    ".github/workflows/tagAndRelease.yml",
    ".github/workflows/release.yml",
    ".github/workflows/syncNext.yml",
    ".dockerignore",
    ".gitignore",
    ".prettierrc",
    "AGENTS.md",
    "CLAUDE.md",
    "instructions.md",
    "LICENSE",
    "Makefile",
    "package.json",
    "package-lock.json",
    "README.md",
    "tsconfig.json",
    "UPDATING.md",
]

# writing-readmes.md: "Use the headings below verbatim, in this order."
README_HEADINGS = [
    "Table of Contents",
    "Image and Container Runtime",
    "Volume and Data Layout",
    "File Models",
    "Dependencies",
    "Network Access and Interfaces",
    "Installation and First-Run Flow",
    "Actions",
    "Tasks",
    "Health Checks",
    "Backups and Restore",
    "Limitations and Differences",
    "Quick Reference for AI Consumers",
]

# Three dot-separated numbers that aren't part of an IP address (10.0.3.1).
VERSION = re.compile(r"(?<![\d.])v?\d+\.\d+\.\d+(?![.\d])")

# writing-instructions.md: "Exactly `- [Title](URL)`, optionally followed by
# ` — a few words` ... and nothing else on the line."
DOC_BULLET = re.compile(r"- \[[^\]]+\]\((https?://[^)\s]+)\)(?: [—–-] \S.*)?")


def read(name):
    return (PKG / name).read_text()


def h2(text):
    return re.findall(r"^## (.+?)\s*$", text, re.M)


@pytest.mark.parametrize("name", LAYOUT)
def test_the_standard_file_is_there(name):
    assert (PKG / name).is_file(), f"startos/{name} is part of Start9's package layout"


def test_prettierrc_names_the_sdk_config():
    # project-structure.md: "one line naming the SDK's shared Prettier config"
    assert read(".prettierrc").strip() == '"@start9labs/start-sdk/prettier.config.json"'


def test_assets_is_there_and_not_empty():
    assets = PKG / "assets"
    assert assets.is_dir() and any(p.is_file() for p in assets.iterdir()), (
        "startos/assets/ must exist with at least one file, or the build fails"
    )


def test_claude_md_only_imports_agents_md():
    assert read("CLAUDE.md").strip() == "@AGENTS.md"


def the_icon():
    # start-cli packs the one file named icon.* at the root (more than one is
    # an error); project-structure.md: .svg, .png, .jpg or .webp, at most 40 KiB.
    icons = [p for p in PKG.iterdir() if p.is_file() and p.stem.lower() == "icon"]
    assert len(icons) == 1, f"one icon file at startos/, found {[p.name for p in icons]}"
    return icons[0]


def test_one_icon_of_an_accepted_type_at_most_40_kib():
    icon = the_icon()
    assert icon.suffix.lower() in {".svg", ".png", ".jpg", ".webp"}, icon.name
    assert icon.stat().st_size <= 40 * 1024, f"{icon.name}: {icon.stat().st_size} bytes"


def test_readme_opens_with_the_logo_title_and_scoping_note():
    text = read("README.md")
    assert text.startswith(f'<p align="center">\n  <img src="{the_icon().name}"')
    assert "\n# BitcoinTX on StartOS\n" in text
    assert "> Everything not listed in this document should behave the same as upstream" in text


def test_readme_has_the_fixed_headings_in_order():
    assert h2(read("README.md")) == README_HEADINGS


def test_every_readme_section_opens_with_prose():
    # "One or two sentences between the heading and the first table or
    # subsection." The table of contents is only its links.
    sections = re.split(r"^## .+$", read("README.md"), flags=re.M)[1:]
    for heading, body in zip(README_HEADINGS, sections):
        if heading == "Table of Contents":
            continue
        first = next(line for line in body.splitlines() if line.strip())
        assert not first.startswith(("|", "#", "```", "- ", "* ")), f"'## {heading}' opens with: {first}"


@pytest.mark.parametrize("name", ["README.md", "instructions.md"])
def test_no_version_numbers(name):
    assert VERSION.findall(read(name)) == [], f"Start9: no version numbers in {name}"


def test_instructions_documentation_links_parse():
    text = read("instructions.md")
    assert "\n## Documentation\n" in text
    section = text.split("\n## Documentation\n", 1)[1].split("\n## ", 1)[0]
    bullets = [line for line in section.splitlines() if line.startswith(("- ", "* "))]
    assert bullets, "without a bullet that parses, Start9 indexes no docs for the package"
    for line in bullets:
        m = DOC_BULLET.fullmatch(line)
        assert m, f"doesn't parse as '- [Title](URL) — a few words': {line}"
        url = m.group(1)
        # A /blob/ link is fetched as one page only when it ends in the
        # file's extension; with an #anchor it would be crawled as a site.
        assert "#" not in url, url
        assert not re.search(r"/blob/[0-9a-f]{40}/", url), f"commit-pinned: {url}"


def test_instructions_describe_the_service_as_it_is():
    # writing-instructions.md: "After updating from an older release…",
    # "now uses…", "no longer…" is releaseNotes; versions.md: release notes are
    # "the only home for what an update asks of the user".
    update_words = re.compile(
        r"\bafter (?:updating|(?:an?|the|this|each|every) (?:\w+ )?update)\b|\bnow uses\b|\bno longer\b",
        re.I,
    )
    assert update_words.findall(read("instructions.md")) == []


def store_descriptions(name: str) -> dict[str, str]:
    """One of manifest/i18n.ts's descriptions, by locale: each a single-quoted string."""
    block = re.search(rf"export const {name} = \{{(.*?)\n\}}", read("startos/manifest/i18n.ts"), re.S).group(1)
    return {locale: text.replace("\\'", "'") for locale, text in re.findall(r"(\w\w_\w\w):\s*'((?:[^'\\]|\\.)*)'", block)}


def test_store_descriptions_keep_start9s_limits():
    # manifest.md, "How long each one may be": short 120 and long 2,000
    # characters in every locale (an overrun fails the build), the English
    # short well inside the tile's two lines (about 80), and not opening
    # with the service's name, which the tile shows just above it.
    locales = {"en_US", "es_ES", "de_DE", "pl_PL", "fr_FR"}
    short, long = store_descriptions("short"), store_descriptions("long")
    assert set(short) == set(long) == locales
    for locale in locales:
        assert len(short[locale]) <= 120, (locale, len(short[locale]))
        assert len(long[locale]) <= 2000, (locale, len(long[locale]))
        assert not short[locale].startswith("BitcoinTX"), locale
    assert len(short["en_US"]) <= 80, len(short["en_US"])


def test_license_is_upstreams_license_alone():
    # project-structure.md: "It carries upstream's license text alone"; with a
    # pre-built image, "copy the license text directly from the upstream
    # repository" (this repository's own LICENSE).
    assert read("LICENSE") == (ROOT / "LICENSE").read_text()


# A package version: X.Y.Z:N, or a 2.0 pre-release's X.Y.Z-alpha.N:0 or
# X.Y.Z-beta.N:0 (Start9's ExVer for an upstream alpha or beta, versions.md;
# on the 2.0 branch only, 2.0 plan 7.4, B10a: a pre-release never reaches the
# mirror)
PACKAGE_VERSION = re.compile(r"\d+\.\d+\.\d+:\d+|\d+\.\d+\.\d+-(alpha|beta)\.[1-9]\d*:0")


@pytest.mark.parametrize("version, ok", [
    ("1.2.10:0", True), ("1.2.4:1", True), ("2.0.0-beta.1:0", True), ("2.0.0-beta.12:0", True),
    ("2.0.0-alpha.1:0", True), ("2.0.0-alpha.1:1", False), ("2.0.0-alpha.0:0", False),
    ("2.0.0-beta.1:1", False), ("2.0.0-beta.0:0", False), ("2.0.0-rc.1:0", False), ("2.0.0", False),
])
def test_a_package_version_is_a_release_or_a_pre_release(version, ok):
    assert bool(PACKAGE_VERSION.fullmatch(version)) is ok


def test_start9s_release_workflow_reads_one_id_and_one_version():
    # Start9's Tag and Release greps these from the text (its extract-version
    # action), so versions.md: "Write version as a quoted string literal".
    manifest = read("startos/manifest/index.ts")
    current = read("startos/versions/current.ts")
    assert re.findall(r"id:\s*['\"]([^'\"]*)", manifest) == ["btctx"]
    versions = re.findall(r"version:\s*['\"]([^'\"]*)", current)
    assert len(versions) == 1 and PACKAGE_VERSION.fullmatch(versions[0]), versions


def test_one_exact_sdk_and_siblings_at_next():
    # maintaining-a-package.md: the SDK pinned to an exact version, one copy of
    # it in the lockfile (the overrides entry), sibling packages at #next (or
    # #next/<base> for a package with parallel lines).
    package = json.loads(read("package.json"))
    deps = package["dependencies"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", deps.pop("@start9labs/start-sdk"))
    assert package["overrides"] == {"@start9labs/start-sdk": "$@start9labs/start-sdk"}
    assert all(re.search(r"#next(/[\w.-]+)?$", spec) for spec in deps.values()), deps
    lock = json.loads(read("package-lock.json"))["packages"]
    sdks = [path for path in lock if path.endswith("node_modules/@start9labs/start-sdk")]
    assert sdks == ["node_modules/@start9labs/start-sdk"]


def test_no_work_record_files():
    # The package template: "no TODO.md, no NOTES.md, no PLAN.md"; pending
    # work is a GitHub issue (labelled start9 in BTCTX-MCP).
    stray = [n for n in ("TODO.md", "NOTES.md", "PLAN.md") if (PKG / n).exists()]
    assert stray == [], f"Start9's template keeps no work records in the package: {stray}"


# Raising a task's replay key again doesn't duplicate an open task (tasks.md,
# "Idempotency and replayId"), but once the user has dismissed it the next
# raise brings it back (StartOS 0.4.0.2, #365). A container rebuild (every
# server restart) runs init, so a task raised after an update asks once: its
# handler skips a rebuild and records that it asked, after raising it.
@pytest.mark.parametrize(
    "name, key",
    [("priceSourceTask.ts", "priceSourceAsked"), ("recalculateTask.ts", "recalculateAsked")],
)
def test_a_task_raised_after_an_update_asks_once(name, key):
    code = read(f"startos/init/{name}")
    assert "if (kind === null) return" in code
    raised = code.rindex("createOwnTask")
    before, after = code[:raised], code[raised:]
    assert f"asked: s.{key}" in before  # reads whether it asked
    assert re.search(r"if \([^)]*\bstore\??\.asked\b", before)  # and skips if it did
    assert f"{key}: true" in after  # records it after raising


def test_updating_md_has_start9s_two_sections():
    headings = h2(read("UPDATING.md"))
    wanted = ["Determining the upstream version", "Applying the bump"]
    assert [h for h in headings if h in wanted] == wanted


def test_the_format_check_runs_before_the_sdks_make():
    """From start-sdk 3.1.0 the SDK's make formats startos/ instead of
    rejecting unformatted source (its s9pk.mk), so CI and the pre-push hook
    run the format check themselves, before make: unformatted source must
    fail there, not be rewritten and pass (#617's review). Start9's review
    runs a format check."""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    job = ci.split("\n  startos:\n", 1)[1].split("\n  startos-pack:\n", 1)[0]
    assert "run: npm run format:check" in job
    assert job.index("npm run format:check") < job.index("make javascript/index.js")
    hook = (ROOT / ".githooks" / "pre-push").read_text()
    assert "npm run -s format:check && rm -rf javascript && make" in hook
