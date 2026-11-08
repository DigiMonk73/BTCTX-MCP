"""MCP server for BitcoinTX: add transactions from pasted text or plain English."""

import zoneinfo
from importlib.metadata import PackageNotFoundError, version

# The tax timezone's rules come from the tzdata package alone, as BitcoinTX
# reads them (its backend/__init__.py, #889). Python's zoneinfo reads the
# computer's own zone files first: older ones than BitcoinTX's would read a
# time the AI gives with no timezone, in a zone whose rules have changed since,
# by the old rules, and the row would be saved an hour off (#908).
zoneinfo.reset_tzpath([])
# A zone read before this line (an import of another package's) is cached
# from the computer's files; none may outlive the switch.
zoneinfo.ZoneInfo.clear_cache()

try:
    # The installed package's own version (pyproject.toml): a number written
    # here stayed at 0.1.0 while the releases moved on (#133)
    __version__ = version("btctx-mcp")
except PackageNotFoundError:  # run from a source tree, not installed
    __version__ = "unknown"
