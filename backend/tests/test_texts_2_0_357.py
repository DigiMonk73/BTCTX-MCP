"""
2.0's texts (#357; 2.0 spec 5.14): one wording of the IRS rule everywhere,
no word left of 1.x's one wallet and one exchange in what ships, and the
release tests' and the way back's words kept to what the app does.
"""

import re
import subprocess
from pathlib import Path

from backend.migrate import PRE_2_0_KIND, copy_for
from backend.tests.test_disclaimer import BETWEEN_WORDS, TEXT, ts_constant, unreleased
from backend.tests.test_test_files import needs_a_checkout

ROOT = Path(__file__).parents[2]

# 5.14, from 3.2: the rule, never what BitcoinTX promises (FIFO is its
# default, not the rule: 3.7 rules out choosing coins)
IRS_RULE = ("From 2025, cost basis is figured wallet by wallet and account by account; unless you identify the "
            "coins you sell, first in, first out within each, by the date first acquired (Treas. Reg. "
            "§1.1012-1(j)).")
# B7b's help text for a new wallet, 5.1's words exactly (never reworded)
WALLET_HELP_RULE = "since 2025 the IRS figures cost basis wallet by wallet."

# Where the rule is stated, each in the one wording
STATES_THE_RULE = ["README.md", "docs/USING.md", "mcp_server/btctx_mcp/guide.py", "startos/startos/manifest/i18n.ts"]

# 1.x's limit, in any of the words it was said in
ONE_WALLET = re.compile("|".join([
    r"one wallet,? (?:and )?one exchange", r"one self-custody wallet and one exchange", r"tracks one (?:self-custody )?wallet",
    r"\bpools? (?:it|them)\b", r"\bpooled here\b", r"\bcounts as one\b", r"\bwallet or exchange btc\b",
    r"one-wallet-one-exchange", r"\bexchange by exchange\b",
]), re.I)


def flat(text: str) -> str:
    """Words only: a line break, a quote's "> ", joined strings, bold."""
    return BETWEEN_WORDS.sub(" ", text).strip()


def shipped_texts() -> dict[str, str]:
    """Every tracked text that ships or tells users how BitcoinTX works, as
    words. Left out: history (the CHANGELOG's released versions, the
    package's released notes, migrations, the plan in docs/temp) and tests,
    which may quote old words to check they're gone."""
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    history = ("docs/temp/", "backend/migrations/", "startos/startos/versions/")
    tests = ("backend/tests/", "mcp_server/tests/", "frontend/e2e/", "frontend/src/test/")
    return {path: flat(unreleased(path, (ROOT / path).read_text()))
            for path in tracked.splitlines()
            if path.endswith(TEXT) and not path.startswith(history + tests)
            and not re.search(r"\.test\.tsx?$", path)}


def test_the_irs_rule_is_stated_in_its_one_wording():
    rule = flat(IRS_RULE)
    assert rule in flat(ts_constant("ACCOUNTS_NOTICE"))
    for path in STATES_THE_RULE:
        assert rule in flat((ROOT / path).read_text()), path


@needs_a_checkout
def test_no_other_wording_of_the_rule():
    """Every "wallet by wallet" or "account by account" is the rule's one
    wording (or the wallet's help text, 5.1's own words)."""
    rule, help_rule = flat(IRS_RULE), flat(WALLET_HELP_RULE)
    found = [f"{path}: …{text[max(0, hit.start() - 60):hit.end() + 20]}…"
             for path, text in shipped_texts().items()
             for hit in re.finditer(r"wallet by wallet|account by account", text.replace(rule, "").replace(help_rule, ""))]
    assert not found, found


@needs_a_checkout
def test_nothing_left_of_one_wallet_and_one_exchange():
    found = [f"{path}: {hit.group(0)}" for path, text in shipped_texts().items() for hit in ONE_WALLET.finditer(text)]
    assert not found, found


def test_the_release_tests_counts_are_the_apps():
    """REF-2's ledger count and the tool count AGENT-TESTS expects (119 went
    unseen when B7a's rows made it 141)."""
    import json

    tests = (ROOT / "docs/AGENT-TESTS.md").read_text()
    rows = len(json.loads((ROOT / "testdata/reference_ledger.json").read_text())["transactions"])
    assert re.findall(r"✓ (\d+) transactions loaded", tests) == [str(rows)]
    tools = len(re.findall(r"^@mcp\.tool\(", (ROOT / "mcp_server/btctx_mcp/server.py").read_text(), re.M))
    counts = re.findall(r"Expect:? (\d+) tools", flat(tests))
    assert counts and set(counts) == {str(tools)}, counts


def maintenance_way_back() -> str:
    text = (ROOT / "docs/MAINTENANCE.md").read_text()
    return text.split("\n## Going back to 1.x\n", 1)[1].split("\n## ", 1)[0]


def test_the_way_back_names_what_the_app_does():
    """5.16's steps for Docker and the Mac app: the pre-2.0 copy by the name
    the upgrade gives it, the side files the restore removes too, and the
    Docker copy run through the 1.x image, as its own user (#446)."""
    kind, label, kept = copy_for("0012")
    assert (kind, label, kept) == (PRE_2_0_KIND, "from-0012", None)
    steps = maintenance_way_back()
    assert f"backups/btctx-{kind}-from-" in steps
    for side in ("btctx.db-journal", "btctx.db-wal", "btctx.db-shm"):
        assert side in steps, side
    assert re.search(r"docker run --rm -v \S+:/data ghcr\.io/digimonk73/btctx-mcp:v1\.\d+\.\d+ sh -c 'cp ", steps)
    assert "--user" in steps
    assert "~/Library/Application Support/BitcoinTX/btctx.db" in steps
