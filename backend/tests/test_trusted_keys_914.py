"""
StartOS 0.4.1.2 renamed the setting that says which signers' packages it
installs: System → Trusted Keys (its release notes, #914). Where our docs send
a user or a tester there, they name it as StartOS shows it, so nobody looks
for a menu that's gone. The old name was "keyrings". Released text keeps its
words: the CHANGELOG's versions, and docs/archive and docs/temp.
"""

import re
import subprocess

import pytest

from backend.tests.test_disclaimer import BETWEEN_WORDS, ROOT, TEXT, unreleased
from backend.tests.test_test_files import needs_a_checkout

OLD_NAME = re.compile(r"\btrusted keyrings?\b", re.I)
KEPT_AS_WRITTEN = ("docs/archive/", "docs/temp/")
# The docs that send someone to the setting: the README's StartOS section, the
# release tests' VM and Community Beta steps, and the owner's beta check.
SEND_THERE = ("README.md", "docs/AGENT-TESTS.md", "docs/HOW-CHANGES-FLOW.md")


@needs_a_checkout
def test_no_doc_uses_the_old_name():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    old = [path for path in tracked.splitlines()
           if path.endswith(TEXT) and not path.startswith(KEPT_AS_WRITTEN)
           and OLD_NAME.search(BETWEEN_WORDS.sub(" ", unreleased(path, (ROOT / path).read_text())))]
    assert not old, old


@pytest.mark.parametrize("name", SEND_THERE)
def test_the_docs_name_trusted_keys(name):
    assert "Trusted Keys" in " ".join((ROOT / name).read_text().split()), name
