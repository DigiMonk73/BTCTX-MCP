"""
The StartOS package keeps Start9's packaging rules (owner's rule, 2026-09-29):
Start9 forks startos/ (through the DigiMonk73/BTCTX-StartOS mirror) into its
community registry and reviews it against its packaging guide,
https://docs.start9.com/packaging (project-structure.md, writing-readmes.md,
writing-instructions.md). These are the rules a script can check; what the
README and instructions say is still read against the guide by hand.
"""

import re
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[2] / "startos"

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


def test_no_work_record_files():
    # The package template: "no TODO.md, no NOTES.md, no PLAN.md"; pending
    # work is a GitHub issue (labelled start9 in BTCTX-MCP).
    stray = [n for n in ("TODO.md", "NOTES.md", "PLAN.md") if (PKG / n).exists()]
    assert stray == [], f"Start9's template keeps no work records in the package: {stray}"


def test_updating_md_has_start9s_two_sections():
    headings = h2(read("UPDATING.md"))
    wanted = ["Determining the upstream version", "Applying the bump"]
    assert [h for h in headings if h in wanted] == wanted
