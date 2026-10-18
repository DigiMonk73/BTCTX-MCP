"""
The StartOS instructions' Documentation links (#467). Start9's support
indexer crawls each one into the package's documentation index, and says to
leave out "upstream install guides [that] describe a deployment the package
deliberately does not use" (writing-instructions.md, "Choosing documentation
URLs"): a link to the whole README would teach it the Mac app's and
Docker's steps. Each link is a page of this repository on `main`, which has
it once a release fast-forwards `main` to `develop`, so the page must be
here too.
"""

import re
from pathlib import Path

from backend.services.reports.pdf_layout import DISCLAIMER
from backend.tests.test_startos_conformance import DOC_BULLET, read

ROOT = Path(__file__).resolve().parents[2]
ON_MAIN = re.compile(r"https://github\.com/DigiMonk73/BTCTX-MCP/blob/main/(\S+)")

# The AI connector runs on the user's own computer whatever BitcoinTX runs on,
# and its README labels each install's steps; its StartOS ones apply here.
CONNECTOR = "mcp_server/README.md"

# What belongs to another install: its name, its commands, its sections.
OTHER_INSTALLS = re.compile(r"docker|mac app|macos|\.dmg|pip install|git clone|setup code", re.I)
INSTALL_HEADINGS = re.compile(r"^#+ .*\b(?:install|upgrad|updat|first login|from source).*$", re.I | re.M)


def documentation_links():
    section = read("instructions.md").split("\n## Documentation\n", 1)[1].split("\n## ", 1)[0]
    bullets = [line for line in section.splitlines() if line.startswith(("- ", "* "))]
    # test_startos_conformance.py checks that every bullet parses
    return [m.group(1) for m in map(DOC_BULLET.fullmatch, bullets) if m]


def test_each_link_is_a_page_of_this_repository_on_main():
    links = documentation_links()
    assert links
    for url in links:
        m = ON_MAIN.fullmatch(url)
        assert m, f"not a page of DigiMonk73/BTCTX-MCP on main: {url}"
        assert (ROOT / m.group(1)).is_file(), f"{m.group(1)} isn't in the repository: the link would be a 404"


def test_no_link_teaches_another_installs_steps():
    pages = [ON_MAIN.fullmatch(url).group(1) for url in documentation_links()]
    about_the_app = [page for page in pages if page != CONNECTOR]
    assert about_the_app, "a page on what BitcoinTX does, beside the connector's"
    for page in about_the_app:
        text = (ROOT / page).read_text()
        found = sorted({w.lower() for w in OTHER_INSTALLS.findall(text)} | set(INSTALL_HEADINGS.findall(text)))
        assert not found, f"{page} has another install's steps: {found}"


def test_the_using_page_words_the_notices_as_the_readme_does():
    # The one-wallet box and the disclaimer, word for word (test_disclaimer.py
    # keeps the README's the same as the app's and the PDFs').
    readme, using = (ROOT / "README.md").read_text(), (ROOT / "docs/USING.md").read_text()
    box = re.compile(r"> \[!IMPORTANT\]\n((?:>.*\n)+)")
    assert box.search(using).group(1) == box.search(readme).group(1)
    assert DISCLAIMER in " ".join(using.split())
