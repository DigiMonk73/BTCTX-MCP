"""
Which of CI's jobs a change needs (#985; the owner's choice, 2026-11-23).

    git diff --name-only HEAD^1 HEAD | python3 scripts/ci_changes.py --event pull_request --base develop
    python3 scripts/ci_changes.py --docs-tests

The first reads the files a pull request changes, one per line, and writes
`skip=<JSON list of job ids>` for $GITHUB_OUTPUT: the jobs ci.yml may skip,
which "CI passed" then counts as passed. The second lists the test files
that read the docs, which run on every change (ci.yml's `docs` job).

- A push (to develop, main or 2.0) or a run from the Actions tab skips
  nothing: each merged commit is tested in full.
- A pull request changing only docs (`is_docs`) skips every heavy job; the
  lint and the tests that read the docs still run.
- One changing nothing the click-through tests can see (`unseen_by_browsers`)
  skips them.
- One into 2.0 skips the click-through tests, Docker and the StartOS pack
  (the medium set, the owner's choice of 2026-10-22; they run on each merge
  into 2.0).

A path this file doesn't name never skips a job: the rules list what may
skip, never what must run.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Every job a change may skip, by its id in ci.yml
HEAVY = ("python", "python-guard", "connector", "frontend", "smoke", "e2e", "docker", "startos",
         "startos-pack", "audit", "audit-macos", "macos-app")
MEDIUM_SET_SKIPS = ("e2e", "docker", "startos-pack")

# Folders whose Markdown is part of what's built or tested as data, not docs:
# the app's own files, the StartOS package (Start9 reviews its text), test data
NOT_DOCS = ("backend/", "frontend/", "startos/", "testdata/", "desktop/")
# Outside the app the click-through tests run (the server and the web page)
BROWSER_UNSEEN = ("startos/", "mcp_server/", "desktop/", ".github/")
CI_ITSELF = (".github/workflows/ci.yml", "scripts/ci_changes.py")

# A test or helper that names a Markdown file or the docs folder in a string
NAMES_DOCS = re.compile(r"""\.md["']|["']docs["'/]""")
TEST_FOLDERS = ("backend/tests", "mcp_server/tests")


def is_docs(path: str) -> bool:
    """Documentation only: Markdown outside the app's and the package's own
    folders, or anything under docs/ (its images too)."""
    return path.startswith("docs/") or (path.endswith(".md") and not path.startswith(NOT_DOCS))


def unseen_by_browsers(path: str) -> bool:
    """A file the click-through tests never run or read: docs, the StartOS
    package, the AI connector, the Mac app's wrapper, GitHub's settings and
    other workflows. CI's own rules always run them, to test themselves."""
    return path not in CI_ITSELF and (is_docs(path) or path.startswith(BROWSER_UNSEEN))


def skipped(event: str, base: str, paths: list[str]) -> list[str]:
    """The jobs a change may skip, in HEAVY's order."""
    if event != "pull_request" or not paths:
        return []
    skip = set()
    if all(is_docs(path) for path in paths):
        skip.update(HEAVY)
    if all(unseen_by_browsers(path) for path in paths):
        skip.add("e2e")
    if base == "2.0":
        skip.update(MEDIUM_SET_SKIPS)
    return [job for job in HEAVY if job in skip]


def docs_tests(root: Path = ROOT) -> list[str]:
    """The test files that read the docs: each that names a Markdown file or
    the docs folder, or names a helper (a test folder's other module, or a
    script) that does."""
    helpers = [path for folder in TEST_FOLDERS for path in (root / folder).glob("*.py")
               if not path.name.startswith(("test_", "conftest"))] + list((root / "scripts").glob("*.py"))
    readers = [path.stem for path in helpers if NAMES_DOCS.search(path.read_text())]
    tests = sorted(path for folder in TEST_FOLDERS for path in (root / folder).glob("test_*.py"))
    return [str(path.relative_to(root)) for path in tests
            if NAMES_DOCS.search(text := path.read_text()) or any(stem in text for stem in readers)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--event", help="github.event_name")
    parser.add_argument("--base", default="", help="a pull request's base branch")
    parser.add_argument("--docs-tests", action="store_true", help="list the test files that read the docs")
    args = parser.parse_args(argv)
    if args.docs_tests:
        print("\n".join(docs_tests()))
        return 0
    if not args.event:
        parser.error("--event or --docs-tests")
    paths = [line.strip() for line in sys.stdin if line.strip()] if args.event == "pull_request" else []
    print(f"skip={json.dumps(skipped(args.event, args.base, paths))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
