"""
The connector of a 2.0 pre-release (2.0 plan 7.4, B10a, point 2; #532).

On PyPI a beta is btctx-mcp 2.0.0bN (PEP 440's form of 2.0.0-beta.N). It
belongs with BitcoinTX Beta, the Mac beta app installed beside BitcoinTX:
its default key file is that app's, so a beta connector never reaches the
installed app's real ledger. And it reads a beta version on either side:
PEP 440 sorts 2.0.0b1 below 2.0.0, and BitcoinTX says 2.0.0-beta.1 where
the connector says 2.0.0b1.
"""

from pathlib import Path

import pytest

from btctx_mcp import client, server

SUPPORT = Path("Library") / "Application Support"


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("BTCTX_MCP_FILE", raising=False)
    return tmp_path


@pytest.mark.parametrize("version, app", [
    ("2.0.0b1", "BitcoinTX Beta"), ("2.0.0b12", "BitcoinTX Beta"),
    ("2.0.0", "BitcoinTX"), ("1.2.10", "BitcoinTX"), ("unknown", "BitcoinTX"),
])
def test_a_beta_connectors_key_file_is_the_beta_apps(home, version, app):
    assert client.mac_app(version) == app
    assert client.default_key_file(version) == home / SUPPORT / app / "mcp.json"


def test_the_connector_takes_its_own_version(home, monkeypatch):
    """With no version given, the installed connector's own: the path
    from_env takes when no key is configured (the Mac app's key file)."""
    monkeypatch.delenv("BTCTX_AI_KEY", raising=False)
    monkeypatch.delenv("BTCTX_PASSWORD", raising=False)
    for version, app in (("2.0.0b1", "BitcoinTX Beta"), ("1.2.10", "BitcoinTX")):
        monkeypatch.setattr(client, "__version__", version)
        assert client.default_key_file() == home / SUPPORT / app / "mcp.json"
        assert client.BtctxClient.from_env()._key_file == home / SUPPORT / app / "mcp.json"


def test_btctx_mcp_file_still_wins(home, monkeypatch):
    monkeypatch.setenv("BTCTX_MCP_FILE", str(home / "elsewhere.json"))
    assert client.default_key_file("2.0.0b1") == home / "elsewhere.json"


def test_a_beta_connector_says_to_open_the_beta_app(monkeypatch):
    monkeypatch.setattr(client, "__version__", "2.0.0b1")
    assert "Open the BitcoinTX Beta app and try again" in client.BtctxClient._not_found(["x: not found"])
    monkeypatch.setattr(client, "__version__", "1.2.10")
    assert "Open the BitcoinTX app and try again" in client.BtctxClient._not_found(["x: not found"])


def test_the_same_beta_on_both_sides_is_no_mismatch():
    assert server.mismatch_notice("2.0.0b1", "2.0.0-beta.1") is None
    assert server.mismatch_notice("2.0.0b3", "2.0.0-beta.3") is None


def test_another_beta_gets_the_pin_pip_takes():
    older = server.mismatch_notice("2.0.0b1", "2.0.0-beta.2")
    assert older.startswith("Your BitcoinTX connector is v2.0.0b1 but BitcoinTX is v2.0.0-beta.2.")
    assert "change btctx-mcp==2.0.0b1 in its uvx command to btctx-mcp==2.0.0b2" in older
    newer = server.mismatch_notice("2.0.0b3", "2.0.0-beta.2")
    assert "Update BitcoinTX, or set the connector back to v2.0.0b2" in newer


def test_a_release_sorts_after_its_betas():
    assert "Update BitcoinTX" in server.mismatch_notice("2.0.0", "2.0.0-beta.4")
    assert "to btctx-mcp==2.0.0," in server.mismatch_notice("2.0.0b4", "2.0.0")
    assert "to btctx-mcp==2.0.0b1," in server.mismatch_notice("1.2.10", "2.0.0-beta.1")
    assert "Update BitcoinTX" in server.mismatch_notice("2.0.0b1", "1.2.10")


def test_one_x_versions_read_as_before():
    assert server.mismatch_notice("1.2.9", "1.2.10").endswith(
        "change btctx-mcp==1.2.9 in its uvx command to btctx-mcp==1.2.10, then restart the AI app.")
    assert server.mismatch_notice("1.2.10", "1.2.9").endswith(
        "Update BitcoinTX, or set the connector back to v1.2.9 in your AI app's settings.")
    # a version that's neither: the notice still names it, unchanged
    assert "to btctx-mcp==dev," in server.mismatch_notice("1.2.10", "dev")
