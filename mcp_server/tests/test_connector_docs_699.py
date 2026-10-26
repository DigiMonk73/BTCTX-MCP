"""
The connector's documents against what 2.0 does (D3 of the docs overhaul,
#699; #676's gaps in the setup guide, found by an AI following it).

What an AI reads to set the connector up (AI_SETUP.md), what a user reads
(the connector's README), and what the AI reads to enter transactions (the
ledger guide and the tools' descriptions) say what the 2.0 connector does.
"""

import re
from pathlib import Path

import pytest

from btctx_mcp import __version__, guide
from btctx_mcp.guide import LEDGER_GUIDE

from test_server import anyio_backend, backend_db, mcp_client  # noqa: F401  (fixtures)

pytestmark = pytest.mark.anyio

HERE = Path(__file__).parents[1]
AI_SETUP = (HERE / "AI_SETUP.md").read_text()
README = (HERE / "README.md").read_text()
GUIDE = " ".join(LEDGER_GUIDE.split())


def flat(text: str) -> str:
    return " ".join(text.split())


def section(text: str, heading: str) -> str:
    """A markdown section: from its heading to the next of its level or above."""
    level = heading.split(" ")[0]
    start = text.index(heading)
    ends = [m.start() for m in re.finditer(rf"^#{{1,{len(level)}}} ", text[start + 1:], re.M)]
    return text[start:start + 1 + ends[0]] if ends else text[start:]


# AI_SETUP.md (#676)

def test_every_client_restarts_before_the_check():
    """#676, 1: a running Claude Code session doesn't get the tools of a
    server it just added, so the check of section 4 can't run in it."""
    mac = flat(section(AI_SETUP, "## 2A."))
    assert "Then, before section 4: start a new session (Claude Code, Grok Build) or quit and reopen the " \
           "app (Claude Desktop, any other)" in mac
    assert "Then, before section 4" in flat(section(AI_SETUP, "## 2B."))


def test_the_address_check_is_for_a_server_install_only():
    """#676, 2: the Mac app's prompt gives no address to check."""
    check = flat(section(AI_SETUP, "## 1."))
    assert "**BitcoinTX is reachable** (Docker and StartOS only: the Mac app's prompt has no address)" in check
    assert "0.9.2 or later for the Mac app" not in check
    assert "The Mac app: BitcoinTX (a 2.0 alpha's or beta's: BitcoinTX Preview) must be open" in check


def test_already_set_up_is_for_a_release_only():
    """#676, 3: read as applying to a pre-release, it would move the
    tester's own `bitcointx` to the alpha's connector."""
    assert "**Already set up?** For a release only, never a 2.0 alpha or beta (the rule just above)." \
           in flat(AI_SETUP)


def test_a_pre_releases_update_names_its_own_server():
    """Session 22's note on #699: the update steps named only `bitcointx`,
    which reaches the tester's own BitcoinTX."""
    assert "`mcpServers.bitcointx-preview.args`" in AI_SETUP
    updating = flat(section(README, "## Updating"))
    assert "`bitcointx-preview`" in updating and "never the `bitcointx` server" in updating


# The connector's README

def test_the_readme_calls_the_ai_connection_optional():
    """Decision 31 (the owner, 2026-10-26): wherever the AI connection is
    introduced, it's optional, off until you turn it on."""
    intro = flat(README.split("## Tools")[0])
    assert "optional" in intro and "off until you turn it on" in intro


def test_the_readme_says_how_long_the_connector_waits():
    """The writes that can answer the past-year question, the preview and
    Ledger Review wait 20 minutes (client.LONG_TIMEOUT, #637)."""
    from btctx_mcp.client import LONG_TIMEOUT, TIMEOUT

    assert (LONG_TIMEOUT, TIMEOUT) == (1200.0, 120.0)
    assert "up to 20 minutes" in flat(README) and "2 minutes" in flat(README)


def test_the_readme_names_the_method():
    """Decision 30 (#713): "Per-wallet FIFO"."""
    assert "simulate FIFO" not in README
    assert "Per-wallet FIFO" in README


# The ledger guide

@pytest.mark.parametrize("version, tag", [
    ("2.0.0", "v2.0.0"), ("2.0.0a3", "v2.0.0-alpha.3"), ("2.0.0b12", "v2.0.0-beta.12"), ("1.2.10", "v1.2.10"),
    ("unknown", None), ("2.0.0.dev1", None),
])
def test_a_connector_version_names_its_release_tag(version, tag):
    assert guide.release_tag(version) == tag


def test_the_guide_links_the_readme_at_its_own_release():
    """3.5 of the docs plan: GitHub shows main's README, which is 1.x's
    until 2.0's release and has no "Wallets, exchanges and banks"."""
    assert guide.readme_url("2.0.0b1", "wallets-exchanges-and-banks") == (
        "https://github.com/DigiMonk73/BTCTX-MCP/blob/v2.0.0-beta.1/README.md#wallets-exchanges-and-banks")
    assert guide.readme_url("unknown", "x") == "https://github.com/DigiMonk73/BTCTX-MCP/blob/main/README.md#x"
    assert guide.readme_url(__version__, "wallets-exchanges-and-banks") in GUIDE


def test_the_guide_names_the_method_and_the_screen():
    assert "(FIFO cost basis" not in GUIDE and "BitcoinTX's first in, first out" not in GUIDE
    assert "Per-wallet FIFO" in GUIDE
    assert "Privacy & network" not in GUIDE and "Settings -> Privacy & Network" in GUIDE


def test_the_guide_covers_get_coins_moveds_answer():
    """T8's notes 1 and 2 (#694): it answers for a wallet's Withdrawal too;
    its held is the wallet's coins, never a menu; dated_today is the form's."""
    assert "get_coins_moved shows a saved Transfer's" not in GUIDE
    assert "get_coins_moved shows the same for a saved Transfer or BTC Withdrawal from a wallet" in GUIDE
    assert "Don't offer the wallet's coins (coins.held, or get_coins_moved's held) as a menu" in GUIDE
    assert "dated_today is for BitcoinTX's own form: ignore it" in GUIDE


def test_the_guide_says_a_late_choice_is_a_reminder():
    """T8's note 3: a choice recorded after the coins left shows in Ledger
    Review's reminder, which the AI passes on, never fixes."""
    assert "Reminder: coins chosen after they left" in GUIDE
    assert "pass it on as it says, never as something to fix" in GUIDE


# The tools' descriptions

async def test_the_tools_say_what_2_0_does(mcp_client):  # noqa: F811
    tools = {t.name: flat(t.description) for t in (await mcp_client.list_tools()).tools}
    assert tools["get_coins_moved"].startswith(
        "The coins a saved Transfer, or BTC Withdrawal from one of the user's wallets, takes")
    assert "held:" in tools["get_coins_moved"] and "dated_today" in tools["get_coins_moved"]
    assert "coins chosen after they left" in tools["review_ledger"]
    # T8's note 4: a deposit's cost basis carries over into a Buy
    assert "making a transaction a Buy needs cost_basis_usd" not in tools["update_transaction"]
    assert "a Buy's cost_basis_usd (a deposit's own is kept when you send none)" in tools["update_transaction"]
    assert "the FIFO result" not in tools["preview_transactions"]
