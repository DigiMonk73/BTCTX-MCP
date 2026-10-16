"""MCP server for BitcoinTX: add transactions from pasted text or plain English."""

from importlib.metadata import PackageNotFoundError, version

try:
    # The installed package's own version (pyproject.toml): a number written
    # here stayed at 0.1.0 while the releases moved on (#133)
    __version__ = version("btctx-mcp")
except PackageNotFoundError:  # run from a source tree, not installed
    __version__ = "unknown"
